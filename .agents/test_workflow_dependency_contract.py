"""Generic dependency freshness and empty-selection approval contracts.

Retained regression IDs now exercise public generic evidence. Domain phase
records are no longer a normal dependency evaluator in this suite.
"""

import unittest


class WorkflowDependencyContractTests(unittest.TestCase):
    def test_dependency_identity_binds_spec_and_semantic_results_only(self):
        # Generic evidence preserves freshness and explicit empty-set review gates.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_evidence_dag_journeys.EvidenceDagPublicTests.test_semantic_input_drift_rejects_inflight_result_and_bookkeeping_does_not',
            'test_evidence_dag_journeys.RelationshipPublicTests.test_consumed_child_evidence_drift_rejects_acquired_worker',
        )

    def test_parent_aggregate_ignores_provenance_but_binds_results(self):
        # Generic evidence preserves freshness and explicit empty-set review gates.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_evidence_dag_journeys.RelationshipPublicTests.test_unrelated_and_bookkeeping_changes_preserve_relevant_consumer',
            'test_evidence_dag_journeys.RelationshipPublicTests.test_consumed_child_evidence_drift_rejects_acquired_worker',
        )

    def test_zero_child_parent_requires_current_fully_approved_decompose_skip(self):
        # Generic evidence preserves freshness and explicit empty-set review gates.
        from test_evidence_dag_journeys import run_generic_regressions
        run_generic_regressions(self,
            'test_evidence_dag_journeys.RelationshipPublicTests.test_known_empty_is_aggregate_not_unknown_and_does_not_manufacture_artifact',
            'test_phase_review_contract.GenericReviewGateTests.test_empty_selection_still_requires_configured_independent_review_and_root_consent',
        )


if __name__ == "__main__":
    unittest.main()
