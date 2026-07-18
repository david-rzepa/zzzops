import unittest
from pathlib import Path


ROOT = Path(__file__).parent.parent
README = ROOT / "README.md"
START = "<!-- zzzops-feature-inventory -->"
END = "<!-- /zzzops-feature-inventory -->"
REPO_MACHINERY_SKILLS = {"run-zzzops-acceptance"}
USER_FEATURE_SURFACES = {
    ".agents/zzzops.py",
    ".agents/templates/project-goals/PREFERENCES.json",
    ".github/workflows",
    ".zzzops/rules/BACKENDS.md",
}


def inventory_paths() -> list[str]:
    text = README.read_text(encoding="utf-8")
    table = text.split(START, 1)[1].split(END, 1)[0]
    return [line.split("`")[1] for line in table.splitlines() if "`" in line]


class FeatureInventoryTests(unittest.TestCase):
    def test_every_discoverable_skill_is_listed_once(self):
        paths = inventory_paths()
        skills = sorted(
            path.relative_to(ROOT).as_posix()
            for path in (ROOT / ".agents" / "skills").glob("*/SKILL.md")
            if path.parent.name not in REPO_MACHINERY_SKILLS
        )
        self.assertEqual(skills, sorted(path for path in paths if path.startswith(".agents/skills/")))

    def test_every_listed_surface_exists(self):
        for path in inventory_paths():
            self.assertTrue((ROOT / path).exists(), path)

    def test_every_user_facing_supporting_surface_is_listed(self):
        self.assertTrue(USER_FEATURE_SURFACES <= set(inventory_paths()))


if __name__ == "__main__":
    unittest.main()
