"""G1038: conventional agent/engine commits and path-based frozen tests.

Submit tests use a reduced graph with the real base/test/checkpoint/submit code.
No new test repeats the complete product journey merely to reach submit.
"""
from __future__ import annotations

import copy
import json
import shutil
import tempfile
import unittest

import engine_fixtures as fx
import merge_sync_fixtures as msf
from engine import identity
from engine.ops import base, merge
from engine.ops.run import Done


def checkpoint_workflow():
    wf = fx.load_template("workflow.json")
    original = wf["graphs"]["default"]["nodes"]
    nodes = {n: copy.deepcopy(original[n]) for n in
             ("base", "test_design", "review_tests", "implement", "review_impl", "integrate")}
    nodes["base"]["inputs"] = {k: v for k, v in nodes["base"]["inputs"].items() if k in ("heads", "prs", "merges")}
    nodes["test_design"]["inputs"] = {"base": {"from": "base.base_commit"}}
    nodes["review_tests"]["inputs"] = {"tests": {"from": "test_design.tests.change"}}
    nodes["implement"]["inputs"] = {
        "base": {"from": "base.base_commit"}, "tests": {"from": "test_design.tests.change"},
        "tests_review": {"from": "review_tests.summary", "context": True}}
    nodes["review_impl"]["inputs"] = {"code": {"from": "implement.code.change"}}
    nodes["merge"] = {"kind": "agent", "stage": "delivery", "prompt": "design.md",
        "inputs": {"pr": {"from": "integrate.pr"}}, "outputs": {"merge_commit": "sha", "merged_at": "string"}}
    nodes["integrate"] = {"kind": "agent", "stage": "delivery", "prompt": "design.md",
        "inputs": {"review": {"from": "review_impl.summary"}}, "outputs": {"pr": "object", "ci": "object"}}
    return {"schema": 1, "graphs": {"default": {"terminal": ["merge"], "nodes": nodes}}}


class GrammarTests(unittest.TestCase):
    def test_release_types_scopes_and_bangs(self):
        parse = getattr(identity, "conventional", None)
        self.assertTrue(callable(parse), "identity.conventional is the shared grammar")
        self.assertEqual({"feat", "fix", "perf", "revert", "docs", "style", "chore", "refactor", "test", "build", "ci"},
                         set(getattr(identity, "CONVENTIONAL_TYPES", ())))
        for typ in identity.CONVENTIONAL_TYPES:
            for suffix in (": subject", "(engine): subject", "!: subject", "(engine)!: subject"):
                with self.subTest(subject=typ + suffix):
                    parsed = parse(typ + suffix)
                    self.assertIsNotNone(parsed)
                    self.assertEqual(typ, parsed[0])
        for bad in ("plain subject", "unknown: subject", "test:no space", "test: ", "test(): empty scope",
                    "fix(a(b)): nested scope", "Test: uppercase"):
            with self.subTest(subject=bad):
                self.assertIsNone(parse(bad))


class SubmitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.w = fx.World(self.tmp)
        self.w.bootstrap(workflow=checkpoint_workflow())
        self.A = fx.Agent(self.w, "a", "codex:aaaa/writer")
        self.B = fx.Agent(self.w, "b", "codex:bbbb/reviewer")
        self.g = self.w.new(title="Submit probe")["created"]["id"]
        self.w.ok("a", "start", str(self.g), "base", "--as", "codex:aaaa/op")
        self.wt = self.A.worktree(self.g)

    def record(self, node):
        return self.w.ok("a", "show", str(self.g), "--json")["goal"]["records"][node]

    def review_tests(self):
        card = self.B.start(self.g, "review_tests")
        prior = [{"id": f["id"], "status": "resolved"} for f in
                 (card.get("previous") or {}).get("findings", []) if f["status"] == "open"]
        self.B.submit(self.g, "review_tests", card,
                      {"decision": "approved", "summary": "Reviewed", "findings": prior}, artifact="Reviewed\n")
        return card

    def write_tests(self):
        card = self.A.start(self.g, "test_design")
        self.wt.commit({"tests/probe.txt": "test v1\n"}, "test(engine): probe")
        self.A.submit(self.g, "test_design", card, {"commands": ["true"]})
        self.review_tests()
        return self.record("test_design")["output"]["tests"]

    def implement(self):
        card = self.A.start(self.g, "implement")
        self.wt.commit({"src/probe.py": "probe = 1\n"}, "feat: probe")
        self.A.submit(self.g, "implement", card, {"summary": "Implemented"})
        return self.record("implement")["output"]["code"]

    def test_submit_refuses_freeform_and_then_non_test_type_for_preserved_node(self):
        card = self.A.start(self.g, "test_design")
        bad = self.wt.commit({"tests/probe.txt": "tests\n"}, "plain words")
        rc, out = self.A.submit(self.g, "test_design", card, {"commands": ["true"]}, ok=False)
        self.assertEqual(1, rc)
        self.assertEqual("commit_subject", out["error"]["code"])
        self.assertEqual(bad, out["error"]["details"]["commit"])
        self.assertIn("plain words", out["error"]["message"])
        self.wt.git("commit", "-q", "--amend", "-m", "fix: tests")
        rc, out = self.A.submit(self.g, "test_design", card, {"commands": ["true"]}, ok=False)
        self.assertEqual(1, rc)
        self.assertEqual("test_commit_type", out["error"]["code"])
        self.wt.git("commit", "-q", "--amend", "-m", "test(engine): corrected")
        self.A.submit(self.g, "test_design", card, {"commands": ["true"]})

    def test_implement_cannot_edit_then_revert_a_frozen_test(self):
        self.write_tests()
        card = self.A.start(self.g, "implement")
        bad = self.wt.commit({"tests/probe.txt": "weakened\n"}, "fix: temporary weakening")
        self.wt.commit({"tests/probe.txt": "test v1\n", "src/probe.py": "code\n"}, "fix: restore tests")
        rc, out = self.A.submit(self.g, "implement", card, {"summary": "Built"}, ok=False)
        self.assertEqual(1, rc)
        self.assertEqual("test_freeze", out["error"]["code"])
        self.assertIn(bad[:12], out["error"]["message"])
        self.assertIn("tests/probe.txt", out["error"]["message"])

    def test_no_commit_test_rerun_uses_head_but_keeps_scoped_change_and_implementation_current(self):
        old_tests = self.write_tests()
        self.implement()
        before = self.w.ok("a", "show", str(self.g), "--json")["states"]["implement"]
        self.w.ok("a", "reopen", str(self.g), "test_design", "--note", "reconsider tests")
        card = self.A.start(self.g, "test_design")
        self.assertNotIn("suggested_checkpoint", card)
        responses = {f["id"]: "disputed: tests already prove the behavior" for f in card["corrections"]}
        head = self.wt.git("rev-parse", "HEAD")
        self.A.submit(self.g, "test_design", card, {"commands": ["true"], "responses": responses})
        current = self.record("test_design")["output"]["tests"]
        self.assertEqual(head, current["commit"])
        self.assertEqual(old_tests["change"], current["change"])
        self.assertNotIn("scope", current)
        after = self.w.ok("a", "show", str(self.g), "--json")["states"]["implement"]
        self.assertEqual(before, after)

    def test_test_fix_after_code_stays_in_place_and_review_views_split_by_paths(self):
        self.write_tests()
        code = self.implement()
        self.w.ok("a", "reopen", str(self.g), "test_design", "--note", "test correction")
        card = self.A.start(self.g, "test_design")
        fix = self.wt.commit({"tests/probe.txt": "test v2\n"}, "test: correct expectation")
        responses = {f["id"]: "fixed: expectation corrected" for f in card["corrections"]}
        self.A.submit(self.g, "test_design", card, {"commands": ["true"], "responses": responses})
        tests = self.record("test_design")["output"]["tests"]
        self.assertEqual(fix, tests["commit"])
        self.assertTrue(self.wt.git("merge-base", "--is-ancestor", code["commit"], fix) == "")
        tests_card = self.review_tests()
        test_view = tests_card["inputs"]["tests"]["diff"]
        self.assertIn("tests/probe.txt", test_view)
        self.assertIn("--", test_view)
        impl_card = self.A.start(self.g, "implement")
        self.A.submit(self.g, "implement", impl_card, {"summary": "Built against corrected tests"})
        review = self.B.start(self.g, "review_impl")
        code_view = review["inputs"]["code"]["diff"]
        self.assertIn(":(exclude,top,literal)tests/probe.txt", code_view)
        # Execute each printed view: evidence must match what a reviewer sees.
        import subprocess
        for view, included, excluded in ((test_view, "tests/probe.txt", "src/probe.py"),
                                         (code_view, "src/probe.py", "tests/probe.txt")):
            result = subprocess.run(view, shell=True, cwd=self.wt.path, env=self.w.env,
                                    capture_output=True, text=True, check=True)
            self.assertIn(included, result.stdout)
            self.assertNotIn(excluded, result.stdout)

    def test_agent_merge_is_refused_even_if_it_uses_the_engine_subject(self):
        card = self.A.start(self.g, "test_design")
        old = self.wt.git("rev-parse", "HEAD")
        first = self.wt.commit({"tests/probe.txt": "test\n"}, "test: probe")
        self.wt.git("checkout", "-q", "-b", "agent-side", old)
        side = self.wt.commit({"side.txt": "side\n"}, "test: side")
        self.wt.git("checkout", "-q", f"zzzops/work/g{self.g}")
        self.wt.git("merge", "-q", "--no-ff", side, "-m", f"chore(sync): merge dev into G{self.g}")
        rc, out = self.A.submit(self.g, "test_design", card, {"commands": ["true"]}, ok=False)
        self.assertEqual(1, rc)
        self.assertEqual("validation", out["error"]["code"])
        self.assertIn("only base makes merge commits", out["error"]["message"])


