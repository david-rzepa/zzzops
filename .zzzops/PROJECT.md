# Project success charter

**Status:** complete
**Last reviewed:** 2026-08-29

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

- `[policy:backend]` **Canonical goal backend**: github_issues (default origin unknown)
- `[policy:git_review_release]` **Git, review, and release**: Use one branch and PR per goal. Prefer GitHub-native stacked PRs when the official capability is installed and provider stack membership is verified; otherwise explicitly use chained PRs from exact reviewed checkpoints. Merge in dependency order, use Conventional Commits, collect human PR approval when safe work is exhausted, and retain owner-only main releases. (default origin unknown)
- `[policy:execution_continuation]` **Execution and work continuation**: Continue across actionable goals under reviewed dependency and resource policy, incorporate newly captured goals at the next safe checkpoint, and persist unanswered questions without live interviewing, notification, polling, or waiting. (default origin unknown)
- `[policy:verification_testing]` **Verification and testing**: Require artifact-appropriate observable evidence in small chunks; documentation and test cases need no recursive tests, while product behavior and reusable test infrastructure require direct verification. (default origin unknown)
- `[policy:code_quality]` **Code-quality and refactoring boundaries**: Preserve behavior unless a goal explicitly authorizes a behavior change. (default origin unknown)
- `[policy:dependencies_tooling]` **Dependencies, tooling, and generated artifacts**: Use project-native tooling; do not hand-edit generated or dependency-owned files; generate supported platform distributions from shared canonical sources and verify them with platform-native validation and acceptance evidence. (default origin unknown)
- `[policy:security_privacy_compliance]` **Security, privacy, secrets, and compliance**: Repository policy may tighten but never weaken safety and authority boundaries. (default origin unknown)
- `[policy:documentation_style]` **Documentation and style**: Follow evidenced repository documentation and style conventions; use outcome-first, low-technical-detail user updates by default while allowing explicit project policy to override the style. (default origin unknown)
- `[policy:deployment_resources]` **Deployment, environment, and resources**: Do not deploy without authority; choose bounded parallelism from the deterministic tracked-file repository size. (default origin unknown)
- `[policy:engineering_rigor]` **Engineering rigor**: structured (adopted from the recorded ZzzOps default)
- `[policy:workflow_adherence]` **ZzzOps workflow adherence**: tracked (adopted from the recorded ZzzOps default)
- `[policy:autonomy_approval_parallelism]` **Autonomy, approvals, and parallelism**: Interview adaptively during goal capture at the reviewed depth; treat the requesting user as the sole stakeholder; execute unattended by persisting consequential questions as durable blockers; repair in-scope CI failures without another approval; record privacy-safe execution reports; refill valuable bounded work; and use up to three size-aware workers. (default origin unknown)
- `[policy:automated_design]` **Automated design authority**: disabled (customized from a ZzzOps default)

Detailed rationale and review history: [PROJECT_AUDIT.md](PROJECT_AUDIT.md). Canonical policy state: [POLICY.json](POLICY.json).
