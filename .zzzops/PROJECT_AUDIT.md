# ZzzOps project policy audit

Status: complete. Reviewer: david-rzepa. Revision: 12.

## Evidence and decisions

- [x] `[policy:backend]` **Canonical goal backend** (applicable)
  - Decision: github_issues
  - Rationale: GitHub capability is usable and completed issue #81 made it the only supported authority.
  - Sources: E-003: init inspect 2026-07-18 — GitHub Issues are enabled for david-rzepa/zzzops and the authenticated user has ADMIN permission.; E-004: user decisions and completed issues #77/#81 — Health reminders were removed and GitHub Issues is now the only supported canonical goal backend.
  - Confidence/default: high; user decision and current product scope → accepted
  - Settings: `{"authority": "github_issues", "capability_evidence": "init inspect 2026-07-18", "fallback": "forbidden", "repository_identity": "david-rzepa/zzzops", "tradeoffs": {"github_issues": "shared native issue queue requiring GitHub access"}}`
  - Exceptions: none
  - Unresolved: none
- [x] `[policy:git_review_release]` **Git, review, and release** (applicable)
  - Decision: Per-goal branches from dev and PRs to dev. Writable implementation waits until every dependency is complete; read-only investigation may prepare later work without claiming or starting it. Use Conventional Commits, human review after checks, and owner-only main releases.
  - Rationale: Root repository instructions define the integration and release boundary.
  - Sources: E-002: AGENTS.md — Repository guidance requires dev-based per-goal implementation and PRs, Conventional Commits, human review, owner-only main releases, prompt-budget checks, observable work, and reviewed PROJECT policy as the operational source of truth.; E-005: user decisions and goals #59/#88/#94/#95 — User decisions require review-ready dependency stacking, a brief bounded human-unblock watch, and artifact-specific verification without recursive documentation or test meta-tests.; E-007: user decisions and goal #117 on 2026-07-20 — User selected bounded refill for documentation, test coverage, and non-behavioral code quality, completed dependencies before writable implementation, read-only advance investigation, and up to three size-aware workers with clean worktree removal or reuse.
  - Confidence/default: high; repository policy → accepted
  - Settings: `{"branch_base": "dev", "child_target": "nearest_parent_branch", "commit_style": "conventional", "commit_unit": "verified_subgoal", "conversational_approval": "allowed_otherwise", "dependency_base": "dependency_branch", "execution_branch": "per_goal", "merge_after_approval": "when_authorized", "multiple_dependency_base": "reviewed_base_containing_all", "parent_pseudo_trunk": true, "pr_approval": "required_when_repository_requires_pr", "pull_request_target": "dev", "pull_request_unit": "per_goal", "read_only_dependency_investigation": "allowed_before_completion", "release_actor": "david-rzepa", "release_branch": "main", "release_update": "explicit_owner_force_push", "release_workflow": "main_update_runs_release_ci", "review_gate": "human_after_checks", "review_pending_dependency": "wait_for_completed_dependencies", "review_state_reads_per_checkpoint": 1, "shared_pull_request": "explicit_reviewed_override"}`
  - Exceptions: none
  - Unresolved: none
- [x] `[policy:execution_continuation]` **Execution and work continuation** (applicable)
  - Decision: Continue across actionable goals under reviewed dependency and resource policy, and incorporate newly captured goals at the next safe checkpoint.
  - Rationale: The charter prioritizes reducing babysitting while preserving explicit boundaries.
  - Sources: E-001: .zzzops/PROJECT.md — The existing confirmed charter defines the outcome, KPIs, acceptance criteria, and value constraints.; E-005: user decisions and goals #59/#88/#94/#95 — User decisions require review-ready dependency stacking, a brief bounded human-unblock watch, and artifact-specific verification without recursive documentation or test meta-tests.
  - Confidence/default: high; ZzzOps default → accepted
  - Settings: `{"after_additive_capture": "resume_once_and_reprioritize", "continue_while_actionable": true, "cross_task": "require_explicit_harness_signal", "execute_intent": "same_task_until_superseded", "exhausted_handoff_retains_intent": true, "human_unblock_watch": {"enabled": true, "max_blockers": 1, "max_seconds": 180, "notify_once": true, "poll_seconds": 30, "trigger": "total_actionable_exhaustion"}, "max_easy_wins": 2, "new_goal_checkpoint": "next_safe_checkpoint", "stop_reasons_clear_intent": ["user_stop", "pause", "replacement_request", "capture_only", "required_authority", "blocking_boundary"], "triage_new_first": true}`
  - Exceptions: none
  - Unresolved: none
