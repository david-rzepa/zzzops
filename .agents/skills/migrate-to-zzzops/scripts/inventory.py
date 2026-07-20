"""Read-only, section-aware TODO inventory for agent-led migration."""

from __future__ import annotations

import difflib
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

SCHEMA_VERSION = 2
SKIP_DIRS = {
    ".git", ".agents", ".claude", ".codex", ".zzzops", "node_modules",
    "vendor", "dist", "build", "out", "target", "bin", "obj",
    ".cache", ".venv", "venv", "__pycache__", "Library", "Temp",
}
TEXT_SUFFIXES = {
    "", ".c", ".cc", ".cpp", ".cs", ".css", ".go", ".h", ".hpp", ".html",
    ".java", ".js", ".jsx", ".json", ".kt", ".lua", ".md", ".mdx", ".php",
    ".ps1", ".py", ".rb", ".rs", ".rst", ".sh", ".sql", ".toml", ".ts",
    ".tsx", ".txt", ".xml", ".yaml", ".yml",
}
BACKLOG_STEMS = {"todo", "todos", "backlog", "roadmap", "tasks", "pending", "work-items", "work_items"}
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
MARKER = re.compile(r"(?i)(?:#|//|/\*|<!--|--|;|\*)\s*(?:TODO|TO\s+DO|FIXME|HACK|XXX)\b[:\s-]*(.+)")
TASK = re.compile(r"^\s*[-*+]\s*\[\s\]\s+(.+)")
LIST = re.compile(r"^\s*[-*+]\s+(.+)")
COMPLETION = re.compile(r"(?i)\b(?:DONE|FIXED|ANSWERED|RESOLVED|LARGELY\s+(?:DONE|FIXED|RESOLVED)|MOSTLY\s+DONE|COMPLETED|SOLVED)\b")
HISTORICAL = re.compile(r"(?i)\bhistor(?:y|ical|ically)\b")
CONDITIONAL = re.compile(r"(?i)\b(?:once\b[^.;]{0,160}\blands?|only\s+after|after\b[^.;]{0,160}\blands?|until\b[^.;]{0,160})\b")
KNOWN_DEFECT = re.compile(r"(?i)\b(?:known\s+defect|not\s+fixed|unfixed|unverified|unresolved|unexplained|missing|hazard|caveat|issue|still\s+(?:broken|fails?|never)|active\s+defect)\b")
DECISION = re.compile(r"(?i)\b(?:decide|decision|determine|to\s+determine|whether\b|choose\b|consider\b)\b")
BLOCKED = re.compile(r"(?i)\b(?:parked|deferred|disabled|blocked|blocker|redesign|planned)\b")
EXPLICIT = re.compile(r"(?i)\b(?:TODO|TO\s+DO|FIXME|HACK|XXX|remaining|outstanding)\b")
FOLLOW_UP = re.compile(r"(?i)\b(?:follow[- ]?ups?|needs?|should|must|worth\s+re-?checking|audit|verify|rebuild|split|wire|tune|pick|finish|add|remove)\b")
DEPENDENCY = re.compile(r"(?i)(?:\bonce\b[^.;]*|\bonly\s+after\b[^.;]*|\bafter\b[^.;]*\blands?\b[^.;]*|\buntil\b[^.;]*|\bdepends?\s+on\b[^.;]*|\bblocker\s*=\s*[^.;]*)")
INLINE_NUMBERED = re.compile(r"\((\d+)\)\s*(.*?)(?=(?:;|\.)?\s*\(\d+\)\s*|$)")
STOP_WORDS = {"a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from", "in", "is", "it", "of", "on", "or", "that", "the", "this", "to", "was", "with", "not", "still", "todo", "follow", "up", "outstanding", "remaining"}


@dataclass
class Heading:
    level: int
    title: str
    line: int


@dataclass
class Section:
    hierarchy: list[Heading]
    start: int
    end: int

    @property
    def heading(self) -> Heading:
        return self.hierarchy[-1]


def normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def heading_identity(hierarchy: list[Heading]) -> str:
    identities = []
    status_suffix = re.compile(
        r"(?i)\s*(?:--|:)\s*(?:largely\s+resolved|mostly\s+done|done|fixed|answered|resolved|completed|solved|parked)\b.*$"
    )
    for item in hierarchy:
        title = re.sub(r"(?i)^\(?historical\)?\s*", "", item.title).strip()
        identities.append(normalized(status_suffix.sub("", title)))
    return " / ".join(identities)


def fingerprint(path: str, hierarchy: list[Heading], text: str, occurrence: int) -> str:
    identity = f"{path.casefold()}\0{heading_identity(hierarchy)}\0{normalized(text)}\0{occurrence}"
    return hashlib.sha256(identity.encode()).hexdigest()


