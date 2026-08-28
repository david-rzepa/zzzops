from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "plugins" / "zzzops" / "zzzops" / "concepts.py"
SPEC = importlib.util.spec_from_file_location("zzzops_concepts_test", MODULE)
assert SPEC and SPEC.loader
concepts = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = concepts
SPEC.loader.exec_module(concepts)


def definition(identifier: str, term: str, aliases: list[str] | None = None) -> str:
    metadata = {
        "aliases": aliases or [],
        "authority": "informational-only",
        "id": identifier,
        "schema_version": 1,
        "term": term,
    }
    sections = {
        "Meaning": "Concise meaning.",
        "Decision rule": "Apply one observable test.",
        "Scope and authority": "This concept grants no authority and cannot weaken higher authority.",
        "Examples": "A valid example.",
        "Counterexamples": "An invalid example.",
        "Parameters and invariants": "Projects configure detail; authority is invariant.",
        "Aliases and related concepts": "No eager traversal.",
        "Compatibility": "Review material changes.",
    }
    body = "\n\n".join(f"## {name}\n\n{content}" for name, content in sections.items())
    return (
        "<!-- zzzops-concept\n" + json.dumps(metadata, sort_keys=True, separators=(",", ":"))
        + f"\nzzzops-concept -->\n\n# {term}\n\n{body}\n"
    )