class FakeMergeTests(msf.OpFixture):
    def test_fake_honors_messages_and_replays_each_commit_for_rebase(self):
        tests = self.publish({"tests/probe.txt": "test\n"}, "test: probe\n\nTest body")
        head = self.publish({"src/probe.py": "code\n"}, "feat!: probe\n\nBREAKING CHANGE: migrate users")
        trunk = self.trunk({"upstream.txt": "advanced base\n"})
        gh = self.ctx().gh
        url = gh.run("pr", "create", "--head", "zzzops/work/g1000", "--base", "dev",
                     "--title", "Default PR title", "--body-file", "-", input="PR body")
        number = url.strip().rsplit("/", 1)[-1]
        initial = self.fake.load()
        for method in ("squash", "merge", "rebase"):
            with self.subTest(method=method):
                self.fake.save(copy.deepcopy(initial))
                self.w.remote_git("update-ref", "refs/heads/dev", trunk)
                self.w.remote_git("update-ref", "refs/heads/zzzops/work/g1000", head)
                args = ["pr", "merge", number, f"--{method}", "--match-head-commit", head]
                if method != "rebase":
                    args += ["--subject", "fix!: explicit subject", "--body", "Explicit body\n\nBREAKING CHANGE: preserved"]
                gh.run(*args)
                self.repo.git("fetch", "-q", "origin", "dev")
                tip = self.repo.git("rev-parse", "FETCH_HEAD")
                parents = self.git.out("rev-list", "--parents", "-n", "1", tip).split()[1:]
                if method == "rebase":
                    commits = self.git.out("rev-list", "--reverse", f"{trunk}..{tip}").split()
                    self.assertEqual(2, len(commits))
                    self.assertEqual(["test: probe", "feat!: probe"], [self.ident.subject(c) for c in commits])
                    self.assertEqual(trunk, self.git.out("rev-parse", f"{commits[0]}^"))
                    self.assertEqual([commits[0]], parents)
                    for original, replay in zip((tests, head), commits):
                        self.assertEqual(self.git.out("show", "-s", "--format=%B", original),
                                         self.git.out("show", "-s", "--format=%B", replay))
                        self.assertEqual(2, len(self.git.out("rev-list", "--parents", "-n", "1", replay).split()))
                else:
                    self.assertEqual([trunk] if method == "squash" else [trunk, head], parents)
                    self.assertEqual("fix!: explicit subject\n\nExplicit body\n\nBREAKING CHANGE: preserved",
                                     self.git.out("show", "-s", "--format=%B", tip))
                self.assertEqual("advanced base", self.git.out("show", f"{tip}:upstream.txt"))
                self.assertEqual("test", self.git.out("show", f"{tip}:tests/probe.txt"))
                self.assertEqual("code", self.git.out("show", f"{tip}:src/probe.py"))