- [x] `[policy:verification_testing]` **Verification and testing** (applicable)
  - Decision: Require artifact-appropriate observable evidence in small chunks; documentation and test cases need no recursive tests, while product behavior and reusable test infrastructure require direct verification.
  - Rationale: Root instructions forbid unobservable implementation and unsanctioned test-bug fixes.
  - Sources: E-002: AGENTS.md — Repository guidance requires dev-based per-goal implementation and PRs, Conventional Commits, human review, owner-only main releases, prompt-budget checks, observable work, and reviewed PROJECT policy as the operational source of truth.; E-005: user decisions and goals #59/#88/#94/#95 — User decisions require review-ready dependency stacking, a brief bounded human-unblock watch, and artifact-specific verification without recursive documentation or test meta-tests.
  - Confidence/default: high; repository policy → accepted
  - Settings: `{"artifact_verification": {"documentation": "inspect_artifact_no_feature_test", "product_runtime": "risk_proportionate_behavioral_probe", "test_cases": "run_changed_tests_no_recursive_meta_test", "test_harness": "focused_behavioral_regression"}, "mode": "chunk_probe", "test_bug": "capture_and_ask", "widen": "as_relevant"}`
  - Exceptions: none
  - Unresolved: none
- [x] `[policy:code_quality]` **Code-quality and refactoring boundaries** (applicable)
  - Decision: Preserve behavior unless a goal explicitly authorizes a behavior change.
  - Rationale: A bounded self-review prevents unrelated cleanup from expanding work.
  - Sources: E-002: AGENTS.md — Repository guidance requires dev-based per-goal implementation and PRs, Conventional Commits, human review, owner-only main releases, prompt-budget checks, observable work, and reviewed PROJECT policy as the operational source of truth.
  - Confidence/default: medium; ZzzOps default → accepted
  - Settings: `{"completion_self_review": "required_before_review_or_done", "dead_code": "remove_only_if_evidenced_and_in_scope", "dynamic_generated_vendor": "retain_without_proof", "non_behavioral_only_without_feature_goal": true, "record_clean_review": true, "reverify_after_changes": true, "review_scope": "goal_diff_tests_and_relevant_surroundings"}`
  - Exceptions: none
  - Unresolved: none
- [x] `[policy:dependencies_tooling]` **Dependencies, tooling, and generated artifacts** (applicable)
  - Decision: Use project-native tooling; do not hand-edit generated or dependency-owned files.
  - Rationale: Keeps deterministic mechanics portable and ownership clear.
  - Sources: E-001: .zzzops/PROJECT.md — The existing confirmed charter defines the outcome, KPIs, acceptance criteria, and value constraints.
  - Confidence/default: medium; ZzzOps default → accepted
  - Settings: `{"dependency_changes": "explicit_scope", "generated_files": "source_or_generator_only", "tooling": "project_native"}`
  - Exceptions: none
  - Unresolved: none
