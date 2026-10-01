"""Public regressions for publication through a provider-observed PR chain."""

from __future__ import annotations

import contextlib
import copy
import io
import json
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace
import unittest
from unittest import mock

# Bootstrap the shared plugin module before importing fixtures that reuse it.
import test_zzzops  # noqa: F401
import test_evidence_dag_journeys as dag_fixtures
import test_workflow_publication_contract as publication_fixtures


z = dag_fixtures.z


class ProviderTopologySession(dag_fixtures.TaskSession):
    """Public dispatcher with only the external PR-list boundary made synthetic."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.open_pulls = []

    def call(self, number, payload=None, *, expected=0):
        self.sequence += 1
        runtime = self.control / "runtime.json"
        runtime.write_text(json.dumps(self.runtime))
        argv = ["zzzops", "--repo", str(self.repo), "workflow", "--intent", "execute",
                "--goal", str(number), "--runtime", str(runtime)]
        if payload is not None:
            payload = copy.deepcopy(payload)
            payload.setdefault("request_id", f"public-{time.time_ns()}-{self.sequence}")
            request = self.control / "input.json"
            request.write_text(json.dumps(payload))
            argv += ["--input", str(request)]
        api = self.api
        real_run = subprocess.run

        def provider_command(command, *args, **kwargs):
            if list(command[:3]) == ["gh", "pr", "list"]:
                return subprocess.CompletedProcess(
                    command, 0, stdout=json.dumps(self.open_pulls), stderr="",
                )
            return real_run(command, *args, **kwargs)

        with contextlib.ExitStack() as stack:
            patches = [
                mock.patch.object(subprocess, "run", side_effect=provider_command),
                mock.patch.object(api, "configure_cli_stdout"),
                mock.patch.object(api._package, "package_status", return_value={"ok": True}),
                # Initialization inspection is an external configuration read;
                # keep workflow_context_step itself real.
                mock.patch.object(api, "inspect_initialization", return_value={"initialized": True}),
                mock.patch.object(api, "reviewed_project_state", side_effect=lambda _repo: copy.deepcopy(self.project)),
                mock.patch.object(api, "GitHubGoalTransitionAdapter", return_value=self.provider),
                mock.patch.object(api, "GitHubReservationAdapter", return_value=SimpleNamespace()),
                mock.patch.object(api, "portfolio_snapshot", side_effect=self.portfolio_snapshot),
                mock.patch.object(api, "acquire_storage_lock", side_effect=lambda *_a, **_k: {"acquired": True, "expires_at": time.time() + 300}),
                mock.patch.object(api, "renew_storage_lock", side_effect=lambda *_a, **_k: {"acquired": True, "expires_at": time.time() + 300}),
                mock.patch.object(api, "release_storage_lock", return_value={"released": True}),
                mock.patch.object(api._heartbeat, "stop_heartbeat"),
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(sys, "stdout", io.StringIO()),
            ]
            for patch in patches:
                stack.enter_context(patch)
            code = api.main()
            response = json.loads(sys.stdout.getvalue())
        self.calls.append({"operation": (payload or {}).get("operation", "checkpoint"),
                           "goal": number, "code": code, "response": response})
        if expected is not None and code != expected:
            raise AssertionError(
                f"public {number} {(payload or {}).get('operation', 'checkpoint')}: "
                f"expected exit {expected}, got {code}: {response}"
            )
        return response


class PublicationAncestorChainPublicTests(unittest.TestCase):
    def setUp(self):
        # Composition avoids rediscovering the publication fixture's own tests.
        self.fixture = publication_fixtures.GenericPublicationPublicTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.repo = self.fixture.fixture.repo
        self.branch_review = (
            Path(__file__).parents[1]
            / "plugins/zzzops/skills/execute-zzzops/references/BRANCH_REVIEW.md"
        ).read_text()
        old = self.fixture.session
        self.session = ProviderTopologySession(
            old.repo, old.project, old.runtime, old.provider, old.control,
        )
        self.fixture.session = self.session
        self._build_provider_chain()
        self.session.git("checkout", "-q", "-B", "candidate-6", "chain-5")
        (self.repo / "candidate.txt").write_text("candidate change\n")
        self.session.git("add", "candidate.txt")
        self.session.git("commit", "-qm", "fixture: candidate change")
        self.heads["candidate-6"] = self.session.git("rev-parse", "HEAD")
        self.provider_queries = []
        patch = mock.patch.object(z, "_github_pull_request_states", side_effect=self._pull_request_states)
        patch.start()
        self.addCleanup(patch.stop)
        self._record_managed_context(102, "chain-5", "chain-4", 15)
        self._record_managed_context(103, "competing", "dev", 77)

    def _authorize_candidate(self, *, published=False):
        f = self.fixture
        f.context = {"branch": "candidate-6", "base": "chain-5", "target": "chain-5",
                     "pr": "https://github.com/owner/repo/pull/16" if published else None}
        f.submit_role("context", f.context)
        f.submit_role("inspect", "Exact candidate context reviewed", actor="context-reviewer")
        f.submit_role("consent", {"context": f.produced("context"),
            "policy": dag_fixtures.content_hash(self.session.project["policy"]), "decision": "approved"})

    def _record_managed_context(self, number, branch, base, pr):
        """Other managed branches have real generic root/review/consent Results."""
        f = self.fixture
        graph = copy.deepcopy(f.graph)
        graph["nodes"] = [node for node in graph["nodes"] if node["id"] in {"context", "inspect", "consent"}]
        graph["terminals"] = [{"kind": "node", "goal": number, "node": "consent"}]
        def qualify(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    if key == "goal" and child == 100:
                        value[key] = number
                    else:
                        qualify(child)
            elif isinstance(value, list):
                for child in value:
                    qualify(child)
        qualify(graph)
        payload = f.blob({"spec": f.blob({"type": "specification", "content": "Managed repository context",
            "producer": None, "provenance": {"actor": "root-thread", "source": None,
            "policy": dag_fixtures.content_hash(self.session.project["policy"])}}),
            "graph": f.blob(graph), "evidence": [], "operational": {"leases": [], "receipts": []}})
        envelope = {"schema_version": 2, "repository": "owner/repo", "issue": number,
                    "revision": 1, "state": "open", "parent": None, "payload": payload}
        self.session.provider.issues[number] = {**copy.deepcopy(self.session.provider.issues[100]),
            "number": number, "body": "<!-- zzzops-goal\n" + json.dumps(envelope) + "\nzzzops-goal -->"}
        self.session.provider.comments[number] = copy.deepcopy(self.session.provider.comments[100])
        work = self.session.acquire("context", number=number)
        self.session.finish(work, {"value": {"branch": branch, "base": base, "target": "dev",
            "pr": f"https://github.com/owner/repo/pull/{pr}"}}, number=number)
        work = self.session.acquire("inspect", number=number, actor="context-reviewer")
        self.session.finish(work, {"value": "Independent managed context review"}, number=number)
        # Read the host-written Result through the public artifact API.
        issue = self.session.provider.issues[number]
        envelope = z.parse_managed_goal(issue["body"], number)
        payload = self.session.read(number, envelope["payload"])
        results = [self.session.read(number, ref) for ref in payload["evidence"]]
        context = next(result["content"]["outputs"]["value"] for result in results
                       if result["type"] == "result" and result["content"]["node"]["node"] == "context")
        work = self.session.acquire("consent", number=number)
        self.session.finish(work, {"value": {"context": context,
            "policy": dag_fixtures.content_hash(self.session.project["policy"]), "decision": "approved"}}, number=number)

    def _build_provider_chain(self):
        s = self.session
        s.git("checkout", "-q", "dev")
        self.heads = {}
        previous = "dev"
        for index in range(1, 6):
            branch = f"chain-{index}"
            s.git("checkout", "-q", "-B", branch, previous)
            (self.repo / f"chain-{index}.txt").write_text(f"{branch}\n")
            s.git("add", f"chain-{index}.txt")
            s.git("commit", "-qm", f"fixture: {branch}")
            self.heads[branch] = s.git("rev-parse", "HEAD")
            previous = branch
        s.git("checkout", "-q", "-B", "competing", "dev")
        (self.repo / "competing.txt").write_text("competing\n")
        s.git("add", "competing.txt")
        s.git("commit", "-qm", "fixture: competing managed stack")
        self.heads["competing"] = s.git("rev-parse", "HEAD")

    def _pull_request_states(self, _repo, executable, selected, bodies):
        self.assertEqual("gh", executable)
        self.provider_queries.append(copy.deepcopy((selected, bodies)))
        facts = {}
        for item in selected:
            number = item["number"]
            context = bodies[number].get("repository_context", {})
            # A null PR has no individual PR, checks, review, or merge facts.
            if context.get("pr") is None:
                continue
            self.assertEqual(100, number)
            self.assertEqual("https://github.com/owner/repo/pull/16", context["pr"])
            facts[number] = {"merged": False, "merged_at": None,
                "head_oid": self.heads["candidate-6"], "base_oid": self.heads["chain-5"],
                "base_ref": "chain-5", "merge_commit": None,
                "repository": "owner/repo", "checks_present": True,
                "checks_verified": True, "review_verified": False}
        return facts, 512, 1

    def pulls(self, links):
        return [{"number": 10 + index, "url": f"https://github.com/owner/repo/pull/{10 + index}",
                 "headRefName": head, "baseRefName": base,
                 "headRefOid": self.heads[head]}
                for index, (head, base) in enumerate(links, 1)]

    def observe(self, pulls, *, expected=0):
        self.session.open_pulls = copy.deepcopy(pulls)
        if self.fixture.context["pr"] and not any(row.get("headRefName") == "candidate-6" for row in pulls):
            self.session.open_pulls.append({"number": 16, "url": self.fixture.context["pr"],
                "headRefName": "candidate-6", "baseRefName": "chain-5",
                "headRefOid": self.heads["candidate-6"]})
        before_pulls = copy.deepcopy(self.session.open_pulls)
        before_issues = copy.deepcopy(self.session.provider.issues)
        before_comments = copy.deepcopy(self.session.provider.comments)
        before_refs = self.session.git(
            "for-each-ref", "--format=%(refname):%(objectname)", "refs/heads",
        )
        response = self.session.call(100, expected=expected)
        self.assertEqual(before_pulls, self.session.open_pulls)
        self.assertEqual(before_issues, self.session.provider.issues)
        self.assertEqual(before_comments, self.session.provider.comments)
        self.assertEqual(
            before_refs,
            self.session.git("for-each-ref", "--format=%(refname):%(objectname)", "refs/heads"),
        )
        return response["next_steps"]

    def assert_publish_frontier(self, steps):
        publication = next(
            (step for step in steps if step.get("node", {}).get("node") == "observe"
             and step.get("kind") == "execute"), None,
        )
        self.assertIsNotNone(publication, f"expected normal publish frontier, got {steps}")
        self.assertEqual("start", publication["start"]["operation"])
        self.assertEqual("chain-5", publication["base_branch"])
        self.assertEqual(self.heads["chain-5"], publication["base_commit"])
        self.assertIn("input_hash", publication)

    def assert_safe_repair(self, steps, *identities):
        repair = next(
            (step for step in steps if step.get("kind") == "repair_stack"), None,
        )
        self.assertIsNotNone(repair, f"expected safe repair routing, got {steps}")
        self.assertFalse(any(step.get("kind") == "execute" and
                             step.get("node", {}).get("node") == "observe" for step in steps),
                         "Unsafe topology must not also grant publication work")
        rendered = json.dumps(repair)
        for identity in identities:
            self.assertIn(identity, rendered)
        action = repair["action"]
        continuation = repair.get("continuation", action)
        self.assertIn("dev", continuation.lower())
        self.assertRegex(continuation, r"(?i)(continue|rooted|from dev|dev root)")
        self.assertNotRegex(action, r"(?i)(force|rewrite all|blind)")
        self.assertNotEqual(
            "Rebase open PRs into one linear stack before publication.", action,
        )
        # BRANCH_REVIEW prescribes chained-PR fallback or blocking while
        # preserving immediate bases. This repair_stack blocks publication;
        # observe() proves it leaves provider observations and local refs intact.
        self.assertIn("immediate base", self.branch_review)
        self.assertIn("chained PRs", self.branch_review)
        self.assertIn("follow PROJECT's fallback or block", self.branch_review)
        self.assertEqual("root", repair["assignment"])

    def linear(self):
        return self.pulls([
            ("chain-1", "dev"), ("chain-2", "chain-1"),
            ("chain-3", "chain-2"), ("chain-4", "chain-3"),
            ("chain-5", "chain-4"),
        ])

    def test_public_unpublished_candidate_accepts_sparse_chain_and_unmanaged_root(self):
        self._authorize_candidate()
        linear = self.linear()
        # The unpublished candidate directly targets the exact chain-5 tip. Its
        # target is an immediate PR base, while dev remains the integration root.
        with self.subTest(label="sparse five-PR exact-tip chain"):
            self.assert_publish_frontier(self.observe(linear))

        # An unmanaged PR rooted independently at dev is outside this managed chain.
        unrelated = {"number": 99, "url": "https://github.com/owner/repo/pull/99",
                     "headRefName": "unrelated", "baseRefName": "dev", "headRefOid": "9" * 40}
        with self.subTest(label="unrelated unmanaged dev-root PR"):
            self.assert_publish_frontier(self.observe(linear + [unrelated]))

    def test_public_published_candidate_with_successor_keeps_immediate_base(self):
        self._authorize_candidate(published=True)
        linear = self.linear()
        observed_candidate = [
            *linear,
            {"number": 16, "url": "https://github.com/owner/repo/pull/16",
             "headRefName": "candidate-6", "baseRefName": "chain-5",
             "headRefOid": self.heads["candidate-6"]},
            {"number": 17, "url": "https://github.com/owner/repo/pull/17",
             "headRefName": "successor-7", "baseRefName": "candidate-6",
             "headRefOid": "7" * 40},
        ]
        with self.subTest(label="observed candidate with successor"):
            self.assert_publish_frontier(self.observe(observed_candidate))

    def test_public_unpublished_candidate_rejects_unsafe_topology_without_mutation(self):
        self._authorize_candidate()
        self._reject_unsafe_topologies()

    def test_public_published_candidate_rejects_unsafe_topology_without_mutation(self):
        self._authorize_candidate(published=True)
        self._reject_unsafe_topologies()

    def _reject_unsafe_topologies(self):
        linear = self.linear()
        cases = [
            ("fork", linear + [{"number": 88, "url": "https://github.com/owner/repo/pull/88",
                                "headRefName": "fork-2", "baseRefName": "chain-1", "headRefOid": "8" * 40}],
             ("chain-2", "fork-2", "#88")),
            ("missing anchor", linear[1:], ("chain-2", "chain-1", "#12")),
            ("cycle", self.pulls([("chain-1", "chain-5"), ("chain-2", "chain-1"),
                                  ("chain-3", "chain-2"), ("chain-4", "chain-3"),
                                  ("chain-5", "chain-4")]), ("chain-1", "chain-5", "#11")),
            ("malformed", [*[row for row in linear if row["headRefName"] != "chain-5"], {"number": 15, "url": "https://github.com/owner/repo/pull/15",
                                           "headRefName": "chain-5", "baseRefName": "chain-4"}],
             ("chain-5", "#15")),
            ("competing managed stack", linear + [{"number": 77, "url": "https://github.com/owner/repo/pull/77",
                                                    "headRefName": "competing", "baseRefName": "dev",
                                                    "headRefOid": self.heads["competing"]}],
             ("competing", "chain-1", "#77")),
        ]
        for label, pulls, identities in cases:
            with self.subTest(label=label):
                self.assert_safe_repair(self.observe(pulls), *identities)

        drifted = copy.deepcopy(linear)
        next(row for row in drifted if row["headRefName"] == "chain-5")["headRefOid"] = "d" * 40
        with self.subTest(label="provider ancestor head drift"):
            self.assert_safe_repair(self.observe(drifted), "chain-5", "#15")

        changed_base = self.heads["chain-5"]
        self.session.git("checkout", "-q", "chain-5")
        (self.repo / "drift.txt").write_text("changed\n")
        self.session.git("add", "drift.txt")
        self.session.git("commit", "-qm", "fixture: drift base")
        self.session.git("checkout", "-q", "candidate-6")
        try:
            with self.subTest(label="base drift"):
                self.assert_safe_repair(self.observe(linear), "chain-4", "chain-5")
        finally:
            self.session.git("branch", "-f", "chain-5", changed_base)

if __name__ == "__main__":
    unittest.main()
