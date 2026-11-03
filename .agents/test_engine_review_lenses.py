"""G1022: one multi-lens reviewer per subject, plus a separate design Adversary (design revision 2, §3-§9).

These tests run on the SHIPPED template (`fx.SHIPPED`, the 15-node graph). The G1000/G1020 lens tests run on the
frozen 26-node template (`fx.GRAPH26`); the other engine tests on the frozen 12-node graph (`fx.TEMPLATES`). They
are written before the implementation and define these contracts:

- An agent review node may declare `lenses`: an ordered object {"<lens>": {"prompt": <file>, "skippable"?: bool}}.
  A non-skippable lens requires a non-skippable node. A node without `lenses` behaves as in G1000.
- A goal removes a lens with the skip key `<node>:<lens>`. A new key naming a non-skippable lens is refused
  ("... is not skippable (lenses.<lens>.skippable: false in workflow.json)"); on reading it only warns. An unknown
  lens (or a lens key on a node without `lenses`) only warns.
- Every new finding of a node with `lenses` carries `lens`, one of the node's declared lenses (a skipped one is
  accepted). Display labels are `<node>:<lens>` (untagged: `<node>`) on candidates, notes and approval items.
- A reviewer card has `lenses: {apply, skipped, text}`; `text` may be a blob view after shrink.
- A reviewer's fingerprint has a `lenses` part (applied lens names); a `lenses`-only stale does not count against
  the budget. `node_def_fp` covers `lenses` only on nodes that have it.
- Approval items carry `lenses: {<node>: {apply, skipped}}`; the PR body writes
  `- **<node>** (<applied lenses>): <summary>` and `- **<node>:<lens>**: skipped: <reason>`.
- `Graph.lenses(filter)` is renamed `Graph.reviewers(filter)`.
"""

from __future__ import annotations

import copy
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

import engine_fixtures as fx
from engine import schemas
from engine.ops import OPS
from test_engine_lenses import INTENT, Pilot, push_goal_doc, verdict
from test_engine_schemas import default_goal, record

DESIGN_LENSES = ["intent", "simplicity", "truth", "adversary", "concurrency", "rollout", "experience"]
DESIGN_REQUIRED = {"intent", "simplicity"}
IMPL_LENSES = ["compliance", "correctness", "missing", "tests", "craft"]
IMPL_REQUIRED = {"compliance", "missing", "craft"}
SHIPPED_NODES = ["design", "review_design", "adversary_design", "filter_design", "approve_design", "base",
                 "test_design", "review_tests", "implement", "run_tests", "review_impl", "filter_impl", "integrate",
                 "approve_merge", "merge"]
MISSING_GREP = "git grep <pattern> <code.commit>"
SHIPPED_RENAME = {n: f"n{i + 1:02d}_x" for i, n in enumerate(SHIPPED_NODES)}
LENS_RENAME = dict({l: f"dl{i + 1}" for i, l in enumerate(DESIGN_LENSES)},
                   **{l: f"il{i + 1}" for i, l in enumerate(IMPL_LENSES)})
GOLDEN = fx.ROOT / ".agents" / "fixtures" / "node_def_fp_1.1.json"


def shipped(name: str) -> dict:
    return json.loads((fx.SHIPPED / name).read_text(encoding="utf-8"))


def fixture(graph: str, name: str) -> dict:
    return json.loads((fx.ROOT / ".agents" / "fixtures" / graph / name).read_text(encoding="utf-8"))


def shipped_prompt_exists(name: str) -> bool:
    return (fx.SHIPPED / "prompts" / name).is_file()


def prompt_text(name: str) -> str:
    return (fx.SHIPPED / "prompts" / name).read_text(encoding="utf-8")


def heading(prompt: str) -> str:
    return next(l.strip() for l in prompt_text(prompt).splitlines() if l.strip())


def tag(text: str, material: bool, lens: str, impact="something concrete goes wrong", target=None) -> dict:
    f = {"text": text, "impact": impact, "material": material, "lens": lens}
    if target:
        f["target"] = target
    return f


def renamed_shipped() -> dict:
    """The shipped workflow with every node id and every lens name renamed."""
    wf = fx.renamed_workflow(shipped("workflow.json"), SHIPPED_RENAME)
    for g in wf["graphs"].values():
        for nd in g["nodes"].values():
            if "filter" in (nd.get("review") or {}):
                nd["review"]["filter"] = SHIPPED_RENAME.get(nd["review"]["filter"], nd["review"]["filter"])
            if "lenses" in nd:
                nd["lenses"] = {LENS_RENAME[k]: v for k, v in nd["lenses"].items()}
    return wf


def policy_with_intent(base: dict | None = None) -> dict:
    p = copy.deepcopy(base or shipped("POLICY.json"))
    p["settings"]["intent"] = copy.deepcopy(INTENT)
    return p


def read_text_view(w: fx.World, v) -> str:
    """The text of an inline string, a {text} view or a blob view (read from whichever clone holds it)."""
    if isinstance(v, str):
        return v
    if "text" in v:
        return v["text"]
    for c in w.clones.values():
        out = c.git("cat-file", "-p", v["blob"], check=False)
        if out:
            return out
    raise AssertionError(f"blob {v['blob']} not found in any clone")


def run_cli(*argv, cwd=None):
    nowhere = cwd or tempfile.mkdtemp()
    p = subprocess.run([sys.executable, str(fx.PLUGIN_CODE / "zzzops.py"), *argv], cwd=nowhere, capture_output=True,
                       text=True)
    return p.returncode, json.loads(p.stdout)


# --------------------------------------------------------------------------------------------- 1: template


