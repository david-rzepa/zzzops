# Project success charter

<!-- zzzops-project-state
{
  "backend": "github_issues",
  "initialized": true,
  "policy": {
    "evidence": [
      {
        "finding": "The existing confirmed charter defines the outcome, KPIs, acceptance criteria, and value constraints.",
        "id": "E-001",
        "kind": "observed",
        "source": ".zzzops/PROJECT.md"
      },
      {
        "finding": "Repository guidance requires dev-based per-goal implementation, Conventional Commits, human review, observable work, and user-local preferences.",
        "id": "E-002",
        "kind": "observed",
        "source": "AGENTS.md"
      },
      {
        "finding": "GitHub Issues are enabled for david-rzepa/zzzops and the authenticated user has ADMIN permission.",
        "id": "E-003",
        "kind": "observed",
        "source": "init inspect 2026-07-18"
      },
      {
        "finding": "Health reminders were removed and GitHub Issues is now the only supported canonical goal backend.",
        "id": "E-004",
        "kind": "observed",
        "source": "user decisions and completed issues #77/#81"
      }
    ],
    "schema_version": 1,
    "sections": [
      {
        "applicable": true,
        "confidence": "high",
        "decision": "github_issues",
        "default_disposition": "accepted",
        "default_origin": "user decision and current product scope",
        "exceptions": [],
        "id": "backend",
        "rationale": "GitHub capability is usable and completed issue #81 made it the only supported authority.",
        "required": true,
        "review": {
          "approved": true,
          "date": "2026-07-18",
          "reviewed_digest": "sha256:2b444e1cc59b555abbd06c62d82cc3cd695a25358bee97dcef14ea2ac44f78f7",
          "reviewer": "user"
        },
        "settings": {
          "authority": "github_issues",
          "capability_evidence": "init inspect 2026-07-18",
          "fallback": "forbidden",
          "repository_identity": "david-rzepa/zzzops",
          "tradeoffs": {
            "github_issues": "shared native issue queue requiring GitHub access"
          }
        },
        "source_ids": [
          "E-003",
          "E-004"
        ],
        "title": "Canonical goal backend",
        "unresolved": []
      },
      {
        "applicable": true,
        "confidence": "high",
        "decision": "Per-goal branches from dev, PRs to dev, Conventional Commits, and human review after checks.",
        "default_disposition": "accepted",
        "default_origin": "repository policy",
        "exceptions": [],
        "id": "git_review_release",
        "rationale": "Root repository instructions define the integration and release boundary.",
        "required": true,
        "review": {
          "approved": true,
          "date": "2026-07-18",
          "reviewed_digest": "sha256:2b444e1cc59b555abbd06c62d82cc3cd695a25358bee97dcef14ea2ac44f78f7",
          "reviewer": "user"
        },
        "settings": {
          "branch_base": "dev",
          "child_target": "nearest_parent_branch",
          "commit_style": "conventional",
          "commit_unit": "verified_subgoal",
          "conversational_approval": "allowed_otherwise",
          "dependency_base": "dependency_branch",
          "execution_branch": "per_goal",
          "merge_after_approval": "when_authorized",
          "multiple_dependency_base": "reviewed_base_containing_all",
          "parent_pseudo_trunk": true,
          "pr_approval": "required_when_repository_requires_pr",
          "pull_request_unit": "per_goal",
          "review_gate": "human_after_checks",
          "shared_pull_request": "explicit_reviewed_override"
        },
        "source_ids": [
          "E-002"
        ],
        "title": "Git, review, and release",
        "unresolved": []
      },
      {
        "applicable": true,
        "confidence": "high",
        "decision": "Continue sequentially across actionable goals and incorporate newly captured goals at the next safe checkpoint.",
        "default_disposition": "accepted",
        "default_origin": "ZzzOps default",
        "exceptions": [],
        "id": "execution_continuation",
        "rationale": "The charter prioritizes reducing babysitting while preserving explicit boundaries.",
        "required": true,
        "review": {
          "approved": true,
          "date": "2026-07-18",
          "reviewed_digest": "sha256:2b444e1cc59b555abbd06c62d82cc3cd695a25358bee97dcef14ea2ac44f78f7",
          "reviewer": "user"
        },
        "settings": {
          "after_additive_capture": "resume_once_and_reprioritize",
          "continue_while_actionable": true,
          "cross_task": "require_explicit_harness_signal",
          "execute_intent": "same_task_until_superseded",
          "exhausted_handoff_retains_intent": true,
          "max_easy_wins": 2,
          "new_goal_checkpoint": "next_safe_checkpoint",
          "stop_reasons_clear_intent": [
            "user_stop",
            "pause",
            "replacement_request",
            "capture_only",
            "required_authority",
            "blocking_boundary"
          ],
          "triage_new_first": true
        },
        "source_ids": [
          "E-001"
        ],
        "title": "Execution and work continuation",
        "unresolved": []
      },
      {
        "applicable": true,
        "confidence": "high",
        "decision": "Require observable evidence in small chunks; capture test-discovered product bugs and ask before expanding scope.",
        "default_disposition": "accepted",
        "default_origin": "repository policy",
        "exceptions": [],
        "id": "verification_testing",
        "rationale": "Root instructions forbid unobservable implementation and unsanctioned test-bug fixes.",
        "required": true,
        "review": {
          "approved": true,
          "date": "2026-07-18",
          "reviewed_digest": "sha256:2b444e1cc59b555abbd06c62d82cc3cd695a25358bee97dcef14ea2ac44f78f7",
          "reviewer": "user"
        },
        "settings": {
          "mode": "chunk_probe",
          "test_bug": "capture_and_ask",
          "widen": "as_relevant"
        },
        "source_ids": [
          "E-002"
        ],
        "title": "Verification and testing",
        "unresolved": []
      },
      {
        "applicable": true,
        "confidence": "medium",
        "decision": "Preserve behavior unless a goal explicitly authorizes a behavior change.",
        "default_disposition": "accepted",
        "default_origin": "ZzzOps default",
        "exceptions": [],
        "id": "code_quality",
        "rationale": "A bounded self-review prevents unrelated cleanup from expanding work.",
        "required": true,
        "review": {
          "approved": true,
          "date": "2026-07-18",
          "reviewed_digest": "sha256:2b444e1cc59b555abbd06c62d82cc3cd695a25358bee97dcef14ea2ac44f78f7",
          "reviewer": "user"
        },
        "settings": {
          "completion_self_review": "required_before_review_or_done",
          "dead_code": "remove_only_if_evidenced_and_in_scope",
          "dynamic_generated_vendor": "retain_without_proof",
          "non_behavioral_only_without_feature_goal": true,
          "record_clean_review": true,
          "reverify_after_changes": true,
          "review_scope": "goal_diff_tests_and_relevant_surroundings"
        },
        "source_ids": [
          "E-002"
        ],
        "title": "Code-quality and refactoring boundaries",
        "unresolved": []
      },
      {
        "applicable": true,
        "confidence": "medium",
        "decision": "Use project-native tooling; do not hand-edit generated or dependency-owned files.",
        "default_disposition": "accepted",
        "default_origin": "ZzzOps default",
        "exceptions": [],
        "id": "dependencies_tooling",
        "rationale": "Keeps deterministic mechanics portable and ownership clear.",
        "required": true,
        "review": {
          "approved": true,
          "date": "2026-07-18",
          "reviewed_digest": "sha256:2b444e1cc59b555abbd06c62d82cc3cd695a25358bee97dcef14ea2ac44f78f7",
          "reviewer": "user"
        },
        "settings": {
          "dependency_changes": "explicit_scope",
          "generated_files": "source_or_generator_only",
          "tooling": "project_native"
        },
        "source_ids": [
          "E-001"
        ],
        "title": "Dependencies, tooling, and generated artifacts",
        "unresolved": []
      },
      {
        "applicable": true,
        "confidence": "high",
        "decision": "Repository policy may tighten but never weaken safety and authority boundaries.",
        "default_disposition": "accepted",
        "default_origin": "ZzzOps safety boundary",
        "exceptions": [],
        "id": "security_privacy_compliance",
        "rationale": "The charter expressly forbids secret exposure and invented authority.",
        "required": true,
        "review": {
          "approved": true,
          "date": "2026-07-18",
          "reviewed_digest": "sha256:2b444e1cc59b555abbd06c62d82cc3cd695a25358bee97dcef14ea2ac44f78f7",
          "reviewer": "user"
        },
        "settings": {
          "production_mutation": "explicit_authority",
          "project_constraints": [],
          "secrets": "never_expose"
        },
        "source_ids": [
          "E-001"
        ],
        "title": "Security, privacy, secrets, and compliance",
        "unresolved": []
      },
      {
        "applicable": true,
        "confidence": "high",
        "decision": "Follow evidenced repository documentation and style conventions.",
        "default_disposition": "accepted",
        "default_origin": "repository policy",
        "exceptions": [],
        "id": "documentation_style",
        "rationale": "Repository instructions require prompt-budget updates for instruction/template Markdown.",
        "required": true,
        "review": {
          "approved": true,
          "date": "2026-07-18",
          "reviewed_digest": "sha256:2b444e1cc59b555abbd06c62d82cc3cd695a25358bee97dcef14ea2ac44f78f7",
          "reviewer": "user"
        },
        "settings": {
          "documentation": "repository_conventions",
          "style": "repository_conventions"
        },
        "source_ids": [
          "E-002"
        ],
        "title": "Documentation and style",
        "unresolved": []
      },
      {
        "applicable": true,
        "confidence": "high",
        "decision": "Do not deploy without authority; default to sequential execution except bounded read-only delegation.",
        "default_disposition": "accepted",
        "default_origin": "repository policy",
        "exceptions": [],
        "id": "deployment_resources",
        "rationale": "Repository release policy restricts main updates and user preferences only allow read-only parallelism.",
        "required": true,
        "review": {
          "approved": true,
          "date": "2026-07-18",
          "reviewed_digest": "sha256:2b444e1cc59b555abbd06c62d82cc3cd695a25358bee97dcef14ea2ac44f78f7",
          "reviewer": "user"
        },
        "settings": {
          "delegate_wait_after_seconds": 60,
          "deployment": "explicit_authority",
          "resource_mode": "read_only"
        },
        "source_ids": [
          "E-002"
        ],
        "title": "Deployment, environment, and resources",
        "unresolved": []
      },
      {
        "applicable": true,
        "confidence": "high",
        "decision": "Maximize safe autonomous progress; interview on consequential blockers; use at most two read-only workers.",
        "default_disposition": "accepted",
        "default_origin": "project and user policy",
        "exceptions": [],
        "id": "autonomy_approval_parallelism",
        "rationale": "The charter values autonomy, completed issue #77 removed health reminders, and user-local preferences set a read-only two-worker ceiling.",
        "required": true,
        "review": {
          "approved": true,
          "date": "2026-07-18",
          "reviewed_digest": "sha256:2b444e1cc59b555abbd06c62d82cc3cd695a25358bee97dcef14ea2ac44f78f7",
          "reviewer": "user"
        },
        "settings": {
          "blocker_interview": "immediate_batch",
          "capture_defaults": {
            "confidence": "low",
            "difficulty": "unknown",
            "priority": "P2"
          },
          "claim_ttl_hours": 4,
          "max_workers": 2,
          "planning": {
            "decompose_at": "L",
            "max_depth": 3
          },
          "project_parallel_ceiling": "read_only",
          "refill": {
            "allowed_categories": [
              "documentation",
              "tests",
              "code_quality_non_behavioral"
            ],
            "max_per_run": 3
          }
        },
        "source_ids": [
          "E-001",
          "E-002",
          "E-004"
        ],
        "title": "Autonomy, approvals, and parallelism",
        "unresolved": []
      }
    ]
  },
  "repository": {
    "identity": "david-rzepa/zzzops",
    "remote": "https://github.com/david-rzepa/zzzops.git"
  },
  "revision": 8,
  "schema_version": 1
}
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

