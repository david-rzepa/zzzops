"""G1043 policy/templates/context: cheap schema checks plus one renamed CLI journey."""
from __future__ import annotations

import ast
import copy
import hashlib
import json
from pathlib import Path
import shutil
import shlex
import subprocess
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest import mock

import engine_fixtures as fx
import test_engine_lifecycle as lifecycle
from engine import schemas, render
from engine.fingerprint import fp_parts, input_fp
from engine.ops import OPS, checks as check_ops


def measured_test_script(git, script, cwd, env):
    """Measure the same portable shell/current-interpreter command checks.run uses."""
    command = shlex.join([sys.executable.replace("\\", "/"), script])
    resolved_shell = check_ops.shell(git)
    started = time.perf_counter_ns()
    completed = subprocess.run([resolved_shell, "-c", command], cwd=cwd, env=env, capture_output=True)
    duration_ms = (time.perf_counter_ns() - started) // 1000000
    return command, completed, duration_ms


class CostMeasurementLauncherTests(unittest.TestCase):
    def test_available_shell_records_a_real_red_run_then_green_using_current_interpreter(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = fx.make_repo(directory)
            repo.write({"probe path/test script.py": "from pathlib import Path\nassert Path('built').exists()\n"})
            git = fx.engine_git(repo)
            with fx.env_of(repo.env):
                command, red, milliseconds = measured_test_script(git, "probe path/test script.py", repo.path, repo.env)
                self.assertNotEqual(0, red.returncode)
                self.assertIn(b"AssertionError", red.stderr)
                self.assertIs(type(milliseconds), int)
                self.assertGreaterEqual(milliseconds, 0)
                self.assertEqual([sys.executable.replace("\\", "/"), "probe path/test script.py"], shlex.split(command))
                repo.write({"built": "ready\n"})
                same_command, green, _ = measured_test_script(git, "probe path/test script.py", repo.path, repo.env)
                self.assertEqual(command, same_command)
                self.assertEqual(0, green.returncode, green.stderr)

    def test_launcher_uses_resolved_windows_shell_and_quotes_interpreter_and_script_spaces(self):
        git = object()
        resolved_shell = "C:/Program Files/Git/bin/sh.exe"
        interpreter = r"C:\Program Files\Python310\python.exe"
        with mock.patch.object(check_ops, "shell", return_value=resolved_shell) as resolve, \
                mock.patch.object(sys, "executable", interpreter), \
                mock.patch.object(subprocess, "run", return_value=SimpleNamespace(returncode=1, stderr=b"red")) as run:
            command, observed, milliseconds = measured_test_script(git, "tests/test cost.py", "checkout", {})
        resolve.assert_called_once_with(git)
        self.assertEqual([resolved_shell, "-c", command], run.call_args.args[0])
        self.assertEqual([interpreter.replace("\\", "/"), "tests/test cost.py"], shlex.split(command))
        self.assertEqual(1, observed.returncode)
        self.assertIs(type(milliseconds), int)


class CostPolicyTemplateTests(unittest.TestCase):
    def policy(self, value=True):
        policy = fx.load_template("POLICY.json")
        policy["settings"]["engine"] = {"requires": ["test_cost"]}
        policy["settings"]["verification"]["parallel_commands"] = value
        return policy

    def test_optional_parallel_setting_is_boolean_and_capability_gated_even_when_false(self):
        for value in (True, False):
            with self.subTest(value=value):
                self.assertEqual([], schemas.validate_policy(self.policy(value)))
                policy = self.policy(value)
                policy["settings"]["engine"] = {"requires": []}
                self.assertTrue(any("test_cost" in e for e in schemas.validate_policy(policy)))
        for value in (0, 1, "true", None):
            with self.subTest(value=value):
                self.assertTrue(any("parallel_commands" in e for e in schemas.validate_policy(self.policy(value))))
        self.assertEqual([], schemas.validate_policy(fx.load_template("POLICY.json")))

    def test_parallel_mode_requires_broad_checks_policy_dependency(self):
        wf = fx.load_template("workflow.json")
        node = wf["graphs"]["default"]["nodes"]["run_tests"]
        node["policy"] = ["verification.commands", "verification"]
        self.assertEqual([], schemas.validate_workflow(wf, self.policy(), fx.prompt_exists, OPS))
        node["policy"] = ["verification.commands"]
        self.assertTrue(any("verification" in e and "policy" in e for e in
                            schemas.validate_workflow(wf, self.policy(), fx.prompt_exists, OPS)))

    def test_shipped_cost_and_checks_are_declared_context_and_parallel_is_not_enabled(self):
        wf = json.loads((fx.SHIPPED / "workflow.json").read_text())
        policy = json.loads((fx.SHIPPED / "POLICY.json").read_text())
        nodes = wf["graphs"]["default"]["nodes"]
        self.assertEqual("object", nodes["test_design"]["outputs"].get("cost"))
        for node, name, producer in (("review_tests", "cost", "test_design.cost"),
                                     ("review_impl", "cost", "test_design.cost"),
                                     ("approve_merge", "checks", "run_tests.result")):
            self.assertEqual({"from": producer, "context": True}, nodes[node]["inputs"].get(name))
        self.assertTrue({"verification.commands", "verification"}.issubset(nodes["run_tests"]["policy"]))
        self.assertIn("test_cost", policy["settings"]["engine"]["requires"])
        self.assertNotIn("parallel_commands", policy["settings"]["verification"])
        self.assertTrue((fx.PLUGIN_CODE / "engine/capabilities/test_cost.txt").is_file())

    def test_review_prompts_request_measurements_scope_and_disproportionate_cost(self):
        prompts = fx.SHIPPED / "prompts"
        writer = (prompts / "test_design.md").read_text().lower()
        self.assertIn("cost", writer)
        self.assertIn("checkpoint", writer)
        self.assertRegex(writer, r"measur|observ")
        self.assertIn("red", writer)
        self.assertRegex(writer, r"unavailable|cannot|missing")
        for name in ("review_tests.md", "lens_tests.md"):
            text = (prompts / name).read_text().lower()
            self.assertRegex(text, r"measur|observ")
            self.assertRegex(text, r"time|cost|duration")
            self.assertRegex(text, r"sleep|redundant|disproportionate|journey")
        approve = (prompts / "approve_merge.md").read_text().lower()
        self.assertIn("baseline", approve)
        self.assertIn("unavailable", approve)
        self.assertIn("verification", approve)

    def test_additive_observations_keep_existing_fingerprint_and_op_versions(self):
        from engine import FP_VERSION
        self.assertEqual("v1", FP_VERSION)
        self.assertEqual(1, OPS["checks.run"].version)

    def test_timing_context_does_not_change_approval_or_review_input_identity(self):
        wf = fx.load_template("workflow.json")
        nodes = wf["graphs"]["default"]["nodes"]
        nodes["test_design"]["outputs"]["cost"] = "object"
        nodes["review_tests"]["inputs"]["cost"] = {"from": "test_design.cost", "context": True}
        nodes["approve_merge"]["inputs"]["checks"] = {"from": "run_tests.result", "context": True}
        graph = schemas.build_graph("default", wf["graphs"]["default"])
        settings = fx.load_template("POLICY.json")["settings"]
        for node, key in (("review_tests", "cost"), ("approve_merge", "checks")):
            with self.subTest(node=node):
                values = {name: None for name in nodes[node]["inputs"]}
                values[key] = {"timing": {"total_ms": 1000, "baseline": {"status": "unavailable"}}}
                before = input_fp(fp_parts(graph, node, values, {}, settings, {}))
                values[key] = {"timing": {"total_ms": 9999, "baseline": {"status": "available", "delta_ms": -100}}}
                after = input_fp(fp_parts(graph, node, values, {}, settings, {}))
                self.assertEqual(before, after)

    def test_property_semantics_remain_at_the_audited_seed_step_assertion_baseline(self):
        golden = json.loads((fx.ROOT / ".agents/fixtures/g1043_property_ast.json").read_text())
        tree = ast.parse((fx.ROOT / ".agents/test_engine_property.py").read_text())
        observed = {}
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                observed[node.name] = hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()
            elif isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "LONG" for t in node.targets):
                observed["LONG"] = hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()
        self.assertEqual(golden, observed, "removing stale isolation must preserve property seeds/steps/assertions")