class ShippedTemplateTests(unittest.TestCase):
    def setUp(self):
        self.wf = shipped("workflow.json")
        self.policy = shipped("POLICY.json")
        self.nodes = self.wf["graphs"]["default"]["nodes"]

    def test_validate_policy_passes_with_exactly_one_placeholder_warning(self):
        rc, out = run_cli("validate", "--policy", "--dir", str(fx.SHIPPED))
        self.assertEqual(0, rc, out)
        self.assertTrue(out["ok"], out)
        self.assertEqual(["intent_placeholder"], [w["kind"] for w in out["warnings"]], out)

    def test_shipped_templates_validate(self):
        self.assertEqual([], schemas.validate_policy(self.policy))
        self.assertEqual([], schemas.validate_workflow(self.wf, self.policy, shipped_prompt_exists, OPS))

    def test_the_15_node_graph(self):
        self.assertEqual(SHIPPED_NODES, list(self.nodes))
        agents = [n for n, nd in self.nodes.items() if nd["kind"] == "agent"]
        self.assertEqual(9, len(agents), agents)           # the default budget is 3 x 9 = 27
        for lens in DESIGN_LENSES:
            if lens != "adversary":
                self.assertNotIn(f"{lens}_design", self.nodes)
            self.assertNotIn(f"{lens}_impl", self.nodes)

    def test_review_fan_in(self):
        g = schemas.build_graph("default", self.wf["graphs"]["default"])
        self.assertEqual(["review_design", "adversary_design"], g.reviewers("filter_design"))
        self.assertEqual(["review_impl"], g.reviewers("filter_impl"))
        self.assertEqual([], g.reviewers("design"))
        self.assertTrue(g.is_filter("filter_design") and g.is_filter("filter_impl"))

    def test_review_design_definition(self):
        nd = self.nodes["review_design"]
        self.assertEqual(("agent", "reasoning", "discovery", False, "review.md"),
                         (nd["kind"], nd["capability"], nd["stage"], nd["skippable"], nd["prompt"]))
        self.assertEqual({"subject": "design", "filter": "filter_design"}, nd["review"])
        self.assertEqual({"spec": "goal.spec", "doc": "design.doc"},
                         {k: s["from"] for k, s in nd["inputs"].items()})
        self.assertEqual(["intent"], nd.get("policy"))
        self.assertTrue({"review", "communication"} <= set(nd["instructions"]), nd["instructions"])
        self.assertEqual(DESIGN_LENSES, list(nd["lenses"]))
        for lens, spec in nd["lenses"].items():
            self.assertEqual(f"lens_{lens}.md", spec["prompt"], lens)
            self.assertEqual(lens not in DESIGN_REQUIRED, spec.get("skippable", True), lens)

    def test_review_impl_definition(self):
        nd = self.nodes["review_impl"]
        self.assertEqual(("agent", "reasoning", "delivery", False, "review.md"),
                         (nd["kind"], nd["capability"], nd["stage"], nd["skippable"], nd["prompt"]))
        self.assertEqual({"subject": "implement", "filter": "filter_impl"}, nd["review"])
        froms = {k: (s["from"], bool(s.get("context"))) for k, s in nd["inputs"].items()}
        self.assertEqual({"doc": ("design.doc", False), "tests": ("test_design.tests.change", False),
                          "code": ("implement.code.change", False), "checks": ("run_tests.result", True),
                          "cost": ("test_design.cost", True)}, froms)
        self.assertNotIn("spec", nd["inputs"])                 # D6: compliance judges against the approved design
        self.assertEqual([], nd.get("policy", []))              # project intent is judged once, at design
        self.assertTrue({"review", "communication", "security", "code_quality"} <= set(nd["instructions"]),
                        nd["instructions"])
        self.assertEqual(IMPL_LENSES, list(nd["lenses"]))
        for lens, spec in nd["lenses"].items():
            self.assertEqual(f"lens_{lens}.md", spec["prompt"], lens)
            self.assertEqual(lens not in IMPL_REQUIRED, spec.get("skippable", True), lens)

    def test_adversary_design_is_g1000s_node_byte_for_byte(self):
        """Adjusted by G1026: the node also lists the `owner_questions` instruction (instructions are not
        fingerprinted, so its node_def_fp is still G1000's)."""
        g26 = fixture("graph26", "workflow.json")["graphs"]["default"]["nodes"]["adversary_design"]
        ours = copy.deepcopy(self.nodes["adversary_design"])
        ours["instructions"] = [i for i in ours.get("instructions") or [] if i != "owner_questions"]
        self.assertEqual(g26, ours)
        self.assertNotIn("lenses", self.nodes["adversary_design"])

    def test_filter_and_downstream_wiring(self):
        fd = {k: (s["from"], bool(s.get("optional")), bool(s.get("context")))
              for k, s in self.nodes["filter_design"]["inputs"].items()}
        self.assertEqual({"spec": ("goal.spec", False, False), "doc": ("design.doc", False, False),
                          "review": ("review_design.summary", False, False),
                          "adversary": ("adversary_design.summary", True, False)}, fd)
        fi = {k: (s["from"], bool(s.get("optional")), bool(s.get("context")))
              for k, s in self.nodes["filter_impl"]["inputs"].items()}
        self.assertEqual({"doc": ("design.doc", False, False), "code": ("implement.code.change", False, False),
                          "review": ("review_impl.summary", False, False)}, fi)
        for f in ("filter_design", "filter_impl"):
            self.assertIs(False, self.nodes[f]["skippable"])
            self.assertEqual({"summary": "text", "verdicts": "object"}, self.nodes[f]["outputs"])
        ad = self.nodes["approve_design"]["inputs"]
        self.assertEqual(("filter_design.summary", False), (ad["filter"]["from"], bool(ad["filter"].get("context"))))
        ctx = {s["from"]: bool(s.get("optional")) for s in ad.values() if s.get("context")}
        self.assertEqual({"review_design.summary": False, "adversary_design.summary": True},
                         {k: v for k, v in ctx.items() if k.split(".")[0] in ("review_design", "adversary_design")})
        for n in ("integrate", "approve_merge"):
            froms = {s["from"]: bool(s.get("context")) for s in self.nodes[n]["inputs"].values()}
            self.assertTrue(froms.get("filter_impl.summary"), (n, froms))
            self.assertTrue(froms.get("review_impl.summary"), (n, froms))
        for n, nd in self.nodes.items():                     # nothing reads a removed lens node
            for s in (nd.get("inputs") or {}).values():
                producer = s["from"].split(".")[1 if s["from"].startswith("deps.") else 0]
                self.assertTrue(producer in self.nodes or producer == "goal", (n, s["from"]))

    def test_every_node_and_lens_prompt_exists_and_old_ones_are_gone(self):
        for n, nd in self.nodes.items():
            if nd["kind"] != "op":
                self.assertTrue(shipped_prompt_exists(nd["prompt"]), (n, nd["prompt"]))
            for lens, spec in (nd.get("lenses") or {}).items():
                self.assertTrue(shipped_prompt_exists(spec["prompt"]), (n, lens))
        for name in ("review.md", "filter.md", *(f"lens_{l}.md" for l in DESIGN_LENSES + IMPL_LENSES)):
            self.assertTrue(shipped_prompt_exists(name), name)
        self.assertFalse(shipped_prompt_exists("review_design.md"))
        self.assertFalse(shipped_prompt_exists("review_impl.md"))

    def test_package_ships_every_template_prompt(self):
        sys.path.insert(0, str(fx.PLUGIN_CODE))
        text = (fx.PLUGIN_CODE / "package.py").read_text(encoding="utf-8")
        listed = set(re.findall(r'"zzzops/templates/default/prompts/([^"]+)"', text))
        on_disk = {p.name for p in (fx.SHIPPED / "prompts").iterdir()}
        self.assertEqual(on_disk, listed)

    def test_engine_version_or_capability_marks_the_new_shapes(self):
        """A 1.1 engine must not read `lenses`/`lens`. If G1027's capability files landed first, the engine declares
        `engine/capabilities/lenses.txt` and the template requires `lenses` (root hand-off; G1027 deletes
        ENGINE_VERSION); otherwise the engine takes the next minor version (§8)."""
        import engine
        cap = fx.PLUGIN_CODE / "engine" / "capabilities" / "lenses.txt"
        if cap.is_file():
            requires = shipped("POLICY.json")["settings"]["engine"].get("requires") or []
            self.assertIn("lenses", requires, requires)
            return
        version = getattr(engine, "ENGINE_VERSION", None)
        self.assertIsNotNone(version, f"neither {cap} nor engine.ENGINE_VERSION exists")
        self.assertGreaterEqual(tuple(int(x) for x in version.split(".")), (1, 2, 0), version)


