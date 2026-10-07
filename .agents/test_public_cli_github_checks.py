"""Deterministic public CLI provider-call ledgers for goal #597."""
from __future__ import annotations

import contextlib
import copy
from collections import Counter
from datetime import datetime, timezone
import os
import tempfile
import time
import unittest
from unittest import mock

from test_evidence_dag_journeys import DagFixture, TaskSession, z

store = z._comment_store


class Ledger:
    def __init__(self): self.rows = []
    def wrap(self, name, function):
        def observed(*args, **kwargs):
            self.rows.append((name, copy.deepcopy(args), copy.deepcopy(kwargs)))
            return function(*args, **kwargs)
        return observed
    def counts(self): return Counter(row[0] for row in self.rows)


class PublicCliGithubCheckTests(DagFixture):
    def setUp(self):
        super().setUp()
        self.cache_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.cache_directory.cleanup)
        environment = mock.patch.dict(os.environ, {"XDG_CACHE_HOME": self.cache_directory.name})
        environment.start(); self.addCleanup(environment.stop)

    def restart(self):
        z._workflow._OBSERVED_ARTIFACT_INDEXES.clear()
        self.session = TaskSession(self.fixture.repo, copy.deepcopy(self.session.project),
                                   copy.deepcopy(self.session.runtime), self.provider,
                                   self.session.control)
        return self.session

    def publish_checkpoint(self):
        start = max(row["id"] for row in self.provider.comments[100]) + 1
        self.provider.comments[100].extend(
            {"id": start + offset, "body": f"retained history {offset}"}
            for offset in range(40))
        step = next(item for item in self.session.call(100)["next_steps"]
                    if item["kind"] == "hydration_checkpoint")
        self.session.call(100, step["submission"])
        stamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        self.provider.get_issue_comment_tail = lambda number, limit=100: [
            {**row, "created_at": row.get("created_at", stamp),
             "updated_at": row.get("updated_at", stamp)}
            for row in self.provider.comments[number][-limit:]]
        return step

    def observe(self, session, payload=None):
        ledger = Ledger()
        names = ("get_issue", "get_issue_comment_tail", "get_issue_comments",
                 "create_issue_comment", "update_issue")
        patches = [mock.patch.object(self.provider, name,
                   side_effect=ledger.wrap(name, getattr(self.provider, name)))
                   for name in names if hasattr(self.provider, name)]
        session.portfolio_snapshot = ledger.wrap("portfolio_ownership", session.portfolio_snapshot)
        session.provider_issue_snapshot = ledger.wrap(
            "current_target", lambda _repo, _repository, number:
                copy.deepcopy(self.provider.issues[number]))
        for patch in patches: patch.start()
        try:
            result = session.call(100, payload) if payload is not None else session.call(100)
        finally:
            for patch in reversed(patches): patch.stop()
        return result, ledger

    def test_cold_warm_and_resumed_ledgers_keep_one_fresh_head_observation(self):
        self.publish_checkpoint()
        cold, cold_ledger = self.observe(self.restart())
        warm, warm_ledger = self.observe(self.session)
        resumed, resumed_ledger = self.observe(self.restart())
        self.assertEqual(cold["next_steps"], warm["next_steps"])
        self.assertEqual(warm["next_steps"], resumed["next_steps"])
        for ledger in (warm_ledger, resumed_ledger):
            self.assertEqual(1, ledger.counts()["get_issue_comment_tail"])
            self.assertEqual(0, ledger.counts()["get_issue_comments"])
        self.assertLess(sum(resumed_ledger.counts().values()), sum(cold_ledger.counts().values()))
        with mock.patch.object(store, "hydration_checkpoint_view",
                               side_effect=AssertionError("resumed exact head cannot replay deltas")):
            self.observe(self.restart())

    def test_advancing_head_folds_once_and_matches_cold_reconstruction(self):
        self.publish_checkpoint(); self.observe(self.restart())
        next_id = max(row["id"] for row in self.provider.comments[100]) + 1
        body = store.pack_envelopes(
            {"goal": 100, "transaction": "later", "anchor": "later", "context": {}},
            [store.ArtifactIndex([]).record({"cache-equivalence": "later-comment"})])[0]
        stamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        self.provider.comments[100].append(
            {"id": next_id, "body": body, "created_at": stamp, "updated_at": stamp})
        with mock.patch.object(store, "hydration_checkpoint_view",
                               wraps=store.hydration_checkpoint_view) as folds:
            incremental, ledger = self.observe(self.restart())
        self.assertEqual(1, folds.call_count)
        self.assertEqual(0, ledger.counts()["get_issue_comments"])
        with tempfile.TemporaryDirectory() as empty, mock.patch.dict(os.environ, {"XDG_CACHE_HOME": empty}):
            complete, _ = self.observe(self.restart())
        self.assertEqual(complete["next_steps"], incremental["next_steps"])

    def direct_public_mutation(self, payload, ledger):
        """Call the production public dispatcher with observable external gates."""
        session = self.session
        package = {"ok": True, "version": "test", "revision": "a" * 40}
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(z._package, "package_status",
                side_effect=lambda: (ledger.rows.append(("installation_package", (), {})) or package)))
            stack.enter_context(mock.patch.object(z, "workflow_context_step",
                side_effect=lambda *_a, **_k: (ledger.rows.append(("repository_context", (), {})) or None)))
            stack.enter_context(mock.patch.object(z._installation, "validation_status",
                side_effect=lambda *_a, **_k: (ledger.rows.append(("installation_status", (), {})) or {"required": False})))
            stack.enter_context(mock.patch.object(z, "reviewed_project_state",
                side_effect=lambda *_a: (ledger.rows.append(("policy", (), {})) or copy.deepcopy(session.project))))
            stack.enter_context(mock.patch.object(z, "GitHubGoalTransitionAdapter", return_value=self.provider))
            stack.enter_context(mock.patch.object(z, "GitHubReservationAdapter", return_value=mock.Mock()))
            stack.enter_context(mock.patch.object(z, "portfolio_snapshot",
                side_effect=ledger.wrap("ownership", session.portfolio_snapshot)))
            stack.enter_context(mock.patch.object(z, "provider_issue_snapshot",
                side_effect=ledger.wrap("current_target", lambda _r, _n, number:
                    copy.deepcopy(self.provider.issues[number]))))
            stack.enter_context(mock.patch.object(z, "acquire_storage_lock",
                side_effect=lambda *_a, **_k: (ledger.rows.append(("ownership", (), {})) or
                    {"acquired": True, "expires_at": time.time() + 300})))
            stack.enter_context(mock.patch.object(z, "renew_storage_lock",
                return_value={"acquired": True, "expires_at": time.time() + 300}))
            stack.enter_context(mock.patch.object(z, "release_storage_lock", return_value={"released": True}))
            stack.enter_context(mock.patch.object(self.provider, "get_issue",
                side_effect=ledger.wrap("current_target", self.provider.get_issue)))
            original_comments = self.provider.get_issue_comments
            def observed_comments(*args, **kwargs):
                ledger.rows.append(("provider_history", copy.deepcopy(args), copy.deepcopy(kwargs)))
                ledger.rows.append(("provider_uncertainty", copy.deepcopy(args), copy.deepcopy(kwargs)))
                return original_comments(*args, **kwargs)
            stack.enter_context(mock.patch.object(self.provider, "get_issue_comments",
                                                  side_effect=observed_comments))
            stack.enter_context(mock.patch.object(self.provider, "create_issue_comment",
                side_effect=ledger.wrap("write:create_issue_comment", self.provider.create_issue_comment)))
            stack.enter_context(mock.patch.object(self.provider, "update_issue",
                side_effect=ledger.wrap("write:update_issue", self.provider.update_issue)))
            return z._workflow.public_run(z, self.fixture.repo, "execute", "$execute-zzzops",
                                          session.runtime, payload, 100, payload_supplied=True)

    def test_mutation_rechecks_all_authority_boundaries_and_cache_is_never_write_authority(self):
        self.publish_checkpoint(); self.observe(self.restart())
        work = self.session.acquire("produce")
        payload = self.session.submission(work, {"value": "write-boundary candidate"},
                                          "authority-ledger-submit")
        ledger = Ledger()
        result = self.direct_public_mutation(payload, ledger)
        self.assertEqual("produce", result["submitted"]["node"]["node"])
        required = {"installation_package", "installation_status", "repository_context", "policy",
                    "ownership", "current_target", "provider_history", "provider_uncertainty"}
        self.assertTrue(required <= set(ledger.counts()), required - set(ledger.counts()))
        writes = [index for index, row in enumerate(ledger.rows) if row[0].startswith("write:")]
        self.assertTrue(writes)
        self.assertIn("write:create_issue_comment", ledger.counts())
        self.assertIn("write:update_issue", ledger.counts())
        gate_order = ["installation_package", "repository_context", "installation_status", "policy",
                      "ownership", "current_target", "provider_history", "provider_uncertainty"]
        previous_write = -1
        for write in writes:
            prefix = [row[0] for row in ledger.rows[:write]]
            positions = [max(index for index, value in enumerate(prefix) if value == gate)
                         for gate in gate_order]
            self.assertEqual(positions[:5], sorted(positions[:5]),
                             "installation, identity, policy and ownership gates are ordered")
            self.assertGreater(min(positions[5:]), positions[4],
                               "fresh target/history checks follow ownership and precede writes")
            self.assertLess(max(positions), write)
            self.assertGreater(min(positions), previous_write,
                               "cached or pre-previous-write checks cannot authorize another write")
            previous_write = write

    def test_failure_and_retry_keep_exact_bounded_provider_identity_without_overlap(self):
        self.publish_checkpoint()
        calls = []
        original_full = self.provider.get_issue_comments
        def failed_tail(number, limit=100):
            calls.append(("tail", number, limit)); raise z.GoalHistoryReadError("cancelled")
        self.provider.get_issue_comment_tail = failed_tail
        with mock.patch.object(self.provider, "get_issue_comments", side_effect=lambda number: (
                calls.append(("full", number)) or (_ for _ in ()).throw(z.GoalHistoryReadError("partial")))):
            failure = self.restart().call(100, expected=2)
        self.assertRegex(str(failure), "partial")
        failed = copy.deepcopy(calls); calls.clear()
        self.provider.get_issue_comment_tail = failed_tail
        with mock.patch.object(self.provider, "get_issue_comments", side_effect=lambda number: (
                calls.append(("full", number)) or original_full(number))):
            response = self.restart().call(100)
        self.assertTrue(response["next_steps"])
        self.assertEqual(failed, calls)
        self.assertEqual(len(calls), len(set(calls)))


if __name__ == "__main__": unittest.main()