class ApprovalTimingContextTests(unittest.TestCase):
    def context(self, result):
        wf = fx.renamed_workflow(mapping={"run_tests": "prove", "approve_merge": "consent"})
        wf["graphs"]["default"]["nodes"]["consent"]["inputs"]["checks"] = {"from": "prove.result", "context": True}
        graph = schemas.build_graph("custom", wf["graphs"]["default"])
        blobs = {}
        class Reader(render.Reader):
            def blob_view(self, text):
                blob = hashlib.sha1(text.encode()).hexdigest()
                blobs[blob] = text
                return {"blob": blob, "read": f"git cat-file -p {blob}", "summary": "full result"}
        ctx = render.Ctx(prefix="zzzops", now=1800000000, settings=fx.load_template("POLICY.json")["settings"],
                         coordinator={}, reader=Reader())
        res = SimpleNamespace(graph=graph, cur={"prove": {"result": result}},
                              doc={"records": {}}, goal=1000)
        return render.approve_context(ctx, res, "consent", {"checks": result})[0], blobs

    def test_large_result_keeps_timing_delta_provenance_and_full_blob(self):
        baseline = {"status": "available", "goal": 1001, "node": "prove", "goal_commit": "a" * 40,
                    "merge_commit": "b" * 40, "tree": "c" * 40, "target": "hotfix/repair",
                    "finished_at": "2026-11-02T11:00:00Z", "total_ms": 2000, "verification_ms": 1600,
                    "delta_ms": -500, "verification_delta_ms": -500,
                    "verification": {"status": "available", "verification_ms": 1600, "delta_ms": -500,
                        "verification_plan_sha256": "e" * 64,
                        "source": {"goal": 1001, "node": "prove", "goal_commit": "a" * 40,
                                   "merge_commit": "b" * 40, "tree": "c" * 40, "target": "hotfix/repair",
                                   "finished_at": "2026-11-02T11:00:00Z"},
                        "caveat": "informational; machine load and concurrent goal-command workload may differ"}}
        result = {"passed": True, "tree": "c" * 40,
                  "details": [{"cmd": "targeted", "exit": 0, "seconds": 0, "milliseconds": 400, "source": "goal", "tail": ""},
                              {"cmd": "verbose", "exit": 0, "seconds": 1, "milliseconds": 1100,
                               "source": "verification", "tail": "long command output " * 500}],
                  "timing": {"total_ms": 1500, "goal_ms": 400, "verification_ms": 1100,
                             "baseline": baseline, "parallel_commands": True, "cpu_budget": 4,
                             "workers": {"goal": 2, "verification": 2}, "plan_sha256": "d" * 64,
                             "verification_plan_sha256": "e" * 64,
                             "environment": {"platform": "linux", "python": "3.10", "cpus": 20}}}
        entry, blobs = self.context(result)
        summary = entry["summary"].lower()
        self.assertIn("local", summary)
        self.assertIn("verification", summary)
        self.assertIn("1001", summary)
        self.assertIn("hotfix/repair", summary)
        self.assertTrue("-0.5" in summary or "-500" in summary)
        self.assertIn("blob", entry, "large evidence remains readable outside the compact summary")
        self.assertEqual(result, json.loads(blobs[entry["blob"]]))

    def test_repository_delta_is_visible_when_only_whole_run_comparison_is_unavailable(self):
        nested = {"status": "available", "verification_ms": 1600, "delta_ms": -500,
                  "verification_plan_sha256": "e" * 64,
                  "source": {"goal": 1001, "node": "prove", "goal_commit": "a" * 40,
                             "merge_commit": "b" * 40, "tree": "c" * 40, "target": "hotfix/repair",
                             "finished_at": "2026-11-02T11:00:00Z"},
                  "caveat": "informational; machine load and concurrent goal-command workload may differ"}
        result = {"passed": True, "tree": "c" * 40,
                  "details": [{"cmd": "goal-specific", "exit": 0, "seconds": 0, "milliseconds": 400,
                               "source": "goal", "tail": "verbose evidence " * 500},
                              {"cmd": "canonical-repository", "exit": 0, "seconds": 1, "milliseconds": 1100,
                               "source": "verification", "tail": ""}],
                  "timing": {"total_ms": 1500, "goal_ms": 400, "verification_ms": 1100,
                             "parallel_commands": True, "cpu_budget": 4, "workers": {"goal": 2, "verification": 2},
                             "plan_sha256": "d" * 64, "verification_plan_sha256": "e" * 64,
                             "environment": {"platform": "linux", "python": "3.10", "cpus": 20},
                             "baseline": {"status": "unavailable", "reason": "changed_commands_or_allocation",
                                          "verification": nested}}}
        entry, blobs = self.context(result)
        summary = entry["summary"].lower()
        self.assertIn("changed_commands_or_allocation", summary)
        self.assertIn("verification", summary)
        self.assertTrue("-0.5" in summary or "-500" in summary)
        self.assertIn("1001", summary)
        self.assertIn("hotfix/repair", summary)
        self.assertIn("informational", summary)
        self.assertIn("load", summary)
        self.assertIn("concurrent", summary)
        self.assertNotRegex(summary, r"total\s+delta\s+-")
        self.assertEqual(result, json.loads(blobs[entry["blob"]]))

    def test_unavailable_and_legacy_results_never_invent_a_total_or_baseline(self):
        for reason in ("no_prior_run", "changed_environment", "lookup_budget_exhausted"):
            with self.subTest(reason=reason):
                result = {"passed": True, "tree": "c" * 40, "details": [],
                          "timing": {"total_ms": 1500, "verification_ms": 1100,
                                     "baseline": {"status": "unavailable", "reason": reason,
                                                  "verification": {"status": "unavailable", "reason": reason}},
                                     "goal_ms": 400, "parallel_commands": True, "cpu_budget": 4,
                                     "workers": {"goal": 2, "verification": 2}, "plan_sha256": "d" * 64,
                                     "verification_plan_sha256": "e" * 64,
                                     "environment": {"platform": "linux", "python": "3.10", "cpus": 20}}}
                entry, _ = self.context(result)
                self.assertIn(reason, entry["summary"])
        legacy = {"passed": True, "tree": "c" * 40, "details": [{"cmd": "old command", "seconds": 2, "exit": 0, "tail": ""}]}
        entry, _ = self.context(legacy)
        self.assertIn("2", entry["summary"])
        self.assertRegex(entry["summary"].lower(), r"unavailable|legacy|recorded")
        self.assertNotIn("delta 0", entry["summary"].lower())


