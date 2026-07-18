import unittest
from pathlib import Path


REFERENCE = Path(__file__).parent / "skills" / "execute-zzzops" / "references" / "BRANCH_REVIEW.md"


class CanonicalIssueLinkContractTests(unittest.TestCase):
    def test_direct_and_stacked_prs_have_distinct_issue_link_semantics(self):
        text = REFERENCE.read_text(encoding="utf-8")
        self.assertIn("`Closes #N`", text)
        self.assertIn("`Tracks #N`", text)
        self.assertIn("must not close its issue early", text)
        self.assertIn("later verify it closed", text)


if __name__ == "__main__":
    unittest.main()
