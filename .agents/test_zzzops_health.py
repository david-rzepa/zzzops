import importlib.util
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).with_name("zzzops_health.py")
SPEC = importlib.util.spec_from_file_location("zzzops_health", MODULE_PATH)
health = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(health)


class HealthPolicyTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 7, 15, 16, 0, tzinfo=timezone.utc)  # Wednesday

    def prefs(self):
        prefs = health.default_preferences()
        prefs["enabled"] = True
        prefs["timezone"] = "UTC"
        prefs["schedule"]["work_days"] = list(range(7))
        prefs["reminders"]["late_night"]["enabled"] = False
        prefs["reminders"]["weekend"]["enabled"] = False
        return prefs

    def active_state(self, minutes):
        return {
            "session_started_at": health._iso(self.now - timedelta(minutes=minutes)),
            "last_activity_at": health._iso(self.now - timedelta(minutes=1)),
            "activity_precision": "exact_message",
        }

    def activity(self, precision="exact_message"):
        return {"timestamp": health._iso(self.now), "precision": precision}

    def test_disabled_is_a_safe_noop(self):
        decision, state = health.evaluate(self.now, self.activity(), health.default_preferences(), None)
        self.assertEqual("disabled", decision["reason_code"])
        self.assertFalse(decision["nudge"])
        self.assertEqual(health.default_state(), state)

    def test_break_is_observable_after_continuous_session(self):
        decision, state = health.evaluate(self.now, self.activity(), self.prefs(), self.active_state(100))
        self.assertTrue(decision["nudge"])
        self.assertEqual("break", decision["reason_code"])
        self.assertEqual("exact_message", decision["evidence"]["precision"])
        self.assertFalse(decision["blocking"])
        self.assertIn("break", state["last_nudge_at"])

    def test_observed_receipt_requires_explicit_opt_in(self):
        prefs = self.prefs()
        decision, state = health.evaluate(self.now, self.activity("observed_receipt"), prefs, self.active_state(100))
        self.assertEqual("break", decision["reason_code"])
        self.assertEqual("exact_message", state["activity_precision"])
        prefs["signals"]["allow_observed_receipt"] = True
        decision, state = health.evaluate(self.now, self.activity("observed_receipt"), prefs, self.active_state(100))
        self.assertEqual("observed_receipt", state["activity_precision"])
        self.assertEqual("observed_receipt", decision["evidence"]["precision"])

    def test_current_only_can_nudge_schedule_but_not_infer_session(self):
        prefs = self.prefs()
        prefs["reminders"]["late_night"]["enabled"] = True
        prefs["schedule"]["bedtime"] = "15:00"
        prefs["schedule"]["wake"] = "07:00"
        decision, _state = health.evaluate(self.now, None, prefs, None)
        self.assertEqual("late_night", decision["reason_code"])
        self.assertEqual("current_only", decision["evidence"]["precision"])
        prefs["reminders"]["late_night"]["enabled"] = False
        decision, _state = health.evaluate(self.now, None, prefs, None)
        self.assertEqual("not_due", decision["reason_code"])

    def test_precedence_is_late_night_weekend_long_break_hydration(self):
        prefs = self.prefs()
        prefs["schedule"]["work_days"] = [0, 1, 2, 3, 4]
        prefs["reminders"]["late_night"]["enabled"] = True
        prefs["reminders"]["weekend"]["enabled"] = True
        prefs["schedule"]["bedtime"] = "15:00"
        prefs["schedule"]["wake"] = "07:00"
        saturday = datetime(2026, 7, 18, 16, 0, tzinfo=timezone.utc)
        state = self.active_state(240)
        state["session_started_at"] = health._iso(saturday - timedelta(minutes=240))
        state["last_activity_at"] = health._iso(saturday - timedelta(minutes=1))
        decision, _ = health.evaluate(saturday, {"timestamp": health._iso(saturday), "precision": "exact_message"}, prefs, state)
        self.assertEqual("late_night", decision["reason_code"])

    def test_work_wind_down_and_quiet_windows_are_observable(self):
        prefs = self.prefs()
        after_work = datetime(2026, 7, 15, 19, 0, tzinfo=timezone.utc)
        decision, _ = health.evaluate(after_work, None, prefs, None)
        self.assertEqual("outside_work_hours", decision["reason_code"])
        wind_down = datetime(2026, 7, 15, 23, 0, tzinfo=timezone.utc)
        decision, _ = health.evaluate(wind_down, None, prefs, None)
        self.assertEqual("wind_down", decision["reason_code"])
        prefs["reminders"]["wind_down"]["enabled"] = False
        prefs["reminders"]["outside_work_hours"]["enabled"] = False
        quiet = datetime(2026, 7, 15, 23, 50, tzinfo=timezone.utc)
        decision, _ = health.evaluate(quiet, None, prefs, self.active_state(200))
        self.assertEqual("not_due", decision["reason_code"])

    def test_overnight_work_window_is_supported(self):
        prefs = self.prefs()
        prefs["schedule"]["work_start"] = "22:00"
        prefs["schedule"]["work_end"] = "06:00"
        prefs["reminders"]["wind_down"]["enabled"] = False
        instant = datetime(2026, 7, 15, 2, 0, tzinfo=timezone.utc)
        decision, _ = health.evaluate(instant, None, prefs, None)
        self.assertEqual("not_due", decision["reason_code"])

    def test_global_cooldown_and_snooze_prevent_repeat(self):
        prefs = self.prefs()
        state = self.active_state(100)
        state["last_nudge_at"] = {"any": health._iso(self.now - timedelta(minutes=10))}
        decision, _ = health.evaluate(self.now, self.activity(), prefs, state)
        self.assertEqual("cooldown", decision["reason_code"])
        state["last_nudge_at"] = {}
        state["snoozed_until"] = health._iso(self.now + timedelta(minutes=10))
        decision, _ = health.evaluate(self.now, self.activity(), prefs, state)
        self.assertEqual("snoozed", decision["reason_code"])

    def test_retention_prunes_activity_and_nudge_timestamps(self):
        prefs = self.prefs()
        prefs["privacy"]["retention_hours"] = 1
        state = self.active_state(180)
        state["last_activity_at"] = health._iso(self.now - timedelta(hours=2))
        state["last_nudge_at"] = {"any": health._iso(self.now - timedelta(hours=2))}
        decision, state = health.evaluate(self.now, None, prefs, state)
        self.assertEqual("not_due", decision["reason_code"])
        self.assertIsNone(state["last_activity_at"])
        self.assertEqual({}, state["last_nudge_at"])

    def test_timezone_failure_is_explicit_without_fallback(self):
        prefs = self.prefs()
        prefs["timezone"] = "Missing/Zone"
        with mock.patch.object(health, "ZoneInfo", side_effect=health.ZoneInfoNotFoundError):
            decision, _ = health.evaluate(self.now, None, prefs, None)
        self.assertEqual("timezone_unavailable", decision["reason_code"])

    def test_dst_fold_uses_injected_instant_unambiguously(self):
        prefs = self.prefs()
        prefs["timezone"] = "America/New_York"
        prefs["reminders"]["late_night"]["enabled"] = True
        prefs["schedule"]["bedtime"] = "01:30"
        prefs["schedule"]["wake"] = "07:00"
        instant = datetime(2026, 11, 1, 6, 45, tzinfo=timezone.utc)  # second 01:45
        decision, _ = health.evaluate(instant, None, prefs, None)
        if decision["reason_code"] == "timezone_unavailable":
            self.skipTest("IANA timezone data unavailable")
        self.assertEqual("late_night", decision["reason_code"])
        self.assertIn("-05:00", decision["evidence"]["local_time"])

    def test_invalid_values_and_blocking_are_rejected(self):
        prefs = self.prefs()
        prefs["delivery"]["blocking"] = True
        prefs["schedule"]["work_days"] = [0, 0, 9]
        prefs["reminders"]["break"]["after_minutes"] = 0
        errors = health.validate_preferences(prefs)
        self.assertIn("delivery.blocking is unsupported; health nudges are nonblocking", errors)
        self.assertTrue(any("work_days" in error for error in errors))
        self.assertTrue(any("break.after_minutes" in error for error in errors))

    def test_state_never_contains_messages_or_event_history(self):
        decision, state = health.evaluate(self.now, self.activity(), self.prefs(), self.active_state(100))
        self.assertTrue(decision["nudge"])
        def keys(value):
            if isinstance(value, dict):
                return set(value) | set().union(*(keys(item) for item in value.values()))
            if isinstance(value, list):
                return set().union(*(keys(item) for item in value)) if value else set()
            return set()
        self.assertFalse({"message", "messages", "prompt", "history"} & keys(state))
        self.assertEqual(1, state["nudge_count"]["break"])


if __name__ == "__main__":
    unittest.main()