## Operating policy review
Read every section in this exact file. Each unchecked stable policy ID is a `decision` blocker. Only explicit user approval may check it; repository evidence or agent inference is not approval.

- [x] `[policy:backend]` **Canonical goal backend** (applicable)
  - Decision: github_issues
  - Rationale: GitHub capability is usable and completed issue #81 made it the only supported authority.
  - Sources: E-003: init inspect 2026-07-18 — GitHub Issues are enabled for david-rzepa/zzzops and the authenticated user has ADMIN permission.; E-004: user decisions and completed issues #77/#81 — Health reminders were removed and GitHub Issues is now the only supported canonical goal backend.
  - Confidence/default: high; user decision and current product scope → accepted
  - Settings: `{"authority": "github_issues", "capability_evidence": "init inspect 2026-07-18", "fallback": "forbidden", "repository_identity": "david-rzepa/zzzops", "tradeoffs": {"github_issues": "shared native issue queue requiring GitHub access"}}`
  - Exceptions: none
  - Unresolved: none
- [x] `[policy:git_review_release]` **Git, review, and release** (applicable)
  - Decision: Per-goal branches from dev, PRs to dev, Conventional Commits, and human review after checks.
  - Rationale: Root repository instructions define the integration and release boundary.
  - Sources: E-002: AGENTS.md — Repository guidance requires dev-based per-goal implementation, Conventional Commits, human review, observable work, and user-local preferences.
  - Confidence/default: high; repository policy → accepted
  - Settings: `{"branch_base": "dev", "child_target": "nearest_parent_branch", "commit_style": "conventional", "commit_unit": "verified_subgoal", "conversational_approval": "allowed_otherwise", "dependency_base": "dependency_branch", "execution_branch": "per_goal", "merge_after_approval": "when_authorized", "multiple_dependency_base": "reviewed_base_containing_all", "parent_pseudo_trunk": true, "pr_approval": "required_when_repository_requires_pr", "pull_request_unit": "per_goal", "review_gate": "human_after_checks", "shared_pull_request": "explicit_reviewed_override"}`
  - Exceptions: none
  - Unresolved: none
