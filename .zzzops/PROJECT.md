# Project success charter

**Status:** complete
**Last reviewed:** 2026-09-24

## Overall goal
- Outcome: ZzzOps lets supported coding agents manage long-term project work autonomously with durable state, minimal babysitting, and explicit human control.
- Primary beneficiaries: developers delegating long-running project work to coding agents
- Why it matters: Users can stop supervising agents late into the night without losing progress, priorities, blockers, or available work.
- Time horizon: ongoing, reviewed monthly

## Success metrics
| KPI | Why it matters | Baseline | Target / threshold | Evidence source | Review cadence |
| --- | --- | --- | --- | --- | --- |
| Canonical goal integrity | Lost or duplicated goal truth defeats autonomous execution. | GitHub Issues are the canonical backend. | Zero known lost or duplicated canonical goals. | Backend portfolio and migration/idempotency tests. | Each release |
| Time to usable backlog | Setup friction increases babysitting. | Not yet measured. | Supported plugin install to initialized, capturable backlog in under 10 minutes. | Timed supported-platform plugin installation and initialization acceptance run. | Each release |
| Autonomous workflow transitions | Measures whether agents can continue without unscheduled intervention. | Not yet measured. | At least 80% of eligible workflow transitions need no unscheduled human input. | Goal histories and categorized blocker records. | Monthly after at least 20 transitions |

## Project acceptance criteria
- [x] A clean supported Agent Plugin installation can be agent-initialized and capture a canonical goal without manual form filling.
- [x] An execution run can prioritize, unblock, verify, checkpoint, and cycle across durable goals without losing state.
- [x] Unsupported capabilities and human-only decisions become explicit categorized blockers rather than invented behavior.
- [x] Supported coding agents receive concise, discoverable Agent Plugin workflow semantics.
- [x] Tests prove Agent Plugin packaging and marketplace discovery, backend invariants, fast observable feedback, and prompt-budget accounting.

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
- Keep Codex and Claude Code distributions generated from shared canonical sources; claim platform support only after platform-native validation and install/discovery/workflow acceptance evidence.

### Non-goals
- Replace general-purpose project management suites.
- Guarantee capabilities that Codex does not expose.
- Restore or maintain the retired per-project installer, or maintain divergent Codex and Claude Code workflow implementations.
- Spend tokens on work with no evidenced link to project value.

### Unacceptable tradeoffs
- More autonomy at the expense of user health, privacy, repository safety, or observable correctness.
- Lower prompt cost by omitting state required for safe resumption or human control.

## Assumptions and open questions
- None recorded at initialization; add evidence-backed changes with history.

## Operating policy

