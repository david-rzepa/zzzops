"""G1025: git-flow release branching (design revision 3, §13; `.zzzops/reviews/1025/design.md`).

The capability is `release_lines` (recorded at approve_design; the design text says `branching`). The policy block is
`settings.branching`.

Interfaces these tests rely on, taken from the design:
- `frontier.portfolio(..., ledger=, upstream=)` (§3.1, §5.3, §8): `ledger` is {g: {"release", "state", "closed", "line",
  "hotfix"}} built from the goal-commit trailers (`line` is the `Line:` trailer value, e.g. "release:1"); `upstream` is
  {g: {"target", "tip", "behind", "merged_in_target": {dep: bool}}}.
- Goal schema 2 with `flow` (§2); trailers `Release`, `Closed`, `Line`, `Hotfix` (§3.1).
- Verbs `release cut N --answer F` and `hotfix start X --answer F` (§3.3, §7); items `release_cut`, `hotfix_start`,
  `duplicate_line` (§3.2, §3.3); `next.releases` (§9); `target` on cards, actions and `show` (§4).
- The shipped `graphs.release` (approve_start, sync, approve_finish, finish) with ops `git.line_sync`, `git.line_finish`
  and the sync branch `zzzops/sync/g<line>/<into>` (§2, §5.4, §6, §7).
- From G1031's review: `finish` records the line tip before it merges, and back-merges use that recorded sha, so they
  work after GitHub auto-deletes the line branch.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest

import engine_fixtures as fx
from engine_sim import Sim
from test_engine_base import OP
from test_engine_github import GitHubJourney

BRANCHING = {"production": "main", "release_prefix": "release/", "hotfix_prefix": "hotfix/"}
LINE_NODES = ["approve_start", "sync", "approve_finish", "finish"]
CUT_ANSWER = {"decision": "approved", "quote": "cut it", "decided_by": "Dave"}


# --------------------------------------------------------------------------------------------- helpers


def shipped(name):
    return json.loads((fx.SHIPPED / name).read_text(encoding="utf-8"))


def release_graph() -> dict:
    """The shipped `graphs.release` (a KeyError until G1025 ships it)."""
    return copy.deepcopy(shipped("workflow.json")["graphs"]["release"])


def release_workflow(wf=None) -> dict:
    """The frozen 12-node test graph plus the shipped release graph."""
    wf = copy.deepcopy(wf or fx.load_template("workflow.json"))
    wf["graphs"]["release"] = release_graph()
    return wf


def release_prompts() -> dict:
    files = {}
    for nd in release_graph()["nodes"].values():
        if nd.get("prompt"):
            files[f".zzzops/prompts/{nd['prompt']}"] = (fx.SHIPPED / "prompts" / nd["prompt"]).read_text(encoding="utf-8")
    return files


def require_release_lines(policy: dict) -> dict:
    """Make the policy require capability `release_lines` under whichever scheme the engine has (G1027 §5 covers both
    merge orders): `settings.engine.requires` when declared capabilities exist, else `engine.min` at this engine."""
    from engine import schemas                     # never ENGINE_VERSION here: G1027 deletes it
    eng = schemas.SETTINGS_SHAPE["engine"]
    settings_engine = policy["settings"]["engine"]
    if isinstance(eng, dict) and "requires" in eng:
        requires = settings_engine.setdefault("requires", [])
        if "release_lines" not in requires:
            requires.append("release_lines")
        settings_engine.pop("min", None)            # a leftover engine.min would only add a deprecation warning
    else:
        import engine
        settings_engine["min"] = engine.ENGINE_VERSION
    return policy


def branching_policy(**extra) -> dict:
    p = fx.load_template("POLICY.json")
    p["settings"]["integration_branch"] = "dev"
    p["settings"]["branching"] = dict(BRANCHING, **extra)
    return require_release_lines(p)


def find_kind(obj, kind) -> list:
    """Every dict with `kind == kind` anywhere in a `next` (or other) output."""
    out = []
    if isinstance(obj, dict):
        if obj.get("kind") == kind:
            out.append(obj)
        for v in obj.values():
            out += find_kind(v, kind)
    elif isinstance(obj, list):
        for v in obj:
            out += find_kind(v, kind)
    return out


def kinds(warnings) -> list:
    return [w.get("kind") if isinstance(w, dict) else w for w in warnings or []]


def ledger_of(docs: dict) -> dict:
    """The trailer ledger of §3.1, as `read_state` would build it from these documents' goal commits."""
    out = {}
    for g, d in docs.items():
        flow = d.get("flow") or {}
        out[g] = {"release": d["release"], "state": d["state"], "closed": (d.get("closed") or {}).get("reason"),
                  "line": f"{flow['line']}:{flow['name']}" if flow.get("line") else None, "hotfix": flow.get("hotfix")}
    return out


# --------------------------------------------------------------------------------------------- pure: the frontier


class BSim(Sim):
    """The simulator with the release graph, branching settings, the ledger and an `upstream` map."""

    def __init__(self, branching=True):
        super().__init__(workflow=release_workflow(), policy=branching_policy() if branching else None)
        self.upstream = {}

    def eval(self):
        from engine.frontier import portfolio
        return portfolio(self.docs, self.graphs, self.leases, self.settings, self.now, self.invalid, self.newer,
                         ledger=ledger_of(self.docs), upstream=self.upstream)

    def line(self, gid, n=1, state="open", kind="release", name=None):
        d = self.goal(gid, release=n, graph="release", state=state)
        name = name or str(n)
        d["schema"] = 2
        d["flow"] = {"line": kind, "name": name, "branch": f"{kind}/{name}",
                     "from": "dev" if kind == "release" else "main", "cut": self.sha()}
        return d

    def close(self, g, reason="done"):
        from engine.canon import iso
        self.docs[g].update(state="closed", closed={"reason": reason, "note": "n", "by": "d", "at": iso(self.now)})

    def behind(self, g, target="release/1", **merged):
        self.upstream[g] = {"target": target, "tip": self.sha(), "behind": True,
                            "merged_in_target": {int(k[1:]): v for k, v in merged.items()}}