class ShippedPromptTextTests(unittest.TestCase):
    def test_review_prompt_explains_the_lens_checklist(self):
        text = prompt_text("review.md")
        for needle in ("lenses.apply", "lenses.text", "lenses.skipped", "`lens`"):
            self.assertIn(needle, text, needle)

    def test_review_instruction_is_for_one_independent_reviewer_and_names_code_commit(self):
        text = shipped("POLICY.json")["instructions"]["review"]
        self.assertTrue(text.startswith("You are an independent reviewer"), text[:200])
        self.assertNotIn("each with one lens", text)
        self.assertIn("code.commit", text)
        self.assertIn("read_dev", text)
        self.assertIn("On code, target `test_design` for a problem in the tests", text)   # G1020's sentence stays

    def test_design_lens_prompts_have_no_code_lines(self):
        for lens in DESIGN_LENSES:
            self.assertNotIn("On code:", prompt_text(f"lens_{lens}.md"), lens)
        self.assertNotIn("for code, to the approved design", prompt_text("lens_intent.md"))

    def test_missing_lens_searches_the_goals_own_commit(self):
        text = prompt_text("lens_missing.md")
        self.assertIn(MISSING_GREP, text)
        self.assertIn("read_dev", text)                         # "not `read_dev`"

    def test_tests_lens_drops_the_targeting_sentence(self):
        self.assertNotIn("Test findings target `test_design`.", prompt_text("lens_tests.md"))

    def test_approval_and_worker_prompts_name_the_new_forms(self):
        for name in ("approve_design.md", "approve_merge.md"):
            text = prompt_text(name)
            self.assertNotIn("each lens verdict", text, name)
            self.assertIn("`lenses`", text, name)
            first = text.splitlines()[0]
            self.assertTrue(first.startswith("# ") and first.endswith("?"), first)
        for name in ("design.md", "implement.md"):
            self.assertIn("<node>:<lens>", prompt_text(name), name)

    def test_prompt_stats_check_passes(self):
        p = subprocess.run([sys.executable, str(fx.ROOT / ".agents" / "prompt_stats.py"), "--check"],
                           cwd=fx.ROOT, capture_output=True, text=True)
        self.assertEqual(0, p.returncode, p.stdout + p.stderr)


# --------------------------------------------------------------------------------------------- 2: validation


class LensValidationTests(unittest.TestCase):
    def setUp(self):
        self.wf = shipped("workflow.json")
        self.policy = policy_with_intent()
        self.nodes = self.wf["graphs"]["default"]["nodes"]

    def errors(self, exists=shipped_prompt_exists):
        return schemas.validate_workflow(self.wf, self.policy, exists, OPS)

    def assertRefused(self, needle=None):
        errs = self.errors()
        self.assertTrue(errs, "expected a validation error")
        if needle:
            self.assertTrue(any(needle in e for e in errs), errs)

    def test_lenses_on_a_non_review_node_is_refused(self):
        self.nodes["design"]["lenses"] = {"x": {"prompt": "lens_truth.md"}}
        self.assertRefused("lenses")

    def test_lenses_on_a_filter_is_refused(self):
        self.nodes["filter_impl"]["lenses"] = {"x": {"prompt": "lens_truth.md"}}
        self.assertRefused("lenses")

    def test_a_lens_prompt_that_does_not_exist_is_refused(self):
        self.nodes["review_impl"]["lenses"]["craft"]["prompt"] = "lens_nope.md"
        self.assertRefused("lens_nope.md")

    def test_a_non_skippable_lens_on_a_skippable_node_is_refused(self):
        self.nodes["review_impl"]["skippable"] = True
        self.assertRefused("skippable")
        del self.nodes["review_impl"]["skippable"]              # the default is skippable
        self.assertRefused("skippable")

    def test_a_skippable_node_with_only_skippable_lenses_is_accepted(self):
        nd = self.nodes["review_impl"]
        for spec in nd["lenses"].values():
            spec.pop("skippable", None)
        nd["skippable"] = True
        # the filter input from a skippable reviewer must then be optional (G1000's wiring rule)
        for n in ("filter_impl", "integrate", "approve_merge"):
            for s in self.nodes[n]["inputs"].values():
                if s["from"] == "review_impl.summary":
                    s["optional"] = True
        self.assertEqual([], self.errors())

    def test_bad_lens_shapes_are_refused(self):
        for bad in ({}, [], "lens_truth.md", {"Bad-Name": {"prompt": "lens_truth.md"}},
                    {"x": {"prompt": "lens_truth.md", "extra": 1}}, {"x": {}}, {"x": {"prompt": 3}},
                    {"x": {"prompt": "lens_truth.md", "skippable": "no"}}, {"x": "lens_truth.md"}):
            wf = copy.deepcopy(shipped("workflow.json"))
            wf["graphs"]["default"]["nodes"]["review_impl"]["lenses"] = bad
            errs = schemas.validate_workflow(wf, self.policy, shipped_prompt_exists, OPS)
            self.assertTrue(errs, bad)

    def test_graphs_without_lenses_validate_as_before(self):
        for graph in ("graph12", "graph26"):
            wf = fixture(graph, "workflow.json")
            policy = fixture(graph, "POLICY.json")
            if graph == "graph26":
                policy["settings"]["intent"] = copy.deepcopy(INTENT)
            exists = lambda name, graph=graph: (fx.ROOT / ".agents" / "fixtures" / graph / "prompts" / name).is_file()
            self.assertEqual([], schemas.validate_workflow(wf, policy, exists, OPS), graph)
            self.assertFalse(any("lenses" in nd for nd in wf["graphs"]["default"]["nodes"].values()), graph)

    def test_reviewers_replaces_graph_lenses(self):
        g = schemas.build_graph("default", fixture("graph26", "workflow.json")["graphs"]["default"])
        self.assertEqual([f"{l}_design" for l in DESIGN_LENSES], g.reviewers("filter_design"))