- [x] `[policy:security_privacy_compliance]` **Security, privacy, secrets, and compliance** (applicable)
  - Decision: Repository policy may tighten but never weaken safety and authority boundaries.
  - Rationale: The charter expressly forbids secret exposure and invented authority.
  - Sources: E-001: .zzzops/PROJECT.md — The existing confirmed charter defines the outcome, KPIs, acceptance criteria, and value constraints.
  - Confidence/default: high; ZzzOps safety boundary → accepted
  - Settings: `{"production_mutation": "explicit_authority", "project_constraints": [], "secrets": "never_expose"}`
  - Exceptions: none
  - Unresolved: none
- [x] `[policy:documentation_style]` **Documentation and style** (applicable)
  - Decision: Follow evidenced repository documentation and style conventions; use outcome-first, low-technical-detail user updates by default while allowing explicit project policy to override the style.
  - Rationale: Repository instructions require prompt-budget updates, and the user selected concise actionable communication as this project's default without making it universal policy.
  - Sources: E-002: AGENTS.md — Repository guidance requires dev-based per-goal implementation and PRs, Conventional Commits, human review, owner-only main releases, prompt-budget checks, observable work, and reviewed PROJECT policy as the operational source of truth.; E-006: user decision and goal #102 — Communication style is reviewed project policy; outcome-first, low-technical-detail updates are the user's preferred ZzzOps default and may be overridden by explicit project policy.
  - Confidence/default: high; repository policy and user-preferred ZzzOps default → accepted
  - Settings: `{"communication": {"style": "outcome_first", "technical_detail": "decision_risk_failure_or_request", "user_action": "one_clear_action_with_reason_and_next_step"}, "documentation": "repository_conventions", "installed_prompt_markdown_check": ".agents/prompt_stats.py --check", "prompt_budget_ceiling": "explicit_value_justification", "prompt_counts": "do_not_commit", "style": "repository_conventions"}`
  - Exceptions: none
  - Unresolved: none
- [x] `[policy:deployment_resources]` **Deployment, environment, and resources** (applicable)
  - Decision: Do not deploy without authority; choose bounded parallelism from the deterministic tracked-file repository size.
  - Rationale: Repository release policy restricts main updates, while the tracked tree is below 100 MB and the user selected size-aware parallel defaults.
  - Sources: E-002: AGENTS.md — Repository guidance requires dev-based per-goal implementation and PRs, Conventional Commits, human review, owner-only main releases, prompt-budget checks, observable work, and reviewed PROJECT policy as the operational source of truth.; E-007: user decisions and goal #117 on 2026-07-20 — User selected bounded refill for documentation, test coverage, and non-behavioral code quality, completed dependencies before writable implementation, read-only advance investigation, and up to three size-aware workers with clean worktree removal or reuse.
  - Confidence/default: high; repository policy → accepted
  - Settings: `{"delegate_wait_after_seconds": 60, "deployment": "explicit_authority", "resource_mode": "size_aware"}`
  - Exceptions: none
  - Unresolved: none
