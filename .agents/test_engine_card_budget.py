"""G1018: cards show the full checkpoint for inputs selected by `.change` or `.tree`, and `shrink` keeps cards
near the 4,096-byte target without growing them or hiding a checkpoint view.

Guarantees under test (design G1018 attempt 2):
  G1  a checkpoint view (a dict with `commit` and `diff`) is never blobbed;
  G2  `shrink(card)` is never larger than `card`;
  G3  after `shrink`, the card is at most 4,096 bytes or `shrink_candidates(card)` is empty (no step, lossless,
      clip or blob, can shrink it further); `shrink` is idempotent;
  G4  (measured) default-graph cards without `previous`, at real sizes, are at most 4,096 bytes.

The real-size fixtures copy the field lengths of the cards G1014 produced at 54d7e83 (real prompts, this
repository's policy texts, 28-character holders, a 51-character title, a 400-character design summary, 4-digit goal ids,
neutral paths of the same length). One G4 fixture is built through the CLI (`card.build`), so it grows when
new card sections are added.
"""

from __future__ import annotations

import copy
import hashlib
import inspect
import json
import re
import shlex
import shutil
import subprocess
import tempfile
import unittest
from types import SimpleNamespace

import engine_fixtures as fx
import test_engine_journeys as tj
import test_engine_lifecycle as lc

from engine import card as C
from engine.canon import canonical
from engine.fingerprint import fp_selected
from engine.render import command, first_line
from engine.schemas import build_graph

LIMIT = 4096
HEX = re.compile(r"^[0-9a-f]{40}$")
EXCL = "':/' ':(top,exclude).zzzops/reviews'"
WF = fx.load_template("workflow.json")
POLICY = fx.load_template("POLICY.json")
# the instruction texts this repository's own policy uses (the real cards' texts; longer than the template's)
_REPO_POLICY = fx.ROOT / ".zzzops" / "POLICY.json"
if _REPO_POLICY.is_file():
    POLICY["instructions"].update(json.loads(_REPO_POLICY.read_text(encoding="utf-8")).get("instructions") or {})
GRAPH = build_graph("default", WF["graphs"]["default"])


def size(c) -> int:
    return len(canonical(c))


def h(tag: str) -> str:
    return hashlib.sha1(tag.encode()).hexdigest()


def git_blob(text: str) -> str:
    data = text.encode("utf-8")
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


class FakeReader:
    """The session reader's blob_view (200-character first line, blob id, read command), without Git."""

    def blob_view(self, text: str) -> dict:
        b = git_blob(text)
        return {"summary": first_line(text, 200), "blob": b, "read": f"git cat-file -p {b}"}

    def prompt(self, name):
        return (fx.TEMPLATES / "prompts" / name).read_text(encoding="utf-8")

    def diffstat(self, base, commit):
        return None


READER = FakeReader()
CTX = SimpleNamespace(prefix="zzzops")


def cp(tag: str) -> dict:
    return {"commit": h(tag + ":commit"), "base": h("base"), "tree": h(tag + ":tree"), "change": h(tag + ":change")}


def view_of(c: dict) -> dict:
    """The card view a `.change` input renders (no `tree`)."""
    return {"commit": c["commit"], "base": c["base"], "change": c["change"],
            "diff": f"git diff {c['base']} {c['commit']} -- {EXCL}"}


def words(n: int, seed="design") -> str:
    out, i = "", 0
    while len(out) < n:
        out += f"{seed}{i} "
        i += 1
    return out[:n]


def shrink_candidates(c):
    """`card.shrink_candidates(card)` (the design's signature); a reader is passed if the helper takes one."""
    fn = C.shrink_candidates
    if len(inspect.signature(fn).parameters) >= 2:
        return fn(c, READER)
    return fn(c)


def shrink(c):
    return C.shrink(copy.deepcopy(c), READER)