def parse_sections(lines: list[str]) -> list[Section]:
    stack: list[Heading] = []
    starts: list[tuple[int, list[Heading]]] = []
    for number, line in enumerate(lines, 1):
        match = HEADING.match(line)
        if not match:
            continue
        level = len(match.group(1))
        stack = [item for item in stack if item.level < level]
        stack.append(Heading(level, match.group(2).strip(), number))
        starts.append((number, list(stack)))
    sections = []
    for index, (start, hierarchy) in enumerate(starts):
        end = len(lines)
        for later_start, later_hierarchy in starts[index + 1:]:
            if later_hierarchy[-1].level <= hierarchy[-1].level:
                end = later_start - 1
                break
        sections.append(Section(hierarchy, start, end))
    return sections


def direct_blocks(lines: list[str], section: Section) -> list[tuple[int, int, list[str]]]:
    """Return paragraphs/list items owned by this section, excluding subsections."""
    blocks: list[tuple[int, int, list[str]]] = []
    current: list[str] = []
    current_start = 0
    index = section.start + 1
    while index <= section.end:
        line = lines[index - 1]
        heading = HEADING.match(line)
        if heading and len(heading.group(1)) > section.heading.level:
            if current:
                blocks.append((current_start, index - 1, current))
                current = []
            nested_level = len(heading.group(1))
            index += 1
            while index <= section.end:
                later = HEADING.match(lines[index - 1])
                if later and len(later.group(1)) <= nested_level:
                    break
                index += 1
            continue
        if not line.strip():
            if current:
                blocks.append((current_start, index - 1, current))
                current = []
            index += 1
            continue
        if re.match(r"^\s*[-*+]\s+", line) and current:
            blocks.append((current_start, index - 1, current))
            current = []
        if not current:
            current_start = index
        current.append(line)
        index += 1
    if current:
        blocks.append((current_start, section.end, current))
    return blocks


def classify(text: str, historical: bool = False) -> tuple[str | None, str | None]:
    dependency_match = DEPENDENCY.search(text)
    dependency = dependency_match.group(0).strip() if dependency_match else None
    if CONDITIONAL.search(text):
        return "conditional_follow_up", dependency
    if KNOWN_DEFECT.search(text):
        return "known_defect", dependency
    if DECISION.search(text):
        return "decision_needed", dependency
    if BLOCKED.search(text):
        return "blocked_or_parked", dependency
    if EXPLICIT.search(text):
        return "explicit_open", dependency
    if not historical and FOLLOW_UP.search(text):
        return "follow_up", dependency
    return None, dependency


def candidate_confidence(candidate_type: str, zero_match: bool = False) -> str:
    if zero_match or candidate_type in {"conditional_follow_up", "historical_context"}:
        return "low"
    if candidate_type in {"follow_up", "blocked_or_parked", "decision_needed", "completion_claim"}:
        return "medium"
    return "high"


def candidate_texts(block_text: str, candidate_type: str) -> list[str]:
    numbered = list(INLINE_NUMBERED.finditer(block_text))
    if candidate_type in {"explicit_open", "follow_up"} and len(numbered) > 1:
        results = []
        for match in numbered:
            text = re.split(r"(?i)\s+Original note below\.?", match.group(2), maxsplit=1)[0].strip(" ;.")
            if text:
                results.append(text)
        return results
    match = TASK.match(block_text) or MARKER.search(block_text) or LIST.match(block_text)
    if match:
        return [re.sub(r"\s+", " ", match.group(1)).strip()[:1000]]
    patterns = {
        "conditional_follow_up": CONDITIONAL,
        "known_defect": KNOWN_DEFECT,
        "decision_needed": DECISION,
        "blocked_or_parked": BLOCKED,
        "explicit_open": EXPLICIT,
        "follow_up": FOLLOW_UP,
    }
    sentences = re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", block_text).strip())
    pattern = patterns.get(candidate_type)
    if pattern:
        selected = [sentence for sentence in sentences if pattern.search(sentence)]
        if selected:
            if candidate_type in {"known_defect", "decision_needed", "conditional_follow_up"}:
                return [sentence[:1000] for sentence in selected]
            return [" ".join(selected)[:1000]]
    return [re.sub(r"\s+", " ", block_text).strip()[:1000]]


def section_data(section: Section) -> dict:
    return {
        "heading": section.heading.title,
        "line": section.heading.line,
        "hierarchy": [{"heading": item.title, "line": item.line, "level": item.level} for item in section.hierarchy],
    }


