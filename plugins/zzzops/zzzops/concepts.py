"""Validate and resolve progressively disclosed ZzzOps concept references."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path, PurePosixPath
import re
from typing import Iterable


CONCEPT_BLOCK = re.compile(
    r"<!-- zzzops-concept\s*\n(\{.*?\})\s*\nzzzops-concept -->",
    re.DOTALL,
)
CONCEPT_LINK = re.compile(r"\[\[([^\]\r\n]+)\]\]\(([^)\r\n]+)\)")
CONCEPT_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
METADATA_FIELDS = {"aliases", "authority", "id", "schema_version", "term"}
REQUIRED_SECTIONS = (
    "Meaning",
    "Decision rule",
    "Scope and authority",
    "Examples",
    "Counterexamples",
    "Parameters and invariants",
    "Aliases and related concepts",
    "Compatibility",
)
INFORMATIONAL_AUTHORITY = "informational-only"


class ConceptError(ValueError):
    """A concept definition or document binding is unsafe or ambiguous."""


@dataclass(frozen=True)
class ConceptDefinition:
    identifier: str
    term: str
    aliases: tuple[str, ...]
    authority: str
    path: Path
    text: str

    @property
    def terms(self) -> tuple[str, ...]:
        return (self.term, *self.aliases)


@dataclass(frozen=True)
class ConceptCatalog:
    by_id: dict[str, ConceptDefinition]
    by_term: dict[str, ConceptDefinition]


@dataclass(frozen=True)
class ConceptLink:
    display: str
    target: str
    display_start: int
    definition: ConceptDefinition


def normalize_term(value: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or "\n" in value or "\r" in value:
        raise ConceptError("concept terms must be non-empty single-line text without surrounding whitespace")
    return value.casefold()


def _section_content(text: str) -> dict[str, str]:
    matches = list(re.finditer(r"(?m)^## ([^\r\n]+)\s*$", text))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        name = match.group(1).strip()
        if name in sections:
            raise ConceptError(f"duplicate concept section: {name}")
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections[name] = text[match.end():end].strip()
    missing = [name for name in REQUIRED_SECTIONS if not sections.get(name)]
    if missing:
        raise ConceptError("missing or empty concept sections: " + ", ".join(missing))
    return sections


def parse_definition(path: Path) -> ConceptDefinition:
    path = path.resolve()
    try:
        text = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    except (OSError, UnicodeError) as exc:
        raise ConceptError(f"could not read concept definition {path.name}: {type(exc).__name__}") from exc
    matches = list(CONCEPT_BLOCK.finditer(text))
    if len(matches) != 1:
        raise ConceptError(f"{path.name} must contain exactly one zzzops-concept metadata block")
    try:
        metadata = json.loads(matches[0].group(1))
    except json.JSONDecodeError as exc:
        raise ConceptError(f"{path.name} concept metadata is invalid JSON") from exc
    if not isinstance(metadata, dict) or set(metadata) != METADATA_FIELDS:
        raise ConceptError(f"{path.name} concept metadata fields do not match the schema")
    if metadata.get("schema_version") != 1:
        raise ConceptError(f"{path.name} concept schema_version must be 1")
    identifier = metadata.get("id")
    if not isinstance(identifier, str) or not CONCEPT_ID.fullmatch(identifier) or path.name != f"{identifier}.md":
        raise ConceptError(f"{path.name} must match its lowercase hyphenated concept id")
    term = metadata.get("term")
    normalized_term = normalize_term(term)
    aliases = metadata.get("aliases")
    if not isinstance(aliases, list) or any(not isinstance(alias, str) for alias in aliases):
        raise ConceptError(f"{path.name} aliases must be a list of terms")
    normalized_aliases = [normalize_term(alias) for alias in aliases]
    if len(set(normalized_aliases)) != len(normalized_aliases) or normalized_term in normalized_aliases:
        raise ConceptError(f"{path.name} aliases must be unique and differ from the canonical term")
    authority = metadata.get("authority")
    if authority != INFORMATIONAL_AUTHORITY:
        raise ConceptError(f"{path.name} concepts must be informational-only and grant no authority")
    title = re.search(r"(?m)^# ([^\r\n]+)\s*$", text)
    if title is None or normalize_term(title.group(1).strip()) != normalized_term:
        raise ConceptError(f"{path.name} H1 must equal its canonical term")
    sections = _section_content(text)
    authority_text = sections["Scope and authority"].casefold()
    if "grants no authority" not in authority_text or "cannot weaken" not in authority_text:
        raise ConceptError(f"{path.name} must state that it grants no authority and cannot weaken higher authority")
    return ConceptDefinition(
        identifier=identifier,
        term=term,
        aliases=tuple(aliases),
        authority=authority,
        path=path,
        text=text,
    )


def load_catalog(roots: Iterable[Path], *, require_concepts: bool = False) -> ConceptCatalog:
    definitions: list[ConceptDefinition] = []
    for root in roots:
        resolved = root.resolve()
        if not resolved.exists():
            continue
        if not resolved.is_dir():
            raise ConceptError(f"concept root is not a directory: {resolved}")
        definitions.extend(parse_definition(path) for path in sorted(resolved.glob("*.md")))
    if require_concepts and not definitions:
        raise ConceptError("concept catalog contains no definitions")
    by_id: dict[str, ConceptDefinition] = {}
    by_term: dict[str, ConceptDefinition] = {}
    for definition in definitions:
        if definition.identifier in by_id:
            raise ConceptError(f"duplicate concept id: {definition.identifier}")
        by_id[definition.identifier] = definition
        for term in definition.terms:
            normalized = normalize_term(term)
            existing = by_term.get(normalized)
            if existing is not None:
                raise ConceptError(
                    f"concept term or alias {term!r} conflicts between {existing.identifier} and {definition.identifier}"
                )
            by_term[normalized] = definition
    return ConceptCatalog(by_id=by_id, by_term=by_term)


def _allowed_target(document: Path, target: str, roots: Iterable[Path]) -> Path:
    if "\\" in target or "?" in target or "#" in target:
        raise ConceptError(f"concept target must be a plain relative Markdown path: {target}")
    relative = PurePosixPath(target)
    if relative.is_absolute() or relative.suffix.casefold() != ".md":
        raise ConceptError(f"concept target must be a relative Markdown path: {target}")
    resolved = document.parent.joinpath(*relative.parts).resolve()
    allowed = [root.resolve() for root in roots]
    if not any(resolved.is_relative_to(root) for root in allowed):
        raise ConceptError(f"concept target escapes an allowed concept root: {target}")
    return resolved


def concept_links(document: Path, catalog: ConceptCatalog, roots: Iterable[Path]) -> list[ConceptLink]:
    document = document.resolve()
    try:
        text = document.read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    except (OSError, UnicodeError) as exc:
        raise ConceptError(f"could not read concept-bearing document {document.name}: {type(exc).__name__}") from exc
    definitions_by_path = {definition.path: definition for definition in catalog.by_id.values()}
    links: list[ConceptLink] = []
    seen: dict[str, Path] = {}
    for match in CONCEPT_LINK.finditer(text):
        display, target = match.groups()
        normalized = normalize_term(display)
        resolved = _allowed_target(document, target, roots)
        definition = definitions_by_path.get(resolved)
        if definition is None:
            raise ConceptError(f"concept target is missing or not catalogued: {target}")
        if catalog.by_term.get(normalized) != definition:
            raise ConceptError(f"concept label {display!r} is not declared by {definition.identifier}")
        prior = seen.get(normalized)
        if prior is not None:
            detail = "conflicting" if prior != resolved else "repeated"
            raise ConceptError(f"{detail} concept binding for {display!r} in {document.name}")
        seen[normalized] = resolved
        links.append(ConceptLink(display, target, match.start(1), definition))
    return links


def _first_exact_occurrence(text: str, term: str) -> int | None:
    pattern = re.compile(rf"(?<![\w-]){re.escape(term)}(?![\w-])", re.IGNORECASE)
    match = pattern.search(text)
    return None if match is None else match.start()


def validate_document(document: Path, catalog: ConceptCatalog, roots: Iterable[Path]) -> list[ConceptLink]:
    document = document.resolve()
    text = document.read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    links = concept_links(document, catalog, roots)
    linked_positions = {normalize_term(link.display): link.display_start for link in links}
    for normalized, definition in catalog.by_term.items():
        display = next(term for term in definition.terms if normalize_term(term) == normalized)
        first = _first_exact_occurrence(text, display)
        if first is None:
            continue
        if linked_positions.get(normalized) != first:
            raise ConceptError(
                f"first occurrence of concept term or alias {display!r} in {document.name} must be its concept link"
            )
    return links


def validate_skill_documents(plugin_root: Path, catalog: ConceptCatalog) -> None:
    roots = (plugin_root / "concepts",)
    for document in sorted((plugin_root / "skills").glob("**/*.md")):
        validate_document(document, catalog, roots)


def resolve_document_concepts(document: Path, roots: Iterable[Path]) -> list[ConceptDefinition]:
    """Load only definitions explicitly linked by one document; do not traverse related concepts."""
    document = document.resolve()
    resolved: list[ConceptDefinition] = []
    seen: set[Path] = set()
    text = document.read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    for match in CONCEPT_LINK.finditer(text):
        target = _allowed_target(document, match.group(2), roots)
        if target not in seen:
            definition = parse_definition(target)
            if normalize_term(match.group(1)) not in {normalize_term(term) for term in definition.terms}:
                raise ConceptError(f"concept label {match.group(1)!r} is not declared by {definition.identifier}")
            resolved.append(definition)
            seen.add(target)
    return resolved
