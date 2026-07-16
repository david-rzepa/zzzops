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


if __name__ == "__main__":
    unittest.main()