def source_line(start: int, block_lines: list[str], text: str) -> int:
    words = [word for word in re.findall(r"[a-z0-9_]+", normalized(text)) if word not in STOP_WORDS]
    if not words:
        return start
    for width in range(min(3, len(words)), 0, -1):
        for offset, line in enumerate(block_lines):
            line_text = normalized(line)
            if all(word in line_text for word in words[:width]):
                return start + offset
    return start


def make_candidate(
    relative: str, dedicated: bool, migrated: set[str], counts: dict, section: Section,
    line: int, text: str, candidate_type: str, evidence: list[dict], context: str,
    enclosing: str | None = None, dependency: str | None = None, review_reason: str | None = None,
) -> dict:
    key = (relative.casefold(), heading_identity(section.hierarchy), normalized(text))
    counts[key] = counts.get(key, 0) + 1
    item_fingerprint = fingerprint(relative, section.hierarchy, text, counts[key])
    return {
        "path": relative, "line": line, "text": text, "dedicated_backlog": dedicated,
        "fingerprint": item_fingerprint, "already_migrated": item_fingerprint in migrated,
        "candidate_type": candidate_type,
        "confidence": candidate_confidence(candidate_type, review_reason == "open_section_without_line_match"),
        "section": section_data(section), "evidence": evidence, "context": context[:2000],
        "enclosing_completion_claim": enclosing, "possible_dependency": dependency,
        "review_reason": review_reason, "possible_same_outcome": [],
    }


def inventory_markdown(relative: str, lines: list[str], dedicated: bool, migrated: set[str]) -> list[dict]:
    found: list[dict] = []
    counts: dict[tuple[str, str, str], int] = {}
    for section in parse_sections(lines):
        heading = section.heading
        completed = bool(COMPLETION.search(heading.title))
        historical = bool(HISTORICAL.search(heading.title))
        enclosing = heading.title if completed else next(
            (item.title for item in reversed(section.hierarchy[:-1]) if COMPLETION.search(item.title)), None,
        )
        matched_blocks = 0
        if completed or historical or BLOCKED.search(heading.title):
            candidate_type = "historical_context" if historical else ("completion_claim" if completed else "blocked_or_parked")
            found.append(make_candidate(
                relative, dedicated, migrated, counts, section, heading.line, heading.title, candidate_type,
                [{"line": heading.line, "text": lines[heading.line - 1]}], lines[heading.line - 1], enclosing,
            ))
        for start, end, block_lines in direct_blocks(lines, section):
            raw_text = " ".join(line.strip() for line in block_lines)
            candidate_type, dependency = classify(normalized(raw_text), historical)
            if not candidate_type and TASK.match(block_lines[0]):
                candidate_type = "explicit_open"
            if not candidate_type and dedicated and LIST.match(block_lines[0]):
                checked = bool(re.match(r"^\s*[-*+]\s*\[[xX]\]", block_lines[0]))
                candidate_type = "completion_claim" if checked or COMPLETION.search(raw_text) else "explicit_open"
            if not candidate_type:
                continue
            matched_blocks += 1
            evidence = [{"line": number, "text": lines[number - 1]} for number in range(start, end + 1)]
            for text in candidate_texts(raw_text, candidate_type):
                found.append(make_candidate(
                    relative, dedicated, migrated, counts, section, source_line(start, block_lines, text), text, candidate_type,
                    evidence, "\n".join(block_lines), enclosing, dependency,
                ))
        if dedicated and not completed and not historical and matched_blocks == 0:
            blocks = direct_blocks(lines, section)
            if blocks:
                start, end, block_lines = blocks[0]
                found.append(make_candidate(
                    relative, dedicated, migrated, counts, section, heading.line, heading.title, "explicit_open",
                    [{"line": number, "text": lines[number - 1]} for number in range(start, end + 1)],
                    "\n".join(block_lines), enclosing, review_reason="open_section_without_line_match",
                ))
    return found


def inventory_plain(relative: str, lines: list[str], dedicated: bool, migrated: set[str]) -> list[dict]:
    found, counts = [], {}
    for number, line in enumerate(lines, 1):
        match = TASK.match(line) or MARKER.search(line) or (LIST.match(line) if dedicated else None)
        if not match:
            continue
        text = re.sub(r"\s+", " ", match.group(1)).strip()[:500]
        if not text:
            continue
        key = (relative.casefold(), normalized(text))
        counts[key] = counts.get(key, 0) + 1
        item_fingerprint = fingerprint(relative, [], text, counts[key])
        candidate_type, dependency = classify(text)
        candidate_type = candidate_type or "explicit_open"
        found.append({
            "path": relative, "line": number, "text": text, "dedicated_backlog": dedicated,
            "fingerprint": item_fingerprint, "already_migrated": item_fingerprint in migrated,
            "candidate_type": candidate_type, "confidence": candidate_confidence(candidate_type), "section": None,
            "evidence": [{"line": number, "text": line}], "context": line,
            "enclosing_completion_claim": None, "possible_dependency": dependency,
            "review_reason": None, "possible_same_outcome": [],
        })
    return found


