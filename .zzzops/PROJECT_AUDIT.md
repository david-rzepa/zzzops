# ZzzOps project policy audit

Status: complete. Reviewer: user. Revision: 19.

## Evidence and decisions

- [x] `[policy:backend]` **Canonical goal backend** (applicable)
  - Decision: github_issues
  - Rationale: GitHub capability is usable and completed issue #81 made it the only supported authority.
  - Sources: E-003: init inspect 2026-07-18 — GitHub Issues are enabled for david-rzepa/zzzops and the authenticated user has ADMIN permission.; E-004: user decisions and completed issues #77/#81 — Health reminders were removed and GitHub Issues is now the only supported canonical goal backend.
  - Confidence/default: high; user decision and current product scope → accepted
  - Provenance: default origin unknown
  - Settings: `{"authority": "github_issues", "capability_evidence": "init inspect 2026-07-18", "fallback": "forbidden", "repository_identity": "david-rzepa/zzzops", "tradeoffs": {"github_issues": "shared native issue queue requiring GitHub access"}}`
  - Exceptions: none
  - Unresolved: none
- [x] `[policy:git_review_release]` **Git, review, and release** (applicable)
  - Decision: Use one chained branch and PR per goal: start from dev, then stack each subsequent goal from the preceding exact reviewed checkpoint and merge in dependency order. Use Conventional Commits, human review after checks, and owner-only main releases.
  - Rationale: The user explicitly selected chained PRs while retaining per-goal review units and ordered integration.
  - Sources: E-002: AGENTS.md — Repository guidance requires dev-based per-goal implementation and PRs, Conventional Commits, human review, owner-only main releases, prompt-budget checks, observable work, and reviewed PROJECT policy as the operational source of truth.; E-005: user decisions and goals #59/#88/#94/#95 — User decisions require review-ready dependency stacking, a brief bounded human-unblock watch, and artifact-specific verification without recursive documentation or test meta-tests.; E-007: user decisions and goal #117 on 2026-07-20 — User selected bounded refill for documentation, test coverage, and non-behavioral code quality, completed dependencies before writable implementation, read-only advance investigation, and up to three size-aware workers with clean worktree removal or reuse.; E-008: user decisions 2026-08-01 — Use chained per-goal PRs from exact reviewed checkpoints; interview only during capture at standard adaptive depth with the requesting user as sole stakeholder; execute unattended with durable blockers; capture test-discovered out-of-scope bugs as blocked goals; enable privacy-safe execution reports.
  - Confidence/default: high; repository policy → changed
  - Provenance: default origin unknown
  - Settings: `{"branch_base": "dev", "child_target": "nearest_parent_branch", "commit_style": "conventional", "commit_unit": "verified_subgoal", "conversational_approval": "allowed_otherwise", "dependency_base": "dependency_branch", "execution_branch": "per_goal", "merge_after_approval": "when_authorized", "multiple_dependency_base": "reviewed_base_containing_all", "parent_pseudo_trunk": true, "pr_approval": "required_when_repository_requires_pr", "pull_request_target": "preceding_goal_branch_then_dev", "pull_request_unit": "per_goal", "read_only_dependency_investigation": "allowed_before_completion", "release_actor": "david-rzepa", "release_branch": "main", "release_update": "explicit_owner_force_push", "release_workflow": "main_update_runs_release_ci", "review_gate": "human_after_checks", "review_pending_dependency": "stack_from_reviewed_checkpoint", "review_state_reads_per_checkpoint": 1, "shared_pull_request": "explicit_reviewed_override"}`
  - Exceptions: none
  - Unresolved: none
