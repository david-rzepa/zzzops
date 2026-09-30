"""Public regressions for publication through a provider-observed PR chain."""

from __future__ import annotations

import contextlib
import copy
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest import mock

# Bootstrap the shared plugin module before importing fixtures that reuse it.
import test_zzzops  # noqa: F401
import test_workflow_journey as journey_fixtures
import test_workflow_owned_outputs as public_fixtures


z = journey_fixtures.z


class ProviderTopologySession(public_fixtures.PublicSession):
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
                mock.patch.object(api, "workflow_context_step", return_value=None),
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
        self.fixture = journey_fixtures.FullWorkflowJourneyTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        control = tempfile.TemporaryDirectory()
        self.addCleanup(control.cleanup)
        self.repo = self.fixture.repo
        for name, content in {
            "source.py": "def answer():\n    return 1\n",
            "behavior_test.py": "from source import answer\nassert answer() == 1\n",
            "read_dependency.txt": "unchanged dependency\n",
        }.items():
            (self.repo / name).write_text(content)
        self.session = ProviderTopologySession(
            self.repo, self.fixture.project, self.fixture.runtime,
            self.fixture.provider, control.name,
            pull_request_states=self._pull_request_states,
        )
        self.session.git("add", "source.py", "behavior_test.py", "read_dependency.txt")
        self.session.git("commit", "-qm", "fixture: existing source and test")
        self._build_provider_chain()
        self.fixture.provider.issues[102] = self.fixture.issue(
            102, parent=None, title="Known chain tip",
        )
        self.fixture.provider.comments[102] = []
        self.fixture.provider.issues[103] = self.fixture.issue(
            103, parent=None, title="Known competing stack",
        )
        self.fixture.provider.comments[103] = []
        self._record_fixture_implementation(102, "chain-5", "chain-4")
        self._record_fixture_implementation(103, "competing", "dev")
        self.session.git("checkout", "-q", "-B", "candidate-6", "chain-5")
        self.session.prepare()
        self._set_candidate("candidate-6", "chain-5", target="chain-5")
        self.session.design()
        self.session.implement()
        self.session.git("add", "source.py")
        self.session.git("commit", "-qm", "feat: required behavior")
        self.heads["candidate-6"] = self.session.git("rev-parse", "candidate-6")

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

    def _record_fixture_implementation(self, number, branch, base):
        issue = self.fixture.provider.issues[number]
        goal = z.parse_managed_goal(issue["body"], number)
        goal["implementation"].update(branch=branch, base=base, target="dev")
        issue["body"] = z.render_managed_goal(
            goal, z._goals.compact_human_goal_text(issue["body"]), number,
        )

    def _set_candidate(self, branch, base, *, target="dev", managed_ancestor="chain-4"):
        s = self.session
        parent = s.goal(100)
        parent_implementation = copy.deepcopy(parent["implementation"])
        parent_implementation.update(branch=managed_ancestor, base="dev", target="dev")
        s.call(100, {"operation": "revise", "expected_digest": parent["digest"],
                     "changes": {"implementation": parent_implementation}})
        child = s.goal(101)
        child_implementation = copy.deepcopy(child["implementation"])
        child_implementation.update(
            branch=branch, base=base, target=target, pr=None,
        )
        s.call(101, {"operation": "revise", "expected_digest": child["digest"],
                     "changes": {"implementation": child_implementation}})
        self.candidate_branch, self.candidate_base = branch, base
        s.git("checkout", "-q", branch)

    def _pull_request_states(self, _repo, executable, selected, bodies):
        self.assertEqual("gh", executable)
        self.assertEqual([], [item["number"] for item in selected])
        self.assertIn(101, bodies)
        return ({101: {
            "merged": False, "merged_at": None,
            "head_oid": self.heads[self.candidate_branch],
            "base_oid": self.heads.get(self.candidate_base, self.session.git("rev-parse", "dev")),
            "base_ref": self.candidate_base, "merge_commit": None,
            "repository": "owner/repo", "checks_verified": True,
            "review_verified": False,
        }}, 512, 1)

    def pulls(self, links):
        return [{"number": 10 + index, "url": f"https://github.com/owner/repo/pull/{10 + index}",
                 "headRefName": head, "baseRefName": base,
                 "headRefOid": self.heads[head]}
                for index, (head, base) in enumerate(links, 1)]

    def observe(self, pulls, *, expected=0):
        self.session.open_pulls = copy.deepcopy(pulls)
        before_issues = copy.deepcopy(self.session.provider.issues)
        before_comments = copy.deepcopy(self.session.provider.comments)
        response = self.session.call(101, expected=expected)
        self.assertEqual(before_issues, self.session.provider.issues)
        self.assertEqual(before_comments, self.session.provider.comments)
        return response["next_steps"]

    def assert_publish_frontier(self, steps):
        publication = next(
            (step for step in steps if step.get("phase") == "publish"), None,
        )
        self.assertIsNotNone(publication, f"expected normal publish frontier, got {steps}")
        self.assertIn(publication["kind"], {"assess", "execute", "review", "human_approval"})

    def assert_safe_repair(self, steps, *identities):
        repair = next(
            (step for step in steps if step.get("kind") == "repair_stack"), None,
        )
        self.assertIsNotNone(repair, f"expected safe repair routing, got {steps}")
        rendered = json.dumps(repair)
        for identity in identities:
            self.assertIn(identity, rendered)
        self.assertRegex(rendered, r"(?i)(dev|root|continue)")
        self.assertNotRegex(rendered, r"(?i)(force|rewrite all|blind)")

    def test_public_execute_resolves_sparse_chain_and_preserves_safe_rejections(self):
        linear = self.pulls([
            ("chain-1", "dev"), ("chain-2", "chain-1"),
            ("chain-3", "chain-2"), ("chain-4", "chain-3"),
            ("chain-5", "chain-4"),
        ])

        # The unpublished candidate directly targets the exact chain-5 tip. Its
        # target is an immediate PR base, while dev remains the integration root.
        with self.subTest(label="sparse five-PR exact-tip chain"):
            self.assert_publish_frontier(self.observe(linear))

        # An unmanaged PR rooted independently at dev is outside this managed chain.
        unrelated = {"number": 99, "url": "https://github.com/owner/repo/pull/99",
                     "headRefName": "unrelated", "baseRefName": "dev", "headRefOid": "9" * 40}
        with self.subTest(label="unrelated unmanaged dev-root PR"):
            self.assert_publish_frontier(self.observe(linear + [unrelated]))

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

        cases = [
            ("fork", linear + [{"number": 88, "url": "https://github.com/owner/repo/pull/88",
                                "headRefName": "fork-2", "baseRefName": "chain-1", "headRefOid": "8" * 40}],
             ("chain-2", "fork-2", "#88")),
            ("missing anchor", linear[1:], ("chain-2", "chain-1", "#12")),
            ("cycle", self.pulls([("chain-1", "chain-5"), ("chain-2", "chain-1"),
                                  ("chain-3", "chain-2"), ("chain-4", "chain-3"),
                                  ("chain-5", "chain-4")]), ("chain-1", "chain-5", "#11")),
            ("malformed", [*linear[:-1], {"number": 15, "url": "https://github.com/owner/repo/pull/15",
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
        drifted[-1]["headRefOid"] = "d" * 40
        with self.subTest(label="candidate head drift"):
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
