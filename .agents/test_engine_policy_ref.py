"""`--policy-ref`: a read-only preview of `next`, `show` and `validate` under a policy that has not landed."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest

import engine_fixtures as fx


class PolicyRefTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.w = fx.World(self.tmp)
        self.w.bootstrap()
        self.g = self.w.new(title="x")["created"]["id"]

    def policy_branch(self, files, topic="rename", push=True):
        s = self.w.seed
        s.git("pull", "-q", "--ff-only", "origin", "dev")
        s.git("checkout", "-q", "-b", f"zzzops/policy/{topic}")
        c = s.commit(files, "chore(zzzops): policy change")
        if push:
            s.git("push", "-q", "origin", f"HEAD:refs/heads/zzzops/policy/{topic}")
        s.git("checkout", "-q", "dev")
        return c

    def renamed(self):
        return {".zzzops/workflow.json": json.dumps(fx.renamed_workflow(), indent=2) + "\n"}

    def test_next_previews_a_policy_branch_without_its_own_pause(self):
        tip = self.policy_branch(self.renamed())
        self.assertEqual("policy_branch", self.w.ok("b", "next")["blockers"][0]["kind"])
        for ref in ("zzzops/policy/rename", "rename"):
            out = self.w.ok("b", "next", "--policy-ref", ref)
            self.assertEqual([], out["blockers"])
            self.assertEqual([(self.g, fx.RENAME["design"])], [(a["goal"], a["node"]) for a in out["actions"]])
            self.assertEqual({"ref": "zzzops/policy/rename", "commit": tip}, out["coordinator"]["policy_preview"])
            self.assertIn("policy_preview", [w["kind"] for w in out["warnings"]])

    def test_another_open_policy_branch_still_pauses_the_preview(self):
        self.policy_branch(self.renamed())
        self.policy_branch({".zzzops/prompts/design.md": "other\n"}, topic="other")
        out = self.w.ok("b", "next", "--policy-ref", "rename")
        self.assertEqual(["policy_branch"], [b["kind"] for b in out["blockers"]])
        self.assertIn("zzzops/policy/other", out["blockers"][0]["message"])

    def test_an_unpushed_local_commit_previews_only_where_it_exists(self):
        tip = self.policy_branch(self.renamed(), push=False)
        out = self.w.ok("a", "next", "--policy-ref", tip, cwd=self.w.seed.path)
        self.assertEqual([fx.RENAME["design"]], [a["node"] for a in out["actions"]])
        self.assertEqual(tip, out["coordinator"]["policy_preview"]["commit"])
        rc, err = self.w.run("b", "next", "--policy-ref", tip)
        self.assertEqual((1, "not_found"), (rc, err["error"]["code"]))

    def test_show_reads_states_under_the_preview(self):
        self.policy_branch(self.renamed())
        out = self.w.ok("b", "show", str(self.g), "--json", "--policy-ref", "rename")
        self.assertIn(fx.RENAME["design"], out["states"])
        self.assertNotIn("design", out["states"])

    def test_validate_reports_an_invalid_preview_and_leaves_dev_alone(self):
        self.policy_branch({".zzzops/POLICY.json": "{\"schema\": 2}\n"}, topic="bad")
        rc, out = self.w.run("b", "validate", "--policy-ref", "bad")
        self.assertEqual(1, rc)
        self.assertTrue(out["policy"])
        self.assertTrue(self.w.ok("b", "validate")["ok"])

    def test_validate_reports_impact_on_current_goals(self):
        self.policy_branch(self.renamed())
        out = self.w.ok("b", "validate", "--policy-ref", "rename")
        self.assertIn("impact", out)
        self.assertIn(f"G{self.g}", out["impact"]["nodes"])

    def test_writes_refuse_the_flag(self):
        self.policy_branch(self.renamed())
        for argv in (["start", str(self.g), "design"], ["new", "--file", self.w.file({"title": "t", "spec": "s"})],
                     ["reopen", str(self.g), "design", "--note", "n"]):
            rc, err = self.w.run("b", *argv, "--policy-ref", "rename")
            self.assertEqual((1, "usage"), (rc, err["error"]["code"]), argv)
            self.assertIn("read-only preview", err["error"]["message"])

    def test_unknown_ref_and_flag_conflict(self):
        rc, err = self.w.run("b", "next", "--policy-ref", "nope")
        self.assertEqual((1, "not_found"), (rc, err["error"]["code"]))
        rc, err = self.w.run("b", "validate", "--policy", "--policy-ref", "x")
        self.assertEqual((1, "usage"), (rc, err["error"]["code"]))


if __name__ == "__main__":
    unittest.main()
