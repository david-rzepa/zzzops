"""Behavioral contract for durable, reusable ZzzOps working-input files.

These tests intentionally load the production module by file path.  A missing
module is a product-level red result; malformed fixtures fail separately before
any lifecycle assertion runs.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "plugins/zzzops/zzzops/working_inputs.py"


def production_module():
    if not MODULE.is_file():
        raise AssertionError(f"missing approved production behavior: {MODULE.relative_to(ROOT)}")
    spec = importlib.util.spec_from_file_location("zzzops_working_inputs_under_test", MODULE)
    if spec is None or spec.loader is None:
        raise AssertionError("working-input production module has no importable loader")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    required = {"WorkingInputStore", "WorkingInputBusy", "WorkingInputUncertain"}
    missing = sorted(required - set(vars(module)))
    if missing:
        raise AssertionError("working-input production API is incomplete: " + ", ".join(missing))
    return module


class AppliedThenLost(RuntimeError):
    """The fake provider applied exact bytes but lost its response."""


class FixtureProvider:
    def __init__(self):
        self.calls = []
        self.applied = {}
        self.checks = 0
        self.check_results = []

    def send(self, request_id, body):
        if not isinstance(body, bytes):
            raise AssertionError("dispatch fixture received mutable/non-byte payload")
        self.calls.append((request_id, body))
        self.applied[request_id] = body
        return {"receipt": request_id}

    def apply_then_lose(self, request_id, body):
        self.send(request_id, body)
        raise AppliedThenLost(request_id)

    def check(self, request_id, digest):
        self.checks += 1
        if self.check_results:
            return self.check_results.pop(0)
        body = self.applied.get(request_id)
        return body is not None and hashlib.sha256(body).hexdigest() == digest


class WorkingInputBehaviorTests(unittest.TestCase):
    def setUp(self):
        self.module = production_module()
        self.temporary = tempfile.TemporaryDirectory()
        self.repo = Path(self.temporary.name) / "repo"
        self.repo.mkdir()
        (self.repo / ".git").mkdir()
        self.provider = FixtureProvider()

    def tearDown(self):
        self.temporary.cleanup()

    def store(self, owner="root", **overrides):
        return self.module.WorkingInputStore(
            self.repo, repository="owner/project", owner=owner,
            provider_check=self.provider.check, **overrides)

    def assert_descriptor(self, value):
        self.assertEqual({"payload_id", "path", "subject", "purpose", "owner"}, set(value))
        path = Path(value["path"])
        self.assertTrue(path.is_absolute())
        self.assertTrue(path.is_relative_to(self.repo / ".zzzops/work/inputs/v1"))
        self.assertEqual("input.json", path.name)
        return path

    def test_stable_revision_restart_and_draft_to_goal_relabel(self):
        store = self.store()
        first = store.write("draft:abc", "goal-create", {"revision": 1})
        path = self.assert_descriptor(first)
        inode = path.stat().st_ino
        initial_files = sorted(p.relative_to(self.repo) for p in path.parent.rglob("*"))

        second = store.write("draft:abc", "goal-create", {"revision": 2, "answer": "settled"})
        self.assertEqual(first, second)
        self.assertEqual(inode, path.stat().st_ino, "editable revisions must retain the stable file itself")
        self.assertEqual({"revision": 2, "answer": "settled"}, json.loads(path.read_text()))
        self.assertEqual(initial_files, sorted(p.relative_to(self.repo) for p in path.parent.rglob("*")),
                         "revisions must not create one input file per edit")

        restarted = self.store().open("draft:abc", "goal-create")
        self.assertEqual(first, restarted)
        relabeled = self.store().relabel("draft:abc", "goal:554", "goal-create")
        self.assertEqual(first["payload_id"], relabeled["payload_id"])
        self.assertEqual(path, Path(relabeled["path"]))
        self.assertEqual(inode, path.stat().st_ino)
        self.assertEqual({"revision": 2, "answer": "settled"}, self.store().read("goal:554", "goal-create"))
        with self.assertRaises(KeyError):
            self.store().open("draft:abc", "goal-create", create=False)

    def test_identity_separates_owner_purpose_and_draft_without_implicit_adoption(self):
        root = self.store("root")
        identities = [
            root.write("draft:a", "capture", {"value": 1}),
            root.write("draft:b", "capture", {"value": 2}),
            root.write("draft:a", "policy-review", {"value": 3}),
            self.store("worker").write("draft:a", "capture", {"value": 4}),
        ]
        self.assertEqual(4, len({item["payload_id"] for item in identities}))
        self.assertEqual(4, len({item["path"] for item in identities}))
        with self.assertRaises(KeyError):
            self.store("new-owner").open("goal:554", "capture", create=False)
        legacy = self.repo / "request.json"
        legacy.write_text('{"legacy":true}\n')
        created = root.open("goal:554", "execute")
        self.assertNotEqual(legacy.resolve(), Path(created["path"]))
        self.assertEqual('{"legacy":true}\n', legacy.read_text(), "legacy input must remain untouched")

    def test_freeze_dispatch_exact_retry_and_recovered_state_boundaries(self):
        store = self.store()
        store.write("goal:554", "execute", {"operation": "submit", "value": "one"})
        frozen = store.freeze("goal:554", "execute", "request-1", "goal-submit")
        snapshot = Path(frozen["snapshot"])
        exact = snapshot.read_bytes()
        self.assertEqual("frozen", store.status("request-1")["state"])
        self.assertEqual(hashlib.sha256(exact).hexdigest(), frozen["digest"])

        store.write("goal:554", "execute", {"operation": "submit", "value": "edited later"})
        result = store.dispatch("request-1", self.provider.send)
        self.assertEqual({"receipt": "request-1"}, result)
        self.assertEqual(exact, self.provider.calls[-1][1], "dispatch must never reread the editable file")
        self.assertEqual("confirmed", store.status("request-1")["state"])
        self.assertEqual(result, store.dispatch("request-1", self.provider.send))
        self.assertEqual(1, len(self.provider.calls), "confirmed same-request replay must not call provider again")

        before = self.store(fault=lambda point: (_ for _ in ()).throw(RuntimeError(point))
                            if point == "before_snapshot" else None)
        before.write("goal:554", "before", {"x": 1})
        with self.assertRaisesRegex(RuntimeError, "before_snapshot"):
            before.freeze("goal:554", "before", "request-before", "goal-submit")
        with self.assertRaises(KeyError):
            before.status("request-before")

        after = self.store(fault=lambda point: (_ for _ in ()).throw(RuntimeError(point))
                           if point == "after_snapshot_fsync" else None)
        after.write("goal:554", "after", {"x": 2})
        with self.assertRaisesRegex(RuntimeError, "after_snapshot_fsync"):
            after.freeze("goal:554", "after", "request-frozen", "goal-submit")
        recovered = self.store().status("request-frozen")
        self.assertEqual("frozen", recovered["state"])
        self.assertEqual(0, len(self.provider.calls), "frozen recovery must prove dispatch was never authorized")

    def test_dispatching_crashes_are_uncertain_and_reconcile_is_bounded(self):
        def crash(point):
            if point == "after_dispatching_fsync":
                raise RuntimeError(point)

        store = self.store(fault=crash)
        store.write("goal:554", "execute", {"operation": "submit", "value": "durable"})
        store.freeze("goal:554", "execute", "request-crash", "goal-submit")
        with self.assertRaisesRegex(RuntimeError, "after_dispatching_fsync"):
            store.dispatch("request-crash", self.provider.send)
        self.assertEqual("dispatching", self.store().status("request-crash")["state"])
        self.assertEqual([], self.provider.calls)
        for operation in (
            lambda: self.store().dispatch("request-crash", self.provider.send),
            lambda: self.store().handoff("goal:554", "execute", "worker"),
            lambda: self.store().retire("request-crash", {"receipt": "invented"}),
            lambda: self.store().abandon("request-crash", approved_by="user"),
        ):
            with self.assertRaises(self.module.WorkingInputUncertain):
                operation()

        uncertain = self.store()
        uncertain.write("goal:554", "uncertain", {"operation": "submit", "value": "applied"})
        uncertain.freeze("goal:554", "uncertain", "request-lost", "goal-submit")
        with self.assertRaises(AppliedThenLost):
            uncertain.dispatch("request-lost", self.provider.apply_then_lose)
        self.assertEqual("uncertain", uncertain.status("request-lost")["state"])
        self.assertEqual("reconciled", uncertain.reconcile("request-lost")["state"])
        self.assertEqual(1, self.provider.checks)

        bounded = self.store()
        bounded.write("goal:554", "bounded", {"value": "unknown"})
        bounded.freeze("goal:554", "bounded", "request-bounded", "goal-submit")
        with self.assertRaises(AppliedThenLost):
            bounded.dispatch("request-bounded", self.provider.apply_then_lose)
        self.provider.applied.pop("request-bounded")
        self.provider.check_results = [None, None, None, True]
        with self.assertRaises(self.module.WorkingInputUncertain) as caught:
            bounded.reconcile("request-bounded")
        self.assertEqual(4, self.provider.checks, "one prior check plus exactly three bounded checks")
        self.assertIn("request-bounded", str(caught.exception))
        self.assertIn("reconcile", str(caught.exception).lower())
        self.assertTrue(Path(bounded.status("request-bounded")["snapshot"]).is_file())

    def test_active_references_block_handoff_retirement_and_abandonment(self):
        store = self.store()
        descriptor = store.write("goal:554", "execute", {"value": "protected"})
        store.freeze("goal:554", "execute", "request-ref", "goal-submit")
        with store.reference("request-ref", "lease"):
            with self.assertRaises(self.module.WorkingInputBusy):
                store.handoff("goal:554", "execute", "worker")
        with store.reader("request-ref") as body:
            self.assertIsInstance(body, bytes)
            for operation in (
                lambda: store.handoff("goal:554", "execute", "worker"),
                lambda: store.retire("request-ref", {"receipt": "request-ref"}),
                lambda: store.abandon("request-ref", approved_by="user"),
            ):
                with self.assertRaises(self.module.WorkingInputBusy):
                    operation()
            self.assertTrue(Path(store.status("request-ref")["snapshot"]).exists())
        store.dispatch("request-ref", self.provider.send)
        with self.assertRaises((PermissionError, ValueError)):
            store.retire("request-ref", {"receipt": "wrong-result"})
        store.retire("request-ref", {"receipt": "request-ref"})
        self.assertFalse(Path(store.status("request-ref")["snapshot"]).exists())
        self.assertTrue(Path(descriptor["path"]).exists(), "retirement removes snapshot, not editable history")

        store.write("goal:554", "abandon", {"value": "discardable local input"})
        store.freeze("goal:554", "abandon", "request-abandon", "goal-submit")
        with self.assertRaises(PermissionError):
            store.abandon("request-abandon", approved_by=None)
        store.abandon("request-abandon", approved_by="user")
        self.assertFalse(Path(store.status("request-abandon")["snapshot"]).exists())

    def test_unresolved_snapshots_have_no_age_or_count_eviction(self):
        store = self.store()
        snapshots = []
        for index in range(25):
            purpose = f"pending-{index}"
            request = f"request-pending-{index}"
            store.write("goal:554", purpose, {"index": index})
            snapshots.append(Path(store.freeze("goal:554", purpose, request, "goal-submit")["snapshot"]))
        self.assertTrue(all(path.is_file() for path in snapshots))
        self.assertEqual(25, len(set(snapshots)))
        # Reopening the store simulates an arbitrarily later invocation; age
        # and count alone cannot authorize eviction of unresolved exact bytes.
        restarted = self.store()
        for index, path in enumerate(snapshots):
            self.assertEqual("frozen", restarted.status(f"request-pending-{index}")["state"])
            self.assertTrue(path.is_file())

    def test_repository_machine_lock_serializes_writers_and_handoff(self):
        first, second = self.store("root"), self.store("root")
        first.write("goal:554", "race", {"revision": 0})
        barrier = threading.Barrier(3)
        failures = []

        def writer(store, revision):
            try:
                barrier.wait()
                for _ in range(20):
                    store.write("goal:554", "race", {"revision": revision, "body": "x" * 1024})
            except BaseException as exc:  # captured and asserted on the coordinator thread
                failures.append(exc)

        threads = [threading.Thread(target=writer, args=(first, 1)),
                   threading.Thread(target=writer, args=(second, 2))]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join(10)
        self.assertFalse(any(thread.is_alive() for thread in threads), "lock race deadlocked")
        self.assertEqual([], failures)
        self.assertIn(first.read("goal:554", "race")["revision"], {1, 2})
        json.loads(Path(first.open("goal:554", "race")["path"]).read_text())

        handed = first.handoff("goal:554", "race", "worker")
        self.assertEqual("worker", handed["owner"])
        self.assertEqual(handed, self.store("worker").open("goal:554", "race", create=False))
        with self.assertRaises(KeyError):
            first.open("goal:554", "race", create=False)

    def test_guidance_is_readable_json_and_legacy_migration_is_non_destructive(self):
        store = self.store()
        legacy = self.repo / "manual-transition.json"
        legacy.write_text('{"operation":"submit"}\n')
        purposes = ("capture", "execute", "migration", "policy-review")
        for purpose in purposes:
            guidance = store.guidance("goal:554", purpose, legacy_paths=[legacy])
            self.assertEqual({"path", "payload_id", "commands", "legacy"}, set(guidance))
            self.assertTrue(Path(guidance["path"]).is_relative_to(self.repo / ".zzzops/work/inputs/v1"))
            self.assertTrue(guidance["commands"])
            for command in guidance["commands"]:
                self.assertIsInstance(command, list)
                self.assertNotIn("<", " ".join(command), "helper commands must be directly runnable")
            self.assertIn(str(legacy.resolve()), json.dumps(guidance["legacy"]))
            self.assertIn("untouched", json.dumps(guidance["legacy"]).lower())
        self.assertEqual('{"operation":"submit"}\n', legacy.read_text())

        descriptor = store.write("goal:554", "execute", {"z": 1, "a": [2, 3]})
        command = store.guidance("goal:554", "execute")["commands"][0]
        rendered = subprocess.run(command, cwd=self.repo, text=True, capture_output=True, check=True)
        self.assertEqual(json.loads(Path(descriptor["path"]).read_text()), json.loads(rendered.stdout))


if __name__ == "__main__":
    unittest.main()