- [x] `[policy:execution_continuation]` **Execution and work continuation** (applicable)
  - Decision: Continue across actionable goals under reviewed dependency and resource policy, incorporate newly captured goals at the next safe checkpoint, and persist unanswered questions without live interviewing, notification, polling, or waiting.
  - Rationale: Execution is unattended; durable blockers preserve every consequential request without requiring a live user.
  - Sources: E-001: .zzzops/PROJECT.md — The existing confirmed charter defines the outcome, KPIs, acceptance criteria, and value constraints.; E-005: user decisions and goals #59/#88/#94/#95 — User decisions require review-ready dependency stacking, a brief bounded human-unblock watch, and artifact-specific verification without recursive documentation or test meta-tests.; E-008: user decisions 2026-08-01 — Use chained per-goal PRs from exact reviewed checkpoints; interview only during capture at standard adaptive depth with the requesting user as sole stakeholder; execute unattended with durable blockers; capture test-discovered out-of-scope bugs as blocked goals; enable privacy-safe execution reports.
  - Confidence/default: high; ZzzOps default → changed
  - Provenance: default origin unknown
  - Settings: `{"after_additive_capture": "resume_once_and_reprioritize", "continue_while_actionable": true, "cross_task": "require_explicit_harness_signal", "execute_intent": "same_task_until_superseded", "exhausted_handoff_retains_intent": true, "max_easy_wins": 2, "new_goal_checkpoint": "next_safe_checkpoint", "stop_reasons_clear_intent": ["user_stop", "pause", "replacement_request", "capture_only", "required_authority", "blocking_boundary"], "triage_new_first": true}`
  - Exceptions: none
  - Unresolved: none
- [x] `[policy:verification_testing]` **Verification and testing** (applicable)
  - Decision: Require artifact-appropriate observable evidence in small chunks; documentation and test cases need no recursive tests, while product behavior and reusable test infrastructure require direct verification.
  - Rationale: Root instructions forbid unobservable implementation and unsanctioned test-bug fixes.
  - Sources: E-002: AGENTS.md — Repository guidance requires dev-based per-goal implementation and PRs, Conventional Commits, human review, owner-only main releases, prompt-budget checks, observable work, and reviewed PROJECT policy as the operational source of truth.; E-005: user decisions and goals #59/#88/#94/#95 — User decisions require review-ready dependency stacking, a brief bounded human-unblock watch, and artifact-specific verification without recursive documentation or test meta-tests.; E-008: user decisions 2026-08-01 — Use chained per-goal PRs from exact reviewed checkpoints; interview only during capture at standard adaptive depth with the requesting user as sole stakeholder; execute unattended with durable blockers; capture test-discovered out-of-scope bugs as blocked goals; enable privacy-safe execution reports.
  - Confidence/default: high; repository policy → changed
  - Provenance: default origin unknown
  - Settings: `{"artifact_verification": {"documentation": "inspect_artifact_no_feature_test", "product_runtime": "risk_proportionate_behavioral_probe", "test_cases": "run_changed_tests_no_recursive_meta_test", "test_harness": "focused_behavioral_regression"}, "mode": "chunk_probe", "test_bug": "capture_as_blocker", "widen": "as_relevant"}`
  - Exceptions: none
  - Unresolved: none
- [x] `[policy:code_quality]` **Code-quality and refactoring boundaries** (applicable)
  - Decision: Preserve behavior unless a goal explicitly authorizes a behavior change.
  - Rationale: A bounded self-review prevents unrelated cleanup from expanding work.
  - Sources: E-002: AGENTS.md — Repository guidance requires dev-based per-goal implementation and PRs, Conventional Commits, human review, owner-only main releases, prompt-budget checks, observable work, and reviewed PROJECT policy as the operational source of truth.
  - Confidence/default: medium; ZzzOps default → accepted
  - Provenance: default origin unknown
  - Settings: `{"completion_self_review": "required_before_review_or_done", "dead_code": "remove_only_if_evidenced_and_in_scope", "dynamic_generated_vendor": "retain_without_proof", "non_behavioral_only_without_feature_goal": true, "record_clean_review": true, "reverify_after_changes": true, "review_scope": "goal_diff_tests_and_relevant_surroundings"}`
  - Exceptions: none
  - Unresolved: none
- [x] `[policy:dependencies_tooling]` **Dependencies, tooling, and generated artifacts** (applicable)
  - Decision: Use project-native tooling; do not hand-edit generated or dependency-owned files.
  - Rationale: Keeps deterministic mechanics portable and ownership clear.
  - Sources: E-001: .zzzops/PROJECT.md — The existing confirmed charter defines the outcome, KPIs, acceptance criteria, and value constraints.
  - Confidence/default: medium; ZzzOps default → accepted
  - Provenance: default origin unknown
  - Settings: `{"dependency_changes": "explicit_scope", "generated_files": "source_or_generator_only", "tooling": "project_native"}`
  - Exceptions: none
  - Unresolved: none