def duplicate_groups(candidates: list[dict]) -> list[dict]:
    def tokens(text: str) -> set[str]:
        return {token for token in re.findall(r"[a-z0-9_]+", normalized(text)) if len(token) > 2 and token not in STOP_WORDS}

    token_sets = [tokens(item["text"]) for item in candidates]
    normalized_texts = [normalized(item["text"]) for item in candidates]

    def similar(left_index: int, right_index: int) -> bool:
        left, right = candidates[left_index], candidates[right_index]
        excluded = {"completion_claim", "historical_context"}
        if left["path"] != right["path"] or left["candidate_type"] in excluded or right["candidate_type"] in excluded:
            return False
        left_tokens, right_tokens = token_sets[left_index], token_sets[right_index]
        if not left_tokens or not right_tokens:
            return False
        shared = len(left_tokens & right_tokens)
        if shared < 2:
            return False
        overlap = shared / len(left_tokens | right_tokens)
        containment = shared / min(len(left_tokens), len(right_tokens))
        if overlap >= 0.58 or containment >= 0.72:
            return True
        left_text, right_text = normalized_texts[left_index], normalized_texts[right_index]
        length_ratio = min(len(left_text), len(right_text)) / max(len(left_text), len(right_text))
        return shared >= 3 and length_ratio >= 0.65 and difflib.SequenceMatcher(None, left_text, right_text).ratio() >= 0.72

    adjacency = {index: set() for index in range(len(candidates))}
    for left in range(len(candidates)):
        for right in range(left + 1, len(candidates)):
            if similar(left, right):
                adjacency[left].add(right)
                adjacency[right].add(left)
    groups, seen = [], set()
    for start in range(len(candidates)):
        if start in seen or not adjacency[start]:
            continue
        stack, component = [start], []
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            component.append(current)
            stack.extend(adjacency[current] - seen)
        members = [candidates[index] for index in sorted(component)]
        group_id = hashlib.sha256("\0".join(sorted(item["fingerprint"] for item in members)).encode()).hexdigest()
        locations = [{"path": item["path"], "line": item["line"], "fingerprint": item["fingerprint"]} for item in members]
        groups.append({"group_id": group_id, "members": locations})
        for item in members:
            item["possible_same_outcome"] = [location for location in locations if location["fingerprint"] != item["fingerprint"]]
    return groups


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    state_path = root / ".zzzops" / "migration" / "STATE.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8-sig")) if state_path.exists() else {"items": []}
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": f"Cannot read migration state: {exc}"}))
        return 2
    migrated = {item.get("fingerprint") for item in state.get("items", []) if isinstance(item, dict)}
    try:
        listed = subprocess.run(
            ["git", "-c", f"safe.directory={root.as_posix()}", "ls-files", "-co", "--exclude-standard", "-z"],
            cwd=root, check=True, capture_output=True,
        ).stdout.decode("utf-8", errors="surrogateescape")
        paths = [root / name for name in listed.split("\0") if name and not any(part in SKIP_DIRS for part in Path(name).parts[:-1])]
    except (OSError, subprocess.CalledProcessError) as exc:
        print(json.dumps({"error": f"Cannot inventory Git repository: {type(exc).__name__}"}))
        return 2
    found = []
    for path in paths:
        try:
            if path.suffix.casefold() not in TEXT_SUFFIXES or path.stat().st_size > 2_000_000:
                continue
            relative = path.relative_to(root).as_posix()
            dedicated = path.stem.casefold() in BACKLOG_STEMS
            lines = path.read_text(encoding="utf-8-sig").splitlines()
        except (OSError, UnicodeError):
            continue
        if path.suffix.casefold() in {".md", ".mdx"} and any(HEADING.match(line) for line in lines):
            found.extend(inventory_markdown(relative, lines, dedicated, migrated))
        else:
            found.extend(inventory_plain(relative, lines, dedicated, migrated))
    groups = duplicate_groups(found)
    print(json.dumps({
        "schema_version": SCHEMA_VERSION,
        "candidate_count": len(found),
        "new_count": sum(not item["already_migrated"] for item in found),
        "candidates": found,
        "possible_same_outcome": groups,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
