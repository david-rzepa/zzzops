from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("prompt_stats.py")
SPEC = importlib.util.spec_from_file_location("prompt_stats", SCRIPT)
assert SPEC and SPEC.loader
prompt_stats = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prompt_stats)


class PromptStatsTests(unittest.TestCase):
    def test_canonical_size_is_line_ending_invariant(self) -> None:
        lf = "one\ntwo\n".encode()
        expected = prompt_stats.canonical_size(lf)
        self.assertEqual(prompt_stats.canonical_size(b"one\r\ntwo\r\n"), expected)
        self.assertEqual(prompt_stats.canonical_size(b"one\rtwo\r"), expected)

    def test_report_includes_rows_and_total(self) -> None:
        report = prompt_stats.render_report([("AGENTS.md", 8, 2)])
        self.assertIn("| `AGENTS.md` | 8 | 2 |", report)
        self.assertIn("| **Total** | **8** | **2** |", report)

    def test_budget_boundary_is_explicit(self) -> None:
        self.assertTrue(prompt_stats.within_budget([("a", 4, 2)], limit=2))
        self.assertFalse(prompt_stats.within_budget([("a", 4, 3)], limit=2))


if __name__ == "__main__":
    unittest.main()