- [x] `[policy:security_privacy_compliance]` **Security, privacy, secrets, and compliance** (applicable)
  - Decision: Repository policy may tighten but never weaken safety and authority boundaries.
  - Rationale: The charter expressly forbids secret exposure and invented authority.
  - Sources: E-001: .zzzops/PROJECT.md — The existing confirmed charter defines the outcome, KPIs, acceptance criteria, and value constraints.
  - Confidence/default: high; ZzzOps safety boundary → accepted
  - Provenance: default origin unknown
  - Settings: `{"production_mutation": "explicit_authority", "project_constraints": [], "secrets": "never_expose"}`
  - Exceptions: none
  - Unresolved: none
- [x] `[policy:documentation_style]` **Documentation and style** (applicable)
  - Decision: Follow evidenced repository documentation and style conventions; use outcome-first, low-technical-detail user updates by default while allowing explicit project policy to override the style.
  - Rationale: Repository instructions require prompt-budget updates, and the user selected concise actionable communication as this project's default without making it universal policy.
  - Sources: E-002: AGENTS.md — Repository guidance requires dev-based per-goal implementation and PRs, Conventional Commits, human review, owner-only main releases, prompt-budget checks, observable work, and reviewed PROJECT policy as the operational source of truth.; E-006: user decision and goal #102 — Communication style is reviewed project policy; outcome-first, low-technical-detail updates are the user's preferred ZzzOps default and may be overridden by explicit project policy.
  - Confidence/default: high; repository policy and user-preferred ZzzOps default → accepted
  - Provenance: default origin unknown
  - Settings: `{"communication": {"style": "outcome_first", "technical_detail": "decision_risk_failure_or_request", "user_action": "one_clear_action_with_reason_and_next_step"}, "documentation": "repository_conventions", "installed_prompt_markdown_check": ".agents/prompt_stats.py --check", "prompt_budget_ceiling": "explicit_value_justification", "prompt_counts": "do_not_commit", "style": "repository_conventions"}`
  - Exceptions: none
  - Unresolved: none
- [x] `[policy:deployment_resources]` **Deployment, environment, and resources** (applicable)
  - Decision: Do not deploy without authority; choose bounded parallelism from the deterministic tracked-file repository size.
  - Rationale: Repository release policy restricts main updates, while the tracked tree is below 100 MB and the user selected size-aware parallel defaults.
  - Sources: E-002: AGENTS.md — Repository guidance requires dev-based per-goal implementation and PRs, Conventional Commits, human review, owner-only main releases, prompt-budget checks, observable work, and reviewed PROJECT policy as the operational source of truth.; E-007: user decisions and goal #117 on 2026-07-20 — User selected bounded refill for documentation, test coverage, and non-behavioral code quality, completed dependencies before writable implementation, read-only advance investigation, and up to three size-aware workers with clean worktree removal or reuse.
  - Confidence/default: high; repository policy → accepted
  - Provenance: default origin unknown
  - Settings: `{"delegate_wait_after_seconds": 60, "deployment": "explicit_authority", "resource_mode": "size_aware"}`
  - Exceptions: none
  - Unresolved: none
