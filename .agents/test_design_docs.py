"""The engine contract lives in docs/design/ (G1017).

These tests keep the moved DESIGN, SPEC, IMPLEMENTATION_PLAN, HISTORY and
README honest: no private data or external-folder paths, links and cited
section numbers resolve, every cited amendment id is indexed, and the README's
pending-amendments table never lists a goal whose code has already landed
(`test_no_landed_goal_is_pending`, the guard).

Pending-table format (docs/design/README.md):

    | Goal | Sections | Landed when |
    |---|---|---|
    | G1024 | SPEC §3.2 | `plugins/zzzops/zzzops/engine contains "policy_update"` |

The marker is `<path> contains|lacks "<JSON string>"`. The path is a tracked
file or a directory; a directory matches `contains` when any tracked file under
it (recursively) contains the string, and `lacks` when none does.

Standard library only.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs" / "design"
DOCUMENTS = ("README.md", "DESIGN.md", "SPEC.md", "IMPLEMENTATION_PLAN.md", "HISTORY.md")
THIS_FILE = ".agents/test_design_docs.py"
CONTRACT_GOAL = 1017

# Built by concatenation so that this file does not match itself.
EXTERNAL_FOLDER = "zzzops-design-" + "reset"
LOCAL_PATH_PREFIXES = ("/" + "home/", "/" + "Users/", "/" + "tmp/")
PRIVATE_PATTERNS = (
    re.compile("Rze" + "pa"),
    re.compile(r"\b" + "Da" + r"vid\b"),
    re.compile("claude-" + "1000"),
    # The source documents' example session prefixes (design: privacy scrub 3).
    re.compile(r"\b(?:" + "|".join(("7f3e" + "9a10", "9c1d" + "4e7a", "9c" + "1d", "c9" + "0b", "77" + "e0")) + r")\b"),
)

# Goals merged before G1017's base whose contract change G1017 applies (case 1),
# with their PRs. #742 (`--policy-ref`) has no goal of its own.
MERGED_AMENDMENTS = {
    "G1014": "#743", "G1018": "#744", "G1001": "#745", "G1015": "#746",
    "G1016": "#747", "G1000": "#748", "G1021": "#749", "G1020": "#750",
}
UNGOALED_AMENDMENT_PRS = ("#742",)

# One sentinel per applied amendment: contract terms the amendment introduced
# and that the approved revision 6.3 lacks, so the HISTORY row alone cannot
# pass. Keyed by goal (or PR); a later goal that legitimately renames a term
# updates its entry here. Each term must appear in the named document.
AMENDMENT_SENTINELS = {
    "#742": [("SPEC.md", "--policy-ref")],
    "G1001": [("SPEC.md", "request_key"), ("SPEC.md", "Request-Key:")],
    "G1014": [("SPEC.md", "inputs_changed")],
    "G1015": [("SPEC.md", "legacy_policy"), ("SPEC.md", "settings.legacy")],
    "G1016": [("SPEC.md", "no_longer_live"), ("SPEC.md", "respond_to")],
    # G1018's card shrink steps (SPEC §4.20); rev 6.3 SPEC never says "shrink".
    "G1018": [("SPEC.md", "shrink")],
    # G1021's 15-minute no-checks human question (SPEC §5.4).
    "G1021": [("SPEC.md", "no checks appeared")],
    "G1000": [("SPEC.md", "filter_design"), ("DESIGN.md", "filter_design")],
    "G1020": [("SPEC.md", "approved with")],
    # G1022's skip key form (SPEC §3.3) and the separate design Adversary's rationale (DESIGN §3.8).
    "G1022": [("SPEC.md", "<node>:<lens>"), ("DESIGN.md", "adversary_design")],
    # G1023's wording, folded under G1016's row (SPEC §4.20 hint, §3.10 example).
    "G1023": [("SPEC.md", "<full 40-hex sha>")],
}

# Case-3 goals whose contract sections are known (design revision 3, plus the
# root's note for G1025): each has a pending row with this marker path until
# it lands, and a HISTORY §4 row after. G1026-G1028 also depend on G1017 but
# their sections are not known yet, so they need no row.
REQUIRED_PENDING = {
    1022: "plugins/zzzops/zzzops/templates/default/workflow.json",
    1024: "plugins/zzzops/zzzops/engine",
    1025: "plugins/zzzops/zzzops/engine",
}


# ---------------------------------------------------------------- helpers

class PendingTableError(ValueError):
    """The README's pending table, or one of its rows, cannot be parsed."""