- `[policy:backend]` **Canonical goal backend** — Agent instructions: Use the CLI-selected backend as the authority for shared goal state. Require the repository identity and observed capability evidence to match; never fall back silently. CLI configuration: authority="github_issues"; capability_evidence="init inspect 2026-07-18"; repository_identity="davi… (customized from a ZzzOps default)
- `[policy:git_review_release]` **Git, review, and release** — Agent instructions: Follow repository rules and the CLI-selected pull-request mode. Keep one branch and pull request per source-changing goal and one active stack. Base dependent work on the exact reviewed dependency checkpoint, make verified sub-goal commits, collect human pull-request approval at true queue exhaustion, and integrate in dependency order. Never bypass policy review, required checks, merge authority, or release authority. Preserve released state; replace affected project-owned state only after explicit evidence that the project has never been released. Ordinary branches start from dev and pull requests target their preceding goal branch or dev. Only david-rzepa may force-update main after release preconditions; main updates run release CI. CLI configuration: pull_request_mode="github_stacked_when_verified_else_chained"; review_pending_dependency="stack_fro… (customized from a ZzzOps default)
- `[policy:verification_testing]` **Verification and testing** — Agent instructions: Require artifact-appropriate observable evidence in small chunks. Documentation and test cases need no recursive tests; product behavior and reusable test infrastructure require direct verification. Use the smallest unique falsifiable local probe, widen when relevant, inspect exact pull-request-head CI when configured, and capture test-discovered product bugs separately. Capture test-discovered bugs as durable blockers. Preserve required exact-head CI. CLI configuration: required_ci="inspect_exact_pr_head" (customized from a ZzzOps default)
- `[policy:code_quality]` **Code-quality and refactoring boundaries** — Agent instructions: Preserve behavior unless a goal explicitly authorizes a behavior change. Without a feature goal, limit cleanup to behavior-preserving changes; remove dead code only with evidence and treat dynamic, generated, and vendored code conservatively. CLI configuration: none (adopted from the recorded ZzzOps default)
- `[policy:dependencies_tooling]` **Dependencies, tooling, and generated artifacts** — Agent instructions: Use project-native tooling, do not hand-edit generated artifacts, and make dependency changes only with explicit goal scope and verification. Generate supported-platform distributions from shared canonical sources and verify with platform-native validation and acceptance evidence. CLI configuration: none (customized from a ZzzOps default)
- `[policy:security_privacy_compliance]` **Security, privacy, secrets, and compliance** — Agent instructions: Never expose secrets or mutate production without authority. Repository rules may tighten but cannot weaken safety, privacy, or compliance boundaries. CLI configuration: none (adopted from the recorded ZzzOps default)
- `[policy:documentation_style]` **Documentation and style** — Agent instructions: Follow evidenced repository documentation and style conventions, communicate outcomes first, and include implementation detail only where it helps decisions. Run .agents/prompt_stats.py --check after prompt Markdown changes. Do not commit generated counts or raise ceilings without explicit value justification. CLI configuration: none (customized from a ZzzOps default)
- `[policy:deployment_resources]` **Deployment, environment, and resources** — Agent instructions: Do not deploy without authority. Prefer bounded worktree parallelism below the reviewed 100 MiB tracked-worktree threshold and read-only investigation at or above it; wait rather than duplicate active delegated work. Wait for delegated work after 60 seconds rather than duplicating it. CLI configuration: none (customized from a ZzzOps default)
- `[policy:engineering_rigor]` **Engineering rigor** — Agent instructions: Assess engineering risk and commitment carefully, raise rigor when evidence warrants it, and scale requirements discovery from light through thorough with effective rigor. CLI configuration: level="structured"; minimums.authentication="agentic"; minimums.authorization="agentic"; minimums.d… (customized from a ZzzOps default)
- `[policy:model_routing]` **Model routing and delegation** — Agent instructions: Route each phase by effective rigor, consequence, boundedness, and phase type. Refresh runtime model and effort availability, select only reviewed pairs at sufficient capability and least cost, keep human interaction on root, require a session override above root capability, and persist a blocker when no reviewed capable pair is available. CLI configuration: assessment_tree=7 items; model_inventory.reviewed_pairs=32 items; tiers=4 items (customized from a ZzzOps default)
- `[policy:workflow_adherence]` **ZzzOps workflow adherence** — Agent instructions: Require durable tracked goals for substantial repository work. Read-only investigation and ZzzOps administration are exempt; only explicit scoped user authority grants an exception. Execute the reviewed phase graph with its independent reviews and human approvals. CLI configuration: phase_dag.phases=6 items; phase_dag.schema_version=1 (adopted from the recorded ZzzOps default)
- `[policy:automated_design]` **Automated design authority** — Agent instructions: Automated design is disabled by default. If an explicit reviewed policy enables it, limit it to bounded in-scope implementation: compare alternatives and structural cost for high-commitment choices, record assumptions and a falsifiable signal, prefer unambiguously risk-reducing privacy or security changes, and block on product scope, incompatible contracts, destructive migration, spending, deployment, external writes, human review, safety authority, or higher authority. CLI configuration: none (adopted from the recorded ZzzOps default)
- `[policy:autonomy_approval_parallelism]` **Autonomy, approvals, and parallelism** — Agent instructions: Capture requirements adaptively with the requesting user; during unattended execution persist consequential questions as blockers. Keep human interaction on root, enforce reviewed worker and resource limits, record privacy-safe execution diagnostics, and suggest only bounded valuable work in reviewed categories. Keep worktrees clean, remove or deliberately reuse them after work, and never abandon dirty worktrees. Do not automatically adopt suggested defaults without review. Repair in-scope CI failures without additional approval. Continue across actionable goals and reprioritize new work at safe checkpoints; persist unanswered questions without human-unblock watching, polling or notifications. CLI configuration: execution_reports.enabled=true; max_workers=3; refill.allowed_categories=documentation,tests,code_q… (customized from a ZzzOps default)

Detailed rationale and review history: [PROJECT_AUDIT.md](PROJECT_AUDIT.md). Canonical policy state: [POLICY.json](POLICY.json).