class FrontierTests(unittest.TestCase):
    def drive_to_ready(self, s, g, node):
        for _ in range(60):
            st = s.st(g, node)
            if st["name"] in ("ready", "needs_human"):
                return st
            acts = [a for a in s.actionable(g) if a != node]
            self.assertTrue(acts, (node, s.names(g)))
            s.step(g, acts[0])
        self.fail(s.names(g))

    def test_pass3_rewrites_only_base_and_workspace_nodes_downstream(self):
        s = BSim()
        s.line(9000)
        s.goal(1001, release=1)
        self.drive_to_ready(s, 1001, "implement")
        before = s.st(1001)
        self.assertEqual("current", before["base"]["name"])
        self.assertEqual("ready", before["implement"]["name"])
        s.behind(1001)
        after = s.st(1001)
        self.assertEqual(("ready", "upstream"), (after["base"]["name"], after["base"]["reason"]))
        self.assertEqual(["upstream"], after["base"]["stale_because"])
        self.assertEqual("blocked", after["implement"]["name"])
        self.assertEqual([{"node": "base", "reason": "restack"}],
                         [{k: m[k] for k in ("node", "reason")} for m in after["implement"]["missing"]])
        for n in ("design", "review_design", "approve_design", "test_design", "review_tests"):
            self.assertEqual(before[n]["name"], after[n]["name"], n)
        # pass 2 is unchanged: with `upstream` empty, the same documents give the same states
        s.upstream = {}
        self.assertEqual(before["implement"]["name"], s.st(1001, "implement")["name"])

    def test_a_ready_workspace_op_is_blocked_while_base_restacks(self):
        s = BSim()
        s.line(9000)
        s.goal(1001, release=1)
        self.drive_to_ready(s, 1001, "review_impl")
        s.settings["verification"]["commands"] = ["make check"]       # run_tests is ready (stale policy)
        s.reopen(1001, "test_design")                                 # an agent workspace node is ready
        self.assertEqual("ready", s.st(1001, "run_tests")["name"])
        s.behind(1001)
        st = s.st(1001)
        self.assertEqual("upstream", st["base"]["reason"])
        for n in ("test_design", "run_tests"):
            self.assertEqual("blocked", st[n]["name"], n)
            self.assertIn("restack", [m["reason"] for m in st[n]["missing"]], n)

    def test_one_scheduled_restack_per_agent_attempt(self):
        s = BSim()
        s.line(9000)
        s.goal(1001, release=1)
        self.drive_to_ready(s, 1001, "implement")
        s.behind(1001)
        self.assertEqual("upstream", s.st(1001, "base")["reason"])
        s.op(1001, "base", same=True)
        s.docs[1001]["records"]["base"]["output"]["scheduled_for"] = {"node": "implement", "after_attempt": 0}
        s.behind(1001)                                                # the target moved again
        st = s.st(1001)
        self.assertEqual("current", st["base"]["name"])
        self.assertEqual("ready", st["implement"]["name"])
        s.step(1001, "implement")
        s.reopen(1001, "implement")                                   # a new implement attempt is due
        self.assertEqual("upstream", s.st(1001, "base").get("reason"))

    def test_no_restack_for_a_goal_parked_at_approve_merge(self):
        s = BSim()
        s.line(9000)
        s.goal(1001, release=1)
        self.drive_to_ready(s, 1001, "approve_merge")
        s.behind(1001)
        self.assertEqual("current", s.st(1001, "base")["name"])

    def test_no_restack_without_branching(self):
        s = BSim(branching=False)
        s.goal(1001)
        self.drive_to_ready(s, 1001, "implement")
        s.behind(1001, target="dev")
        self.assertEqual("current", s.st(1001, "base")["name"])

    def test_effective_release_gate_follows_the_cut_line(self):
        s = BSim()
        s.goal(1002, release=2)
        for _ in range(60):
            st = s.st(1002, "merge")
            if st["name"] in ("ready", "waiting"):
                break
            s.step(1002, s.actionable(1002)[0])
        self.assertEqual(("waiting", "release"), (st["name"], st["reason"]))
        s.line(9000, 1)                                               # release 1 is cut: effective is 2
        self.assertEqual("ready", s.st(1002, "merge")["name"])
        s.close(9000)                                                 # a finished line keeps effective at 2
        self.assertEqual("ready", s.st(1002, "merge")["name"])

    def test_line_complete_waits_for_open_members(self):
        s = BSim()
        s.line(9000)
        s.goal(1001, release=1)
        s.step(9000, "approve_start")
        s.step(9000, "sync")
        st = s.st(9000, "approve_finish")
        self.assertEqual("waiting", st["name"])
        s.close(1001, "cancelled")
        self.assertEqual(("needs_human", "approve"), (s.st(9000, "approve_finish")["name"],
                                                      s.st(9000, "approve_finish")["kind"]))
        s.step(9000, "approve_finish")
        self.assertEqual("ready", s.st(9000, "finish")["name"])
        s.goal(1002, release=1)                                       # a late member
        st = s.st(9000, "finish")
        self.assertEqual(("waiting", "line_members_open"), (st["name"], st["reason"]))
        s.close(1002, "superseded")                                   # superseded counts like cancelled
        self.assertEqual("ready", s.st(9000, "finish")["name"])

    def test_release_sync_is_a_frontier_wait_that_ends_on_its_own(self):
        s = BSim()
        s.line(9000)
        s.goal(1001, release=1)
        s.drive(1001, until="merge")
        s.close(1001)
        s.goal(1002, release=2, deps=[1001])
        self.drive_to_ready(s, 1002, "approve_design")
        s.step(1002, "approve_design")
        s.upstream[1002] = {"target": "dev", "tip": s.sha(), "behind": False, "merged_in_target": {1001: False}}
        st = s.st(1002, "base")
        self.assertEqual(("waiting", "release_sync"), (st["name"], st.get("reason")))
        s.upstream[1002]["merged_in_target"] = {1001: True}           # the sync landed; nothing else changed
        self.assertEqual("ready", s.st(1002, "base")["name"])

    def test_target_fp_part_only_off_the_integration_branch(self):
        s = BSim()
        s.goal(1001, release=2)                                       # targets dev
        s.line(9000)
        s.goal(1002, release=1)                                       # targets release/1
        st1 = self.drive_to_ready(s, 1001, "base")
        st2 = self.drive_to_ready(s, 1002, "base")
        parts = lambda st: st.get("parts") or st["ready"]["parts"]
        self.assertNotIn("target", parts(st1))
        self.assertEqual("release/1", parts(st2)["target"])


# golden digest of every node's input_fp and fp_parts over a fixed journey on the frozen 12-node graph, computed on
# b452cd7, before G1025 (§13 item 9). The shipped graph is not pinned: G1022 rewrites it. After a goal legitimately
# changes these fingerprints and this branch is restacked onto it, regenerate the digest AT THE NEW BASE COMMIT (never
# at this branch's head, which would pin G1025's own changes): check out the base, then run
#   python -c "import sys; sys.path.insert(0, '.agents'); import engine_fixtures as fx, test_engine_branching as t; \
#              print(t.journey_fps(fx.load_template('workflow.json')))"
GOLDEN_FP = {"graph12": "1f5dada7505f698b5ff2dca604c2d2aedffce4b11b0e9f67e287bd643ccfb128"}


def journey_fps(workflow, policy=None, ledger=False):
    s = Sim(workflow=workflow, policy=policy)
    if ledger:
        from engine.frontier import portfolio
        s.eval = lambda: portfolio(s.docs, s.graphs, s.leases, s.settings, s.now, s.invalid, s.newer,
                                   ledger=ledger_of(s.docs), upstream={})
    s.goal(1001)
    s.drive(1001)
    recs = s.docs[1001]["records"]
    data = json.dumps({n: [r["input_fp"], r.get("fp_parts")] for n, r in sorted(recs.items())}, sort_keys=True)
    return hashlib.sha256(data.encode()).hexdigest()


class NoSettingsRegressionTests(unittest.TestCase):
    def test_fp_parts_are_byte_identical_without_branching(self):
        self.assertEqual(GOLDEN_FP["graph12"], journey_fps(fx.load_template("workflow.json")))
        self.assertEqual(journey_fps(fx.load_template("workflow.json")), journey_fps(fx.load_template("workflow.json")))

    def test_branching_on_and_targeting_dev_keeps_every_fingerprint(self):
        p = branching_policy()
        self.assertEqual(GOLDEN_FP["graph12"], journey_fps(release_workflow(), p, ledger=True))


# --------------------------------------------------------------------------------------------- pure: validation