- [x] `[policy:execution_continuation]` **Execution and work continuation** (applicable)
  - Decision: Continue sequentially across actionable goals and incorporate newly captured goals at the next safe checkpoint.
  - Rationale: The charter prioritizes reducing babysitting while preserving explicit boundaries.
  - Sources: E-001: .zzzops/PROJECT.md — The existing confirmed charter defines the outcome, KPIs, acceptance criteria, and value constraints.
  - Confidence/default: high; ZzzOps default → accepted
  - Settings: `{"after_additive_capture": "resume_once_and_reprioritize", "continue_while_actionable": true, "cross_task": "require_explicit_harness_signal", "execute_intent": "same_task_until_superseded", "exhausted_handoff_retains_intent": true, "max_easy_wins": 2, "new_goal_checkpoint": "next_safe_checkpoint", "stop_reasons_clear_intent": ["user_stop", "pause", "replacement_request", "capture_only", "required_authority", "blocking_boundary"], "triage_new_first": true}`
  - Exceptions: none
  - Unresolved: none
- [x] `[policy:verification_testing]` **Verification and testing** (applicable)
  - Decision: Require observable evidence in small chunks; capture test-discovered product bugs and ask before expanding scope.
  - Rationale: Root instructions forbid unobservable implementation and unsanctioned test-bug fixes.
  - Sources: E-002: AGENTS.md — Repository guidance requires dev-based per-goal implementation, Conventional Commits, human review, observable work, and user-local preferences.
  - Confidence/default: high; repository policy → accepted
  - Settings: `{"mode": "chunk_probe", "test_bug": "capture_and_ask", "widen": "as_relevant"}`
  - Exceptions: none
  - Unresolved: none
