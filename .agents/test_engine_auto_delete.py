"""G1031: best-effort branch-deletion warning, without a full goal journey.

The shared CLI world checks real policy loading and fake `gh` wiring. Unit probes cover the helper's failure
matrix and subprocess timeout without sleeps. Documentation is checked directly during implementation.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import types
import unittest
from unittest import mock

import engine_fixtures as fx
import test_engine_branching as branching
from engine import gh


class HeadBranchSettingTests(unittest.TestCase):
    def helper(self):
        helper = getattr(gh, "head_branch_auto_delete", None)
        self.assertTrue(callable(helper), "G1031 requires the best-effort repository-setting probe")
        return helper

    def session(self):
        return types.SimpleNamespace(R="origin", git=types.SimpleNamespace(
            primary="/unused", config=lambda key: "https://github.com/test/repo.git"))

    def test_helper_parses_only_boolean_settings_and_uses_short_timeout(self):
        helper = self.helper()
        for text, expected in [("true\n", True), ("false\n", False), ("null\n", None), ("", None),
                               ("garbage\n", None), ('"true"\n', None), ("1\n", None), ("[]\n", None)]:
            with self.subTest(text=text), mock.patch.object(gh.Gh, "run", return_value=text) as run:
                self.assertIs(expected, helper(self.session()))
                run.assert_called_once()
                args, kwargs = run.call_args
                self.assertEqual(("api", "repos/test/repo", "--jq", ".delete_branch_on_merge"), args)
                self.assertEqual(10, kwargs.get("timeout"), "best-effort probe must not use the 60 s default")

    def test_helper_is_silent_on_error_timeout_and_unknown_repository(self):
        helper = self.helper()
        for error in [gh.GhError(["api"], 1, "Forbidden", False),
                      gh.GhError(["api"], -1, "timed out", True)]:
            with self.subTest(error=str(error)), mock.patch.object(gh.Gh, "run", side_effect=error):
                self.assertIsNone(helper(self.session()))
        with mock.patch.object(gh, "gh_repo", return_value=None), mock.patch.object(gh.Gh, "run") as run:
            self.assertIsNone(helper(self.session()))
            run.assert_not_called()

    def test_gh_run_timeout_override_reaches_subprocess_and_keeps_default(self):
        s = self.session()
        def timeout(*args, **kwargs):
            raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])
        # No sleep and no wall-clock assertion: inspect the bound handed to the child.
        with mock.patch.object(gh.subprocess, "run", side_effect=timeout) as run:
            with self.assertRaises(gh.GhError):
                gh.Gh(s).run("api", "repos/test/repo", timeout=10)
            self.assertEqual(10, run.call_args.kwargs["timeout"])
            with self.assertRaises(gh.GhError):
                gh.Gh(s).run("api", "repos/test/repo")
            self.assertEqual(gh.TIMEOUT, run.call_args.kwargs["timeout"])


class ValidateHeadBranchSettingTests(unittest.TestCase):
    def test_real_validate_policy_and_fake_gh_warning_matrix(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        w = fx.World(tmp)
        fake = fx.FakeGitHub(w)
        w.bootstrap(policy=branching.branching_policy(), workflow=branching.release_workflow())
        w.push_dev(branching.release_prompts(), "chore(zzzops): release prompts")

        for value, expected, error in [(True, True, False), (False, False, False),
                                        (None, False, False), (True, False, True)]:
            with self.subTest(value=value, error=error):
                state = fake.load()
                state["repository"] = {} if value is None else {"delete_branch_on_merge": value}
                state["faults"] = {"repo_settings_error": error}
                fake.save(state)
                before = len(fake.calls())
                rc, out = w.run("a", "validate")
                self.assertEqual(0, rc, out)
                self.assertTrue(out["ok"], out)
                warnings = [x for x in out["warnings"] if x["kind"] == "auto_delete_head_branches"]
                self.assertEqual(1 if expected else 0, len(warnings), out)
                calls = [a for a in fake.calls()[before:] if a[:2] == ["api", "repos/test/repo"]]
                self.assertEqual(1, len(calls), "one repository probe per branching validate")
                if warnings:
                    text = warnings[0]["message"]
                    for required in ["settings.branching", "finish", "release/", "hotfix/", "stacked", "off"]:
                        self.assertIn(required, text)

        # Removing branching switches the probe off even when the repository setting remains on.
        w.bootstrap()
        state = fake.load()
        state.update(repository={"delete_branch_on_merge": True}, faults={})
        fake.save(state)
        before = len(fake.calls())
        out = w.ok("a", "validate")
        self.assertFalse(any(x["kind"] == "auto_delete_head_branches" for x in out["warnings"]))
        self.assertFalse(any(a[:2] == ["api", "repos/test/repo"] for a in fake.calls()[before:]))

        # An unusable gh is already an environment error; do not add an unauthenticated probe.
        w.bootstrap(policy=branching.branching_policy(), workflow=branching.release_workflow())
        w.push_dev(branching.release_prompts(), "chore(zzzops): release prompts")
        before = len(fake.calls())
        w.ok("a", "next")
        self.assertFalse(any(a[:2] == ["api", "repos/test/repo"] for a in fake.calls()[before:]))
        state = fake.load()
        state["faults"] = {"auth": True}
        fake.save(state)
        before = len(fake.calls())
        rc, out = w.run("a", "validate")
        self.assertEqual(1, rc, out)
        self.assertFalse(out["ok"])
        self.assertTrue(out["environment"])
        self.assertFalse(any(x["kind"] == "auto_delete_head_branches" for x in out["warnings"]))
        self.assertFalse(any(a[:2] == ["api", "repos/test/repo"] for a in fake.calls()[before:]))


if __name__ == "__main__":
    unittest.main()
