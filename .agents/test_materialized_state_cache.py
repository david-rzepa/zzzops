"""Black-box durable materialized-state behavior for goal #597."""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from test_evidence_dag_journeys import DagFixture, TaskSession, z

store = z._comment_store


class RestartedMaterializedStateTests(DagFixture):
    """Every observation after ``restart`` traverses a new public dispatcher."""

    def setUp(self):
        super().setUp()
        self.cache_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.cache_directory.cleanup)
        environment = mock.patch.dict(os.environ, {"XDG_CACHE_HOME": self.cache_directory.name})
        environment.start()
        self.addCleanup(environment.stop)

    def restart(self):
        # PublicSession invokes api.main each time; replacing the wrapper as well
        # prevents an invocation-local object from satisfying a resumed check.
        z._workflow._OBSERVED_ARTIFACT_INDEXES.clear()
        self.session = TaskSession(
            self.fixture.repo, copy.deepcopy(self.session.project),
            copy.deepcopy(self.session.runtime), self.provider, self.session.control,
        )
        return self.session

    def publish_checkpoint(self):
        start = max(row["id"] for row in self.provider.comments[100]) + 1
        self.provider.comments[100].extend(
            {"id": start + offset, "body": f"retained history {offset}"}
            for offset in range(40)
        )
        step = next(item for item in self.session.call(100)["next_steps"]
                    if item["kind"] == "hydration_checkpoint")
        self.session.call(100, step["submission"])
        stamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        self.provider.get_issue_comment_tail = mock.Mock(side_effect=lambda number, limit=100: [
            {**row, "created_at": row.get("created_at", stamp),
             "updated_at": row.get("updated_at", stamp)}
            for row in self.provider.comments[number][-limit:]
        ])
        return step

    def files(self):
        return {path.relative_to(self.cache_directory.name): path.read_bytes()
                for path in Path(self.cache_directory.name).rglob("*") if path.is_file()}

    def test_absolute_state_survives_dispatcher_restart_and_is_partitioned(self):
        self.publish_checkpoint()
        self.session.call(100)
        self.assertTrue(self.files(), "a resumed process needs durable derived state")

        with mock.patch.object(store, "hydration_checkpoint_view",
                               side_effect=AssertionError("exact resumed head must reuse absolute state")):
            self.restart().call(100)

        self.provider.issues[100]["body"] += "\nconcurrent human edit"
        with mock.patch.object(self.provider, "get_issue_comments",
                               wraps=self.provider.get_issue_comments) as full:
            self.restart().call(100)
        self.assertEqual(1, full.call_count, "issue-body identity partitions durable state")

        other = self.restart()
        other.project["repository"] = "other/repo"
        rejected = other.call(100, expected=2)
        self.assertEqual("repair", rejected["next_steps"][0]["kind"])
        self.assertRegex(str(rejected["next_steps"][0]), "(?i)repository|identity")

    def test_edit_and_delete_invalidate_before_reuse(self):
        self.publish_checkpoint()
        self.session.call(100)
        original = copy.deepcopy(self.provider.comments[100])
        edited = copy.deepcopy(original)
        edited[0]["body"] += " edited"
        for name, comments in (("edit", edited), ("delete", original[1:])):
            with self.subTest(name=name):
                self.provider.comments[100] = copy.deepcopy(comments)
                with mock.patch.object(self.provider, "get_issue_comments",
                                       wraps=self.provider.get_issue_comments) as full:
                    self.restart().call(100)
                self.assertEqual(1, full.call_count)
                self.provider.comments[100] = copy.deepcopy(original)

    def test_persisted_version_mismatch_is_a_safe_miss_without_naming_an_implementation_constant(self):
        self.publish_checkpoint(); self.session.call(100)
        changed = 0
        for path in Path(self.cache_directory.name).rglob("*.json"):
            document = json.loads(path.read_text(encoding="utf-8"))
            def replace(value):
                nonlocal changed
                if isinstance(value, dict):
                    for key, child in value.items():
                        if "version" in key.casefold():
                            value[key] = "unsupported-by-current-reader"; changed += 1
                        else: replace(child)
                elif isinstance(value, list):
                    for child in value: replace(child)
            replace(document)
            path.write_text(json.dumps(document), encoding="utf-8")
        self.assertGreater(changed, 0, "durable state must persist its codec/reducer/schema version")
        with mock.patch.object(self.provider, "get_issue_comments",
                               wraps=self.provider.get_issue_comments) as full:
            self.restart().call(100)
        self.assertEqual(1, full.call_count)

    def test_ambiguous_nonunique_or_unordered_head_forces_complete_read(self):
        self.publish_checkpoint(); self.session.call(100)
        original_tail = self.provider.get_issue_comment_tail
        for name, transform in (
                ("duplicate", lambda rows: rows + [copy.deepcopy(rows[-1])]),
                ("unordered", lambda rows: list(reversed(rows))),
                ("missing_identity", lambda rows: [{k: v for k, v in row.items() if k != "id"}
                                                     for row in rows])):
            with self.subTest(name=name):
                self.provider.get_issue_comment_tail = lambda number, limit=100, transform=transform: transform(
                    original_tail(number, limit))
                with mock.patch.object(self.provider, "get_issue_comments",
                                       wraps=self.provider.get_issue_comments) as full:
                    response = self.restart().call(100)
                self.assertTrue(response["next_steps"])
                self.assertEqual(1, full.call_count,
                                 "ambiguous head cannot authorize absolute-state reuse")
        self.provider.get_issue_comment_tail = original_tail

    def test_corrupt_or_ambiguous_derived_storage_is_a_safe_miss(self):
        self.publish_checkpoint()
        self.session.call(100)
        paths = [path for path in Path(self.cache_directory.name).rglob("*") if path.is_file()]
        self.assertTrue(paths)
        for path in paths:  # valid implementations may keep one or many snapshots
            path.write_bytes(b"{interrupted")
        with mock.patch.object(self.provider, "get_issue_comments",
                               wraps=self.provider.get_issue_comments) as full:
            response = self.restart().call(100)
        self.assertTrue(response["next_steps"])
        self.assertEqual(1, full.call_count)

    def test_failed_partial_read_does_not_populate_and_exact_retry_identity_is_stable(self):
        self.publish_checkpoint()
        before = self.files()
        calls = []

        def cancelled(number, limit=100):
            calls.append(("tail", number, limit))
            raise z.GoalHistoryReadError("cancelled tail")

        original = self.provider.get_issue_comments
        self.provider.get_issue_comment_tail = cancelled
        with mock.patch.object(self.provider, "get_issue_comments", side_effect=lambda number: (
                calls.append(("full", number)) or (_ for _ in ()).throw(z.GoalHistoryReadError("partial page")))):
            failed = self.restart().call(100, expected=2)
        self.assertRegex(str(failed), "partial")
        self.assertEqual(before, self.files())
        failed_identity = copy.deepcopy(calls)

        calls.clear()
        self.provider.get_issue_comment_tail = cancelled
        with mock.patch.object(self.provider, "get_issue_comments", side_effect=lambda number: (
                calls.append(("full", number)) or original(number))):
            retry = self.restart().call(100)
        self.assertTrue(retry["next_steps"])
        self.assertEqual(failed_identity, calls)
        self.assertTrue(self.files())


if __name__ == "__main__":
    unittest.main()
