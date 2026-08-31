# Goal branches and review

## Workflow adherence

Reviewed workflow adherence controls how agent work reaches this execution loop; it is distinct from the rigor used to specify and verify that work.

- `optional`: ZzzOps is available, but direct agent work is allowed.
- `tracked`: substantial repository-changing agent work requires a durable goal, while otherwise-authorized implementation may run outside `$execute-zzzops`.
- `managed`: repository-changing agent work uses the appropriate ZzzOps workflow, and tracked implementation runs through `$execute-zzzops`.

Read-only investigation and ZzzOps administration are exempt. A user may authorize a narrowly scoped exception explicitly, but no adherence level weakens safety or other reviewed policy. `$review-zzzops-policy` reflects the approved level in a bounded `AGENTS.md` block while preserving other instructions. This is guidance for agents; ZzzOps cannot observe or control direct human edits and does not promise a universal gate.

Branch/review behavior is project policy, proposed during initialization from repository evidence. The shipped default uses one branch and PR per source-changing goal, bases independent goals on the nearest authorized trunk, and lets descendants continue from a dependency's exact verified review checkpoint. Review is presented when safe work is exhausted, without conversational approval prompts between goals. Policy review foregrounds this choice; repositories may instead require immediate per-goal review and completed dependencies before descendant writes. Read-only agents may still investigate later goals in advance without claiming, editing, branching, or marking them started.

Where pull requests are supported, the fallback also uses one PR per source-changing goal. Being small, related, or selected in one run is not enough to bundle goals. Repository policy or an explicit user instruction may permit a shared PR, but every affected goal records the override, rationale, shared branch/PR, target, and review consequence before work is combined. Parent and child goals retain separate PRs targeting their resolved pseudo-trunks. PR granularity is independent of commit/squash policy, and capture-only goal creation remains Git-free.

| Scenario | Base | Integration target |
| --- | --- | --- |
| Independent root goal | Nearest authorized trunk | Repository-policy target |
| Dependent goal after dependencies complete | Nearest authorized trunk containing dependencies | Repository-policy target containing dependencies |
| Direct child | Parent pseudo-trunk | Parent pseudo-trunk |
| Child with sibling dependency | Sibling dependency branch | Nearest parent pseudo-trunk |
| Multiple dependencies | Reviewed base containing all | Nearest authorized target |

Canonical goal state records branch/base/target/PR and review checkpoint. After implementation, automated checks, and self-review, one transition sets the goal to `blocked`, clears its claim, records the exact pending checkpoint plus a `human-action` blocker, and releases its reservation. The portfolio defensively projects any complete legacy pending checkpoint as `wait_human`, never writable, while permitted descendants may still continue from that immutable base. Under the default exhaustion gate, execution eventually presents one concise PR queue in dependency and merge order. The PR review UI—not commands such as “approve goal 1”—is the approval surface. Checks, merge authority, release policy, and dependency integration order remain mandatory.

Requested changes reuse the affected branch and create a new verified checkpoint. When an ancestor changes, execution pauses only its affected descendants, invalidates their stale checkpoints and approvals, retargets or rebases exclusively owned unintegrated branches in dependency order, recomputes every immediate-base diff, and reruns the relevant probes and required checks. Unsafe or unauthorized reconciliation blocks that chain while unrelated work continues. After approval, the agent merges only with authority, verifies the target, resolves the blocker, and completes the goal.

Native stacks use GitHub's atomic asynchronous merge after every layer passes its exact-head, check, feedback, review, mergeability, and authority gates. If a repository rule rejects that operation, execution preserves the stack and reports the action needed. Only explicit administrator-bypass authority for that exact stack permits the non-atomic fallback: disclose that native stack metadata will be removed, re-read immutable provider state, unstack, then merge bottom-to-top while verifying and recording each result. A partial failure stops remaining layers with a recoverable next action; bypass never excuses a failed or pending check, changed head, unresolved feedback, or safety/release gate.

