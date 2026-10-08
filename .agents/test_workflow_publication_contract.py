"""Contracts for deterministic work bases and provider-bound publication."""

import importlib.util
import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

# Bootstrap the production module aliases before loading the isolated adapter.
import test_zzzops as fixtures


MODULE_PATH = Path(__file__).parents[1] / "plugins" / "zzzops" / "zzzops" / "workflow.py"
SPEC = importlib.util.spec_from_file_location("workflow_publication_contract_subject", MODULE_PATH)
workflow = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(workflow)


class StepAPI:
    @staticmethod
    def workflow_step_plan(*_args, **_kwargs):
        return {
            "next_steps": [{
                "kind": "execute", "phase": "implement", "assignment": "delegate",
                "selection": {"model": "worker-model", "effort": "medium"},
            }],
            "frontier": {"blocked": []},
        }

    @staticmethod
    def _workflow_phase_configuration(_project, _goal):
        return {"phases": [{"id": "implement"}]}, {}

    @staticmethod
    def workflow_live_inputs(_repo, _project, _goal, _intent, _graph):
        return {"plan": {"goal_spec": "sha256:" + "1" * 64,
                         "policy": "sha256:" + "2" * 64,
                         "phase_dag": "sha256:" + "3" * 64}}

    @staticmethod
    def _workflow_section(_project, _section):
        return {"configuration": {}}

    @staticmethod
    def workflow_instruction(name):
        return {"name": name}


class PublicationAPI:
    def __init__(self):
        self.calls = []

    def linear_publication_next_step(self, ordered, candidate, *, trunk):
        self.calls.append((ordered, candidate, trunk))
        return {"action": "publish_linear"}


class WorkflowPublicationContractTests(unittest.TestCase):
    def legacy_project(self):
        dag = json.loads((Path(__file__).parent / 'fixtures/legacy_phase_dag.json').read_text())
        return {'policy': {'sections': [{'id': 'workflow_adherence', 'configuration': {'phase_dag': dag}}]}}

    def git(self, repo, *args):
        return subprocess.run(
            ["git", *args], cwd=repo, check=True, capture_output=True, text=True,
        ).stdout.strip()

    def test_step_base_commit_uses_declared_base_not_unrelated_checkout_head(self):
        # Exact publication safeguards now consume ordinary current generic evidence.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_workflow_publication_contract.GenericPublicationPublicTests.test_declared_base_is_not_replaced_by_unrelated_checkout_head',
        )

    def publication_engine(self, *, local_head, local_base, provider_head, provider_base):
        api = PublicationAPI()
        engine = workflow.Workflow.__new__(workflow.Workflow)
        engine.api, engine.repo = api, Path("/repo")
        engine.project = self.legacy_project()
        engine.portfolio = lambda: [{"key": 7, "parent": 1, "implementation": {"branch": "goal-7"}}]
        engine.publication_identity = lambda _goal: {
            "head_oid": provider_head, "base_oid": provider_base, "base_ref": "dev",
        }

        def run(command, **_kwargs):
            if command[:3] == ["gh", "pr", "list"]:
                return SimpleNamespace(stdout=json.dumps([{
                    "headRefName": "goal-7", "baseRefName": "dev", "headRefOid": provider_head,
                }]))
            if command[:2] == ["git", "rev-parse"]:
                return SimpleNamespace(stdout=(local_head if command[2] == "goal-7" else local_base) + "\n")
            raise AssertionError(command)

        return engine, api, run

    def goal(self):
        return {
            "key": 7, "parent": 1,
            "implementation": {
                "branch": "goal-7", "base": "dev", "target": "dev",
                "pr": "https://example.test/pull/7",
            },
        }

    def test_provider_head_or_base_drift_requires_local_sync(self):
        provider_head, provider_base = "a" * 40, "b" * 40
        cases = (("c" * 40, provider_base), (provider_head, "d" * 40))
        for local_head, local_base in cases:
            with self.subTest(local_head=local_head, local_base=local_base):
                engine, api, run = self.publication_engine(
                    local_head=local_head, local_base=local_base,
                    provider_head=provider_head, provider_base=provider_base,
                )
                with mock.patch.object(workflow.subprocess, "run", side_effect=run):
                    result = engine.publication_gate(self.goal())
                self.assertEqual("repair_stack", result["kind"])
                self.assertIn("Synchronize", result["action"])
                self.assertEqual(provider_head, result["head"])
                self.assertEqual(provider_base, result["base"])
                self.assertEqual([], api.calls)

    def test_exact_provider_identity_drives_publication_topology(self):
        provider_head, provider_base = "a" * 40, "b" * 40
        engine, api, run = self.publication_engine(
            local_head=provider_head, local_base=provider_base,
            provider_head=provider_head, provider_base=provider_base,
        )
        with mock.patch.object(workflow.subprocess, "run", side_effect=run):
            self.assertIsNone(engine.publication_gate(self.goal()))

        self.assertEqual(1, len(api.calls))
        ordered, candidate, trunk = api.calls[0]
        self.assertEqual([], ordered)
        self.assertEqual("dev", trunk)
        self.assertEqual({
            "branch": "goal-7", "base": "dev",
            "base_head": provider_base, "head": provider_head,
        }, candidate)




from test_evidence_dag_journeys import DagFixture, REF_TYPE, FINDING_TYPE, ADMISSION_TYPE, content_hash, output, shape, spec_input, z
import test_evidence_dag_journeys as dag_fixtures
from test_evidence_dag import task, selector, scope