class LensSkipKeyTests(unittest.TestCase):
    """§4 goal `skip`: `<node>:<lens>` keys, validated against the workflow."""

    def setUp(self):
        self.wf = shipped("workflow.json")

    def check(self, skip, old=None, reading=False):
        return schemas.validate_goal(default_goal(skip=skip), old, None, self.wf, reading=reading)

    def test_an_optional_lens_skip_is_accepted_silently(self):
        for key in ("review_impl:tests", "review_impl:correctness", "review_design:concurrency",
                    "review_design:experience"):
            self.assertEqual(([], []), self.check({key: "docs-only goal"}), key)

    def test_a_new_skip_of_a_mandatory_lens_is_refused(self):
        for node, lens in [("review_design", l) for l in sorted(DESIGN_REQUIRED)] + \
                          [("review_impl", l) for l in sorted(IMPL_REQUIRED)]:
            errs, _ = self.check({f"{node}:{lens}": "not needed"})
            msg = " ".join(errs)
            self.assertIn(f"{node}:{lens}", msg)
            self.assertIn("is not skippable", msg)
            self.assertIn(f"lenses.{lens}.skippable: false in workflow.json", msg)

    def test_a_mandatory_lens_skip_already_held_only_warns(self):
        key = "review_design:intent"
        errs, warns = self.check({key: "x"}, reading=True)
        self.assertEqual([], errs)
        self.assertTrue(any(key in w["message"] for w in warns), warns)
        old = default_goal(skip={key: "x"})
        errs, _ = self.check({key: "x"}, old=old)
        self.assertEqual([], errs)

    def test_unknown_lens_keys_only_warn(self):
        for key in ("review_design:typo", "nosuch:tests", "design:truth", "adversary_design:adversary"):
            errs, warns = self.check({key: "x"})
            self.assertEqual([], errs, key)
            self.assertTrue(any(key.split(":")[1] in w["message"] and w["kind"] == "orphan_record" for w in warns),
                            (key, warns))

    def test_reason_rules_apply_to_lens_keys(self):
        errs, _ = self.check({"review_impl:tests": ""})
        self.assertTrue(errs)

    def test_lens_finding_key(self):
        f = {"id": "review_impl:2:1", "target": "implement", "target_fp": None, "target_attempt": None, "text": "t",
             "status": "open", "response": None, "rounds": 1, "upheld": False, "note": None, "impact": "x",
             "material": True}
        self.assertEqual([], schemas.validate_finding(dict(f, lens="missing")))
        self.assertTrue(schemas.validate_finding(dict(f, lens=3)))
        errs = schemas.validate_goal(default_goal(records={"review_impl": record(findings=[dict(f, lens="missing")])}),
                                     None, None, None)[0]
        self.assertEqual([], errs)


# --------------------------------------------------------------------------------------------- 9: fingerprints


class FingerprintStabilityTests(unittest.TestCase):
    def test_node_def_fp_of_graphs_without_lenses_is_unchanged(self):
        from engine.fingerprint import node_def_fp
        golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
        for graph in ("graph12", "graph26"):
            nodes = fixture(graph, "workflow.json")["graphs"]["default"]["nodes"]
            self.assertEqual(golden[graph], {n: node_def_fp(nd) for n, nd in nodes.items()}, graph)
        shipped_nodes = shipped("workflow.json")["graphs"]["default"]["nodes"]
        self.assertEqual(golden["graph26"]["adversary_design"], node_def_fp(shipped_nodes["adversary_design"]))

    def test_only_nodes_with_lenses_gain_the_lens_part(self):
        from engine.fingerprint import node_def_fp
        nd = shipped("workflow.json")["graphs"]["default"]["nodes"]["review_impl"]
        bare = {k: v for k, v in nd.items() if k != "lenses"}
        self.assertNotEqual(node_def_fp(bare), node_def_fp(nd))
        flipped = copy.deepcopy(nd)
        flipped["lenses"]["tests"]["skippable"] = False
        self.assertNotEqual(node_def_fp(nd), node_def_fp(flipped))
        added = copy.deepcopy(nd)
        added["lenses"]["extra"] = {"prompt": "lens_craft.md"}
        self.assertNotEqual(node_def_fp(nd), node_def_fp(added))
        reprompted = copy.deepcopy(nd)
        reprompted["lenses"]["tests"]["prompt"] = "lens_craft.md"      # prompts are not fingerprinted
        self.assertEqual(node_def_fp(nd), node_def_fp(reprompted))


# --------------------------------------------------------------------------------------------- 15: docs (12 is in test_engine_names.py)


class ContractDocsTests(unittest.TestCase):
    def test_g1022_landed_its_contract_edits(self):
        """G1017's rule (test 15): the pending row is deleted and HISTORY §4 logs G1022."""
        import test_design_docs as dd
        rows = dd.parse_pending_table(dd.read_doc("README.md"))
        self.assertNotIn(1022, [r.goal for r in rows])
        log = dd.section(dd.read_doc("HISTORY.md"), r"amendments after approval")
        self.assertTrue(any(re.search(r"\bG1022\b", l) for l in log.splitlines() if l.strip().startswith("|")))


# --------------------------------------------------------------------------------------------- World tests


class ReviewWorld(unittest.TestCase):
    """A World bootstrapped with the shipped 15-node template and a real intent."""

    renamed = False

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.w = fx.World(self.tmp)
        self.gh = fx.FakeGitHub(self.w)
        self.m = SHIPPED_RENAME if self.renamed else {}
        self.lm = LENS_RENAME if self.renamed else {}
        self.bootstrap()
        self.p = Pilot(self.w, self.m)

    def bootstrap(self):
        wf = renamed_shipped() if self.renamed else shipped("workflow.json")
        self.w.bootstrap(policy=policy_with_intent(), workflow=wf, prompts=False)
        self.push_prompts(fx.SHIPPED)

    def push_prompts(self, root):
        self.w.push_dev({f".zzzops/prompts/{p.name}": p.read_text(encoding="utf-8")
                         for p in sorted((root / "prompts").iterdir())}, "chore(zzzops): prompts")

    def n(self, x):
        return self.m.get(x, x)

    def l(self, lens):
        return self.lm.get(lens, lens)

    def key(self, node, lens):
        return f"{self.n(node)}:{self.l(lens)}"

    def goal(self, skip=None, **fields):
        return self.w.new(title="Review goal", skip=dict(skip or {}), **fields)["created"]["id"]

    def edit(self, g, *sets, ok=True):
        argv = ["edit", str(g)]
        for s in sets:
            argv += ["--set", s]
        argv += ["--base", self.p.tip(g)]
        if ok:
            return self.w.ok("a", *argv)
        return self.w.run("a", *argv)

    def open_ids(self, g, node):
        return [f["id"] for f in (self.p.record(g, node) or {}).get("findings", []) if f["status"] == "open"]

    def until_ready(self, g, node, hooks=None, limit=200):
        return self.p.drive(g, lambda st: st[node].startswith("ready"), hooks, limit=limit)

    def lens_text(self, card) -> str:
        return read_text_view(self.w, card["lenses"]["text"])

    def instruction_text(self, card, name) -> str:
        return read_text_view(self.w, card["instructions"][name])

    def submit(self, ag, g, node, card, out, ok=True):
        return ag.submit(g, self.n(node), card, out, artifact="# review\n" if card.get("artifact") else None, ok=ok)

    def runs(self, g) -> int:
        return sum(r.get("correction_runs", 0) for r in self.p.show(g)["goal"]["records"].values())


