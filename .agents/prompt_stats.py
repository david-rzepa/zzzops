#!/usr/bin/env python3
"""Report prompt inventory and enforce representative Codex context budgets."""

from __future__ import annotations

import argparse
import math
import time
from pathlib import Path


HARNESS_PROMPTS = {
    "codex": ("AGENTS.md",),
}

COMMUNICATION_PROMPT = "plugins/zzzops/rules/COMMUNICATION.md"

# These limits protect context paid on every Codex turn and the two frequent ZzzOps paths. At the
# goal #297 baseline, always-loaded/codex is 625 tokens. Goal #302 reduced capture/execution to
# 3,324/8,452 tokens; their ceilings retain only the measured 13-token execution margin. Cold
# mutually exclusive workflows remain advisory rather than competing for one aggregate allowance.
ENFORCED_PROMPT_BUDGETS = {
    "always-loaded/codex": 700,
    "capture/codex": 3_324,
    "execution/codex": 8_465,
}

WORKFLOW_PROMPTS = {
    "agentic-coaching": (
        "plugins/zzzops/skills/review-agentic-engineering/SKILL.md",
        "plugins/zzzops/skills/review-agentic-engineering/references/ATTRIBUTION.md",
        COMMUNICATION_PROMPT, "plugins/zzzops/rules/FEEDBACK.md",
    ),
    "bootstrap-greenfield": (
        "plugins/zzzops/skills/bootstrap-zzzops-repository/SKILL.md",
        "plugins/zzzops/zzzops/references/bootstrap/ANALYZE.md",
        "plugins/zzzops/zzzops/references/bootstrap/PLAN.md",
        "plugins/zzzops/zzzops/references/bootstrap/GREENFIELD.md",
        COMMUNICATION_PROMPT, "plugins/zzzops/rules/INITIALIZATION.md", "plugins/zzzops/rules/BACKENDS.md",
        "plugins/zzzops/rules/FEEDBACK.md",
    ),
    "bootstrap-brownfield": (
        "plugins/zzzops/skills/bootstrap-zzzops-repository/SKILL.md",
        "plugins/zzzops/zzzops/references/bootstrap/ANALYZE.md",
        "plugins/zzzops/zzzops/references/bootstrap/PLAN.md",
        "plugins/zzzops/zzzops/references/bootstrap/BROWNFIELD.md",
        COMMUNICATION_PROMPT, "plugins/zzzops/rules/INITIALIZATION.md", "plugins/zzzops/rules/BACKENDS.md",
        "plugins/zzzops/rules/FEEDBACK.md",
    ),
    "capture": (
        "plugins/zzzops/skills/add-zzzops-goal/SKILL.md",
        COMMUNICATION_PROMPT, "plugins/zzzops/rules/INITIALIZATION.md", "plugins/zzzops/rules/BACKENDS.md",
        "plugins/zzzops/rules/CONTINUATION.md", "plugins/zzzops/rules/FEEDBACK.md",
    ),
    "execution": (
        "plugins/zzzops/skills/execute-zzzops/SKILL.md",
        "plugins/zzzops/skills/execute-zzzops/references/EXECUTE.md",
        "plugins/zzzops/skills/execute-zzzops/references/BRANCH_REVIEW.md",
        "plugins/zzzops/skills/execute-zzzops/references/SELF_REVIEW.md",
        COMMUNICATION_PROMPT, "plugins/zzzops/rules/INITIALIZATION.md", "plugins/zzzops/rules/BACKENDS.md",
        "plugins/zzzops/rules/GOAL_SYSTEM.md", "plugins/zzzops/rules/CONTINUATION.md",
        "plugins/zzzops/rules/EXECUTION_STRATEGY.md", "plugins/zzzops/rules/FEEDBACK.md",
    ),
    "policy-review": (
        "plugins/zzzops/skills/review-zzzops-policy/SKILL.md",
        COMMUNICATION_PROMPT, "plugins/zzzops/rules/INITIALIZATION.md", "plugins/zzzops/rules/FEEDBACK.md",
    ),
    "migration": (
        "plugins/zzzops/skills/migrate-to-zzzops/SKILL.md",
        COMMUNICATION_PROMPT, "plugins/zzzops/rules/INITIALIZATION.md", "plugins/zzzops/rules/BACKENDS.md",
        "plugins/zzzops/rules/FEEDBACK.md",
    ),
    "suggestion": (
        "plugins/zzzops/skills/suggest-zzzops-work/SKILL.md",
        COMMUNICATION_PROMPT, "plugins/zzzops/rules/INITIALIZATION.md", "plugins/zzzops/rules/BACKENDS.md",
        "plugins/zzzops/rules/FEEDBACK.md",
    ),
    "acceptance": (
        ".agents/skills/run-zzzops-acceptance/SKILL.md",
        "plugins/zzzops/rules/FEEDBACK.md",
    ),
    "feedback": (
        "plugins/zzzops/skills/send-zzzops-feedback/SKILL.md",
        COMMUNICATION_PROMPT, "plugins/zzzops/rules/INITIALIZATION.md", "plugins/zzzops/rules/FEEDBACK.md",
    ),
}