class GenericPublicationPublicTests(DagFixture):
    """Finite adapter wire proposal; no domain phase or envelope metadata.

    repository_context is {branch,base,target,pr:null|string}. Its authenticated
    root output needs configured independent review and current root authorization.
    repository_authorization is {context:Ref,policy:Hash,decision:'approved'}.
    publication_evidence is {repository,pr,head_oid,base_oid,base_ref,ci}, where ci is
    verified|unverified|absent|unknown. Negative observations remain recordable;
    authorization/effects/completion enforce CI. Absent requires known complete
    provider evidence; unknown/incomplete is never absent. The adapter
    obtains provider facts, exact CI and policy itself. Caller booleans confer none.
    publication_authorization is {subject:Ref,review:Ref,policy,decision:'approved'}.
    Operational integrate accepts authorization:Ref and expected_head, and cannot
    issue missing semantic Results. All such calls target a synthetic provider.
    """

    def setUp(self):
        super().setUp()
        self.setup_publication()

    def setup_publication(self):
        self.observation = {"repository": "owner/repo", "head_oid": self.fixture.head_oid,
            "base_oid": self.fixture.base_oid, "base_ref": "dev", "merged": False,
            "merged_at": None, "merge_commit": None, "checks_present": True,
            "checks_verified": True, "review_verified": True}
        def provider_facts(_repo, executable, selected, bodies):
            self.assertEqual("gh", executable)
            selected_numbers = [entry["number"] for entry in selected]
            if 100 in selected_numbers:
                self.assertIn(100, bodies)
            return ({100: copy.deepcopy(self.observation)} if 100 in selected_numbers else {}), 512, 1
        patch = mock.patch.object(z, "_github_pull_request_states", side_effect=provider_facts)
        patch.start()
        self.addCleanup(patch.stop)
        z._workflow_section(self.session.project, "verification_testing")["configuration"]["required_ci"] = "inspect_exact_pr_head"
        self.merge_calls = []
        self.session.provider_command = self.provider_command
        self.context = {"branch": "goal-child", "base": "dev", "target": "dev",
                        "pr": "https://github.com/owner/repo/pull/9"}
        self.configure()

    def provider_command(self, command, *args, **kwargs):
        if list(command[:1]) != ["gh"]:
            return None
        if list(command[:3]) == ["gh", "pr", "list"]:
            values = [] if self.observation["merged"] else [{"headRefName": "goal-child", "baseRefName": "dev", "headRefOid": self.observation["head_oid"]}]
            return subprocess.CompletedProcess(command, 0, stdout=json.dumps(values), stderr="")
        if list(command[:3]) == ["gh", "pr", "merge"]:
            self.assertIn("--match-head-commit", command)
            self.assertEqual(self.observation["head_oid"], command[command.index("--match-head-commit") + 1])
            self.merge_calls.append(list(command))
            self.mark_merged()
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        raise AssertionError("Unexpected provider command in synthetic publication fixture: %r" % command)

    def mark_merged(self):
        self.observation.update(merged=True, merged_at="2026-09-29T15:00:00Z", merge_commit="f" * 40, review_verified=True)

    def configure(self, renamed=False):
        self.provider.issues[100]["state"] = "open"  # Independent fixture scenario, never a CLI reopen.
        roles = ("context", "inspect", "consent", "observe", "review", "approve", "finish")
        self.ids = {name: ("n%d" % i if renamed else name) for i, name in enumerate(roles)}
        n = self.ids
        context_type = {"kind": "object", "fields": {
            **{key: {"kind": "string"} for key in ("branch", "base", "target")},
            "pr": {"kind": "union", "variants": [{"kind": "null"}, {"kind": "string"}]}}}
        permit_type = {"kind": "object", "fields": {"context": REF_TYPE,
            "policy": {"kind": "string"}, "decision": {"kind": "enum", "values": ["approved"]}}}
        published_type = shape({"repository": "owner/repo", "pr": self.context["pr"],
            "head_oid": "head", "base_oid": "base", "base_ref": "dev", "ci": "verified",
            "review_verified": False})
        published_type["fields"]["ci"] = {"kind": "enum", "values": ["verified", "unverified", "absent", "unknown"]}
        approval_type = {"kind": "object", "fields": {"subject": REF_TYPE, "review": REF_TYPE,
            "policy": {"kind": "string"}, "decision": {"kind": "enum", "values": ["approved"]}}}
        def binding(role, schema):
            return {"producer": {"node": selector(n[role])}, "output": "value", "path": [],
                    "mode": "identity", "type": schema}
        context = task(n["context"], role="root")
        context["inputs"] = {"request": spec_input()}
        context["outputs"] = {"value": output("repository_context", context_type)}
        inspect = task(n["inspect"], [n["context"]])
        inspect["inputs"] = {"subject": binding("context", context_type)}
        inspect["independent_of"] = [selector(n["context"])]
        consent = task(n["consent"], [n["inspect"]], role="root")
        consent["inputs"] = {"subject": binding("context", context_type), "review": binding("inspect", {"kind": "string"})}
        consent["outputs"] = {"value": output("repository_authorization", permit_type)}
        observe = task(n["observe"], [n["consent"]])
        observe["inputs"] = {"context": binding("context", context_type), "authority": binding("consent", permit_type)}
        observe["executor"].update(resources=["repository_publication"], authority=scope(n["context"]))
        observe["outputs"] = {"value": output("publication_evidence", published_type)}
        review = task(n["review"], [n["observe"]])
        review["inputs"] = {"subject": binding("observe", published_type)}
        review["independent_of"] = [selector(n["observe"])]
        approve = task(n["approve"], [n["review"]], role="root")
        approve["inputs"] = {"subject": binding("observe", published_type), "review": binding("review", {"kind": "string"})}
        approve["outputs"] = {"value": output("publication_authorization", approval_type)}
        finish = task(n["finish"], [n["approve"]])
        finish["inputs"] = {"authorization": binding("approve", approval_type)}
        self.install({"nodes": [context, inspect, consent, observe, review, approve, finish],
                      "task_sets": [], "terminals": [selector(n["finish"])]})

    def submit_role(self, role, value, actor=None):
        work = self.session.acquire(self.ids[role], actor=actor)
        self.session.finish(work, {"value": value})
        return work

    def authorize_context(self):
        self.submit_role("context", self.context)
        self.assertNotIn(self.ids["observe"], self.names())
        self.submit_role("inspect", "Exact repository context reviewed", actor="context-reviewer")
        self.assertNotIn(self.ids["observe"], self.names())
        self.submit_role("consent", {"context": self.produced(self.ids["context"]),
            "policy": content_hash(self.session.project["policy"]), "decision": "approved"})
        self.assertIn(self.ids["observe"], self.names())

    def observed_value(self):
        ci = ("verified" if self.observation["checks_verified"] else
              "absent" if self.observation["checks_present"] is False else
              "unverified" if self.observation["checks_present"] is True else "unknown")
        return {**{key: (self.context["pr"] if key == "pr" else self.observation[key])
                for key in ("repository", "pr", "head_oid", "base_oid", "base_ref")},
                "ci": ci, "review_verified": self.observation["review_verified"]}

    def approve_publication(self):
        self.submit_role("observe", self.observed_value())
        self.assertNotIn(self.ids["finish"], self.names())
        self.submit_role("review", "Exact observed publication reviewed", actor="publication-reviewer")
        self.assertNotIn(self.ids["finish"], self.names())
        self.submit_role("approve", {"subject": self.produced(self.ids["observe"]),
            "review": self.produced(self.ids["review"]), "policy": content_hash(self.session.project["policy"]),
            "decision": "approved"})
        return self.produced(self.ids["approve"])

    def with_merge_observation(self, graph):
        """Finite post-effect wire; no archive flag or submitted boolean authority.

        merge_observation has exactly authorization:Ref, repository:string,
        pr:string, head_oid:string, base_oid:string, base_ref:string,
        merge_commit:string, merged_at:string. Its identity inputs pin the
        authenticated repository context, publication subject and current root
        authorization. The repository_publication adapter compares every field
        with provider facts. Integrate consumes current authorization before
        this post-effect Result exists; configured terminals still require it.
        """
        n = self.ids
        by_id = {node["id"]: node for node in graph["nodes"]}
        observe = task("observed_merge", [n["approve"]])
        def exact(role):
            return {"producer": {"node": selector(n[role])}, "output": "value",
                    "path": [], "mode": "identity",
                    "type": copy.deepcopy(by_id[n[role]]["outputs"]["value"]["schema"])}
        observe["inputs"] = {"context": exact("context"), "subject": exact("observe"),
                             "authorization": exact("approve")}
        observe["executor"].update(resources=["repository_publication"], authority=scope(n["context"]))
        schema = {"kind": "object", "fields": {"authorization": REF_TYPE,
            **{key: {"kind": "string"} for key in
               ("repository", "pr", "head_oid", "base_oid", "base_ref", "merge_commit", "merged_at")}}}
        observe["outputs"] = {"value": output("merge_observation", schema)}
        graph["nodes"].append(observe)
        finish = by_id[n["finish"]]
        finish["requires"].append(selector("observed_merge"))
        finish["inputs"]["merge"] = {"producer": {"node": selector("observed_merge")},
            "output": "value", "path": [], "mode": "identity", "type": schema}
        return graph

    def merge_value(self):
        return {"authorization": self.produced(self.ids["approve"]),
                **{key: (self.context["pr"] if key == "pr" else self.observation[key])
                   for key in ("repository", "pr", "head_oid", "base_oid", "base_ref", "merge_commit", "merged_at")}}

    def test_integrate_precedes_post_effect_terminal_and_observation_is_exact(self):
        self.install(self.with_merge_observation(copy.deepcopy(self.graph)))
        self.authorize_context()
        authority = self.approve_publication()
        self.assertNotIn(self.ids["finish"], self.names())
        request = self.integration_request(authority)
        request["request_id"] = "before-post-effect-terminal"
        self.session.call(100, request)
        self.assertEqual(1, len(self.merge_calls))
        self.assertEqual("open", self.provider.issues[100]["state"], "Merge cannot mint the pending observation Result or complete goal")
        self.assertNotIn(self.ids["finish"], self.names())
        work = self.session.acquire("observed_merge")
        acquisition = json.dumps(work["lease"]["acquisition"])
        for role in ("context", "observe", "approve"):
            self.assertIn(self.produced(self.ids[role])["hash"], acquisition)
        value = self.merge_value()
        for key, wrong in (("head_oid", "a" * 40), ("base_oid", "b" * 40),
                           ("merge_commit", "c" * 40), ("merged_at", "2020-01-01T00:00:00Z"),
                           ("authorization", self.produced(self.ids["context"]))):
            with self.subTest(field=key):
                before = copy.deepcopy((self.provider.issues, self.provider.comments))
                self.session.call(100, self.session.submission(work, {"value": {**value, key: wrong}}, "wrong-merge-" + key), expected=2)
                self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.session.finish(work, {"value": value})
        self.assertIn(self.ids["finish"], self.names())
        self.submit_role("finish", "Exact post-effect evidence consumed")
        self.assertEqual(set(), self.names())

    def test_unmerged_provider_cannot_issue_merge_observation_then_external_merge_is_readable(self):
        self.install(self.with_merge_observation(copy.deepcopy(self.graph)))
        self.authorize_context()
        self.approve_publication()
        work = self.session.acquire("observed_merge")
        forged = {**self.merge_value(), "merge_commit": "f" * 40, "merged_at": "2026-09-29T15:00:00Z"}
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        self.session.call(100, self.session.submission(work, {"value": forged}, "forged-merge"), expected=2)
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.assertNotIn(self.ids["finish"], self.names())
        self.mark_merged()  # External provider event; no lease takeover or semantic Result fabrication.
        self.session.finish(work, {"value": self.merge_value()})
        self.assertEqual(0, len(self.merge_calls))
        self.submit_role("finish", "Observed external merge has exact evidence")

    def test_declared_base_is_not_replaced_by_unrelated_checkout_head(self):
        self.authorize_context()
        self.session.git("checkout", "-qb", "unrelated")
        (self.fixture.repo / "unrelated.txt").write_text("Unrelated committed checkout\n")
        self.session.git("add", "unrelated.txt")
        self.session.git("commit", "-qm", "unrelated checkout")
        head = self.session.git("rev-parse", "HEAD")
        self.assertNotEqual(self.fixture.base_oid, head)
        work = self.session.acquire(self.ids["observe"])
        self.assertEqual("dev", work["base_branch"])
        self.assertEqual(self.fixture.base_oid, work["base_commit"])
        self.assertNotEqual(head, work["base_commit"])
        self.session.finish(work, {"value": self.observed_value()})

    def test_renamed_graph_requires_current_review_and_root_before_completion(self):
        for renamed in (False, True):
            with self.subTest(renamed=renamed):
                self.configure(renamed)
                self.authorize_context()
                self.approve_publication()
                self.submit_role("finish", "All configured exact evidence accepted")
                self.assertEqual(set(), self.names())
                self.assertEqual(self.ids["finish"], self.result(self.ids["finish"])[1]["node"]["node"])
                self.assertEqual("open", self.provider.issues[100]["state"], "Semantic completion alone cannot claim a provider merge")

    def test_live_head_base_ci_and_caller_approval_flags_reject_before_valid_control(self):
        self.authorize_context()
        work = self.session.acquire(self.ids["observe"])
        original = copy.deepcopy(self.observation)
        declared = self.observed_value()
        for field, value in (("head_oid", "a" * 40), ("base_oid", "b" * 40), ("checks_verified", False)):
            with self.subTest(field=field):
                self.observation = {**original, field: value}
                before = copy.deepcopy((self.provider.issues, self.provider.comments))
                response = self.session.call(100, self.session.submission(work, {"value": declared}, "changed-" + field), expected=2)
                self.assertRegex(json.dumps(response), r"(?i)head|base|checks|CI|stale|provider|input")
                self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.observation = original
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        forged = {**self.observed_value(), "approved": True, "checks_verified": True}
        self.session.call(100, self.session.submission(work, {"value": forged}, "forged-approval"), expected=2)
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.session.finish(work, {"value": self.observed_value()})

    def test_negative_ci_observation_is_recordable_and_review_can_admit_correction_without_approval(self):
        graph = copy.deepcopy(self.graph)
        observed = self.ids["observe"]
        source_input = copy.deepcopy(next(node for node in graph["nodes"] if node["id"] == self.ids["review"])["inputs"])
        finder = task("describe_defect", [self.ids["review"]])
        finder["inputs"] = copy.deepcopy(source_input)
        finder["independent_of"] = [selector(observed)]
        finder["outputs"] = {"value": output("finding", FINDING_TYPE)}
        finder["permits"] = [{"type": "finding", "scope": scope(observed)}]
        authorize = task("authorize_correction", ["describe_defect"], role="root")
        authorize["inputs"] = copy.deepcopy(source_input)
        admit = task("admit_correction", ["describe_defect", "authorize_correction"], role="root")
        admit["inputs"] = copy.deepcopy(source_input)
        admit["outputs"] = {"value": output("admission", ADMISSION_TYPE)}
        admit["permits"] = [{"type": "admission", "scope": scope(observed)}]
        graph["nodes"].extend([finder, authorize, admit])
        self.install(graph)
        self.authorize_context()
        self.observation["checks_verified"] = False
        self.submit_role("observe", self.observed_value())
        subject = self.produced(observed)
        self.assertEqual("unverified", self.read_blob(subject)["content"]["ci"])
        self.submit_role("review", "Observed failed checks require correction", actor="publication-reviewer")
        finding = {"id": "failed-ci", "revision": 1, "source": subject, "subjects": [subject],
            "target": scope(observed), "request": "Correct the failing checks and publish current provider evidence",
            "rationale": "Exact authenticated publication observation reports unverified CI", "supersedes": None}
        self.session.finish(self.session.acquire("describe_defect", actor="defect-reviewer"), {"value": finding})
        self.session.finish(self.session.acquire("authorize_correction"), {"value": "Authorize in-scope correction"})
        admission = {"finding": self.produced("describe_defect"), "target_inputs": self.result(observed)[1]["inputs"],
            "authority": self.result("authorize_correction")[0], "applicability": "applicable", "rationale": "Current failing subject needs correction"}
        self.session.finish(self.session.acquire("admit_correction"), {"value": admission})
        self.assertIn(observed, self.names())
        self.assertNotIn(self.ids["finish"], self.names())
        self.assertFalse(any(step.get("kind") == "complete" for step in self.session.checkpoint(100)))
        self.assertEqual([], self.merge_calls)

    def test_ci_absent_unknown_unverified_and_disabled_authorization_are_distinct(self):
        cases = [("inspect_exact_pr_head", True, True, True),
                 ("inspect_exact_pr_head", False, False, False),
                 ("existing_only", False, False, True),
                 ("existing_only", None, False, False),
                 ("existing_only", True, False, False),
                 ("disabled", None, False, True)]
        for mode, present, verified, allowed in cases:
            with self.subTest(mode=mode, present=present, verified=verified):
                z._workflow_section(self.session.project, "verification_testing")["configuration"]["required_ci"] = mode
                self.observation.update(checks_present=present, checks_verified=verified, merged=False)
                self.configure()
                self.authorize_context()
                self.submit_role("observe", self.observed_value())
                self.assertEqual(self.observed_value(), self.read_blob(self.produced(self.ids["observe"]))["content"])
                self.submit_role("review", "Reviewed current observation, including negative CI", actor="publication-reviewer")
                value = {"subject": self.produced(self.ids["observe"]), "review": self.produced(self.ids["review"]),
                    "policy": content_hash(self.session.project["policy"]), "decision": "approved"}
                if allowed:
                    self.submit_role("approve", value)
                    self.assertIn(self.ids["finish"], self.names())
                else:
                    ready = self.names()
                    if self.ids["approve"] in ready:
                        work = self.session.acquire(self.ids["approve"])
                        before = copy.deepcopy((self.provider.issues, self.provider.comments))
                        response = self.session.call(100, self.session.submission(work, {"value": value}, "ci-block-" + str(len(self.session.calls))), expected=2)
                        self.assertEqual(before, (self.provider.issues, self.provider.comments))
                    else:
                        response = self.session.call(100)
                    self.assertRegex(json.dumps(response), r"(?i)CI|checks|unknown|unverified|incomplete")
                    self.assertNotIn(self.ids["finish"], self.names())
                    before = copy.deepcopy((self.provider.issues, self.provider.comments))
                    self.session.call(100, {"operation": "complete", "request_id": "premature-ci-complete-" + str(len(self.session.calls))}, expected=2)
                    self.assertEqual(before, (self.provider.issues, self.provider.comments))

    def test_changed_root_context_stales_acquired_publication(self):
        self.authorize_context()
        work = self.session.acquire(self.ids["observe"])
        self.replace_spec("Changed required repository target; current context must be reconsidered")
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        response = self.session.call(100, self.session.submission(work, {"value": self.observed_value()}, "stale-context"), expected=2)
        self.assertRegex(json.dumps(response), r"(?i)stale|context|input|ancestor|authority")
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.assertNotIn(self.ids["finish"], self.names())

    def test_publication_submit_lost_body_response_reuses_exact_result(self):
        self.authorize_context()
        work = self.session.acquire(self.ids["observe"])
        request = self.session.submission(work, {"value": self.observed_value()}, "publication-lost-response")
        update = self.provider.update_issue
        lost = []
        def uncertain(number, payload):
            result = update(number, payload)
            if number == 100 and not lost:
                lost.append(True)
                raise z.GoalTransitionProviderError("Publication body committed; response lost")
            return result
        with mock.patch.object(self.provider, "update_issue", side_effect=uncertain):
            self.session.call(100, request, expected=None)
        self.assertTrue(lost, "Fault must reach the actual durable provider boundary")
        self.session.call(100, request)
        reference = self.produced(self.ids["observe"])
        stable = copy.deepcopy((self.provider.issues, self.provider.comments))
        self.session.call(100, request)
        self.assertEqual(stable, (self.provider.issues, self.provider.comments))
        self.assertEqual(reference, self.produced(self.ids["observe"]))
        self.assertNotIn(self.ids["finish"], self.names())

    def integration_request(self, authorization):
        steps = self.session.checkpoint(100)
        candidates = [step for step in steps if step.get("submission", {}).get("operation") == "integrate"]
        self.assertTrue(candidates, "Current exact publication authorization must expose operational integration contract")
        request = copy.deepcopy(candidates[0]["submission"])
        self.assertEqual(authorization, request["authorization"])
        self.assertEqual(self.observation["head_oid"], request["expected_head"])
        return request

    def test_exact_root_authorization_rejects_wrong_subject_review_policy_and_forged_integration(self):
        self.authorize_context()
        self.submit_role("observe", self.observed_value())
        self.submit_role("review", "Reviewed exact subject", actor="publication-reviewer")
        root = self.session.acquire(self.ids["approve"])
        value = {"subject": self.produced(self.ids["observe"]), "review": self.produced(self.ids["review"]),
                 "policy": content_hash(self.session.project["policy"]), "decision": "approved"}
        wrong = self.produced(self.ids["context"])
        for changes in ({"subject": wrong}, {"review": wrong}, {"policy": "sha256:" + "0" * 64}):
            before = copy.deepcopy((self.provider.issues, self.provider.comments))
            response = self.session.call(100, self.session.submission(root, {"value": {**value, **changes}}, "wrong-approval-" + next(iter(changes))), expected=2)
            self.assertRegex(json.dumps(response), r"(?i)subject|review|policy|current|authority|stale")
            self.assertEqual(before, (self.provider.issues, self.provider.comments))
        request = self.session.submission(root, {"value": value}, "nonroot-approval")
        request["actor"] = "publication-reviewer"
        self.session.call(100, request, expected=2)
        self.session.finish(root, {"value": value})
        authority = self.produced(self.ids["approve"])
        self.submit_role("finish", "Exact configured graph complete")
        request = self.integration_request(authority)
        forged = self.blob({"type": "publication_authorization", "content": value, "producer": None,
            "provenance": {"actor": "root-thread", "source": None, "policy": value["policy"]}})
        for bad in (None, wrong, forged):
            before = copy.deepcopy((self.provider.issues, self.provider.comments))
            rejected = {**request, "request_id": "bad-integration-" + str(len(self.session.calls)), "authorization": bad}
            response = self.session.call(100, rejected, expected=2)
            self.assertRegex(json.dumps(response), r"(?i)authoriz|approval|root|subject|reference|current")
            self.assertEqual(before, (self.provider.issues, self.provider.comments))
            self.assertEqual([], self.merge_calls)
        request["request_id"] = "exact-integration"
        self.session.call(100, request)
        self.assertEqual(1, len(self.merge_calls))
        stable = copy.deepcopy((self.provider.issues, self.provider.comments))
        self.session.call(100, request)
        self.assertEqual(1, len(self.merge_calls))
        self.assertEqual(stable, (self.provider.issues, self.provider.comments))

    def test_stale_root_authorization_cannot_integrate_after_context_drift(self):
        self.authorize_context()
        authority = self.approve_publication()
        self.submit_role("finish", "Current terminal evidence")
        request = self.integration_request(authority)
        old_body = self.provider.issues[100]["body"]
        self.replace_spec("Different repository target requiring new current authorization")
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        response = self.session.call(100, {**request, "request_id": "stale-root-context"}, expected=2)
        self.assertRegex(json.dumps(response), r"(?i)stale|current|context|authority|evidence|input")
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.assertEqual([], self.merge_calls)
        # Fixture restores the exact external substantive input; added immutable
        # source bytes remain unreferenced history, not an authority bypass.
        self.provider.issues[100]["body"] = old_body
        self.session.call(100, {**request, "request_id": "restored-current-context"})
        self.assertEqual(1, len(self.merge_calls))

    def test_strict_ci_blocks_integration_and_only_reviewed_disabled_configuration_permits_it(self):
        for mode in ("inspect_exact_pr_head", "disabled"):
            with self.subTest(mode=mode):
                self.observation.update(checks_verified=True, merged=False, merged_at=None, merge_commit=None, review_verified=True)
                z._workflow_section(self.session.project, "verification_testing")["configuration"]["required_ci"] = mode
                self.configure()
                self.authorize_context()
                authority = self.approve_publication()
                self.submit_role("finish", "Complete exact evidence")
                request = self.integration_request(authority)
                self.observation["checks_verified"] = False
                before = copy.deepcopy((self.provider.issues, self.provider.comments))
                previous_merges = len(self.merge_calls)
                if mode == "inspect_exact_pr_head":
                    response = self.session.call(100, request, expected=2)
                    self.assertRegex(json.dumps(response), r"(?i)CI|checks|stale|current|evidence")
                    self.assertEqual(before, (self.provider.issues, self.provider.comments))
                    self.assertEqual(previous_merges, len(self.merge_calls))
                    self.observation["checks_verified"] = True
                self.session.call(100, request)
                self.assertEqual(previous_merges + 1, len(self.merge_calls))

    def test_strict_ci_blocks_complete_and_reviewed_disabled_ci_preserves_current_terminal_requirement(self):
        for mode in ("inspect_exact_pr_head", "disabled"):
            with self.subTest(mode=mode):
                self.observation.update(checks_verified=True, merged=False, merged_at=None, merge_commit=None, review_verified=True)
                z._workflow_section(self.session.project, "verification_testing")["configuration"]["required_ci"] = mode
                self.configure()
                self.authorize_context()
                authority = self.approve_publication()
                self.mark_merged()
                before = copy.deepcopy((self.provider.issues, self.provider.comments))
                request = {"operation": "complete", "authorization": authority, "request_id": "complete-" + mode}
                self.session.call(100, request, expected=2)
                self.assertEqual(before, (self.provider.issues, self.provider.comments), "Even disabled CI cannot replace missing terminal Result")
                self.submit_role("finish", "Current complete graph")
                self.observation["checks_verified"] = False
                if mode == "inspect_exact_pr_head":
                    before = copy.deepcopy((self.provider.issues, self.provider.comments))
                    response = self.session.call(100, request, expected=2)
                    self.assertRegex(json.dumps(response), r"(?i)CI|checks|stale|current|evidence")
                    self.assertEqual(before, (self.provider.issues, self.provider.comments))
                    self.observation["checks_verified"] = True
                self.session.call(100, request)
                self.assertEqual("closed", self.provider.issues[100]["state"])

    def reconciliation_request(self):
        steps = self.session.checkpoint(100)
        candidates = [step for step in steps if step.get("submission", {}).get("operation") == "reconcile"]
        self.assertTrue(candidates, "External merge must expose exact readback reconciliation")
        return copy.deepcopy(candidates[0]["submission"])

    def test_external_merge_cannot_mint_missing_results_and_exact_replay_preserves_history(self):
        self.authorize_context()
        self.mark_merged()
        request = self.reconciliation_request()
        prior = copy.deepcopy(self.payload()[1]["evidence"])
        for change in ({"expected_digest": "0" * 64}, {"expected_merge": "sha256:" + "0" * 64}):
            before = copy.deepcopy((self.provider.issues, self.provider.comments))
            self.session.call(100, {**request, **change}, expected=2)
            self.assertEqual(before, (self.provider.issues, self.provider.comments))
        request["request_id"] = "incomplete-external-merge"
        self.session.call(100, request)
        self.assertEqual("open", self.provider.issues[100]["state"])
        self.assertEqual(prior, self.payload()[1]["evidence"], "Reconciliation cannot issue semantic Results")
        stable = copy.deepcopy((self.provider.issues, self.provider.comments))
        self.session.call(100, request)
        self.assertEqual(stable, (self.provider.issues, self.provider.comments))
        self.assertFalse(any(step.get("kind") == "complete" for step in self.session.checkpoint(100)))

    def test_external_merge_preserves_owned_worker_until_exact_observed_stop(self):
        self.authorize_context()
        work = self.session.acquire(self.ids["observe"])
        self.mark_merged()
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        steps = self.session.checkpoint(100)
        reconcile = [step for step in steps if step.get("submission", {}).get("operation") == "reconcile"]
        if reconcile:
            response = self.session.call(100, reconcile[0]["submission"], expected=2)
            self.assertRegex(json.dumps(response), r"(?i)worker|lease|stopped|owner")
        else:
            self.assertRegex(json.dumps(steps), r"(?i)worker|lease|stopped|owner")
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        self.assertTrue(any(lease["token"] == work["lease"]["token"] for lease in self.payload()[1]["operational"]["leases"]))
        with mock.patch.object(z._workflow.time, "time", return_value=work["lease"]["expires_at"] + 1):
            steps = self.session.checkpoint(100)
            recovery = [step for step in steps if "recovery_contract" in step or step.get("kind") == "recover"]
            self.assertTrue(recovery)
            request = copy.deepcopy(recovery[0].get("submission", recovery[0].get("recovery_contract")))
            request.update(worker_status="stopped", evidence="Observed publication worker terminal state")
            self.session.call(100, request)
        request = self.reconciliation_request()
        self.session.call(100, request)
        self.assertEqual("open", self.provider.issues[100]["state"], "Stopped work still supplies no missing Result")

    def test_external_merge_closes_only_current_terminal_and_partial_close_replay_repairs(self):
        self.authorize_context()
        self.approve_publication()
        self.submit_role("finish", "Current complete graph")
        self.mark_merged()
        request = self.reconciliation_request()
        request["request_id"] = "complete-external-merge"
        prior = copy.deepcopy(self.payload()[1]["evidence"])
        self.session.call(100, request)
        self.assertEqual("closed", self.provider.issues[100]["state"])
        self.assertEqual(prior, self.payload()[1]["evidence"])
        stable = copy.deepcopy((self.provider.issues, self.provider.comments))
        self.session.call(100, request)
        self.assertEqual(stable, (self.provider.issues, self.provider.comments))
        self.provider.issues[100]["state"] = "open"
        body = self.provider.issues[100]["body"]
        response = self.session.call(100, request, expected=None)
        self.assertTrue(any(step.get("kind") == "repair" for step in response["next_steps"]))
        self.assertEqual(body, self.provider.issues[100]["body"], "Stored receipt cannot silently claim closure after provider partial state")