# --------------------------------------------------------------------------------------------- 3: cards


class ReviewerCardTests(ReviewWorld):
    def test_review_design_card_carries_the_lens_checklist(self):
        g = self.goal()
        self.p.drive(g, lambda st: st["design"] == "current")
        ag, card = self.p.start(g, "review_design")
        self.assertEqual([self.l(x) for x in DESIGN_LENSES], card["lenses"]["apply"])
        self.assertEqual({}, card["lenses"].get("skipped", {}))
        text = self.lens_text(card)
        for lens in DESIGN_LENSES:
            self.assertIn(heading(f"lens_{lens}.md"), text, lens)
        schema = card["output_schema"]["findings"]
        self.assertIn('"lens"', schema)
        for lens in DESIGN_LENSES:
            self.assertIn(f'"{self.l(lens)}"', schema, lens)
        from engine.canon import canonical
        from engine.card import CARD_LIMIT
        self.assertLessEqual(len(canonical({k: v for k, v in card.items() if k not in ("ok", "coordinator")})),
                             CARD_LIMIT)
        _, adv = self.p.start(g, "adversary_design", avoid=(ag.label,))
        self.assertNotIn("lenses", adv)
        self.assertNotIn('"lens"', adv["output_schema"]["findings"])

    def test_review_impl_card_searches_the_goals_own_commit(self):
        g = self.goal()
        self.until_ready(g, "review_impl")
        ag, card = self.p.start(g, "review_impl")
        self.assertEqual([self.l(x) for x in IMPL_LENSES], card["lenses"]["apply"])
        text = self.lens_text(card)
        for lens in IMPL_LENSES:
            self.assertIn(heading(f"lens_{lens}.md"), text, lens)
        self.assertIn(MISSING_GREP, text)
        self.assertIn("commit", card["inputs"]["code"])
        self.assertIn("code.commit", self.instruction_text(card, "review"))
        for name in ("security", "code_quality", "communication"):
            self.assertIn(name, card["instructions"], name)
        self.assertNotIn("spec", card["inputs"])
        self.assertNotIn("intent", card.get("policy") or {})
        schema = card["output_schema"]["findings"]
        for lens in IMPL_LENSES:
            self.assertIn(f'"{self.l(lens)}"', schema, lens)
        from engine.canon import canonical
        from engine.card import CARD_LIMIT
        # G1026: review_impl lists the owner_questions instruction (a blob view); design §9 lets a review card
        # exceed the target by that one view, so the limit applies to the card without it.
        sized = {k: v for k, v in card.items() if k not in ("ok", "coordinator")}
        sized["instructions"] = {k: v for k, v in sized["instructions"].items() if k != "owner_questions"}
        self.assertLessEqual(len(canonical(sized)), CARD_LIMIT)


# --------------------------------------------------------------------------------------------- 4: lens tag


class LensTagTests(ReviewWorld):
    def test_new_findings_of_a_multi_lens_reviewer_need_a_declared_lens(self):
        g = self.goal()
        self.until_ready(g, "review_impl")
        ag, card = self.p.start(g, "review_impl")
        untagged = {"text": "no lens", "impact": "x", "material": True}
        for f in (untagged, dict(untagged, lens="style"), dict(untagged, lens=self.l("concurrency")),
                  dict(untagged, lens=3)):
            out = {"decision": "changes_requested", "summary": "s", "findings": [f]}
            rc, err = self.submit(ag, g, "review_impl", card, out, ok=False)
            self.assertNotEqual(0, rc, f)
            self.assertEqual("validation", err["error"]["code"], err)
        self.assertIsNone(self.p.record(g, "review_impl"))
        self.submit(ag, g, "review_impl", card, {"decision": "changes_requested", "summary": "s",
                                                 "findings": [tag("a real bug", True, self.l("correctness"))]})
        f = self.p.record(g, "review_impl")["findings"][0]
        self.assertEqual(self.l("correctness"), f["lens"])

    def test_tagged_findings_are_labelled_on_candidates_and_notes(self):
        g = self.goal()
        self.until_ready(g, "filter_impl", {"review_impl": [{"findings": [
            tag("sibling path left behind", False, self.l("missing")),
            tag("off by one", True, self.l("correctness"))]}]})
        r = self.p.record(g, "review_impl")
        by_lens = {f["lens"]: f["id"] for f in r["findings"]}
        note_id, mat_id = by_lens[self.l("missing")], by_lens[self.l("correctness")]
        card, _ = self.p.run(g, "filter_impl", verdicts={note_id: verdict("note", "a nit")})
        cands = {c["id"]: c for c in card["candidates"]}
        self.assertEqual(self.key("review_impl", "missing"), cands[note_id]["lens"])
        self.assertEqual(self.key("review_impl", "correctness"), cands[mat_id]["lens"])
        self.assertEqual("ready (reopened)", self.p.states(g)["implement"])
        ag, icard = self.p.start(g, "implement")
        self.assertEqual([mat_id], [c["id"] for c in icard["corrections"]])
        self.assertEqual([(note_id, self.key("review_impl", "missing"))],
                         [(x["id"], x["lens"]) for x in icard.get("notes") or []])

    def test_design_notes_are_grouped_by_label_on_the_approval(self):
        g = self.goal()
        self.until_ready(g, "filter_design", {"review_design": [{"findings": [
            tag("a wording nit", False, self.l("truth"))]}]})
        nid = self.open_ids(g, "review_design")[0]
        self.p.drive(g, lambda st: st["approve_design"] == "needs_human (approve)",
                     {"filter_design": [{"verdicts": {nid: verdict("note", "wording only")}}]})
        item = self.p.item(g, "approve_design")
        notes = (item.get("notes") or {}).get(self.key("review_design", "truth")) or []
        self.assertEqual([nid], [x["id"] for x in notes], item.get("notes"))
        self.assertEqual({"apply": [self.l(x) for x in DESIGN_LENSES], "skipped": {}},
                         (item.get("lenses") or {}).get(self.n("review_design")), item.get("lenses"))


