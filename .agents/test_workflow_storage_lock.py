import importlib.util
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


MODULE_PATH = Path(__file__).parent.parent / "plugins" / "zzzops" / "zzzops" / "workflow.py"
SPEC = importlib.util.spec_from_file_location("workflow_storage_lock", MODULE_PATH)
workflow = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(workflow)


class StorageLockWriteTests(unittest.TestCase):
    def engine(self, *, acquired_expiry=500, renewal=None):
        calls = []
        adapter = SimpleNamespace(get_issue_comments=lambda number: [])
        artifact_index = SimpleNamespace(comments=[])
        renewal = renewal or {"acquired": True, "outcome": "renewed", "expires_at": 800}
        api = SimpleNamespace(
            GitHubReservationAdapter=lambda repo, repository: adapter,
            acquire_storage_lock=lambda *args: {
                "acquired": True, "outcome": "acquired", "expires_at": acquired_expiry,
            },
            renew_storage_lock=lambda *args: calls.append("renew") or renewal,
            release_storage_lock=lambda *args: calls.append("release") or {"released": True},
            apply_goal_transition=lambda *args, **kwargs: calls.append("write"),
            GOAL_TRANSITION_SCHEMA_VERSION=2,
        )
        engine = object.__new__(workflow.Workflow)
        engine.api = api
        engine.repo = Path("/repo")
        engine.repository = "owner/repo"
        engine.adapter = adapter
        engine.artifact_index = lambda _number: artifact_index
        return engine, calls

    def save(self, engine):
        desired = {"revision": 4}
        engine.save(
            {"body": "body"},
            {"key": 12, "revision": 4, "digest": "sha256:old"},
            desired,
        )
        return desired

    def test_expired_reservation_blocks_write_without_attempting_renewal(self):
        engine, calls = self.engine(acquired_expiry=100)
        with mock.patch.object(workflow.time, "time", return_value=101):
            with engine.locked():
                with self.assertRaisesRegex(ValueError, "expired before writing"):
                    self.save(engine)
        self.assertEqual(["release"], calls)

    def test_replaced_reservation_blocks_write(self):
        engine, calls = self.engine(renewal={"acquired": False, "outcome": "not_owned"})
        with mock.patch.object(workflow.time, "time", return_value=100):
            with engine.locked():
                with self.assertRaisesRegex(ValueError, "lost before writing"):
                    self.save(engine)
        self.assertEqual(["renew", "release"], calls)

    def test_save_renews_immediately_before_the_provider_write(self):
        engine, calls = self.engine()
        with mock.patch.object(workflow.time, "time", return_value=100):
            with engine.locked():
                desired = self.save(engine)
        self.assertEqual(5, desired["revision"])
        self.assertEqual(["renew", "write", "release"], calls)

    def test_lost_reservation_remains_invalid_for_followup_write(self):
        engine, calls = self.engine(renewal={"acquired": False, "outcome": "not_owned"})
        with mock.patch.object(workflow.time, "time", return_value=100):
            with engine.locked():
                with self.assertRaisesRegex(ValueError, "lost before writing"):
                    self.save(engine)
                with self.assertRaisesRegex(ValueError, "current workflow storage reservation"):
                    self.save(engine)
        self.assertEqual(["renew", "release"], calls)

    def test_long_read_keeps_exact_storage_owner_live_until_write(self):
        original_expiry = time.time() + .05
        engine, calls = self.engine(acquired_expiry=original_expiry)
        renewed = threading.Event()
        def renew(_adapter, _repository, _key, owner, run, ttl):
            self.assertEqual(("workflow", 300), (owner, ttl))
            self.assertTrue(run)
            calls.append("renew")
            renewed.set()
            return {"acquired": True, "outcome": "renewed", "expires_at": time.time() + 300}
        engine.api.renew_storage_lock = renew
        with mock.patch.object(workflow, "_STORAGE_RENEW_INTERVAL_SECONDS", .01):
            with engine.locked():
                self.assertTrue(renewed.wait(1), "keepalive did not renew during the read")
                time.sleep(.06)
                self.assertGreater(time.time(), original_expiry)
                self.assertGreater(engine._storage_reservation["expires_at"], time.time())
                self.save(engine)
        self.assertIn("write", calls)
        self.assertEqual("release", calls[-1])

    def test_failed_keepalive_cannot_authorize_delayed_write(self):
        engine, calls = self.engine(acquired_expiry=time.time() + 300)
        attempted = threading.Event()
        def lost(*_args):
            calls.append("renew")
            attempted.set()
            return {"acquired": False, "outcome": "not_owned"}
        engine.api.renew_storage_lock = lost
        with mock.patch.object(workflow, "_STORAGE_RENEW_INTERVAL_SECONDS", .01):
            with engine.locked():
                self.assertTrue(attempted.wait(1), "keepalive did not check ownership")
                with self.assertRaisesRegex(ValueError, "current workflow storage reservation"):
                    self.save(engine)
        self.assertNotIn("write", calls)
        self.assertEqual("release", calls[-1])


if __name__ == "__main__":
    unittest.main()
