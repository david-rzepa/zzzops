# Project success charter

<!-- zzzops-project-state
{"audit":{"digest":"sha256:19849ad3e2fa649bb7e3e7a3dc0fb64ee9853823f13cdfa6e0848c392a340b51","path":".zzzops/PROJECT_AUDIT.md"},"backend":"github_issues","initialized":true,"policy":{"schema_version":1,"sections":[{"decision":"github_issues","id":"backend","settings":{"authority":"github_issues","capability_evidence":"init inspect 2026-07-18","fallback":"forbidden","repository_identity":"david-rzepa/zzzops","tradeoffs":{"github_issues":"shared native issue queue requiring GitHub access"}}},{"decision":"Per-goal branches from dev and PRs to dev. Writable implementation waits until every dependency is complete; read-only investigation may prepare later work without claiming or starting it. Use Conventional Commits, human review after checks, and owner-only main releases.","id":"git_review_release","settings":{"branch_base":"dev","child_target":"nearest_parent_branch","commit_style":"conventional","commit_unit":"verified_subgoal","conversational_approval":"allowed_otherwise","dependency_base":"dependency_branch","execution_branch":"per_goal","merge_after_approval":"when_authorized","multiple_dependency_base":"reviewed_base_containing_all","parent_pseudo_trunk":true,"pr_approval":"required_when_repository_requires_pr","pull_request_target":"dev","pull_request_unit":"per_goal","read_only_dependency_investigation":"allowed_before_completion","release_actor":"david-rzepa","release_branch":"main","release_update":"explicit_owner_force_push","release_workflow":"main_update_runs_release_ci","review_gate":"human_after_checks","review_pending_dependency":"wait_for_completed_dependencies","review_state_reads_per_checkpoint":1,"shared_pull_request":"explicit_reviewed_override"}},{"decision":"Continue across actionable goals under reviewed dependency and resource policy, and incorporate newly captured goals at the next safe checkpoint.","id":"execution_continuation","settings":{"after_additive_capture":"resume_once_and_reprioritize","continue_while_actionable":true,"cross_task":"require_explicit_harness_signal","execute_intent":"same_task_until_superseded","exhausted_handoff_retains_intent":true,"human_unblock_watch":{"enabled":true,"max_blockers":1,"max_seconds":180,"notify_once":true,"poll_seconds":30,"trigger":"total_actionable_exhaustion"},"max_easy_wins":2,"new_goal_checkpoint":"next_safe_checkpoint","stop_reasons_clear_intent":["user_stop","pause","replacement_request","capture_only","required_authority","blocking_boundary"],"triage_new_first":true}},{"decision":"Require artifact-appropriate observable evidence in small chunks; documentation and test cases need no recursive tests, while product behavior and reusable test infrastructure require direct verification.","id":"verification_testing","settings":{"artifact_verification":{"documentation":"inspect_artifact_no_feature_test","product_runtime":"risk_proportionate_behavioral_probe","test_cases":"run_changed_tests_no_recursive_meta_test","test_harness":"focused_behavioral_regression"},"mode":"chunk_probe","test_bug":"capture_and_ask","widen":"as_relevant"}},{"decision":"Preserve behavior unless a goal explicitly authorizes a behavior change.","id":"code_quality","settings":{"completion_self_review":"required_before_review_or_done","dead_code":"remove_only_if_evidenced_and_in_scope","dynamic_generated_vendor":"retain_without_proof","non_behavioral_only_without_feature_goal":true,"record_clean_review":true,"reverify_after_changes":true,"review_scope":"goal_diff_tests_and_relevant_surroundings"}},{"decision":"Use project-native tooling; do not hand-edit generated or dependency-owned files.","id":"dependencies_tooling","settings":{"dependency_changes":"explicit_scope","generated_files":"source_or_generator_only","tooling":"project_native"}},{"decision":"Repository policy may tighten but never weaken safety and authority boundaries.","id":"security_privacy_compliance","settings":{"production_mutation":"explicit_authority","project_constraints":[],"secrets":"never_expose"}},{"decision":"Follow evidenced repository documentation and style conventions; use outcome-first, low-technical-detail user updates by default while allowing explicit project policy to override the style.","id":"documentation_style","settings":{"communication":{"style":"outcome_first","technical_detail":"decision_risk_failure_or_request","user_action":"one_clear_action_with_reason_and_next_step"},"documentation":"repository_conventions","installed_prompt_markdown_check":".agents/prompt_stats.py --check","prompt_budget_ceiling":"explicit_value_justification","prompt_counts":"do_not_commit","style":"repository_conventions"}},{"decision":"Do not deploy without authority; choose bounded parallelism from the deterministic tracked-file repository size.","id":"deployment_resources","settings":{"delegate_wait_after_seconds":60,"deployment":"explicit_authority","resource_mode":"size_aware"}},{"decision":"Maximize safe autonomous progress; interview on consequential blockers; refill documentation, test-coverage, and non-behavioral code-quality work within the reviewed limit; use at most three size-aware workers with explicit worktree cleanup or reuse.","id":"autonomy_approval_parallelism","settings":{"blocker_interview":"immediate_batch","blocker_order":["safety_access_human","cross_goal_decisions","specification","technical_unknown"],"capture_defaults":{"confidence":"low","difficulty":"unknown","priority":"P2"},"claim_ttl_hours":4,"dependency_implementation_gate":"dependencies_done","max_workers":3,"parallelization":{"at_or_above_threshold_mode":"read_only","below_threshold_mode":"worktrees","measurement":"existing_git_tracked_worktree_bytes","threshold_bytes":104857600},"planning":{"decompose_at":"L","max_depth":3},"project_parallel_ceiling":"size_aware","read_only_dependency_investigation":true,"refill":{"allowed_categories":["documentation","tests","code_quality_non_behavioral"],"enabled":true,"max_per_run":3},"worktree_lifecycle":{"abandoned_or_dirty":"forbidden","after_task":"remove_or_retain_clean_for_reuse","reuse_requires":["clean_state","reviewed_base","new_goal_resources","safe_branch_reassignment"]}}}]},"repository":{"identity":"david-rzepa/zzzops","remote":"https://github.com/david-rzepa/zzzops.git"},"revision":12,"schema_version":1}
zzzops-project-state -->



