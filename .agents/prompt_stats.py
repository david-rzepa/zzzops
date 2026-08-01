#!/usr/bin/env python3
"""Print and enforce a stable cross-harness prompt-budget estimate."""

from __future__ import annotations

import argparse
import math
import time
from pathlib import Path


# Goal #129 adds the privacy boundary itself: shared immutable-report rules, exact public-
# payload consent, and one session gate that prevents feedback issues entering execution silently.
MAX_ESTIMATED_TOKENS = 14_400

HARNESS_PROMPTS = {
    "codex": ("AGENTS.md",),
    "claude": ("CLAUDE.md", "AGENTS.md"),
}

WORKFLOW_PROMPTS = {
    "capture": (
        ".agents/skills/add-zzzops-goal/SKILL.md",
        ".zzzops/rules/INITIALIZATION.md", ".zzzops/rules/BACKENDS.md",
        ".zzzops/rules/CONTINUATION.md", ".zzzops/rules/FEEDBACK.md",
    ),
    "execution": (
        ".agents/skills/execute-zzzops/SKILL.md",
        ".agents/skills/execute-zzzops/references/EXECUTE.md",
        ".agents/skills/execute-zzzops/references/BRANCH_REVIEW.md",
        ".agents/skills/execute-zzzops/references/SELF_REVIEW.md",
        ".zzzops/rules/INITIALIZATION.md", ".zzzops/rules/BACKENDS.md",
        ".zzzops/rules/GOAL_SYSTEM.md", ".zzzops/rules/CONTINUATION.md",
        ".zzzops/rules/EXECUTION_STRATEGY.md", ".zzzops/rules/FEEDBACK.md",
    ),
    "policy-review": (
        ".agents/skills/review-zzzops-policy/SKILL.md",
        ".zzzops/rules/INITIALIZATION.md", ".zzzops/rules/FEEDBACK.md",
    ),
    "migration": (
        ".agents/skills/migrate-to-zzzops/SKILL.md",
        ".zzzops/rules/INITIALIZATION.md", ".zzzops/rules/BACKENDS.md",
        ".zzzops/rules/FEEDBACK.md",
    ),
    "suggestion": (
        ".agents/skills/suggest-zzzops-work/SKILL.md",
        ".zzzops/rules/INITIALIZATION.md", ".zzzops/rules/BACKENDS.md",
        ".zzzops/rules/FEEDBACK.md",
    ),
    "acceptance": (
        ".agents/skills/run-zzzops-acceptance/SKILL.md",
        ".zzzops/rules/FEEDBACK.md",
    ),
    "feedback": (
        ".agents/skills/send-zzzops-feedback/SKILL.md",
        ".zzzops/rules/INITIALIZATION.md", ".zzzops/rules/FEEDBACK.md",
    ),
}

WORKFLOW_SIGNALS = {
    "capture": ("duplicate/relationship checks", "adaptive requirements interview", "sole stakeholder", "active same-task execute intent"),
    "execution": ("complete:true", "smallest falsifiable chunk", "difficulty is cost, not value", "human_after_checks", "Execution assumes the user is absent", "continue while policy permits safe useful work"),
    "policy-review": ("only this workflow changes or confirms policy", "explicit approval of the current digest", "execution-report recording"),
    "migration": ("explicit completeness review", "preserve every source location", "apply only after explicit approval"),
    "suggestion": ("no-write default", "zzzops-refill", "never copy source labels"),
    "acceptance": ("exactly one active item", "Never infer an ID", "blockers unchecked"),
    "feedback": ("exact target, title, labels, and body", "public", "nothing was deleted"),
}

GLOBAL_SIGNALS = (
    "user/safety > project rules",
    "Human-facing goal links",
    "Reports accept no free text",
)

def canonical_size(data: bytes) -> int:
    """Count UTF-8 bytes after normalizing platform line endings to LF."""
    return len(data.replace(b"\r\n", b"\n").replace(b"\r", b"\n"))


def prompt_files(root: Path) -> list[Path]:
    files = [root / "AGENTS.md", root / "CLAUDE.md"]
    files.extend((root / ".zzzops" / "rules").glob("*.md"))
    files.extend((root / ".agents" / "skills").glob("*/SKILL.md"))
    files.extend((root / ".agents" / "skills").glob("*/references/*.md"))
    files.extend((root / ".agents" / "zzzops" / "templates" / "project-goals").glob("*.md"))
    files.extend((root / ".claude" / "skills").glob("*/SKILL.md"))
    return sorted({path for path in files if path.is_file()}, key=lambda path: path.relative_to(root).as_posix())


