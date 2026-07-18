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
            self.write(root, "TODO.md", "# Backlog\n- Ship CLI help\n- [ ] Add smoke probe\n")
            self.write(root, "notes.md", "- ordinary note\n")
            self.write(root, ".zzzops/rules/private.md", "# TODO: machinery must be excluded\n")
            self.write(root, "goals/items/old.md", "# TODO: canonical goals must be excluded\n")
            self.write(root, "ignored.md", "# TODO: ignored work must be excluded\n")
            (root / "image.png").write_bytes(b"TODO: binary-ish bytes")

            first = self.run_inventory(root)
            self.assertEqual(first["candidate_count"], 5)
            self.assertEqual(first["new_count"], 5)
            candidates = {(item["path"], item["line"]): item for item in first["candidates"]}
            expected = {
                ("src/app.py", 2): ("Parse quoted values", False),
                ("src/app.py", 3): ("Parse quoted values", False),
                ("README.md", 2): ("Document setup", False),
                ("TODO.md", 2): ("Ship CLI help", True),
                ("TODO.md", 3): ("Add smoke probe", True),
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
            self.assertEqual(second["candidate_count"], 5)
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

    def test_non_git_fallback_skips_machinery(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write(root, "src/app.py", "# TODO: Keep fallback useful\n")
            self.write(root, ".zzzops/rules/private.md", "# TODO: exclude machinery\n")
            self.write(root, "vendor/dependency.py", "# TODO: exclude vendor\n")

            result = self.run_inventory(root)
            self.assertEqual(result["candidate_count"], 1)
            self.assertEqual(result["new_count"], 1)
            self.assertEqual(
                (result["candidates"][0]["path"], result["candidates"][0]["line"], result["candidates"][0]["text"]),
                ("src/app.py", 1, "Keep fallback useful"),
            )


if __name__ == "__main__":
    unittest.main()