class CostPlumbingJourney(lifecycle.Journey):
    def setUp(self):
        # One journey, with configured node names changed throughout.
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.w = fx.World(self.tmp)
        wf = fx.stub_github_workflow(fx.stub_base_workflow())
        nodes = wf["graphs"]["default"]["nodes"]
        nodes["test_design"]["outputs"]["cost"] = "object"
        nodes["review_tests"]["inputs"]["cost"] = {"from": "test_design.cost", "context": True}
        nodes["approve_merge"]["inputs"]["checks"] = {"from": "run_tests.result", "context": True}
        nodes["run_tests"]["policy"] = ["verification.commands", "verification"]
        self.m = fx.RENAME
        self.w.bootstrap(workflow=fx.renamed_workflow(wf), settings={"verification.commands": ["true"]})
        self.A = fx.Agent(self.w, "a", "codex:aaaa/writer")
        self.B = fx.Agent(self.w, "b", "codex:bbbb/reviewer")

    def test_measured_cost_reaches_review_and_actual_checks_summary_reaches_full_approval(self):
        self.assertTrue((fx.PLUGIN_CODE / "engine/capabilities/test_cost.txt").is_file(), "test_cost not implemented yet")
        goal = self.goal()
        self.through_design(goal)
        card = self.A.start(goal, self.n("test_design"))
        wt = self.A.worktree(goal)
        checkpoint = wt.commit({"tests/test_cut.py": "from pathlib import Path\nnamespace = {}\nexec(Path('src/cut.py').read_text(), namespace)\nassert namespace['cut'] == 1\n"}, "test: measured fixture")
        with fx.env_of(self.w.env):
            command, completed, duration_ms = measured_test_script(
                fx.engine_git(self.w.clones["a"]), "tests/test_cut.py", wt.path, self.w.env)
        self.assertNotEqual(0, completed.returncode, "cost records an actual red run")
        cost = {"checkpoint": checkpoint, "commands": [{"cmd": command, "duration_ms": duration_ms, "exit": completed.returncode}],
                "total_ms": duration_ms, "changed_tests": [{"id_or_scope": "tests/test_cut.py", "duration_ms": duration_ms,
                    "observation": "measured test script: red before implementation"}], "summary": "Observed red test script; implementation does not exist yet"}
        self.A.submit(goal, self.n("test_design"), card, {"commands": [command], "cost": cost})
        reviewed = self.B.start(goal, self.n("review_tests"))
        observed = reviewed["inputs"]["cost"]
        if "blob" in observed:
            observed = json.loads(self.w.clones["b"].git("cat-file", "-p", observed["blob"]))
        self.assertEqual(cost, observed)
        self.B.submit(goal, self.n("review_tests"), reviewed,
                      {"decision": "approved", "summary": "Measured fixture cost reviewed"}, artifact="reviewed\n")
        card = self.A.start(goal, self.n("implement"))
        wt.commit({"src/cut.py": "cut = 1\n"}, "feat: fixture implementation")
        self.A.submit(goal, self.n("implement"), card, {"summary": "Fixture"})
        out = self.w.ok("a", "start", str(goal), self.n("run_tests"), "--as", "codex:aaaa/op")
        result = out["ran"]["output"]["result"]
        self.assertTrue(result["passed"])
        self.assertIn("timing", result)
        self.assertIs(type(result["timing"]["total_ms"]), int)
        self.review(self.B, goal, "review_impl")
        card = self.A.start(goal, self.n("integrate"))
        self.A.submit(goal, self.n("integrate"), card,
                      {"pr": {"number": 1, "head": checkpoint, "tree": result["tree"], "base": "dev"},
                       "ci": {"stacked": False, "required": [], "passed": [], "failed": []}})
        full = self.w.ok("a", "next", "--goal", str(goal))
        item = next(i for i in full["needs_human"] if i["node"] == self.n("approve_merge"))
        checks = next(c for c in item["context"] if c["label"] == f"{self.n('run_tests')}.result")
        summary = checks["summary"].lower()
        self.assertIn("local", summary)
        self.assertIn("verification", summary)
        self.assertIn("no_prior_run", summary)


if __name__ == "__main__":
    unittest.main()
