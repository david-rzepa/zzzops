import unittest
from pathlib import Path


class ContinuationContractTests(unittest.TestCase):
    def test_scoped_user_refinement_does_not_stop_execution(self):
        text = (Path(__file__).parent.parent / ".zzzops" / "rules" / "CONTINUATION.md").read_text(encoding="utf-8")
        self.assertIn("design refinement", text)
        self.assertIn("they are not replacements", text)


if __name__ == "__main__":
    unittest.main()