class ValidationTests(unittest.TestCase):
    def errors(self, policy):
        from engine import schemas
        return [str(x) for x in schemas.validate_policy(policy)]

    def test_branching_block_is_accepted(self):
        self.assertEqual([], self.errors(branching_policy()))

    def test_branching_shapes_and_overlaps_are_refused(self):
        self.assertEqual([], self.errors(branching_policy()))       # so the refusals below are about the values
        bad = [{"release_prefix": "release"},                 # a prefix ends in /
               {"release_prefix": ""},
               {"hotfix_prefix": "zzzops/hotfix/"},          # under zzzops/
               {"production": "dev"},                        # equal to the integration branch
               {"release_prefix": "rel/", "hotfix_prefix": "rel/hot/"},   # overlapping prefixes
               {"production": "release/1"},                  # release_prefix + a number == production
               {"production": "bad..name"}]
        for extra in bad:
            with self.subTest(extra=extra):
                errs = self.errors(branching_policy(**extra))
                self.assertTrue(any("branching" in e for e in errs), errs)
        p = branching_policy()
        p["settings"]["branching"]["extra"] = 1
        self.assertTrue(self.errors(p))

    def test_capability_release_lines_is_declared(self):
        caps = fx.PLUGIN_CODE / "engine" / "capabilities"
        if caps.is_dir():
            self.assertTrue((caps / "release_lines.txt").is_file())
        else:
            from engine import ENGINE_VERSION
            self.assertGreater(tuple(map(int, ENGINE_VERSION.split("."))), (1, 1, 0))

    def test_goal_schema_2_flow_forms(self):
        from engine import GOAL_SCHEMAS, schemas
        self.assertIn(2, GOAL_SCHEMAS)
        wf = release_workflow()
        base = {"schema": 2, "id": 1, "title": "t", "graph": "default", "state": "open", "closed": None, "spec": "s",
                "priority": "P2", "release": 1, "depends_on": [], "skip": {}, "links": {"issue": None}, "budget": None,
                "records": {}}
        member = dict(base, flow={"hotfix": "login-crash"})
        line = dict(base, graph="release", flow={"line": "release", "name": "1", "branch": "release/1", "from": "dev",
                                                  "cut": "a" * 40})
        for doc in (member, line):
            errs, _ = schemas.validate_goal(doc, None, {1: doc}, wf)
            self.assertEqual([], list(errs), doc["flow"])
        for flow in ({"hotfix": "a..b"}, {"line": "support", "name": "1", "branch": "support/1", "from": "dev",
                                           "cut": "a" * 40}, {"hotfix": "x", "line": "release"}):
            doc = dict(base, flow=flow)
            errs, _ = schemas.validate_goal(doc, None, {1: doc}, wf)
            self.assertTrue(errs, flow)

    def test_workflow_node_field_placement(self):
        from engine import schemas
        wf = release_workflow()
        p = branching_policy()
        prompts = lambda name: (fx.TEMPLATES / "prompts" / name).is_file() or (fx.SHIPPED / "prompts" / name).is_file()
        self.assertEqual([], [str(e) for e in schemas.validate_workflow(wf, p, prompts)])
        bad = copy.deepcopy(wf)
        bad["graphs"]["release"]["nodes"]["approve_start"]["schedule"] = "upstream"     # op nodes only
        self.assertTrue(schemas.validate_workflow(bad, p, prompts))
        bad = copy.deepcopy(wf)
        bad["graphs"]["release"]["nodes"]["sync"]["schedule"] = "always"
        self.assertTrue(schemas.validate_workflow(bad, p, prompts))
        bad = copy.deepcopy(wf)
        bad["graphs"]["default"]["nodes"]["implement"]["line_complete"] = True          # human and op nodes only
        self.assertTrue(schemas.validate_workflow(bad, p, prompts))

    def test_shipped_templates(self):
        g = release_graph()
        self.assertEqual(LINE_NODES, list(g["nodes"]))
        self.assertEqual("git.line_sync", g["nodes"]["sync"]["op"])
        self.assertEqual("upstream", g["nodes"]["sync"]["schedule"])
        self.assertEqual("git.line_finish", g["nodes"]["finish"]["op"])
        self.assertTrue(g["nodes"]["approve_finish"]["line_complete"])
        self.assertTrue(g["nodes"]["finish"]["line_complete"])
        for p in ("approve_start.md", "approve_finish.md"):
            self.assertTrue((fx.SHIPPED / "prompts" / p).is_file(), p)
        self.assertNotIn("branching", shipped("POLICY.json")["settings"])
        for nd in shipped("workflow.json")["graphs"]["default"]["nodes"].values():
            self.assertNotIn(nd.get("op"), ("git.line_sync", "git.line_finish"))
            self.assertNotIn("schedule", nd)

    def test_validate_policy_dir_needs_a_release_graph_with_branching(self):
        def run(d):
            p = subprocess.run([sys.executable, str(fx.PLUGIN_CODE / "zzzops.py"), "validate", "--policy", "--dir", d],
                               cwd=tempfile.gettempdir(), capture_output=True, text=True)
            return p.returncode
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        d = os.path.join(tmp, "tpl")
        shutil.copytree(fx.SHIPPED, d)
        pol = shipped("POLICY.json")
        pol["settings"]["branching"] = dict(BRANCHING)
        require_release_lines(pol)
        with open(os.path.join(d, "POLICY.json"), "w") as fh:
            json.dump(pol, fh)
        self.assertEqual(0, run(d))
        wf = shipped("workflow.json")
        del wf["graphs"]["release"]
        with open(os.path.join(d, "workflow.json"), "w") as fh:
            json.dump(wf, fh)
        self.assertNotEqual(0, run(d))


class DocsTests(unittest.TestCase):
    def test_history_row_and_no_pending_row(self):
        docs = fx.ROOT / "docs" / "design"
        history = (docs / "HISTORY.md").read_text(encoding="utf-8")
        log = history[history.index("## 4. Amendments after approval"):]
        self.assertTrue(any(l.startswith("|") and "G1025" in l for l in log.splitlines()))
        readme = (docs / "README.md").read_text(encoding="utf-8")
        self.assertFalse(any(l.startswith("| G1025") for l in readme.splitlines()))


# --------------------------------------------------------------------------------------------- CLI journeys


class Branching(GitHubJourney):
    """A World with the fake GitHub, `settings.branching`, the release graph and a `main` production branch."""
    settings = {}
    branching = True

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.w = fx.World(self.tmp)
        self.gh = fx.FakeGitHub(self.w)
        self.m = {n: n for n in fx.DEFAULT_NODES}
        if self.branching:
            self.w.bootstrap(policy=branching_policy(), workflow=release_workflow(), settings=self.settings)
            self.w.push_dev(release_prompts(), "chore(zzzops): release prompts")
        else:
            self.w.bootstrap(settings=self.settings)
        self.w.seed.git("push", "-q", "origin", "HEAD:refs/heads/main")
        self.A = fx.Agent(self.w, "a", "claude:aaaa/w-1")
        self.B = fx.Agent(self.w, "b", "codex:bbbb/w-2")
        self._pusher = None

    def n(self, x):
        return x

    # ---- helpers
    def tip(self, branch):
        return self.w.remote_git("rev-parse", "--verify", "-q", f"refs/heads/{branch}", check=False) or None

    def goal_tip(self, g):
        return self.tip(f"zzzops/goal/g{g}")

    def is_ancestor(self, a, b):
        return subprocess.run(["git", "--git-dir", self.w.remote, "merge-base", "--is-ancestor", a, b],
                              env=self.w.env).returncode == 0

    def push_branch(self, branch, files, message="fix: on branch"):
        if self._pusher is None:
            self._pusher = self.w.add_clone("p")
        p = self._pusher
        p.git("fetch", "-q", "origin", f"refs/heads/{branch}")
        p.git("checkout", "-q", "--detach", "FETCH_HEAD")
        c = p.commit(files, message)
        p.git("push", "-q", "origin", f"HEAD:refs/heads/{branch}")
        return c

    def nxt(self, *goals, clone="a"):
        argv = ["next"]
        for g in goals:
            argv += ["--goal", str(g)]
        return self.w.ok(clone, *argv)

    def done(self, g, code=None):
        """Deliver, integrate, approve and merge one goal through the real ops."""
        self.deliver(g, code=code)
        self.op(g, "integrate")
        self.approve(g, "approve_merge")
        out = self.op(g, "merge")
        self.assertEqual("done", (out.get("closed") or {}).get("reason"), out)
        return out

    def cut(self, n=1, clone="a", answer=None, ok=True):
        argv = ["release", "cut", str(n), "--answer", self.w.file(answer or CUT_ANSWER)]
        if ok:
            return self.w.ok(clone, *argv)
        return self.w.run(clone, *argv)

    def hotfix_start(self, name, clone="a", ok=True):
        argv = ["hotfix", "start", name, "--answer", self.w.file(CUT_ANSWER)]
        return self.w.ok(clone, *argv) if ok else self.w.run(clone, *argv)

    def cut_release_1(self):
        g = self.goal(release=1)
        self.done(g)
        out = self.cut(1)
        return g, out["goal"]

    def cancel(self, g):
        self.close_as(g, "cancelled")

    def close_as(self, g, reason):
        f = self.w.file({"set": {"state": "closed", "closed.reason": reason, "closed.note": f"{reason} by hand"}})
        self.w.ok("a", "edit", str(g), "--file", f, "--base", self.goal_tip(g))

    def answer_blocked(self, g, node, text="resolution approved"):
        it = [i for i in self.nxt(g)["needs_human"] if i.get("node") == node][0]
        return self.w.ok("a", "answer", str(g), node, "--fp", it["fp"],
                         "--file", self.w.file({"text": text, "quote": "yes", "decided_by": "Dave"}))

    def message(self, commit):
        return self.w.remote_git("log", "-1", "--format=%B", commit)


