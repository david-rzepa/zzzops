from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("inventory.py")


class InventoryTests(unittest.TestCase):
    maxDiff = None

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

    def test_section_hints_preserve_completion_context_and_advisory_duplicates(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            self.write(
                root,
                "TODO.md",
                """# Project work

## Earthquake v1 -- DONE
FOLLOW-UPS (not blocking): (1) drive erosion shattering from logged epicentres; (2) add corrective angular velocity; (3) expose a seismicity map.

## Climate clock -- FIXED
One remaining clock defect is not fixed: wind advection still uses the geomorphic clock.

## Completed renderer -- DONE
Once the renderer lands, tune the cloud threshold against production captures.

## Biomes -- PARKED
Blocker: decide the taxonomy before redesigning the classifier.

## Export collision metadata
The export pipeline currently drops collision metadata during transfer.

## DEM baseline
Rebuild the real-Earth DEM baseline at production resolution.

## OUTSTANDING stocktake
The real-Earth DEM baseline needs rebuilding at production resolution.

## (historical) Superseded transport -- DONE
The earlier implementation used a different clock and was replaced. This paragraph explains why.
""",
            )
            before = (root / "TODO.md").read_bytes()

            result = self.run_inventory(root)
            self.assertEqual(2, result["schema_version"])
            self.assertEqual(before, (root / "TODO.md").read_bytes())
            self.assertFalse((root / ".zzzops").exists())
            candidates = result["candidates"]

            completion = next(item for item in candidates if item["line"] == 3)
            self.assertEqual("completion_claim", completion["candidate_type"])
            earthquake = [item for item in candidates if item["section"]["heading"] == "Earthquake v1 -- DONE" and item["candidate_type"] == "follow_up"]
            self.assertEqual(3, len(earthquake))
            self.assertTrue(all(item["enclosing_completion_claim"] == "Earthquake v1 -- DONE" for item in earthquake))
            self.assertTrue(all(item["evidence"][0]["line"] == 4 for item in earthquake))

            clock = next(item for item in candidates if "wind advection" in item["text"])
            self.assertEqual("known_defect", clock["candidate_type"])
            self.assertEqual("Climate clock -- FIXED", clock["enclosing_completion_claim"])

            conditional = next(item for item in candidates if "cloud threshold" in item["text"])
            self.assertEqual("conditional_follow_up", conditional["candidate_type"])
            self.assertIsNotNone(conditional["possible_dependency"])

            parked = next(item for item in candidates if "taxonomy" in item["text"])
            self.assertEqual("decision_needed", parked["candidate_type"])
            self.assertIn("Biomes -- PARKED", parked["section"]["heading"])
            parked_heading = next(item for item in candidates if item["text"] == "Biomes -- PARKED")
            self.assertEqual("blocked_or_parked", parked_heading["candidate_type"])

            zero_match = next(item for item in candidates if item["section"]["heading"] == "Export collision metadata")
            self.assertEqual("open_section_without_line_match", zero_match["review_reason"])
            self.assertEqual("low", zero_match["confidence"])

            baseline_mentions = [item for item in candidates if "DEM baseline" in item["text"]]
            self.assertEqual(2, len(baseline_mentions))
            self.assertTrue(all(item["possible_same_outcome"] for item in baseline_mentions))
            self.assertTrue(result["possible_same_outcome"])

            historical = [item for item in candidates if "Superseded transport" in item["section"]["heading"]]
            self.assertEqual(["historical_context"], [item["candidate_type"] for item in historical])

    def test_fingerprint_is_stable_when_unrelated_candidate_is_inserted_earlier(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            original = "# Work\n\n## Target\n- [ ] Preserve this outcome\n"
            self.write(root, "TODO.md", original)
            first = self.run_inventory(root)
            target_before = next(item for item in first["candidates"] if item["text"] == "Preserve this outcome")

            self.write(root, "TODO.md", "# Work\n\n## Unrelated\n- [ ] Inserted earlier\n\n## Target\n- [ ] Preserve this outcome\n")
            second = self.run_inventory(root)
            target_after = next(item for item in second["candidates"] if item["text"] == "Preserve this outcome")
            self.assertEqual(target_before["fingerprint"], target_after["fingerprint"])


if __name__ == "__main__":
    unittest.main()
