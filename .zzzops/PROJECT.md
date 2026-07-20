# Project success charter

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

- `[policy:backend]` **Canonical goal backend**: github_issues
- `[policy:git_review_release]` **Git, review, and release**: Per-goal branches from dev and PRs to dev. Writable implementation waits until every dependency is complete; read-only investigation may prepare later work without claiming or starting it. Use Conventional Commits, human review after checks, and owner-only main releases.
- `[policy:execution_continuation]` **Execution and work continuation**: Continue across actionable goals under reviewed dependency and resource policy, and incorporate newly captured goals at the next safe checkpoint.
- `[policy:verification_testing]` **Verification and testing**: Require artifact-appropriate observable evidence in small chunks; documentation and test cases need no recursive tests, while product behavior and reusable test infrastructure require direct verification.
- `[policy:code_quality]` **Code-quality and refactoring boundaries**: Preserve behavior unless a goal explicitly authorizes a behavior change.
- `[policy:dependencies_tooling]` **Dependencies, tooling, and generated artifacts**: Use project-native tooling; do not hand-edit generated or dependency-owned files.
- `[policy:security_privacy_compliance]` **Security, privacy, secrets, and compliance**: Repository policy may tighten but never weaken safety and authority boundaries.
- `[policy:documentation_style]` **Documentation and style**: Follow evidenced repository documentation and style conventions; use outcome-first, low-technical-detail user updates by default while allowing explicit project policy to override the style.
- `[policy:deployment_resources]` **Deployment, environment, and resources**: Do not deploy without authority; choose bounded parallelism from the deterministic tracked-file repository size.
- `[policy:autonomy_approval_parallelism]` **Autonomy, approvals, and parallelism**: Maximize safe autonomous progress; interview on consequential blockers; refill documentation, test-coverage, and non-behavioral code-quality work within the reviewed limit; use at most three size-aware workers with explicit worktree cleanup or reuse.

Detailed rationale and review history: [PROJECT_AUDIT.md](PROJECT_AUDIT.md). Canonical policy state: [POLICY.json](POLICY.json).
