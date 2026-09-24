# Synthetic workflow integration matrix

This matrix records the executable, provider-isolated regression journeys for
the public workflow. The suites use synthetic repositories and in-memory GitHub
adapters; they invoke the packaged public CLI or `Workflow` transition boundary
and never require a dogfood repository, identity, or provider mutation.

Run the complete matrix from the repository root:

```bash
PYTHONPATH=.agents:plugins/zzzops python3 .agents/test_workflow_integration.py
PYTHONPATH=.agents:plugins/zzzops python3 .agents/test_workflow_public_contract.py
PYTHONPATH=.agents:plugins/zzzops python3 .agents/test_workflow_owned_outputs.py
PYTHONPATH=.agents:plugins/zzzops python3 .agents/test_workflow_heartbeat.py
PYTHONPATH=.agents:plugins/zzzops python3 .agents/test_workflow_dispatch.py
PYTHONPATH=.agents:plugins/zzzops python3 .agents/test_workflow_policy_enforcement.py
PYTHONPATH=.agents:plugins/zzzops python3 .agents/test_workflow_policy_context.py
```

| Public behavior | Synthetic end-to-end evidence |
| --- | --- |
| Execute → assess → start → bind → result → independent review → human approval | `test_persisted_execute_review_human_approval_journey` |
| Resume execute/review work, reject duplicate writers, and recover only a stopped worker | `test_actor_selection_and_duplicate_submission_are_guarded`, `test_expiry_requires_recovery_and_missing_delegation_blocks`, and `test_actual_old_dispatch_start_to_repaired_dispatch_same_lease` |
| Heartbeat active, stopped, malformed, self-referential, and unknown liveness handling | all cases in `test_workflow_heartbeat.py` |
| Immutable artifact persistence, public reads, missing references, and hash/tamper rejection | `test_artifact_round_trip_is_exact_and_missing_reference_is_rejected`, `test_artifact_content_tampering_is_rejected`, and `test_test_design_correction_retains_baseline_failure_predecessor` |
| Result/review correction chain and immutable predecessor evidence | `test_recorded_output_exposes_own_review_and_correction_without_consumer_authority` |
| Policy receipts are required but never disclosed or persisted in evidence | `test_start_and_worker_bind_require_current_policy_read_without_writes_on_rejection` and `test_public_migration_blocker_contract_persists_and_replays_receipt` |
| Cache reuse, unavailable-provider recovery, and missing archive relations | `test_open_goal_cache_reuses_only_an_exact_provider_revision_marker`, `test_unavailable_provider_is_not_cached_as_fresh_and_restores`, and `test_open_goal_hydrates_only_its_exact_closed_dependency_without_unrelated_pr_reads` |
| Blocked, dependency-only, active-worker/capacity, mixed runnable/waiting, all-done, and empty portfolios | all cases in `test_workflow_dispatch.py` and `test_checkpoint_replaces_unstartable_phase_with_capacity_step` |
| Public input rejection, batch identity, and no unintended write on failure | all cases in `test_workflow_public_contract.py` and `test_public_workflow_cli_rejects_supplied_non_objects_and_unknown_operations_before_context` |
| Terminal exhaustion with no follow-up command | `test_completed_or_empty_portfolio_reports_explicit_exhaustion` |

The matrix is intentionally split by safety boundary: public CLI contracts,
durable workflow transitions, ownership/proof enforcement, heartbeat behavior,
and dispatch selection. A green aggregate only counts after every command above
passes; mocked response shapes alone are not evidence for a journey.
