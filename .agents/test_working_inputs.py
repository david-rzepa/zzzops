"""Behavioral contract for durable, reusable ZzzOps working-input files.

These tests intentionally load the production module by file path.  A missing
module is a product-level red result; malformed fixtures fail separately before
any lifecycle assertion runs.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
from contextlib import redirect_stdout


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
        self.dispatch_started = threading.Event()
        self.dispatch_release = threading.Event()

    def send(self, request_id, body):
        if not isinstance(body, bytes):
            raise AssertionError("dispatch fixture received mutable/non-byte payload")
        self.calls.append((request_id, body))
        self.applied[request_id] = body
        return {"receipt": request_id}

    def apply_then_lose(self, request_id, body):
        self.send(request_id, body)
        raise AppliedThenLost(request_id)

    def blocking_send(self, request_id, body):
        self.dispatch_started.set()
        if not self.dispatch_release.wait(5):
            raise AssertionError("provider dispatch fixture was not released")
        return self.send(request_id, body)

    def repair_response(self, request_id, body):
        self.calls.append((request_id, body))
        return {"next_steps": [{"kind": "repair", "reason": "provider state needs reconciliation"}]}

    def missing_receipt(self, request_id, body):
        self.calls.append((request_id, body))
        return {"next_steps": [{"kind": "checkpoint"}]}

    def fail_before_apply(self, request_id, body):
        self.calls.append((request_id, body))
        raise ConnectionError("provider failed before application")

    def check(self, request_id, digest):
        self.checks += 1
        if self.check_results:
            return self.check_results.pop(0)
        body = self.applied.get(request_id)
        return body is not None and hashlib.sha256(body).hexdigest() == digest


class WorkingInputFixtureControlTests(unittest.TestCase):
    def test_fixtures_initialize_without_production_module(self):
        provider = FixtureProvider()
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "repo"
            repo.mkdir()
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            self.assertTrue((repo / ".git").is_dir())
            self.assertEqual([], provider.calls)
            self.assertFalse(provider.dispatch_started.is_set())


class WorkingInputBehaviorTests(unittest.TestCase):
    def setUp(self):
        self.module = None
        self.temporary = tempfile.TemporaryDirectory()
        self.repo = Path(self.temporary.name) / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        self.provider = FixtureProvider()

    def tearDown(self):
        self.temporary.cleanup()

    def store(self, owner="root", **overrides):
        if self.module is None:
            self.require_behavior("working-input store")
        return self.module.WorkingInputStore(
            self.repo, repository="owner/project", owner=owner,
            provider_check=self.provider.check, **overrides)

    def require_behavior(self, criterion):
        self.assertTrue(MODULE.is_file(),
                        f"missing production behavior for {criterion}: {MODULE.relative_to(ROOT)}")
        if self.module is None:
            self.module = production_module()
        return self.module

    def assert_descriptor(self, value):
        self.assertEqual({"payload_id", "path", "subject", "purpose", "owner"}, set(value))
        path = Path(value["path"])
        self.assertTrue(path.is_absolute())
        self.assertTrue(path.is_relative_to(self.repo / ".zzzops/work/inputs/v1"))
        self.assertEqual("input.json", path.name)
        return path

    def assert_runnable_recovery(self, error, request_id, reason):
        recovery = error.exception.recovery
        action = "status" if reason in {"active-lease", "active-reference"} else "reconcile"
        expected = [
            sys.executable, str(ROOT / "plugins/zzzops/zzzops/zzzops.py"),
            "working-input", action, "--repo", str(self.repo),
            "--request-id", request_id,
        ]
        self.assertEqual({"request_id": request_id, "reason": reason, "command": expected}, recovery)
        sys.path.insert(0, str(ROOT / ".agents"))
        try:
            import test_zzzops as fixtures
            public_cli = fixtures.zzzops
        finally:
            sys.path.pop(0)
        output = io.StringIO()
        with (mock.patch.object(sys, "argv", expected[1:]),
              mock.patch.object(public_cli._working_inputs, "execute_command",
                                return_value={"state": "suppressed"}) as execute,
              redirect_stdout(output)):
            self.assertEqual(0, public_cli.main())
        execute.assert_called_once()
        call = execute.call_args
        self.assertEqual(action, call.args[0])
        self.assertEqual(self.repo, call.kwargs["repo"])
        self.assertEqual(request_id, call.kwargs["request_id"])

    def test_stable_revision_restart_and_draft_to_goal_relabel(self):
        self.require_behavior('stable revision, restart, relabel, file-count and patch-size reuse')
        store = self.store()
        stable_body = "UNIQUE-WORKING-INPUT-BODY-554:" + "x" * 1024
        first = store.write("draft:abc", "goal-create", {"revision": 1, "body": stable_body})
        path = self.assert_descriptor(first)
        inode = path.stat().st_ino
        store_root = self.repo / ".zzzops/work/inputs/v1"
        initial_files = sorted(p.relative_to(self.repo) for p in store_root.rglob("*") if p.is_file())
        baseline = Path(self.temporary.name) / "external-revision-one.json"
        baseline.write_bytes(path.read_bytes())
        initial_bytes = sum(p.stat().st_size for p in store_root.rglob("*") if p.is_file())

        second = store.write("draft:abc", "goal-create",
                             {"revision": 2, "body": stable_body, "answer": "settled"})
        self.assertEqual(first, second)
        self.assertEqual(inode, path.stat().st_ino, "editable revisions must retain the stable file itself")
        self.assertEqual({"revision": 2, "body": stable_body, "answer": "settled"},
                         json.loads(path.read_text()))
        current_files = sorted(p.relative_to(self.repo) for p in store_root.rglob("*") if p.is_file())
        self.assertEqual(initial_files, current_files,
                         "revisions must not create one input file per edit")
        current_bytes = sum(p.stat().st_size for p in store_root.rglob("*") if p.is_file())
        observed_growth = max(0, current_bytes - initial_bytes)
        duplicate_full_bytes = baseline.stat().st_size + path.stat().st_size
        self.assertEqual({"revision": 1, "body": stable_body}, json.loads(baseline.read_text()),
                         "external baseline artifact must remain immutable")
        self.assertLess(observed_growth, duplicate_full_bytes,
                        "observed store growth must be smaller than retaining duplicate full inputs")
        stored_bytes = b"\n".join(
            candidate.read_bytes() for candidate in store_root.rglob("*") if candidate.is_file())
        self.assertEqual(1, stored_bytes.count(stable_body.encode()),
                         "registry metadata must not duplicate the reusable payload body")

        restarted = self.store().open("draft:abc", "goal-create")
        self.assertEqual(first, restarted)
        relabeled = self.store().relabel("draft:abc", "goal:554", "goal-create")
        self.assertEqual(first["payload_id"], relabeled["payload_id"])
        self.assertEqual(path, Path(relabeled["path"]))
        self.assertEqual(inode, path.stat().st_ino)
        self.assertEqual({"revision": 2, "body": stable_body, "answer": "settled"},
                         self.store().read("goal:554", "goal-create"))
        with self.assertRaises(KeyError):
            self.store().open("draft:abc", "goal-create", create=False)

    def test_identity_separates_owner_purpose_and_draft_without_implicit_adoption(self):
        self.require_behavior('owner, purpose, draft identity and refused implicit adoption')
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
        self.require_behavior('durable freeze, exact dispatch, retry, recovery and digest verification')
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
        self.assertFalse(any(request == "request-frozen" for request, _body in self.provider.calls),
                         "frozen recovery must prove dispatch was never authorized")
        reopened = self.store(fault=lambda point: (_ for _ in ()).throw(RuntimeError(point))
                              if point == "after_dispatching_fsync" else None)
        with self.assertRaisesRegex(RuntimeError, "after_dispatching_fsync"):
            reopened.dispatch("request-frozen", self.provider.send)
        self.assertEqual("dispatching", self.store().status("request-frozen")["state"])
        self.assertFalse(any(request == "request-frozen" for request, _body in self.provider.calls),
                         "recovered frozen state must durably cross dispatching before provider I/O")

        clean = self.store()
        clean.write("goal:554", "corrupt", {"x": 3})
        corrupt = clean.freeze("goal:554", "corrupt", "request-corrupt", "goal-submit")
        Path(corrupt["snapshot"]).write_bytes(b'{"tampered":true}')
        with self.assertRaisesRegex(ValueError, "digest|corrupt|snapshot"):
            self.store().recover("request-corrupt")
        self.assertFalse(any(request == "request-corrupt" for request, _body in self.provider.calls),
                         "corrupt recovered bytes must never cross dispatch barrier")

    def test_dispatching_crashes_are_uncertain_and_reconcile_is_bounded(self):
        self.require_behavior('durable dispatching barrier and bounded uncertainty reconciliation')
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
        self.assertEqual("confirmed", uncertain.reconcile("request-lost")["state"])
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
        self.assert_runnable_recovery(caught, "request-bounded", "three-check-limit")

        failed = self.store()
        failed.write("goal:554", "pre-apply", {"value": "not applied"})
        failed.freeze("goal:554", "pre-apply", "request-pre-apply", "goal-submit")
        with self.assertRaises(self.module.WorkingInputUncertain) as caught:
            failed.dispatch("request-pre-apply", self.provider.fail_before_apply)
        self.assertNotIn("request-pre-apply", self.provider.applied)
        self.assert_runnable_recovery(caught, "request-pre-apply", "provider-exception")
        restarted = self.store()
        self.assertEqual("uncertain", restarted.status("request-pre-apply")["state"])
        self.provider.check_results = [False]
        restarted.reconcile("request-pre-apply")
        restarted.dispatch("request-pre-apply", self.provider.send)
        confirmed = self.store()
        self.assertEqual("confirmed", confirmed.status("request-pre-apply")["state"])
        receipt = confirmed.status("request-pre-apply")["receipt"]
        snapshot = Path(confirmed.status("request-pre-apply")["snapshot"])
        self.assertTrue(snapshot.is_file())
        confirmed.retire("request-pre-apply", receipt)
        self.assertFalse(snapshot.exists(), "restart must observe durable confirmation before deletion")

    def test_repair_missing_receipt_and_unconfirmed_reconciliation_retain_exact_bytes(self):
        self.require_behavior('distinct repair, missing-receipt and unconfirmed-reconciliation uncertainty')
        store = self.store()
        cases = (("repair", self.provider.repair_response, "repair-response"),
                 ("missing", self.provider.missing_receipt, "missing-receipt"))
        for label, sender, recovery_reason in cases:
            purpose, request = f"uncertain-{label}", f"request-{label}"
            store.write("goal:554", purpose, {"case": label})
            frozen = store.freeze("goal:554", purpose, request, "goal-submit")
            exact = Path(frozen["snapshot"]).read_bytes()
            with self.assertRaises(self.module.WorkingInputUncertain) as caught:
                store.dispatch(request, sender)
            self.assertIn(label if label == "repair" else "receipt", str(caught.exception).lower())
            status = store.status(request)
            self.assertEqual("uncertain", status["state"])
            self.assertEqual(exact, Path(status["snapshot"]).read_bytes())
            self.assert_runnable_recovery(caught, request, recovery_reason)

        self.provider.check_results = [None, None, None]
        before = Path(store.status("request-missing")["snapshot"]).read_bytes()
        with self.assertRaises(self.module.WorkingInputUncertain) as caught:
            store.reconcile("request-missing")
        after = store.status("request-missing")
        self.assertEqual("uncertain", after["state"])
        self.assertEqual(before, Path(after["snapshot"]).read_bytes())
        self.assert_runnable_recovery(caught, "request-missing", "unconfirmed-reconciliation")

    def test_active_references_block_handoff_retirement_and_abandonment(self):
        self.require_behavior('lease, reader, provider-dispatch and locked deletion races')
        store = self.store()
        descriptor = store.write("goal:554", "execute", {"value": "protected"})
        store.freeze("goal:554", "execute", "request-ref", "goal-submit")
        with store.reference("request-ref", "lease"):
            with self.assertRaises(self.module.WorkingInputBusy) as caught:
                store.handoff("goal:554", "execute", "worker")
            self.assert_runnable_recovery(caught, "request-ref", "active-lease")
        with store.reader("request-ref") as body:
            self.assertIsInstance(body, bytes)
            for operation in (
                lambda: store.handoff("goal:554", "execute", "worker"),
                lambda: store.retire("request-ref", {"receipt": "request-ref"}),
                lambda: store.abandon("request-ref", approved_by="user"),
            ):
                with self.assertRaises(self.module.WorkingInputBusy) as caught:
                    operation()
                self.assert_runnable_recovery(caught, "request-ref", "active-reference")
            self.assertTrue(Path(store.status("request-ref")["snapshot"]).exists())

        store.write("goal:554", "provider-race", {"value": "in flight"})
        store.freeze("goal:554", "provider-race", "request-provider-race", "goal-submit")
        dispatch_errors = []
        dispatch = threading.Thread(target=lambda: self._capture(
            dispatch_errors, store.dispatch, "request-provider-race", self.provider.blocking_send))
        dispatch.start()
        self.assertTrue(self.provider.dispatch_started.wait(5), "provider dispatch did not reach synchronized barrier")
        for operation in (
            lambda: store.handoff("goal:554", "provider-race", "worker"),
            lambda: store.retire("request-provider-race", {"receipt": "request-provider-race"}),
            lambda: store.abandon("request-provider-race", approved_by="user"),
        ):
            with self.assertRaises(self.module.WorkingInputBusy):
                operation()
        self.provider.dispatch_release.set()
        dispatch.join(5)
        self.assertFalse(dispatch.is_alive())
        self.assertEqual([], dispatch_errors)

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

        before_delete = threading.Event()
        reader_acquired = threading.Event()
        release_reader = threading.Event()
        def deletion_fault(point):
            if point == "before_delete_lock":
                before_delete.set()
                if not reader_acquired.wait(5):
                    raise AssertionError("final deletion race reader was not acquired")
        guarded = self.store(fault=deletion_fault)
        guarded.write("goal:554", "delete-race", {"value": "recheck"})
        guarded.freeze("goal:554", "delete-race", "request-delete-race", "goal-submit")
        guarded.dispatch("request-delete-race", self.provider.send)
        late_errors = []
        def late_reader():
            try:
                if not before_delete.wait(5):
                    raise AssertionError("retirement did not reach pre-lock barrier")
                with self.store().reader("request-delete-race"):
                    reader_acquired.set()
                    if not release_reader.wait(5):
                        raise AssertionError("late reader was not released")
            except BaseException as exc:
                late_errors.append(exc)
        reader = threading.Thread(target=late_reader)
        reader.start()
        with self.assertRaises(self.module.WorkingInputBusy):
            guarded.retire("request-delete-race", {"receipt": "request-delete-race"})
        release_reader.set()
        reader.join(5)
        self.assertEqual([], late_errors)
        self.assertTrue(Path(guarded.status("request-delete-race")["snapshot"]).exists(),
                        "retirement must recheck references under the final deletion lock")

        abandon_before_lock = threading.Event()
        abandon_reader_acquired = threading.Event()
        abandon_release = threading.Event()
        def abandon_fault(point):
            if point == "before_delete_lock":
                abandon_before_lock.set()
                if not abandon_reader_acquired.wait(5):
                    raise AssertionError("abandonment race reader was not acquired")
        abandon_store = self.store(fault=abandon_fault)
        abandon_store.write("goal:554", "abandon-race", {"value": "recheck"})
        abandon_store.freeze("goal:554", "abandon-race", "request-abandon-race", "goal-submit")
        protected = self.repo / ".zzzops" / "protected"
        protected.mkdir(parents=True)
        protected_files = {}
        for name in ("published-evidence", "approvals", "receipts", "history", "diagnostics"):
            target = protected / f"{name}.json"
            target.write_bytes((json.dumps({"sentinel": name}) + "\n").encode())
            protected_files[target] = target.read_bytes()
        abandon_errors = []
        def abandon_late_reader():
            try:
                if not abandon_before_lock.wait(5):
                    raise AssertionError("abandonment did not reach pre-lock barrier")
                with self.store().reader("request-abandon-race"):
                    abandon_reader_acquired.set()
                    if not abandon_release.wait(5):
                        raise AssertionError("abandonment late reader was not released")
            except BaseException as exc:
                abandon_errors.append(exc)
        abandon_reader = threading.Thread(target=abandon_late_reader)
        abandon_reader.start()
        with self.assertRaises(self.module.WorkingInputBusy):
            abandon_store.abandon("request-abandon-race", approved_by="user")
        abandon_release.set()
        abandon_reader.join(5)
        self.assertEqual([], abandon_errors)
        self.assertTrue(Path(abandon_store.status("request-abandon-race")["snapshot"]).exists(),
                        "abandonment must recheck references under the final deletion lock")
        abandon_store.abandon("request-abandon-race", approved_by="user")
        self.assertEqual(protected_files, {path: path.read_bytes() for path in protected_files},
                         "abandonment may delete only the working snapshot")

    def test_unresolved_snapshots_have_no_age_or_count_eviction(self):
        self.require_behavior('unresolved snapshot retention without eviction')
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

    def test_exclusive_freeze_private_storage_and_deletion_recovery(self):
        self.require_behavior('exclusive snapshot publication, private storage and durable deletion')
        store = self.store()
        first = store.write("draft:one", "execute", {"value": "first"})
        second = store.write("draft:two", "execute", {"value": "second"})
        self.assertNotEqual(first["payload_id"], second["payload_id"])
        self.assertEqual(0o700, (self.repo / ".zzzops/work/inputs/v1").stat().st_mode & 0o777)
        self.assertEqual(0o600, Path(first["path"]).stat().st_mode & 0o777)

        snapshots = self.repo / ".zzzops/work/inputs/v1/snapshots"
        snapshots.mkdir(parents=True, exist_ok=True)
        orphan = snapshots / "exclusive.json"
        orphan.write_bytes(b"old exact bytes")
        with self.assertRaises(FileExistsError):
            store.freeze("draft:one", "execute", "exclusive", "goal-submit")
        self.assertEqual(b"old exact bytes", orphan.read_bytes())
        with self.assertRaises(KeyError):
            store.status("exclusive")

        duplicate = store.freeze("draft:one", "execute", "duplicate", "goal-submit")
        duplicate_bytes = Path(duplicate["snapshot"]).read_bytes()
        store.write("draft:one", "execute", {"value": "changed"})
        with self.assertRaisesRegex(ValueError, "request_id already exists"):
            store.freeze("draft:one", "execute", "duplicate", "goal-submit")
        self.assertEqual(duplicate_bytes, Path(duplicate["snapshot"]).read_bytes())

        frozen = store.freeze("draft:one", "execute", "delete-recovery", "goal-submit")
        store.dispatch("delete-recovery", self.provider.send)
        crashing = self.store(fault=lambda point: (_ for _ in ()).throw(RuntimeError(point))
                              if point == "after_delete_transition" else None)
        with self.assertRaisesRegex(RuntimeError, "after_delete_transition"):
            crashing.retire("delete-recovery", {"receipt": "delete-recovery"})
        recovered = self.store().status("delete-recovery")
        self.assertEqual("retired", recovered["state"])
        self.assertFalse(Path(frozen["snapshot"]).exists())

    def test_request_ids_are_contained_and_failed_index_save_leaves_no_orphan(self):
        self.require_behavior('bounded request identity and failed-index snapshot cleanup')
        store = self.store(); store.write("goal:554", "contained", {"value": 1})
        for invalid in ("../escape", "/absolute", "space value", "", "x" * 129):
            with self.subTest(request_id=invalid), self.assertRaisesRegex(ValueError, "request_id"):
                store.freeze("goal:554", "contained", invalid, "goal-submit")
        original = store._save
        store._save = lambda state: (_ for _ in ()).throw(OSError("index fsync failed"))
        with self.assertRaisesRegex(OSError, "index fsync failed"):
            store.freeze("goal:554", "contained", "save-failure", "goal-submit")
        store._save = original
        self.assertFalse((self.repo / ".zzzops/work/inputs/v1/snapshots/save-failure.json").exists())

    @unittest.skipIf(sys.platform == "win32", "linked-worktree process fixture uses POSIX signalling")
    def test_linked_worktree_process_reference_uses_common_git_lock(self):
        self.require_behavior('linked-worktree and process durable reference coordination')
        subprocess.run(["git", "config", "user.email", "fixture@example.invalid"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.name", "Fixture"], cwd=self.repo, check=True)
        marker = self.repo / "tracked"; marker.write_text("x")
        subprocess.run(["git", "add", "tracked"], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-qm", "fixture"], cwd=self.repo, check=True)
        linked = Path(self.temporary.name) / "linked"
        subprocess.run(["git", "worktree", "add", "-q", "--detach", str(linked)], cwd=self.repo, check=True)
        store = self.store(); store.write("goal:554", "process", {"value": 1})
        store.freeze("goal:554", "process", "process-reference", "goal-submit")
        ready, release = Path(self.temporary.name) / "ready", Path(self.temporary.name) / "release"
        script = """