class NoBranchingTests(Branching):
    branching = False

    def test_no_cut_item_and_byte_identical_goal_commits(self):
        g = self.goal()
        msg = self.message(self.goal_tip(g))
        for t in ("Release:", "Closed:", "Line:", "Hotfix:"):
            self.assertNotIn(t, msg)
        self.done(g)
        msg = self.message(self.goal_tip(g))
        for t in ("Release:", "Closed:", "Line:"):
            self.assertNotIn(t, msg)
        out = self.nxt()
        self.assertEqual([], find_kind(out, "release_cut"))
        self.assertNotIn("releases", out)
        rc, err = self.cut(1, ok=False)
        self.assertNotEqual(0, rc)


class CutItemTests(Branching):
    def test_cut_item_waits_for_open_and_held_goals_then_offers_n(self):
        a = self.goal(release=1)
        held = self.goal(release=1, state="held")
        later = self.goal(release=2)
        self.done(a)
        self.assertEqual([], find_kind(self.nxt(), "release_cut"))         # a held goal blocks the cut
        self.w.ok("a", "edit", str(held), "--set", 'state="open"', "--base", self.goal_tip(held))
        self.assertEqual([], find_kind(self.nxt(), "release_cut"))         # so does an open one
        self.cancel(held)                                                 # a cancelled goal does not
        out = self.nxt()
        items = find_kind(out, "release_cut")
        self.assertEqual(1, len(items), out)
        it = items[0]
        self.assertEqual((1, "release/1", "dev"), (it["release"], it["branch"], it["from"]))
        self.assertEqual(self.tip("dev"), it["tip"])
        self.assertIn(a, it["goals"])
        self.assertIn("release cut 1", it["command"])
        self.assertEqual({"decision", "quote", "decided_by"}, set(it["answer_template"]))
        self.assertNotIn(later, it["goals"])
        self.assertEqual(1, out["releases"]["effective"])

    def test_only_cancelled_goals_do_not_make_a_release_complete(self):
        a = self.goal(release=1)
        self.cancel(a)
        self.assertEqual([], find_kind(self.nxt(), "release_cut"))

    def test_superseded_goal_neither_blocks_the_cut_nor_completes_the_release_alone(self):
        sup = self.goal(release=1)
        a = self.goal(release=1)
        self.close_as(sup, "superseded")
        out = self.nxt()
        self.assertEqual([], find_kind(out, "release_cut"))                # alone it does not complete release 1
        self.assertEqual(1, out["releases"]["effective"])
        self.done(a)
        items = find_kind(self.nxt(), "release_cut")                      # and it does not block the cut
        self.assertEqual(1, len(items))
        self.assertEqual(1, items[0]["release"])
        self.assertIn(a, items[0]["goals"])

    def test_hotfix_members_are_ignored_and_the_item_goes_once_a_line_exists(self):
        a = self.goal(release=1)
        self.goal(release=1, flow={"hotfix": "login-crash"})              # an open hotfix member does not block
        self.done(a)
        self.assertEqual(1, len(find_kind(self.nxt(), "release_cut")))
        self.cut(1)
        out = self.nxt()
        self.assertEqual([], find_kind(out, "release_cut"))
        self.assertEqual(2, out["releases"]["effective"])
        self.assertEqual("release/1", out["releases"]["lines"]["1"]["branch"])

    def test_one_open_release_line_at_a_time(self):
        _, line = self.cut_release_1()
        b = self.goal()                                                   # defaults to the effective release, 2
        self.assertEqual(2, self.show(b)["goal"]["release"])
        self.done(b)
        out = self.nxt()
        self.assertEqual([], find_kind(out, "release_cut"))
        self.assertTrue(any("2" in json.dumps(x) for x in out["releases"]["waiting"]), out["releases"])
        rc, err = self.cut(2, ok=False)
        self.assertEqual("not_ready", err["error"]["code"])


class LedgerTests(Branching):
    def test_trailers_are_written_with_branching(self):
        a = self.goal(release=1)
        self.assertIn("Release: 1", self.message(self.goal_tip(a)))
        c = self.goal(release=1)
        self.cancel(c)
        self.assertIn("Closed: cancelled", self.message(self.goal_tip(c)))
        sup = self.goal(release=1)
        self.close_as(sup, "superseded")
        self.assertIn("Closed: superseded", self.message(self.goal_tip(sup)))
        self.done(a)
        self.assertIn("Closed: done", self.message(self.goal_tip(a)))
        line = self.cut(1)["goal"]
        msg = self.message(self.goal_tip(line))
        self.assertIn("Line: release:1", msg)
        self.assertIn("Request-Key:", msg)
        h = self.goal(release=2, flow={"hotfix": "x1"})
        self.assertIn("Hotfix: x1", self.message(self.goal_tip(h)))

    def test_closed_goals_are_counted_from_trailers_alone(self):
        """A closed goal whose document cannot be read still counts, by its trailers (no document read)."""
        from test_engine_store import push_goal_doc
        a = self.goal(release=1)
        tip = self.goal_tip(a)
        s = self.w.seed
        blob = s.git("hash-object", "-w", "--stdin", input="not json\n")
        tree = s.git("mktree", input=f"100644 blob {blob}\tgoal.json\n")
        c = s.git("commit-tree", tree, "-p", tip, "-m",
                  f"zzzops: merge G{a}\n\nOutcome: done\nState: closed\nRelease: 1\nClosed: done\nEngine: 9.9.9")
        s.git("push", "-q", "--force", "origin", f"{c}:refs/heads/zzzops/goal/g{a}")
        out = self.nxt()
        items = find_kind(out, "release_cut")
        self.assertEqual(1, len(items), out)
        self.assertEqual([a], items[0]["goals"])

    def test_legacy_closed_goals_are_read_in_one_batch(self):
        # three goals closed before branching was on (no trailers), then branching is turned on
        plain = fx.load_template("POLICY.json")
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        self.w = fx.World(tmp)
        self.gh = fx.FakeGitHub(self.w)
        self.w.bootstrap(workflow=release_workflow())
        self.w.push_dev(release_prompts(), "chore: prompts")
        self.A = fx.Agent(self.w, "a", "claude:aaaa/w-1")
        self.B = fx.Agent(self.w, "b", "codex:bbbb/w-2")
        a = self.goal(release=1)
        self.done(a)
        b, c = self.goal(release=1), self.goal(release=1)
        self.cancel(b)
        self.cancel(c)
        pol = branching_policy()
        self.w.push_dev({".zzzops/POLICY.json": json.dumps(pol, indent=2) + "\n"}, "chore(zzzops): branching")

        def git_commands():
            trace = os.path.join(tmp, "git-trace.txt")
            if os.path.exists(trace):
                os.remove(trace)
            out = self.w.ok("a", "next", env={"GIT_TRACE": trace})
            with open(trace) as fh:
                lines = [l for l in fh if "built-in: git" in l or "run_command:" in l]
            return out, len(lines), sum(1 for l in lines if "cat-file" in l and "--batch" in l)

        out, n3, batches = git_commands()
        it = find_kind(out, "release_cut")
        self.assertEqual(1, len(it), out)
        self.assertEqual(sorted([a, b, c]), sorted(it[0]["goals"]))
        # re-close two of them under branching: they now carry trailers, and the legacy set shrinks to one goal
        for g in (b, c):
            self.w.ok("a", "edit", str(g), "--set", 'state="open"', "--base", self.goal_tip(g))
            self.cancel(g)
        _, n1, batches1 = git_commands()
        self.assertEqual(n1, n3, "the legacy fallback must not cost a git call per closed goal")
        self.assertLessEqual(batches, 1 + batches1)


