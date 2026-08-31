"""Small cross-platform shim for the tracked human acceptance plan."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import threading
from typing import Callable

START = "<!-- zzzops-acceptance-plan\n"
END = "\nzzzops-acceptance-plan -->"
DELEGATION_SUMMARY_LIMIT = 256
COORDINATOR_OPERATIONS = (
    "goal_state", "reservation", "integration", "approval", "external_write",
)


def digest(repo: Path, paths: list[str]) -> str:
    value = hashlib.sha256()
    for relative in sorted(paths):
        path = repo / relative
        value.update(relative.encode())
        value.update(b"\0")
        value.update(path.read_bytes() if path.is_file() else b"<missing>")
        value.update(b"\0")
    return value.hexdigest()


def load(plan_path: Path) -> tuple[str, dict, int, int]:
    text = plan_path.read_text(encoding="utf-8")
    start = text.index(START) + len(START)
    end = text.index(END, start)
    return text, json.loads(text[start:end]), start, end


def save(plan_path: Path, text: str, data: dict, start: int, end: int) -> None:
    plan_path.write_text(text[:start] + json.dumps(data, separators=(",", ":")) + text[end:], encoding="utf-8")


def _delegation_tasks(*, conflicting: bool = False, coupled: bool = False) -> list[dict]:
    common = ["path:shared"] if conflicting else None
    return [
        {
            "id": "worker-a", "resources": common or ["path:alpha"], "coupled": coupled,
            "facts": ["alpha:probe-failed", "alpha:fixture-added"],
            "noise": "SENTINEL-NOISE-A-" * 80,
        },
        {
            "id": "worker-b", "resources": common or ["path:beta"], "coupled": coupled,
            "facts": ["beta:docs-audited", "beta:no-conflict"],
            "noise": "SENTINEL-NOISE-B-" * 80,
        },
    ]


def run_delegation_fixture(
    tasks: list[dict], *, workers_available: bool, writable: bool = False, capacity: int = 2,
    coordinator_operations: dict[str, Callable[[], None]] | None = None,
) -> dict:
    """Exercise the delegation contract with deterministic injected work."""
    resources = [resource for task in tasks for resource in task["resources"]]
    if not workers_available:
        skip_reason = "unavailable_capacity_or_capability"
    elif len(tasks) < 2:
        skip_reason = "trivial_scope"
    elif any(task.get("coupled") for task in tasks):
        skip_reason = "tight_coupling"
    elif len(resources) != len(set(resources)):
        skip_reason = "dependency_or_resource_conflict"
    else:
        skip_reason = None
    if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity < 1:
        raise ValueError("delegation fixture capacity must be positive")
    delegated = skip_reason is None
    worker_count = min(capacity, len(tasks)) if delegated else 1
    parallel = delegated and worker_count > 1
    active = 0
    peak_active = 0
    lock = threading.Lock()
    barrier = threading.Barrier(worker_count) if parallel else None
    events: list[dict] = []
    worker_authority_calls: list[str] = []
    worker_write_violations: list[str] = []
    root_context = tempfile.TemporaryDirectory() if writable else None
    worktrees: dict[str, Path] = {}
    git_repo = Path(root_context.name) / "repository" if root_context else None

    def git(*arguments: str, cwd: Path) -> None:
        result = subprocess.run(
            ["git", *arguments], cwd=cwd, capture_output=True, text=True, check=False,
        )
        if result.returncode:
            raise ValueError("delegation fixture Git operation failed")

    if git_repo is not None:
        git_repo.mkdir()
        git("init", "-q", "-b", "dev", cwd=git_repo)
        git("config", "user.name", "ZzzOps Fixture", cwd=git_repo)
        git("config", "user.email", "fixture@example.invalid", cwd=git_repo)
        (git_repo / "README.md").write_text("fixture\n", encoding="utf-8")
        git("add", "README.md", cwd=git_repo)
        git("commit", "-qm", "test: initialize fixture", cwd=git_repo)
        for task in tasks:
            worktree = Path(root_context.name) / task["id"]
            git("worktree", "add", "-q", "-b", f"fixture-{task['id']}", str(worktree), cwd=git_repo)
            worktrees[task["id"]] = worktree

    def worker(task: dict) -> dict:
        nonlocal active, peak_active
        with lock:
            worker_authority_calls.extend(
                operation for operation in task.get("authority_attempts", [])
                if operation in COORDINATOR_OPERATIONS
            )
            worker_write_violations.extend(
                resource for resource in task.get("write_attempts", [])
                if not writable or resource not in task["resources"]
            )
            active += 1
            peak_active = max(peak_active, active)
            events.append({"event": "started", "task": task["id"]})
        if barrier is not None:
            barrier.wait()
        if writable:
            worktree = worktrees[task["id"]]
            artifact = worktree / f"{task['id']}.txt"
            artifact.write_text("\n".join(task["facts"]) + "\n", encoding="utf-8")
            git("add", artifact.name, cwd=worktree)
            git("commit", "-qm", f"test: complete {task['id']}", cwd=worktree)
        result = {"id": task["id"], "facts": task["facts"], "noise": task["noise"]}
        with lock:
            active -= 1
            events.append({"event": "finished", "task": task["id"]})
        return result

    if delegated:
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            results = list(executor.map(worker, tasks))
    else:
        results = [worker(task) for task in tasks]
    clean_worktrees = True
    for worktree in worktrees.values():
        status = subprocess.run(
            ["git", "status", "--porcelain"], cwd=worktree,
            capture_output=True, text=True, check=True,
        ).stdout
        clean_worktrees = clean_worktrees and not status.strip()
        git("worktree", "remove", str(worktree), cwd=git_repo)
    cleanup_verified = clean_worktrees and all(not worktree.exists() for worktree in worktrees.values())
    committed_worktrees = len(worktrees) if clean_worktrees else 0
    if root_context is not None:
        root_context.cleanup()

    facts = sorted(fact for result in results for fact in result["facts"])
    summary = ";".join(facts)
    if len(summary.encode("utf-8")) > DELEGATION_SUMMARY_LIMIT:
        raise ValueError("delegation fixture summary exceeds its deterministic bound")
    coordinator_calls = []
    callbacks = coordinator_operations or {operation: lambda: None for operation in COORDINATOR_OPERATIONS}
    for operation in COORDINATOR_OPERATIONS:
        callbacks[operation]()
        coordinator_calls.append({"actor": "coordinator", "operation": operation})
    input_bytes = len(json.dumps(tasks, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    summary_bytes = len(summary.encode("utf-8"))
    first_finish = next((index for index, event in enumerate(events) if event["event"] == "finished"), len(events))
    starts_before_finish = sum(event["event"] == "started" for event in events[:first_finish])
    overlap = starts_before_finish >= 2
    sequential_steps = sum(len(task["facts"]) for task in tasks)
    critical_path_steps = max(len(task["facts"]) for task in tasks) if overlap else sequential_steps
    return {
        "delegated": delegated,
        "execution": "parallel" if overlap else "sequential",
        "skip_reason": skip_reason,
        "worker_count": worker_count,
        "capacity": capacity,
        "peak_active": peak_active,
        "events": events,
        "overlap": overlap,
        "worker_authority_calls": worker_authority_calls,
        "worker_write_violations": worker_write_violations,
        "authority_valid": not worker_authority_calls,
        "coordinator_calls": coordinator_calls,
        "summary": summary,
        "summary_bytes": summary_bytes,
        "summary_limit": DELEGATION_SUMMARY_LIMIT,
        "input_bytes": input_bytes,
        "coordinator_context_reduction_bytes": input_bytes - summary_bytes,
        "context_basis": "serialized_fixture_bytes",
        "sentinel_excluded": "SENTINEL" not in summary,
        "writable": writable,
        "disjoint_worktree_assignments": not writable or len(set(worktrees.values())) == len(tasks),
        "cleanup_verified": cleanup_verified,
        "committed_worktrees": committed_worktrees,
        "writes_valid": not worker_write_violations,
        "latency": {
            "basis": "deterministic_fixture_steps",
            "sequential_steps": sequential_steps,
            "critical_path_steps": critical_path_steps,
        },
        "context_compaction": {"provenance": "unavailable", "milliseconds": None},
    }


def delegation_acceptance_report() -> dict:
    """Return all deterministic contract scenarios without claiming host behavior."""
    independent = run_delegation_fixture(_delegation_tasks(), workers_available=True)
    writable_tasks = _delegation_tasks()
    for task in writable_tasks:
        task["write_attempts"] = list(task["resources"])
    return {
        "schema_version": 1,
        "independent_read_only": independent,
        "resource_conflict": run_delegation_fixture(
            _delegation_tasks(conflicting=True), workers_available=True,
        ),
        "tight_coupling": run_delegation_fixture(
            _delegation_tasks(coupled=True), workers_available=True,
        ),
        "workers_unavailable": run_delegation_fixture(
            _delegation_tasks(), workers_available=False,
        ),
        "writable_worktrees": run_delegation_fixture(
            writable_tasks, workers_available=True, writable=True,
        ),
        "host_evidence": "manual_supported_host_check_required",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("next", "check", "audit", "coverage", "delegation"))
    parser.add_argument("item", nargs="?")
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--plan", type=Path, default=Path("docs/ACCEPTANCE_TEST_PLAN.md"))
    args = parser.parse_args()
    repo = args.repo.resolve()
    if args.command == "delegation":
        print(json.dumps(delegation_acceptance_report(), sort_keys=True, separators=(",", ":")))
        return 0
    plan = (repo / args.plan).resolve()
    text, data, start, end = load(plan)
    items = data["items"]
    if args.command == "coverage":
        required = [
            "plugins/zzzops/plugin.json", ".agents/plugins/marketplace.json",
            "plugins/zzzops/skills/add-zzzops-goal", "plugins/zzzops/skills/bootstrap-zzzops-repository",
            "plugins/zzzops/skills/migrate-to-zzzops",
            "plugins/zzzops/skills/review-zzzops-policy", "plugins/zzzops/skills/suggest-zzzops-work",
            "plugins/zzzops/skills/execute-zzzops", "plugins/zzzops/skills/review-agentic-engineering",
            "plugins/zzzops/skills/send-zzzops-feedback",
            "plugins/zzzops/skills/validate-zzzops-installation",
        ]
        mapped = {
            surface
            for item in items
            for surface in item.get("surfaces", item["paths"])
        }
        automated_without_evidence = []
        for contract in data.get("automated_surfaces", []):
            evidence = contract.get("evidence", [])
            missing_evidence = [
                path for path in evidence if not (repo / path).is_file()
            ]
            if not evidence or missing_evidence:
                automated_without_evidence.append({
                    "surface": contract["surface"],
                    "missing": missing_evidence,
                })
            else:
                mapped.add(contract["surface"])
        missing = [path for path in required if not any(entry == path or entry.startswith(path + "/") for entry in mapped)]
        print(json.dumps({
            "unmapped_required_surfaces": missing,
            "automated_surfaces_without_evidence": automated_without_evidence,
        }))
        return 1 if missing or automated_without_evidence else 0
    if args.command == "audit":
        changed = []
        for item in items:
            current = digest(repo, item["paths"])
            if item["status"] == "checked" and item["fingerprint"] != current:
                item["status"], item["fingerprint"] = "unchecked", None
                changed.append(item["id"])
        save(plan, text, data, start, end)
        print(json.dumps({"stale": changed}))
        return 0
    if args.command == "next":
        item = next((entry for entry in items if entry["status"] != "checked"), None)
        print(json.dumps(item))
        return 0 if item else 1
    item = next((entry for entry in items if entry["id"] == args.item), None)
    if not item:
        raise SystemExit("unknown item")
    item["status"], item["fingerprint"] = "checked", digest(repo, item["paths"])
    save(plan, text, data, start, end)
    print(json.dumps({"checked": item["id"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