# --------------------------------------------------------------------------------------------- 5/6: skips


class LensSkipTests(ReviewWorld):
    REASON = "docs only, owner agreed"

    def test_removing_an_optional_lens_shows_on_cards_the_approval_and_the_pr(self):
        g = self.goal(skip={self.key("review_impl", "tests"): self.REASON})
        self.until_ready(g, "review_impl")
        self.assertNotEqual("skipped", self.p.states(g)["review_impl"])
        ag, card = self.p.start(g, "review_impl")
        applied = [self.l(x) for x in IMPL_LENSES if x != "tests"]
        self.assertEqual(applied, card["lenses"]["apply"])
        self.assertEqual({self.l("tests"): self.REASON}, card["lenses"]["skipped"])
        self.assertNotIn(heading("lens_tests.md"), self.lens_text(card))
        self.submit(ag, g, "review_impl", card, self.p.output(self.n("review_impl"), card,
                                                               summary="review_impl looks right"))
        self.p.drive(g, lambda st: st["approve_merge"] == "needs_human (approve)" and st["integrate"] == "current",
                     limit=200)
        item = self.p.item(g, "approve_merge")
        self.assertEqual({"apply": applied, "skipped": {self.l("tests"): self.REASON}},
                         (item.get("lenses") or {}).get(self.n("review_impl")), item.get("lenses"))
        body = next(iter(self.gh.load()["prs"].values()))["body"]
        self.assertIn(f"- **{self.n('review_impl')}** ({', '.join(applied)}): review_impl looks right", body)
        self.assertIn(f"- **{self.key('review_impl', 'tests')}**: skipped: {self.REASON}", body)

    def test_edit_adds_and_removes_a_lens_skip(self):
        g = self.goal()
        key = self.key("review_impl", "tests")
        self.edit(g, f'skip.{key}="{self.REASON}"')
        self.assertEqual({key: self.REASON}, self.p.show(g)["goal"]["skip"])
        self.edit(g, f"skip.{key}=null")
        self.assertEqual({}, self.p.show(g)["goal"]["skip"])

    def test_new_refuses_a_mandatory_lens_skip(self):
        for node, lens in (("review_design", "intent"), ("review_design", "simplicity"),
                           ("review_impl", "compliance"), ("review_impl", "missing"), ("review_impl", "craft")):
            rc, err = self.w.run("a", "new", "--file", self.w.file({"title": "t", "spec": f"s {node} {lens}",
                                                                     "skip": {self.key(node, lens): "not needed"}}))
            self.assertNotEqual(0, rc, (node, lens))
            msg = json.dumps(err)
            self.assertIn(self.key(node, lens), msg)
            self.assertIn("not skippable", msg)
            self.assertIn(f"lenses.{self.l(lens)}.skippable: false", msg)

    def test_edit_refuses_a_mandatory_lens_and_node_skips_of_reviewers(self):
        g = self.goal()
        rc, err = self.edit(g, f'skip.{self.key("review_impl", "missing")}="no"', ok=False)
        self.assertNotEqual(0, rc, err)
        self.assertIn("not skippable", json.dumps(err))
        for node in ("review_design", "review_impl"):
            rc, err = self.edit(g, f'skip.{self.n(node)}="no"', ok=False)
            self.assertNotEqual(0, rc, (node, err))
            self.assertIn("not skippable", json.dumps(err))
        self.assertEqual({}, self.p.show(g)["goal"]["skip"])

    def test_a_held_mandatory_lens_skip_warns_and_the_goal_stays_valid(self):
        """A policy made a lens mandatory after the goal skipped it: reading warns, the goal is not invalid."""
        g = self.goal()
        tip = self.p.tip(g)
        self.w.seed.git("fetch", "-q", "origin", f"refs/heads/zzzops/goal/g{g}")
        doc = json.loads(self.w.seed.git("show", "FETCH_HEAD:goal.json"))
        doc["skip"][self.key("review_design", "intent")] = "skipped before the policy change"
        push_goal_doc(self.w, doc, tip)
        self.assertIn(self.key("review_design", "intent"), self.p.show(g)["goal"]["skip"])
        rc, out = self.w.run("a", "validate")
        self.assertEqual([], out["goals"].get(str(g)), out)
        self.assertTrue(any(self.key("review_design", "intent") in w["message"] for w in out["warnings"]), out)

    def test_an_unknown_lens_skip_is_accepted_with_a_warning_and_the_lens_still_runs(self):
        key = f"{self.n('review_design')}:typo"
        g = self.goal(skip={key: "mistyped"})
        rc, out = self.w.run("a", "validate")
        self.assertTrue(any("typo" in w["message"] for w in out["warnings"]), out)
        self.p.drive(g, lambda st: st["design"] == "current")
        _, card = self.p.start(g, "review_design")
        self.assertEqual([self.l(x) for x in DESIGN_LENSES], card["lenses"]["apply"])


# --------------------------------------------------------------------------------------------- 7: freshness


class LensFreshnessTests(ReviewWorld):
    def test_unskipping_and_skipping_a_lens_stales_the_reviewer_without_budget(self):
        key = self.key("review_impl", "tests")
        g = self.goal(skip={key: "docs only"})
        self.p.drive(g, lambda st: st["review_impl"] == "current", limit=200)
        before = self.p.record(g, "review_impl")["correction_runs"]
        self.edit(g, f"skip.{key}=null")
        self.assertEqual("ready (stale: lenses)", self.p.states(g)["review_impl"])
        card, _ = self.p.run(g, "review_impl")
        self.assertEqual(["lenses"], card.get("stale_because"))
        self.assertIn(self.l("tests"), card["lenses"]["apply"])
        self.assertEqual(before, self.p.record(g, "review_impl")["correction_runs"])
        self.assertEqual("current", self.p.states(g)["review_impl"])
        self.edit(g, f'skip.{self.key("review_impl", "correctness")}="internal only"')
        self.assertEqual("ready (stale: lenses)", self.p.states(g)["review_impl"])
        self.p.run(g, "review_impl")
        self.assertEqual(before, self.p.record(g, "review_impl")["correction_runs"])

    def test_a_lens_prompt_change_does_not_stale_the_reviewer(self):
        g = self.goal()
        self.p.drive(g, lambda st: st["review_impl"] == "current", limit=200)
        self.w.push_dev({".zzzops/prompts/lens_tests.md": prompt_text("lens_tests.md") + "\nOne more question.\n"},
                        "chore(zzzops): lens text")
        self.assertEqual("current", self.p.states(g)["review_impl"])


