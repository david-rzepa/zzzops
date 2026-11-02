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
# Genuine per-invocation exclusive tests can run after all concurrent children join.
# Commands needing isolation from other invocations must be scheduled sequentially.
LINUX_EXCLUSIVE_TESTS: tuple[str, ...] = ()

NATIVE_COVERAGE = {
    "installation_cleanup": (
        "test_legacy_cleanup.LegacyCleanupTests.test_default_cli_is_dry_run_and_interrupted_cleanup_converges",
    ),
    "marketplace_package": (
        "test_marketplace_bundle.MarketplaceBundleTests.test_fixed_version_build_is_deterministic_and_complete",
        "test_marketplace_bundle.MarketplaceBundleTests.test_generated_claude_marketplace_passes_the_full_package_check",
        "test_marketplace_bundle.MarketplaceBundleTests.test_package_check_assertion_fails_on_a_wrong_channel_build_with_a_claude_hint",
        "test_agent_plugin.AgentPluginTests.test_marketplace_points_to_the_self_contained_package",
    ),
    "package_cli": ("test_engine_docs.CliWithoutRepositoryTests.test_help_and_policy_validation_need_no_repository",),
    "git_crlf_drift": (
        "test_engine_identity.IdentityTests.test_crlf_checkout_gives_the_same_identities",
        "test_engine_identity.IdentityTests.test_identity_under_hostile_global_configuration",
        "test_engine_identity.IdentityTests.test_text_input_reaches_git_unchanged",
    ),
    "path_confinement": ("test_engine_identity.IdentityTests.test_i1_i2_and_artifact_commits",),
    "goal_journey": ("test_engine_lifecycle.SubmitTests.test_new_creates_no_branch_and_first_artifact_does",),
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
    "failure_details": [{"id": test.id(), "traceback": detail} for test, detail in result.failures],
    "error_details": [{"id": test.id(), "traceback": detail} for test, detail in result.errors],
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
            cwd=root, check=False, stderr=subprocess.PIPE, encoding="utf-8", errors="replace",
        )
        diagnostic = completed.stderr or ""
        if diagnostic:
            print(diagnostic, end="", file=sys.stderr)
        if not report_path.stat().st_size:
            raise RuntimeError(f"native test subprocess exited {completed.returncode} without a report: {diagnostic}")
        observation = json.loads(report_path.read_text(encoding="utf-8"))
        observation["stderr"] = diagnostic
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
    workers: int = 1,
) -> dict:
    started = clock()
    discovered = discover() if discover is not None else discover_native_tests(root=root)
    selected = select_native_tests(discovered)
    if type(workers) is not int or workers not in (1, 2):
        raise ValueError("Native workers must be 1 or 2")
    launch_child = launch if launch is not None else lambda batch: _launch_native(batch, Path(root))
    worker_reports = []
    if workers == 1:
        observation = dict(launch_child(selected))
    else:
        weights, fallback = load_linux_timings()
        batches = partition_linux_tests(selected, min(workers, len(selected)), weights,
                                        fallback, auxiliary_seconds=0.0)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(launch_child, batch) for batch in batches]
            for index, (batch, future) in enumerate(zip(batches, futures)):
                child = dict(future.result())
                # Completion/count checks supplement the same native facility skip rules.
                _validate_linux_observation(batch, child)
                worker_reports.append({"worker_index": index, "selected_ids": batch,
                                       "observation": child})
        observation = _combine_linux_observations([worker["observation"] for worker in worker_reports])
        _validate_linux_observation(selected, observation)
    elapsed = clock() - started
    _validate_observation(selected, observation)
    durations = {key: float(value) for key, value in observation.get("durations", {}).items()}
    report = {
        "platform": platform, "selected_ids": selected, "selected_count": len(selected),
        "workers": workers, "worker_reports": worker_reports,
        "executed_ids": list(observation["executed_ids"]),
        "completed_ids": list(observation.get("completed_ids", [])),
        "tests_run": observation["tests_run"], "failures": observation.get("failures", 0),
        "errors": observation.get("errors", 0), "skipped": len(observation.get("skips", ())),
        "failure_details": list(observation.get("failure_details", [])),
        "error_details": list(observation.get("error_details", [])),
        "coverage_limits": list(observation.get("skips", ())), "wall_seconds": elapsed,
        "aggregate_test_seconds": sum(durations.values()),
        "slowest_tests": sorted(durations.items(), key=lambda item: item[1], reverse=True)[:5],
        "slowest_groups": _group_timings(durations),
    }
    (emit or (lambda value: print(json.dumps(value, sort_keys=True))))(report)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        write_step_summary(report, Path(os.environ["GITHUB_STEP_SUMMARY"]))
    if observation.get("returncode", 0) or observation.get("failures", 0) or observation.get("errors", 0):
        raise subprocess.CalledProcessError(int(observation.get("returncode") or 1), [sys.executable, "native-tests"])
    return report


