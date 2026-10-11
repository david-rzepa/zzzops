"""Cross-version contract for incremental GitHub comment markers."""
import json
import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import zzzops


IDENTITY = SimpleNamespace(
    returncode=0,
    stderr="",
    stdout=json.dumps({
        "nameWithOwner": "owner/repo",
        "hasIssuesEnabled": True,
        "viewerPermission": "ADMIN",
    }),
)


class IncrementalCommentMarkerTests(unittest.TestCase):
    def adapter(self):
        patcher = mock.patch.object(zzzops.shutil, "which", return_value="gh")
        patcher.start()
        self.addCleanup(patcher.stop)
        return zzzops.GitHubGoalTransitionAdapter(Path.cwd(), "owner/repo")

    @staticmethod
    def comment(identifier=9):
        return {
            "id": identifier,
            "body": "history",
            "updated_at": "2026-01-02T00:00:00Z",
        }

    def test_timezone_markers_reach_complete_overlap_with_exact_encoding_and_counters(self):
        cases = (
            ("2026-01-01T23:59:59Z", "2026-01-01T23:59:59Z"),
            ("2026-01-01T23:59:59.123456Z", "2026-01-01T23:59:59.123456Z"),
            ("2026-01-01T23:59:59+05:30", "2026-01-01T23:59:59%2B05:30"),
            ("2026-01-01T23:59:59.5-04:00", "2026-01-01T23:59:59.5-04:00"),
        )
        for marker, encoded in cases:
            with self.subTest(marker=marker), mock.patch.object(zzzops.subprocess, "run") as run:
                comments = [self.comment()]
                raw = json.dumps([comments])
                run.side_effect = [IDENTITY, SimpleNamespace(returncode=0, stderr="", stdout=raw)]
                adapter = self.adapter()

                self.assertEqual(comments, adapter.get_issue_comments_since(42, marker))
                self.assertEqual(
                    {"calls": 1, "bytes": len(raw.encode()), "comments": 1,
                     "modes": {"since": 1}},
                    adapter.comment_read_counters[42],
                )
                self.assertEqual(
                    ["gh", "api", "--paginate", "--slurp",
                     "repos/owner/repo/issues/42/comments?per_page=100&since=" + encoded],
                    run.call_args_list[1].args[0],
                )

    @mock.patch.object(zzzops.subprocess, "run")
    def test_incremental_pagination_flattens_complete_pages_and_counts_once(self, run):
        first = [self.comment(identifier) for identifier in range(1, 101)]
        second = [self.comment(101)]
        raw = json.dumps([first, second])
        run.side_effect = [IDENTITY, SimpleNamespace(returncode=0, stderr="", stdout=raw)]
        adapter = self.adapter()

        self.assertEqual(first + second,
                         adapter.get_issue_comments_since(42, "2026-01-01T23:59:59Z"))
        self.assertEqual(
            {"calls": 1, "bytes": len(raw.encode()), "comments": 101,
             "modes": {"since": 1}},
            adapter.comment_read_counters[42],
        )

    def test_invalid_markers_fail_before_identity_or_provider_calls(self):
        invalid = (
            None, True, 1, "", " ", "not-a-timestamp", "2026-02-30T12:00:00Z",
            "2026-01-01T23:59:59", "https://example.test/2026-01-01T23:59:59Z",
            "2026-01-01T25:00:00Z", "2026-01-01 23:59:59",
        )
        for marker in invalid:
            with self.subTest(marker=marker), mock.patch.object(
                    zzzops.subprocess, "run",
                    side_effect=[IDENTITY, SimpleNamespace(returncode=0, stderr="", stdout="[[]]")],
            ) as run:
                adapter = self.adapter()
                with self.assertRaisesRegex(zzzops.GoalHistoryReadError,
                                            "Invalid incremental comment marker"):
                    adapter.get_issue_comments_since(42, marker)
                run.assert_not_called()
                self.assertEqual({}, adapter.comment_read_counters)

    def test_identity_and_provider_failures_require_complete_history_fallback(self):
        failures = (
            ("identity", [SimpleNamespace(returncode=1, stderr="identity denied", stdout="")]),
            ("provider", [IDENTITY, SimpleNamespace(returncode=1, stderr="provider denied", stdout="")]),
            ("exception", [IDENTITY, subprocess.TimeoutExpired("gh", 30)]),
        )
        for name, effects in failures:
            with self.subTest(name=name), mock.patch.object(zzzops.subprocess, "run",
                                                            side_effect=effects):
                adapter = self.adapter()
                with self.assertRaises(zzzops.GoalHistoryReadError) as raised:
                    adapter.get_issue_comments_since(42, "2026-01-01T23:59:59Z")
                self.assertIn("Incremental comment-history read", str(raised.exception))
                self.assertIn("Fall back to a complete history read", str(raised.exception))
                self.assertEqual({}, adapter.comment_read_counters)

    @mock.patch.object(zzzops.subprocess, "run")
    def test_incomplete_provider_pages_never_return_partial_history(self, run):
        incomplete = json.dumps([[self.comment()] * 99, [self.comment(100)]])
        run.side_effect = [IDENTITY, SimpleNamespace(returncode=0, stderr="", stdout=incomplete)]
        adapter = self.adapter()

        with self.assertRaisesRegex(zzzops.GoalHistoryReadError,
                                    "invalid or partial comment history"):
            adapter.get_issue_comments_since(42, "2026-01-01T23:59:59Z")
        self.assertEqual({}, adapter.comment_read_counters)


if __name__ == "__main__":
    unittest.main()