import importlib.util, pathlib, sys, time
spec=importlib.util.spec_from_file_location('child_working_inputs', sys.argv[1]); m=importlib.util.module_from_spec(spec); sys.modules[spec.name]=m; spec.loader.exec_module(m)
s=m.WorkingInputStore(pathlib.Path(sys.argv[2]), repository='owner/project', owner='worker')
with s.reference('process-reference', 'reader'):
 pathlib.Path(sys.argv[3]).write_text('ready')
 while not pathlib.Path(sys.argv[4]).exists(): time.sleep(.02)
"""
        child = subprocess.Popen([sys.executable, "-c", script, str(MODULE), str(linked), str(ready), str(release)])
        try:
            for _ in range(100):
                if ready.exists(): break
                time.sleep(.02)
            self.assertTrue(ready.exists())
            with self.assertRaises(self.module.WorkingInputBusy):
                store.abandon("process-reference", approved_by="user")
            common = subprocess.run(["git", "rev-parse", "--git-common-dir"], cwd=linked,
                                    text=True, capture_output=True, check=True).stdout.strip()
            self.assertEqual((self.repo / ".git").resolve(), (linked / common).resolve())
            self.assertEqual(0, subprocess.run(
                ["git", "check-ignore", "-q", ".zzzops/work/inputs/v1/input.json"],
                cwd=linked, check=False).returncode)
        finally:
            release.touch(); child.wait(5)

    @unittest.skipIf(sys.platform == "win32", "fake gh executable fixture is POSIX")
    def test_public_cli_reconcile_uses_provider_evidence(self):
        self.require_behavior('public CLI reconciliation uses real provider evidence')
        store = self.store(); store.write("goal:554", "cli", {"value": "remote"})
        frozen = store.freeze("goal:554", "cli", "request-cli", "goal-submit")
        with self.assertRaises(self.module.WorkingInputUncertain):
            store.dispatch("request-cli", self.provider.missing_receipt)
        binary = Path(self.temporary.name) / "bin"; binary.mkdir()
        gh = binary / "gh"
        receipt = {"request_id": "request-cli", "digest": frozen["digest"],
                   "action": "goal-submit", "authenticated": True}
        response = json.dumps([[{"body": json.dumps(receipt), "author_association": "OWNER"}]])
        gh.write_text("#!" + sys.executable + "\nprint(" + repr(response) + ")\n")
        gh.chmod(0o700)
        environment = dict(os.environ, PATH=str(binary) + os.pathsep + os.environ.get("PATH", ""))
        result = subprocess.run(
            [sys.executable, str(ROOT / "plugins/zzzops/zzzops/zzzops.py"),
             "working-input", "reconcile", "--repo", str(self.repo),
             "--request-id", "request-cli"],
            text=True, capture_output=True, env=environment, check=False)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("confirmed", json.loads(result.stdout)["state"])

    def test_process_reference_blocks_deletion_on_supported_platform(self):
        self.require_behavior('real cross-process reference lock')
        store = self.store(); store.write("goal:554", "process-lock", {"value": 1})
        store.freeze("goal:554", "process-lock", "process-lock", "goal-submit")
        ready, release = Path(self.temporary.name) / "process-ready", Path(self.temporary.name) / "process-release"
        script = """
