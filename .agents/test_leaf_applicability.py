"""Configured generic graphs preserve leaf, composition and migration authority."""
import copy
import json
import unittest

from test_zzzops import PLUGIN_ROOT, zzzops
import test_evidence_dag_journeys as dag_fixtures


class LeafApplicabilityTests(unittest.TestCase):
    def setUp(self):
        plan = json.loads((PLUGIN_ROOT / 'zzzops/templates/project-goals/INIT_PLAN.json').read_text())
        self.project = {'policy': plan['policy']}
        self.dag = next(s for s in plan['policy']['sections']
                        if s['id'] == 'workflow_adherence')['configuration']['phase_dag']

    def test_default_selects_leaf_owned_work(self):
        self.assertEqual([], zzzops._policy._workflow_phase_dag_errors(self.dag))
        nodes = {node["id"]: node for node in self.dag["nodes"]}
        for name in ("test_design", "implement"):
            node = nodes[name]
            self.assertIn("repository_workspace", node["executor"]["resources"])
            self.assertIn("allocation", node["inputs"])
            self.assertIn("authorization", node["inputs"])
            self.assertNotIn("applicability", node, "Structure alone grants no workspace authority")
        dag_fixtures.run_generic_regressions(self,
            "test_evidence_dag_journeys.WorkspaceAuthorityPublicTests.test_parent_grant_omission_and_mismatch_cannot_expand_child_authority")

    def test_review_types_and_consequence_overrides_are_policy_owned(self):
        # Review strength is configured graph evidence, not a hidden risk switch.
        frozen = copy.deepcopy(self.dag)
        dag_fixtures.run_generic_regressions(self,
            "test_evidence_dag_journeys.EvidenceDagPublicTests.test_stronger_policy_requires_added_independent_review_and_preserves_history",
            "test_evidence_dag_journeys.EvidenceDagPublicTests.test_lighter_policy_proposal_preserves_findings_and_requires_exact_approval")
        self.assertEqual(frozen, self.dag)
        invalid = copy.deepcopy(self.dag)
        invalid["nodes"][0]["review"] = {"by_consequence": {"unknown": {"human_approval": True}}}
        self.assertTrue(zzzops._policy._workflow_phase_dag_errors(invalid))

    def test_old_reviewed_dag_is_accepted_and_reported_stale(self):
        from pathlib import Path
        old = json.loads((Path(__file__).parent / 'fixtures/legacy_phase_dag.json').read_text())
        self.assertTrue(zzzops._policy._workflow_phase_dag_errors(old),
                        'Released predecessor needs explicit migration; never execute it as the active Graph')
        self.assertNotEqual(zzzops._phase_evidence.sha256_digest(old), zzzops._phase_evidence.sha256_digest(self.dag))
        self.assertNotIn('plan', {n['id'] for n in self.dag['nodes']})
        section = next(s for s in self.project['policy']['sections'] if s['id'] == 'workflow_adherence')
        current = zzzops._policy.policy_default_catalog()['zzzops.policy.workflow_adherence']
        content = copy.deepcopy(current['content'])
        content['configuration']['phase_dag'] = old
        section.pop('default_id', None)
        section.update(content)
        section['default_provenance'] = {
            'status': 'adopted', 'default_id': current['id'], 'schema_version': zzzops._policy.POLICY_DEFAULT_SCHEMA_VERSION,
            'source': {'version': '0.0.0-dev', 'revision': 'a' * 40},
            'digest': zzzops._policy.policy_content_digest(content), 'snapshot': content,
        }
        comparison = next(row for row in zzzops._policy.compare_policy_defaults(self.project['policy']) if row['section_id'] == 'workflow_adherence')
        self.assertEqual('update_available', comparison['status'])

    def test_leaf_and_composition_graphs_at_every_depth(self):
        # One symbolic Graph retains its exact bytes at root and nested depth.
        # A required child must finish; an empty known collection is explicit.
        for parent in (None, 99):
            for children in ([], [101]):
                with self.subTest(parent=parent, children=children):
                    case = dag_fixtures.RelationshipPublicTests()
                    case.setUp()
                    try:
                        graph = case.symbolic_graph()
                        case.install(graph)
                        if parent:
                            case.add_goal(parent, graph)
                            envelope = case.envelope_for(100)
                            envelope["parent"] = parent
                            case.put_envelope(100, envelope)
                        for number in children:
                            case.add_goal(number, graph, parent=100)
                        self.assertEqual(not children, "collect" in case.names())
                        for number in children:
                            case.complete(number)
                        self.assertIn("collect", case.names())
                        work = case.session.acquire("collect")
                        selected = [row for row in case.resolutions(work) if row["selector"]["goal"] == "#children"]
                        self.assertTrue(selected)
                        self.assertTrue(all({t["goal"] for t in row["targets"]} == set(children) for row in selected))
                        case.session.finish(work, {"value": "Exact required children consumed"})
                        payload = case.read_at(100, case.envelope_for(100)["payload"])
                        self.assertEqual(graph, case.read_at(100, payload["graph"]))
                    finally:
                        case.doCleanups()
        dag_fixtures.run_generic_regressions(self,
            "test_evidence_dag_journeys.RelationshipPublicTests.test_new_missing_child_stales_worker_and_does_not_omit_required_work",
            "test_evidence_dag_journeys.RelationshipPublicTests.test_every_child_required_including_archived_exact_completion")

    def test_existing_child_only_policy_keeps_its_reviewed_meaning(self):
        # Historical policy stays evidence until trusted conversion; current
        # child work still needs exact current parent authority after conversion.
        dag_fixtures.run_generic_regressions(self,
            "test_goal_schema_conversion.MigrationEntryPublicTests.test_reviewed_nonempty_historical_mapping_preserves_source_and_missing_reviews",
            "test_evidence_dag_journeys.RelationshipPublicTests.test_child_requires_current_parent_review_and_blocks_again_after_parent_drift")


if __name__ == '__main__':
    unittest.main()
