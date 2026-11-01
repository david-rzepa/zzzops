"""G1000: parallel review lenses in the shipped default graph (design rev 3, §3-§9 and §13).

These tests run on the SHIPPED template (`fx.SHIPPED`); the other engine tests run on the frozen 12-node graph
(`.agents/fixtures/graph12`). They are written before the implementation and define these contracts:

- A lens is a review node with `review: {"subject": S, "filter": F}`. Every new finding of a lens carries
  `impact` (non-empty text) and `material` (boolean).
- A filter node outputs `summary` (text) and `verdicts`: {"<finding id>": {"verdict": "keep" | "note",
  "reason": "<text>"}}, exactly for the non-material candidates on its card. Its card lists `candidates`:
  [{id, lens, target, text, impact, material, response}].
- A target's card lists `notes` [{text, impact, lens, reason, ...}]; a lens's re-review card has
  `previous.changed` (`git diff <old blob> <new blob>`); a node that declares `policy` keys has a card section
  `policy: {key: value}`.
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import engine_fixtures as fx
from engine import schemas
from engine.ops import OPS

LENSES = ("intent", "simplicity", "truth", "adversary", "concurrency", "rollout", "experience")
REQUIRED = ("intent", "simplicity")
SUBJECTS = {"design": "filter_design", "impl": "filter_impl"}
SHIPPED_NODES = (["design"] + [f"{l}_design" for l in LENSES] + ["filter_design", "approve_design", "base",
                 "test_design", "review_tests", "implement", "run_tests"] + [f"{l}_impl" for l in LENSES]
                 + ["filter_impl", "integrate", "approve_merge", "merge"])
INTENT = {"purpose": "Ship small, reliable tools.", "serves": "Developers who use the tools.",
          "not": ["A framework."], "principles": ["Keep it small."]}
HEX40 = "1234567890abcdef1234567890abcdef12345678"


def shipped(name: str) -> dict:
    return json.loads((fx.SHIPPED / name).read_text(encoding="utf-8"))


def shipped_prompt_exists(name: str) -> bool:
    return (fx.SHIPPED / "prompts" / name).is_file()


def verdict(v: str, reason: str = "judged by the filter") -> dict:
    return {"verdict": v, "reason": reason}


def lens_finding(text: str, material: bool, impact: str = "something concrete goes wrong", target=None) -> dict:
    f = {"text": text, "impact": impact, "material": material}
    if target:
        f["target"] = target
    return f


SHIPPED_RENAME = {n: f"n{i + 1:02d}_x" for i, n in enumerate(SHIPPED_NODES)}


def renamed_shipped() -> dict:
    """The shipped workflow with every node id renamed, `review.filter` included."""
    wf = fx.renamed_workflow(shipped("workflow.json"), SHIPPED_RENAME)
    for g in wf["graphs"].values():
        for nd in g["nodes"].values():
            if "filter" in (nd.get("review") or {}):
                nd["review"]["filter"] = SHIPPED_RENAME.get(nd["review"]["filter"], nd["review"]["filter"])
    return wf


def push_goal_doc(w: fx.World, doc: dict, parent: str):
    """Write a goal document straight to the remote, as a human editing goal.json by hand would."""
    s = w.seed
    data = json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    blob = s.git("hash-object", "-w", "--stdin", input=data)
    tree = s.git("mktree", input=f"100644 blob {blob}\tgoal.json\n")
    c = s.git("commit-tree", tree, "-p", parent, "-m",
              f"zzzops: edit G{doc['id']}\n\nOutcome: edited\nState: {doc['state']}\nEngine: 1.1.0")
    s.git("push", "-q", "origin", f"{c}:refs/heads/zzzops/goal/g{doc['id']}")
    return c


# --------------------------------------------------------------------------------------------- template


class ShippedTemplateTests(unittest.TestCase):
    def setUp(self):
        self.wf = shipped("workflow.json")
        self.policy = shipped("POLICY.json")
        self.nodes = self.wf["graphs"]["default"]["nodes"]

    def validate_dir(self, d):
        nowhere = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, nowhere, True)
        p = subprocess.run([sys.executable, str(fx.PLUGIN_CODE / "zzzops.py"), "validate", "--policy", "--dir", str(d)],
                           cwd=nowhere, capture_output=True, text=True)
        return p.returncode, json.loads(p.stdout)

    def copy_template(self):
        d = os.path.join(tempfile.mkdtemp(), "tpl")
        self.addCleanup(shutil.rmtree, os.path.dirname(d), True)
        shutil.copytree(fx.SHIPPED, d)
        return d

    def test_validate_policy_passes_with_exactly_one_placeholder_warning(self):
        rc, out = self.validate_dir(fx.SHIPPED)
        self.assertEqual(0, rc, out)
        self.assertTrue(out["ok"], out)
        self.assertEqual(["intent_placeholder"], [w["kind"] for w in out["warnings"]], out)

    def test_validate_policy_without_intent_fails(self):
        d = self.copy_template()
        p = json.loads(open(os.path.join(d, "POLICY.json")).read())
        del p["settings"]["intent"]
        with open(os.path.join(d, "POLICY.json"), "w") as fh:
            json.dump(p, fh)
        rc, out = self.validate_dir(d)
        self.assertEqual(1, rc, out)
        self.assertTrue(any("intent" in e for e in out["policy"]), out)

    def test_real_intent_gives_no_warning_and_any_todo_value_warns(self):
        d = self.copy_template()
        path = os.path.join(d, "POLICY.json")
        p = json.loads(open(path).read())
        p["settings"]["intent"] = copy.deepcopy(INTENT)
        with open(path, "w") as fh:
            json.dump(p, fh)
        rc, out = self.validate_dir(d)
        self.assertEqual((0, []), (rc, out["warnings"]), out)
        p["settings"]["intent"]["principles"] = ["Keep it small.", "TODO: ask the owner"]
        with open(path, "w") as fh:
            json.dump(p, fh)
        rc, out = self.validate_dir(d)
        self.assertEqual(0, rc, out)
        self.assertEqual(["intent_placeholder"], [w["kind"] for w in out["warnings"]], out)

    def test_shipped_placeholder_intent(self):
        intent = self.policy["settings"]["intent"]
        self.assertTrue({"purpose", "serves", "not", "principles"} <= set(intent), intent)
        values = [v for x in intent.values() for v in (x if isinstance(x, list) else [x])]
        self.assertTrue(values and all(v.startswith("TODO:") for v in values), intent)

    def test_shipped_templates_validate(self):
        self.assertEqual([], schemas.validate_policy(self.policy))
        self.assertEqual([], schemas.validate_workflow(self.wf, self.policy, shipped_prompt_exists, OPS))

    def test_the_26_node_graph(self):
        self.assertEqual(sorted(SHIPPED_NODES), sorted(self.nodes))
        self.assertEqual(26, len(self.nodes))
        for removed in ("review_design", "review_impl"):
            self.assertNotIn(removed, self.nodes)
        g = schemas.build_graph("default", self.wf["graphs"]["default"])
        for subj, short in (("design", "design"), ("implement", "impl")):
            filt = SUBJECTS[short]
            self.assertEqual("bounded", self.nodes[filt]["capability"])
            self.assertIs(False, self.nodes[filt]["skippable"])
            self.assertEqual({"summary": "text", "verdicts": "object"}, self.nodes[filt]["outputs"])
            for lens in LENSES:
                n = f"{lens}_{short}"
                nd = self.nodes[n]
                self.assertEqual({"subject": subj, "filter": filt}, nd["review"], n)
                self.assertEqual("reasoning", nd["capability"], n)
                self.assertEqual(f"lens_{lens}.md", nd["prompt"], n)
                self.assertIn("review", nd["instructions"], n)
                self.assertEqual(lens not in REQUIRED, nd.get("skippable", True), n)
                self.assertEqual(["intent"] if lens == "intent" else [], nd.get("policy", []), n)
                # the filter reads every lens summary; optional exactly for the skippable lenses
                spec = [s for s in self.nodes[filt]["inputs"].values() if s["from"] == f"{n}.summary"]
                self.assertEqual(1, len(spec), (filt, n))
                self.assertFalse(spec[0].get("context", False), (filt, n))
                self.assertEqual(lens not in REQUIRED, spec[0].get("optional", False), (filt, n))
                self.assertIn(n, g.producers(filt))
        self.assertIs(False, self.nodes["approve_merge"]["skippable"])
        self.assertEqual("filter_design.summary", self.nodes["approve_design"]["inputs"]["filter"]["from"])
        self.assertFalse(self.nodes["approve_design"]["inputs"]["filter"].get("context", False))
        froms = {n: {s["from"] for s in (self.nodes[n].get("inputs") or {}).values()} for n in self.nodes}
        self.assertIn("filter_design.summary", froms["base"])
        self.assertIn("filter_impl.summary", froms["integrate"])
        self.assertIn("filter_impl.summary", froms["approve_merge"])
        self.assertIn("deps.filter_design.summary", froms["design"])
        for n in self.nodes:
            self.assertFalse(any(f.split(".")[0] in ("review_design", "review_impl") for f in froms[n]), n)

    def test_every_node_has_a_prompt_and_old_review_prompts_are_gone(self):
        for n, nd in self.nodes.items():
            if nd["kind"] != "op":
                self.assertTrue(shipped_prompt_exists(nd["prompt"]), (n, nd["prompt"]))
        for lens in LENSES:
            self.assertTrue(shipped_prompt_exists(f"lens_{lens}.md"), lens)
        self.assertTrue(shipped_prompt_exists("filter.md"))
        self.assertFalse(shipped_prompt_exists("review_design.md"))
        self.assertFalse(shipped_prompt_exists("review_impl.md"))
        self.assertIn("review", self.policy["instructions"])

    def test_human_prompts_start_with_the_question(self):
        for name in ("approve_design.md", "approve_merge.md"):
            first = (fx.SHIPPED / "prompts" / name).read_text().splitlines()[0]
            self.assertTrue(first.startswith("# ") and first.endswith("?"), first)

    def test_engine_source_names_no_shipped_node(self):
        import re
        names = [n for n in SHIPPED_NODES if n not in ("base", "merge")]
        pattern = re.compile(r"[\"'](%s)[\"']" % "|".join(names))
        hits = []
        for path in sorted((fx.PLUGIN_CODE / "engine").rglob("*.py")):
            for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if pattern.search(line):
                    hits.append(f"{path.relative_to(fx.ROOT)}:{i}: {line.strip()}")
        self.assertEqual([], hits)

    def test_frozen_fixture_is_the_12_node_graph(self):
        self.assertEqual(fx.DEFAULT_NODES, list(fx.load_template("workflow.json")["graphs"]["default"]["nodes"]))
        self.assertNotEqual(fx.TEMPLATES.resolve(), fx.SHIPPED.resolve())


# --------------------------------------------------------------------------------------------- schema rules


class LensSchemaTests(unittest.TestCase):
    def setUp(self):
        self.wf = shipped("workflow.json")
        self.policy = shipped("POLICY.json")
        self.policy["settings"]["intent"] = copy.deepcopy(INTENT)
        self.nodes = self.wf["graphs"]["default"]["nodes"]

    def errors(self, wf=None, policy=None):
        return schemas.validate_workflow(wf or self.wf, policy or self.policy, shipped_prompt_exists, OPS)

    def test_skippable_is_a_boolean_field_on_every_kind(self):
        wf = fx.load_template("workflow.json")
        nodes = wf["graphs"]["default"]["nodes"]
        for n in ("design", "approve_merge", "base"):                 # agent, human, op
            nodes[n]["skippable"] = False
        self.assertEqual([], schemas.validate_workflow(wf, fx.load_template("POLICY.json"), fx.prompt_exists, OPS))
        nodes["design"]["skippable"] = "no"
        self.assertTrue(any("skippable" in e for e in
                            schemas.validate_workflow(wf, fx.load_template("POLICY.json"), fx.prompt_exists, OPS)))

    def test_filter_input_from_a_skippable_lens_must_be_optional(self):
        spec = next(s for s in self.nodes["filter_design"]["inputs"].values() if s["from"] == "truth_design.summary")
        spec.pop("optional", None)
        self.assertTrue(self.errors(), "a required input from a skippable lens must be refused")

    def test_filter_input_from_a_required_lens_must_be_required(self):
        spec = next(s for s in self.nodes["filter_design"]["inputs"].values() if s["from"] == "intent_design.summary")
        spec["optional"] = True
        self.assertTrue(self.errors(), "an optional input from a non-skippable lens must be refused")

    def test_lenses_naming_one_filter_share_one_subject(self):
        self.nodes["truth_impl"]["review"]["filter"] = "filter_design"
        self.assertTrue(self.errors())

    def test_graph_requires_intent_when_a_node_declares_it(self):
        p = copy.deepcopy(self.policy)
        del p["settings"]["intent"]
        self.assertEqual([], schemas.validate_policy(p))              # optional for the schema ...
        self.assertTrue(any("intent" in e for e in self.errors(policy=p)))   # ... required by the graph


class IntentShapeTests(unittest.TestCase):
    def policy(self, intent):
        p = fx.load_template("POLICY.json")
        if intent is not None:
            p["settings"]["intent"] = intent
        return p

    def test_intent_is_optional(self):
        self.assertEqual([], schemas.validate_policy(self.policy(None)))

    def test_full_intent_and_extra_text_keys_pass(self):
        self.assertEqual([], schemas.validate_policy(self.policy(dict(INTENT))))
        self.assertEqual([], schemas.validate_policy(self.policy(dict(INTENT, audience="ops teams"))))
        self.assertEqual([], schemas.validate_policy(self.policy(dict(INTENT, audience=["ops", "devs"]))))

    def test_non_text_values_fail(self):
        for bad in (dict(INTENT, audience=3), dict(INTENT, audience={"x": "y"}), dict(INTENT, audience=[1]),
                    dict(INTENT, purpose=True), "a purpose", ["a purpose"]):
            self.assertTrue(schemas.validate_policy(self.policy(bad)), bad)

    def test_other_settings_keys_still_reject_extras(self):
        p = self.policy(dict(INTENT))
        p["settings"]["merge"]["extra"] = "x"
        self.assertTrue(schemas.validate_policy(p))
        p = self.policy(dict(INTENT))
        p["settings"]["unknown"] = {"a": "b"}
        self.assertTrue(schemas.validate_policy(p))
        p = self.policy(dict(INTENT))
        del p["settings"]["merge"]
        self.assertTrue(schemas.validate_policy(p))


# --------------------------------------------------------------------------------------------- World driver


class Pilot:
    """Plays agents and the human on the shipped graph through the CLI. `m` maps shipped names to graph names."""

    def __init__(self, w: fx.World, m: dict):
        self.w, self.m = w, m
        self.rev = {v: k for k, v in m.items()}
        self.agents = [fx.Agent(w, "a", "claude:aaaa/w-1"), fx.Agent(w, "b", "codex:bbbb/w-2"),
                       fx.Agent(w, "a", "claude:cccc/w-3")]
        self.turn = 0

    def n(self, x):
        return self.m.get(x, x)

    def show(self, g):
        return self.w.ok("a", "show", str(g), "--json")

    def states(self, g):
        return {self.rev.get(k, k): v for k, v in self.show(g)["states"].items()}

    def record(self, g, node):
        return self.show(g)["goal"]["records"].get(self.n(node))

    def tip(self, g):
        return self.show(g)["goal_commit"]

    def start(self, g, node, avoid=()):
        last = None
        for ag in self.agents:
            if ag.label in avoid:
                continue
            rc, card = ag.start(g, self.n(node), ok=False)
            if rc == 0:
                return ag, card
            last = card
            if card.get("error", {}).get("code") != "independence":
                break
        raise AssertionError(f"start {g} {node}: {json.dumps(last)[:2000]}")

    def output(self, node, card, findings=(), keep_open=(), verdicts=None, summary=None):
        """The default output for a card: reviews resolve prior findings and approve unless given findings."""
        schema = card["output_schema"]
        out = {}
        self.turn += 1
        if "decision" in schema:
            prior = [{"id": f["id"], "status": "open" if f["id"] in keep_open else "resolved"}
                     for f in (card.get("previous") or {}).get("findings", []) if f["status"] == "open"]
            new = list(findings)
            out = {"decision": "changes_requested" if new or keep_open else "approved",
                   "summary": summary or f"{node} verdict", "findings": prior + new}
        else:
            for k, t in schema.items():
                if k in ("findings", "responses"):
                    continue
                if k == "verdicts":
                    given = dict(verdicts or {})
                    out[k] = {c["id"]: given.pop(c["id"], verdict("note", "a nit"))
                              for c in card.get("candidates", []) if not c["material"]}
                    out[k].update(given)
                elif t.startswith("checkpoint"):
                    if card["workspace"]:
                        fx.GitDir(card["workspace"], self.w.env).commit(
                            {f"work/{self.rev.get(node, node)}.txt": f"{node} {self.turn}\n"}, f"feat: {node}")
                elif t == "strings":
                    out[k] = ["true"]
                elif t in ("text", "string"):
                    out[k] = summary if (summary and k == "summary") else f"{node} {k}"
            if findings:
                out["findings"] = list(findings)
        if card.get("corrections"):
            out["responses"] = {c["id"]: "fixed: done" for c in card["corrections"]}
        return out

    def run(self, g, node, ok=True, **kw):
        """Start and submit one agent node; returns (card, submit result)."""
        ag, card = self.start(g, node, avoid=kw.pop("avoid", ()))
        out = self.output(self.n(node), card, **kw)
        art = f"# {node} {self.turn}\n" if card.get("artifact") else None
        res = ag.submit(g, self.n(node), card, out, artifact=art, ok=ok)
        return card, res

    def item(self, g, node):
        full = self.w.ok("a", "next", "--goal", str(g))
        return next((x for x in full["needs_human"] if x["node"] == self.n(node)), None)

    def answer(self, g, node, decision="approved", findings=None):
        it = self.item(g, node)
        assert it and it["kind"] == "approve", it
        ans = {"decision": decision, "summary": decision, "quote": "yes" if decision == "approved" else "redo it",
               "decided_by": "Dave"}
        if findings:
            ans["findings"] = findings
        return self.w.ok("a", "answer", str(g), self.n(node), "--fp", it["fp"], "--file", self.w.file(ans))

    def drive(self, g, until, hooks=None, limit=120):
        """Act on G until `until(states)` holds. hooks: shipped node -> list of run() kwargs, used in order."""
        hooks = {k: list(v) for k, v in (hooks or {}).items()}
        for _ in range(limit):
            st = self.states(g)
            if until(st):
                return st
            nxt = self.w.ok("a", "next", "--goal", str(g))
            acts = [a for a in nxt["actions"] if a["goal"] == g]
            if not acts:                                     # agents and ops first, then the human
                appr = [x for x in nxt["needs_human"] if x["goal"] == g and x["kind"] == "approve"]
                if not appr:
                    raise AssertionError(f"no action for G{g}: {json.dumps(nxt)[:1500]} {st}")
                self.answer(g, self.rev.get(appr[0]["node"], appr[0]["node"]))
                continue
            a = acts[0]
            node = self.rev.get(a["node"], a["node"])
            if a["kind"] == "op":
                self.w.ok("a", "start", str(g), a["node"], "--as", "claude:aaaa/op")
            else:
                kw = hooks[node].pop(0) if hooks.get(node) else {}
                self.run(g, node, **kw)
        raise AssertionError(f"G{g} did not reach the condition: {self.states(g)}")


def lens_ids(subject="design", skip=()):
    return [f"{l}_{subject}" for l in LENSES if f"{l}_{subject}" not in skip]


class LensWorld(unittest.TestCase):
    """A World bootstrapped with the shipped template and a real intent."""

    renamed = False
    skip = {}

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.w = fx.World(self.tmp)
        self.gh = fx.FakeGitHub(self.w)
        self.m = SHIPPED_RENAME if self.renamed else {}
        wf = renamed_shipped() if self.renamed else shipped("workflow.json")
        policy = shipped("POLICY.json")
        policy["settings"]["intent"] = copy.deepcopy(INTENT)
        self.w.bootstrap(policy=policy, workflow=wf, prompts=False)
        self.w.push_dev({f".zzzops/prompts/{p.name}": p.read_text(encoding="utf-8")
                         for p in sorted((fx.SHIPPED / "prompts").iterdir())}, "chore(zzzops): prompts")
        self.p = Pilot(self.w, self.m)

    def n(self, x):
        return self.m.get(x, x)

    def goal(self, skip=None):
        skip = {self.n(k): v for k, v in (skip if skip is not None else self.skip).items()}
        return self.w.new(title="Lens goal", skip=skip)["created"]["id"]

    def set_intent(self, intent):
        self.w.seed.git("pull", "-q", "--ff-only", "origin", "dev")
        p = json.loads(open(os.path.join(self.w.seed.path, ".zzzops", "POLICY.json")).read())
        p["settings"]["intent"] = intent
        self.w.push_dev({".zzzops/POLICY.json": json.dumps(p, indent=2) + "\n"}, "chore(zzzops): intent")

    def bump_rev(self, node):
        self.w.seed.git("pull", "-q", "--ff-only", "origin", "dev")
        path = os.path.join(self.w.seed.path, ".zzzops", "workflow.json")
        wf = json.loads(open(path).read())
        nd = wf["graphs"]["default"]["nodes"][self.n(node)]
        nd["rev"] = nd.get("rev", 0) + 1
        self.w.push_dev({".zzzops/workflow.json": json.dumps(wf, indent=2) + "\n"}, "chore(zzzops): rev")

    def through_design(self, g):
        """Run design once (its first version)."""
        return self.p.drive(g, lambda st: st["design"] == "current")

    def lenses_done(self, g, hooks=None):
        """Run design and every design lens; stop with the filter ready."""
        return self.p.drive(g, lambda st: st["filter_design"].startswith("ready"), hooks)

    def candidates_of(self, card):
        return {c["id"]: c for c in card.get("candidates", [])}

    def lens_finding_ids(self, g, lens):
        r = self.p.record(g, lens)
        return [f["id"] for f in r["findings"] if f["status"] == "open"]


# --------------------------------------------------------------------------------------------- journey


class LensJourneyTests(LensWorld):
    def test_1_seven_design_lenses_run_in_parallel_with_distinct_holders(self):
        g = self.goal()
        self.through_design(g)
        nxt = self.w.ok("a", "next", "--goal", str(g))
        ready = sorted(self.p.rev.get(a["node"], a["node"]) for a in nxt["actions"] if a["goal"] == g)
        self.assertEqual(sorted(lens_ids()), ready)
        designer = self.p.record(g, "design")["holder"]
        labels = [f"claude:{i}{i}{i}{i}/lens-{i}" for i in range(1, 8)]
        self.assertNotIn(designer, labels)
        cards = {}
        for lens, label in zip(lens_ids(), labels):
            cards[lens] = fx.Agent(self.w, "b", label).start(g, self.n(lens))
        st = self.p.states(g)
        for lens in lens_ids():
            self.assertEqual("running", st[lens], lens)
        self.assertTrue(st["filter_design"].startswith("blocked"), st["filter_design"])
        self.assertEqual(len(labels), len({c["lease"]["holder"] for c in cards.values()}))

    def test_2_material_findings_wait_for_the_filter_then_reopen_the_design_once(self):
        g = self.goal()
        st = self.lenses_done(g, {"truth_design": [{"findings": [lens_finding("claims are untestable", True)]}],
                                  "adversary_design": [{"findings": [lens_finding("skips can be gamed", True)]}]})
        self.assertEqual("current", st["design"])                      # waiting for the filter: the join
        self.assertTrue(st["approve_design"].startswith("blocked"), st["approve_design"])
        for lens in lens_ids():                                        # a filtered lens's record is ok
            self.assertTrue(self.p.record(g, lens)["ok"], lens)
        truth_ids, adv_ids = self.lens_finding_ids(g, "truth_design"), self.lens_finding_ids(g, "adversary_design")
        self.assertEqual(1, len(truth_ids))
        card, _ = self.p.run(g, "filter_design", summary="filter: two material findings reopen the design")
        cands = self.candidates_of(card)
        self.assertEqual(set(truth_ids + adv_ids), set(cands))
        c = cands[truth_ids[0]]
        self.assertEqual((self.n("truth_design"), self.n("design"), "claims are untestable", True),
                         (c["lens"], c["target"], c["text"], c["material"]))
        self.assertEqual("something concrete goes wrong", c["impact"])
        self.assertIn("response", c)
        st = self.p.states(g)
        self.assertEqual("ready (reopened)", st["design"])
        ag, dcard = self.p.start(g, "design")
        self.assertEqual(sorted(truth_ids + adv_ids), sorted(x["id"] for x in dcard["corrections"]))
        old_blob = self.p.record(g, "design")["output"]["doc"]["blob"]
        ag.submit(g, self.n("design"), dcard, self.p.output(self.n("design"), dcard), artifact="# design v2\n")
        self.assertEqual(1, self.p.record(g, "design")["correction_runs"])
        new_blob = self.p.record(g, "design")["output"]["doc"]["blob"]
        self.assertNotEqual(old_blob, new_blob)
        # 3: every lens re-reviews with previous.changed
        st = self.p.states(g)
        for lens in lens_ids():
            self.assertTrue(st[lens].startswith("ready"), (lens, st[lens]))
        for lens in lens_ids():
            card, _ = self.p.run(g, lens)
            changed = json.dumps((card.get("previous") or {}).get("changed"))
            self.assertIn(f"git diff {old_blob} {new_blob}", changed, (lens, card.get("previous")))
        self.p.run(g, "filter_design")
        st = self.p.states(g)
        self.assertEqual("needs_human (approve)", st["approve_design"])

    def test_4_and_7_approve_design_lists_the_filter_every_lens_and_the_skips(self):
        reason = "docs-only goal: nothing runs concurrently"
        g = self.goal(skip={"concurrency_design": reason, "concurrency_impl": reason})
        hooks = {lens: [{"summary": f"{lens} says fine"}] for lens in lens_ids()}
        hooks["filter_design"] = [{"summary": "filter: nothing reopens, no notes"}]
        self.p.drive(g, lambda st: st["approve_design"] == "needs_human (approve)", hooks)
        st = self.p.states(g)
        self.assertEqual("skipped", st["concurrency_design"])
        item = json.dumps(self.p.item(g, "approve_design"))
        self.assertIn("filter: nothing reopens, no notes", item)
        for lens in lens_ids(skip=("concurrency_design",)):
            self.assertIn(f"{lens} says fine", item, lens)
        self.assertIn("skipped", item)
        self.assertIn(reason, item)
        self.assertIn(self.n("concurrency_design"), item)

    def test_a_skipped_approval_still_waits_for_the_lenses_and_the_filter(self):
        g = self.goal(skip={"approve_design": "small goal"})
        st = self.lenses_done(g)
        self.assertTrue(st["base"].startswith("blocked"), st["base"])
        self.p.run(g, "filter_design")
        self.assertEqual("ready (new)", self.p.states(g)["base"])

    def test_5_new_refuses_a_skip_of_a_non_skippable_node(self):
        for node in ("intent_design", "simplicity_impl", "filter_design", "approve_merge"):
            rc, err = self.w.run("a", "new", "--file", self.w.file({"title": "t", "spec": "s",
                                                                     "skip": {self.n(node): "not needed"}}))
            self.assertNotEqual(0, rc, node)
            self.assertIn("not skippable", json.dumps(err), (node, err))
        self.goal(skip={"truth_design": "a skippable lens"})            # skippable lenses can be skipped

    def test_edit_refuses_a_skip_of_a_non_skippable_node(self):
        g = self.goal()
        rc, err = self.w.run("a", "edit", str(g), "--set", f'skip.{self.n("intent_design")}="no"',
                             "--base", self.p.tip(g))
        self.assertNotEqual(0, rc)
        self.assertIn("not skippable", json.dumps(err), err)
        self.w.ok("a", "edit", str(g), "--set", f'skip.{self.n("rollout_design")}="internal change"',
                  "--base", self.p.tip(g))

    def test_6_edit_refuses_a_new_skip_of_a_lens_with_live_findings(self):
        g = self.goal()
        self.lenses_done(g, {"concurrency_design": [{"findings": [lens_finding("lease race", True)]}]})
        self.p.run(g, "filter_design")
        self.assertEqual("ready (reopened)", self.p.states(g)["design"])
        rc, err = self.w.run("a", "edit", str(g), "--set", f'skip.{self.n("concurrency_design")}="noisy"',
                             "--base", self.p.tip(g))
        self.assertNotEqual(0, rc, err)
        self.assertEqual("ready (reopened)", self.p.states(g)["design"])
        # waiving the finding first, visibly, makes the skip possible
        fid = self.lens_finding_ids(g, "concurrency_design")[0]
        lens = self.n("concurrency_design")
        self.w.ok("a", "edit", str(g), "--set", f'records.{lens}.findings[{fid}].status="waived"',
                  "--set", f'records.{lens}.findings[{fid}].note="waived by Dave: out of scope"',
                  "--base", self.p.tip(g))
        self.w.ok("a", "edit", str(g), "--set", f'skip.{lens}="noisy"', "--base", self.p.tip(g))


class FullLensJourneyTests(LensWorld):
    def test_8_capture_to_merge_and_the_pr_body_lists_every_code_lens_and_the_skips(self):
        reason = "internal-only change"
        g = self.goal(skip={"experience_design": reason, "experience_impl": reason})
        hooks = {lens: [{"summary": f"{lens} ok"}] for lens in lens_ids("impl")}
        hooks["filter_impl"] = [{"summary": "filter_impl: nothing reopens"}]
        self.p.drive(g, lambda st: st["approve_merge"] == "needs_human (approve)" and st["integrate"] == "current",
                     hooks, limit=200)
        prs = self.gh.load()["prs"]
        self.assertEqual(1, len(prs))
        body = next(iter(prs.values()))["body"]
        self.assertIn("## Reviews", body)
        self.assertIn("filter_impl: nothing reopens", body)
        for lens in lens_ids("impl", skip=("experience_impl",)):
            self.assertIn(f"**{self.n(lens)}**: {lens} ok", body, body)
        self.assertIn(f"skipped: {reason}", body)
        self.assertIn(self.n("experience_impl"), body)
        item = json.dumps(self.p.item(g, "approve_merge"))
        self.assertIn("filter_impl: nothing reopens", item)
        self.assertIn(reason, item)
        self.p.drive(g, lambda st: not st)                    # a closed goal has no node states
        self.assertEqual(("closed", "done"), (self.p.show(g)["goal"]["state"], self.p.show(g)["goal"]["closed"]["reason"]))
        self.assertEqual("MERGED", next(iter(self.gh.load()["prs"].values()))["state"])


class RenamedFullLensJourneyTests(FullLensJourneyTests):
    renamed = True


class RenamedLensJourneyTests(LensJourneyTests):
    renamed = True


# --------------------------------------------------------------------------------------------- nitpick filter


class FilterTests(LensWorld):
    def test_a_note_judged_note_leaves_the_target_current_and_does_not_count(self):
        g = self.goal()
        self.lenses_done(g, {"simplicity_design": [{"findings": [lens_finding("rename a helper", False,
                                                                               "slightly harder to read")]}]})
        nid = self.lens_finding_ids(g, "simplicity_design")[0]
        card, _ = self.p.run(g, "filter_design", verdicts={nid: verdict("note", "a preference")})
        self.assertEqual(False, self.candidates_of(card)[nid]["material"])
        st = self.p.states(g)
        self.assertEqual("current", st["design"])
        self.assertEqual("needs_human (approve)", st["approve_design"])
        self.assertEqual(0, self.p.record(g, "design")["correction_runs"])
        # the note is on the approval item, with its lens
        item = json.dumps(self.p.item(g, "approve_design"))
        self.assertIn("rename a helper", item)
        self.assertIn(self.n("simplicity_design"), item)
        # and on the target's next card (the human asks for changes)
        self.p.answer(g, "approve_design", decision="changes_requested")
        ag, dcard = self.p.start(g, "design")
        notes = dcard.get("notes") or []
        self.assertEqual(1, len(notes), dcard)
        self.assertEqual(("rename a helper", "slightly harder to read", self.n("simplicity_design"), "a preference"),
                         (notes[0]["text"], notes[0]["impact"], notes[0]["lens"], notes[0]["reason"]))
        self.assertNotIn(nid, [c["id"] for c in dcard["corrections"]])

    def test_a_material_claim_reopens_whatever_the_filter_thinks(self):
        g = self.goal()
        self.lenses_done(g, {"rollout_design": [{"findings": [lens_finding("no rollback path", True)]}]})
        fid = self.lens_finding_ids(g, "rollout_design")[0]
        card, _ = self.p.run(g, "filter_design")
        self.assertEqual(True, self.candidates_of(card)[fid]["material"])
        self.assertEqual("ready (reopened)", self.p.states(g)["design"])

    def test_a_note_promoted_to_keep_reopens_the_target(self):
        g = self.goal()
        self.lenses_done(g, {"experience_design": [{"findings": [lens_finding("the error message is wrong", False)]}],
                             "truth_design": [{"findings": [lens_finding("a nit", False)]}]})
        keep = self.lens_finding_ids(g, "experience_design")[0]
        nit = self.lens_finding_ids(g, "truth_design")[0]
        self.p.run(g, "filter_design", verdicts={keep: verdict("keep", "the operator gets stuck"),
                                                 nit: verdict("note", "a nit")})
        self.assertEqual("ready (reopened)", self.p.states(g)["design"])
        ag, dcard = self.p.start(g, "design")
        self.assertEqual([keep], [c["id"] for c in dcard["corrections"]])
        self.assertEqual(["a nit"], [x["text"] for x in dcard.get("notes") or []])

    def test_filter_verdicts_must_cover_exactly_the_notes(self):
        g = self.goal()
        self.lenses_done(g, {"simplicity_design": [{"findings": [lens_finding("note one", False),
                                                                 lens_finding("note two", False)]}],
                             "truth_design": [{"findings": [lens_finding("material one", True)]}]})
        n1, n2 = self.lens_finding_ids(g, "simplicity_design")
        mat = self.lens_finding_ids(g, "truth_design")[0]
        ag, card = self.p.start(g, "filter_design")
        self.assertEqual({n1, n2, mat}, set(self.candidates_of(card)))
        for bad in ({n1: verdict("note")},                                        # missing a verdict
                    {n1: verdict("note"), n2: verdict("keep"), mat: verdict("note")},        # a material claim
                    {n1: verdict("note"), n2: verdict("keep"), "truth_design:9:9": verdict("note")},  # unknown id
                    {n1: verdict("drop"), n2: verdict("keep")},                    # not keep or note
                    {n1: {"verdict": "note"}, n2: verdict("keep")}):              # no reason
            out = {"summary": "filter", "verdicts": bad}
            rc, err = ag.submit(g, self.n("filter_design"), card, out, ok=False)
            self.assertNotEqual(0, rc, bad)
            self.assertEqual("validation", err["error"]["code"], err)
        self.assertIsNone(self.p.record(g, "filter_design"))              # nothing landed
        self.assertEqual("current", self.p.states(g)["design"])
        ag.submit(g, self.n("filter_design"), card,
                  {"summary": "filter", "verdicts": {n1: verdict("note"), n2: verdict("keep")}})
        self.assertTrue(self.p.record(g, "filter_design")["ok"])
        self.assertEqual("ready (reopened)", self.p.states(g)["design"])

    def test_lens_findings_need_impact_and_material(self):
        g = self.goal()
        self.p.drive(g, lambda st: st["truth_design"].startswith("ready"))
        ag, card = self.p.start(g, "truth_design")
        for f in ({"text": "no labels"}, {"text": "no impact", "material": True},
                  {"text": "empty impact", "impact": " ", "material": True},
                  {"text": "not a bool", "impact": "x", "material": "yes"}):
            rc, err = ag.submit(g, self.n("truth_design"), card,
                                {"decision": "changes_requested", "summary": "s", "findings": [f]}, artifact="# r\n",
                                ok=False)
            self.assertNotEqual(0, rc, f)
            self.assertEqual("validation", err["error"]["code"], err)
        ag.submit(g, self.n("truth_design"), card, {"decision": "changes_requested", "summary": "s",
                                                    "findings": [lens_finding("labelled", True)]}, artifact="# r\n")

    def test_unfiltered_reviews_and_humans_are_unchanged(self):
        """review_tests has no filter: findings need no impact/material, and its record is not ok."""
        g = self.goal()
        self.p.drive(g, lambda st: st["review_tests"].startswith("ready"))
        self.p.run(g, "review_tests", findings=[{"text": "a test is missing"}])
        r = self.p.record(g, "review_tests")
        self.assertFalse(r["ok"])
        self.assertEqual("ready (reopened)", self.p.states(g)["test_design"])

    def test_a_crash_looping_lens_leaves_the_filter_visibly_blocked(self):
        g = self.goal()
        self.p.drive(g, lambda st: st["concurrency_design"].startswith("ready"))
        for lens in lens_ids():
            if lens in ("concurrency_design", "intent_design"):
                continue
            self.p.run(g, lens)
        for lens in ("concurrency_design", "intent_design"):
            for _ in range(3):
                ag, card = self.p.start(g, lens)
                ag.submit(g, self.n(lens), card, blocked={"waiting_for": "agent", "instructions": "try again",
                                                          "reason": "tool crashed"})
        st = self.p.states(g)
        self.assertTrue(st["filter_design"].startswith("blocked"), st["filter_design"])
        self.assertIn(self.n("concurrency_design"), st["filter_design"])
        nxt = self.w.ok("a", "next", "--goal", str(g))
        items = {x["node"]: x for x in nxt["needs_human"] if x["kind"] == "crash_loop"}
        self.assertIn(self.n("concurrency_design"), items)
        self.assertIn(self.n("intent_design"), items)
        sets = lambda it: [k for o in it.get("options", []) for k in ((o.get("file") or {}).get("set") or {})]
        self.assertIn(f"skip.{self.n('concurrency_design')}", sets(items[self.n("concurrency_design")]))
        self.assertNotIn(f"skip.{self.n('intent_design')}", sets(items[self.n("intent_design")]))

    def test_a_filter_holder_who_produced_the_subject_is_refused(self):
        g = self.goal()
        self.lenses_done(g)
        designer = self.p.record(g, "design")["holder"]
        ag = next(a for a in self.p.agents if a.label == designer)
        rc, err = ag.start(g, self.n("filter_design"), ok=False)
        self.assertNotEqual(0, rc)
        self.assertEqual("independence", err["error"]["code"], err)
        self.p.run(g, "filter_design", avoid=(designer,))

    def unjudged_note(self, change):
        """F1: a lens re-run that adds a note stales the filter on `candidates` alone."""
        g = self.goal()
        hooks = {"intent_design": [{"summary": "intent: serves the purpose"}]}
        self.p.drive(g, lambda st: st["approve_design"] == "needs_human (approve)", hooks)
        filter_runs = self.p.record(g, "filter_design")["correction_runs"]
        change()
        st = self.p.states(g)
        self.assertTrue(st["intent_design"].startswith("ready (stale"), st["intent_design"])
        self.p.run(g, "intent_design", summary="intent: serves the purpose",
                   findings=[lens_finding("the principle wording drifts", False)])
        nid = self.lens_finding_ids(g, "intent_design")[0]
        st = self.p.states(g)
        self.assertEqual("ready (stale: candidates)", st["filter_design"])
        self.assertEqual("current", st["design"])                          # not reopened ...
        self.assertTrue(st["approve_design"].startswith("blocked"), st["approve_design"])   # ... nor advanced past
        self.assertTrue(st["base"].startswith("blocked"), st["base"])
        return g, nid, filter_runs

    def check_unjudged_note(self, change):
        g, nid, runs = self.unjudged_note(change)
        card, _ = self.p.run(g, "filter_design", verdicts={nid: verdict("keep", "the owner's principle is at stake")})
        self.assertEqual(["candidates"], card.get("stale_because"))
        self.assertIn(nid, self.candidates_of(card))
        self.assertEqual(runs, self.p.record(g, "filter_design")["correction_runs"])     # no budget
        self.assertEqual("ready (reopened)", self.p.states(g)["design"])

    def check_unjudged_note_judged_note(self, change):
        g, nid, runs = self.unjudged_note(change)
        self.p.run(g, "filter_design", verdicts={nid: verdict("note", "wording only")})
        self.assertEqual(runs, self.p.record(g, "filter_design")["correction_runs"])
        st = self.p.states(g)
        self.assertEqual("current", st["design"])
        self.assertEqual("needs_human (approve)", st["approve_design"])
        self.p.answer(g, "approve_design", decision="changes_requested")
        ag, dcard = self.p.start(g, "design")
        self.assertIn("the principle wording drifts", [x["text"] for x in dcard.get("notes") or []])

    def test_unjudged_note_after_an_intent_change_keep(self):
        self.check_unjudged_note(lambda: self.set_intent(dict(INTENT, purpose="Ship small, fast tools.")))

    def test_unjudged_note_after_an_intent_change_note(self):
        self.check_unjudged_note_judged_note(lambda: self.set_intent(dict(INTENT, purpose="Ship small, fast tools.")))

    def test_unjudged_note_after_a_lens_rev_bump_keep(self):
        self.check_unjudged_note(lambda: self.bump_rev("intent_design"))

    def test_unjudged_note_after_a_lens_rev_bump_note(self):
        self.check_unjudged_note_judged_note(lambda: self.bump_rev("intent_design"))

    def test_a_lens_reconfirming_the_same_notes_leaves_the_filter_fresh(self):
        g = self.goal()
        self.lenses_done(g, {"simplicity_design": [{"summary": "simplicity: one note",
                                                    "findings": [lens_finding("merge two helpers", False)]}]})
        nid = self.lens_finding_ids(g, "simplicity_design")[0]
        self.p.run(g, "filter_design", verdicts={nid: verdict("note", "a preference")})
        self.bump_rev("simplicity_design")
        st = self.p.states(g)
        self.assertTrue(st["simplicity_design"].startswith("ready (stale"), st)
        card, _ = self.p.run(g, "simplicity_design", keep_open=(nid,), summary="simplicity: one note")
        st = self.p.states(g)
        self.assertEqual("current", st["filter_design"])
        self.assertEqual("current", st["design"])
        self.assertEqual("needs_human (approve)", st["approve_design"])

    def test_a_fresh_filter_record_without_a_verdict_keeps_the_note(self):
        g = self.goal()
        self.lenses_done(g, {"simplicity_design": [{"findings": [lens_finding("merge two helpers", False)]}]})
        nid = self.lens_finding_ids(g, "simplicity_design")[0]
        self.p.run(g, "filter_design", verdicts={nid: verdict("note", "a preference")})
        self.assertEqual("current", self.p.states(g)["design"])
        tip = self.p.tip(g)
        self.w.seed.git("fetch", "-q", "origin", f"refs/heads/zzzops/goal/g{g}")
        doc = json.loads(self.w.seed.git("show", "FETCH_HEAD:goal.json"))
        doc["records"][self.n("filter_design")]["output"]["verdicts"] = {}
        push_goal_doc(self.w, doc, tip)
        st = self.p.states(g)
        self.assertEqual("current", st["filter_design"])                     # still fresh
        self.assertEqual("ready (reopened)", st["design"])                   # the unjudged note is live
        ag, dcard = self.p.start(g, "design")
        self.assertEqual([nid], [c["id"] for c in dcard["corrections"]])


# --------------------------------------------------------------------------------------------- intent


class IntentTests(LensWorld):
    def test_the_intent_lens_card_shows_policy_intent(self):
        g = self.goal()
        self.through_design(g)
        ag, card = self.p.start(g, "intent_design")
        self.assertEqual({"intent": INTENT}, card.get("policy"))
        ag, card = self.p.start(g, "truth_design", avoid=(ag.label,))
        self.assertNotIn("intent", card.get("policy") or {})

    def test_changing_intent_stales_only_the_intent_lenses(self):
        g = self.goal()
        self.p.drive(g, lambda st: st["approve_design"] == "needs_human (approve)")
        self.set_intent(dict(INTENT, serves="Operators too."))
        st = self.p.states(g)
        self.assertEqual("ready (stale: policy.intent)", st["intent_design"])
        stale = sorted(n for n, s in st.items() if s.startswith("ready (stale"))
        self.assertEqual(["intent_design"], stale, st)
        for lens in lens_ids():
            if lens != "intent_design":
                self.assertEqual("current", st[lens], lens)
        self.assertEqual("current", st["design"])
        # the intent re-run is exempt from the budget
        self.p.run(g, "intent_design")
        self.assertEqual(0, self.p.record(g, "intent_design")["correction_runs"])


# --------------------------------------------------------------------------------------------- re-review pointer


class PointerTests(LensWorld):
    def test_reviewed_records_the_subject_artifact_on_a_fresh_submit_only(self):
        g = self.goal()
        self.through_design(g)
        doc = self.p.record(g, "design")["output"]["doc"]
        self.p.run(g, "simplicity_design")
        reviewed = self.p.record(g, "simplicity_design").get("reviewed") or {}
        self.assertEqual((doc["blob"], doc["commit"]),
                         ((reviewed.get("doc") or {}).get("blob"), (reviewed.get("doc") or {}).get("commit")), reviewed)
        # a lease overtaken by a design change lands stale and records no `reviewed`
        ag, card = self.p.start(g, "truth_design")
        self.w.ok("a", "edit", str(g), "--set", 'spec="a changed spec"', "--base", self.p.tip(g))
        ag.submit(g, self.n("truth_design"), card, self.p.output(self.n("truth_design"), card), artifact="# r\n")
        r = self.p.record(g, "truth_design")
        self.assertEqual("done", r["status"])
        self.assertNotIn("doc", r.get("reviewed") or {}, r)

    def test_a_missing_old_blob_says_review_in_full(self):
        g = self.goal()
        self.lenses_done(g, {"truth_design": [{"findings": [lens_finding("wrong claim", True)]}]})
        self.p.run(g, "filter_design")
        self.p.run(g, "design")
        tip = self.p.tip(g)
        self.w.seed.git("fetch", "-q", "origin", f"refs/heads/zzzops/goal/g{g}")
        doc = json.loads(self.w.seed.git("show", "FETCH_HEAD:goal.json"))
        r = doc["records"][self.n("truth_design")]
        self.assertIn("doc", r.get("reviewed") or {}, r)
        r["reviewed"]["doc"]["blob"] = HEX40
        push_goal_doc(self.w, doc, tip)
        ag, card = self.p.start(g, "truth_design")
        prev = json.dumps(card.get("previous"))
        self.assertIn("previous version not available; review in full", prev)
        self.assertNotIn(f"git diff {HEX40}", prev)


if __name__ == "__main__":
    unittest.main()