class ConceptTests(unittest.TestCase):
    def test_shipped_definition_and_first_use_resolve_once(self) -> None:
        plugin = ROOT / "plugins" / "zzzops"
        catalog = concepts.load_catalog((plugin / "concepts",), require_concepts=True)
        self.assertEqual({"bounded-commitment"}, set(catalog.by_id))
        links = concepts.validate_document(
            plugin / "skills" / "execute-zzzops" / "SKILL.md", catalog, (plugin / "concepts",),
        )
        self.assertEqual(["bounded commitment"], [link.display for link in links])
        resolved = concepts.resolve_document_concepts(
            plugin / "skills" / "execute-zzzops" / "SKILL.md", (plugin / "concepts",),
        )
        self.assertEqual(["bounded-commitment"], [item.identifier for item in resolved])
        bounded = catalog.by_id["bounded-commitment"].path.read_text(encoding="utf-8")
        self.assertIn("human explicitly reviews the exact design decision", bounded)
        self.assertIn("never infer design approval from policy approval", bounded)
        self.assertIn("cannot make it low commitment", bounded)

    def test_unlinked_or_late_first_use_fails_but_later_plain_use_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            concepts_root = root / "concepts"
            skills = root / "skills" / "example"
            concepts_root.mkdir()
            skills.mkdir(parents=True)
            (concepts_root / "bounded-commitment.md").write_text(
                definition("bounded-commitment", "bounded commitment"), encoding="utf-8",
            )
            catalog = concepts.load_catalog((concepts_root,), require_concepts=True)
            skill = skills / "SKILL.md"
            skill.write_text("A bounded commitment is useful.\n", encoding="utf-8")
            with self.assertRaisesRegex(concepts.ConceptError, "first occurrence"):
                concepts.validate_document(skill, catalog, (concepts_root,))
            skill.write_text(
                "A [[bounded commitment]](../../concepts/bounded-commitment.md) is useful. "
                "The BOUNDED COMMITMENT remains local.\n",
                encoding="utf-8",
            )
            self.assertEqual(1, len(concepts.validate_document(skill, catalog, (concepts_root,))))

    def test_declared_alias_needs_its_own_first_use_binding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            concepts_root = root / "concepts"
            concepts_root.mkdir()
            path = concepts_root / "bounded-commitment.md"
            path.write_text(definition("bounded-commitment", "bounded commitment", ["bounded change"]), encoding="utf-8")
            catalog = concepts.load_catalog((concepts_root,))
            document = root / "skill.md"
            document.write_text("A bounded change is useful.\n", encoding="utf-8")
            with self.assertRaisesRegex(concepts.ConceptError, "first occurrence"):
                concepts.validate_document(document, catalog, (concepts_root,))
            document.write_text("A [[bounded change]](concepts/bounded-commitment.md) is useful.\n", encoding="utf-8")
            self.assertEqual(
                "bounded-commitment",
                concepts.validate_document(document, catalog, (concepts_root,))[0].definition.identifier,
            )

    def test_catalog_rejects_conflicts_and_malformed_authority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "one.md").write_text(definition("one", "shared term"), encoding="utf-8")
            (root / "two.md").write_text(definition("two", "other term", ["shared term"]), encoding="utf-8")
            with self.assertRaisesRegex(concepts.ConceptError, "conflicts"):
                concepts.load_catalog((root,))
            unsafe = definition("one", "shared term").replace('"informational-only"', '"policy-override"')
            (root / "one.md").write_text(unsafe, encoding="utf-8")
            (root / "two.md").unlink()
            with self.assertRaisesRegex(concepts.ConceptError, "grant no authority"):
                concepts.load_catalog((root,))

    def test_project_and_packaged_targets_are_explicit_and_duplicate_ids_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            packaged = root / "plugin" / "concepts"
            project = root / ".zzzops" / "concepts"
            packaged.mkdir(parents=True)
            project.mkdir(parents=True)
            (packaged / "packaged-term.md").write_text(
                definition("packaged-term", "packaged term"), encoding="utf-8",
            )
            (project / "project-term.md").write_text(
                definition("project-term", "project term"), encoding="utf-8",
            )
            catalog = concepts.load_catalog((packaged, project))
            document = root / "guidance.md"
            document.write_text(
                "[[packaged term]](plugin/concepts/packaged-term.md) and "
                "[[project term]](.zzzops/concepts/project-term.md)\n",
                encoding="utf-8",
            )
            self.assertEqual(2, len(concepts.validate_document(document, catalog, (packaged, project))))
            (project / "packaged-term.md").write_text(
                definition("packaged-term", "shadow term"), encoding="utf-8",
            )
            with self.assertRaisesRegex(concepts.ConceptError, "duplicate concept id"):
                concepts.load_catalog((packaged, project))

    def test_definition_requires_every_operational_section(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "incomplete.md"
            path.write_text(
                definition("incomplete", "incomplete concept").replace(
                    "## Counterexamples\n\nAn invalid example.\n\n", "",
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(concepts.ConceptError, "Counterexamples"):
                concepts.parse_definition(path)

    def test_missing_target_traversal_and_repeated_binding_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            concepts_root = root / "concepts"
            concepts_root.mkdir()
            (concepts_root / "bounded-commitment.md").write_text(
                definition("bounded-commitment", "bounded commitment"), encoding="utf-8",
            )
            catalog = concepts.load_catalog((concepts_root,))
            document = root / "skill.md"
            document.write_text("[[bounded commitment]](missing.md)\n", encoding="utf-8")
            with self.assertRaisesRegex(concepts.ConceptError, "escapes|missing"):
                concepts.validate_document(document, catalog, (concepts_root,))
            document.write_text("[[bounded commitment]](../escape.md)\n", encoding="utf-8")
            with self.assertRaisesRegex(concepts.ConceptError, "escapes"):
                concepts.validate_document(document, catalog, (concepts_root,))
            document.write_text(
                "[[bounded commitment]](concepts/bounded-commitment.md) and "
                "[[bounded commitment]](concepts/bounded-commitment.md)\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(concepts.ConceptError, "repeated"):
                concepts.validate_document(document, catalog, (concepts_root,))

    def test_related_concepts_are_not_eagerly_resolved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            concepts_root = root / "concepts"
            concepts_root.mkdir()
            first = definition("first", "first concept").replace(
                "No eager traversal.", "See [[missing concept]](missing.md), but do not traverse it.",
            )
            (concepts_root / "first.md").write_text(first, encoding="utf-8")
            document = root / "skill.md"
            document.write_text("[[first concept]](concepts/first.md)\n", encoding="utf-8")
            resolved = concepts.resolve_document_concepts(document, (concepts_root,))
            self.assertEqual(["first"], [item.identifier for item in resolved])


if __name__ == "__main__":
    unittest.main()