- [x] `[policy:autonomy_approval_parallelism]` **Autonomy, approvals, and parallelism** (applicable)
  - Decision: Maximize safe autonomous progress; interview on consequential blockers; refill documentation, test-coverage, and non-behavioral code-quality work within the reviewed limit; use at most three size-aware workers with explicit worktree cleanup or reuse.
  - Rationale: The charter values autonomy, and the user selected one reviewed policy surface with bounded valuable refill, strict writable dependency gates, and size-aware parallelism.
  - Sources: E-001: .zzzops/PROJECT.md — The existing confirmed charter defines the outcome, KPIs, acceptance criteria, and value constraints.; E-002: AGENTS.md — Repository guidance requires dev-based per-goal implementation and PRs, Conventional Commits, human review, owner-only main releases, prompt-budget checks, observable work, and reviewed PROJECT policy as the operational source of truth.; E-004: user decisions and completed issues #77/#81 — Health reminders were removed and GitHub Issues is now the only supported canonical goal backend.; E-007: user decisions and goal #117 on 2026-07-20 — User selected bounded refill for documentation, test coverage, and non-behavioral code quality, completed dependencies before writable implementation, read-only advance investigation, and up to three size-aware workers with clean worktree removal or reuse.
  - Confidence/default: high; user-selected ZzzOps defaults and project policy → accepted
  - Settings: `{"blocker_interview": "immediate_batch", "blocker_order": ["safety_access_human", "cross_goal_decisions", "specification", "technical_unknown"], "capture_defaults": {"confidence": "low", "difficulty": "unknown", "priority": "P2"}, "claim_ttl_hours": 4, "dependency_implementation_gate": "dependencies_done", "max_workers": 3, "parallelization": {"at_or_above_threshold_mode": "read_only", "below_threshold_mode": "worktrees", "measurement": "existing_git_tracked_worktree_bytes", "threshold_bytes": 104857600}, "planning": {"decompose_at": "L", "max_depth": 3}, "project_parallel_ceiling": "size_aware", "read_only_dependency_investigation": true, "refill": {"allowed_categories": ["documentation", "tests", "code_quality_non_behavioral"], "enabled": true, "max_per_run": 3}, "worktree_lifecycle": {"abandoned_or_dirty": "forbidden", "after_task": "remove_or_retain_clean_for_reuse", "reuse_requires": ["clean_state", "reviewed_base", "new_goal_resources", "safe_branch_reassignment"]}}`
  - Exceptions: none
  - Unresolved: none

## Review record

| Date | Actor/run | Change | Reason/evidence |
| --- | --- | --- | --- |
| 2026-07-18 | ZzzOps initialization | Created pending revision 4 | Confirmed agent-generated draft; exact-file policy review still required. |
| 2026-07-18 | user | Reviewed policy revision 5 | Approved: backend, git_review_release, execution_continuation, verification_testing, code_quality, dependencies_tooling, security_privacy_compliance, documentation_style, deployment_resources, autonomy_approval_parallelism; source digest `sha256:2144f007236745e92fc6b43f863f8ae8ecc5273bc2311113165aa1d59fdbeb8b`. |
| 2026-07-18 | ZzzOps initialization | Created pending revision 6 | Confirmed agent-generated draft; exact-file policy review still required. |
| 2026-07-18 | user | Reviewed policy revision 7 | Approved: backend, git_review_release, execution_continuation, verification_testing, code_quality, dependencies_tooling, security_privacy_compliance, documentation_style, deployment_resources, autonomy_approval_parallelism; source digest `sha256:2b444e1cc59b555abbd06c62d82cc3cd695a25358bee97dcef14ea2ac44f78f7`. |
| 2026-07-19 | ZzzOps maintenance | Removed inert transition state in revision 8 | The field was permanently false and contradicted the final v1 no-prior-schema-migration contract; reviewed policy decisions are unchanged. |
| 2026-07-19 | ZzzOps execute #95 | Encoded policy/default conformance in revision 9 | Added source-cited review-ready stacking, bounded human-watch defaults, artifact verification, release boundaries, and prompt-budget settings; PR review is the exact-file policy checkpoint. |
| 2026-07-19 | ZzzOps execute #95 review | Clarified stacked actionability in revision 10 | Made explicit that a review-blocked dependency can still make its child actionable; dependency status and merge order do not serialize implementation when the exact checkpoint satisfies reviewed policy. |
| 2026-07-19 | user/ZzzOps execute #102 | Added communication policy in revision 11 | User selected outcome-first, low-technical-detail communication as the default while requiring explicit project policy to remain able to override it. |
| 2026-07-20 | user/ZzzOps execute #117 | Consolidated operational policy in revision 12 | Removed local preferences; selected bounded refill for documentation, test coverage, and non-behavioral code quality, completed dependency gates for writes, tracked-size parallel defaults with three workers, read-only advance investigation, and mandatory worktree cleanup or safe reuse. |

The machine-readable authority is [POLICY.json](POLICY.json); this file is its human audit view.