- [x] `[policy:code_quality]` **Code-quality and refactoring boundaries** (applicable)
  - Decision: Preserve behavior unless a goal explicitly authorizes a behavior change.
  - Rationale: A bounded self-review prevents unrelated cleanup from expanding work.
  - Sources: E-002: AGENTS.md — Repository guidance requires dev-based per-goal implementation, Conventional Commits, human review, observable work, and user-local preferences.
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
  - Decision: Follow evidenced repository documentation and style conventions.
  - Rationale: Repository instructions require prompt-budget updates for instruction/template Markdown.
  - Sources: E-002: AGENTS.md — Repository guidance requires dev-based per-goal implementation, Conventional Commits, human review, observable work, and user-local preferences.
  - Confidence/default: high; repository policy → accepted
  - Settings: `{"documentation": "repository_conventions", "style": "repository_conventions"}`
  - Exceptions: none
  - Unresolved: none
- [x] `[policy:deployment_resources]` **Deployment, environment, and resources** (applicable)
  - Decision: Do not deploy without authority; default to sequential execution except bounded read-only delegation.
  - Rationale: Repository release policy restricts main updates and user preferences only allow read-only parallelism.
  - Sources: E-002: AGENTS.md — Repository guidance requires dev-based per-goal implementation, Conventional Commits, human review, observable work, and user-local preferences.
  - Confidence/default: high; repository policy → accepted
  - Settings: `{"delegate_wait_after_seconds": 60, "deployment": "explicit_authority", "resource_mode": "read_only"}`
  - Exceptions: none
  - Unresolved: none