# --------------------------------------------------------------------------------------------- 8: no finding lost


class NoFindingLostTests(ReviewWorld):
    def test_skipping_the_lens_of_an_open_finding_keeps_it(self):
        """Adjusted at rebase onto G1028: a material finding of a stale review is carried before its filter runs (G1028)."""
        g = self.goal()
        self.until_ready(g, "filter_design", {"review_design": [{"findings": [
            tag("lease race", True, self.l("concurrency"))]}]})
        fid = self.open_ids(g, "review_design")[0]
        self.edit(g, f'skip.{self.key("review_design", "concurrency")}="nothing runs concurrently"')
        self.assertEqual([fid], self.open_ids(g, "review_design"))
        # the stale review's material finding is carried (G1028): it reopens the design, and the reviewer waits
        st = self.p.states(g)
        self.assertEqual("ready (reopened)", st["design"])
        self.assertTrue(st["review_design"].startswith("blocked (design not current"), st["review_design"])
        dcard0, _ = self.p.run(g, "design")
        carried = {c["id"]: c for c in dcard0["corrections"]}
        self.assertIn(fid, carried)
        self.assertTrue(carried[fid].get("stale_review"))
        self.assertEqual([fid], self.open_ids(g, "review_design"))
        self.assertTrue(self.p.states(g)["review_design"].startswith("ready (stale"), self.p.states(g)["review_design"])
        ag, card = self.p.start(g, "review_design")
        self.assertIn(fid, [f["id"] for f in (card.get("previous") or {}).get("findings", [])])
        self.assertNotIn(self.l("concurrency"), card["lenses"]["apply"])
        self.assertIn(self.l("concurrency"), card["lenses"]["skipped"])
        # the finding stays open, and a new finding tagged with the skipped lens is accepted (D8)
        out = {"decision": "changes_requested", "summary": "still a race",
               "findings": [{"id": fid, "status": "open"}, tag("and a nit", False, self.l("concurrency"))]}
        self.submit(ag, g, "review_design", card, out)
        self.assertEqual(2, len(self.open_ids(g, "review_design")))
        nid = next(i for i in self.open_ids(g, "review_design") if i != fid)
        self.p.run(g, "adversary_design")
        fcard, _ = self.p.run(g, "filter_design", verdicts={nid: verdict("note", "a nit")})
        self.assertEqual(self.key("review_design", "concurrency"),
                         {c["id"]: c for c in fcard["candidates"]}[fid]["lens"])
        self.assertEqual("ready (reopened)", self.p.states(g)["design"])
        _, dcard = self.p.start(g, "design")
        self.assertIn(fid, [c["id"] for c in dcard["corrections"]])


# --------------------------------------------------------------------------------------------- 10: journey


class ReviewJourneyTests(ReviewWorld):
    def test_design_reviewers_run_in_parallel_and_reopen_the_design_once(self):
        g = self.goal()
        self.p.drive(g, lambda st: st["design"] == "current")
        nxt = self.w.ok("a", "next", "--goal", str(g))
        ready = sorted(self.p.rev.get(a["node"], a["node"]) for a in nxt["actions"] if a["goal"] == g)
        self.assertEqual(["adversary_design", "review_design"], ready)
        designer = self.p.record(g, "design")["holder"]
        r_ag, a_ag = fx.Agent(self.w, "b", "claude:1111/rev-1"), fx.Agent(self.w, "b", "claude:2222/adv-1")
        self.assertNotIn(designer, (r_ag.label, a_ag.label))
        rcard, acard = r_ag.start(g, self.n("review_design")), a_ag.start(g, self.n("adversary_design"))
        st = self.p.states(g)
        self.assertEqual(("running", "running"), (st["review_design"], st["adversary_design"]))
        self.assertTrue(st["filter_design"].startswith("blocked"), st["filter_design"])
        self.submit(r_ag, g, "review_design", rcard,
                    {"decision": "changes_requested", "summary": "r", "findings": [tag("gap", True, self.l("truth"))]})
        self.assertTrue(self.p.states(g)["filter_design"].startswith("blocked"))
        self.submit(a_ag, g, "adversary_design", acard,
                    {"decision": "changes_requested", "summary": "a",
                     "findings": [{"text": "can be gamed", "impact": "x", "material": True}]})
        self.p.run(g, "filter_design")
        self.assertEqual("ready (reopened)", self.p.states(g)["design"])
        _, dcard = self.p.start(g, "design")
        self.assertEqual(2, len(dcard["corrections"]))

    def test_a_skipped_adversary_lets_the_filter_run_on_the_reviewer_alone(self):
        g = self.goal(skip={self.n("adversary_design"): "small goal"})
        self.until_ready(g, "filter_design", {"review_design": [{"findings": [tag("a nit", False, self.l("truth"))]}]})
        self.assertEqual("skipped", self.p.states(g)["adversary_design"])
        card, _ = self.p.run(g, "filter_design")
        self.assertEqual({self.key("review_design", "truth")}, {c["lens"] for c in card["candidates"]})

    def test_g1000s_refusal_still_guards_a_node_skip_of_the_adversary(self):
        g = self.goal()
        self.p.drive(g, lambda st: st["design"] == "current")
        self.p.run(g, "adversary_design", findings=[{"text": "can be gamed", "impact": "x", "material": True}])
        fid = self.open_ids(g, "adversary_design")[0]
        rc, err = self.edit(g, f'skip.{self.n("adversary_design")}="noisy"', ok=False)
        self.assertNotEqual(0, rc, err)
        self.assertIn(fid, json.dumps(err))
        self.assertNotIn("not skippable", json.dumps(err))

    def test_review_impl_rereview_gets_the_change(self):
        g = self.goal()
        self.until_ready(g, "filter_impl", {"review_impl": [{"findings": [
            tag("off by one", True, self.l("correctness"))]}]})
        self.p.run(g, "filter_impl")
        self.p.run(g, "implement")
        self.until_ready(g, "review_impl")
        _, card = self.p.start(g, "review_impl")
        prev = card.get("previous") or {}
        self.assertTrue("interdiff" in prev or "changed" in prev, prev)