The workflow remains agent-driven. ZzzOps deliberately has no universal branch-management script: repository instructions, hosting rules, dependency ancestry, dirty state, and merge authority require contextual inspection.

## Delegation and sequential fallback

Agents delegate when there are at least two independent bounded tasks, or one clearly beneficial long or context-heavy isolated task, capped by eligible work and reviewed worker capacity. Safety or authority boundaries, dependency/resource conflict, unavailable capability, tight coupling, trivial scope, and measured setup or synthesis overhead are fixed reasons to stay sequential. No workers is a normal fallback: complete the work sequentially, record the reason where the task reports its execution decision, and never claim delegation occurred.

The coordinator alone owns canonical goal state, claims and reservations, integration, consequential decisions, external writes, approvals, and user communication. Read-only workers do not edit, install, or mutate Git or shared systems. Writable workers require reviewed worktree mode, disjoint assigned resources, and an isolated tree; the coordinator validates and integrates their result. A tree is removed after use or explicitly verified clean and reset for safe reuse.

Workers return concise evidence-linked facts, risks, and discoveries rather than transcripts. The coordinator independently checks the relevant evidence and synthesizes the result. Delegation is not a promise of speed: conflict, trivial work, or setup and synthesis overhead can make the sequential path the correct one.

## Continuation after capture

Execute-all intent may remain active across a same-task yield or queue-exhausted handoff. If the next turn merely captures unrelated work, ZzzOps completes that capture and re-enters ordinary inventory once, so the new goal joins the queue without jumping it. Explicit stop, pause, replacement, capture-only wording, authority/blocker boundaries, or loss of a trustworthy same-task signal wins. Time proximity alone is never evidence; separate tasks and unsupported harnesses do not share intent.

Goal capture uses the project policy's adaptive requirements-interview depth before creating the canonical issue. The default `standard` depth establishes outcome and observable acceptance, checks scope, and explores constraints, dependencies, risks, authority, or verification only when they can materially change the goal. It treats the requesting user as the requirements and acceptance owner; multi-party stakeholder discovery is outside this behavior.

Engineering rigor supplies that depth rather than adding a second quality knob. Capture records evidenced risk categories and any authorized override; the portfolio derives the effective level and maps `vibe`, `structured`, and `agentic` to `light`, `standard`, and `thorough`. Authentication or payment work can therefore escalate a structured project goal to agentic without changing the project default, while an unknown risk label or forbidden downgrade blocks instead of silently lowering the bar. Legacy reviewed policies retain their existing capture depth until reconciled.

The same effective level controls completion. Vibe work may rely on observed behavior where policy permits. Structured work requires observable acceptance, targeted automation, and the repository's canonical verification contract. Agentic work additionally requires every relevant deterministic gate, regression check, architectural constraint, and security, data, recovery, or operations signal. Checks must be run and observed; merely adding CI or a verification script is not evidence. Work suggestion compares those declared expectations with the real harness and proposes evidenced gap-closing goals rather than editing the repository silently.

## Incidental entropy observations

Ordinary execution never schedules a broad entropy review. When work already exposes concrete repository decay outside the current goal—such as stale context, a repeated pattern, an obsolete prose-only guardrail, or verification drift—the agent may record one compact evidence fact and one to four relevant paths. It must not pause implementation to search for observations or design future work.

The inbox lives under the repository's common Git directory, so worktrees share it and plugin upgrades do not erase it. Each observation is an atomically created, fingerprint-named file, so concurrent duplicates collapse without a global counter or lock. Every `$suggest-zzzops-work` invocation checks observations permitted by the existing refill `allowed_categories` policy and validates them against the current repository. Shipped drafts offer documentation, tests, non-behavioral code quality, and agent observability; existing projects keep their reviewed list until they explicitly opt into a new category.

Stale or duplicate observations are dismissed. Supported observations remain through dry-run preview and are consumed only after an ordinary goal is confirmed. The inbox is not a second backlog, health score, automatic repair mechanism, or grant of goal-write authority. A user can request a wider repository entropy review through `$suggest-zzzops-work` without another skill or setting.

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
