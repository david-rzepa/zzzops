import unittest
from pathlib import Path


REFERENCE = Path(__file__).parent / "skills" / "run-zzzops-acceptance" / "SKILL.md"


class AcceptanceSkillContractTests(unittest.TestCase):
    def test_requires_explicit_same_task_check(self):
        text = REFERENCE.read_text(encoding="utf-8")
        self.assertIn("manual test", text)
        self.assertIn("acceptance test", text)
        self.assertIn("`check ID`", text)
        self.assertIn("same task", text)
        self.assertIn("Never infer an ID", text)
        self.assertIn("exactly one active item", text)
        self.assertIn("prerequisites", text)
        self.assertIn("human action", text)
        self.assertIn("expected result", text)


if __name__ == "__main__":
    unittest.main()
