"""Contracts for deterministic work bases and provider-bound publication."""

import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


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
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            self.git(repo, "init", "-q")
            self.git(repo, "config", "user.email", "test@example.com")
            self.git(repo, "config", "user.name", "Test")
            (repo / "base.txt").write_text("base\n")
            self.git(repo, "add", "base.txt")
            self.git(repo, "commit", "-qm", "base")
            self.git(repo, "branch", "dev")
            declared_base = self.git(repo, "rev-parse", "dev")
            self.git(repo, "checkout", "-qb", "unrelated")
            (repo / "unrelated.txt").write_text("unrelated\n")
            self.git(repo, "add", "unrelated.txt")
            self.git(repo, "commit", "-qm", "unrelated")
            unrelated_head = self.git(repo, "rev-parse", "HEAD")
            self.assertNotEqual(declared_base, unrelated_head)

            live = {
                "implement": {
                    "goal_spec": "sha256:" + "1" * 64,
                    "policy": "sha256:" + "2" * 64,
                    "repository": {"snapshot": {"files": {}}},
                    "upstream_outputs": [],
                },
            }
            goal = {
                "key": 7, "url": "https://example.test/goals/7", "status": "ready",
                "acceptance_criteria": ["Work is complete."], "claim": None,
                "implementation": {"branch": "goal-7", "base": "dev", "target": "dev", "pr": None},
                "phase_evidence": None,
                "workflow": {
                    "leases": {}, "receipts": {}, "workers": {}, "artifacts": {},
                    "assessments": {"implement": {
                        "goal_spec": live["implement"]["goal_spec"],
                        "policy": live["implement"]["policy"], "files": [],
                        "dimensions": {"consequence": "bounded", "boundedness": "atomic", "engineering_rigor": "structured"},
                    }},
                },
            }
            engine = workflow.Workflow.__new__(workflow.Workflow)
            engine.api, engine.repo, engine.project, engine.runtime = StepAPI(), repo, self.legacy_project(), {
                "delegation": {"available": True, "discovery_complete": True, "tool": "spawn_agent"},
            }
            # This isolated base-selection test supplies explicit artifact-only
            # scope evidence; it does not mock the scope eligibility decision.
            goal["parent"] = 1
            parent = {"key": 1, "parent": None}
            scope = {"parent": 1, "child": 7, "test_design": [], "implement": []}
            artifacts = {}
            for owner, content in [(parent, {"output_scopes": [scope]}),
                                   (goal, {"output_scope": scope})]:
                identity = workflow.digest(content)
                output = {"reference": "urn:" + identity, "hash": identity}
                artifacts[identity] = content
                envelope = StepAPI.workflow_live_inputs(repo, {}, owner, "execute", {})["plan"]
                record = {"actor": "plan-author", "input_envelope": envelope,
                          "input_hash": workflow.digest(envelope), "output": output}
                review = {"decision": "approved", "reviewer": "independent-reviewer",
                          "record_hash": workflow.digest(record), "input_hash": record["input_hash"],
                          "output_hash": identity}
                owner["phase_evidence"] = {"records": {"plan": record},
                                           "reviews": {"plan": review}, "withdrawals": []}
            engine.read = lambda number: ({}, parent if number == 1 else goal)
            engine.read_artifact = lambda _number, reference: artifacts[reference["hash"]]
            engine.context = lambda _goal: (
                {"phases": [{"id": "implement"}]},
                {"implement": {"assignment_group": "implementation", "review": {}, "not_required": "never"}},
                live, {},
            )

            step = engine.step(7)[0]
            self.assertEqual("dev", step["base_branch"])
            self.assertEqual(declared_base, step["base_commit"])
            self.assertNotEqual(unrelated_head, step["base_commit"])

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


if __name__ == "__main__":
    unittest.main()