- [x] `[policy:autonomy_approval_parallelism]` **Autonomy, approvals, and parallelism** (applicable)
  - Decision: Interview adaptively during goal capture at the reviewed depth; treat the requesting user as the sole stakeholder; execute unattended by persisting consequential questions as durable blockers; repair in-scope CI failures without another approval; record privacy-safe execution reports; refill valuable bounded work; and use up to three size-aware workers.
  - Rationale: This separates present-user requirements discovery from unattended execution while preserving durable control, chained progress, and privacy-safe machinery feedback.
  - Sources: E-001: .zzzops/PROJECT.md — The existing confirmed charter defines the outcome, KPIs, acceptance criteria, and value constraints.; E-002: AGENTS.md — Repository guidance requires dev-based per-goal implementation and PRs, Conventional Commits, human review, owner-only main releases, prompt-budget checks, observable work, and reviewed PROJECT policy as the operational source of truth.; E-004: user decisions and completed issues #77/#81 — Health reminders were removed and GitHub Issues is now the only supported canonical goal backend.; E-007: user decisions and goal #117 on 2026-07-20 — User selected bounded refill for documentation, test coverage, and non-behavioral code quality, completed dependencies before writable implementation, read-only advance investigation, and up to three size-aware workers with clean worktree removal or reuse.; E-008: user decisions 2026-08-01 — Use chained per-goal PRs from exact reviewed checkpoints; interview only during capture at standard adaptive depth with the requesting user as sole stakeholder; execute unattended with durable blockers; capture test-discovered out-of-scope bugs as blocked goals; enable privacy-safe execution reports.; E-009: user decision 2026-08-02 — Authorization to execute a goal includes diagnosing and repairing CI failures caused by that goal's own changes; do not ask for separate fix approval unless the repair expands scope or needs new authority.
  - Confidence/default: high; user-selected ZzzOps defaults and project policy → changed
  - Provenance: default origin unknown
  - Settings: `{"blocker_interview": "capture_only", "blocker_order": ["safety_access_human", "cross_goal_decisions", "specification", "technical_unknown"], "capture_defaults": {"confidence": "low", "difficulty": "unknown", "priority": "P2"}, "claim_ttl_hours": 4, "dependency_implementation_gate": "stack_from_reviewed_checkpoint", "execution_reports": {"enabled": true}, "in_scope_ci_failure_repair": "authorized_without_additional_approval", "max_workers": 3, "parallelization": {"at_or_above_threshold_mode": "read_only", "below_threshold_mode": "worktrees", "measurement": "existing_git_tracked_worktree_bytes", "threshold_bytes": 104857600}, "planning": {"decompose_at": "L", "max_depth": 3}, "project_parallel_ceiling": "size_aware", "read_only_dependency_investigation": true, "refill": {"allowed_categories": ["documentation", "tests", "code_quality_non_behavioral"], "enabled": true, "max_per_run": 3}, "requirements_interview": {"capture_depth": "standard", "execution_questions": "durable_blockers_only", "mode": "adaptive", "stakeholder_model": "requesting_user_only"}, "worktree_lifecycle": {"abandoned_or_dirty": "forbidden", "after_task": "remove_or_retain_clean_for_reuse", "reuse_requires": ["clean_state", "reviewed_base", "new_goal_resources", "safe_branch_reassignment"]}}`
  - Exceptions: none
  - Unresolved: none
- [x] `[policy:automated_design]` **Automated design authority** (applicable)
  - Decision: disabled
  - Rationale: Require explicit user direction for design choices; unattended execution persists them as durable blockers.
  - Sources: E-002: AGENTS.md — Repository guidance requires dev-based per-goal implementation and PRs, Conventional Commits, human review, owner-only main releases, prompt-budget checks, observable work, and reviewed PROJECT policy as the operational source of truth.; E-011: user decision 2026-08-09 — Disable automated design authority; require explicit user direction for design choices.
  - Confidence/default: medium; user decision → changed
  - Provenance: customized from a ZzzOps default
  - Settings: `{"decision_record": ["alternatives", "rationale", "assumptions", "falsifiable_validation_signal"], "hard_stops": ["product_scope", "incompatible_public_contract", "destructive_migration", "external_spending", "deployment", "external_write", "human_review", "safety_authority", "higher_authority"], "insufficient_evidence": "durable_design_blocker", "privacy_security": "unambiguously_risk_reducing_without_material_behavior_change", "scope": "reversible_in_scope_implementation", "selection_basis": ["project_objectives", "kpi_evidence", "constraints", "precedence"]}`
  - Exceptions: none
  - Unresolved: none

## Review record

| Date | Actor/run | Change | Reason/evidence |
| --- | --- | --- | --- |
| 2026-08-02 | ZzzOps initialization | Created pending revision 15 | Confirmed agent-generated draft; explicit policy review still required. |
| 2026-08-02 | user | Reviewed policy revision 16 | Approved: backend, git_review_release, execution_continuation, verification_testing, code_quality, dependencies_tooling, security_privacy_compliance, documentation_style, deployment_resources, autonomy_approval_parallelism; source digest sha256:049640647764a6cc2c9834da01fb74a767c6a2efb5652ac34a76954f4b8b134c. |
| 2026-08-09 | ZzzOps initialization | Created pending revision 17 | Confirmed agent-generated draft; explicit policy review still required. |
| 2026-08-09 | ZzzOps initialization | Created pending revision 18 | Confirmed agent-generated draft; explicit policy review still required. |
| 2026-08-09 | user | Reviewed policy revision 19 | Approved: automated_design; source digest sha256:334572a80f28915d6759f1cd4c896cc6c7ea5b1f3c37a6d2c7e910d424aed4b8. |

The machine-readable authority is [POLICY.json](POLICY.json); this file is its human audit view.