import importlib.util, pathlib, sys, time
spec=importlib.util.spec_from_file_location('process_working_inputs', sys.argv[1]); m=importlib.util.module_from_spec(spec); sys.modules[spec.name]=m; spec.loader.exec_module(m)
s=m.WorkingInputStore(pathlib.Path(sys.argv[2]), repository='owner/project', owner='worker')
with s.reference('process-lock', 'reader'):
 pathlib.Path(sys.argv[3]).write_text('ready')
 while not pathlib.Path(sys.argv[4]).exists(): time.sleep(.02)
"""
        child = subprocess.Popen([sys.executable, "-c", script, str(MODULE), str(self.repo), str(ready), str(release)])
        try:
            for _ in range(150):
                if ready.exists(): break
                time.sleep(.02)
            self.assertTrue(ready.exists(), "child process did not acquire its durable reference")
            with self.assertRaises(self.module.WorkingInputBusy):
                store.abandon("process-lock", approved_by="user")
        finally:
            release.touch(); child.wait(5)

    def test_public_mutation_runs_from_frozen_bytes_after_dispatch_barrier(self):
        self.require_behavior('real public mutation consumes frozen bytes after durable barrier')
        sys.path.insert(0, str(ROOT / ".agents"))
        try:
            import test_zzzops as fixtures
            public_cli = fixtures.zzzops
        finally:
            sys.path.pop(0)
        payload = {"operation": "submit", "request_id": "barrier-request", "value": "exact"}
        observed = []
        def provider_boundary(api, repo, intent, source, runtime, exact, number, **options):
            row = api._working_inputs.WorkingInputStore(
                repo, repository="local", owner="root").status("barrier-request")
            observed.append((row["state"], exact, Path(row["snapshot"]).read_bytes()))
            return {"next_steps": [{"kind": "checkpoint"}]}
        with mock.patch.object(public_cli._workflow, "_public_run", side_effect=provider_boundary):
            result = public_cli._workflow.public_run(
                public_cli, self.repo, "execute", "$execute-zzzops",
                {"root_id": "root"}, payload, 554)
        self.assertEqual("checkpoint", result["next_steps"][0]["kind"])
        self.assertEqual("dispatching", observed[0][0])
        self.assertEqual(payload, observed[0][1])
        self.assertEqual(payload, json.loads(observed[0][2]))
        self.assertEqual("confirmed", self.store().status("barrier-request")["state"])

    @staticmethod
    def _capture(errors, function, *args):
        try:
            function(*args)
        except BaseException as exc:
            errors.append(exc)

    def test_repository_machine_lock_serializes_writers_and_handoff(self):
        self.require_behavior('repository-machine lock and explicit handoff')
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
        self.require_behavior('public next-step guidance, readable JSON and legacy preservation')
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
        sys.path.insert(0, str(ROOT / ".agents"))
        try:
            import test_zzzops as fixtures
            public_cli = fixtures.zzzops
        finally:
            sys.path.pop(0)
        routes = {
            "capture": ("capture", "$add-zzzops-goal"),
            "execute": ("execute", "$execute-zzzops"),
            "migration": ("inspect", "$migrate-to-zzzops"),
            "policy-review": ("inspect", "$review-zzzops-policy"),
        }
        engine = mock.MagicMock()
        engine.read_only.return_value = None
        engine.portfolio.return_value = None
        checkpoints = {
            "migration": {"next_steps": [{"kind": "migration-checkpoint"}]},
            "execute": {"next_steps": [{"kind": "execute-checkpoint"}]},
        }
        with (mock.patch.object(public_cli._package, "package_status",
                                return_value={"ok": True, "version": "1", "revision": "abc"}),
              mock.patch.object(public_cli._installation, "validation_status",
                                return_value={"required": False}),
              mock.patch.object(public_cli, "workflow_context_step",
                                return_value=None),
              mock.patch.object(public_cli, "reviewed_project_state", return_value={}),
              mock.patch.object(public_cli._workflow, "Workflow", return_value=engine),
              mock.patch.object(public_cli._workflow, "checkpoint") as checkpoint):
            for purpose, (intent, source) in routes.items():
                checkpoint.return_value = checkpoints.get(purpose, {"next_steps": []})
                result = public_cli._workflow.public_run(
                    public_cli, self.repo, intent, source, {"root_id": "root"}, None, None)
                self.assertIsInstance(result, dict)
                self.assertIsInstance(result.get("next_steps"), list)
                expected_kind = {"capture": "capture", "execute": "execute-checkpoint",
                                 "migration": "migration-checkpoint", "policy-review": None}[purpose]
                actual_kind = result["next_steps"][0]["kind"] if result["next_steps"] else None
                self.assertEqual(expected_kind, actual_kind,
                                 f"controlled ready {purpose}/{intent} route returned the wrong response")
                guidance = result.get("working_input")
                self.assertIsInstance(
                    guidance, dict,
                    f"actual public {purpose}/{intent} response must return working-input guidance")
                self.assertTrue(Path(guidance["path"]).is_relative_to(
                    self.repo / ".zzzops/work/inputs/v1"))
                commands = guidance["commands"]
                self.assertTrue(commands)
                self.assertNotIn("<", " ".join(commands[0]))
            first_draft = public_cli._workflow.public_run(
                public_cli, self.repo, "capture", "$add-zzzops-goal", {"root_id": "root"}, None, None)
            concurrent = public_cli._workflow.public_run(
                public_cli, self.repo, "capture", "$add-zzzops-goal", {"root_id": "root"}, None, None)
            self.assertNotEqual(first_draft["working_input"]["draft_id"],
                                concurrent["working_input"]["draft_id"])
            resumed = public_cli._workflow.public_run(
                public_cli, self.repo, "capture", "$add-zzzops-goal",
                {"root_id": "root", "working_input_draft": first_draft["working_input"]["draft_id"]},
                None, None)
            self.assertEqual(first_draft["working_input"]["path"], resumed["working_input"]["path"])
        self.assertEqual('{"operation":"submit"}\n', legacy.read_text())

        descriptor = store.write("goal:554", "execute", {"z": 1, "a": [2, 3]})
        ignored = subprocess.run(
            ["git", "check-ignore", "-q", str(Path(descriptor["path"]).relative_to(self.repo))],
            cwd=self.repo, check=False)
        self.assertEqual(0, ignored.returncode, ".zzzops working-input state must be ignored by Git")
        command = store.guidance("goal:554", "execute")["commands"][0]
        rendered = subprocess.run(command, cwd=self.repo, text=True, capture_output=True, check=True)
        self.assertEqual(json.loads(Path(descriptor["path"]).read_text()), json.loads(rendered.stdout))


if __name__ == "__main__":
    unittest.main()
