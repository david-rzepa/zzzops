"""G1032: the bootstrap skill and docs say what to do when rulesets and branch protection are unreadable (403)."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "plugins/zzzops/skills/bootstrap-zzzops-repository/SKILL.md"


def step(text, n):
    m = re.search(rf"(?ms)^{n}\. (.*?)(?=^\d+\. |\Z)", text)
    assert m, f"step {n} not found"
    return m.group(1)


class BootstrapRulesUnreadable(unittest.TestCase):
    def setUp(self):
        self.text = SKILL.read_text(encoding="utf-8")
        self.s2, self.s7 = step(self.text, 2), step(self.text, 7)

    def test_step2_has_the_403_fallback_for_required_ci(self):
        self.assertIn("403", self.s2)
        self.assertRegex(self.s2, r"(?i)do not retry|not retry|never retry")
        self.assertRegex(self.s2, r"(?i)owner")
        self.assertRegex(self.s2, r"(?i)check[- ]runs?|gh pr checks")
        self.assertIn("required_ci", self.s2)
        self.assertRegex(self.s2, r"(?i)before (step )?3|before validat")

    def test_fallback_proposes_names_and_never_leaves_required_ci_silently_empty(self):
        self.assertRegex(self.s2, r"(?i)exactly|match")                      # names must match the rollup name
        self.assertRegex(self.s2, r"(?i)never leave|not leave|silently")
        self.assertRegex(self.s2, r"(?i)no CI gate")
        self.assertRegex(self.s2, r"(?i)bootstrap (commit|PR)|commit or PR message|PR message")

    def test_step7_points_back_and_skips_rules_probes_after_403(self):
        self.assertIn("403", self.s7)
        self.assertRegex(self.s7, r"(?i)step 2")
        self.assertRegex(self.s7, r"(?i)skip")
        self.assertIn("delete_branch_on_merge", self.s7)
        self.assertIn("allow_squash_merge", self.s7)

    def test_owner_is_told_what_guards_merges(self):
        both = self.s2 + self.s7
        self.assertIn("--match-head-commit", both)
        self.assertRegex(both, r"(?i)public|upgrad")
        self.assertRegex(both, r"(?i)zzzops/goal/\*\*")

    def test_docs_point_to_the_fallback(self):
        bp = (ROOT / "docs/BRANCH_PROTECTION.md").read_text(encoding="utf-8")
        self.assertRegex(bp, r"(?i)403")
        self.assertRegex(bp, r"(?i)unreadable|unavailable")
        init = (ROOT / "docs/INITIALIZATION.md").read_text(encoding="utf-8")
        self.assertRegex(init, r"(?i)when rules are unreadable")
        self.assertIn("required_ci", init)


if __name__ == "__main__":
    unittest.main()
