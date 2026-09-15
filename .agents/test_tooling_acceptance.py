import unittest

from tooling_acceptance import native_tooling_acceptance


class ToolingAcceptanceTests(unittest.TestCase):
    def test_native_capability_closes_gap_without_installation(self):
        first = native_tooling_acceptance()
        second = native_tooling_acceptance()
        self.assertTrue(first["native_search_ok"])
        self.assertTrue(first["reuse_behavior_ok"])
        self.assertIsNone(first["selected_candidate"])
        self.assertFalse(first["install_performed"])
        self.assertIn(first["fallback"], {"native_rg", "python_stdlib_search"})
        self.assertTrue(first["repeated_bootstrap_noop"])
        self.assertEqual(first["selected_candidate"], second["selected_candidate"])
        self.assertEqual(first["install_performed"], second["install_performed"])


if __name__ == "__main__":
    unittest.main()
