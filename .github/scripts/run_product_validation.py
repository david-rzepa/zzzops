"""Run one named, read-only ZzzOps product-validation leg."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import Callable, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[2]
LINUX_TIMINGS = ROOT / ".github" / "scripts" / "linux_test_timings.json"
LINUX_AUXILIARY_SECONDS = 20.0
# This unchanged one-second wall-clock contract needs an otherwise idle shard.
# Keep this list explicit and discovery-guarded: never omit or relax the test.
LINUX_EXCLUSIVE_TESTS = (
    "test_evidence_dag_journeys.EvidenceDagPublicTests.test_pure_frontier_has_no_io_and_fixed_expanded_equal_work_budget",
)

NATIVE_COVERAGE = {
    "installation_cleanup": (
        "test_installation_validation.InstallationValidationTests.test_cli_clean_first_use_and_idempotent_status",
        "test_legacy_cleanup.LegacyCleanupTests.test_default_cli_is_dry_run_and_interrupted_cleanup_converges",
    ),
    "marketplace_package": (
        "test_marketplace_bundle.MarketplaceBundleTests.test_fixed_version_build_is_deterministic_and_complete",
        "test_agent_plugin.AgentPluginTests.test_marketplace_points_to_the_self_contained_package",
    ),
    "package_cli": ("test_zzzops.InitializationTests.test_cli_without_command_shows_help_without_writing_local_state",),
    "heartbeat_process": ("test_workflow_heartbeat.HeartbeatProcessTests.test_one_coordinator_renews_multiple_leases_and_stops_tracking_workers",),
    "git_crlf_drift": (
        "test_evidence_dag_journeys.WorkspaceAuthorityPublicTests.test_mixed_clean_checkout_rejects_raw_consumed_drift_and_restores_exact_acquisition",
        "test_evidence_dag_journeys.WorkspaceAuthorityPublicTests.test_crlf_design_correction_retains_frozen_raw_checkout_overrides",
        "test_evidence_dag_journeys.WorkspaceAuthorityPublicTests.test_clean_crlf_checkout_pins_raw_consumed_bytes_and_allows_owned_red_edit",
    ),
    "path_confinement": ("test_evidence_dag_journeys.WorkspaceAuthorityPublicTests.test_acquired_owned_path_cannot_be_replaced_by_escaping_symlink",),
    "public_delivery": ("test_workflow_publication_contract.GenericDeliveryPublicTests.test_reviewed_red_green_proofs_commit_and_exact_publication_form_one_delivery_graph",),
}


def run(*command: str) -> None:
    subprocess.run(command, cwd=ROOT, check=True)


def _test_ids(suite: unittest.TestSuite) -> set[str]:
    found: set[str] = set()
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            found.update(_test_ids(test))
        else:
            found.add(test.id())
    return found


def discover_native_tests(root: Path = ROOT) -> set[str]:
    tests = Path(root) / ".agents"
    loader = unittest.TestLoader()
    suite = loader.discover(str(tests), pattern="test_*.py", top_level_dir=str(tests))
    if loader.errors:
        raise RuntimeError("native unittest discovery loader errors:\n" + "\n".join(loader.errors))
    return _test_ids(suite)


def discover_linux_tests(root: Path = ROOT) -> list[str]:
    """Preserve multiplicity until duplicate canonical identities are rejected."""
    tests = Path(root) / ".agents"
    loader = unittest.TestLoader()
    suite = loader.discover(str(tests), pattern="test_*.py", top_level_dir=str(tests))
    if loader.errors:
        raise RuntimeError("Linux unittest discovery loader errors:\n" + "\n".join(loader.errors))

    def identities(group):
        for test in group:
            if isinstance(test, unittest.TestSuite):
                yield from identities(test)
            else:
                yield test.id()

    found = list(identities(suite))
    if not found or len(found) != len(set(found)):
        raise ValueError("Linux discovery inventory is empty or contains duplicate IDs")
    return sorted(found)


def load_linux_timings(path: Path = LINUX_TIMINGS) -> tuple[dict[str, float], float]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    weights, fallback = value["seconds"], value["default_seconds"]
    if value.get("schema_version") != 1 or not isinstance(weights, dict):
        raise ValueError("Invalid Linux timing hints")
    for seconds in [fallback, *weights.values()]:
        if (isinstance(seconds, bool) or not isinstance(seconds, (int, float))
                or not math.isfinite(seconds) or seconds <= 0):
            raise ValueError("Linux timing hints must be finite positive seconds")
    return weights, float(fallback)


def partition_linux_tests(discovered: Iterable[str], shard_count: int,
                          weights: Mapping[str, float], fallback: float = 10.0,
                          auxiliary_seconds: float = LINUX_AUXILIARY_SECONDS) -> list[list[str]]:
    """Longest-first packing; timing hints never determine inventory membership."""
    inventory = list(discovered)
    if not inventory or len(inventory) != len(set(inventory)):
        raise ValueError("Linux partition inventory is empty or contains duplicate IDs")
    if type(shard_count) is not int or not 1 <= shard_count <= len(inventory):
        raise ValueError("Linux shard count must be positive and cannot create empty shards")
    shards: list[list[str]] = [[] for _ in range(shard_count)]
    loads = [auxiliary_seconds, *([0.0] * (shard_count - 1))]
    for test_id in sorted(inventory, key=lambda item: (-weights.get(item, fallback), item)):
        candidates = [item for item in range(shard_count) if not shards[item]] or range(shard_count)
        index = min(candidates, key=lambda item: (loads[item], item))
        shards[index].append(test_id)
        loads[index] += weights.get(test_id, fallback)
    # These checks also guard future changes to the partition algorithm.
    assigned = [test_id for shard in shards for test_id in shard]
    if (any(not shard for shard in shards) or len(assigned) != len(set(assigned))
            or set(assigned) != set(inventory)):
        raise ValueError("Linux shards have missing, duplicate or empty assignments")
    return [sorted(shard) for shard in shards]


def select_native_tests(discovered: Iterable[str]) -> list[str]:
    selected = [test_id for ids in NATIVE_COVERAGE.values() for test_id in ids]
    if not selected:
        raise ValueError("native test selection is empty")
    if len(selected) != len(set(selected)):
        raise ValueError("native test selection contains duplicate IDs")
    missing = set(selected) - set(discovered)
    if missing:
        raise ValueError("native test selection has missing IDs: " + ", ".join(sorted(missing)))
    return selected


_CHILD_RUNNER = r'''
import json, os, sys, time, unittest
class Stream:
    def __init__(self, wrapped): self.wrapped = wrapped
    def write(self, value): self.wrapped.write(value)
    def flush(self): self.wrapped.flush()
    def writeln(self, value=""): self.wrapped.write(value + "\n")
class Result(unittest.TextTestResult):
    def startTest(self, test):
        self._started = time.perf_counter()
        self.executed_ids.append(test.id())
        super().startTest(test)
    def stopTest(self, test):
        self.durations[test.id()] = time.perf_counter() - self._started
        self.completed_ids.append(test.id())
        super().stopTest(test)
    def addSkip(self, test, reason):
        self.invalid_skips.append({"id": test.id(), "reason": reason})
        super().addSkip(test, reason)
sys.path.insert(0, os.path.join(sys.argv[1], ".agents"))
suite = unittest.defaultTestLoader.loadTestsFromNames(json.loads(sys.argv[2]))
result = Result(Stream(sys.stderr), True, 1)
result.executed_ids, result.completed_ids, result.durations = [], [], {}
result.native_skips, result.invalid_skips = [], []
suite.run(result)
result.printErrors()
payload = {
    "returncode": 0 if result.wasSuccessful() and not result.invalid_skips else 1,
    "tests_run": result.testsRun, "executed_ids": result.executed_ids,
    "completed_ids": result.completed_ids,
    "failures": len(result.failures), "errors": len(result.errors),
    "skips": result.native_skips, "invalid_skips": result.invalid_skips,
    "durations": result.durations,
}
with open(sys.argv[3], "w", encoding="utf-8") as handle:
    json.dump(payload, handle)
'''


def _launch_native(selected: list[str], root: Path) -> dict:
    with tempfile.NamedTemporaryFile(prefix="zzzops-native-", suffix=".json", delete=False) as handle:
        report_path = Path(handle.name)
    try:
        completed = subprocess.run(
            [sys.executable, "-c", _CHILD_RUNNER, str(root), json.dumps(selected), str(report_path)],
            cwd=root, check=False,
        )
        if not report_path.stat().st_size:
            raise RuntimeError(f"native test subprocess exited {completed.returncode} without a report")
        observation = json.loads(report_path.read_text(encoding="utf-8"))
        if completed.returncode and observation.get("returncode") == 0:
            observation["returncode"] = completed.returncode
        return observation
    finally:
        report_path.unlink(missing_ok=True)


def _validate_observation(selected: list[str], observation: Mapping) -> None:
    executed = list(observation.get("executed_ids", ()))
    tests_run = observation.get("tests_run")
    if not executed or not tests_run:
        raise ValueError("native execution observation is empty")
    if len(executed) != len(set(executed)):
        raise ValueError("native execution observation contains duplicate executed IDs")
    if tests_run != len(executed):
        raise ValueError("native execution count mismatch")
    if set(executed) != set(selected) or tests_run != len(selected):
        raise ValueError("native execution is partial or has unexpected executed IDs")
    if observation.get("invalid_skips"):
        raise ValueError(f"skip lacks unavailable native facility evidence: {observation['invalid_skips']}")
    for skip in observation.get("skips", ()):
        if skip.get("id") not in selected:
            raise ValueError("skip references a test outside the selected IDs")
        if skip.get("kind") != "unavailable_native_facility":
            raise ValueError("skip is not an unavailable native facility")
        if not skip.get("reason"):
            raise ValueError("native facility skip requires a reason")
        if not skip.get("evidence"):
            raise ValueError("native facility skip requires probe evidence")


def _group_timings(durations: Mapping[str, float]) -> list[tuple[str, float]]:
    groups = [(group, sum(float(durations.get(test_id, 0.0)) for test_id in ids)) for group, ids in NATIVE_COVERAGE.items()]
    return sorted(groups, key=lambda item: item[1], reverse=True)


def run_native_validation(
    platform: str, root: Path = ROOT,
    discover: Callable[[], Iterable[str]] | None = None,
    launch: Callable[[list[str]], Mapping] | None = None,
    clock: Callable[[], float] = time.perf_counter,
    emit: Callable[[dict], None] | None = None,
) -> dict:
    started = clock()
    discovered = discover() if discover is not None else discover_native_tests(root=root)
    selected = select_native_tests(discovered)
    observation = dict(launch(selected) if launch is not None else _launch_native(selected, Path(root)))
    elapsed = clock() - started
    _validate_observation(selected, observation)
    durations = {key: float(value) for key, value in observation.get("durations", {}).items()}
    report = {
        "platform": platform, "selected_ids": selected, "selected_count": len(selected),
        "tests_run": observation["tests_run"], "failures": observation.get("failures", 0),
        "errors": observation.get("errors", 0), "skipped": len(observation.get("skips", ())),
        "coverage_limits": list(observation.get("skips", ())), "wall_seconds": elapsed,
        "aggregate_test_seconds": sum(durations.values()),
        "slowest_tests": sorted(durations.items(), key=lambda item: item[1], reverse=True)[:5],
        "slowest_groups": _group_timings(durations),
    }
    (emit or (lambda value: print(json.dumps(value, sort_keys=True))))(report)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        write_step_summary(report, Path(os.environ["GITHUB_STEP_SUMMARY"]))
    if observation.get("returncode", 0):
        raise subprocess.CalledProcessError(int(observation["returncode"]), [sys.executable, "native-tests"])
    return report


def write_step_summary(report: Mapping, path: Path) -> None:
    lines = [
        f"## Native validation: {report['platform']}", "", f"- selected: {report['selected_count']}",
        f"- tests run: {report['tests_run']}",
        f"- failures/errors/skipped: {report['failures']}/{report['errors']}/{report['skipped']}",
        f"- wall seconds: {report['wall_seconds']:.2f}",
        f"- aggregate test seconds: {report['aggregate_test_seconds']:.2f}", "", "### Selected tests", "",
        *(f"- {test_id}" for test_id in report["selected_ids"]), "", "### Slowest tests", "",
        *(f"- {test_id}: {seconds:.3f}s" for test_id, seconds in report["slowest_tests"]),
        "", "### Slowest coverage groups", "",
        *(f"- {group}: {seconds:.3f}s" for group, seconds in report["slowest_groups"]),
        "", "### Coverage limits", "",
    ]
    limits = report["coverage_limits"]
    lines.extend(f"- {item['id']}: {item['reason']} ({item['evidence']})" for item in limits)
    if not limits:
        lines.append("- none")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def linux_validation() -> None:
    run(sys.executable, "-m", "unittest", "discover", "-s", ".agents", "-p", "test_*.py")
    linux_auxiliary_validation()


def linux_auxiliary_validation() -> None:
    run(sys.executable, "-m", "unittest", "discover", "-s", "plugins/zzzops/skills/migrate-to-zzzops/scripts", "-p", "test_*.py")
    run(sys.executable, ".agents/manual_acceptance.py", "coverage")
    run("npm", "run", "test:plugin")
    run("npm", "run", "test:release")
    run(sys.executable, ".agents/prompt_stats.py", "--check")
    run(sys.executable, "-m", "compileall", "-q", ".agents", "plugins/zzzops", ".github/scripts")


def _validate_linux_observation(selected: list[str], observation: Mapping) -> None:
    _validate_observation(selected, observation)
    completed = list(observation.get("completed_ids", ()))
    if (len(completed) != len(set(completed)) or len(completed) != len(selected)
            or set(completed) != set(selected)):
        raise ValueError("Linux execution has missing, duplicate or partial completed IDs")
    for key in ("tests_run", "returncode", "failures", "errors"):
        if type(observation.get(key)) is not int or observation[key] < 0:
            raise ValueError("Linux execution lacks valid outcome counts")


def linux_shard_plan(shard_index: int, shard_count: int, root: Path = ROOT) -> dict:
    inventory = discover_linux_tests(root)
    missing_exclusive = set(LINUX_EXCLUSIVE_TESTS) - set(inventory)
    if missing_exclusive:
        raise ValueError("Linux exclusive test IDs missing from discovery: " + ", ".join(sorted(missing_exclusive)))
    weights, fallback = load_linux_timings()
    shards = partition_linux_tests(inventory, shard_count, weights, fallback)
    if type(shard_index) is not int or not 0 <= shard_index < shard_count:
        raise ValueError("Linux shard index is outside the configured shard count")
    selected = shards[shard_index]
    return {
        "schema_version": 1, "platform": "linux", "python_version": sys.version.split()[0],
        "shard_index": shard_index, "shard_count": shard_count,
        "inventory_count": len(inventory),
        "inventory_sha256": hashlib.sha256("\n".join(inventory).encode()).hexdigest(),
        "selected_ids": selected, "selected_count": len(selected),
        "estimated_test_seconds": sum(weights.get(item, fallback) for item in selected),
        "auxiliary_checks": shard_index == 0,
    }


def linux_worker_plan(selected: list[str], workers: int) -> tuple[list[list[str]], list[str]]:
    if type(workers) is not int or workers not in (1, 2):
        raise ValueError("Linux workers must be 1 or 2")
    if workers == 1:
        return [selected], []
    exclusive = sorted(set(selected) & set(LINUX_EXCLUSIVE_TESTS))
    concurrent = [item for item in selected if item not in exclusive]
    weights, fallback = load_linux_timings()
    batches = (partition_linux_tests(concurrent, min(workers, len(concurrent)), weights,
                                    fallback, auxiliary_seconds=0.0) if concurrent else [])
    return batches, exclusive


def _combine_linux_observations(observations: list[Mapping]) -> dict:
    combined = {"returncode": 0, "tests_run": 0, "failures": 0, "errors": 0,
                "executed_ids": [], "completed_ids": [], "skips": [], "invalid_skips": [],
                "durations": {}}
    for observation in observations:
        for key in ("tests_run", "failures", "errors"):
            combined[key] += observation[key]
        combined["returncode"] = max(combined["returncode"], observation["returncode"])
        for key in ("executed_ids", "completed_ids", "skips", "invalid_skips"):
            combined[key].extend(observation.get(key, []))
        durations = observation.get("durations", {})
        if combined["durations"].keys() & durations.keys():
            raise ValueError("Linux workers have duplicate duration IDs")
        combined["durations"].update(durations)
    return combined


def run_linux_shard(shard_index: int, shard_count: int, report_path: Path | None = None,
                    workers: int = 1) -> dict:
    started = time.perf_counter()
    report = linux_shard_plan(shard_index, shard_count)
    report["status"] = "failed"
    report["workers"] = workers
    report["worker_reports"] = []
    try:
        batches, exclusive = linux_worker_plan(report["selected_ids"], workers)
        report["concurrent_worker_count"] = len(batches)
        report["serial_ids"] = exclusive
        # Threads only supervise fresh interpreters; unittest globals stay isolated.
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_launch_native, batch, ROOT) for batch in batches]
            for index, (batch, future) in enumerate(zip(batches, futures)):
                try:
                    child = dict(future.result())
                    report["worker_reports"].append({"worker_index": index, "serial": False,
                                                     "selected_ids": batch, "observation": child})
                except Exception as error:
                    report["worker_reports"].append({"worker_index": index, "serial": False,
                                                     "selected_ids": batch, "error": str(error)})
        # Pool exit waits for every child, including failures, before the timing test.
        if exclusive:
            worker = {"worker_index": len(batches), "serial": True, "selected_ids": exclusive}
            report["worker_reports"].append(worker)
            try:
                worker["observation"] = dict(_launch_native(exclusive, ROOT))
            except Exception as error:
                worker["error"] = str(error)
        for worker in report["worker_reports"]:
            if "error" in worker:
                raise RuntimeError(worker["error"])
            _validate_linux_observation(worker["selected_ids"], worker["observation"])
        observation = _combine_linux_observations([worker["observation"] for worker in report["worker_reports"]])
        report.update({key: observation[key] for key in (
            "returncode", "tests_run", "executed_ids", "completed_ids", "failures", "errors",
            "skips", "invalid_skips", "durations",
        ) if key in observation})
        _validate_linux_observation(report["selected_ids"], observation)
        if observation["returncode"] or observation["failures"] or observation["errors"]:
            raise subprocess.CalledProcessError(1, [sys.executable, "linux-shard-tests"])
        if report["auxiliary_checks"]:
            linux_auxiliary_validation()
        report["status"] = "success"
    finally:
        report["wall_seconds"] = time.perf_counter() - started
        if report_path is not None:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with Path(summary).open("a", encoding="utf-8") as handle:
                handle.write(
                    f"## Linux Python {report['python_version']} shard {shard_index + 1}/{shard_count}\n\n"
                    f"- status: {report['status']}\n- inventory: {report['inventory_count']}\n"
                    f"- selected/executed/completed: {report['selected_count']}/"
                    f"{len(report.get('executed_ids', []))}/{len(report.get('completed_ids', []))}\n"
                    f"- estimated tests/wall seconds: {report['estimated_test_seconds']:.2f}/"
                    f"{report['wall_seconds']:.2f}\n"
                    f"- workers: {workers}; serial tests: {len(report.get('serial_ids', []))}\n"
                    f"- auxiliary checks: {report['auxiliary_checks']}\n")
        print(json.dumps(report, sort_keys=True))
    return report


def windows_validation() -> None:
    run_native_validation("windows")


def macos_validation() -> None:
    run_native_validation("macos")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", choices=("linux", "windows", "macos"), required=True)
    parser.add_argument("--discover-native", action="store_true")
    parser.add_argument("--shard-index", type=int)
    parser.add_argument("--shard-count", type=int)
    parser.add_argument("--discover-linux", action="store_true")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--workers", type=int, choices=(1, 2), default=1)
    args = parser.parse_args()
    sharded = args.shard_index is not None or args.shard_count is not None
    if sharded or args.discover_linux or args.report or args.workers != 1:
        if args.platform != "linux" or args.discover_native:
            parser.error("Linux shard options require --platform linux")
        if args.shard_index is None or args.shard_count is None:
            parser.error("Both --shard-index and --shard-count are required")
        if args.discover_linux:
            print(json.dumps(linux_shard_plan(args.shard_index, args.shard_count), sort_keys=True))
        else:
            run_linux_shard(args.shard_index, args.shard_count, args.report, args.workers)
        return 0
    if args.discover_native:
        if args.platform == "linux":
            parser.error("--discover-native is for native Windows/macOS validation")
        selected = select_native_tests(discover_native_tests())
        print(json.dumps({"platform": args.platform, "selected_ids": selected, "selected_count": len(selected), "tests_run": 0}, sort_keys=True))
        return 0
    {"linux": linux_validation, "windows": windows_validation, "macos": macos_validation}[args.platform]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