class RenamedReviewJourneyTests(ReviewWorld):
    """Test 13: the review journey on a renamed copy of the shipped graph, lens names renamed too."""

    renamed = True

    def test_renamed_graph_journey(self):
        reason = "docs only"
        rc, err = self.w.run("a", "new", "--file", self.w.file({"title": "t", "spec": "renamed refusal",
                                                                 "skip": {self.key("review_impl", "missing"): "no"}}))
        self.assertNotEqual(0, rc)
        self.assertIn("not skippable", json.dumps(err))
        g = self.goal(skip={self.key("review_impl", "tests"): reason})
        self.p.drive(g, lambda st: st["approve_merge"] == "needs_human (approve)" and st["integrate"] == "current",
                     {"review_impl": [{"summary": "renamed review ok"}]}, limit=200)
        applied = [self.l(x) for x in IMPL_LENSES if x != "tests"]
        body = next(iter(self.gh.load()["prs"].values()))["body"]
        self.assertIn(f"- **{self.n('review_impl')}** ({', '.join(applied)}): renamed review ok", body)
        self.assertIn(f"- **{self.key('review_impl', 'tests')}**: skipped: {reason}", body)

    def test_renamed_tags_and_labels(self):
        g = self.goal()
        self.until_ready(g, "filter_design", {"review_design": [{"findings": [
            tag("a nit", False, self.l("rollout"))]}]})
        card, _ = self.p.run(g, "filter_design")
        self.assertEqual([self.key("review_design", "rollout")], [c["lens"] for c in card["candidates"]])


# --------------------------------------------------------------------------------------------- 11: migration


class MigrationWorld(ReviewWorld):
    source = "graph12"

    def bootstrap(self):
        root = fx.ROOT / ".agents" / "fixtures" / self.source
        policy = fixture(self.source, "POLICY.json")
        if self.source == "graph26":
            policy["settings"]["intent"] = copy.deepcopy(INTENT)
        self.w.bootstrap(policy=policy, workflow=fixture(self.source, "workflow.json"), prompts=False)
        self.push_prompts(root)

    def adopt_shipped(self, include_cost=True):
        """The policy branch of §8: the 15-node workflow, its POLICY (with intent) and prompts."""
        policy = policy_with_intent()
        policy["settings"]["integration_branch"] = "dev"
        policy["settings"]["goals"]["first_id"] = 1000
        workflow = shipped("workflow.json")
        if not include_cost:
            # This isolated G1022 migration promises reviewer redefinition only.
            # G1043's required cost output intentionally reruns delivery instead.
            nodes = workflow["graphs"]["default"]["nodes"]
            nodes["test_design"]["outputs"].pop("cost")
            nodes["review_tests"]["inputs"].pop("cost")
            nodes["review_impl"]["inputs"].pop("cost")
        files = {".zzzops/POLICY.json": json.dumps(policy, indent=2) + "\n",
                 ".zzzops/workflow.json": json.dumps(workflow, indent=2) + "\n"}
        for p in sorted((fx.SHIPPED / "prompts").iterdir()):
            files[f".zzzops/prompts/{p.name}"] = p.read_text(encoding="utf-8")
        self.w.push_dev(files, "chore(zzzops): adopt the consolidated review graph")


class MigrationFrom12Tests(MigrationWorld):
    def test_in_flight_reviewers_go_stale_without_budget(self):
        g = self.goal()
        self.p.drive(g, lambda st: st["review_impl"] == "current", limit=200)
        used = self.runs(g)
        self.adopt_shipped(include_cost=False)
        st = self.p.states(g)
        self.assertEqual("ready (stale: def, lenses, policy.intent)", st["review_design"])
        self.assertEqual("ready (new)", st["adversary_design"])
        self.assertIsNone(self.p.record(g, "filter_design"))
        self.assertNotEqual("current", st["filter_design"])
        self.p.run(g, "review_design")
        self.p.run(g, "adversary_design")
        self.assertEqual("ready (new)", self.p.states(g)["filter_design"])
        self.p.run(g, "filter_design")
        self.p.drive(g, lambda st: st["review_impl"].startswith("ready"), limit=50)
        self.assertEqual("ready (stale: def, lenses)", self.p.states(g)["review_impl"])
        self.p.run(g, "review_impl")
        self.assertEqual(used, self.runs(g))

    def test_a_prior_untagged_finding_is_labelled_by_the_node_and_counts_as_material(self):
        g = self.goal()
        self.until_ready(g, "review_design", limit=50)
        self.p.run(g, "review_design", findings=[{"text": "an old finding"}])
        fid = self.open_ids(g, "review_design")[0]
        self.p.run(g, "design")
        self.adopt_shipped()
        self.assertTrue(self.p.states(g)["review_design"].startswith("ready (stale"), self.p.states(g))
        self.p.run(g, "review_design", keep_open=(fid,))
        self.p.run(g, "adversary_design")
        card, _ = self.p.run(g, "filter_design")
        c = {x["id"]: x for x in card["candidates"]}[fid]
        self.assertEqual((self.n("review_design"), True), (c["lens"], c["material"]))
        self.assertEqual("ready (reopened)", self.p.states(g)["design"])


class MigrationFrom26Tests(MigrationWorld):
    source = "graph26"

    def test_adversary_stays_current_and_old_lens_records_are_orphans(self):
        g = self.goal()
        self.p.drive(g, lambda st: st["approve_design"] == "needs_human (approve)")
        self.adopt_shipped()
        st = self.p.states(g)
        self.assertEqual("current", st["adversary_design"])
        self.assertEqual("ready (new)", st["review_design"])
        self.assertNotEqual("current", st["filter_design"])
        rc, out = self.w.run("a", "validate")
        orphans = " ".join(w["message"] for w in out["warnings"] if w["kind"] == "orphan_record")
        for lens in DESIGN_LENSES:
            if lens != "adversary":
                self.assertIn(f"{lens}_design", orphans, lens)
        self.assertNotIn("adversary_design", orphans)

    def test_a_goal_over_the_new_default_budget_needs_an_explicit_budget(self):
        g = self.goal()
        self.p.drive(g, lambda st: st["design"] == "current")
        tip = self.p.tip(g)
        self.w.seed.git("fetch", "-q", "origin", f"refs/heads/zzzops/goal/g{g}")
        doc = json.loads(self.w.seed.git("show", "FETCH_HEAD:goal.json"))
        doc["records"]["design"]["correction_runs"] = 28
        push_goal_doc(self.w, doc, tip)
        budget = lambda: [x for x in self.w.ok("a", "next", "--goal", str(g))["needs_human"]
                          if x["goal"] == g and x["kind"] == "budget"]
        self.assertEqual([], budget())                          # 28 of 60 under the 26-node graph
        self.adopt_shipped()
        self.assertTrue(budget(), "28 runs is over the 15-node default of 27")
        self.edit(g, "budget=40")
        self.assertEqual([], budget())


if __name__ == "__main__":
    unittest.main()
