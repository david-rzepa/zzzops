"""G1040: stable command options are not volatile tempfile suffixes."""
from __future__ import annotations

import unittest

import engine_fixtures  # makes the checked-out engine importable
from engine import records
import test_engine_blocked_findings as blocked


class NormalizationBoundaryTests(unittest.TestCase):
    def test_distinct_stable_options_remain_distinct_at_end_or_before_quotes(self):
        for ending in ("", "'", '"', ".log", "/output"):
            with self.subTest(ending=ending):
                strategy = "verification command failed: python check.py --strategy" + ending
                protocol = "verification command failed: python check.py --protocol" + ending
                self.assertNotEqual(records.norm(strategy), records.norm(protocol))

    def test_temp_paths_keep_equivalent_failures_equivalent(self):
        for before, after in (
            ("/tmp/tmpk3j_9x2a/check.py:12", "/tmp/tmpzz8_q1w0/check.py:99"),
            ("zzzops-card-budget-ab12cd_e/check.py:12", "zzzops-card-budget-q9w8e7r6/check.py:99"),
            (".zzzops-cleanup-ab12cd_e.tmp", ".zzzops-cleanup-q9w8e7r6.tmp"),
        ):
            with self.subTest(before=before):
                self.assertEqual(records.norm(before), records.norm(after))

    def test_different_option_failure_reopens_then_actual_repeat_escalates(self):
        s = blocked.sim()

        def fail(option):
            blocked.to(s, "run_tests")
            record = s.op(1, "run_tests", ok=False, raised=[{
                "key": "failed", "input": "code",
                "text": "verification command failed: python check.py " + option}])
            return record["findings"][0]

        first = fail("--strategy")
        s.step(1, "implement", responses={first["id"]: "fixed: corrected strategy option"})
        different = fail("--protocol")
        self.assertEqual(1, different["rounds"])
        self.assertIsNone(different["response"])
        self.assertEqual(("ready", "reopened"),
                         (s.st(1, "implement")["name"], s.st(1, "implement").get("reason")))
        answer = "fixed: corrected protocol option"
        s.step(1, "implement", responses={different["id"]: answer})
        repeated = fail("--protocol")
        self.assertEqual(2, repeated["rounds"])
        self.assertEqual(answer, repeated["response"])
        self.assertEqual("dispute", s.st(1, "implement").get("kind"))


if __name__ == "__main__":
    unittest.main()
