import re
import unittest
from pathlib import Path


ROOT = Path(__file__).parent.parent
UNBLOCK = ROOT / ".agents" / "skills" / "execute-zzzops" / "references" / "UNBLOCK.md"


def contract() -> tuple[int, int]:
    text = UNBLOCK.read_text(encoding="utf-8")
    match = re.search(r"`poll cadence: (\d+) seconds; maximum window: (\d+) seconds`", text)
    if not match:
        raise AssertionError("bounded human-unblock polling defaults are missing")
    return int(match.group(1)), int(match.group(2))


def simulate(states: list[str], *, wait_supported: bool = True) -> dict[str, int | str]:
    cadence, window = contract()
    limit = window // cadence
    result: dict[str, int | str] = {"notifications": 1, "reads": 0, "refreshes": 0, "resumes": 0}
    if not wait_supported:
        return result | {"outcome": "unsupported"}
    for state in states[:limit]:
        result["reads"] += 1
        if state == "merged":
            result["refreshes"] = result["resumes"] = 1
            return result | {"outcome": "unblocked"}
        if state in {"changes_requested", "provider_failure", "user_interrupt"}:
            return result | {"outcome": state}
    return result | {"outcome": "timeout"}


class HumanUnblockPollingContractTests(unittest.TestCase):
    def test_defaults_are_bounded_and_not_busy_waiting(self):
        cadence, window = contract()
        self.assertEqual((30, 180), (cadence, window))
        self.assertEqual(6, window // cadence)

    def test_check_green_pr_merged_during_window_resumes_once(self):
        result = simulate(["open", "merged"])
        self.assertEqual("unblocked", result["outcome"])
        self.assertEqual(1, result["notifications"])
        self.assertEqual(2, result["reads"])
        self.assertEqual(1, result["refreshes"])
        self.assertEqual(1, result["resumes"])

    def test_changes_requested_stops_without_resume(self):
        result = simulate(["changes_requested"])
        self.assertEqual("changes_requested", result["outcome"])
        self.assertEqual(0, result["resumes"])

    def test_unchanged_state_times_out_at_six_reads(self):
        result = simulate(["open"] * 20)
        self.assertEqual("timeout", result["outcome"])
        self.assertEqual(6, result["reads"])

    def test_unsupported_wait_hands_off_without_reading(self):
        result = simulate([], wait_supported=False)
        self.assertEqual("unsupported", result["outcome"])
        self.assertEqual(0, result["reads"])

    def test_provider_failure_stops_without_retry_loop(self):
        result = simulate(["provider_failure", "merged"])
        self.assertEqual("provider_failure", result["outcome"])
        self.assertEqual(1, result["reads"])
        self.assertEqual(0, result["resumes"])

    def test_user_interruption_stops_immediately(self):
        result = simulate(["user_interrupt", "merged"])
        self.assertEqual("user_interrupt", result["outcome"])
        self.assertEqual(1, result["reads"])
        self.assertEqual(0, result["resumes"])

    def test_installed_contract_names_required_stop_and_handoff_behavior(self):
        text = UNBLOCK.read_text(encoding="utf-8")
        for phrase in (
            "one notification",
            "highest-leverage",
            "safe read-only recheck",
            "changes requested",
            "provider failure",
            "user interruption",
            "refresh the portfolio once",
            "resume the existing execute loop once",
            "preserve the unchanged blocker",
        ):
            self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
