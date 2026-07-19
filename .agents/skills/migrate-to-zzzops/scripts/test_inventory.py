from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("inventory.py")


class InventoryTests(unittest.TestCase):
    def run_inventory(self, root: Path) -> dict:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), str(root)],
            cwd=root,
            text=True,
            encoding="utf-8",
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        return json.loads(result.stdout)

    @staticmethod
    def write(root: Path, relative: str, text: str) -> None:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def test_git_inventory_is_complete_and_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            self.write(root, ".gitignore", "ignored.md\n")
            self.write(
                root,
                "src/app.py",
                'print("ready")\n# TODO: Parse quoted values\n# TODO: Parse quoted values\n',
            )
            self.write(root, "README.md", "# Guide\n- [ ] Document setup\n- ordinary bullet\n")
            self.write(
                root,
                "TODO.md",
                "# Backlog\n- Ship CLI help\n- [ ] Add smoke probe\n- [x] Already shipped\n- [X] Also shipped\n- DONE Legacy completion marker\n",
            )
            self.write(root, "notes.md", "- ordinary note\n")
            self.write(root, "packages/app/TODO.md", "- [ ] Ship package feature\n")
            self.write(root, "goals/TODO.md", "- [ ] Review repository goals\n")
            self.write(root, ".zzzops/rules/private.md", "# TODO: machinery must be excluded\n")
            self.write(root, "ignored.md", "# TODO: ignored work must be excluded\n")
            (root / "image.png").write_bytes(b"TODO: binary-ish bytes")

            first = self.run_inventory(root)
            self.assertEqual(first["candidate_count"], 10)
            self.assertEqual(first["new_count"], 10)
            candidates = {(item["path"], item["line"]): item for item in first["candidates"]}
            expected = {
                ("src/app.py", 2): ("Parse quoted values", False),
                ("src/app.py", 3): ("Parse quoted values", False),
                ("README.md", 2): ("Document setup", False),
                ("TODO.md", 2): ("Ship CLI help", True),
                ("TODO.md", 3): ("Add smoke probe", True),
                ("TODO.md", 4): ("[x] Already shipped", True),
                ("TODO.md", 5): ("[X] Also shipped", True),
                ("TODO.md", 6): ("DONE Legacy completion marker", True),
                ("packages/app/TODO.md", 1): ("Ship package feature", True),
                ("goals/TODO.md", 1): ("Review repository goals", True),
            }
            self.assertEqual(
                {key: (item["text"], item["dedicated_backlog"]) for key, item in candidates.items()},
                expected,
            )
            self.assertNotEqual(
                candidates[("src/app.py", 2)]["fingerprint"],
                candidates[("src/app.py", 3)]["fingerprint"],
            )
            self.assertTrue(all(not item["already_migrated"] for item in first["candidates"]))

            state = root / ".zzzops" / "migration" / "STATE.json"
            state.parent.mkdir(parents=True, exist_ok=True)
            state.write_text(
                json.dumps({"items": [{"fingerprint": item["fingerprint"]} for item in first["candidates"]]}),
                encoding="utf-8",
            )
            second = self.run_inventory(root)
            self.assertEqual(second["candidate_count"], 10)
            self.assertEqual(second["new_count"], 0)
            self.assertEqual(
                [
                    (item["path"], item["line"], item["text"], item["fingerprint"])
                    for item in second["candidates"]
                ],
                [
                    (item["path"], item["line"], item["text"], item["fingerprint"])
                    for item in first["candidates"]
                ],
            )
            self.assertTrue(all(item["already_migrated"] for item in second["candidates"]))

    def test_non_git_repository_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write(root, "src/app.py", "# TODO: Repository required\n")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(root)],
                text=True,
                encoding="utf-8",
                capture_output=True,
            )
            self.assertEqual(2, result.returncode)
            self.assertIn("Cannot inventory Git repository", json.loads(result.stdout)["error"])


if __name__ == "__main__":
    unittest.main()