class EngineSubjectsTests(msf.OpFixture):
    def test_combine_is_conventional_without_needing_merge_mode(self):
        left = self.publish({"left.txt": "left\n"}, "feat: left")
        right = self.trunk({"right.txt": "right\n"})
        onto = base.combine(self.git, 1000, [left, right], [{"goal": 999, "head": left}], True, "dev")
        self.assertTrue(self.ident.subject(onto).startswith("chore(stack): "), self.ident.subject(onto))

    def test_review_artifact_subject_is_unchanged(self):
        tip, _ = self.ident.artifact_commit(self.base, self.base, 1000, "design", b"design\n")
        self.assertEqual("docs(review): design for G1000", self.ident.subject(tip))

    def test_merge_passes_conventional_subject_and_breaking_body_for_each_method(self):
        test = self.publish({"tests/probe.txt": "test\n"}, "test: probe")
        self.checkpoint_record(test)
        self.publish({"src/probe.py": "code\n"}, "feat!: new contract\n\nBREAKING CHANGE: migrate users")
        integrated = self.integrate()
        self.assertIsInstance(integrated, Done)
        self.assertTrue(integrated.ok)
        pr = integrated.output["pr"]
        head = pr["head"]
        initial_state = self.fake.load()
        # Each subcase starts with the same open PR and integration ref; all calls
        # stay inside the fake GitHub and the fixture's bare repository.
        for method in ("squash", "merge", "rebase"):
            with self.subTest(method=method):
                self.fake.save(copy.deepcopy(initial_state))
                self.w.remote_git("update-ref", "refs/heads/dev", self.base)
                self.w.remote_git("update-ref", "refs/heads/zzzops/pr/g1000", head)
                self.settings["merge"]["method"] = method
                context = self.ctx("merge", {"pr": pr})
                outcome = merge.run(context)
                self.assertIsInstance(outcome, Done, getattr(outcome, "blocked", outcome))
                self.assertTrue(outcome.ok)
                call = [c for c in self.fake.calls() if c[:2] == ["pr", "merge"]][-1]
                self.assertIn("--match-head-commit", call)
                self.assertEqual(head, call[call.index("--match-head-commit") + 1])
                if method == "rebase":
                    self.assertNotIn("--subject", call)
                    self.assertNotIn("--body", call)
                else:
                    self.assertIn("--subject", call)
                    subject = call[call.index("--subject") + 1]
                    if method == "squash":
                        self.assertEqual(f"{self.ident.subject(head)} (#{pr['number']})", subject)
                        self.assertIn("BREAKING CHANGE: migrate users", call[call.index("--body") + 1])
                    else:
                        self.assertTrue(subject.startswith("chore(merge): G1000 "), subject)
                # Verify actual trunk result, not merely the command arguments.
                self.repo.git("fetch", "-q", "origin", "dev")
                trunk = self.repo.git("rev-parse", "FETCH_HEAD")
                subjects = self.git.out("log", "--format=%s", f"{self.base}..{trunk}").splitlines()
                conventional = getattr(identity, "conventional", None)
                self.assertTrue(callable(conventional))
                self.assertTrue(subjects)
                self.assertTrue(all(conventional(s) is not None for s in subjects), subjects)


if __name__ == "__main__":
    unittest.main()
