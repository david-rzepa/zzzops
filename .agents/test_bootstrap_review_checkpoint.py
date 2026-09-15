import importlib.util
import unittest


MODULE_PATH = __import__("pathlib").Path(__file__).parents[1] / "plugins/zzzops/zzzops/bootstrap.py"
SPEC = importlib.util.spec_from_file_location("zzzops_bootstrap_checkpoint", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class BootstrapReviewCheckpointTests(unittest.TestCase):
    def _checkpoint(self, tooling=None):
        return MODULE.create_review_checkpoint(
            100, [12, 11, 12], tooling,
            {"title": "first milestone", "goal_id": None},
        )

    def test_checkpoint_waits_before_product_goals(self):
        checkpoint = self._checkpoint({"selected": True, "provenance": "tool-x@1"})
        self.assertEqual(checkpoint["status"], "awaiting_product_review")
        self.assertFalse(checkpoint["product_goals_created"])
        self.assertEqual(checkpoint["harness_goal_ids"], [11, 12])

    def test_repeated_bootstrap_reuses_checkpoint(self):
        first = self._checkpoint()
        repeated = MODULE.create_review_checkpoint(999, [], {"selected": True}, {}, existing=first)
        self.assertEqual(repeated, first)

    def test_approval_is_explicit_and_idempotent(self):
        checkpoint = self._checkpoint()
        approved = MODULE.record_review_decision(checkpoint, "approved", checkpoint["checkpoint_id"])
        self.assertEqual(MODULE.record_review_decision(approved, "approved", checkpoint["checkpoint_id"]), approved)
        self.assertEqual(approved["status"], "approved")

    def test_deferral_is_resumable_and_conflicting_decision_fails(self):
        checkpoint = self._checkpoint()
        deferred = MODULE.record_review_decision(checkpoint, "deferred", checkpoint["checkpoint_id"])
        self.assertEqual(deferred["status"], "deferred")
        with self.assertRaises(ValueError):
            MODULE.record_review_decision(deferred, "approved", checkpoint["checkpoint_id"])

    def test_no_selected_tooling_is_recorded_without_fake_candidate(self):
        checkpoint = self._checkpoint()
        self.assertEqual(checkpoint["tooling"], {"selected": False, "candidates": []})


if __name__ == "__main__":
    unittest.main()