**Status:** complete
**Last reviewed:** 2026-07-18

## Overall goal
- Outcome: ZzzOps lets Codex and Claude Code manage long-term project work autonomously with durable state, minimal babysitting, and explicit human control.
- Primary beneficiaries: developers delegating long-running project work to coding agents
- Why it matters: Users can stop supervising agents late into the night without losing progress, priorities, blockers, or available work.
- Time horizon: ongoing, reviewed monthly

## Success metrics
| KPI | Why it matters | Baseline | Target / threshold | Evidence source | Review cadence |
| --- | --- | --- | --- | --- | --- |
| Canonical goal integrity | Lost or duplicated goal truth defeats autonomous execution. | GitHub Issues are the canonical backend. | Zero known lost or duplicated canonical goals. | Backend portfolio and migration/idempotency tests. | Each release |
| Time to usable backlog | Setup friction increases babysitting. | Not yet measured. | Clean install to initialized, capturable backlog in under 10 minutes. | Timed clean-install and initialization acceptance run. | Each release |
| Autonomous workflow transitions | Measures whether agents can continue without unscheduled intervention. | Not yet measured. | At least 80% of eligible workflow transitions need no unscheduled human input. | Goal histories and categorized blocker records. | Monthly after at least 20 transitions |

## Project acceptance criteria
- [x] A clean installation can be agent-initialized and capture a canonical goal without manual form filling.
- [x] An execution run can prioritize, unblock, verify, checkpoint, and cycle across durable goals without losing state.
- [x] Unsupported capabilities and human-only decisions become explicit categorized blockers rather than invented behavior.
- [x] Codex and Claude Code receive equivalent concise workflow semantics.
- [x] Tests prove installer preservation, backend invariants, fast observable feedback, and prompt-budget accounting.

## Value rubric
- `critical`: required for project acceptance, safety, or a binding deadline.
- `high`: materially moves a priority KPI or unlocks critical/high-value work.
- `medium`: useful measurable contribution with limited leverage.
- `low`: weak, speculative, cosmetic, or currently unmeasured contribution.

When KPIs conflict, prefer: user authority and safety, correctness, privacy, verified project value, autonomy, then prompt savings

## Constraints and non-goals
### Constraints
- Remain primarily agent-driven and keep deterministic scripts narrow and cross-platform.
- Do not silently dual-write, fail over, invent user decisions, or expose secrets.
- Keep installed prompts distilled and prompt counts current.
- Use available subscription capacity to advance evidenced project goals and safe valuable backlog work; do not let quota maximization override value, safety, or user authority.

### Non-goals
- Replace general-purpose project management suites.
- Guarantee capabilities that Codex or Claude Code does not expose.
- Spend tokens on work with no evidenced link to project value.

### Unacceptable tradeoffs
- More autonomy at the expense of user health, privacy, repository safety, or observable correctness.
- Lower prompt cost by omitting state required for safe resumption or human control.

## Assumptions and open questions
- None recorded at initialization; add evidence-backed changes with history.

## Operating policy

- [policy:backend] Canonical goal backend
- [policy:git_review_release] Git, review, and release
- [policy:execution_continuation] Execution and work continuation
- [policy:verification_testing] Verification and testing
- [policy:code_quality] Code-quality and refactoring boundaries
- [policy:dependencies_tooling] Dependencies, tooling, and generated artifacts
- [policy:security_privacy_compliance] Security, privacy, secrets, and compliance
- [policy:documentation_style] Documentation and style
- [policy:deployment_resources] Deployment, environment, and resources
- [policy:autonomy_approval_parallelism] Autonomy, approvals, and parallelism

Full reviewed evidence and history: [PROJECT_AUDIT.md](PROJECT_AUDIT.md) (`sha256:410c8eaba7eafe9be3f8119e3991751377213600b5a29f20bbcc65a1287ca857`).