class CutVerbTests(Branching):
    def test_cut_creates_the_branch_and_the_line_goal_and_is_idempotent(self):
        a = self.goal(release=1)
        self.done(a)
        dev = self.tip("dev")
        out = self.cut(1)
        self.assertEqual((1, "release/1", dev), (out["release"], out["branch"], out["cut"]))
        self.assertEqual(dev, self.tip("release/1"))
        line = out["goal"]
        doc = self.show(line)["goal"]
        self.assertEqual(("release", 1, 2), (doc["graph"], doc["release"], doc["schema"]))
        self.assertEqual({"line": "release", "name": "1", "branch": "release/1", "from": "dev", "cut": dev}, doc["flow"])
        self.assertEqual([], doc["depends_on"])
        self.assertEqual("done", doc["records"]["approve_start"]["status"])
        self.assertIsNone(self.tip(f"zzzops/work/g{line}"))
        again = self.cut(1, answer=dict(CUT_ANSWER, quote="again"))
        self.assertEqual(line, again["goal"])
        self.assertTrue((again.get("created") or {}).get("recovered"), again)
        goals = self.w.remote_git("for-each-ref", "--format=%(refname)", "refs/heads/zzzops/goal/")
        self.assertEqual(2, len(goals.split()))                           # the member and one line goal
        # right after the cut, sync runs once with reason `new` and records merged = cut, doing no work
        act = [x for x in self.nxt(line)["actions"] if x["node"] == "sync"]
        self.assertEqual("new", act[0]["reason"])
        out = self.op(line, "sync")
        self.assertEqual(dev, out["ran"]["output"]["merged"])
        self.assertEqual([], [p for p in self.gh.load()["prs"].values() if p["headRefName"].startswith("zzzops/sync/")])

    def test_two_racing_cuts_leave_one_line_goal(self):
        a = self.goal(release=1)
        self.done(a)
        self.nxt(clone="b")
        results = []
        threads = [threading.Thread(target=lambda c=c, q=q: results.append(
            self.cut(1, clone=c, answer=dict(CUT_ANSWER, quote=q), ok=False))) for c, q in (("a", "one"), ("b", "two"))]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual([0, 0], sorted(rc for rc, _ in results), results)
        ids = {out["goal"] for _, out in results}
        self.assertEqual(1, len(ids))
        goals = self.w.remote_git("for-each-ref", "--format=%(refname)", "refs/heads/zzzops/goal/").split()
        self.assertEqual(2, len(goals))
        self.assertEqual(1, sum(1 for _, out in results if (out.get("created") or {}).get("recovered")))

    def test_hand_cut_branch_is_adopted_only_when_it_is_an_ancestor(self):
        a = self.goal(release=1)
        self.done(a)
        dev = self.tip("dev")
        self.w.remote_git("update-ref", "refs/heads/release/1", self.w.remote_git("rev-parse", dev + "~1"))
        anc = self.tip("release/1")
        out = self.cut(1)
        self.assertEqual(anc, out["cut"])
        self.assertIn("line_branch_adopted", kinds(out.get("warnings")))

    def test_diverged_hand_cut_branch_is_refused(self):
        a = self.goal(release=1)
        self.done(a)
        self.w.seed.git("push", "-q", "origin", "HEAD:refs/heads/release/1")
        self.push_branch("release/1", {"stray.txt": "x\n"}, "stray")
        rc, err = self.cut(1, ok=False)
        self.assertEqual("conflict", err["error"]["code"])
        self.assertEqual(1, len(self.w.remote_git("for-each-ref", "--format=%(refname)",
                                                  "refs/heads/zzzops/goal/").split()))

    def test_goal_reopened_between_next_and_cut_refuses(self):
        a, b = self.goal(release=1), self.goal(release=1)
        self.done(a)
        self.cancel(b)
        self.assertEqual(1, len(find_kind(self.nxt(), "release_cut")))
        self.w.ok("a", "edit", str(b), "--set", 'state="open"', "--base", self.goal_tip(b))
        rc, err = self.cut(1, ok=False)
        self.assertEqual("not_ready", err["error"]["code"])
        self.assertIsNone(self.tip("release/1"))

    def test_duplicate_line_goals_and_missing_branch_are_human_items(self):
        from test_engine_store import push_goal_doc
        _, line = self.cut_release_1()
        doc = copy.deepcopy(self.show(line)["goal"])
        twin = max(int(r.rsplit("g", 1)[1]) for r in self.w.remote_git(
            "for-each-ref", "--format=%(refname)", "refs/heads/zzzops/goal/").split()) + 1
        doc.update(id=twin, records={})
        push_goal_doc(self.w, doc)
        out = self.nxt()
        dup = find_kind(out, "duplicate_line")
        self.assertEqual(1, len(dup), out)
        self.assertIn("release/1", json.dumps(dup[0]))
        self.assertNotIn(twin, [a["goal"] for a in out["actions"]])
        self.assertNotIn(line, [a["goal"] for a in out["actions"]])
        # a line branch gone from the remote
        self.w.remote_git("update-ref", "-d", "refs/heads/release/1")
        out = self.nxt()
        self.assertIn("gone", json.dumps(out["needs_human"]))


