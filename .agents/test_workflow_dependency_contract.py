"""Dependency and aggregate publication identity contracts."""

import copy
import hashlib
import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


workflow = load("workflow_dependency_contract_subject", "plugins/zzzops/zzzops/workflow.py")
phase = load("phase_dependency_contract_subject", "plugins/zzzops/zzzops/phase_evidence.py")


class API:
    empty_phase_evidence = staticmethod(phase.empty_phase_evidence)
    goal_spec_digest = staticmethod(phase.goal_spec_digest)
    derive_phase_steps = staticmethod(phase.derive_phase_steps)

    @staticmethod
    def workflow_live_inputs(_repo, _project, goal, _intent, graph):
        result = {}
        for node in graph["phases"]:
            result[node["id"]] = {
                "repository": {"snapshot": {}}, "provider": {"snapshot": {}},
                "capabilities": {"snapshot": {}}, "dependencies": [], "parents": [],
            }
        return result


class WorkflowDependencyContractTests(unittest.TestCase):
    def engine(self, records):
        engine = workflow.Workflow.__new__(workflow.Workflow)
        engine.api, engine.repo, engine.project = API(), Path("."), {}
        engine.read = lambda number: ({}, copy.deepcopy(records[number]))
        engine.portfolio = lambda: [copy.deepcopy(value) for value in records.values()]
        engine.file_hashes = lambda paths: {path: "sha256:" + "0" * 64 for path in paths}
        engine.publication_identity = lambda goal: {}
        return engine

    def goal(self, number, *, parent=None, depends_on=None, output="result"):
        artifact = {
            "reference": "urn:sha256:" + hashlib.sha256(output.encode()).hexdigest(),
            "hash": phase.sha256_digest({"output": output}),
        }
        return {
            "key": number, "title": f"Goal {number}", "human_spec": f"Goal {number}",
            "status": "done", "priority": "P1", "value": "high", "difficulty": "S",
            "confidence": "high", "parent": parent, "depends_on": depends_on or [],
            "resources": [], "engineering_rigor": {}, "implementation": None,
            "acceptance_criteria": [],
            "phase_evidence": {
                "schema_version": 2,
                "records": {"implement": {
                    "status": "completed", "output": artifact, "not_required": None,
                    "actor": "worker-a", "input_hash": "sha256:" + "1" * 64,
                }},
                "reviews": {"implement": {"reviewer": "reviewer-a"}},
                "human_approvals": {}, "withdrawals": [],
            },
            "workflow": {"leases": {}, "receipts": {}, "workers": {}, "assessments": {}, "artifacts": {}},
        }

    def dependency_hash(self, engine, goal, phase_name="plan"):
        return engine.inputs(goal, {"phases": [{"id": phase_name}]})[phase_name]["dependencies"][0]["artifact"]["hash"]

    def test_dependency_identity_binds_spec_and_semantic_results_only(self):
        dependency = self.goal(2)
        consumer = self.goal(3, depends_on=[2])
        engine = self.engine({2: dependency, 3: consumer})
        original = self.dependency_hash(engine, consumer)

        dependency["phase_evidence"]["reviews"]["implement"]["reviewer"] = "reviewer-b"
        dependency["phase_evidence"]["withdrawals"].append({"operational": "history"})
        self.assertEqual(original, self.dependency_hash(engine, consumer))

        dependency["value"] = "critical"
        self.assertNotEqual(original, self.dependency_hash(engine, consumer))
        changed_spec = self.dependency_hash(engine, consumer)
        dependency["phase_evidence"]["records"]["implement"]["output"] = {
            "reference": "urn:sha256:" + "a" * 64, "hash": "sha256:" + "a" * 64,
        }
        self.assertNotEqual(changed_spec, self.dependency_hash(engine, consumer))

    def test_parent_aggregate_ignores_provenance_but_binds_results(self):
        parent = self.goal(1)
        parent["status"] = "ready"
        child = self.goal(2, parent=1)
        engine = self.engine({1: parent, 2: child})
        original = self.dependency_hash(engine, parent, "publish")

        child["phase_evidence"]["reviews"]["implement"]["reviewer"] = "reviewer-b"
        child["phase_evidence"]["records"]["implement"]["actor"] = "worker-b"
        self.assertEqual(original, self.dependency_hash(engine, parent, "publish"))

        child["phase_evidence"]["records"]["implement"]["output"] = {
            "reference": "urn:sha256:" + "b" * 64, "hash": "sha256:" + "b" * 64,
        }
        self.assertNotEqual(original, self.dependency_hash(engine, parent, "publish"))

    def test_zero_child_parent_requires_current_fully_approved_decompose_skip(self):
        envelope = phase.phase_input_envelope(
            "decompose", phase.sha256_digest({"goal": 1}), phase.sha256_digest({"policy": 1}),
            phase.sha256_digest({"dag": 1}), repository={"identity": "repo", "snapshot": {}},
            provider={"identity": "github", "snapshot": {}}, capabilities={"identity": "runtime", "snapshot": {}},
            invocation={"intent": "execute", "inputs": {"goal": 1}},
        )
        record = {
            "status": "not_required", "input_envelope": envelope, "input_hash": phase.sha256_digest(envelope),
            "output": None, "verification": None, "routing": None,
            "selection": {"model": "model", "effort": "medium"}, "actor": "worker-a",
            "not_required": {"reason": "The reviewed goal is atomic.", "policy_rule": "atomic_goal"},
            "test_design": None,
        }
        evidence = phase.record_phase_result(None, "decompose", record, envelope)
        goal = self.goal(1)
        goal.update(status="ready", phase_evidence=evidence, implementation=None)
        engine = self.engine({1: goal})
        graph = {"phases": [{"id": "decompose"}]}
        nodes = {"decompose": {"not_required": "atomic_goal", "review": {"independent": True, "human_approval": True}}}
        engine.context = lambda current: (graph, nodes, {"decompose": envelope}, {})

        self.assertEqual("dependency", engine.publication_gate(goal)["kind"])
        evidence = phase.record_phase_review(evidence, "decompose", {
            "reference": "urn:sha256:" + "c" * 64, "hash": "sha256:" + "c" * 64,
        }, "reviewer-b")
        goal["phase_evidence"] = evidence
        self.assertEqual("dependency", engine.publication_gate(goal)["kind"])
        goal["phase_evidence"] = phase.record_phase_approval(evidence, "decompose", "root", "approval-1")
        self.assertIsNone(engine.publication_gate(goal))


if __name__ == "__main__":
    unittest.main()