WORKFLOW_SIGNALS = {
    "agentic-coaching": ("Run only when explicitly invoked", "at most two", "Only genuine `prompt_specification_gap`", "Remain read-only", "Do not resolve `ambiguous` candidates by guessing", "$send-zzzops-feedback"),
    "bootstrap-greenfield": ("never silently de-escalate", "adaptive product interview", "exactly one canonical top-level product-outcome goal", "canonical verification", "Continue from harness outcomes into product milestones", "ordered PR review queue"),
    "bootstrap-brownfield": ("evidence-led product/harness audit", "top-level product-outcome goal", "reconcile it in place", "$migrate-to-zzzops", "canonical verification", "until exhaustion"),
    "capture": ("duplicate/relationship matches", "interview at", "owns requirements/acceptance", "active same-task execute intent", "effective engineering rigor", "vibe → light", "never silently de-escalate", "Git-free creation"),
    "execution": ("complete:true", "smallest falsifiable chunk", "difficulty is cost, not value", "human_at_exhaustion", "human_after_checks", "PR review queue", "Execution assumes the user is absent", "Before substantive work on a newly selected goal", "safe useful work", "effective engineering rigor", "created-but-unrun machinery is not proof"),
    "policy-review": ("only this workflow changes or confirms policy", "explicit approval of the current digest", "The policy is already approved", "privacy-safe execution reports"),
    "migration": ("explicit completeness review", "preserve every source location", "apply only after explicit approval"),
    "suggestion": ("no-write default", "zzzops-refill", "never copy source labels", "goal-effective engineering rigor", "incomplete canonical verification", "proposed goal—not a silent change"),
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
    files = [root / "AGENTS.md"]
    files.extend((root / "plugins" / "zzzops" / "rules").glob("*.md"))
    product_skills = list((root / "plugins" / "zzzops" / "skills").glob("*/SKILL.md"))
    files.extend(product_skills)
    for skill in product_skills:
        files.extend((skill.parent / "references").glob("*.md"))
    files.extend((root / "plugins" / "zzzops" / "zzzops" / "references" / "bootstrap").glob("*.md"))
    files.extend((root / "plugins" / "zzzops" / "zzzops" / "templates" / "project-goals").glob("*.md"))
    files.extend((root / "plugins" / "zzzops" / "concepts").glob("*.md"))
    files.extend((root / ".agents" / "skills").glob("*/SKILL.md"))
    files.extend((root / ".agents" / "skills").glob("*/references/*.md"))
    return sorted({path for path in files if path.is_file()}, key=lambda path: path.relative_to(root).as_posix())


def render_report(rows: list[tuple[str, int, int]]) -> str:
    total_bytes = sum(row[1] for row in rows)
    total_tokens = sum(row[2] for row in rows)
    table = [
        "# Advisory prompt inventory",
        "",
        "Stable Codex estimate: `ceil(canonical UTF-8 bytes / 4)`; line endings normalize to LF. This is prompt-size telemetry, not a blocking budget or billing.",
        "",
        "| Prompt | Bytes | Est. tokens |",
        "| --- | ---: | ---: |",
    ]
    table.extend(f"| `{path}` | {size} | {tokens} |" for path, size, tokens in rows)
    table.append(f"| **Total** | **{total_bytes}** | **{total_tokens}** |")
    return "\n".join(table) + "\n"


def prompt_profile(root: Path, paths: tuple[str, ...]) -> tuple[int, int, str]:
    unique_paths = dict.fromkeys(paths)
    data = b"\n".join((root / path).read_bytes() for path in unique_paths)
    size = canonical_size(data)
    return size, math.ceil(size / 4), data.decode("utf-8")


def workflow_profile(root: Path, workflow: str, harness: str) -> tuple[int, int, str]:
    return prompt_profile(root, (*HARNESS_PROMPTS[harness], *WORKFLOW_PROMPTS[workflow]))


def enforced_context_profiles(root: Path) -> dict[str, tuple[int, int]]:
    profiles = {}
    for harness, paths in HARNESS_PROMPTS.items():
        profiles[f"always-loaded/{harness}"] = prompt_profile(root, paths)[:2]
    for workflow in ("capture", "execution"):
        for harness in HARNESS_PROMPTS:
            profiles[f"{workflow}/{harness}"] = workflow_profile(root, workflow, harness)[:2]
    return profiles


def policy_context_profiles(root: Path) -> dict[str, tuple[int, int]]:
    cold_review_skill = "plugins/zzzops/skills/review-zzzops-policy/SKILL.md"
    static_hot = tuple(
        path.relative_to(root).as_posix()
        for path in prompt_files(root)
        if path.relative_to(root).as_posix() != cold_review_skill
    )
    project_policy = tuple(
        path for path in (".zzzops/PROJECT.md", ".zzzops/POLICY.json")
        if (root / path).is_file()
    )
    cold_review = (
        *WORKFLOW_PROMPTS["policy-review"],
        "plugins/zzzops/zzzops/templates/project-goals/INIT_PLAN.json",
    )
    return {
        "static-hot-prompts": prompt_profile(root, static_hot)[:2],
        "current-project-policy": prompt_profile(root, project_policy)[:2] if project_policy else (0, 0),
        "cold-default-review": prompt_profile(root, cold_review)[:2],
    }


def budget_overruns(
    measurements: dict[str, tuple[int, int]],
    limits: dict[str, int] = ENFORCED_PROMPT_BUDGETS,
) -> list[tuple[str, int, int]]:
    return [
        (context, measurements[context][1], limit)
        for context, limit in limits.items()
        if measurements[context][1] > limit
    ]


def render_enforced_budget_report(
    measurements: dict[str, tuple[int, int]],
    limits: dict[str, int],
    *,
    prompt_count: int,
    inventory_bytes: int,
    inventory_tokens: int,
    policy_context: dict[str, tuple[int, int]] | None = None,
) -> str:
    table = [
        "# Enforced prompt budgets",
        "",
        "Only always-loaded context and frequent routed workflows are blocking. Other workflows and total inventory are advisory.",
        "",
        "| Context | Bytes | Est. tokens | Limit | Status |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for context, limit in limits.items():
        size, tokens = measurements[context]
        status = "PASS" if tokens <= limit else "FAIL"
        table.append(f"| {context} | {size} | {tokens} | {limit} | {status} |")
    table.extend((
        "",
        f"Advisory total inventory: {prompt_count} prompts, {inventory_bytes} bytes, ~{inventory_tokens} tokens.",
    ))
    if policy_context is not None:
        table.extend((
            "",
            "## Policy context boundary",
            "",
            "Public documentation is excluded. Static prompts, the current project policy, and cold default/review context are counted separately.",
            "",
            "| Context class | Bytes | Est. tokens |",
            "| --- | ---: | ---: |",
        ))
        table.extend(
            f"| {name} | {size} | {tokens} |"
            for name, (size, tokens) in policy_context.items()
        )
    return "\n".join(table) + "\n"


def render_workflow_report(root: Path) -> str:
    table = [
        "# Advisory routed workflow prompt report",
        "",
        "Directly routed plugin prompts plus the Codex repository root; conditional execution create/unblock documents are excluded. Capture and execution also have blocking limits in `--check`.",
        "",
        "| Workflow | Codex bytes | Codex est. tokens |",
        "| --- | ---: | ---: |",
    ]
    for workflow in WORKFLOW_PROMPTS:
        codex = workflow_profile(root, workflow, "codex")
        table.append(f"| {workflow} | {codex[0]} | {codex[1]} |")
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
    parser = argparse.ArgumentParser(description="Report prompt inventory or enforce routed context budgets")
    parser.add_argument("--check", action="store_true", help="Fail when always-loaded, capture, or execution context exceeds its committed ceiling")
    parser.add_argument("--profiles", action="store_true", help="Print per-workflow prompt loads for Codex")
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
        measurements = enforced_context_profiles(root)
        print(render_enforced_budget_report(
            measurements,
            ENFORCED_PROMPT_BUDGETS,
            prompt_count=len(rows),
            inventory_bytes=sum(row[1] for row in rows),
            inventory_tokens=sum(row[2] for row in rows),
            policy_context=policy_context_profiles(root),
        ), end="")
        overruns = budget_overruns(measurements)
        if overruns:
            for context, tokens, limit in overruns:
                print(f"FAIL: {context} uses {tokens} estimated tokens; committed limit is {limit}.")
            return 1
        print("PASS: all enforced prompt contexts are within their committed limits.")
        return 0
    print(render_report(rows), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
