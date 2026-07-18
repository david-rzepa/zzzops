import unittest
from pathlib import Path


REFERENCE = Path(__file__).parent / "skills" / "execute-zzzops" / "references" / "BRANCH_REVIEW.md"


class CanonicalIssueLinkContractTests(unittest.TestCase):
    def test_direct_and_stacked_prs_have_distinct_issue_link_semantics(self):
        text = REFERENCE.read_text(encoding="utf-8")
        self.assertIn("`Tracks #N`", text)
        self.assertIn("default-branch merges", text)
        self.assertIn("gh issue close N --reason completed", text)
        self.assertIn("Stacked or incomplete PRs never close an issue", text)


if __name__ == "__main__":
    unittest.main()