class TargetTests(Branching):
    def test_release_goal_bases_integrates_and_merges_on_the_release_branch(self):
        _, line = self.cut_release_1()
        fix = self.push_branch("release/1", {"src/fix.py": "f = 1\n"}, "fix: stabilise")
        g = self.goal(release=1)
        self.discovery(g)
        act = [a for a in self.nxt(g)["actions"] if a["node"] == "base"][0]
        self.assertEqual("release/1", act["target"])
        out = self.op(g, "base")
        self.assertEqual(fix, out["ran"]["output"]["base_commit"])
        card = self.A.start(g, "test_design")
        self.assertEqual({"branch": "release/1", "kind": "release", "commit": fix}, card["target"])
        self.assertEqual(fix, card["read_dev"]["commit"])
        self.A.worktree(g).commit({f"tests/t{g}.txt": "t\n"}, "test")
        self.A.submit(g, "test_design", card, {"commands": ["true"]})
        rc, text = self.w.run("b", "show", str(g))
        self.assertIn("target release/1", text["_stdout"])
        self.review(self.B, g, "review_tests")
        c = self.A.start(g, "implement")
        self.A.worktree(g).commit({f"src/m{g}.py": "x = 1\n"}, "feat")
        self.A.submit(g, "implement", c, {"summary": "Built."})
        self.op(g, "run_tests")
        self.review(self.B, g, "review_impl")
        self.op(g, "integrate")
        pr = [p for p in self.gh.load()["prs"].values() if p["headRefName"] == f"zzzops/pr/g{g}"][0]
        self.assertEqual("release/1", pr["baseRefName"])
        self.approve(g, "approve_merge")
        dev = self.tip("dev")
        out = self.op(g, "merge")
        self.assertEqual("done", out["closed"]["reason"])
        rel = self.tip("release/1")
        self.assertEqual(out["ran"]["output"]["merge_commit"], rel)
        self.assertTrue(self.is_ancestor(fix, rel))
        self.assertEqual(dev, self.tip("dev"))                            # dev only gets it through the sync

    def test_next_release_goal_targets_dev_and_passes_its_gate(self):
        self.cut_release_1()
        g = self.goal()
        self.assertEqual(2, self.show(g)["goal"]["release"])
        self.done(g)
        pr = [p for p in self.gh.load()["prs"].values() if p["headRefName"] == f"zzzops/pr/g{g}"][0]
        self.assertEqual("dev", pr["baseRefName"])

    def test_edit_onto_a_line_restacks_through_the_target_part(self):
        _, line = self.cut_release_1()
        self.push_branch("release/1", {"src/fix.py": "f = 1\n"})
        g = self.goal()                                                   # release 2, on dev
        self.discovery(g)
        self.op(g, "base")
        self.w.ok("a", "edit", str(g), "--set", "release=1", "--base", self.goal_tip(g))
        st = self.states(g)["base"]
        self.assertTrue(st.startswith("ready (stale"), st)
        self.assertIn("target", st)


class RequiredChecksTests(Branching):
    settings = {"verification.required_ci": ["ci"]}

    def test_checks_are_enforced_on_a_release_branch_pr(self):
        g0 = self.goal(release=1)
        self.deliver(g0)
        self.op(g0, "integrate")
        self.gh.set_checks(self.pr_head(g0), ci=["pass"])
        self.op(g0, "integrate")
        self.approve(g0, "approve_merge")
        self.op(g0, "merge")
        self.cut(1)
        g = self.goal(release=1)
        self.deliver(g)
        out = self.op(g, "integrate")
        self.assertEqual("blocked", out["ran"]["outcome"])
        self.gh.set_checks(self.pr_head(g), ci=["fail"])
        self.op(g, "integrate")
        out = self.op(g, "integrate")
        self.assertFalse(out["ran"]["ok"])


class SyncTests(Branching):
    settings = {"merge.method": "squash"}

    def release_fix(self, line, code=None):
        g = self.goal(release=1)
        self.done(g, code=code)
        return g

    def test_release_commit_schedules_a_merge_pr_into_dev(self):
        _, line = self.cut_release_1()
        self.op(line, "sync")                                             # the `new` run after the cut
        dev_goal = self.goal()
        self.discovery(dev_goal)
        self.release_fix(line)
        rtip = self.tip("release/1")
        act = [a for a in self.nxt()["actions"] if a["goal"] == line and a["node"] == "sync"]
        self.assertEqual("upstream", act[0]["reason"])
        # dev goals are not blocked by the pending sync
        self.assertIn((dev_goal, "base"), [(a["goal"], a["node"]) for a in self.nxt()["actions"]])
        out = self.op(line, "sync")
        self.assertEqual("done", out["ran"]["outcome"], out["ran"])
        self.assertEqual(rtip, out["ran"]["output"]["merged"])
        self.assertTrue(self.is_ancestor(rtip, self.tip("dev")))
        prs = [p for p in self.gh.load()["prs"].values() if p["headRefName"] == f"zzzops/sync/g{line}/integration"]
        self.assertEqual(1, len(prs))
        self.assertEqual(("dev", "MERGED"), (prs[0]["baseRefName"], prs[0]["state"]))
        self.assertIn("Release 1", prs[0]["title"])
        self.assertIn("merge", self.gh.load()["merge_methods_used"][-1:])   # --merge whatever merge.method is
        mc = self.tip("dev")
        self.assertEqual(2, len(self.w.remote_git("rev-list", "--parents", "-n", "1", mc).split()) - 1)
        self.assertEqual(mc, out["ran"]["output"]["merge_commit"])
        self.assertIsNone(self.tip(f"zzzops/work/g{line}"))
        self.assertEqual("current", self.states(line)["sync"])

    def resolve_conflict(self, line):
        wt = self.A.worktree(line)
        wt.write({"src/app.py": "def app():\n    return 23\n"})
        wt.git("add", "-A")
        wt.git("-c", "core.editor=true", "commit", "--no-edit")
        return wt.git("rev-parse", "HEAD")

    def test_conflicting_sync_is_an_agent_item_then_an_approval(self):
        _, line = self.cut_release_1()
        self.op(line, "sync")
        d = self.goal()
        self.done(d, code={"src/app.py": "def app():\n    return 7\n"})        # dev changes app.py
        self.release_fix(line, code={"src/app.py": "def app():\n    return 9\n"})   # so does release/1
        out = self.op(line, "sync")
        b = out["ran"]["blocked"]
        self.assertEqual(("conflict", "agent"), (b["category"], b["waiting_for"]))
        act = [a for a in self.nxt(line)["actions"] if a["node"] == "sync"][0]
        self.assertEqual("retry", act["reason"])
        m = self.resolve_conflict(line)
        out = self.op(line, "sync")                                       # the resume accepts the hand merge
        b = out["ran"]["blocked"]
        self.assertEqual("human", b["waiting_for"])
        self.assertIn("remerge-diff", b["question"])
        self.assertEqual(m, self.tip(f"zzzops/sync/g{line}/integration"))  # start did not reset it
        self.answer_blocked(line, "sync")
        out = self.op(line, "sync")
        self.assertEqual("done", out["ran"]["outcome"], out["ran"])
        self.assertEqual("def app():\n    return 23", self.w.remote_git("show", f"{self.tip('dev')}:src/app.py"))

    def test_dev_moving_under_an_open_sync_pr(self):
        _, line = self.cut_release_1()
        self.op(line, "sync")
        d = self.goal()
        self.done(d, code={"src/app.py": "def app():\n    return 7\n"})
        self.release_fix(line, code={"src/app.py": "def app():\n    return 9\n"})
        self.op(line, "sync")
        self.resolve_conflict(line)
        # every sync PR GitHub has or will open next reads BLOCKED, so the PR stays open
        self.gh.update(lambda st: st.setdefault("faults", {}).update(
            {"merge_state": {str(n): "BLOCKED" for n in range(1, st["next_number"] + 3)}}))
        self.op(line, "sync")
        self.answer_blocked(line, "sync")
        out = self.op(line, "sync")                                       # BLOCKED: the PR stays open
        self.assertEqual("time", out["ran"]["blocked"]["waiting_for"])
        # dev moves cleanly: the new I tip is merged into the sync branch, the approval holds
        moved = self.w.push_dev({"docs.txt": "d\n"}, "docs")
        out = self.op(line, "sync")
        head = self.tip(f"zzzops/sync/g{line}/integration")
        self.assertTrue(self.is_ancestor(moved, head))
        self.assertEqual([], [i for i in self.nxt(line)["needs_human"] if i.get("node") == "sync"])
        self.assertEqual("def app():\n    return 23", self.w.remote_git("show", f"{head}:src/app.py"))
        # dev moves with a conflict: a new agent item
        self.w.push_dev({"src/app.py": "def app():\n    return 5\n"}, "dev conflicts")
        out = self.op(line, "sync")
        self.assertEqual(("conflict", "agent"), (out["ran"]["blocked"]["category"], out["ran"]["blocked"]["waiting_for"]))


