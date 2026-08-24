# Goal branches and review

## Workflow adherence

Reviewed workflow adherence controls how agent work reaches this execution loop; it is distinct from the rigor used to specify and verify that work.

- `optional`: ZzzOps is available, but direct agent work is allowed.
- `tracked`: substantial repository-changing agent work requires a durable goal, while otherwise-authorized implementation may run outside `$execute-zzzops`.
- `managed`: repository-changing agent work uses the appropriate ZzzOps workflow, and tracked implementation runs through `$execute-zzzops`.

Read-only investigation and ZzzOps administration are exempt. A user may authorize a narrowly scoped exception explicitly, but no adherence level weakens safety or other reviewed policy. Confirmation projects the reviewed level into a bounded `AGENTS.md` block. Repository-specific PR or CI checks may add deterministic enforcement when they can observe the contract; ZzzOps cannot observe or control direct human edits and does not promise a universal gate.

Branch/review behavior is project policy, proposed during initialization from repository evidence. The first-release fallback uses one branch per source-changing goal, bases independent goals on the nearest authorized trunk, and waits for every dependency to be complete before writable implementation begins. Read-only agents may investigate later goals in advance without claiming, editing, branching, or marking them started. Repositories can replace this fallback through reviewed `git_review_release` settings, including explicitly allowing review-ready branch stacking.

Where pull requests are supported, the fallback also uses one PR per source-changing goal. Being small, related, or selected in one run is not enough to bundle goals. Repository policy or an explicit user instruction may permit a shared PR, but every affected goal records the override, rationale, shared branch/PR, target, and review consequence before work is combined. Parent and child goals retain separate PRs targeting their resolved pseudo-trunks. PR granularity is independent of commit/squash policy, and capture-only goal creation remains Git-free.

| Scenario | Base | Integration target |
| --- | --- | --- |
| Independent root goal | Nearest authorized trunk | Repository-policy target |
| Dependent goal after dependencies complete | Nearest authorized trunk containing dependencies | Repository-policy target containing dependencies |
| Direct child | Parent pseudo-trunk | Parent pseudo-trunk |
| Child with sibling dependency | Sibling dependency branch | Nearest parent pseudo-trunk |
| Multiple dependencies | Reviewed base containing all | Nearest authorized target |

Canonical goal state records branch/base/target/PR and review checkpoint. After implementation, automated checks, and self-review, source work gets a `human-action` blocker rather than `done`. PR-required repositories need valid UI approval and required checks; otherwise explicit conversational approval is allowed. Requested changes reuse the branch and create a new verified checkpoint. After approval, the agent merges only with authority, verifies the target, resolves the blocker, and completes the goal.

The workflow remains agent-driven. ZzzOps deliberately has no universal branch-management script: repository instructions, hosting rules, dependency ancestry, dirty state, and merge authority require contextual inspection.

## Continuation after capture

Execute-all intent may remain active across a same-task yield or queue-exhausted handoff. If the next turn merely captures unrelated work, ZzzOps completes that capture and re-enters ordinary inventory once, so the new goal joins the queue without jumping it. Explicit stop, pause, replacement, capture-only wording, authority/blocker boundaries, or loss of a trustworthy same-task signal wins. Time proximity alone is never evidence; separate tasks and unsupported harnesses do not share intent.

Goal capture uses the project policy's adaptive requirements-interview depth before creating the canonical issue. The default `standard` depth establishes outcome and observable acceptance, checks scope, and explores constraints, dependencies, risks, authority, or verification only when they can materially change the goal. It treats the requesting user as the requirements and acceptance owner; multi-party stakeholder discovery is outside this behavior.

Execution assumes no user is present. It never pauses to ask an interactive question: consequential unknowns, including authority and safety gates, are recorded as categorized issue blockers with recommendations and recheck triggers. Independent goals continue, and the durable blocker queue is summarized at handoff.

## Adaptive discovery of unknowns

ZzzOps treats uncertainty reduction as an adaptive lifecycle concern, not a mandatory phase. Capture and preparation run a bounded blind-spot pass only when unfamiliarity or a change-sensitive decision could materially affect architecture, scope, acceptance, or the quality bar. The pass identifies known unknowns, tacit criteria, and plausible blind spots, then chooses the cheapest useful evidence source or experiment. Execution preserves only material assumptions, constraints, and plan deviations in goal history. Review handoffs explain consequential decisions and remaining unknowns, adding comprehension checks only when they materially improve safe approval.

The patterns from Anthropic's [field guide to finding unknowns](https://claude.com/blog/a-field-guide-to-claude-fable-finding-your-unknowns) map to shipped behavior as follows:

| Pattern | Disposition | ZzzOps behavior |
| --- | --- | --- |
| Blind-spot pass | Adopt | Trigger boundedly from evidenced unfamiliarity or decision risk; return actionable questions, risks, references, or experiments. |
| Brainstorms and prototypes | Adapt | Use bounded alternatives or disposable prototypes only when tacit criteria or feasibility could change the implementation. |
| Interviews | Already satisfied | Capture interviews adapt to reviewed depth; unattended execution records blockers and never requests a live interview. |
| References | Adopt | Prefer source, schemas, tests, fixtures, and other high-fidelity references over duplicated prose when they encode semantics better. |
| Implementation plans | Adapt | Foreground data models, interfaces, architecture, and user-visible decisions; subordinate trusted mechanical steps. |
| Implementation notes | Adapt | Append material assumptions, constraints, and deviations to durable goal history instead of requiring a temporary notes file. |
| Pitches and explainers | Adopt | Completion handoffs explain consequential behavior, trade-offs, remaining unknowns, and non-obvious failure modes. |
| Quizzes | Adapt | Add a few high-value comprehension checks only when reviewer understanding materially affects approval; never replace verification or review gates. |

## Completion self-review

Before human review or completion, the agent reviews the actual goal diff, criteria, tests, and relevant surroundings. It removes only in-scope dead code proven obsolete by the implementation, retains uncertain dynamic/generated/vendor or unrelated paths, fixes findings in observable chunks, reruns affected and relevant wider checks, and records either findings or a clean review. The pass does not authorize repository-wide cleanup or unrelated bug fixes.
