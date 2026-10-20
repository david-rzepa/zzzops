"""Pure scheduling, readiness, provenance, and approval contracts."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import copy
import unittest


ROOT = Path(__file__).resolve().parents[1]
SUBJECT = ROOT / "plugins" / "zzzops" / "zzzops" / "releases.py"


def load_subject():
    if not SUBJECT.exists(): raise AssertionError("release planning requires releases.py")
    spec = importlib.util.spec_from_file_location("release_workflow_subject", SUBJECT)
    module = importlib.util.module_from_spec(spec); assert spec and spec.loader
    spec.loader.exec_module(module); return module


def goal(key, *, release=None, priority="P2", state="write", depends_on=(), commit=None, status="ready", branch=None):
    value = {"key": key, "priority": priority, "work_state": state, "depends_on": list(depends_on), "status": status}
    if release is not None: value["target_release"] = release
    if commit is not None: value["integrated_commit"] = commit
    if branch is not None: value["implementation"] = {"branch": branch}
    return value


class ReleaseWorkflowContractTests(unittest.TestCase):
    def setUp(self): self.r = load_subject()

    def test_disabled_mode_preserves_existing_portfolio_order(self):
        records = [goal(1, priority="P2"), goal(2, priority="P0"), goal(3, priority="P1")]
        result = self.r.select_release_work(records, {"enabled": False}, plan=None, owned=set())
        self.assertEqual([2, 3, 1], [row["goal"] for row in result["ordered"]])
        self.assertTrue(all(row["reason"] == "priority_then_key" for row in result["ordered"]))

    def test_current_release_exhausts_before_later_release(self):
        records = [goal(1, release=1), goal(2, release=2, priority="P0"), goal(3, priority="P1")]
        plan = {"next_release": 1, "assignments": {"1": 1, "2": 2}}
        strict = self.r.select_release_work(records, {"enabled": True, "execution_scope": "active_only"}, plan, owned=set())
        self.assertEqual([3, 1], [row["goal"] for row in strict["ordered"]])
        flexible = self.r.select_release_work([goal(1, release=1, state="wait_human"), goal(2, release=2)],
            {"enabled": True, "execution_scope": "later_when_active_blocked"}, plan, owned=set())
        self.assertEqual([2], [row["goal"] for row in flexible["ordered"]])
        self.assertEqual("later_release_active_blocked", flexible["ordered"][0]["reason"])

    def test_dependency_and_ownership_still_constrain_release_selection(self):
        records = [goal(1, release=1), goal(2, release=1, depends_on=(1,)), goal(3, release=1)]
        result = self.r.select_release_work(records, {"enabled": True, "execution_scope": "active_only"},
            {"next_release": 1, "assignments": {"1": 1, "2": 1, "3": 1}}, owned={3})
        self.assertEqual([1], [row["goal"] for row in result["ordered"]])

    def test_current_goal_depending_on_future_goal_is_actionable_conflict(self):
        records = [goal(4, release=1, depends_on=(2,)), goal(2, release=2)]
        result = self.r.select_release_work(records, {"enabled": True, "execution_scope": "active_only"},
            {"next_release": 1, "assignments": {"4": 1, "2": 2}}, owned=set())
        self.assertEqual([], result["ordered"])
        self.assertEqual("future_release_dependency", result["conflicts"][0]["code"])
        self.assertEqual({"goal": 4, "dependency": 2}, {k: result["conflicts"][0][k] for k in ("goal", "dependency")})

    def test_future_release_work_isolated_until_active_branch_cut(self):
        records = [goal(1, release=1, state="wait_human"), goal(2, release=2, branch="release-2/goal-2")]
        plan = {"next_release": 1, "assignments": {"1": 1, "2": 2}}
        decision = self.r.authorize_integration(records[1], plan, source_branch="release/1", source_ancestors=set())
        self.assertEqual("blocked", decision["status"])
        self.assertEqual("future_release_integration", decision["code"])
        advanced = {**plan, "next_release": 2, "releases": {"1": {"state": "branch_confirmed"}}}
        self.assertEqual("authorized", self.r.authorize_integration(records[1], advanced,
            source_branch="release/2", source_ancestors=set())["status"])

    def test_readiness_requires_integrated_or_removed_members_no_owners_and_observed_evidence(self):
        members = {1: {"status": "done", "integrated_commit": "a" * 40},
                   2: {"status": "cancelled", "cancellation_authority": "sha256:" + "b" * 64}}
        ready = self.r.release_readiness(members, active_owners=set(), observed_commits={"a" * 40}, source_ancestors={"a" * 40})
        self.assertEqual("ready", ready["status"])
        for changed, code in (
            ({"active_owners": {1}}, "active_owner"),
            ({"observed_commits": set()}, "missing_integration_evidence"),
            ({"source_ancestors": set()}, "source_provenance_mismatch"),
        ):
            args = {"active_owners": set(), "observed_commits": {"a" * 40}, "source_ancestors": {"a" * 40}, **changed}
            with self.subTest(code=code): self.assertEqual(code, self.r.release_readiness(members, **args)["code"])
        self.assertEqual("member_incomplete", self.r.release_readiness({1: {"status": "blocked"}},
            active_owners=set(), observed_commits=set(), source_ancestors=set())["code"])

    def test_empty_release_does_not_propose_branch_cut(self):
        self.assertEqual("empty", self.r.release_readiness({}, active_owners=set(), observed_commits=set(), source_ancestors=set())["status"])

    def test_frozen_intent_digest_binds_every_release_boundary_authority(self):
        base = dict(repository="owner/repo", release=1, members={1: "a" * 40}, policy="sha256:" + "b" * 64,
                    source_branch="dev", source_sha="c" * 40, destination="release/1", authority="sha256:" + "d" * 64)
        intent = self.r.freeze_intent(**base)
        for field, value in (("source_sha", "e" * 40), ("destination", "other"), ("authority", "sha256:" + "f" * 64)):
            changed = dict(base); changed[field] = value
            self.assertNotEqual(intent["digest"], self.r.freeze_intent(**changed)["digest"])

    def test_publication_approval_is_exact_and_refreshes_on_source_or_target_change(self):
        frozen = self.r.freeze_intent(repository="owner/repo", release=1, members={1: "a" * 40},
            policy="sha256:" + "b" * 64, source_branch="dev", source_sha="c" * 40,
            destination="release/1", authority="sha256:" + "d" * 64)
        approval = self.r.bind_publication_approval(frozen, target="main")
        self.assertTrue(self.r.approval_matches(approval, frozen, target="main"))
        self.assertFalse(self.r.approval_matches(approval, {**frozen, "source_sha": "e" * 40}, target="main"))
        self.assertFalse(self.r.approval_matches(approval, frozen, target="stable"))

    def test_coordinator_runs_resumable_boundary_and_advances_only_after_confirmation(self):
        class PlanProvider:
            def __init__(self):
                self.record = {"kind": "release-plan", "revision": 0, "next_release": 1,
                    "assignments": {"1": 1, "2": 2}, "releases": {}}
                self.lock = None; self.audit = []
            def acquire_repository_lock(self, repository, request_id):
                if self.lock not in (None, request_id): raise ValueError("concurrent owner")
                self.lock = request_id
            def release_repository_lock(self, repository, request_id):
                if self.lock == request_id: self.lock = None
            def read(self, repository): return copy.deepcopy(self.record)
            def compare_exchange(self, repository, revision, record):
                if revision != self.record["revision"]: raise ValueError("revision changed")
                self.record = copy.deepcopy(record); return copy.deepcopy(record)
            def append_artifact(self, repository, artifact): self.audit.append(copy.deepcopy(artifact))
        class BranchProvider:
            def __init__(self): self.refs = {}; self.mode = "normal"; self.calls = 0
            def observe(self, branch): return self.refs.get(branch)
            def create_only(self, branch, sha):
                self.calls += 1
                if branch in self.refs and self.refs[branch] != sha: raise ValueError("different-SHA conflict")
                if self.mode == "before": raise TimeoutError("unknown before effect")
                self.refs[branch] = sha
                if self.mode == "after": raise TimeoutError("unknown after effect")
                return {"status": "created", "branch": branch, "sha": sha}
        plans, branches = PlanProvider(), BranchProvider()
        coordinator = self.r.ReleaseCoordinator("owner/repo", {
            "enabled": True, "next_release": 1, "integration_branch": "dev",
            "publication_branch": "main", "release_branch_prefix": "release/",
            "execution_scope": "later_when_active_blocked",
        }, plans, branches)
        members = {1: {"status": "done", "integrated_commit": "a" * 40}}
        future = goal(2, release=2, branch="release-2/goal-2", commit="f" * 40)
        self.assertEqual("future_release_integration",
            self.r.authorize_integration(future, plans.record, source_branch="dev",
                                         source_ancestors={"f" * 40})["code"])
        blocked = coordinator.checkpoint({"operation": "propose", "request_id": "propose-future",
            "expected_revision": 0, "members": members, "active_owners": [],
            "observed_commits": ["a" * 40], "source_ancestors": ["a" * 40, "f" * 40],
            "forbidden_commits": ["f" * 40], "source_branch": "dev",
            "source_sha": "a" * 40, "authority": "sha256:" + "b" * 64})
        self.assertEqual("future_release_provenance", blocked["code"])
        self.assertEqual(1, plans.record["next_release"])
        self.assertEqual({}, plans.record["releases"])
        proposal = coordinator.checkpoint({"operation": "propose", "request_id": "propose-1",
            "expected_revision": 0, "members": members, "active_owners": [],
            "observed_commits": ["a" * 40], "source_ancestors": ["a" * 40],
            "source_branch": "dev", "source_sha": "a" * 40, "authority": "sha256:" + "b" * 64})
        self.assertEqual("ready_proposal", proposal["status"])
        self.assertEqual("open", plans.record["releases"].get("1", {"state": "open"})["state"])
        frozen = coordinator.checkpoint({"operation": "freeze", "request_id": "freeze-1",
            "expected_revision": 0, "proposal": proposal})
        self.assertEqual("frozen_intent", frozen["status"])
        self.assertEqual("frozen_intent", plans.record["releases"]["1"]["state"])
        for field, value, code in (("members", {"1": "e" * 40}, "membership_drift"),
                                   ("source_sha", "e" * 40, "source_drift")):
            request = {"operation": "cut", "request_id": "drift-" + field,
                "expected_revision": plans.record["revision"], "intent": frozen["intent"],
                "members": {"1": "a" * 40}, "source_sha": "a" * 40}
            request[field] = value
            self.assertEqual(code, coordinator.checkpoint(request)["code"])
            self.assertEqual(0, branches.calls)
        branches.refs["release/1"] = "e" * 40
        with self.assertRaisesRegex(ValueError, "different|conflict"):
            coordinator.checkpoint({"operation": "cut", "request_id": "cut-conflict",
                "expected_revision": plans.record["revision"], "intent": frozen["intent"],
                "members": {"1": "a" * 40}, "source_sha": "a" * 40})
        branches.refs.clear()
        plans.lock = "other-owner"
        with self.assertRaisesRegex(ValueError, "concurrent"):
            coordinator.checkpoint({"operation": "cut", "request_id": "cut-owned",
                "expected_revision": plans.record["revision"], "intent": frozen["intent"],
                "members": {"1": "a" * 40}, "source_sha": "a" * 40})
        plans.lock = None
        branches.mode = "before"
        pending = coordinator.checkpoint({"operation": "cut", "request_id": "cut-before",
            "expected_revision": plans.record["revision"], "intent": frozen["intent"],
            "members": {"1": "a" * 40}, "source_sha": "a" * 40})
        self.assertEqual("pending", pending["status"])
        self.assertEqual(1, plans.record["next_release"])
        branches.mode = "after"
        cut_after_request = {"operation": "cut", "request_id": "cut-after",
            "expected_revision": plans.record["revision"], "intent": frozen["intent"],
            "members": {"1": "a" * 40}, "source_sha": "a" * 40}
        confirmed = coordinator.checkpoint(cut_after_request)
        self.assertEqual("branch_confirmed", confirmed["status"])
        self.assertEqual(2, plans.record["next_release"])
        replay = coordinator.checkpoint(cut_after_request)
        self.assertEqual("branch_confirmed", replay["status"])
        self.assertEqual("authorized", self.r.authorize_integration(
            future, plans.record, source_branch="dev", source_ancestors={"a" * 40})["status"])

    def test_r1_future_content_blocks_integration_and_freeze_until_confirmed_cut(self):
        r = self.r
        plan = {"revision": 0, "next_release": 1, "assignments": {"1": 1, "2": 2}, "releases": {}}
        future = goal(2, release=2, branch="release-2/goal-2", commit="f" * 40)
        self.assertEqual("future_release_integration",
            r.authorize_integration(future, plan, source_branch="dev", source_ancestors={"f" * 40})["code"])
        readiness = r.release_readiness({1: {"status": "done", "integrated_commit": "a" * 40}},
            active_owners=set(), observed_commits={"a" * 40}, source_ancestors={"a" * 40, "f" * 40},
            forbidden_commits={"f" * 40})
        self.assertEqual("future_release_provenance", readiness["code"])
        with self.assertRaisesRegex(ValueError, "future|provenance"):
            r.freeze_intent(repository="owner/repo", release=1, members={1: "a" * 40},
                policy="sha256:" + "b" * 64, source_branch="dev", source_sha="c" * 40,
                destination="release/1", authority="sha256:" + "d" * 64,
                source_ancestors={"a" * 40, "f" * 40}, forbidden_commits={"f" * 40})

    def test_cancelled_member_requires_goal_authority_and_publication_reads_provider(self):
        members = {1: {"status": "done", "integrated_commit": "a" * 40},
                   2: {"status": "cancelled", "cancellation_authority": None}}
        self.assertEqual("missing_removal_authority", self.r.release_readiness(members,
            active_owners=set(), observed_commits={"a" * 40}, source_ancestors={"a" * 40})["code"])
        members[2]["cancellation_authority"] = "sha256:" + "b" * 64
        self.assertEqual("ready", self.r.release_readiness(members,
            active_owners=set(), observed_commits={"a" * 40}, source_ancestors={"a" * 40})["status"])
        frozen = self.r.freeze_intent(repository="owner/repo", release=1, members={1: "a" * 40},
            policy="sha256:" + "b" * 64, source_branch="dev", source_sha="a" * 40,
            destination="release/1", authority="sha256:" + "d" * 64)
        approval = self.r.bind_publication_approval(frozen, target="main")
        class PublicationProvider:
            def observe_approval(self, reference):
                self.approval_request = reference
                return copy.deepcopy(approval)
            def observe(self, repository, release, target):
                self.request = (repository, release, target)
                return {"tag": "v3.2.1", "version": "3.2.1", "target_sha": "a" * 40}
        provider = PublicationProvider()
        with self.assertRaisesRegex(ValueError, "authenticated|reference"):
            self.r.observe_publication(provider, frozen, {**approval, "decision": "approved"}, target="main")
        publication = self.r.observe_publication(provider, frozen, "approval:release-1-main", target="main")
        self.assertEqual("approval:release-1-main", provider.approval_request)
        self.assertEqual(("owner/repo", 1, "main"), provider.request)
        self.assertEqual(("3.2.1", "v3.2.1"), (publication["version"], publication["tag"]))

    def test_checkpoint_uses_provider_observations_not_forged_caller_facts(self):
        class Plans:
            def __init__(self): self.record = {"revision": 0, "next_release": 1, "assignments": {"1": 1}, "releases": {}}; self.lock = None
            def acquire_repository_lock(self, repository, request_id): self.lock = request_id
            def release_repository_lock(self, repository, request_id): self.lock = None
            def read(self, repository): return copy.deepcopy(self.record)
            def compare_exchange(self, repository, revision, record): self.record = copy.deepcopy(record); return copy.deepcopy(record)
            def append_artifact(self, repository, artifact): pass
        class Observations:
            def observe_release(self, repository, release):
                self.request = (repository, release)
                return {"members": {1: {"status": "in_progress"}}, "active_owners": [1],
                    "observed_commits": [], "source_ancestors": [], "source_branch": "dev",
                    "source_sha": "e" * 40, "forbidden_commits": []}
        observations = Observations()
        coordinator = self.r.ReleaseCoordinator("owner/repo", {
            "enabled": True, "next_release": 1, "integration_branch": "dev",
            "publication_branch": "main", "release_branch_prefix": "release/",
            "execution_scope": "active_only"}, Plans(), branch_provider=None,
            evidence_provider=observations)
        forged = coordinator.checkpoint({"operation": "propose", "request_id": "forged",
            "expected_revision": 0, "members": {1: {"status": "done", "integrated_commit": "a" * 40}},
            "active_owners": [], "observed_commits": ["a" * 40], "source_ancestors": ["a" * 40],
            "source_branch": "dev", "source_sha": "a" * 40, "authority": "sha256:" + "b" * 64})
        self.assertEqual(("owner/repo", 1), observations.request)
        self.assertIn(forged["code"], {"member_incomplete", "active_owner", "source_drift"})
        self.assertNotEqual("ready_proposal", forged["status"])


if __name__ == "__main__": unittest.main()
