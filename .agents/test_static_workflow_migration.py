"""V1 migration keeps one canonical workflow and preserves goal-specific context."""
import copy
import contextlib
import json
import unittest
from unittest import mock

import test_batch_goal_conversion as batch
import test_evidence_dag_journeys as dag


class StaticWorkflowMigrationTests(unittest.TestCase):
    def setUp(self):
        self.case = batch.BatchConversionTests(methodName="runTest")
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)

    def test_dependency_and_blocker_context_does_not_mutate_policy_graph(self):
        blocker = {
            "status": "open",
            "category": "human-action",
            "question": "Retain this exact legacy obligation",
            "evidence": {"source": "legacy", "revision": 3},
        }
        case = self.case
        case.legacy_fields(100, depends_on=[101], blockers=[copy.deepcopy(blocker)],
                           difficulty="S")

        result = case.migrate((100,))
        self.assertEqual("migrated", result["members"]["100"]["status"], result)
        payload = case.assert_preserved(100)
        graph = case.session.read(100, payload["graph"])
        expected = dag.z._static_workflow.definition(
            dag.z._workflow_section(case.session.project, "workflow_adherence")
            ["configuration"]["phase_dag"],
            dag.z._graph_compiler,
        )
        self.assertEqual(expected["graph"], graph)
        self.assertEqual(expected["hash"], dag.z._workflow.digest(graph))

        context_ref = payload["goal_context"]
        context = case.session.read(100, context_ref)
        self.assertEqual("goal_context", context["type"])
        self.assertEqual({
            "version": 1,
            "depends_on": [101],
            "blockers": [blocker],
            "metadata": {"difficulty": "S"},
        }, context["content"])
        self.assertNotIn("legacy_blockers", {node["id"] for node in graph["nodes"]})
        rendered = dag.z._workflow.comment_store.canonical(graph)
        self.assertNotIn("legacy_dependency_101", rendered)
        self.assertNotIn("Retain this exact legacy obligation", rendered)

    def test_pre_static_receipts_recover_context_from_bound_source(self):
        case = self.case
        blocker = {"status": "open", "category": "human-action",
                   "question": "Preserve historical release window"}
        case.legacy_fields(100, depends_on=[101], blockers=[blocker],
                           difficulty="S",
                           engineering_rigor={"risk_categories": ["authorization"]})
        issue = copy.deepcopy(case.provider.issues[100])
        historical_policy = copy.deepcopy(case.session.project["policy"])
        policy_hash = dag.z._workflow.digest(historical_policy)
        policy = {"hash": policy_hash,
                  "uri": "zzzops:owner/repo:goal:100:" + policy_hash}
        for converter in ("lossless-v1-v2/1",
                          dag.z._migration_batch.LEGACY_COMPILED_CONVERTER,
                          dag.z._migration_batch.CONVERTER):
            with self.subTest(converter=converter):
                receipt = {"converter": converter, "goal": 100, "policy": policy}
                source = {"type": "migration_source", "content": issue,
                          "producer": None,
                          "provenance": {"actor": converter, "source": None,
                                         "policy": policy["hash"]}}
                context = dag.z._migration_batch.historical_goal_context(
                    case.session, receipt, source, historical_policy)
                self.assertEqual([101], context["depends_on"])
                self.assertEqual([blocker], context["blockers"])
                self.assertEqual("S", context["metadata"]["difficulty"])
                self.assertEqual("agentic",
                                 context["metadata"]["engineering_rigor"]["effective"])

        source["provenance"]["policy"] = "sha256:" + "b" * 64
        with self.assertRaisesRegex(ValueError, "provenance mismatch"):
            dag.z._migration_batch.historical_goal_context(
                case.session, receipt, source, historical_policy)

    def test_committed_v2_checkpoint_recovers_context_without_graph_repair(self):
        case = self.case
        blocker = {"status": "open", "category": "human-action",
                   "question": "Supply the historical deployment window"}
        routing = dag.z._workflow_section(
            case.session.project, "model_routing")["configuration"]
        routing["assessment_tree"].insert(
            0, {"when": {"engineering_rigor": ["agentic"]},
                "tier": "architectural"})
        case.legacy_fields(100, depends_on=[101], blockers=[blocker],
                           difficulty="S",
                           engineering_rigor={"risk_categories": ["authorization"]})
        with mock.patch.object(dag.z, "GitHubGoalTransitionAdapter",
                               return_value=case.provider):
            engine = dag.z.workflow_engine(case.fixture.repo, case.session.project,
                                           case.session.runtime)
        engine.adapter = case.provider
        with mock.patch.object(engine, "locked", return_value=contextlib.nullcontext()), \
                mock.patch.object(engine.api, "reviewed_project_state",
                                  return_value=copy.deepcopy(case.session.project)), \
                engine.locked():
            engine.invalidate()
            issue, legacy, kind = dag.z._migration_batch.state(engine, 100)
            self.assertEqual("legacy", kind)
            graph = copy.deepcopy(
                dag.z._migration_batch.configuration(engine)["phase_dag"])
            graph["nodes"][0]["prompt"] += " Historical compiled-v2 marker."
            compiled = dag.z._graph_compiler.compile_graph(graph, local_goal=100)
            self.assertFalse(compiled["diagnostics"], compiled)
            historical_graph = compiled["graph"]
            artifacts = {}

            def save(value):
                identity = dag.z._workflow.digest(value)
                artifacts[identity] = copy.deepcopy(value)
                return engine.node_ref(identity, 100)

            converter = dag.z._migration_batch.LEGACY_COMPILED_CONVERTER
            policy_ref = save(engine.project["policy"])
            source_ref = save({"type": "migration_source", "content": issue,
                               "producer": None,
                               "provenance": {"actor": converter, "source": None,
                                              "policy": policy_ref["hash"]}})
            prefix, suffix = dag.z._migration_batch.human_parts(engine, issue["body"])
            spec_ref = save({"type": "goal_specification", "content": prefix + suffix,
                             "producer": None,
                             "provenance": {"actor": converter, "source": source_ref,
                                            "policy": policy_ref["hash"]}})
            payload = {"spec": spec_ref, "graph": save(historical_graph),
                       "evidence": [], "operational": {"leases": [], "receipts": []}}
            target = {"schema_version": 2, "repository": engine.repository,
                      "issue": 100, "revision": legacy["revision"] + 1,
                      "state": "open", "parent": legacy["parent"],
                      "payload": save(payload)}
            receipt_value = {
                "type": "schema_migration", "repository": engine.repository,
                "goal": 100, "converter": converter,
                "compiler_version": dag.z._graph_compiler.SUPPORTED_VERSION,
                "source": source_ref, "target_intent": save(target),
                "target_payload": target["payload"], "policy": policy_ref,
            }
            receipt_ref = save(receipt_value)
            request = dag.z._migration_batch.request_for_receipt(
                receipt_value, dag.z._workflow.digest)
            response = {"next_steps": [{"kind": "schema_migration", "goal": 100,
                                         "status": "migrated",
                                         "receipt": receipt_ref}]}
            snapshot = {"number": 100, "issue": issue,
                        "envelope": {**target, "revision": legacy["revision"]},
                        "artifacts": artifacts,
                        "migration": {"receipt": receipt_ref,
                                      "policy": policy_ref["hash"]}}
            engine.node_persist(snapshot, copy.deepcopy(payload), response, request)

        envelope = dag.z.parse_managed_goal(case.provider.issues[100]["body"], 100)
        committed = case.session.read(100, envelope["payload"])
        graph_ref = copy.deepcopy(committed["graph"])
        steps = case.session.checkpoint(100)
        rendered = str(steps)
        self.assertIn("historical deployment window", rendered)
        observed = engine.node_snapshot(100)
        self.assertEqual([101], observed["goal_context"]["depends_on"])
        self.assertEqual([blocker], observed["goal_context"]["blockers"])
        self.assertEqual("agentic",
                         observed["goal_context"]["metadata"]
                         ["engineering_rigor"]["effective"])
        implement = next(node for node in observed["graph"]["nodes"]
                         if node["id"] == "implement")
        self.assertEqual(
            "architectural",
            dag.z._migration_batch.capability_floor(
                dag.z, case.session.project,
                observed["goal_context"]["metadata"], implement))
        self.assertFalse(any(step.get("kind") in {
            "graph_prepare", "repair_graph", "graph_reconciliation"
        } for step in steps), steps)
        after = case.session.read(100, envelope["payload"])
        self.assertEqual(graph_ref, after["graph"])
        self.assertEqual(historical_graph, case.session.read(100, after["graph"]))

        original_comments = copy.deepcopy(case.provider.comments[100])
        for row in case.provider.comments[100]:
            record = dag.z._comment_store.decode_envelope(row["body"])
            if record and (record.get("context") or {}).get("migration"):
                record["context"].pop("migration")
                row["body"] = dag.z._comment_store.encode_envelope(record)
        rejected = case.session.call(100)
        self.assertRegex(str(rejected), r"(?i)migration lineage|missing history|constraints")
        case.provider.comments[100] = original_comments

    def test_forged_static_goal_context_provenance_is_rejected(self):
        for field, value in (("source", {"hash": "sha256:" + "b" * 64,
                                          "uri": "urn:sha256:" + "b" * 64}),
                             ("policy", "sha256:" + "c" * 64)):
            with self.subTest(field=field):
                case = batch.BatchConversionTests(methodName="runTest")
                case.setUp()
                self.addCleanup(case.doCleanups)
                self.assertTrue(case.migrate((100,))["complete"])
                envelope = dag.z.parse_managed_goal(
                    case.provider.issues[100]["body"], 100)
                payload = copy.deepcopy(case.session.read(100, envelope["payload"]))
                context = copy.deepcopy(case.session.read(100, payload["goal_context"]))
                context["provenance"][field] = value
                payload["goal_context"] = case.blob(context)
                case.replace_legacy_payload(envelope, payload)
                rejected = case.session.call(100)
                self.assertRegex(str(rejected), r"(?i)goal context|migration|lineage")

    def test_committed_static_receipt_loads_canonical_phase_frontier(self):
        case = self.case
        result = case.migrate((100,))
        member = result["members"]["100"]
        self.assertEqual("migrated", member["status"], result)
        receipt = case.session.read(100, member["receipt"])
        self.assertEqual(dag.z._migration_batch.CONVERTER, receipt["converter"])
        self.assertEqual(dag.z._static_workflow.VERSION,
                         receipt["static_workflow_version"])
        payload = case.assert_preserved(100)
        graph = case.session.read(100, payload["graph"])
        self.assertEqual(dag.z._static_workflow.digest(graph),
                         receipt["static_workflow_hash"])

        steps = case.session.call(100)["next_steps"]
        self.assertTrue(any(step.get("kind") == "execute"
                            and step.get("node", {}).get("node") == "understand"
                            for step in steps), steps)
        self.assertFalse(any(step.get("kind") in {
            "graph_prepare", "repair_graph", "graph_reconciliation",
        } for step in steps), steps)

    def test_archived_static_goal_context_authenticates_read_only_snapshot(self):
        case = self.case
        case.legacy_fields(100, depends_on=[101], difficulty="S")
        self.assertTrue(case.migrate((100,))["complete"])
        envelope = dag.z.parse_managed_goal(case.provider.issues[100]["body"], 100)
        graph_ref = copy.deepcopy(case.session.read(100, envelope["payload"])["graph"])
        envelope["state"] = "archived"
        envelope["revision"] += 1
        prefix = case.provider.issues[100]["body"].split("<!-- zzzops-goal", 1)[0]
        case.provider.issues[100]["body"] = (
            prefix + "<!-- zzzops-goal\n" + json.dumps(envelope)
            + "\nzzzops-goal -->\n")
        case.provider.issues[100]["state"] = "closed"
        before = copy.deepcopy((case.provider.issues, case.provider.comments))
        with mock.patch.object(dag.z, "GitHubGoalTransitionAdapter",
                               return_value=case.provider):
            engine = dag.z.workflow_engine(case.fixture.repo, case.session.project,
                                           case.session.runtime)
        engine.adapter = case.provider
        snapshot = engine.node_snapshot(100)
        self.assertEqual([101], snapshot["goal_context"]["depends_on"])
        self.assertEqual("S", snapshot["goal_context"]["metadata"]["difficulty"])
        self.assertEqual(graph_ref, snapshot["payload"]["graph"])
        self.assertEqual(before, (case.provider.issues, case.provider.comments))

    def test_migrated_rigor_raises_route_floor_without_mutating_graph(self):
        case = self.case
        case.legacy_fields(
            100, difficulty="S",
            engineering_rigor={"risk_categories": ["authorization"]},
        )
        routing = dag.z._workflow_section(
            case.session.project, "model_routing")["configuration"]
        routing["assessment_tree"].insert(
            0, {"when": {"engineering_rigor": ["agentic"]},
                "tier": "architectural"})
        case.policy = copy.deepcopy(case.session.project)

        result = case.migrate((100,))
        self.assertEqual("migrated", result["members"]["100"]["status"], result)
        payload = case.assert_preserved(100)
        graph = case.session.read(100, payload["graph"])
        context = case.session.read(100, payload["goal_context"])["content"]
        implement = next(node for node in graph["nodes"] if node["id"] == "implement")
        self.assertNotEqual("architectural", implement["executor"]["capability"])
        self.assertEqual(
            "architectural",
            dag.z._migration_batch.capability_floor(
                dag.z, case.session.project, context["metadata"], implement),
        )
        self.assertEqual("S", context["metadata"]["difficulty"])


if __name__ == "__main__":
    unittest.main()