def write_step_summary(report: Mapping, path: Path) -> None:
    lines = [
        f"## Native validation: {report['platform']}", "", f"- selected: {report['selected_count']}",
        f"- tests run: {report['tests_run']}",
        f"- workers: {report.get('workers', 1)}",
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
                "durations": {}, "failure_details": [], "error_details": []}
    for observation in observations:
        for key in ("tests_run", "failures", "errors"):
            combined[key] += observation[key]
        combined["returncode"] = max(combined["returncode"], observation["returncode"])
        for key in ("executed_ids", "completed_ids", "skips", "invalid_skips", "failure_details", "error_details"):
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
            "skips", "invalid_skips", "durations", "failure_details", "error_details",
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


def available_local_cpus() -> int:
    """Observe this process's affinity before falling back to the portable CPU count."""
    try:
        count = len(os.sched_getaffinity(0))
        if count:
            return count
    except (AttributeError, OSError, NotImplementedError):
        pass
    count = os.cpu_count()
    return count if type(count) is int and count > 0 else 1


def local_worker_budget(workers: int | None = None) -> tuple[int, int]:
    available = available_local_cpus()
    if workers is not None and (type(workers) is not int or workers <= 0):
        raise ValueError("Local workers must be a positive integer")
    budget = os.environ.get("ZZZOPS_TEST_WORKERS")
    if budget is not None:
        if not budget.isascii() or not budget.isdecimal() or int(budget) <= 0:
            raise ValueError("ZZZOPS_TEST_WORKERS must be a positive integer")
        available_budget = min(available, int(budget))
    else:
        available_budget = available
    return available, min(available_budget, workers) if workers is not None else available_budget


