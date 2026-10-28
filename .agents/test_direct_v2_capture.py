"""Regression contract for direct schema-2 public goal capture."""
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import re
import shutil
import sys
import tempfile
import unittest
from unittest import mock

import test_evidence_dag_journeys as dag
import test_graph_compiler as compiler_cases


class DirectV2CaptureTests(dag.DagFixture):
    # This is the installed-boundary smoke's in-process public equivalent:
    # PublicSession calls the shipped public workflow dispatcher for capture,
    # then checkpoint() calls that same dispatcher with targeted execute.
    HUMAN_SPEC = (
        "## Outcome\nPreserve the approved words byte for byte.\n\n"
        "## Acceptance criteria\n"
        "- [ ] The new goal is schema 2 before it becomes managed.\n"
        "- [ ] A fresh execute observes the reviewed workflow.\n"
        "\n  \t\n"
    )

    def setUp(self):
        super().setUp()
        reviewed = compiler_cases.default_graph()
        dag.z._workflow_section(self.session.project, "workflow_adherence")[
            "configuration"
        ]["phase_dag"] = reviewed
        self.reviewed_graph = dag.z._static_workflow.canonical(reviewed, self.compiler())
        self.created_payloads: list[dict] = []
        self.provider.create_issue = self.create_issue
        self.provider.find_capture_goal = self.find_capture_goal

    def compiler(self):
        value = getattr(dag.z, "_graph_compiler", None)
        self.assertIsNotNone(value, "graph compiler service is not registered")
        return value

    def request(self):
        return {
            "schema_version": 1,
            "title": "Direct current-schema capture",
            "body": self.HUMAN_SPEC,
            "labels": ["regression"],
            "goal": {
                "schema_version": 1,
                "status": "new",
                "priority": "P1",
                "value": "high",
                "difficulty": "M",
                "confidence": "high",
                "parent": None,
                "depends_on": [100],
                "claim": None,
                "blockers": [{"status": "open", "category": "technical-unknown",
                              "summary": "Confirm the provider readback."}],
                "evidence": ["Approved capture evidence."],
                "next_action": "Enter the reviewed workflow.",
                "revision": 1,
                "implementation": None,
                "resources": [],
                "engineering_rigor": {"risk_categories": ["authorization"], "override": None},
            },
        }

    def create_issue(self, payload):
        self.created_payloads.append(copy.deepcopy(payload))
        number = max(self.provider.issues) + 1
        issue = {
            "number": number,
            "title": payload["title"],
            "body": payload["body"],
            "state": "open",
            "updated_at": "2026-10-23T12:00:00Z",
            "html_url": f"https://github.com/owner/repo/issues/{number}",
            "labels": [{"name": value} for value in payload["labels"]],
        }
        self.provider.issues[number] = copy.deepcopy(issue)
        self.provider.comments[number] = []
        return copy.deepcopy(issue)

    def find_capture_goal(self, marker):
        matches = [issue for issue in self.provider.issues.values() if marker in issue["body"]]
        self.assertLessEqual(len(matches), 1, "a capture marker must identify at most one issue")
        if not matches:
            return None
        issue = matches[0]
        return {
            "number": issue["number"],
            "revision": 1,
            "state": "open",
            "status": "new",
            "url": issue["html_url"],
        }

    def approved_submission(self):
        return self.approved_submission_for(self.session)

    def approved_submission_for(self, session):
        request = self.request()
        proposal = session.call(100, {"operation": "capture_propose", "request": request})
        submission = copy.deepcopy(proposal["next_steps"][0]["submission"])
        submission["approved_by"] = "approved-user"
        return request, submission

    def installed_session(self, directory):
        installed = Path(directory) / "zzzops"
        shutil.copytree(Path(__file__).parents[1] / "plugins" / "zzzops", installed)
        module_path = installed / "zzzops" / "zzzops.py"
        spec = importlib.util.spec_from_file_location("zzzops_installed_capture_smoke", module_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        api = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = api
        spec.loader.exec_module(api)
        self.addCleanup(sys.modules.pop, spec.name, None)
        control = Path(directory) / "control"
        control.mkdir()
        return dag.PublicSession(self.fixture.repo, self.session.project, self.fixture.runtime,
                                 self.provider, control, api=api)

    def created_number(self):
        created = set(self.provider.issues) - {100}
        self.assertEqual(1, len(created), "one approved capture must create exactly one issue")
        return created.pop()

    def assert_pending_create(self, request):
        self.assertEqual(1, len(self.created_payloads))
        pending = self.created_payloads[0]
        self.assertEqual(request["title"], pending["title"])
        self.assertNotIn(dag.z._goals.GOAL_BLOCK_START, pending["body"])
        self.assertNotIn("zzzops:schema:v1", pending["labels"])
        self.assertFalse(any(label.startswith("zzzops:status:") for label in pending["labels"]))
        marker = re.search(r"<!-- zzzops-capture:sha256:[0-9a-f]{64} -->", pending["body"])
        self.assertIsNotNone(marker, "the pending issue must carry its exact retry identity")
        self.assertEqual(request["body"], pending["body"][: marker.start()])

    def assert_first_managed_write_is_v2(self, number):
        managed = [payload for changed, payload in self.provider.updates
                   if changed == number and dag.z._goals.GOAL_BLOCK_START in payload.get("body", "")]
        self.assertTrue(managed, "capture never published the managed goal")
        for payload in managed:
            envelope = dag.z.parse_managed_goal(payload["body"], number)
            self.assertEqual(2, envelope["schema_version"],
                             "capture must never publish a v1 managed intermediate")
            self.assertEqual("owner/repo", envelope["repository"])
            self.assertEqual(number, envelope["issue"])
            self.assertEqual(
                {"zzzops", "regression", "zzzops:schema:v2",
                 "zzzops:status:new", "zzzops:priority:P1"},
                set(payload.get("labels", [])),
            )
        return dag.z.parse_managed_goal(managed[0]["body"], number)

    def expected_goal_context_artifact(self, number, request):
        excluded = {"schema_version", "status", "revision", "parent", "depends_on",
                    "blockers", "claim", "implementation"}
        metadata = {key: copy.deepcopy(value) for key, value in request["goal"].items()
                    if key not in excluded}
        metadata["engineering_rigor"] = self.session.api.derive_engineering_rigor(
            request["goal"]["engineering_rigor"],
            self.session.api._workflow_section(self.session.project, "engineering_rigor"))
        policy_hash = self.session.api._workflow.digest(self.session.project["policy"])
        engine = self.session.api.workflow_engine(
            self.fixture.repo, self.session.project, self.fixture.runtime,
        )
        return {
            "type": "goal_context",
            "content": {
                "version": 1,
                "depends_on": copy.deepcopy(request["goal"]["depends_on"]),
                "blockers": copy.deepcopy(request["goal"]["blockers"]),
                "metadata": metadata,
            },
            "producer": None,
            "provenance": {
                "actor": "direct-v2-capture/1",
                "source": None,
                "policy": engine.node_ref(policy_hash, number),
            },
        }

    def test_invalid_normalized_goal_has_zero_provider_writes(self):
        request = self.request()
        request["goal"]["engineering_rigor"]["risk_categories"] = ["Not_Normalized"]
        before_issues = copy.deepcopy(self.provider.issues)
        before_comments = copy.deepcopy(self.provider.comments)
        before_updates = copy.deepcopy(self.provider.updates)

        with self.assertRaisesRegex(ValueError, "lowercase identifiers"):
            self.session.call(100, {"operation": "capture_propose", "request": request})

        self.assertEqual([], self.created_payloads)
        self.assertEqual(before_issues, self.provider.issues)
        self.assertEqual(before_comments, self.provider.comments)
        self.assertEqual(before_updates, self.provider.updates)

    def test_unreviewed_risk_category_fails_before_pending_issue(self):
        request = self.request()
        request["goal"]["engineering_rigor"]["risk_categories"] = ["unreviewed"]
        proposal = self.session.call(100, {"operation": "capture_propose", "request": request})
        submission = copy.deepcopy(proposal["next_steps"][0]["submission"])
        submission["approved_by"] = "approved-user"
        before = copy.deepcopy((self.provider.issues, self.provider.comments, self.provider.updates))

        response = self.session.call(100, submission, expected=2)
        self.assertIn("unknown_risk_categories", str(response))
        self.assertEqual(before, (self.provider.issues, self.provider.comments, self.provider.updates))

    def test_minimal_deferred_capture_normalizes_only_administrative_defaults(self):
        request = self.request()
        for key in ("revision", "claim", "implementation"):
            request["goal"].pop(key)
        original = copy.deepcopy(request)
        proposed = self.session.call(100, {"operation": "capture_propose", "request": request})
        submission = copy.deepcopy(proposed["next_steps"][0]["submission"])
        canonical = submission["request"]
        self.assertEqual((1, None, None), tuple(canonical["goal"][key]
                         for key in ("revision", "claim", "implementation")))
        self.assertEqual(original, request)
        self.assertEqual(request["goal"]["blockers"], canonical["goal"]["blockers"])
        self.assertEqual(request["goal"]["evidence"], canonical["goal"]["evidence"])
        submission["approved_by"] = "approved-user"
        self.session.call(100, submission)
        number = self.created_number()
        retry = copy.deepcopy(submission)
        retry["request"] = request
        self.session.call(100, retry)
        self.assertEqual(1, len(self.created_payloads))
        envelope = self.assert_first_managed_write_is_v2(number)
        payload = self.session.read(number, envelope["payload"])
        self.assertEqual(request["body"], self.session.read(number, payload["spec"])["content"])
        context = self.session.read(number, payload["goal_context"])["content"]
        self.assertEqual(request["goal"]["blockers"], context["blockers"])
        self.assertFalse(any(step.get("kind") in {"migration", "migrate", "repair"}
                             for step in self.session.checkpoint(number)))

    def test_capture_defaults_never_replace_explicit_invalid_administration(self):
        for field, value in (("revision", None), ("revision", 2),
                             ("claim", {"owner": "unexpected"}),
                             ("implementation", {"branch": "unexpected"})):
            with self.subTest(field=field, value=value):
                request = self.request()
                request["goal"][field] = value
                self.session.call(100, {"operation": "capture_propose", "request": request}, expected=2)
        self.assertEqual([], self.created_payloads)

    def test_public_capture_first_managed_state_is_current_and_freshly_executable(self):
        request, submission = self.approved_submission()
        self.session.call(100, submission)
        number = self.created_number()

        self.assert_pending_create(request)
        first = self.assert_first_managed_write_is_v2(number)
        payload = self.session.read(number, first["payload"])
        specification = self.session.read(number, payload["spec"])
        graph = self.session.read(number, payload["graph"])
        context = self.session.read(number, payload["goal_context"])
        self.assertEqual(request["body"], specification["content"])
        self.assertEqual(self.reviewed_graph, graph)
        self.assertEqual(self.expected_goal_context_artifact(number, request), context)
        self.assertEqual([], payload["evidence"])
        self.assertEqual([], payload["operational"]["leases"])
        self.assertEqual([], payload["operational"]["receipts"])

        steps = self.session.checkpoint(number)
        self.assertFalse(any(step.get("kind") in {"migration", "migrate", "repair"} for step in steps), steps)
        gates = [step for step in steps if step.get("node")]
        self.assertTrue(gates, "fresh targeted execute must expose the actual reviewed gate")
        self.assertEqual(self.reviewed_graph["nodes"][0]["id"], gates[0]["node"]["node"])

    def test_capture_with_reviewed_risks_makes_understand_executable(self):
        request = self.request()
        request["goal"]["depends_on"] = []
        request["goal"]["blockers"] = []
        proposal = self.session.call(100, {"operation": "capture_propose", "request": request})
        submission = copy.deepcopy(proposal["next_steps"][0]["submission"])
        submission["approved_by"] = "approved-user"
        self.session.call(100, submission)
        number = self.created_number()

        steps = self.session.checkpoint(number)
        self.assertTrue(any(step.get("kind") == "execute"
                            and step.get("node", {}).get("node") == "understand"
                            for step in steps), steps)

    def test_early_capture_raw_rigor_derives_floor_without_rewriting_context(self):
        api = self.session.api
        node = next(row for row in self.reviewed_graph["nodes"] if row["id"] == "understand")
        raw = {"difficulty": "M", "engineering_rigor": {
            "risk_categories": ["authorization"], "override": None}}
        original = copy.deepcopy(raw)
        derived = api.derive_engineering_rigor(
            raw["engineering_rigor"], api._workflow_section(self.session.project, "engineering_rigor"))
        expected = api._migration_batch.capability_floor(
            api, self.session.project, {**raw, "engineering_rigor": derived}, node)

        self.assertEqual(expected, api._migration_batch.capability_floor(
            api, self.session.project, raw, node))
        self.assertEqual(original, raw, "an authenticated capture artifact stays immutable")
        with self.assertRaisesRegex(ValueError, "Captured engineering rigor metadata is invalid"):
            api._migration_batch.capability_floor(api, self.session.project,
                {"engineering_rigor": {"risk_categories": ["unreviewed"], "override": None}}, node)

    def test_installed_copy_public_capture_reaches_targeted_execute_without_migration(self):
        with tempfile.TemporaryDirectory() as directory:
            session = self.installed_session(directory)
            request, submission = self.approved_submission_for(session)
            session.call(100, submission)
            number = self.created_number()
            self.assert_pending_create(request)
            self.assert_first_managed_write_is_v2(number)
            steps = session.checkpoint(number)
        self.assertTrue(any(step.get("node") for step in steps), steps)
        self.assertFalse(any(step.get("kind") in {"migration", "migrate", "repair"}
                             for step in steps), steps)

    def test_release_capture_receipt_recovers_retry_without_duplicate_goal(self):
        class ReleaseProvider:
            def __init__(self):
                self.record = {"kind": "release-plan", "revision": 0, "next_release": 1,
                               "assignments": {}, "releases": {}}
                self.artifacts = []
                self.lock = None

            def acquire_repository_lock(inner, _repository, request_id):
                inner.lock = request_id

            def release_repository_lock(inner, _repository, request_id):
                if inner.lock == request_id:
                    inner.lock = None

            def read(inner, _repository):
                return copy.deepcopy(inner.record)

            def compare_exchange(inner, _repository, revision, record):
                if revision != inner.record["revision"]:
                    raise ValueError("revision changed")
                inner.record = copy.deepcopy(record)
                return copy.deepcopy(record)

            def append_artifact(inner, _repository, artifact):
                inner.artifacts.append(copy.deepcopy(artifact))

            def capture_receipt(inner, repository, proposal_hash):
                matches = [row for row in inner.artifacts
                           if row.get("kind") == "zzzops-capture-receipt"
                           and row.get("repository") == repository
                           and row.get("proposal_hash") == proposal_hash]
                self.assertLessEqual(len(matches), 1)
                return copy.deepcopy(matches[0]) if matches else None

        release = ReleaseProvider()
        dag.z._workflow_section(self.session.project, "git_review_release")["configuration"][
            "release_planning"
        ] = {"enabled": True, "next_release": 1, "integration_branch": "dev",
             "publication_branch": "main", "release_branch_prefix": "release/",
             "execution_scope": "active_only"}
        request, submission = self.approved_submission()
        original = self.provider.update_issue
        failures = 1

        def fail_first_managed_publish(number, payload):
            nonlocal failures
            if failures and dag.z._goals.GOAL_BLOCK_START in payload.get("body", ""):
                failures -= 1
                raise TimeoutError("forced publication failure after capture receipt")
            return original(number, payload)

        self.provider.update_issue = fail_first_managed_publish
        with mock.patch.object(dag.z, "GitHubReleasePlanAdapter", return_value=release):
            self.session.call(100, submission)
            receipts = [row for row in release.artifacts
                        if row.get("kind") == "zzzops-capture-receipt"]
            self.assertEqual(1, len(receipts))
            self.provider.update_issue = original
            self.session.call(100, submission)
        self.assertEqual(1, len(self.created_payloads))
        self.assertEqual(1, len([row for row in release.artifacts
                                if row.get("kind") == "zzzops-capture-receipt"]))
        self.assertEqual(self.created_number(), receipts[0]["goal"]["number"])
        self.assertEqual(submission["proposal_hash"], receipts[0]["proposal_hash"])

    def test_post_create_failure_retry_reuses_issue_and_retains_evidence(self):
        request, submission = self.approved_submission()
        original = self.provider.update_issue
        failures = 1

        def fail_first_managed_publish(number, payload):
            nonlocal failures
            if failures and dag.z._goals.GOAL_BLOCK_START in payload.get("body", ""):
                failures -= 1
                raise TimeoutError("forced post-create publication failure")
            return original(number, payload)

        self.provider.update_issue = fail_first_managed_publish
        try:
            partial = self.session.call(100, submission)
        except (TimeoutError, RuntimeError, ValueError):
            partial = None
        if partial is not None:
            self.assertTrue(any(step.get("kind") in {"blocker", "blocked"}
                                for step in partial.get("next_steps", [])),
                            "a partial publication must not be reported as successful capture")
        number = self.created_number()
        self.assert_pending_create(request)
        self.assertNotIn(dag.z._goals.GOAL_BLOCK_START, self.provider.issues[number]["body"])
        partial_comments = copy.deepcopy(self.provider.comments[number])
        self.assertTrue(partial_comments, "prepared capture artifacts must survive publication failure")
        partial_index = dag.z._comment_store.ArtifactIndex(partial_comments)
        self.assertTrue(any(row.get("context") for row in partial_index.envelopes),
                        "publication retry requires a durable transaction receipt")

        self.provider.update_issue = original
        result = self.session.call(100, submission)
        self.assertEqual(1, len(self.created_payloads), "exact retry must not duplicate the issue")
        self.assertEqual(partial_comments, self.provider.comments[number],
                         "retry must reuse, not republish, prepared artifacts and receipt")
        bodies = [comment["body"] for comment in self.provider.comments[number]]
        self.assertEqual(len(bodies), len(set(bodies)), "durable artifacts must be published once")
        self.assertTrue(result["next_steps"], "a recovered capture must return its current gate")
        first = self.assert_first_managed_write_is_v2(number)
        payload = self.session.read(number, first["payload"])
        specification = self.session.read(number, payload["spec"])
        context = self.session.read(number, payload["goal_context"])
        self.assertEqual(request["body"], specification["content"])
        self.assertEqual(self.expected_goal_context_artifact(number, request), context)


if __name__ == "__main__":
    unittest.main()
