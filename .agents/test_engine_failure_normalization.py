"""G1040: recognize temporary contexts without erasing stable command names."""
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

    def test_stable_script_and_test_names_remain_distinct(self):
        for template in ("node scripts/check-{}.js", "python tests/test_{}.py",
                         "python scripts/tmp{}.py", "node scripts/check-{}/run.js"):
            with self.subTest(template=template):
                self.assertNotEqual(records.norm(template.format("strategy")),
                                    records.norm(template.format("protocol")))

    def test_explicit_temporary_contexts_normalize_only_the_random_component(self):
        for template in ("/tmp/tmp{}/check.py", "C:\\Temp\\tmp{}\\check.py",
                         "/var/folders/stable/T/tmp{}/check.py", ".legacy-{}.json",
                         "zzzops-claude-acceptance-{}/result.json"):
            with self.subTest(template=template):
                self.assertEqual(records.norm(template.format("k3j_9x2a")),
                                 records.norm(template.format("zz8_q1w0")))
        self.assertNotEqual(records.norm("/tmp/tmpk3j_9x2a/check-strategy.js"),
                            records.norm("/tmp/tmpzz8_q1w0/check-protocol.js"))

    def assert_distinct_then_repeat(self, first_command, second_command):
        s = blocked.sim()

        def fail(command):
            blocked.to(s, "run_tests")
            record = s.op(1, "run_tests", ok=False, raised=[{
                "key": "failed", "input": "code",
                "text": "verification command failed: " + command}])
            return record["findings"][0]

        first = fail(first_command)
        s.step(1, "implement", responses={first["id"]: "fixed: corrected first command"})
        different = fail(second_command)
        self.assertEqual(1, different["rounds"])
        self.assertIsNone(different["response"])
        self.assertEqual(("ready", "reopened"),
                         (s.st(1, "implement")["name"], s.st(1, "implement").get("reason")))
        answer = "fixed: corrected second command"
        s.step(1, "implement", responses={different["id"]: answer})
        repeated = fail(second_command)
        self.assertEqual(2, repeated["rounds"])
        self.assertEqual(answer, repeated["response"])
        self.assertEqual("dispute", s.st(1, "implement").get("kind"))

    def test_different_option_failure_reopens_then_actual_repeat_escalates(self):
        self.assert_distinct_then_repeat("python check.py --strategy", "python check.py --protocol")

    def test_different_script_failure_reopens_then_actual_repeat_escalates(self):
        self.assert_distinct_then_repeat("node scripts/check-strategy.js", "node scripts/check-protocol.js")


if __name__ == "__main__":
    unittest.main()
