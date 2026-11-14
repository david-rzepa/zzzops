"""G1044: current producer refs are not pre-reset state; unknown names remain visible.

Only the two literal back_merge slots are current. Classification stays names-only,
so retained evidence needs no line/goal lookup or remote object inspection.
"""
from __future__ import annotations

import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import engine_fixtures as fx
from engine import legacy
from test_engine_legacy import LegacyCase


CURRENT_SYNC = (
    "refs/heads/zzzops/sync/g1/integration",
    "refs/heads/zzzops/sync/g123/release",
    "refs/heads/zzzops/sync/g9876543210/integration",
)
EXISTING_CURRENT = tuple(
    f"refs/heads/zzzops/{name}" for name in (
        "goal/g123", "work/g123", "pr/g123", "stack/g123",
        "lease/g123/implement", "policy/update",
        # G1044 deliberately does not narrow earlier alternatives' numeric handling.
        "goal/g0", "work/g01", "pr/g١", "stack/g0001",
    )
)
NEAR_MISSES = tuple(
    f"refs/heads/zzzops/sync/{name}" for name in (
        "g123/production", "g123/Integration", "g123/Release",
        "g123/integration/extra", "g123/release/extra", "g123/integration-old",
        "g123/integration.json", "g123", "integration", "g/integration",
        "g0/integration", "g01/integration", "g0123/release",
        "g+1/integration", "g-1/release", "gone/integration",
        "g١/integration", "g１/release", "gg123/integration",
    )
) + (
    "refs/zzzops/sync/g123/integration",
    "refs/heads/zzzops/sync-old/g123/integration",
    "refs/heads/zzzops/unknown/g123",
    "refs/heads/zzzops/attempts/42/old",
    "refs/heads/zzzops/goal-42/implement/run",
)


def session_for(refs=(), *, result=None, error=None):
    run = Mock()
    if error is not None:
        run.side_effect = error
    else:
        run.return_value = result or subprocess.CompletedProcess(
            [], 0, "".join(f"{'a' * 40}\t{ref}\n" for ref in refs), "")
    return SimpleNamespace(git=SimpleNamespace(run=run), R="origin")


class SyncRefCountTests(unittest.TestCase):
    def assert_inventory(self, refs, expected):
        session = session_for(refs)
        self.assertEqual((expected, None), legacy.count_refs(session))
        session.git.run.assert_called_once_with(
            "ls-remote", "origin", "refs/heads/zzzops/*", "refs/zzzops/*", check=False)

    def test_mixed_inventory_counts_only_genuine_old_and_unknown_refs(self):
        old = ("refs/heads/zzzops/attempts/42/old", "refs/heads/zzzops/unknown/g123")
        self.assert_inventory(CURRENT_SYNC + EXISTING_CURRENT + old, len(old))

    def test_complete_producer_shapes_are_current_independent_of_goal_membership(self):
        for ref in CURRENT_SYNC:
            with self.subTest(ref=ref):
                self.assert_inventory((ref,), 0)

    def test_adversarial_near_misses_remain_counted_individually(self):
        for ref in NEAR_MISSES:
            with self.subTest(ref=ref):
                self.assert_inventory((ref,), 1)

    def test_existing_current_alternatives_keep_their_previous_behavior(self):
        self.assert_inventory(EXISTING_CURRENT, 0)

    def test_remote_failure_is_unknown_not_a_false_clean_zero(self):
        session = session_for(result=subprocess.CompletedProcess([], 7, "", "\nfatal: unavailable\n"))
        self.assertEqual((None, "fatal: unavailable"), legacy.count_refs(session))
        session.git.run.assert_called_once()
        session = session_for(error=TimeoutError("bounded remote timeout"))
        self.assertEqual((None, "bounded remote timeout"), legacy.count_refs(session))
        session.git.run.assert_called_once()


class SyncRefDisclosureTests(LegacyCase):
    def seed_refs(self, refs):
        commit = self.w.remote_git("rev-parse", "refs/heads/dev")
        for ref in refs:
            self.w.remote_git("update-ref", ref, commit)

    def test_validate_discloses_only_old_ref_with_a_separate_active_signal(self):
        self.local_audit_file()
        self.old_ref()
        self.seed_refs(CURRENT_SYNC)
        out, git, gh = self.measure("validate")
        self.assert_one_check(git, gh)
        item = out["legacy"]
        self.assertEqual({"issues": 0, "files": 1, "refs": 1}, item["counts"])
        self.assertIn("1 old file, 1 old ref on origin", item["message"])
        self.assertEqual([".zzzops/PROJECT_AUDIT.md"], item["files"])
        self.assertEqual("migrate-zzzops-repository", item["skill"])
        self.assertEqual([], item["issues"])
        self.assertEqual([], item["linked"])
        self.assertFalse(item["truncated"])
        self.assertEqual(1, self.cache()["refs"])
        # Warm next uses the corrected stored count without another network check.
        out, git, gh = self.measure("next")
        self.assert_no_check(git, gh)
        self.assertEqual(item["counts"], out["legacy"]["counts"])

    def test_sync_only_is_cached_clean_and_old_refs_alone_still_do_not_activate(self):
        self.seed_refs(CURRENT_SYNC)
        out, git, gh = self.measure("validate")
        self.assert_one_check(git, gh)
        self.assertNotIn("legacy", out)
        self.assertEqual(0, self.cache()["refs"], "activation absence alone must not mask a false count")
        self.assertIsNone(self.cache()["retry_after"])
        out, git, gh = self.measure("next")
        self.assert_no_check(git, gh)
        self.assertNotIn("legacy", out)
        self.seed_refs(("refs/heads/zzzops/sync/g123/production",))
        out, git, gh = self.measure("validate")
        self.assert_one_check(git, gh)
        self.assertEqual(1, self.cache()["refs"], "unknown slot remains genuine advisory evidence")
        self.assertNotIn("legacy", out, "refs alone never activate the legacy item")


if __name__ == "__main__":
    unittest.main()