def render_report(rows: list[tuple[str, int, int]]) -> str:
    total_bytes = sum(row[1] for row in rows)
    total_tokens = sum(row[2] for row in rows)
    table = [
        "# Prompt budget report",
        "",
        "Stable cross-harness estimate: `ceil(canonical UTF-8 bytes / 4)`; line endings normalize to LF. This is prompt-size regression evidence, not billing.",
        "",
        "| Prompt | Bytes | Est. tokens |",
        "| --- | ---: | ---: |",
    ]
    table.extend(f"| `{path}` | {size} | {tokens} |" for path, size, tokens in rows)
    table.append(f"| **Total** | **{total_bytes}** | **{total_tokens}** |")
    return "\n".join(table) + "\n"


def within_budget(rows: list[tuple[str, int, int]], limit: int = MAX_ESTIMATED_TOKENS) -> bool:
    return sum(row[2] for row in rows) <= limit


def workflow_profile(root: Path, workflow: str, harness: str) -> tuple[int, int, str]:
    paths = dict.fromkeys((*HARNESS_PROMPTS[harness], *WORKFLOW_PROMPTS[workflow]))
    data = b"\n".join((root / path).read_bytes() for path in paths)
    size = canonical_size(data)
    return size, math.ceil(size / 4), data.decode("utf-8")


def render_workflow_report(root: Path) -> str:
    table = [
        "# Routed workflow prompt report",
        "",
        "Directly routed source prompts plus each harness root; conditional execution create/unblock documents are excluded.",
        "",
        "| Workflow | Codex bytes | Codex est. tokens | Claude bytes | Claude est. tokens |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for workflow in WORKFLOW_PROMPTS:
        codex = workflow_profile(root, workflow, "codex")
        claude = workflow_profile(root, workflow, "claude")
        table.append(f"| {workflow} | {codex[0]} | {codex[1]} | {claude[0]} | {claude[1]} |")
    return "\n".join(table) + "\n"


def evaluate_workflows(root: Path) -> tuple[list[str], float]:
    started = time.perf_counter()
    failures = []
    for workflow, signals in WORKFLOW_SIGNALS.items():
        for harness in HARNESS_PROMPTS:
            corpus = workflow_profile(root, workflow, harness)[2]
            missing = [signal for signal in (*GLOBAL_SIGNALS, *signals) if signal not in corpus]
            if missing:
                failures.append(f"{workflow}/{harness}: {', '.join(missing)}")
    return failures, (time.perf_counter() - started) * 1000


def main() -> int:
    parser = argparse.ArgumentParser(description="Print or enforce the prompt-budget estimate")
    parser.add_argument("--check", action="store_true", help="Fail when the estimated prompt budget exceeds its committed ceiling")
    parser.add_argument("--profiles", action="store_true", help="Print per-workflow prompt loads for Codex and Claude")
    parser.add_argument("--eval", action="store_true", help="Run deterministic routed-workflow success fixtures")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.profiles:
        print(render_workflow_report(root), end="")
        return 0
    if args.eval:
        failures, latency_ms = evaluate_workflows(root)
        if failures:
            print(f"FAIL: {len(failures)} routed workflow checks failed in {latency_ms:.1f} ms; tool calls: 0; retries: 0")
            print("\n".join(failures))
            return 1
        checks = len(WORKFLOW_PROMPTS) * len(HARNESS_PROMPTS)
        print(f"PASS: {checks}/{checks} routed workflow checks in {latency_ms:.1f} ms; tool calls: 0; retries: 0")
        return 0
    rows = []
    for path in prompt_files(root):
        relative = path.relative_to(root).as_posix()
        size = canonical_size(path.read_bytes())
        rows.append((relative, size, math.ceil(size / 4)))
    if args.check:
        if not within_budget(rows):
            print(f"Prompt budget exceeds {MAX_ESTIMATED_TOKENS} estimated tokens; reduce prompts or deliberately raise the ceiling.")
            return 1
        print(f"Current: {len(rows)} prompts, {sum(row[1] for row in rows)} bytes, ~{sum(row[2] for row in rows)} tokens")
        return 0
    print(render_report(rows), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