def run_local_validation(root: Path = ROOT, workers: int | None = None,
                         report_path: Path | None = None) -> dict:
    """Run every canonical Python ID once; local mode never runs the CI auxiliary leg."""
    started = time.perf_counter()
    report = {"schema_version": 1, "platform": "linux", "mode": "local",
              "python_version": sys.version.split()[0], "status": "failed", "workers": 0,
              "inventory_count": 0, "inventory_sha256": None, "selected_count": 0, "selected_ids": [],
              "worker_reports": [], "executed_ids": [], "completed_ids": [], "durations": {},
              "tests_run": 0, "returncode": 1, "failures": 0, "errors": 0,
              "skips": [], "invalid_skips": [], "serial_ids": [], "aggregate_test_seconds": 0.0,
              "failure_details": [], "error_details": []}
    try:
        observed, budget = local_worker_budget(workers)
        inventory = list(discover_linux_tests(Path(root)))
        if not inventory or len(inventory) != len(set(inventory)):
            raise ValueError("Local discovery inventory is empty or contains duplicate IDs")
        inventory.sort()
        missing = set(LINUX_EXCLUSIVE_TESTS) - set(inventory)
        if missing:
            raise ValueError("Local exclusive test IDs missing from discovery: " + ", ".join(sorted(missing)))
        exclusive = sorted(set(inventory) & set(LINUX_EXCLUSIVE_TESTS))
        concurrent = [test_id for test_id in inventory if test_id not in exclusive]
        count = min(budget, len(concurrent))
        report.update({"observed_cpus": observed, "cpu_budget": budget, "workers": count,
                       "inventory_count": len(inventory), "selected_count": len(inventory),
                       "inventory_sha256": hashlib.sha256("\n".join(inventory).encode()).hexdigest(),
                       "selected_ids": inventory, "serial_ids": exclusive, "concurrent_worker_count": count})
        weights, fallback = load_linux_timings()
        batches = partition_linux_tests(concurrent, count, weights, fallback, auxiliary_seconds=0.0) if count else []

        def launch(index, batch, serial):
            began = time.perf_counter()
            worker = {"worker_index": index, "serial": serial, "selected_ids": batch}
            try:
                worker["observation"] = dict(_launch_native(batch, Path(root)))
            except Exception as error:
                worker["error"] = str(error)
            finally:
                worker["wall_seconds"] = time.perf_counter() - began
            return worker

        if batches:
            with ThreadPoolExecutor(max_workers=count) as pool:
                futures = [pool.submit(launch, index, batch, False) for index, batch in enumerate(batches)]
                # Every future is collected before validation or the serial phase, including failed children.
                report["worker_reports"] = [future.result() for future in futures]
        if exclusive:
            report["worker_reports"].append(launch(len(batches), exclusive, True))
        observations = [worker["observation"] for worker in report["worker_reports"] if "observation" in worker]
        if observations:
            observation = _combine_linux_observations(observations)
            report.update({key: observation[key] for key in (
                "returncode", "tests_run", "executed_ids", "completed_ids", "failures", "errors",
                "skips", "invalid_skips", "durations", "failure_details", "error_details")})
        for worker in report["worker_reports"]:
            if "error" in worker:
                raise RuntimeError(worker["error"])
            _validate_linux_observation(worker["selected_ids"], worker["observation"])
            durations = worker["observation"].get("durations")
            if not isinstance(durations, dict) or set(durations) != set(worker["selected_ids"]):
                raise ValueError("Local execution lacks exact per-test durations")
            if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0
                   for value in durations.values()):
                raise ValueError("Local durations must be finite nonnegative seconds")
        _validate_linux_observation(inventory, observation)
        if observation["returncode"] or observation["failures"] or observation["errors"]:
            raise subprocess.CalledProcessError(int(observation["returncode"] or 1), [sys.executable, "local-tests"])
        report["status"] = "success"
    except Exception as error:
        report["error"] = str(error)
        if type(report["returncode"]) is not int or report["returncode"] <= 0:
            report["returncode"] = 1
        raise
    finally:
        report["wall_seconds"] = time.perf_counter() - started
        durations = {test_id: value for test_id, value in report["durations"].items()
                     if type(value) in (int, float) and math.isfinite(value) and value >= 0}
        report["aggregate_test_seconds"] = sum(durations.values())
        report["slowest_tests"] = sorted(durations.items(), key=lambda item: (-item[1], item[0]))[:5]
        if report_path is not None:
            path = Path(report_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        summary = {key: report[key] for key in ("status", "inventory_count", "inventory_sha256", "workers",
                                                "wall_seconds", "aggregate_test_seconds", "slowest_tests")}
        summary.update(executed_count=len(report["executed_ids"]), completed_count=len(report["completed_ids"]),
                       worker_seconds=[worker["wall_seconds"] for worker in report["worker_reports"]])
        if "error" in report:
            summary["error"] = report["error"][:400]
        print(json.dumps(summary, sort_keys=True))
    return report


def windows_validation() -> None:
    run_native_validation("windows")


def macos_validation() -> None:
    run_native_validation("macos")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", choices=("linux", "windows", "macos"), required=True)
    parser.add_argument("--discover-native", action="store_true")
    parser.add_argument("--local", action="store_true")
    parser.add_argument("--shard-index", type=int)
    parser.add_argument("--shard-count", type=int)
    parser.add_argument("--discover-linux", action="store_true")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--workers", type=int)
    args = parser.parse_args()
    sharded = args.shard_index is not None or args.shard_count is not None
    if args.local:
        if args.platform != "linux" or sharded or args.discover_native or args.discover_linux:
            parser.error("--local requires --platform linux and cannot combine with discovery or CI shard options")
        if args.workers is not None and args.workers <= 0:
            parser.error("Local --workers must be a positive integer")
        run_local_validation(workers=args.workers, report_path=args.report)
        return 0
    args.workers = 1 if args.workers is None else args.workers
    if args.workers not in (1, 2):
        parser.error("Non-local --workers must be 1 or 2")
    if sharded or args.discover_linux or args.report or (args.platform == "linux" and args.workers != 1):
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
    if args.platform == "linux":
        linux_validation()
    else:
        run_native_validation(args.platform, workers=args.workers)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