@dataclass(frozen=True)
class PendingRow:
    goal: int
    sections: str
    path: str
    op: str
    needle: str
    line: int


TABLE_HEADER = re.compile(r"^\|\s*Goal\s*\|\s*Sections\s*\|\s*Landed when\s*\|\s*$")
TABLE_SEPARATOR = re.compile(r"^\|(?:\s*:?-{3,}:?\s*\|){3}\s*$")
GOAL_CELL = re.compile(r"^G(\d+)(?:\s.*)?$")
MARKER = re.compile(r'^(?P<path>[^\s"]+) (?P<op>contains|lacks) (?P<needle>"(?:[^"\\]|\\.)*")$')


def _cells(line: str) -> list[str]:
    body = line.strip()
    if not (body.startswith("|") and body.endswith("|")) or len(body) < 2:
        raise PendingTableError(f"not a table row: {line!r}")
    parts = re.split(r"(?<!\\)\|", body[1:-1])
    return [part.strip().replace("\\|", "|") for part in parts]


def parse_marker(cell: str, line: int) -> tuple[str, str, str]:
    spans = re.findall(r"`([^`]+)`", cell)
    if len(spans) != 1:
        raise PendingTableError(f"line {line}: 'Landed when' needs exactly one `marker`, got {cell!r}")
    match = MARKER.match(spans[0])
    if not match:
        raise PendingTableError(f"line {line}: marker must be '<path> contains|lacks \"<string>\"', got {spans[0]!r}")
    try:
        needle = json.loads(match["needle"])
    except json.JSONDecodeError as exc:
        raise PendingTableError(f"line {line}: marker string is not a valid quoted string: {exc}") from None
    path = match["path"].rstrip("/")
    if not needle:
        raise PendingTableError(f"line {line}: marker string is empty")
    if not path or path.startswith("/") or ".." in path.split("/") or "\\" in path:
        raise PendingTableError(f"line {line}: marker path must be repository-relative, got {path!r}")
    return path, match["op"], needle


def parse_pending_table(text: str) -> list[PendingRow]:
    lines = text.splitlines()
    headers = [index for index, line in enumerate(lines) if TABLE_HEADER.match(line.strip())]
    if len(headers) != 1:
        raise PendingTableError(f"expected exactly one '| Goal | Sections | Landed when |' table, found {len(headers)}")
    start = headers[0]
    if start + 1 >= len(lines) or not TABLE_SEPARATOR.match(lines[start + 1].strip()):
        raise PendingTableError(f"line {start + 2}: the pending table has no separator row")
    rows: list[PendingRow] = []
    seen: set[int] = set()
    for index in range(start + 2, len(lines)):
        raw = lines[index]
        if not raw.strip().startswith("|"):
            break
        number = index + 1
        cells = _cells(raw)
        if len(cells) != 3:
            raise PendingTableError(f"line {number}: a pending row has 3 cells, got {len(cells)}")
        goal_match = GOAL_CELL.match(cells[0])
        if not goal_match:
            raise PendingTableError(f"line {number}: the Goal cell must start with G<id>, got {cells[0]!r}")
        goal = int(goal_match[1])
        if goal in seen:
            raise PendingTableError(f"line {number}: G{goal} has more than one pending row")
        seen.add(goal)
        if not cells[1]:
            raise PendingTableError(f"line {number}: G{goal} lists no sections")
        path, op, needle = parse_marker(cells[2], number)
        rows.append(PendingRow(goal, cells[1], path, op, needle, number))
    return rows


def git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=check)


def tracked_files(root: Path) -> list[str]:
    out = git(root, "ls-files", "-z").stdout.decode("utf-8")
    return [item for item in out.split("\0") if item]