class ScheduledRestackTests(Branching):
    def test_target_move_before_implement_restacks_and_carries_test_design(self):
        _, line = self.cut_release_1()
        g = self.goal(release=1)
        self.discovery(g)
        self.op(g, "base")
        wtd = self.A.worktree(g)
        c = self.A.start(g, "test_design")
        wtd.commit({f"tests/t{g}.txt": "t1\n"}, "test")
        self.A.submit(g, "test_design", c, {"commands": ["true"]})
        self.review(self.B, g, "review_tests")
        moved = self.push_branch("release/1", {"src/fix.py": "f = 1\n"})
        st = self.states(g)
        self.assertTrue(st["base"].startswith("ready (upstream"), st)
        self.assertTrue(st["implement"].startswith("blocked"), st)
        self.assertIn("restack", st["implement"])
        self.assertNotIn((g, "implement"), [(a["goal"], a["node"]) for a in self.nxt(g)["actions"]])
        out = self.op(g, "base")
        self.assertEqual(moved, out["ran"]["output"]["base_commit"])
        self.assertIn("test_design", out["carried"])
        self.assertEqual("implement", out["ran"]["output"]["scheduled_for"]["node"])
        st = self.states(g)
        self.assertEqual("current", st["test_design"])
        # the bound: the target moves again, implement starts anyway
        self.push_branch("release/1", {"src/fix2.py": "f = 2\n"})
        self.assertEqual("current", self.states(g)["base"])
        c = self.A.start(g, "implement")
        wtd.commit({f"src/m{g}.py": "x = 1\n"}, "feat")
        self.A.submit(g, "implement", c, {"summary": "Built."})
        # after implement's new attempt the rule may fire again
        self.w.ok("a", "reopen", str(g), "implement", "--note", "again")
        self.assertTrue(self.states(g)["base"].startswith("ready (upstream"))

    def test_no_restack_for_a_goal_parked_at_approve_merge(self):
        _, line = self.cut_release_1()
        g = self.goal(release=1)
        self.deliver(g)
        self.op(g, "integrate")
        self.push_branch("release/1", {"src/fix.py": "f = 1\n"})
        st = self.states(g)
        self.assertEqual("current", st["base"])
        self.assertEqual("needs_human (approve)", st["approve_merge"])


class NoBranchingRestackTests(Branching):
    branching = False

    def test_dev_move_before_implement_does_not_restack(self):
        g = self.goal()
        self.discovery(g)
        self.op(g, "base")
        c = self.A.start(g, "test_design")
        self.A.worktree(g).commit({f"tests/t{g}.txt": "t1\n"}, "test")
        self.A.submit(g, "test_design", c, {"commands": ["true"]})
        self.review(self.B, g, "review_tests")
        self.w.push_dev({"src/fix.py": "f = 1\n"})
        st = self.states(g)
        self.assertEqual("current", st["base"])
        self.assertTrue(st["implement"].startswith("ready"), st)


class FinishTests(Branching):
    def finish_ready(self, line):
        for _ in range(3):
            if not self.states(line)["sync"].startswith("ready"):
                break
            self.op(line, "sync")
        self.approve(line, "approve_finish")

    def test_finish_merges_into_production_back_into_dev_and_keeps_the_branch(self):
        self.gh.update(lambda st: st.update(auto_delete=False))
        a, line = self.cut_release_1()
        m = self.goal(release=1)
        self.op(line, "sync")
        self.assertTrue(self.states(line)["approve_finish"].startswith("waiting"), self.states(line))
        self.done(m)
        self.op(line, "sync")
        rtip = self.tip("release/1")
        self.approve(line, "approve_finish")
        out = self.op(line, "finish")
        self.assertEqual("done", out["closed"]["reason"], out)
        main = self.tip("main")
        self.assertTrue(self.is_ancestor(rtip, main))
        self.assertEqual(2, len(self.w.remote_git("rev-list", "--parents", "-n", "1", main).split()) - 1)
        self.assertTrue(self.is_ancestor(rtip, self.tip("dev")))
        self.assertEqual(rtip, self.tip("release/1"))                     # kept
        o = out["ran"]["output"]
        self.assertEqual(main, o["production_merge"])
        self.assertIn("dev", o["back_merges"])
        pr = [p for p in self.gh.load()["prs"].values() if p["headRefName"] == "release/1"][0]
        self.assertEqual(("main", "Release 1"), (pr["baseRefName"], pr["title"]))
        # after finishing, a fresh `next` keeps release 2 open on dev, and a new release 1 goal targets dev with a warning
        g2 = self.goal()
        self.assertEqual(2, self.show(g2)["goal"]["release"])
        self.done(g2)
        out = self.w.new(title="late", release=1)
        self.assertIn("release_finished", kinds(out.get("warnings")))
        g = out["created"]["id"]
        self.discovery(g)
        act = [a for a in self.nxt(g)["actions"] if a["node"] == "base"][0]
        self.assertEqual("dev", act["target"])
        # release 2 is complete and release 1 is finished: the cut for 2 is offered
        self.cancel(g)
        self.assertEqual([2], [i["release"] for i in find_kind(self.nxt(), "release_cut")])

    def test_late_member_holds_finish_and_restales_the_approval(self):
        _, line = self.cut_release_1()
        self.finish_ready(line)
        out = self.w.new(title="late", release=1)
        self.assertIn("release_finishing", kinds(out.get("warnings")))
        late = out["created"]["id"]
        self.assertEqual("waiting (line_members_open)", self.states(line)["finish"])
        self.done(late)
        self.assertTrue(self.states(line)["sync"].startswith("ready"))
        self.op(line, "sync")
        self.assertEqual("needs_human (approve)", self.states(line)["approve_finish"])
        main = self.tip("main")
        rc, err = self.w.run("a", "start", str(line), "finish", "--as", OP)
        self.assertNotEqual(0, rc)
        self.assertEqual(main, self.tip("main"))

    def test_late_member_cancelled_lets_finish_run_on_the_existing_approval(self):
        self.gh.update(lambda st: st.update(auto_delete=False))
        _, line = self.cut_release_1()
        self.finish_ready(line)
        late = self.w.new(title="late", release=1)["created"]["id"]
        self.assertEqual("waiting (line_members_open)", self.states(line)["finish"])
        self.cancel(late)
        self.assertEqual("ready (new)", self.states(line)["finish"])
        out = self.op(line, "finish")
        self.assertEqual("done", out["closed"]["reason"])

    def test_production_conflict_is_a_human_item(self):
        _, line = self.cut_release_1()
        self.push_branch("main", {"src/app.py": "def app():\n    return 42\n"}, "edit on main outside git flow")
        self.push_branch("release/1", {"src/app.py": "def app():\n    return 44\n"}, "release edit")
        self.finish_ready(line)
        main = self.tip("main")
        out = self.op(line, "finish")
        b = out["ran"]["blocked"]
        self.assertEqual("human", b["waiting_for"])
        self.assertIn("main", b["question"])
        self.assertEqual(main, self.tip("main"))