class GenericDeliveryPublicTests(DagFixture):
    # Reuse fixture helpers, not test-case inheritance or semantic engine answers.
    def setUp(self):
        super().setUp()
        self.setup_publication()

    setup_publication = GenericPublicationPublicTests.setup_publication
    configure = GenericPublicationPublicTests.configure
    provider_command = GenericPublicationPublicTests.provider_command
    mark_merged = GenericPublicationPublicTests.mark_merged
    submit_role = GenericPublicationPublicTests.submit_role
    observed_value = GenericPublicationPublicTests.observed_value
    integration_request = GenericPublicationPublicTests.integration_request
    with_merge_observation = GenericPublicationPublicTests.with_merge_observation
    merge_value = GenericPublicationPublicTests.merge_value
    workspace_graph = dag_fixtures.WorkspaceAuthorityPublicTests.workspace_graph
    setup_workspace = dag_fixtures.WorkspaceAuthorityPublicTests.setup_workspace
    acquire_workspace = dag_fixtures.WorkspaceAuthorityPublicTests.acquire_workspace
    candidate = dag_fixtures.WorkspaceAuthorityPublicTests.candidate
    review_candidate = dag_fixtures.WorkspaceAuthorityPublicTests.review_candidate
    red_candidate = dag_fixtures.WorkspaceAuthorityPublicTests.red_candidate

    setup_parent_workspace = dag_fixtures.WorkspaceAuthorityPublicTests.setup_parent_workspace
    setup_relationship_transport = dag_fixtures.RelationshipPublicTests.setup_relationship_transport
    envelope_for = dag_fixtures.RelationshipPublicTests.envelope_for
    put_envelope = dag_fixtures.RelationshipPublicTests.put_envelope
    add_goal = dag_fixtures.RelationshipPublicTests.add_goal
    read_at = dag_fixtures.RelationshipPublicTests.read_at
    result_at = dag_fixtures.RelationshipPublicTests.result_at
    resolutions = dag_fixtures.RelationshipPublicTests.resolutions

    def test_reviewed_red_green_proofs_commit_and_exact_publication_form_one_delivery_graph(self):
        self.connected_delivery()

    def connected_delivery(self, parent=False, allocation_mutator=None, observer=None):
        self.configure(renamed=True)
        publication = self.with_merge_observation(copy.deepcopy(self.graph))
        self.session.git("checkout", "-q", "goal-child")
        def composed(graph, _allocations):
            if allocation_mutator:
                allocation_mutator(graph, _allocations)
            observer = next(node for node in publication["nodes"] if node["id"] == self.ids["observe"])
            observer["requires"].append(selector("accept_beta"))
            observer["inputs"]["candidate"] = {"producer": {"node": selector("beta")}, "output": "value", "path": [], "mode": "identity", "type": {"kind": "string"}}
            graph["nodes"].extend(copy.deepcopy(publication["nodes"]))
            graph["terminals"] = copy.deepcopy(publication["terminals"])
        if parent:
            self.setup_relationship_transport()
            def aggregate(graph):
                target = {"kind": "node", "goal": "#children", "node": self.ids["finish"]}
                collect = task("collect", role="root")
                collect["executor"]["authority"]["subject"]["goal"] = 99
                collect["requires"] = [target]
                collect["inputs"] = {"children": {"producer": {"node": target}, "output": "value", "path": [],
                    "mode": "identity", "type": {"kind": "map", "values": {"kind": "string"}}}}
                graph["nodes"].append(collect)
                graph["terminals"] = [{"kind": "node", "goal": 99, "node": "collect"}]
            self.setup_parent_workspace(composed, aggregate)
            observed = next(node for node in publication["nodes"] if node["id"] == "observed_merge")
            inspect = task("inspect_shared_merge")
            inspect["requires"] = [selector("observed_merge")]
            inspect["inputs"] = {"merge": {"producer": {"node": selector("observed_merge")}, "output": "value",
                "path": [], "mode": "identity", "type": observed["outputs"]["value"]["schema"]}}
            inspect["independent_of"] = [selector("observed_merge")]
            inspect["executor"]["authority"]["subject"]["goal"] = 101
            finish = task(self.ids["finish"], role="root")
            finish["executor"]["authority"]["subject"]["goal"] = 101
            finish["requires"] = [{"kind": "node", "goal": 101, "node": "inspect_shared_merge"}]
            finish["inputs"] = {"merge": copy.deepcopy(inspect["inputs"]["merge"]), "review": {
                "producer": {"node": {"kind": "node", "goal": 101, "node": "inspect_shared_merge"}},
                "output": "value", "path": [], "mode": "identity", "type": {"kind": "string"}}}
            self.add_goal(101, {"nodes": [inspect, finish], "task_sets": [],
                               "terminals": [{"kind": "node", "goal": 101, "node": self.ids["finish"]}]}, parent=99)
            self.assertFalse(any(step["node"]["node"] == "collect" for step in self.session.ready(99)))
        else:
            self.setup_workspace(composed)
        if observer:
            observer("prepared")
        self.submit_role("context", self.context)
        self.submit_role("inspect", "Independent exact repository context", actor="context-reviewer")
        self.submit_role("consent", {"context": self.produced(self.ids["context"]), "policy": content_hash(self.session.project["policy"]), "decision": "approved"})
        self.assertNotIn(self.ids["observe"], self.names(), "Repository authority cannot substitute for implementation evidence")
        alpha = self.acquire_workspace("alpha")
        (self.fixture.repo / "behavior_test.py").write_text("from source import value\nassert value() == 2\n")
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        fabricated = self.session.submission(alpha, {"value": "Claimed failing tests without observed checks"}, "unobserved-red")
        response = self.session.call(100, fabricated, expected=2)
        self.assertRegex(json.dumps(response), r"(?i)proof|verification|check|baseline")
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        red_reference, red = self.candidate(alpha, 1)
        self.review_candidate("alpha", 1)
        self.assertEqual(1, red["commands"][0]["exit_code"])
        beta = self.acquire_workspace("beta")
        self.assertIn(red_reference["hash"], json.dumps(beta["lease"]["acquisition"]))
        (self.fixture.repo / "source.py").write_text("def value():\n    return 2\n")
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        response = self.session.call(100, self.session.submission(beta, {"value": "Claimed passing implementation without observed checks"}, "unobserved-green"), expected=2)
        self.assertRegex(json.dumps(response), r"(?i)proof|verification|check")
        self.assertEqual(before, (self.provider.issues, self.provider.comments))
        green_reference, green = self.candidate(beta, 0)
        if observer:
            observer("candidate")
        self.assertNotIn(self.ids["observe"], self.names(), "Candidate must receive its separate verification and review")
        self.review_candidate("beta", 0)
        if observer:
            observer("reviewed")
        self.session.git("add", "source.py", "behavior_test.py")
        self.session.git("commit", "-qm", "verified generic delivery")
        self.observation["head_oid"] = self.session.git("rev-parse", "HEAD")
        self.assertEqual(self.fixture.base_oid, self.session.git("rev-parse", "dev"))
        observer = self.session.acquire(self.ids["observe"])
        self.assertIn(self.produced("beta")["hash"], json.dumps(observer["lease"]["acquisition"]))
        self.session.finish(observer, {"value": self.observed_value()})
        self.assertEqual(red, self.read_blob(red_reference))
        self.assertEqual(green, self.read_blob(green_reference))
        self.submit_role("review", "Reviewed exact head and connected passing proof", actor="publication-reviewer")
        self.assertNotIn(self.ids["finish"], self.names())
        self.submit_role("approve", {"subject": self.produced(self.ids["observe"]), "review": self.produced(self.ids["review"]), "policy": content_hash(self.session.project["policy"]), "decision": "approved"})
        self.assertNotIn(self.ids["finish"], self.names())
        request = self.integration_request(self.produced(self.ids["approve"]))
        request["request_id"] = "connected-delivery-integration"
        self.session.call(100, request)
        self.assertEqual(1, len(self.merge_calls))
        self.assertTrue(self.observation["merged"])
        post_effect = self.session.acquire("observed_merge")
        self.session.finish(post_effect, {"value": self.merge_value()})
        self.submit_role("finish", "Current connected delivery and observed merge evidence")
        self.assertEqual(red, self.read_blob(red_reference))
        self.assertEqual(green, self.read_blob(green_reference))
        self.assertEqual(0, green["commands"][0]["exit_code"])

    def test_second_sibling_consumes_reviewed_committed_first_proof_without_rewriting_history(self):
        import sys
        (self.fixture.repo / "second_source.py").write_text("value = 1\n")
        self.session.git("add", "second_source.py")
        self.session.git("commit", "-qm", "second sibling baseline")
        # Setup changed dev before any delivery work; bind the actual new base.
        self.fixture.base_oid = self.session.git("rev-parse", "dev")
        self.observation["base_oid"] = self.fixture.base_oid
        prepared = {}
        def qualify(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    if key == "goal" and child == 100:
                        value[key] = 102
                    else:
                        qualify(child)
            elif isinstance(value, list):
                for child in value:
                    qualify(child)
        def allocation(graph, manifest):
            second = copy.deepcopy(graph)
            qualify(second)
            second_manifest = copy.deepcopy(manifest)
            for name, entry in second_manifest["allocations"].items():
                entry["task"]["goal"] = 102
                entry["owned"] = {"alpha": ["second_test.py"], "beta": ["second_source.py"], "gamma": []}[name]
                entry["consumed"] = ["source.py", "behavior_test.py", "read_dependency.txt", "second_source.py", "second_test.py"]
                manifest["allocations"]["second_" + name] = copy.deepcopy(entry)
            approval = task("accept_first_root", ["accept_beta"], role="root")
            approval["inputs"] = {"candidate": dag_fixtures.subject_input("beta"),
                                  "review": dag_fixtures.subject_input("accept_beta")}
            graph["nodes"].append(approval)
            for node in second["nodes"]:
                if node["id"] not in ("alpha", "beta", "gamma"):
                    continue
                node["requires"].append(selector("accept_first_root"))
                for key, name in (("first_candidate", "beta"), ("first_review", "accept_beta"), ("first_root", "accept_first_root")):
                    node["inputs"][key] = dag_fixtures.subject_input(name)
                for slot, original in (("parent_allocation", "allocation"), ("parent_authorization", "authorization"), ("parent_approval", "approval")):
                    node["inputs"][slot] = copy.deepcopy(node["inputs"][original])
                    node["inputs"][slot]["producer"]["node"]["goal"] = 99
                    if slot == "parent_allocation":
                        node["inputs"][slot]["path"] = ["allocations", "second_" + node["id"]]
            second_approval = task("accept_second_root", role="root")
            second_approval["executor"]["authority"]["subject"]["goal"] = 102
            second_approval["requires"] = [{**selector("accept_beta"), "goal": 102}]
            second_approval["inputs"] = {"candidate": dag_fixtures.subject_input("beta"),
                                         "review": dag_fixtures.subject_input("accept_beta")}
            qualify(second_approval["inputs"])
            second["nodes"].append(second_approval)
            gamma = next(node for node in second["nodes"] if node["id"] == "gamma")
            gamma["requires"].append({**selector("accept_second_root"), "goal": 102})
            gamma["inputs"]["second_root"] = dag_fixtures.subject_input("accept_second_root")
            gamma["inputs"]["second_root"]["producer"]["node"]["goal"] = 102
            prepared.update(graph=second, manifest=second_manifest)
        def second_output(name, slot="value"):
            return self.result_at(102, name)[1]["outputs"][slot]
        def observe(stage):
            if stage == "prepared":
                self.add_goal(102, prepared["graph"], parent=99)
                self.session.finish(self.session.acquire("charter", number=102), {"grant": prepared["manifest"]}, number=102)
                permit = {"manifest": second_output("charter", "grant"),
                          "tasks": [entry["task"] for entry in prepared["manifest"]["allocations"].values()],
                          "policy": content_hash(self.session.project["policy"]), "decision": "approved"}
                self.session.finish(self.session.acquire("inspect_charter", number=102, actor="second-allocation-reviewer"), {"permit": permit}, number=102)
                self.session.finish(self.session.acquire("consent", number=102), {"permit": permit}, number=102)
            self.assertFalse(any(step["node"]["node"] == "alpha" for step in self.session.ready(102)),
                             "First candidate needs both current independent review and root acceptance")
            if stage == "reviewed":
                self.session.finish(self.session.acquire("accept_first_root"), {"value": "Root accepts exact independently reviewed first sibling"})
                self.assertTrue(any(step["node"]["node"] == "alpha" for step in self.session.ready(102)))
        self.connected_delivery(parent=True, allocation_mutator=allocation, observer=observe)
        first_envelope = self.envelope_for(100)
        first_envelope["state"] = "archived"
        first_envelope["revision"] += 1
        self.put_envelope(100, first_envelope)
        self.provider.issues[100]["state"] = "closed"
        # Seed a fully addressed but disconnected historical Result/proof chain
        # before freezing history. Current payload selection, not cache eviction,
        # makes the corrupt predecessor observable to the second child.
        valid_payload = self.read_blob(first_envelope["payload"])
        beta_result_ref, beta_result = self.result("beta")
        bad_artifact = copy.deepcopy(self.read_blob(beta_result["outputs"]["value"]))
        bad_proof = copy.deepcopy(self.read_blob(bad_artifact["provenance"]["source"]))
        bad_proof["acquisition_hash"] = "sha256:" + "0" * 64
        bad_artifact["provenance"]["source"] = self.blob(bad_proof)
        bad_result = copy.deepcopy(self.read_blob(beta_result_ref))
        bad_result["content"]["outputs"]["value"] = self.blob(bad_artifact)
        bad_result_ref = self.blob(bad_result)
        bad_payload = copy.deepcopy(valid_payload)
        bad_payload["evidence"] = [bad_result_ref if ref == beta_result_ref else ref for ref in bad_payload["evidence"]]
        bad_payload_ref = self.blob(bad_payload)
        unknown_artifact = copy.deepcopy(self.read_blob(beta_result["outputs"]["value"]))
        unknown_artifact["provenance"]["source"] = {"hash": "sha256:" + "9" * 64, "uri": "urn:sha256:" + "9" * 64}
        unknown_result = copy.deepcopy(self.read_blob(beta_result_ref))
        unknown_result["content"]["outputs"]["value"] = self.blob(unknown_artifact)
        unknown_result_ref = self.blob(unknown_result)
        unknown_payload = copy.deepcopy(valid_payload)
        unknown_payload["evidence"] = [unknown_result_ref if ref == beta_result_ref else ref for ref in unknown_payload["evidence"]]
        unknown_payload_ref = self.blob(unknown_payload)
        second_envelope = self.envelope_for(102)
        second_payload = copy.deepcopy(self.read_at(102, second_envelope["payload"]))
        changed_spec = copy.deepcopy(self.read_at(102, second_payload["spec"]))
        changed_spec["content"] = "Different second allocation requires new independent authorization"
        offset = len(self.provider.comments[100])
        second_payload["spec"] = self.blob(changed_spec)
        stale_second_ref = self.blob(second_payload)
        for comment in copy.deepcopy(self.provider.comments[100][offset:]):
            self.provider.create_issue_comment(102, comment["body"])
        frozen_first = copy.deepcopy((self.provider.issues[100], self.provider.comments[100]))
        frozen_parent = copy.deepcopy((self.provider.issues[99], self.provider.comments[99]))
        first_candidate = self.produced("beta")
        first_proof = self.read_blob(first_candidate)["provenance"]["source"]
        proof_bytes = self.read_blob(first_proof)
        self.session.git("checkout", "-qb", "second-sibling")
        start_step = next(step for step in self.session.ready(102) if step["node"]["node"] == "alpha")
        stale_start = {**start_step["start"], "policy_receipt": json.loads(Path(start_step["policy"]["path"]).read_text())["policy_receipt"]}
        stale_start.pop("request_id", None)
        stable_second = copy.deepcopy(self.provider.issues[102])
        for label, number, envelope, payload_ref in (
                ("disconnected_first_proof", 100, first_envelope, bad_payload_ref),
                ("unknown_first_proof", 100, first_envelope, unknown_payload_ref),
                ("stale_second_allocation_contract", 102, second_envelope, stale_second_ref)):
            with self.subTest(boundary=label):
                self.put_envelope(number, {**envelope, "payload": payload_ref, "revision": envelope["revision"] + 1})
                before = copy.deepcopy((self.provider.issues, self.provider.comments))
                self.session.call(102, stale_start, expected=2)
                self.assertEqual(before, (self.provider.issues, self.provider.comments))
                self.provider.issues[100] = copy.deepcopy(frozen_first[0])
                self.provider.issues[102] = copy.deepcopy(stable_second)
                self.assertEqual(start_step["input_hash"], next(step["input_hash"] for step in self.session.ready(102) if step["node"]["node"] == "alpha"))
        def candidate(name, expected):
            work = self.session.acquire(name, number=102, actor="second-writer-" + name)
            self.assertIn(first_candidate["hash"], json.dumps(work["lease"]["acquisition"]))
            self.assertIn(first_proof["hash"], json.dumps(work["lease"]["acquisition"]))
            if name == "alpha":
                (self.fixture.repo / "second_test.py").write_text("from second_source import value\nassert value == 2\n")
            else:
                (self.fixture.repo / "second_source.py").write_text("value = 2\n")
            request = self.session.submission(work, {"value": "Exact second " + name}, "second-" + name)
            request["workspace_checks"] = [[sys.executable, "-B", "second_test.py"]]
            self.session.call(102, request)
            ref = self.read_at(102, second_output(name))["provenance"]["source"]
            self.assertEqual(expected, self.read_at(102, ref)["commands"][0]["exit_code"])
            for check, actor in (("observe_", "second-checker"), ("accept_", "second-reviewer")):
                self.session.finish(self.session.acquire(check + name, number=102, actor=actor), {"value": "Exact second proof reviewed"}, number=102)
            self.assertEqual(frozen_first, (self.provider.issues[100], self.provider.comments[100]))
            self.assertEqual(frozen_parent, (self.provider.issues[99], self.provider.comments[99]))
            self.assertEqual(proof_bytes, self.read_blob(first_proof))
        candidate("alpha", 1)
        self.session.git("add", "second_test.py")
        self.session.git("commit", "-qm", "second sibling observed red test")
        candidate("beta", 0)
        self.assertFalse(any(step["node"]["node"] == "gamma" for step in self.session.ready(102)),
                         "Second sibling independent review cannot replace its configured root approval")
        self.session.finish(self.session.acquire("accept_second_root", number=102),
                            {"value": "Root accepts exact second candidate and independent review"}, number=102)
        self.session.git("add", "second_source.py")
        self.session.git("commit", "-qm", "second sibling observed green implementation")
        ready = next(step for step in self.session.ready(102) if step["node"]["node"] == "gamma")
        corrupt = {**first_envelope, "payload": bad_payload_ref, "revision": first_envelope["revision"] + 1}
        self.put_envelope(100, corrupt)
        self.assertFalse(any(step.get("kind") == "execute" and step.get("node", {}).get("node") == "gamma"
                             for step in self.session.checkpoint(102)))
        # Restore the exact provider snapshot; no workflow decision is patched.
        self.provider.issues[100] = copy.deepcopy(frozen_first[0])
        self.assertEqual(ready["input_hash"], next(step["input_hash"] for step in self.session.ready(102) if step["node"]["node"] == "gamma"))
        for name, changed in (("source.py", "def value():\n    return 1\n"), ("read_dependency.txt", "unrelated consumed drift\n")):
            path = self.fixture.repo / name
            original = path.read_bytes()
            path.write_text(changed)
            steps = self.session.checkpoint(102)
            self.assertFalse(any(step.get("kind") == "execute" and step.get("node", {}).get("node") == "gamma" for step in steps))
            path.write_bytes(original)
            self.assertEqual(ready["input_hash"], next(step["input_hash"] for step in self.session.ready(102) if step["node"]["node"] == "gamma"))
        final = self.session.acquire("gamma", number=102)
        self.session.finish(final, {"value": "Both sibling transformations remain connected"}, number=102)
        self.assertEqual(frozen_first, (self.provider.issues[100], self.provider.comments[100]))
        self.assertEqual(proof_bytes, self.read_blob(first_proof))

    def test_parent_requires_both_children_current_terminals_and_archived_merge_evidence(self):
        self.connected_delivery(parent=True)
        self.assertFalse(any(step["node"]["node"] == "collect" for step in self.session.ready(99)),
                         "One delivered child cannot replace its still-unreviewed sibling")
        inspect = self.session.acquire("inspect_shared_merge", number=101, actor="shared-merge-reviewer")
        self.assertIn(self.produced("observed_merge")["hash"], json.dumps(inspect["lease"]["acquisition"]))
        self.session.finish(inspect, {"value": "Independent review of exact shared delivered merge"}, number=101)
        self.assertFalse(any(step["node"]["node"] == "collect" for step in self.session.ready(99)))
        checkpoint = self.session.checkpoint(101)
        if len(checkpoint) == 1 and checkpoint[0]["kind"] == "hydration_checkpoint":
            self.session.call(101, checkpoint[0]["submission"])
        finish = self.session.acquire(self.ids["finish"], number=101)
        self.session.finish(finish, {"value": "Second child root accepted exact reviewed delivery"}, number=101)
        self.assertTrue(any(step["node"]["node"] == "collect" for step in self.session.ready(99)))
        sibling_output = self.result_at(101, self.ids["finish"])[1]["outputs"]["value"]
        envelope = self.envelope_for(101)
        envelope["state"] = "archived"
        envelope["revision"] += 1
        self.put_envelope(101, envelope)
        self.provider.issues[101]["state"] = "closed"
        self.assertTrue(any(step["node"]["node"] == "collect" for step in self.session.ready(99)),
                        "Archived required child keeps exact usable terminal evidence")
        exact = copy.deepcopy(envelope)
        unknown = copy.deepcopy(envelope)
        unknown["revision"] += 1
        unknown["payload"] = {"hash": "sha256:" + "0" * 64, "uri": "urn:sha256:" + "0" * 64}
        self.put_envelope(101, unknown)
        blocked = self.session.call(99, expected=None)
        self.assertFalse(any(step.get("node", {}).get("node") == "collect" and step.get("kind") == "execute"
                             for step in blocked["next_steps"]))
        self.assertRegex(json.dumps(blocked), r"(?i)unknown|artifact|unavailable|missing|relationship")
        self.assertEqual("closed", self.provider.issues[101]["state"])
        exact["revision"] = unknown["revision"] + 1
        self.put_envelope(101, exact)
        aggregate = self.session.acquire("collect", number=99)
        acquisition = json.dumps(aggregate["lease"]["acquisition"])
        self.assertIn(self.produced(self.ids["finish"])["hash"], acquisition)
        self.assertIn(sibling_output["hash"], acquisition)
        selected = [r for r in self.resolutions(aggregate) if r["selector"]["goal"] == "#children"]
        self.assertTrue(selected)
        self.assertTrue(all({100, 101} == {t["goal"] for t in r["targets"]} for r in selected))
        self.session.finish(aggregate, {"value": "Both canonical children delivered and currently accepted"}, number=99)
        self.assertEqual([], self.session.ready(99))


if __name__ == "__main__":
    unittest.main()