def marker_matches(root: Path, row: PendingRow, tracked: list[str]) -> bool:
    """True when the row's goal has landed in the tree at `root`."""
    if row.path in tracked:
        targets = [row.path]
    else:
        prefix = row.path + "/"
        targets = [item for item in tracked if item.startswith(prefix)]
        if not targets:
            raise PendingTableError(
                f"line {row.line}: G{row.goal}'s marker path {row.path!r} is neither a tracked file nor a directory with tracked files")
    needle = row.needle.encode("utf-8")
    found = False
    for item in targets:
        try:
            data = (root / item).read_bytes()
        except (FileNotFoundError, IsADirectoryError, NotADirectoryError):
            continue
        if needle in data:
            found = True
            break
    return found if row.op == "contains" else not found


def landed_message(goal: int) -> str:
    return (f"G{goal} has landed: apply its amendments (its design, `.zzzops/reviews/{goal}/design.md`) "
            "to docs/design, add a HISTORY §4 row, and delete this row")


def landed_rows(root: Path, text: str) -> list[str]:
    tracked = tracked_files(root)
    return [landed_message(row.goal) for row in parse_pending_table(text) if marker_matches(root, row, tracked)]


def goal_document(root: Path, goal: int) -> dict | None:
    """The goal's state from a local goal ref, or None when no such ref is present."""
    for ref in (f"refs/zzzops/goal/origin/g{goal}", f"refs/remotes/origin/zzzops/goal/g{goal}"):
        shown = git(root, "show", f"{ref}:goal.json", check=False)
        if shown.returncode == 0:
            return json.loads(shown.stdout.decode("utf-8"))
    return None


def slug(heading: str) -> str:
    text = heading.strip().lower().replace("`", "")
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def anchors(text: str) -> set[str]:
    found: set[str] = set()
    counts: dict[str, int] = {}
    in_fence = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        match = None if in_fence else re.match(r"^#{1,6}\s+(.*?)\s*#*\s*$", line)
        if match:
            base = slug(match[1])
            n = counts.get(base, 0)
            counts[base] = n + 1
            found.add(base if n == 0 else f"{base}-{n}")
    return found


def markdown_links(text: str) -> list[str]:
    stripped = re.sub(r"```.*?```", "", text, flags=re.S)
    stripped = re.sub(r"`[^`\n]*`", "", stripped)
    return re.findall(r"\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)", stripped)


def headings(text: str) -> list[str]:
    return re.findall(r"^#{1,4} (.+)$", text, flags=re.M)


def read_doc(name: str) -> str:
    path = DOCS / name
    if not path.is_file():
        raise AssertionError(f"docs/design/{name} does not exist")
    return path.read_text(encoding="utf-8")


def section(text: str, heading_pattern: str) -> str:
    """The body under the first heading matching `heading_pattern`, up to the next heading of the same or higher level."""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = re.match(r"^(#{1,6})\s+(.*)$", line)
        if match and re.search(heading_pattern, match[2], flags=re.I):
            level = len(match[1])
            body = []
            for following in lines[index + 1:]:
                deeper = re.match(r"^(#{1,6})\s", following)
                if deeper and len(deeper[1]) <= level:
                    break
                body.append(following)
            return "\n".join(body)
    raise AssertionError(f"no heading matching {heading_pattern!r}")


# ---------------------------------------------------------- guard unit tests

