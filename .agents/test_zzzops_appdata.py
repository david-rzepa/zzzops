"""Live atomic write probe inside the current platform's real app-data roots."""

import importlib.util
import os
import shutil
import unittest
import uuid
from contextlib import contextmanager
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).with_name("zzzops.py")
SPEC = importlib.util.spec_from_file_location("zzzops_appdata", MODULE_PATH)
zzzops = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(zzzops)


def appdata_roots() -> tuple[Path, Path]:
    if zzzops.sys.platform == "win32":
        return Path(os.environ["APPDATA"]), Path(os.environ["LOCALAPPDATA"])
    if zzzops.sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support"
        return root, root
    return (
        Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")),
        Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")),
    )


@contextmanager
def appdata_test_directory(root: Path, prefix: str):
    path = root / f"{prefix}{uuid.uuid4().hex}"
    path.mkdir(mode=0o700)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


class LiveAppDataTests(unittest.TestCase):
    def test_atomic_round_trip_in_real_appdata_roots(self):
        config_root, state_root = appdata_roots()
        config_root.mkdir(parents=True, exist_ok=True)
        state_root.mkdir(parents=True, exist_ok=True)
        with appdata_test_directory(config_root, "zzzops-pref-test-") as config_dir, appdata_test_directory(state_root, "zzzops-state-test-") as state_dir:
            env = {
                "ZZZOPS_USER_CONFIG_DIR": str(config_dir),
                "ZZZOPS_MACHINE_STATE_DIR": str(state_dir),
            }
            with mock.patch.dict(os.environ, env, clear=False):
                preferences = zzzops.health.default_preferences()
                preferences["enabled"] = True
                state = zzzops.health.default_state()
                zzzops.private_atomic_json(zzzops.user_health_preferences_path(), preferences)
                zzzops.private_atomic_json(zzzops.machine_health_state_path(), state)
                pref_path, loaded_preferences = zzzops.load_user_health_preferences()
                state_path, loaded_state = zzzops.load_machine_health_state()
                self.assertTrue(loaded_preferences["enabled"])
                self.assertEqual(zzzops.health.SCHEMA_VERSION, loaded_state["schema_version"])
                self.assertTrue(pref_path.is_file())
                self.assertTrue(state_path.is_file())
                reset = zzzops.health_reset(include_preferences=True)
                self.assertTrue(reset["ok"])
                self.assertFalse(pref_path.exists())
                self.assertFalse(state_path.exists())


if __name__ == "__main__":
    unittest.main()