- [x] `[policy:autonomy_approval_parallelism]` **Autonomy, approvals, and parallelism** (applicable)
  - Decision: Maximize safe autonomous progress; interview on consequential blockers; use at most two read-only workers.
  - Rationale: The charter values autonomy, completed issue #77 removed health reminders, and user-local preferences set a read-only two-worker ceiling.
  - Sources: E-001: .zzzops/PROJECT.md — The existing confirmed charter defines the outcome, KPIs, acceptance criteria, and value constraints.; E-002: AGENTS.md — Repository guidance requires dev-based per-goal implementation, Conventional Commits, human review, observable work, and user-local preferences.; E-004: user decisions and completed issues #77/#81 — Health reminders were removed and GitHub Issues is now the only supported canonical goal backend.
  - Confidence/default: high; project and user policy → accepted
  - Settings: `{"blocker_interview": "immediate_batch", "capture_defaults": {"confidence": "low", "difficulty": "unknown", "priority": "P2"}, "claim_ttl_hours": 4, "max_workers": 2, "planning": {"decompose_at": "L", "max_depth": 3}, "project_parallel_ceiling": "read_only", "refill": {"allowed_categories": ["documentation", "tests", "code_quality_non_behavioral"], "max_per_run": 3}}`
  - Exceptions: none
  - Unresolved: none

## History
| Date | Actor/run | Change | Reason/evidence |
| --- | --- | --- | --- |
| 2026-07-18 | ZzzOps initialization | Created pending revision 4 | Confirmed agent-generated draft; exact-file policy review still required. |
| 2026-07-18 | user | Reviewed policy revision 5 | Approved: backend, git_review_release, execution_continuation, verification_testing, code_quality, dependencies_tooling, security_privacy_compliance, documentation_style, deployment_resources, autonomy_approval_parallelism; source digest `sha256:2144f007236745e92fc6b43f863f8ae8ecc5273bc2311113165aa1d59fdbeb8b`. |
| 2026-07-18 | ZzzOps initialization | Created pending revision 6 | Confirmed agent-generated draft; exact-file policy review still required. |
| 2026-07-18 | user | Reviewed policy revision 7 | Approved: backend, git_review_release, execution_continuation, verification_testing, code_quality, dependencies_tooling, security_privacy_compliance, documentation_style, deployment_resources, autonomy_approval_parallelism; source digest `sha256:2b444e1cc59b555abbd06c62d82cc3cd695a25358bee97dcef14ea2ac44f78f7`. |
| 2026-07-19 | ZzzOps maintenance | Removed inert transition state in revision 8 | The field was permanently false and contradicted the final v1 no-prior-schema-migration contract; reviewed policy decisions are unchanged. |