class PendingGuardUnitTests(unittest.TestCase):
    """The guard's parser and marker evaluation, on synthetic trees."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
        subprocess.run(["git", "init", "-q", str(self.root)], check=True, env=env, capture_output=True)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write(self, rel: str, content: str, track: bool = True) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        if track:
            git(self.root, "add", "--", rel)

    @staticmethod
    def table(*rows: str) -> str:
        return "\n".join(["# Design", "", "## Pending amendments", "",
                          "| Goal | Sections | Landed when |", "|---|---|---|", *rows, "", "Next paragraph."]) + "\n"

    def test_contains_marker_fails_when_present_and_passes_when_absent(self) -> None:
        self.write("engine/a.py", "x = 1\n")
        text = self.table('| G1024 | SPEC §3.2 | `engine/a.py contains "policy_update"` |')
        self.assertEqual([], landed_rows(self.root, text))
        self.write("engine/a.py", "kind = 'policy_update'\n")
        self.assertEqual([landed_message(1024)], landed_rows(self.root, text))

    def test_lacks_marker_works_the_other_way_round(self) -> None:
        self.write("workflow.json", '{"nodes": ["truth_design"]}\n')
        text = self.table(r'| G1022 | SPEC §7 | `workflow.json lacks "\"truth_design\""` |')
        self.assertEqual([], landed_rows(self.root, text))
        self.write("workflow.json", '{"nodes": ["design"]}\n')
        self.assertEqual([landed_message(1022)], landed_rows(self.root, text))

    def test_escaped_quotes_are_part_of_the_needle(self) -> None:
        self.write("workflow.json", '{"nodes": ["truth_design_v2"]}\n')
        text = self.table(r'| G1022 | SPEC §7 | `workflow.json lacks "\"truth_design\""` |')
        self.assertEqual([landed_message(1022)], landed_rows(self.root, text))

    def test_directory_marker_matches_through_a_file_two_levels_down(self) -> None:
        self.write("pkg/engine/__init__.py", "")
        self.write("pkg/engine/ops/git_ops.py", "pass\n")
        text = self.table('| G1025 | SPEC §5.4 | `pkg contains "git.line_sync"` |')
        self.assertEqual([], landed_rows(self.root, text))
        self.write("pkg/engine/ops/git_ops.py", "NAME = 'git.line_sync'\n")
        self.assertEqual([landed_message(1025)], landed_rows(self.root, text))

    def test_directory_lacks_marker_needs_every_file_to_lack_it(self) -> None:
        self.write("pkg/a.txt", "old_name\n")
        self.write("pkg/sub/deeper/b.txt", "old_name\n")
        text = self.table('| G1030 | DESIGN §3.8 | `pkg lacks "old_name"` |')
        self.assertEqual([], landed_rows(self.root, text))
        self.write("pkg/a.txt", "new_name\n")
        self.assertEqual([], landed_rows(self.root, text), "one file still has it")
        self.write("pkg/sub/deeper/b.txt", "new_name\n")
        self.assertEqual([landed_message(1030)], landed_rows(self.root, text))

    def test_directory_marker_ignores_untracked_files(self) -> None:
        self.write("pkg/a.py", "pass\n")
        self.write("pkg/scratch/b.py", "policy_update\n", track=False)
        text = self.table('| G1024 | SPEC §3.2 | `pkg contains "policy_update"` |')
        self.assertEqual([], landed_rows(self.root, text))

    def test_directory_marker_is_not_a_string_prefix(self) -> None:
        self.write("pkg/a.py", "pass\n")
        self.write("pkgextra/b.py", "policy_update\n")
        text = self.table('| G1024 | SPEC §3.2 | `pkg contains "policy_update"` |')
        self.assertEqual([], landed_rows(self.root, text))

    def test_trailing_slash_on_a_directory_marker_is_accepted(self) -> None:
        self.write("pkg/sub/b.py", "policy_update\n")
        text = self.table('| G1024 | SPEC §3.2 | `pkg/ contains "policy_update"` |')
        self.assertEqual([landed_message(1024)], landed_rows(self.root, text))

    def test_marker_path_that_does_not_exist_fails(self) -> None:
        self.write("engine/a.py", "pass\n")
        for op in ("contains", "lacks"):
            with self.subTest(op=op):
                text = self.table(f'| G1024 | SPEC §3.2 | `engine/typo.py {op} "x"` |')
                with self.assertRaisesRegex(PendingTableError, "neither a tracked file nor a directory"):
                    landed_rows(self.root, text)

    def test_untracked_marker_file_counts_as_missing(self) -> None:
        self.write("engine/a.py", "pass\n")
        self.write("engine/new.py", "x\n", track=False)
        text = self.table('| G1024 | SPEC §3.2 | `engine/new.py lacks "x"` |')
        with self.assertRaises(PendingTableError):
            landed_rows(self.root, text)

    def test_malformed_rows_fail_with_a_parse_error_rather_than_being_skipped(self) -> None:
        self.write("engine/a.py", "pass\n")
        bad_rows = {
            "two cells": '| G1024 | `engine/a.py contains "x"` |',
            "four cells": '| G1024 | SPEC §3.2 | `engine/a.py contains "x"` | extra |',
            "goal without G": '| 1024 | SPEC §3.2 | `engine/a.py contains "x"` |',
            "goal not a number": '| Gxyz | SPEC §3.2 | `engine/a.py contains "x"` |',
            "no sections": '| G1024 |  | `engine/a.py contains "x"` |',
            "no backticks": '| G1024 | SPEC §3.2 | engine/a.py contains "x" |',
            "two markers": '| G1024 | SPEC §3.2 | `engine/a.py contains "x"` or `engine/a.py contains "y"` |',
            "unknown operator": '| G1024 | SPEC §3.2 | `engine/a.py has "x"` |',
            "unquoted string": '| G1024 | SPEC §3.2 | `engine/a.py contains x` |',
            "empty string": '| G1024 | SPEC §3.2 | `engine/a.py contains ""` |',
            "bad escape": r'| G1024 | SPEC §3.2 | `engine/a.py contains "\q"` |',
            "absolute path": '| G1024 | SPEC §3.2 | `/engine/a.py contains "x"` |',
            "parent path": '| G1024 | SPEC §3.2 | `../engine/a.py contains "x"` |',
            "no trailing pipe": '| G1024 | SPEC §3.2 | `engine/a.py contains "x"`',
        }
        for name, row in bad_rows.items():
            with self.subTest(name):
                with self.assertRaises(PendingTableError):
                    landed_rows(self.root, self.table(row))

    def test_a_malformed_row_after_a_good_one_still_fails(self) -> None:
        self.write("engine/a.py", "pass\n")
        text = self.table('| G1024 | SPEC §3.2 | `engine/a.py contains "x"` |', "| G1025 | broken |")
        with self.assertRaises(PendingTableError):
            landed_rows(self.root, text)

    def test_duplicate_goal_rows_fail(self) -> None:
        self.write("engine/a.py", "pass\n")
        row = '| G1024 | SPEC §3.2 | `engine/a.py contains "x"` |'
        with self.assertRaisesRegex(PendingTableError, "more than one"):
            landed_rows(self.root, self.table(row, row))

    def test_missing_or_duplicated_table_fails(self) -> None:
        with self.assertRaises(PendingTableError):
            parse_pending_table("# README\n\nNo table here.\n")
        with self.assertRaises(PendingTableError):
            parse_pending_table(self.table() + self.table())
        with self.assertRaises(PendingTableError):
            parse_pending_table("| Goal | Sections | Landed when |\n| G1 | a | `x contains \"y\"` |\n")

    def test_an_empty_table_has_no_rows_and_the_table_ends_at_the_first_non_row(self) -> None:
        self.assertEqual([], parse_pending_table(self.table()))
        text = self.table('| G1024 | SPEC §3.2, §8.3 | `engine contains "x"` (directory marker) |')
        rows = parse_pending_table(text + "\n| not | part | of it |\n")
        self.assertEqual([PendingRow(1024, "SPEC §3.2, §8.3", "engine", "contains", "x", 7)], rows)

    def test_escaped_pipe_inside_a_cell(self) -> None:
        rows = parse_pending_table(self.table(r'| G1024 | SPEC §3.2 | `engine contains "a\|b"` |'))
        self.assertEqual("a|b", rows[0].needle)

    def test_goal_cell_may_carry_a_name_after_the_id(self) -> None:
        rows = parse_pending_table(self.table('| G1022 multi-lens reviewer | SPEC §7 | `w.json lacks "x"` |'))
        self.assertEqual(1022, rows[0].goal)

    def test_landed_message_names_the_goal_its_design_and_the_fix(self) -> None:
        message = landed_message(1024)
        self.assertIn("G1024 has landed", message)
        self.assertIn(".zzzops/reviews/1024/design.md", message)
        self.assertIn("HISTORY §4", message)
        self.assertIn("delete this row", message)


# ---------------------------------------------------------- real-tree tests

class DesignDocsTests(unittest.TestCase):
    """docs/design/ in this repository."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tracked = tracked_files(ROOT)

    def test_design_documents_exist_and_are_tracked(self) -> None:
        for name in DOCUMENTS:
            with self.subTest(name):
                self.assertTrue(f"docs/design/{name}" in self.tracked, f"docs/design/{name} is not tracked")
                self.assertTrue((DOCS / name).is_file())

    def test_no_landed_goal_is_pending(self) -> None:
        """The guard: a pending row whose marker matches means the goal landed without its amendment."""
        text = read_doc("README.md")
        landed = landed_rows(ROOT, text)
        self.assertEqual([], landed, "\n".join(landed))

    def test_pending_rows_belong_to_open_goals_that_depend_on_g1017(self) -> None:
        # This reads live goal state from local goal refs, so its result on a fixed
        # commit can change when a goal ref moves (for example, a stale PR re-run
        # after a pending goal closed while its tree still holds that row).
        rows = parse_pending_table(read_doc("README.md"))
        unavailable = []
        for row in rows:
            with self.subTest(goal=row.goal):
                self.assertNotEqual(CONTRACT_GOAL, row.goal, "G1017 cannot own a pending row")
                goal = goal_document(ROOT, row.goal)
                if goal is None:
                    unavailable.append(f"G{row.goal}")
                    continue
                self.assertIn(CONTRACT_GOAL, goal.get("depends_on", []),
                              f"G{row.goal} has a pending row but does not depend on G1017; "
                              "add the dependency or apply its amendment")
                self.assertEqual("open", goal.get("state"),
                                 f"G{row.goal} is {goal.get('state')!r}; a closed goal cannot be pending")
        if unavailable:
            self.skipTest("goal state not available locally (no goal refs fetched) for " + ", ".join(unavailable))

    def test_known_case_3_goals_are_pending_or_logged(self) -> None:
        rows = {row.goal: row for row in parse_pending_table(read_doc("README.md"))}
        log = section(read_doc("HISTORY.md"), r"amendments after approval")
        logged = [line for line in log.splitlines() if line.strip().startswith("|")]
        for goal, marker_path in REQUIRED_PENDING.items():
            with self.subTest(goal=goal):
                in_history = any(re.search(rf"\bG{goal}\b", line) for line in logged)
                if goal in rows:
                    self.assertFalse(in_history, f"G{goal} has both a pending row and a HISTORY §4 row")
                    self.assertEqual(marker_path, rows[goal].path, f"G{goal}'s marker path")
                else:
                    self.assertTrue(in_history, f"G{goal} needs a pending row (or, once landed, a HISTORY §4 row)")

    def test_applied_amendments_are_in_the_documents(self) -> None:
        missing = []
        for owner, terms in AMENDMENT_SENTINELS.items():
            for name, term in terms:
                if term not in read_doc(name):
                    missing.append(f"{owner}: {name} lacks {term!r}")
        self.assertEqual([], missing)

    def test_no_external_folder_or_local_paths(self) -> None:
        offenders = []
        for item in self.tracked:
            if item == THIS_FILE:
                continue
            if not (item.startswith(("plugins/", ".agents/", "docs/")) or item in ("README.md", "AGENTS.md")):
                continue
            path = ROOT / item
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
                continue
            if EXTERNAL_FOLDER in text:
                offenders.append(f"{item}: names the external design folder")
            if item.startswith("docs/design/"):
                for prefix in LOCAL_PATH_PREFIXES:
                    if prefix in text:
                        offenders.append(f"{item}: contains a local path starting {prefix}")
        self.assertTrue(DOCS.is_dir(), "docs/design does not exist")
        self.assertEqual([], offenders)

    def test_private_data_is_scrubbed(self) -> None:
        offenders = []
        for name in DOCUMENTS:
            text = read_doc(name)
            for number, line in enumerate(text.splitlines(), 1):
                for pattern in PRIVATE_PATTERNS:
                    if pattern.search(line):
                        offenders.append(f"docs/design/{name}:{number}: {pattern.pattern}")
        self.assertEqual([], offenders)

    def test_source_folder_paths_are_rewritten(self) -> None:
        # HISTORY.md is scanned too: it names the reports in prose ("the R0-R9 reviews").
        pattern = re.compile(r"(?<![\w./-])(?:reviews/|review\d/|passes/|audit/)|REV[56]_CHANGES")
        offenders = []
        for name in ("DESIGN.md", "SPEC.md", "IMPLEMENTATION_PLAN.md", "HISTORY.md"):
            for number, line in enumerate(read_doc(name).splitlines(), 1):
                if pattern.search(line):
                    offenders.append(f"docs/design/{name}:{number}: {line.strip()[:120]}")
        self.assertEqual([], offenders)

    def test_relative_links_resolve(self) -> None:
        sources = [DOCS / name for name in DOCUMENTS] + [ROOT / "README.md", ROOT / "docs" / "MAINTAINING.md"]
        broken = []
        for source in sources:
            self.assertTrue(source.is_file(), f"{source.relative_to(ROOT)} does not exist")
            for link in markdown_links(source.read_text(encoding="utf-8")):
                if re.match(r"^[a-z][a-z0-9+.-]*:", link, flags=re.I):
                    continue
                target, _, fragment = link.partition("#")
                resolved = (source.parent / target).resolve() if target else source
                where = f"{source.relative_to(ROOT)} -> {link}"
                if not resolved.exists():
                    broken.append(where)
                    continue
                if fragment and resolved.suffix == ".md" and DOCS in resolved.parents:
                    if fragment not in anchors(resolved.read_text(encoding="utf-8")):
                        broken.append(where + " (no such heading)")
        self.assertEqual([], broken)

    def test_entry_points_link_the_design_docs(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("(docs/design/README.md)", readme)
        maintaining = (ROOT / "docs" / "MAINTAINING.md").read_text(encoding="utf-8")
        self.assertIn("(design/DESIGN.md)", maintaining)
        self.assertIn("(design/SPEC.md)", maintaining)
        self.assertIn("docs/design", maintaining, "MAINTAINING says where § citations resolve")

    def test_shipped_docstrings_name_the_docs_design_paths(self) -> None:
        entry = (ROOT / "plugins/zzzops/zzzops/zzzops.py").read_text(encoding="utf-8").splitlines()[1]
        package = (ROOT / "plugins/zzzops/zzzops/engine/__init__.py").read_text(encoding="utf-8").splitlines()[0]
        for line in (entry, package):
            with self.subTest(line=line):
                self.assertIn("docs/design/DESIGN.md", line)
                self.assertIn("docs/design/SPEC.md", line)

    def test_cited_sections_exist(self) -> None:
        """Engine and test citations (`SPEC §x`, `DESIGN §x`, plan `Step N` and `§x`) resolve to headings."""
        numbers = {}
        for doc in ("SPEC", "DESIGN", "IMPLEMENTATION_PLAN"):
            numbers[doc] = {match[1] for match in re.finditer(
                r"^#{1,4} (?:Step )?(\d+(?:\.\d+)*)\.?\s", read_doc(f"{doc}.md"), flags=re.M)}
        cite = re.compile(r"\b(SPEC|DESIGN|IMPLEMENTATION_PLAN)(?:\.md)? ?§ ?(\d+(?:\.\d+)*)")
        step = re.compile(r"\bStep (\d+)\b")
        missing, total = [], 0
        for item in self.tracked:
            if item == THIS_FILE or not item.startswith(("plugins/", ".agents/")):
                continue
            try:
                text = (ROOT / item).read_text(encoding="utf-8")
            except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
                continue
            found = [(doc, number) for doc, number in cite.findall(text)]
            if item.startswith(".agents/test_"):
                found += [("IMPLEMENTATION_PLAN", number) for number in step.findall(text)]
            for doc, number in found:
                total += 1
                if number not in numbers[doc]:
                    missing.append(f"{item}: {doc} §{number}")
        self.assertGreater(total, 30, "expected the engine's existing section citations")
        self.assertEqual([], sorted(set(missing)))

    def test_amendment_ids_resolve_in_history(self) -> None:
        history = read_doc("HISTORY.md")
        index = section(history, r"amendment index")
        blocks: list[tuple[str, str]] = []
        heading = ""
        for line in index.splitlines():
            match = re.match(r"^#{1,6}\s+(.*)$", line)
            if match:
                heading = match[1]
            else:
                blocks.append((heading, line))
        cite = re.compile(r"\bREV([56]) ([A-H]\d+(?:(?:, | and |/)[A-H]\d+)*)")
        missing, total = [], 0
        for name in ("DESIGN.md", "SPEC.md"):
            for rev, ids in cite.findall(read_doc(name)):
                for ident in re.split(r", | and |/", ids):
                    total += 1
                    word = re.compile(rf"(?<![\w-]){ident}(?![\w-])")
                    tag = f"REV{rev}"
                    if not any(word.search(line) and (tag in head or tag in line) for head, line in blocks):
                        missing.append(f"{name}: {tag} {ident}")
        self.assertGreater(total, 30, "expected the documents' REV5/REV6 citations")
        self.assertEqual([], sorted(set(missing)))

    def test_history_lists_the_amendments_applied_since_approval(self) -> None:
        history = read_doc("HISTORY.md")
        log = section(history, r"amendments after approval")
        rows = [line for line in log.splitlines() if line.strip().startswith("|")]
        self.assertGreaterEqual(len(rows), 2 + len(MERGED_AMENDMENTS) + len(UNGOALED_AMENDMENT_PRS))
        for goal, pr in MERGED_AMENDMENTS.items():
            with self.subTest(goal=goal):
                self.assertTrue(any(re.search(rf"\b{goal}\b", row) and pr in row for row in rows),
                                f"no HISTORY §4 row for {goal} ({pr})")
        for pr in UNGOALED_AMENDMENT_PRS:
            self.assertTrue(any(pr in row for row in rows), f"no HISTORY §4 row for {pr}")
        self.assertIn("Revision 6.3", history, "the revision history moved into HISTORY.md")

    def test_status_lines(self) -> None:
        for name in ("DESIGN.md", "SPEC.md"):
            with self.subTest(name):
                head = "\n".join(read_doc(name).splitlines()[:12])
                self.assertIn("Revision 6.3, approved 2026-10-31 and implemented in #740", head)
                self.assertIn("HISTORY", head)
                self.assertNotIn("awaiting", head.lower())
        plan_head = "\n".join(read_doc("IMPLEMENTATION_PLAN.md").splitlines()[:12])
        self.assertIn("Completed 2026-10-31", plan_head)
        self.assertIn("historical record", plan_head)
        self.assertNotIn("**Revision history:**", read_doc("DESIGN.md"))

    def test_moved_documents_keep_their_numbered_headings(self) -> None:
        expected = {
            "SPEC.md": ("1. Conventions", "1.7 Identity", "3.16", "4.20", "8.4"),
            "DESIGN.md": ("3.15 CLI surface", "3.16 Stacked delivery", "4.1 Default graph", "10. Design-level validation contract", "11. Change log"),
            "IMPLEMENTATION_PLAN.md": ("1.2 Tests", "Step 0.", "Step 12.", "3. Deviations"),
        }
        for name, prefixes in expected.items():
            found = headings(read_doc(name))
            for prefix in prefixes:
                with self.subTest(document=name, heading=prefix):
                    self.assertTrue(any(item.startswith(prefix) for item in found), f"{name} lost heading {prefix!r}")

    def test_readme_states_normativity_amendment_and_repair(self) -> None:
        readme = read_doc("README.md")
        for link in ("(SPEC.md)", "(DESIGN.md)", "(HISTORY.md", "(IMPLEMENTATION_PLAN.md)"):
            self.assertIn(link, readme)
        self.assertRegex(readme, r"SPEC[^\n]*contract")
        self.assertIn("test_no_landed_goal_is_pending", readme)
        paragraphs = re.split(r"\n\s*\n", readme)
        repair = [p for p in paragraphs if "Repair" in p and "test_no_landed_goal_is_pending" in p]
        self.assertTrue(repair, "README needs a Repair paragraph naming the guard")
        self.assertTrue(any("Do not delete the row alone" in p for p in repair))
        parse_pending_table(readme)


if __name__ == "__main__":
    unittest.main()
