"""Full reviewed-DAG journey through durable public workflow state."""

from __future__ import annotations

import contextlib
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import test_zzzops as fixtures


z = fixtures.zzzops


class MemoryGoalProvider:
    """A multi-issue provider with read-after-write behavior matching GitHub."""

    repository = "owner/repo"

    def __init__(self, issues):
        self.issues = {issue["number"]: copy.deepcopy(issue) for issue in issues}
        self.comments = {number: [] for number in self.issues}
        self.updates = []

    def get_issue(self, number):
        return copy.deepcopy(self.issues[number])

    def update_issue(self, number, payload):
        self.updates.append((number, copy.deepcopy(payload)))
        issue = self.issues[number]
        issue.update({
            "body": payload["body"], "state": payload["state"],
            "updated_at": f"2026-09-17T12:{len(self.updates):02d}:00Z",
            "labels": [{"name": label} for label in payload["labels"]],
        })
        return copy.deepcopy(issue)

    def get_issue_comments(self, number):
        return copy.deepcopy(self.comments[number])

    def create_issue_comment(self, number, body):
        comment = {
            "id": len(self.comments[number]) + 1, "body": body,
            "html_url": f"https://github.com/owner/repo/issues/{number}#issuecomment-{len(self.comments[number]) + 1}",
        }
        self.comments[number].append(copy.deepcopy(comment))
        return copy.deepcopy(comment)


class FullWorkflowJourneyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        subprocess.run(["git", "init", "-q", "-b", "dev", str(self.repo)], check=True)
        subprocess.run(["git", "-C", str(self.repo), "config", "user.email", "journey@example.test"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "config", "user.name", "Journey"], check=True)
        (self.repo / "product.txt").write_text("baseline\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.repo), "add", "product.txt"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "commit", "-qm", "baseline"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "branch", "goal-child"], check=True)
        self.base_oid = subprocess.check_output(
            ["git", "-C", str(self.repo), "rev-parse", "dev"], text=True,
        ).strip()
        self.head_oid = subprocess.check_output(
            ["git", "-C", str(self.repo), "rev-parse", "goal-child"], text=True,
        ).strip()
        self.merge_oid = "f" * 40
        self.pr_merged = False

        template = json.loads((fixtures.PLUGIN_ROOT / "zzzops/templates/project-goals/INIT_PLAN.json").read_text(encoding="utf-8"))
        self.project = {
            "backend": "github_issues", "repository": {"identity": "owner/repo"},
            "policy": template["policy"],
        }
        routing = z._workflow_section(self.project, "model_routing")["configuration"]
        routing["model_inventory"]["reviewed_pairs"] = [
            {"model": "worker-routine", "effort": "low", "tier": "routine", "cost": 1},
            {"model": "worker-bounded", "effort": "medium", "tier": "bounded", "cost": 2},
            {"model": "worker-reasoning", "effort": "high", "tier": "reasoning", "cost": 3},
            {"model": "root", "effort": "high", "tier": "architectural", "cost": 10},
        ]
        self.runtime = {
            "root_pair": {"model": "root", "effort": "high"},
            "available_pairs": [
                {"model": "worker-routine", "effort": "low"},
                {"model": "worker-bounded", "effort": "medium"},
                {"model": "worker-reasoning", "effort": "high"},
                {"model": "root", "effort": "high"},
            ],
            "root_id": "root-thread",
            "delegation": {"available": True, "tool": "spawn_agent", "discovery_complete": True},
        }
        self.provider = MemoryGoalProvider([
            self.issue(100, parent=None, title="Ship the complete outcome"),
            self.issue(101, parent=100, title="Implement the child behavior"),
        ])
        self.patches = [
            mock.patch.object(z, "GitHubGoalTransitionAdapter", return_value=self.provider),
            mock.patch.object(z, "portfolio_snapshot", side_effect=self.portfolio),
            mock.patch.object(z, "_github_pull_request_states", side_effect=self.pull_request_states),
        ]
        for patch in self.patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.engine = z.workflow_engine(self.repo, self.project, self.runtime)
        self.engine.locked = contextlib.nullcontext
        self.sequence = 0

    def issue(self, number, *, parent, title):
        goal = fixtures.GoalTransitionTests().goal()
        goal.update({
            "parent": parent, "difficulty": "M", "engineering_rigor": {"risk_categories": [], "override": None},
            "implementation": {
                "branch": None, "base": None, "target": None, "pr": None,
                "review": {"status": "not_started", "checkpoint": None},
            },
        })
        body = z.render_managed_goal(
            goal,
            "## Outcome / Why\n\nDeliver the requested behavior.\n\n## Acceptance\n\n- [ ] Observable behavior passes.\n",
            number,
        )
        return {
            "number": number, "title": title, "body": body, "state": "open",
            "updated_at": "2026-09-17T12:00:00Z",
            "html_url": f"https://github.com/owner/repo/issues/{number}",
            "labels": [{"name": "zzzops"}, {"name": "zzzops:status:ready"}, {"name": "zzzops:priority:P2"}],
        }

    def portfolio(self, _repo):
        return {
            "complete": True, "valid": True,
            "goals": [z.github_goal_record(self.provider.get_issue(number)) for number in sorted(self.provider.issues)],
        }

    def pull_request_states(self, _repo, executable, selected, bodies):
        self.assertEqual("gh", executable)
        self.assertEqual([101], [item["number"] for item in selected])
        self.assertIn(101, bodies)
        return ({101: {
            "merged": self.pr_merged,
            "merged_at": "2026-09-17T14:00:00Z" if self.pr_merged else None,
            "head_oid": self.head_oid,
            "base_oid": self.base_oid,
            "base_ref": "dev",
            "merge_commit": self.merge_oid if self.pr_merged else None,
            "repository": "owner/repo",
            "checks_verified": True,
            "review_verified": self.pr_merged,
        }}, 512, 1)

    def goal(self, number):
        return z.github_goal_record(self.provider.get_issue(number))

    def mutate(self, number, **payload):
        self.sequence += 1
        request_id = f"journey-{self.sequence}"
        before = self.goal(number)["revision"]
        request = {**payload, "request_id": request_id}
        result = self.engine.mutate(number, request)
        reread = self.goal(number)
        self.assertGreater(reread["revision"], before)
        self.assertIn(request_id, reread["workflow"]["receipts"])
        return result, reread

    @staticmethod
    def artifact(label):
        digest = "sha256:" + hashlib.sha256(label.encode()).hexdigest()
        return {"reference": "urn:" + digest, "hash": digest}

    def assess(self, number, phase):
        step = self.engine.step(number)[0]
        self.assertEqual(("assess", phase), (step["kind"], step["phase"]))
        self.mutate(
            number, operation="assess", phase=phase, input_hash=step["input_hash"], files=[],
            dimensions={"consequence": "bounded", "boundedness": "atomic", "engineering_rigor": "structured"},
        )

    def start(self, number, phase, kind):
        step = self.engine.step(number)[0]
        if step["kind"] == "assess":
            self.assess(number, phase)
            step = self.engine.step(number)[0]
        self.assertEqual((kind, phase), (step["kind"], step["phase"]))
        z._policy_context.attach({'next_steps': [step]}, self.repo, self.project, source='$execute-zzzops')
        receipt = json.loads(Path(step['policy']['path']).read_text())['policy_receipt']
        result, _goal = self.mutate(number, **{**step["start"], 'policy_receipt': receipt})
        perform = result["next_steps"][0]
        self.assertEqual("perform", perform["kind"])
        return perform

    def bind(self, number, step, actor):
        lease = step["lease"]
        z._policy_context.attach({'next_steps': [step]}, self.repo, self.project, source='$execute-zzzops')
        receipt = json.loads(Path(step['policy']['path']).read_text())['policy_receipt']
        if lease["worker"] is None:
            self.mutate(
                number, operation="bind", phase=step["phase"], lease=lease["token"],
                actor=actor, selection=lease["selection"], policy_receipt=receipt,
            )
        return lease

    def execute(self, number, phase, *, verifier=None, wrong_pair=False, output_suffix=""):
        step = self.start(number, phase, "execute")
        actor = "root-thread" if step["assignment"] == "root" else f"{number}-{phase}-executor{output_suffix}"
        lease = self.bind(number, step, actor)
        verification = None
        test_design = None
        if verifier is not None:
            command = [sys.executable, "-c", f"raise SystemExit({0 if verifier == 'pass' else 1})"]
            verified, _goal = self.mutate(
                number, operation="verify", phase=phase, lease=lease["token"], actor=actor, commands=[command],
            )
            verification = verified["next_steps"][0]["verification"]
            proof = self.engine.read_artifact(number, verification)
            self.assertEqual(verifier == 'pass', proof['passed'])
            if phase == "test_design":
                test_design = {
                    "baseline_failure": verification,
                    "coverage": [{
                        "criterion": criterion, "test": self.artifact(f"test-{number}-{index}"), "exclusion": None,
                    } for index, criterion in enumerate(step["input_envelope"]["acceptance_criteria"])],
                }
                verification = None
        record = copy.deepcopy(step["result_contract"]["record"])
        record.update({
            "output": self.engine.artifact(number, {"output": f"{number}-{phase}{output_suffix}"}), "actor": actor,
            "selection": copy.deepcopy(lease["selection"]), "verification": verification,
            "test_design": test_design,
        })
        if phase == 'publish':
            missing = copy.deepcopy(record)
            missing['verification'] = None
            with self.assertRaisesRegex(ValueError, 'passing verification'):
                self.engine.mutate(number, {
                    'request_id': f'missing-publication-verification-{number}',
                    'operation': 'record_result', 'phase': phase, 'lease': lease['token'],
                    'actor': actor, 'record': missing, 'files': [],
                })
        if wrong_pair:
            invalid = copy.deepcopy(record)
            invalid["selection"] = {"model": "wrong", "effort": "wrong"}
            before = self.goal(number)
            with self.assertRaisesRegex(ValueError, "model/effort"):
                self.engine.mutate(number, {
                    "request_id": f"rejected-{number}-{phase}", "operation": "record_result", "phase": phase,
                    "lease": lease["token"], "actor": actor, "files": [], "record": invalid,
                })
            self.assertEqual(before["revision"], self.goal(number)["revision"])
            self.assertNotIn(phase, (self.goal(number).get("phase_evidence") or {}).get("records", {}))
        self.mutate(
            number, operation="record_result", phase=phase, lease=lease["token"], actor=actor,
            files=[], record=record,
        )

    def review(self, number, phase, *, decision="approved"):
        step = self.start(number, phase, "review")
        actor = f"{number}-{phase}-reviewer-{self.sequence}"
        record_actor = self.goal(number)["phase_evidence"]["records"][phase]["actor"]
        self.assertNotEqual(record_actor, actor)
        lease = self.bind(number, step, actor)
        self.mutate(
            number, operation="record_review", phase=phase, lease=lease["token"], actor=actor,
            artifact=self.engine.artifact(number, {"review": f"review-{number}-{phase}-{self.sequence}"}),
            outcomes={
                "acceptance": decision,
                "entropy": {"outcome": "no_findings", "evidence": f"Independently inspected {phase} evidence.", "goals": []},
            },
        )

    def approve(self, number, phase):
        step = self.start(number, phase, "human_approval")
        self.assertEqual("root", step["assignment"])
        self.mutate(
            number, operation="approve", phase=phase, lease=step["lease"]["token"], actor="root-thread",
            approval={"actor": "root-thread", "approval_token": f"user:approved-{number}-{phase}"},
        )

    def phase(self, number, phase, *, verifier=None, wrong_pair=False, reject_once=False):
        self.execute(number, phase, verifier=verifier, wrong_pair=wrong_pair)
        if reject_once:
            self.review(number, phase, decision="changes_requested")
            step = self.engine.step(number)[0]
            self.assertEqual(("execute", phase), (step["kind"], step["phase"]))
            self.execute(number, phase, verifier=verifier, output_suffix="-corrected")
        self.review(number, phase)
        node = z._workflow_phase_configuration(self.project, self.goal(number))[1][phase]
        if node["review"]["human_approval"]:
            self.approve(number, phase)

    def test_parent_and_child_complete_only_from_reviewed_full_dag_evidence(self):
        # Parent understanding is independently reviewed and explicitly approved.
        self.phase(100, "understand")
        parent = self.goal(100)
        self.assertIn("understand", parent["phase_evidence"]["human_approvals"])

        # A child can understand its goal, but its plan remains gated by the parent's decomposition.
        self.phase(101, "understand")
        gated = self.engine.step(101)[0]
        self.assertEqual("dependency", gated["kind"])
        self.assertTrue(gated["blocked"])

        self.phase(100, "decompose")
        self.phase(100, "plan", wrong_pair=True, reject_once=True)

        # Parent publication and completion are impossible until implementation children finish.
        blocked = self.engine.step(100)[0]
        self.assertEqual("dependency", blocked["kind"])
        self.assertEqual([101], blocked["children"])
        with self.assertRaisesRegex(ValueError, "completion|publication"):
            self.engine.mutate(100, {"request_id": "parent-too-early", "operation": "complete"})
        self.assertNotEqual("done", self.goal(100)["status"])

        self.phase(101, "plan")

        # No result may claim behavioural tests without an observed failing baseline.
        design = self.start(101, "test_design", "execute")
        design_actor = "101-test_design-no-proof"
        design_lease = self.bind(101, design, design_actor)
        fabricated = copy.deepcopy(design["result_contract"]["record"])
        fabricated.update({
            "output": self.artifact("fabricated-design"), "actor": design_actor,
            "selection": design_lease["selection"],
            "test_design": {
                "baseline_failure": self.artifact("not-observed"),
                "coverage": [{"criterion": criterion, "test": self.artifact("claimed-test"), "exclusion": None}
                             for criterion in design["input_envelope"]["acceptance_criteria"]],
            },
        })
        with self.assertRaisesRegex(ValueError, "failing-baseline"):
            self.engine.mutate(101, {
                "request_id": "fabricated-test-design", "operation": "record_result", "phase": "test_design",
                "lease": design_lease["token"], "actor": design_actor, "files": [], "record": fabricated,
            })
        self.mutate(
            101, operation="release", phase="test_design", lease=design_lease["token"],
            worker_status="stopped", evidence="Test worker stopped after rejected unverified submission.",
        )
        self.phase(101, "test_design", verifier="fail")

        # Implementation likewise requires a current passing verifier artifact.
        implementation = self.start(101, "implement", "execute")
        implementation_actor = "101-implement-no-proof"
        implementation_lease = self.bind(101, implementation, implementation_actor)
        fabricated = copy.deepcopy(implementation["result_contract"]["record"])
        fabricated.update({
            "output": self.artifact("fabricated-implementation"), "actor": implementation_actor,
            "selection": implementation_lease["selection"], "verification": self.artifact("not-observed"),
        })
        with self.assertRaisesRegex(ValueError, "passing verification"):
            self.engine.mutate(101, {
                "request_id": "fabricated-implementation", "operation": "record_result", "phase": "implement",
                "lease": implementation_lease["token"], "actor": implementation_actor, "files": [], "record": fabricated,
            })
        self.mutate(
            101, operation="release", phase="implement", lease=implementation_lease["token"],
            worker_status="stopped", evidence="Implementation worker stopped after rejected unverified submission.",
        )
        self.phase(101, "implement", verifier="pass")
        self.assertNotIn("implement", self.goal(101)["phase_evidence"]["human_approvals"])

        implementation_metadata = {
            "branch": "goal-child", "base": "dev", "target": "dev",
            "pr": "https://github.com/owner/repo/pull/101",
            "review": {"status": "not_started", "checkpoint": None},
        }
        child = self.goal(101)
        self.mutate(
            101, operation="revise", expected_digest=child["digest"],
            changes={"implementation": implementation_metadata},
        )

        real_run = subprocess.run

        def provider_boundary(command, *args, **kwargs):
            if command[:3] == ["gh", "pr", "list"]:
                pulls = [] if self.pr_merged else [{
                    "headRefName": "goal-child", "baseRefName": "dev", "headRefOid": self.head_oid,
                }]
                return SimpleNamespace(returncode=0, stdout=json.dumps(pulls), stderr="")
            if command[:3] == ["gh", "pr", "merge"]:
                self.assertEqual(self.head_oid, command[-1])
                self.pr_merged = True
                return SimpleNamespace(returncode=0, stdout="", stderr="")
            return real_run(command, *args, **kwargs)

        with mock.patch.object(z._workflow.subprocess, "run", side_effect=provider_boundary):
            self.phase(101, "publish", verifier="pass")
            integration = self.engine.step(101)[0]
            self.assertEqual("integration", integration["kind"])
            self.assertEqual(self.head_oid, integration["head"])
            self.assertFalse(self.pr_merged)
            self.mutate(
                101, operation="integrate", expected_head=self.head_oid,
                approved_by="user:exact-head-approval",
            )
            self.assertTrue(self.pr_merged)
            integrated = self.goal(101)["implementation"]["review"]
            self.assertEqual({"status": "approved", "checkpoint": self.head_oid}, integrated)
            completion = self.engine.step(101)[0]
            self.assertEqual("complete", completion["kind"])
            self.mutate(101, **completion["submission"])
        self.assertEqual("done", self.goal(101)["status"])

        # Child completion becomes aggregate input; the parent can now publish and complete.
        self.phase(100, "publish", verifier="pass")
        completion = self.engine.step(100)[0]
        self.assertEqual("complete", completion["kind"])
        self.mutate(100, **completion["submission"])
        self.assertEqual("done", self.goal(100)["status"])

        for number in (100, 101):
            durable = self.goal(number)["phase_evidence"]
            for phase, record in durable["records"].items():
                self.assertIn(phase, durable["reviews"])
                self.assertEqual("completed", record["status"])


if __name__ == "__main__":
    unittest.main()