class HotfixTests(Branching):
    X = "login-crash"

    def member(self, **kw):
        return self.goal(release=1, flow={"hotfix": self.X}, **kw)

    def test_member_waits_on_hotfix_start_then_merges_into_the_hotfix_branch(self):
        m = self.member()
        self.discovery(m)
        st = self.states(m)["base"]
        self.assertTrue(st.startswith("waiting"), st)
        items = find_kind(self.nxt(), "hotfix_start")
        self.assertEqual(1, len(items))
        self.assertIn(f"hotfix start {self.X}", items[0]["command"])
        main = self.tip("main")
        out = self.hotfix_start(self.X)
        self.assertEqual(main, self.tip(f"hotfix/{self.X}"))
        line = out["goal"]
        self.assertEqual({"line": "hotfix", "name": self.X, "branch": f"hotfix/{self.X}", "from": "main", "cut": main},
                         self.show(line)["goal"]["flow"])
        self.assertEqual([], find_kind(self.nxt(), "hotfix_start"))
        self.done(m)
        pr = [p for p in self.gh.load()["prs"].values() if p["headRefName"] == f"zzzops/pr/g{m}"][0]
        self.assertEqual(f"hotfix/{self.X}", pr["baseRefName"])

    def test_finish_reaches_production_dev_and_the_open_release_branch_by_the_recorded_tip(self):
        self.gh.update(lambda st: st.update(auto_delete=True))           # GitHub deletes hotfix/x on the finish merge
        _, rline = self.cut_release_1()
        m = self.member()
        line = self.hotfix_start(self.X)["goal"]
        self.done(m)
        htip = self.tip(f"hotfix/{self.X}")
        out = self.op(line, "sync")                                       # record-only: no merge PR into dev
        self.assertEqual(htip, out["ran"]["output"]["merged"])
        self.assertFalse(self.is_ancestor(htip, self.tip("dev")))
        self.assertEqual([], [p for p in self.gh.load()["prs"].values()
                              if p["headRefName"].startswith(f"zzzops/sync/g{line}/")])
        self.approve(line, "approve_finish")
        out = self.op(line, "finish")
        self.assertEqual("done", out["closed"]["reason"], out)
        self.assertTrue(self.is_ancestor(htip, self.tip("main")))
        self.assertTrue(self.is_ancestor(htip, self.tip("dev")))
        self.assertTrue(self.is_ancestor(htip, self.tip("release/1")))
        heads = {p["headRefName"]: p["baseRefName"] for p in self.gh.load()["prs"].values()}
        self.assertEqual("dev", heads.get(f"zzzops/sync/g{line}/integration"))
        self.assertEqual("release/1", heads.get(f"zzzops/sync/g{line}/release"))

    def test_tip_binding_a_member_merged_after_approval_restales_finish(self):
        m1, m2 = self.member(), self.member()
        line = self.hotfix_start(self.X)["goal"]
        self.done(m1)
        self.cancel(m2)
        self.op(line, "sync")
        self.approve(line, "approve_finish")
        m3 = self.member()
        self.done(m3)
        self.assertTrue(self.states(line)["sync"].startswith("ready"), self.states(line))
        self.op(line, "sync")
        self.assertEqual("needs_human (approve)", self.states(line)["approve_finish"])
        main = self.tip("main")
        rc, _ = self.w.run("a", "start", str(line), "finish", "--as", OP)
        self.assertNotEqual(0, rc)
        self.assertEqual(main, self.tip("main"))

    def test_hotfix_names_are_single_use(self):
        self.gh.update(lambda st: st.update(auto_delete=False))
        m = self.member()
        line = self.hotfix_start(self.X)["goal"]
        self.done(m)
        self.op(line, "sync")
        self.approve(line, "approve_finish")
        self.op(line, "finish")
        rc, err = self.w.run("a", "new", "--file", self.w.file({"title": "again", "spec": "s",
                                                                  "flow": {"hotfix": self.X}}))
        self.assertEqual("validation", err["error"]["code"])
        self.assertIn("choose a new name", json.dumps(err))
        g = self.goal(release=1)
        rc, err = self.w.run("a", "edit", str(g), "--set", "flow=" + json.dumps({"hotfix": self.X}),
                             "--base", self.goal_tip(g))
        self.assertIn("choose a new name", json.dumps(err))
        rc, err = self.hotfix_start(self.X, ok=False)
        self.assertNotEqual(0, rc)
        self.assertIn("choose a new name", json.dumps(err))

    def test_invalid_member_dependencies_are_refused(self):
        dev_goal = self.goal()
        rc, err = self.w.run("a", "new", "--file", self.w.file({"title": "hf", "spec": "s", "depends_on": [dev_goal],
                                                                  "flow": {"hotfix": self.X}}))
        self.assertEqual("validation", err["error"]["code"])
        rc, err = self.w.run("a", "new", "--file", self.w.file({"title": "hf", "spec": "s", "flow": {"hotfix": "a..b"}}))
        self.assertEqual("validation", err["error"]["code"])


class StackingTests(Branching):
    def stacked_pair(self):
        _, line = self.cut_release_1()
        self.op(line, "sync")
        dep = self.goal(release=1)
        self.deliver(dep)
        self.op(dep, "integrate")
        d = self.w.new(title="dependent", depends_on=[dep])["created"]["id"]    # release 2, on dev
        self.deliver(d)
        self.op(d, "integrate")
        self.assertEqual(f"zzzops/pr/g{dep}", self.pr_of(d)["baseRefName"])
        return line, dep, d

    def pr_of(self, g):
        return [p for p in self.gh.load()["prs"].values() if p["headRefName"] == f"zzzops/pr/g{g}"][0]

    def test_dev_goal_on_a_release_goal_waits_for_the_sync_then_restacks_onto_dev(self):
        self.gh.update(lambda st: st.update(auto_delete=False))
        line, dep, d = self.stacked_pair()
        self.approve(dep, "approve_merge")
        self.op(dep, "merge")
        self.assertEqual("dev", self.pr_of(d)["baseRefName"])            # its own target, not release/1
        self.assertEqual("waiting (release_sync)", self.states(d)["base"])
        self.op(line, "sync")
        st = self.states(d)["base"]
        self.assertTrue(st.startswith("ready"), st)
        out = self.op(d, "base")
        self.assertTrue(self.is_ancestor(self.tip("release/1"), out["ran"]["output"]["base_commit"]))

    def test_pr_already_retargeted_by_github_is_moved_to_dev(self):
        self.gh.update(lambda st: st.update(auto_delete=True))
        line, dep, d = self.stacked_pair()
        self.approve(dep, "approve_merge")
        self.op(dep, "merge")
        self.op(line, "sync")
        self.op(d, "base")
        for _ in range(6):
            st = self.states(d)
            nxt = [a["node"] for a in self.nxt(d)["actions"] if a["goal"] == d]
            if "integrate" in nxt:
                break
            if not nxt:
                break
            node = nxt[0]
            if node in ("test_design", "implement"):
                c = self.A.start(d, node)
                self.A.submit(d, node, c, {"commands": ["true"]} if node == "test_design" else {"summary": "B."})
            elif node.startswith("review"):
                self.review(self.B, d, node)
            else:
                self.op(d, node)
        self.op(d, "integrate")
        self.assertEqual("dev", self.pr_of(d)["baseRefName"])

    def test_same_target_stacking_retargets_to_the_release_branch(self):
        self.gh.update(lambda st: st.update(auto_delete=False))
        _, line = self.cut_release_1()
        a = self.goal(release=1)
        self.deliver(a)
        self.op(a, "integrate")
        b = self.w.new(title="B", release=1, depends_on=[a])["created"]["id"]
        self.deliver(b)
        self.op(b, "integrate")
        self.approve(a, "approve_merge")
        self.op(a, "merge")
        self.assertEqual("release/1", self.pr_of(b)["baseRefName"])


if __name__ == "__main__":
    unittest.main()
