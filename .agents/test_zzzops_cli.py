import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).with_name("zzzops.py")
SPEC = importlib.util.spec_from_file_location("zzzops_cli", MODULE_PATH)
zzzops = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(zzzops)


class HealthCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.config = root / "user"
        self.machine = root / "machine"
        self.env = {
            "ZZZOPS_USER_CONFIG_DIR": str(self.config),
            "ZZZOPS_MACHINE_STATE_DIR": str(self.machine),
        }
        self.patch = mock.patch.dict(os.environ, self.env, clear=False)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def test_paths_are_separate_user_and_machine_locations(self):
        self.assertEqual(self.config / "health_preferences.json", zzzops.user_health_preferences_path())
        self.assertEqual(self.machine / "health_state.json", zzzops.machine_health_state_path())

    def test_windows_defaults_use_roaming_preferences_and_local_state(self):
        env = {"APPDATA": "C:/roaming", "LOCALAPPDATA": "C:/local"}
        with mock.patch.object(zzzops.sys, "platform", "win32"):
            self.assertEqual(Path("C:/roaming/ZzzOps/health_preferences.json"), zzzops.user_health_preferences_path(env))
            self.assertEqual(Path("C:/local/ZzzOps/health_state.json"), zzzops.machine_health_state_path(env))

    def test_missing_preferences_are_opt_in_disabled_and_do_not_write(self):
        status = zzzops.health_status()
        self.assertFalse(status["enabled"])
        self.assertFalse(status["preferences_exists"])
        self.assertFalse(status["state_exists"])
        result = zzzops.health_check("2026-07-16T12:00:00Z", None, "current_only")
        self.assertEqual("disabled", result["decision"]["reason_code"])
        self.assertFalse((self.machine / "health_state.json").exists())

    def test_preferences_preserve_unknown_keys(self):
        path = self.config / "health_preferences.json"
        data = zzzops.health.default_preferences()
        data["enabled"] = True
        data["future_extension"] = {"keep": True}
        zzzops.private_atomic_json(path, data)
        loaded_path, loaded = zzzops.load_user_health_preferences()
        self.assertEqual(path, loaded_path)
        self.assertTrue(loaded["future_extension"]["keep"])

    def test_check_persists_only_minimal_machine_state(self):
        prefs = zzzops.health.default_preferences()
        prefs["enabled"] = True
        prefs["schedule"]["work_days"] = list(range(7))
        prefs["reminders"]["late_night"]["enabled"] = False
        prefs["reminders"]["weekend"]["enabled"] = False
        zzzops.private_atomic_json(self.config / "health_preferences.json", prefs)
        now = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)
        state = zzzops.health.default_state()
        state["session_started_at"] = zzzops.health._iso(now - timedelta(minutes=100))
        state["last_activity_at"] = zzzops.health._iso(now - timedelta(minutes=1))
        state["activity_precision"] = "exact_message"
        zzzops.private_atomic_json(self.machine / "health_state.json", state)
        result = zzzops.health_check(zzzops.health._iso(now), zzzops.health._iso(now), "exact_message")
        self.assertEqual("break", result["decision"]["reason_code"])
        stored = json.loads((self.machine / "health_state.json").read_text(encoding="utf-8"))
        self.assertEqual("exact_message", stored["activity_precision"])
        self.assertNotIn("message", stored)
        self.assertNotIn("history", stored)

    def test_storage_denial_is_explicit_and_has_no_fallback(self):
        prefs = zzzops.health.default_preferences()
        prefs["enabled"] = True
        prefs["reminders"]["late_night"]["enabled"] = True
        prefs["schedule"]["bedtime"] = "00:00"
        prefs["schedule"]["wake"] = "23:59"
        zzzops.private_atomic_json(self.config / "health_preferences.json", prefs)
        with mock.patch.object(zzzops, "private_atomic_json", side_effect=PermissionError("sandbox")):
            result = zzzops.health_check(
                "2026-07-16T12:00:00Z", "2026-07-16T12:00:00Z", "exact_message"
            )
        self.assertFalse(result["ok"])
        self.assertEqual("storage_unavailable", result["reason_code"])
        self.assertTrue(result["fallback"].startswith("none"))

    def test_reset_can_remove_state_and_preferences(self):
        zzzops.private_atomic_json(self.config / "health_preferences.json", zzzops.health.default_preferences())
        zzzops.private_atomic_json(self.machine / "health_state.json", zzzops.health.default_state())
        result = zzzops.health_reset(include_preferences=True)
        self.assertTrue(result["ok"])
        self.assertEqual(2, len(result["removed"]))
        self.assertFalse((self.config / "health_preferences.json").exists())
        self.assertFalse((self.machine / "health_state.json").exists())

    def test_interactive_cancel_does_not_create_preferences(self):
        with mock.patch("builtins.input", side_effect=["q"]):
            zzzops.edit_health_preferences()
        self.assertFalse((self.config / "health_preferences.json").exists())

    def test_status_subcommand_emits_json(self):
        env = os.environ.copy()
        result = subprocess.run(
            [sys.executable, str(MODULE_PATH), "--repo", str(MODULE_PATH.parents[1]), "health", "status"],
            env=env, text=True, encoding="utf-8", capture_output=True, check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr + result.stdout)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["enabled"])
        self.assertEqual(str(self.machine / "health_state.json"), payload["state_path"])


if __name__ == "__main__":
    unittest.main()