def blob_views(obj):
    """Every blob view (a dict with blob, read and summary) anywhere in obj."""
    if isinstance(obj, dict):
        if "blob" in obj and "read" in obj and "summary" in obj:
            yield obj
        for v in obj.values():
            yield from blob_views(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from blob_views(v)


# ------------------------------------------------------------------------------------------ real-size fixtures


def pre_card(node: str, *, goal=1014, inputs=None, context=None, cmds_to_run=None, previous=None,
             corrections=None, workspace=True, title=None) -> dict:
    """A card as `build` lays it out before `shrink`: prompt and instructions inline up to 600 bytes."""
    nd = WF["graphs"]["default"]["nodes"][node]
    cap = nd.get("capability", "bounded")
    holder = f"claude:e6ad/{node}-{goal}-1"
    root = "/home/dev/" + "x" * 16
    text = READER.prompt(nd["prompt"])
    ins = POLICY["instructions"]
    card = {"ok": True, "coordinator": {"commit": h("dev"), "current": True}, "goal": goal,
            "title": title or words(51, "Title"), "node": node, "stage": nd["stage"],
            "run": {"root": False, "capability": cap, "models": list(POLICY["settings"]["routing"]["tiers"][cap])},
            "lease": {"branch": f"zzzops/lease/g{goal}/{node}", "attempt": 1, "holder": holder,
                      "timeout_minutes": 120, "renew_every_minutes": 30, "expires_at": "2026-11-01T06:27:01Z"},
            "renew": "Renew every 30 minutes (timeout 120). After any pause, renew first.", "reason": "new",
            "prompt": {"text": text} if len(text.encode()) <= C.INLINE else READER.blob_view(text),
            "instructions": {k: ({"text": ins[k]} if len(ins[k].encode()) <= C.INLINE else READER.blob_view(ins[k]))
                             for k in nd.get("instructions", []) if k in ins},
            "inputs": inputs or {}, "context": context or {}}
    if cmds_to_run:
        card["commands_to_run"] = {"from": "commands", "list": cmds_to_run,
                                   "note": "Run these in the workspace before you submit."}
    card["corrections"] = corrections or []
    if previous:
        card["previous"] = previous
    card["read_dev"] = {"commit": h("dev"), "show": f"git show {h('dev')}:<path>",
                        "grep": f"git grep <pattern> {h('dev')}", "mirror": root + "/.git/zzzops/coordinator"}
    card["workspace"] = f"{root}/.zzzops/worktrees/g{goal}" if workspace else None
    review = bool(nd.get("review"))
    card["output_schema"] = C.output_schema(GRAPH, node, {})
    if review:
        card["artifact"] = {"output": "report", "path": f".zzzops/reviews/{goal}/{node}.md"}
    g, N = str(goal), "1"
    card["commands"] = {
        "submit": command(CTX, ["submit", g, node, "--attempt", N, "--as", holder, "--output", "<F>"]
                          + (["--artifact", "<A>"] if review else [])),
        "blocked": command(CTX, ["submit", g, node, "--attempt", N, "--as", holder, "--blocked", "<F>"]),
        "renew": command(CTX, ["renew", g, node, "--attempt", N]),
        "abandon": command(CTX, ["abandon", g, node, "--attempt", N])}
    return card


def doc_input(goal=1014):
    b = h("doc")
    return {"path": f".zzzops/reviews/{goal}/design.md", "blob": b, "read": f"git cat-file -p {b}",
            "summary": words(400)}


CMDS = ["cd .agents && python3 -m unittest test_engine_live_input_changes -v"]


def checks_result():
    """The size and shape of the real run_tests result on G1014 (3,495 bytes as JSON)."""
    return {"details": [{"cmd": CMDS[0], "exit": 0, "seconds": 17, "tail": words(1450, "ok")},
                        {"cmd": "python3 -m unittest discover -s .agents", "exit": 0, "seconds": 269,
                         "tail": words(1450, "ran")}],
            "passed": True, "tree": h("checks-tree")}


def implement_fixture(**kw):
    return pre_card("implement", inputs={"base": h("base"), "doc": doc_input(), "tests": view_of(cp("tests"))},
                    context={"commands": list(CMDS), "tests_review": C.view(READER, words(534, "review"))},
                    cmds_to_run=list(CMDS), **kw)


def review_tests_fixture(**kw):
    return pre_card("review_tests", inputs={"doc": doc_input(), "tests": view_of(cp("tests"))}, workspace=False, **kw)


def review_impl_fixture(**kw):
    return pre_card("review_impl", inputs={"code": view_of(cp("code")), "doc": doc_input(),
                                           "tests": view_of(cp("tests"))},
                    context={"checks": C.view(READER, checks_result())}, workspace=False, **kw)


def big_previous(n=4200):
    return {"findings": [{"id": f"review_impl:1:{i}", "target": "implement", "text": words(n // 4, f"f{i}"),
                          "status": "open", "response": "fixed: done"} for i in range(4)]}


def views_in(c):
    return {(s, k): v for s in ("inputs", "context") for k, v in (c.get(s) or {}).items()
            if isinstance(v, dict) and "commit" in v and "diff" in v}


# ------------------------------------------------------------------------------------------------- shrink


class ShrinkBudgetTests(unittest.TestCase):
    def fixtures(self):
        return {"implement": implement_fixture(), "review_tests": review_tests_fixture(),
                "review_impl": review_impl_fixture()}

    def test_real_size_cards_fit_with_every_view_inline(self):
        """G1 + G4 on hand-built cards with the real field lengths."""
        for name, c in self.fixtures().items():
            with self.subTest(card=name):
                before = views_in(c)
                self.assertTrue(before)
                out = shrink(c)
                self.assertLessEqual(size(out), LIMIT, f"{name}: {size(out)} bytes")
                self.assertEqual(before, views_in(out))

    def test_shrink_never_grows_a_card(self):
        """G2, including a card of small instructions that today's shrink makes larger."""
        cards = dict(self.fixtures())
        small = pre_card("implement", inputs={"base": h("base")}, previous=big_previous())
        small["prompt"] = {"text": "short prompt " * 30}
        cards["small_instructions"] = small
        cards["previous"] = implement_fixture(previous=big_previous())
        for name, c in cards.items():
            with self.subTest(card=name):
                self.assertLessEqual(size(shrink(c)), size(c))

    def test_a_card_over_budget_because_of_previous_is_a_fixed_point(self):
        """G3: over 4,096 bytes, nothing left to shrink, idempotent, and views still inline (G1)."""
        c = implement_fixture(previous=big_previous())
        views = views_in(c)
        out = shrink(c)
        self.assertGreater(size(out), LIMIT)
        self.assertEqual(out, shrink(out))
        self.assertFalse(shrink_candidates(out), shrink_candidates(out))
        self.assertEqual(views, views_in(out))
        self.assertEqual(c["previous"], out["previous"])

    def test_steps_run_in_order_argv_goes_first(self):
        """A card 100 bytes over the target loses only `argv`; prompt, instructions and summaries stay."""
        c = review_tests_fixture(previous={"findings": [{"id": "review_tests:1:1", "target": "test_design",
                                                         "text": "", "status": "open"}]})
        c["previous"]["findings"][0]["text"] = "p" * (LIMIT + 100 - size(c))
        self.assertEqual(LIMIT + 100, size(c))
        out = shrink(c)
        self.assertLessEqual(size(out), LIMIT)
        for k, v in out["commands"].items():
            self.assertNotIn("argv", v, k)
            self.assertEqual(c["commands"][k]["command"], v["command"])
        self.assertEqual(c["prompt"], out["prompt"])
        self.assertIn("text", out["prompt"])
        self.assertEqual(c["instructions"], out["instructions"])
        self.assertEqual(c["inputs"], out["inputs"])
        self.assertEqual(400, len(out["inputs"]["doc"]["summary"]))

    def test_summaries_are_clipped_to_120_characters_and_keep_their_blob(self):
        c = review_impl_fixture(previous=big_previous())
        before = {v["blob"]: v["read"] for v in blob_views(c)}
        out = shrink(c)
        seen = list(blob_views(out))
        self.assertTrue(seen)
        for v in seen:
            self.assertLessEqual(len(v["summary"]), 120, v)
            if v["blob"] in before:
                self.assertEqual(before[v["blob"]], v["read"])
        self.assertTrue(out["inputs"]["doc"]["summary"])
        self.assertTrue(words(400).startswith(out["inputs"]["doc"]["summary"].rstrip("…")))

    def test_context_commands_point_at_commands_to_run_only_when_that_is_smaller(self):
        long = ["cd .agents && python3 -m unittest test_engine_card_budget -v",
                "python3 -m unittest discover -s .agents -p 'test_engine_*.py'"]
        c = implement_fixture(previous=big_previous())
        c["context"]["commands"], c["commands_to_run"]["list"] = list(long), list(long)
        out = shrink(c)
        self.assertEqual("see commands_to_run", out["context"]["commands"])
        self.assertEqual(long, out["commands_to_run"]["list"])
        c = implement_fixture(previous=big_previous())
        c["context"]["commands"], c["commands_to_run"]["list"] = ["make"], ["make"]
        out = shrink(c)
        self.assertEqual(["make"], out["context"]["commands"])

    def test_a_different_context_commands_is_never_replaced(self):
        c = implement_fixture(previous=big_previous())
        c["context"]["commands"] = ["cd .agents && python3 -m unittest something_else_entirely -v"]
        out = shrink(c)
        self.assertEqual(c["context"]["commands"], out["context"]["commands"])

    def test_a_blobbed_correction_keeps_200_characters_and_full_has_no_summary(self):
        text = words(1500, "corr")
        corr = {"id": "review_impl:1:1", "from": "review_impl", "text": text, "rounds": 1, "upheld": False}
        c = implement_fixture(previous=big_previous(), corrections=[corr])
        out = shrink(c)
        got = out["corrections"][0]
        self.assertEqual(text[:200], got["text"])
        self.assertIn("blob", got["full"])
        self.assertEqual(f"git cat-file -p {got['full']['blob']}", got["full"]["read"])
        self.assertNotIn("summary", got["full"])
        self.assertLess(size(out), size(c))


class KeySummaryTests(unittest.TestCase):
    """A blobbed dict or list gets a one-line key summary instead of `{` (in `view()` and in `shrink`)."""

    def test_view_of_a_large_dict(self):
        r = checks_result()
        v = C.view(READER, r)
        self.assertEqual(f"details: 2 items; passed=true; tree={r['tree']}", v["summary"])
        self.assertEqual(f"git cat-file -p {v['blob']}", v["read"])

    def test_view_summary_rules_and_clip(self):
        v = C.view(READER, {"b": {"x": words(700)}, "a": 3, "c": [1, 2, 3], "d": "s"})
        self.assertEqual("a=3; b: {…}; c: 3 items; d=s", v["summary"])
        v = C.view(READER, {f"k{i:02d}": words(40) for i in range(20)})
        self.assertLessEqual(len(v["summary"]), 120)
        self.assertTrue(v["summary"].startswith("k00="))

    def test_small_values_stay_inline(self):
        self.assertEqual({"passed": True}, C.view(READER, {"passed": True}))

    def test_shrink_blobs_an_inline_dict_with_a_key_summary(self):
        d = {"details": [{"cmd": "c" * 150, "exit": 0, "tail": "t" * 300}], "passed": True, "tree": h("t")}
        self.assertLessEqual(len(canonical(d)), C.INLINE)
        c = {"ok": True, "context": {"checks": d}, "previous": {"text": "p" * 4300}, "commands": {}}
        out = shrink(c)
        self.assertIn("blob", out["context"]["checks"])
        self.assertEqual(f"details: 1 items; passed=true; tree={h('t')}", out["context"]["checks"]["summary"])


class ShrinkCandidatesTests(unittest.TestCase):
    def test_reports_the_argv_step_on_an_over_budget_card(self):
        c = implement_fixture(previous=big_previous())
        self.assertGreater(size(c), LIMIT)
        self.assertIn("argv", repr(shrink_candidates(c)))

    def test_reports_the_clip_step_once_argv_is_gone(self):
        c = implement_fixture(previous=big_previous())
        for v in c["commands"].values():
            v.pop("argv")
        cands = shrink_candidates(c)
        self.assertTrue(cands)
        self.assertNotIn("argv", repr(cands))
        self.assertRegex(repr(cands), "clip|summar")

    def test_empty_after_shrink(self):
        for c in (implement_fixture(previous=big_previous()), review_impl_fixture(previous=big_previous())):
            self.assertFalse(shrink_candidates(shrink(c)))

    def test_never_offers_a_checkpoint_view(self):
        c = implement_fixture(previous=big_previous())
        c["inputs"]["tests"]["diff"] += " " * 900          # the largest value on the card, still a view
        out = shrink(c)
        self.assertEqual(c["inputs"]["tests"], out["inputs"]["tests"])


# ------------------------------------------------------------------------------------------------- value_of


class FakeSession:
    def __init__(self, views=None):
        self._views = views or {}
        self.git = SimpleNamespace(exists=lambda oid: True)

    def ctx(self):
        return SimpleNamespace(reader=READER)

    def portfolio(self):
        return SimpleNamespace(views=self._views)

    def fetch_work_of(self, g):
        pass


def res_of(graph=GRAPH, cur=None, records=None):
    return SimpleNamespace(graph=graph, goal=1000, cur=cur or {}, doc={"records": records or {}, "skip": {}})


class ValueOfTests(unittest.TestCase):
    T = cp("tests")
    K = cp("code")

    def test_change_selector_renders_the_checkpoint_without_tree(self):
        res = res_of(cur={"test_design": {"tests": self.T, "commands": CMDS}})
        self.assertEqual(view_of(self.T), C.value_of(FakeSession(), res, "review_tests", "tests", self.T["change"]))

    def test_tree_selector_renders_the_checkpoint_with_tree(self):
        res = res_of(cur={"implement": {"code": self.K, "summary": "s"}})
        got = C.value_of(FakeSession(), res, "run_tests", "code", self.K["tree"])
        self.assertEqual(dict(view_of(self.K), tree=self.K["tree"]), got)

    def test_producer_from_the_recorded_output_when_not_current(self):
        rec = {"test_design": {"status": "done", "output": {"tests": self.T, "commands": CMDS}}}
        res = res_of(records=rec)
        self.assertEqual(view_of(self.T), C.value_of(FakeSession(), res, "implement", "tests", self.T["change"]))

    def test_mismatched_producer_falls_back_to_the_bare_value(self):
        res = res_of(cur={"test_design": {"tests": self.T}})
        other = h("other")
        self.assertEqual(other, C.value_of(FakeSession(), res, "review_tests", "tests", other))

    def test_missing_or_skipped_producer_falls_back_to_the_bare_value(self):
        v = self.T["change"]
        self.assertEqual(v, C.value_of(FakeSession(), res_of(), "review_tests", "tests", v))
        res = res_of()
        res.doc["skip"] = {"test_design": {"reason": "x"}}
        self.assertEqual(v, C.value_of(FakeSession(), res, "review_tests", "tests", v))

    def test_whole_checkpoint_view_gains_base(self):
        self.assertEqual(dict(view_of(self.T), tree=self.T["tree"]), C.checkpoint_view(self.T))
        self.assertEqual(view_of(self.T), C.checkpoint_view(self.T, "change"))

    def test_deps_sub_field_selector_renders_the_view(self):
        wf = copy.deepcopy(WF["graphs"]["default"])
        wf["nodes"]["review_tests"]["inputs"]["dep_tests"] = {"from": "deps.test_design.tests.change",
                                                              "context": True, "optional": True}
        graph = build_graph("default", wf)
        session = FakeSession(views={1001: {"cur": {"test_design": {"tests": self.T}}}})
        got = C.value_of(session, res_of(graph=graph), "review_tests", "dep_tests", {"1001": self.T["change"]})
        self.assertEqual({"1001": view_of(self.T)}, got)


# ----------------------------------------------------------------------------------------- through the CLI


def obj_type(w, sha):
    for gd in [None, *w.clones.values()]:
        args = ["git", "--git-dir", w.remote] if gd is None else ["git", "-C", gd.path]
        p = subprocess.run(args + ["cat-file", "-t", sha], capture_output=True, text=True, env=w.env)
        if p.returncode == 0:
            return p.stdout.strip()
    return None


def changed_files(w, clone, diff):
    argv = shlex.split(diff)
    assert argv[:2] == ["git", "diff"], argv
    p = subprocess.run(["git", "-C", w.clones[clone].path, "diff", "--name-only", *argv[2:]], capture_output=True,
                       text=True, env=w.env)
    if p.returncode != 0:
        raise AssertionError(p.stderr)
    return p.stdout.split()


class CardViewTests(lc.Journey):
    """Cards for `.change` inputs carry {commit, base, change, diff}; fingerprints stay on the sub-field."""

    def record(self, g, node):
        return self.show(g)["goal"]["records"][self.n(node)]

    def test_review_tests_card_shows_the_test_checkpoint(self):
        g = self.goal()
        self.through_design(g)
        c = self.A.start(g, self.n("test_design"))
        self.A.worktree(g).commit({"work/x.txt": "x\n"}, "test: x")
        self.A.submit(g, self.n("test_design"), c, {"commands": ["true"]})
        card = self.B.start(g, self.n("review_tests"))
        v = card["inputs"]["tests"]
        rec = self.record(g, "test_design")["output"]["tests"]
        self.assertIsInstance(v, dict, v)
        self.assertEqual({"commit", "base", "change", "diff"}, set(v))
        self.assertEqual((rec["commit"], rec["base"], rec["change"]), (v["commit"], v["base"], v["change"]))
        self.assertEqual(f"git diff {rec['base']} {rec['commit']} -- "
                         "':(top,literal)work/x.txt' ':(top,exclude).zzzops/reviews'", v["diff"])
        self.assertEqual(["work/x.txt"], changed_files(self.w, "b", v["diff"]))
        self.assertEqual("commit", obj_type(self.w, v["commit"]))
        self.assertEqual("commit", obj_type(self.w, v["base"]))

    def test_review_impl_card_shows_tests_and_code(self):
        g = self.goal()
        self.through_impl(g)
        card = self.B.start(g, self.n("review_impl"))
        code = self.record(g, "implement")["output"]["code"]
        tests = self.record(g, "test_design")["output"]["tests"]
        code_view, tests_view = view_of(code), view_of(tests)
        code_view["diff"] += " ':(exclude,top,literal)tests/test_cut.py'"
        tests_view["diff"] = (f"git diff {tests['base']} {tests['commit']} -- "
                              "':(top,literal)tests/test_cut.py' ':(top,exclude).zzzops/reviews'")
        self.assertEqual(code_view, card["inputs"]["code"])
        self.assertEqual(tests_view, card["inputs"]["tests"])
        self.assertEqual(["src/cut.py"], changed_files(self.w, "b", card["inputs"]["code"]["diff"]))
        self.assertEqual(["tests/test_cut.py"], changed_files(self.w, "b", card["inputs"]["tests"]["diff"]))

    def test_fingerprints_stay_on_the_selected_sub_field(self):
        g = self.goal()
        self.through_impl(g)
        card = self.B.start(g, self.n("review_impl"))
        self.B.submit(g, self.n("review_impl"), card, {"decision": "approved", "summary": "ok", "findings": []},
                      artifact="# r\n")
        graph = build_graph("default", self.w.workflow["graphs"]["default"])
        recs = self.show(g)["goal"]["records"]
        checked = 0
        for n in ("review_tests", "implement", "review_impl", "run_tests"):
            n = self.n(n)
            for name, sel in graph.selectors[n].items():
                if sel and sel.kind == "node" and sel.path[:1] in (("change",), ("tree",)):
                    want = fp_selected(graph, n, name, recs[sel.node]["output"][sel.output][sel.path[0]])
                    self.assertEqual(want, recs[n]["fp_parts"]["inputs"][name], (n, name))
                    checked += 1
        self.assertEqual(5, checked)


class RenamedCardViewTests(CardViewTests):
    renamed = True


class RealLengthCardTests(lc.Journey):
    """G4 through `card.build`: implement and review_impl with real-length labels, title, summaries and checks."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="zzzops-card-budget-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.w = fx.World(self.tmp)
        wf = fx.stub_ops_workflow()
        self.m = {n: n for n in fx.DEFAULT_NODES}
        if self.renamed:
            wf = fx.renamed_workflow(wf)
            self.m = fx.RENAME
        self.w.bootstrap(policy=copy.deepcopy(POLICY), workflow=wf)
        self.A = fx.Agent(self.w, "a", "claude:e6ad/implement-1000-1")
        self.B = fx.Agent(self.w, "b", "codex:e6ad/review_impl-1000-1")

    def test_real_length_cards_fit_with_their_views_inline(self):
        g = self.w.new(title=words(51, "Title"))["created"]["id"]
        c = self.A.start(g, self.n("design"))
        self.A.submit(g, self.n("design"), c, {"summary": words(420)}, artifact="# Design\n\n" + words(3000) + "\n")
        self.review(self.B, g, "review_design")
        self.approve(g, "approve_design")
        c = self.A.start(g, self.n("base"))
        self.A.submit(g, self.n("base"), c, {"base_commit": self.w.remote_git("rev-parse", "dev"), "stack": [],
                                             "branch": f"zzzops/work/g{g}"})
        c = self.A.start(g, self.n("test_design"))
        self.A.worktree(g).commit({".agents/test_cut.py": "def test_cut():\n    assert cut() == 1\n"}, "test: cut")
        self.A.submit(g, self.n("test_design"), c, {"commands": list(CMDS)})
        c = self.B.start(g, self.n("review_tests"))
        self.B.submit(g, self.n("review_tests"), c, {"decision": "approved", "summary": words(534, "review"),
                                                     "findings": []}, artifact="# r\n")
        impl = self.A.start(g, self.n("implement"))
        self.A.worktree(g).commit({"src/cut.py": "def cut():\n    return 1\n"}, "feat: cut")
        self.A.submit(g, self.n("implement"), impl, {"summary": "Built."})
        c = self.A.start(g, self.n("run_tests"))
        self.A.submit(g, self.n("run_tests"), c, {"result": checks_result()})
        ri = self.B.start(g, self.n("review_impl"))
        for name, card, keys in (("implement", impl, ["tests"]), ("review_impl", ri, ["code", "tests"])):
            with self.subTest(card=name):
                self.assertNotIn("previous", card)
                self.assertLessEqual(size(card), LIMIT, f"{name}: {size(card)} bytes")
                for k in keys:
                    self.assertIn("diff", card["inputs"][k], (name, k))
                    self.assertIn("commit", card["inputs"][k], (name, k))
        self.assertNotEqual("{", ri["context"]["checks"].get("summary"))
        self.assertTrue(ri["context"]["checks"]["summary"].startswith("details: 2 items"))


class RenamedRealLengthCardTests(RealLengthCardTests):
    renamed = True


class RecordingPilot(tj.Autopilot):
    def __init__(self, w, gh):
        super().__init__(w, gh)
        self.cards, self.items = [], []
        for ag in self.agents:
            start = ag.start

            def rec(g, node, *extra, ok=True, _start=start):
                out = _start(g, node, *extra, ok=ok)
                card = out if ok else out[1]
                if isinstance(card, dict) and card.get("ok"):
                    self.cards.append(card)
                return out
            ag.start = rec

    def answer(self, g, item):
        self.items.append(item)
        super().answer(g, item)


class CardJourneyTests(unittest.TestCase):
    """Every card of a full journey: views name real commits, bare 40-hex values are commits, G3 holds."""
    renamed = False

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.w = fx.World(self.tmp)
        self.gh = fx.FakeGitHub(self.w)
        self.w.bootstrap(workflow=fx.renamed_workflow() if self.renamed else None)
        self.m = fx.RENAME if self.renamed else {n: n for n in fx.DEFAULT_NODES}
        self.pilot = RecordingPilot(self.w, self.gh)

    def test_every_card_and_approve_item(self):
        g = self.w.new(title="Card views")["created"]["id"]
        self.pilot.drive([g])
        self.assertTrue(self.pilot.cards)
        views = 0
        for card in self.pilot.cards:
            where = card["node"]
            for sect in ("inputs", "context"):
                for k, v in (card.get(sect) or {}).items():
                    if isinstance(v, dict) and "commit" in v and "diff" in v:
                        views += 1
                        self.assertEqual("commit", obj_type(self.w, v["commit"]), (where, k))
                        self.assertEqual("commit", obj_type(self.w, v["base"]), (where, k))
                    elif isinstance(v, str) and HEX.match(v):
                        self.assertEqual("commit", obj_type(self.w, v), (where, k, v))
            self.assertTrue(size(card) <= LIMIT or not shrink_candidates(card), (where, size(card)))
        self.assertGreaterEqual(views, 4)
        merge = [i for i in self.pilot.items if i["node"] == self.m["approve_merge"]]
        self.assertTrue(merge)
        code = self.w.ok("a", "show", str(g), "--json")["goal"]["records"][self.m["implement"]]["output"]["code"]
        entries = [e for e in merge[-1]["context"] if "diff" in e and e.get("label", "").endswith(".code.change")]
        self.assertEqual(1, len(entries), merge[-1]["context"])
        self.assertEqual((code["commit"], code["base"]), (entries[0]["commit"], entries[0]["base"]))

    def test_fingerprints_of_every_sub_field_input(self):
        g = self.w.new(title="Card fps")["created"]["id"]
        self.pilot.drive([g])
        graph = build_graph("default", (fx.renamed_workflow() if self.renamed else WF)["graphs"]["default"])
        recs = self.w.ok("a", "show", str(g), "--json")["goal"]["records"]
        checked = set()
        for n, sels in graph.selectors.items():
            for name, sel in sels.items():
                if sel and sel.kind == "node" and sel.path[:1] in (("change",), ("tree",)) and n in recs:
                    if (graph.nodes[n].get("inputs") or {})[name].get("context"):
                        continue
                    want = fp_selected(graph, n, name, recs[sel.node]["output"][sel.output][sel.path[0]])
                    self.assertEqual(want, recs[n]["fp_parts"]["inputs"][name], (n, name))
                    checked.add(n)
        want = {self.m[x] for x in ("review_tests", "implement", "review_impl", "approve_merge", "run_tests",
                                    "integrate")}
        self.assertEqual(want, checked)


class RenamedCardJourneyTests(CardJourneyTests):
    renamed = True


if __name__ == "__main__":
    unittest.main()
