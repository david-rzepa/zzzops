"""Informational verification costs: bounded local evidence, never workflow authority."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

from engine import GOAL_SCHEMAS

DOCUMENT_LIMIT = 64
HISTORY_LIMIT = 256
TREE_LIMIT = 16
LOOKUP_SECONDS = 2.0
CLEANUP_SECONDS = 1.0
_HASH = re.compile(r"^[0-9a-f]{64}$")
CAVEAT = "informational; machine load and concurrent goal-command workload may differ"


def unavailable(reason, limit=None):
    value = {"status": "unavailable", "reason": reason}
    if limit is not None:
        value["limit"] = limit
    return dict(value, verification=dict(value))


def available_cpus():
    try:
        return max(1, len(os.sched_getaffinity(0)))
    except (AttributeError, OSError):
        return max(1, os.cpu_count() or 1)


def cpu_budget(cpus):
    raw = os.environ.get("ZZZOPS_TEST_WORKERS")
    if raw is None:
        return cpus
    if not raw.isascii() or not raw.isdigit() or int(raw) < 1:
        raise ValueError("ZZZOPS_TEST_WORKERS must be a positive integer")
    return min(cpus, int(raw))


class _Exhausted(Exception):
    def __init__(self, limit):
        self.limit = limit


def _scope(source, current, hash_key, duration_key):
    if not isinstance(source, dict) or not isinstance(current, dict):
        return "legacy_timing"
    if hash_key not in source or duration_key not in source or "environment" not in source:
        return "legacy_timing"
    if (not isinstance(source[hash_key], str) or not _HASH.fullmatch(source[hash_key])
            or type(source[duration_key]) is not int or source[duration_key] < 0
            or not isinstance(source["environment"], dict)):
        return "invalid_evidence"
    if source["environment"] != current.get("environment"):
        return "changed_environment"
    if source[hash_key] != current.get(hash_key):
        return "changed_commands_or_allocation"
    if type(current.get(duration_key)) is not int or current[duration_key] < 0:
        return "invalid_evidence"
    return None


def _comparison(row, current):
    source = row["timing"]
    provenance = {k: row[k] for k in ("goal", "node", "goal_commit", "merge_commit", "tree", "target", "finished_at")}
    reason = _scope(source, current, "plan_sha256", "total_ms")
    if reason:
        result = {"status": "unavailable", "reason": reason, "source": provenance}
    else:
        result = dict(provenance, status="available", total_ms=source["total_ms"],
                      delta_ms=current["total_ms"] - source["total_ms"])
        if type(source.get("verification_ms")) is int and source["verification_ms"] >= 0:
            result["verification_ms"] = source["verification_ms"]
    reason = _scope(source, current, "verification_plan_sha256", "verification_ms")
    if reason:
        narrow = {"status": "unavailable", "reason": reason, "source": provenance}
    else:
        narrow = {"status": "available", "source": provenance, "verification_ms": source["verification_ms"],
                  "delta_ms": current["verification_ms"] - source["verification_ms"],
                  "verification_plan_sha256": source["verification_plan_sha256"], "caveat": CAVEAT}
        if result["status"] == "available":
            result["verification_delta_ms"] = narrow["delta_ms"]
    result["verification"] = narrow
    return result


def select_baseline(candidates, history, *, target, current, code_tree, clock=time.monotonic):
    """Select one proven merged source; qualify both scopes without another search.

    Callers supply accepted documents and their configured graphs, not live refs.
    The process supervisor additionally bounds blocking object/pipe operations.
    """
    deadline = clock() + LOOKUP_SECONDS

    def check():
        if clock() >= deadline:
            raise _Exhausted("deadline")

    try:
        docs = []
        for candidate in candidates:
            check()
            if len(docs) >= DOCUMENT_LIMIT:
                raise _Exhausted("documents")
            docs.append(candidate)
        rows = {}
        for item in docs:
            check()
            doc, graph = item["document"], item["graph"]
            if not isinstance(doc, dict) or doc.get("schema") not in GOAL_SCHEMAS:
                return unavailable("invalid_evidence")
            records = doc.get("records")
            if not isinstance(records, dict):
                return unavailable("invalid_evidence")
            for merge_node, definition in graph.nodes.items():
                if definition.get("op") != "github.merge":
                    continue
                merge = records.get(merge_node) or {}
                if merge.get("status") != "done" or merge.get("ok") is not True:
                    continue
                commit = (merge.get("output") or {}).get("merge_commit")
                if not commit:
                    continue
                pr_selector = graph.selectors[merge_node].get("pr")
                producer = pr_selector.node if pr_selector is not None else None
                if not producer or graph.nodes[producer].get("op") != "git.integrate":
                    continue
                publication = records.get(producer) or {}
                pr = (publication.get("output") or {}).get("pr") or {}
                if (publication.get("status") != "done" or publication.get("ok") is not True
                        or pr.get("base") != target["branch"]):
                    continue
                for node, nd in graph.nodes.items():
                    if nd.get("op") != "checks.run":
                        continue
                    record = records.get(node) or {}
                    if record.get("status") != "done" or record.get("ok") is not True:
                        continue
                    result = (record.get("output") or {}).get("result")
                    if not isinstance(result, dict):
                        return unavailable("invalid_evidence")
                    if result.get("passed") is not True:
                        continue
                    tree = result.get("tree")
                    if not isinstance(tree, str) or not isinstance(record.get("finished_at"), str):
                        return unavailable("invalid_evidence")
                    if pr.get("tree") != tree:
                        continue
                    rows.setdefault(commit, []).append({"goal": item["goal"], "node": node,
                        "goal_commit": item["goal_commit"], "merge_commit": commit,
                        "tree": tree, "target": target["branch"], "finished_at": record["finished_at"],
                        "timing": result.get("timing")})
        if not rows:
            return unavailable("no_prior_run")
        tree_work = 0
        for index, commit in enumerate(history):
            check()
            if index >= HISTORY_LIMIT:
                raise _Exhausted("history")
            if commit not in rows:
                continue
            if tree_work >= TREE_LIMIT:
                raise _Exhausted("trees")
            tree_work += 1
            try:
                observed_tree = code_tree(commit)
            except Exception:
                return unavailable("missing_history")
            check()
            matching = [row for row in rows[commit] if row["tree"] == observed_tree]
            if matching:
                newest = max(matching, key=lambda r: (r["finished_at"], r["goal"], r["node"]))
                return _comparison(newest, current)
        return unavailable("no_prior_run")
    except _Exhausted as error:
        return unavailable("lookup_budget_exhausted", error.limit)
    except (KeyError, TypeError, AttributeError, ValueError):
        return unavailable("invalid_evidence")


def _kill_lookup(proc):
    try:
        if os.name == "nt":
            outcome = subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                                     capture_output=True, timeout=CLEANUP_SECONDS / 2)
            if outcome.returncode == 0:
                return
        else:
            os.killpg(proc.pid, signal.SIGKILL)
            return
    except (OSError, subprocess.TimeoutExpired):
        pass
    try:
        proc.kill()
    except OSError:
        pass


def supervise_lookup(argv, *, input_bytes=None, popen=None, kill_group=None, clock=time.monotonic):
    """One local process group, two seconds work and one second bounded cleanup."""
    popen = popen or subprocess.Popen
    kill_group = kill_group or _kill_lookup
    deadline = clock() + LOOKUP_SECONDS
    group = ({"start_new_session": True} if os.name != "nt"
             else {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP})
    try:
        proc = popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **group)
    except OSError:
        return unavailable("missing_history")
    try:
        kwargs = {"timeout": max(0.0, deadline - clock())}
        if input_bytes is not None:
            kwargs["input"] = input_bytes
        stdout, _ = proc.communicate(**kwargs)
    except subprocess.TimeoutExpired:
        cleanup_end = clock() + CLEANUP_SECONDS
        kill_group(proc)
        try:
            proc.communicate(timeout=max(0.0, cleanup_end - clock()))
        except (subprocess.TimeoutExpired, OSError):
            # kill was already requested; never wait unboundedly for optional evidence.
            pass
        return unavailable("lookup_budget_exhausted", "deadline")
    except OSError:
        cleanup_end = clock() + CLEANUP_SECONDS
        kill_group(proc)
        try:
            proc.communicate(timeout=max(0.0, cleanup_end - clock()))
        except (subprocess.TimeoutExpired, OSError):
            pass
        return unavailable("missing_history")
    if proc.returncode:
        return unavailable("missing_history")
    try:
        result = json.loads(stdout)
        if not isinstance(result, dict) or result.get("status") not in ("available", "unavailable"):
            raise ValueError("invalid lookup result")
        if not isinstance(result.get("verification"), dict):
            raise ValueError("missing verification comparison")
        return result
    except (ValueError, TypeError, UnicodeError):
        return unavailable("invalid_evidence")


def lookup_baseline(ctx, timing):
    """Adapter from an accepted invocation snapshot; no extra fetch or portfolio load."""
    tips = ctx.snap.goals
    if not tips:
        return unavailable("no_prior_run")
    if len(tips) > DOCUMENT_LIMIT:
        return unavailable("lookup_budget_exhausted", "documents")
    state = getattr(ctx.session, "state", None)
    workflow = getattr(state, "workflow", None)
    if not workflow or not ctx.target or not ctx.target.get("tip"):
        return unavailable("invalid_evidence")
    payload = {"primary": ctx.git.primary, "common": ctx.git.common, "now": ctx.now,
               "tips": tips, "workflow": workflow, "target": ctx.target, "current": timing}
    command = [sys.executable, "-c", "import runpy,sys;sys.path.insert(0,sys.argv[1]);"
               "runpy.run_module('engine.test_cost',run_name='__main__')", str(Path(__file__).resolve().parent.parent)]
    return supervise_lookup(command, input_bytes=json.dumps(payload).encode())


def _worker(payload):
    from engine.gitrun import Git
    from engine.identity import Identity
    from engine.schemas import build_graph, validate_goal
    from engine.store import read_goal_json

    git = Git(payload["primary"], payload["common"], payload["now"])
    workflow = payload["workflow"]
    graphs = {name: build_graph(name, value) for name, value in workflow["graphs"].items()}
    try:
        def candidates():
            for goal, tip in payload["tips"].items():
                document, error = read_goal_json(git, tip)
                if error or not isinstance(document, dict):
                    raise ValueError("unreadable accepted goal")
                errors, _ = validate_goal(document, workflow=workflow, reading=True)
                if errors or document.get("id") != int(goal):
                    raise ValueError("invalid accepted goal")
                yield {"goal": int(goal), "goal_commit": tip, "document": document,
                       "graph": graphs[document["graph"]]}
        # At most one extra item signals a truncated history. The supervisor bounds
        # the Git call too, including object IO and identity's code-tree operations.
        history = git.out("rev-list", "--first-parent", f"--max-count={HISTORY_LIMIT + 1}",
                          payload["target"]["tip"]).splitlines()
        return select_baseline(candidates(), history, target=payload["target"], current=payload["current"],
                               code_tree=Identity(git).code_tree)
    finally:
        git.close()


if __name__ == "__main__":
    try:
        value = _worker(json.load(sys.stdin))
    except Exception:
        value = unavailable("invalid_evidence")
    print(json.dumps(value, sort_keys=True))
