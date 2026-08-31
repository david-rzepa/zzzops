# Human acceptance journey

Use this release check to experience ZzzOps as a new user would, not to repeat CI by hand. The mandatory path is one four-checkpoint journey in a disposable private GitHub repository. Target at most 20 minutes of human attention; autonomous implementation and CI wait time are excluded. If the journey exceeds that target, record the excess ceremony or repetition as UX evidence instead of silently extending the estimate.

Ask for the next test, perform only that action, and explicitly say `check UX-001` when its expected result is satisfied. Report confusion, repetition, surprising writes, or unclear next steps before marking a checkpoint. A checked checkpoint becomes stale when behavior mapped to it changes.

## What the human judges

Pay attention to whether skills are easy to discover, questions feel consequential, summaries are comprehensible, approvals and side effects are obvious, progress is proportionate, recovery guidance is actionable, and a fresh task can explain what happens next. Exact inventories, policy matrices, idempotence, file preservation, and exhaustive failure cases belong to automated validation. The delegation spot check judges whether worker use, fallback, authority, and cleanup are visible and trustworthy; automation remains responsible for exhaustive cleanup safety.

## Canonical setup and input

Prerequisites: a current Codex CLI, authenticated `gh`, Python 3.10 or newer for the local runner, and clean disposable Codex marketplace/plugin state. Create a new private GitHub repository with Issues enabled and a single README commit, then open Codex at its root. Do not reuse a real project or put secrets in the fixture.

Use this exact project specification when prompted:

> Bootstrap a Python 3.12 command-line application supported on Linux and Windows. Its first product milestone will print a greeting for a supplied name. Use structured engineering rigor. It has no authentication, persistence, network access, deployment target, or compatibility commitment. Establish only the proportionate agent-ready harness and leave greeting behavior unimplemented.

Accept the recommended structured policy and automatic risk escalation. Retain explicit human approval before PR merges. Routine reversible implementation choices may remain agent-led.

<!-- zzzops-acceptance-plan
{"version":2,"items":[{"id":"UX-001","title":"Install ZzzOps and begin onboarding","status":"unchecked","paths":[".agents/plugins/marketplace.json","plugins/zzzops/plugin.json","plugins/zzzops/skills/validate-zzzops-installation/SKILL.md","plugins/zzzops/zzzops/installation.py",".agents/skills/run-zzzops-acceptance/SKILL.md"],"surfaces":["plugins/zzzops/plugin.json",".agents/plugins/marketplace.json","plugins/zzzops/skills/validate-zzzops-installation"],"fingerprint":null,"notes":"The shared acceptance runner changed; rerun this checkpoint before release."},{"id":"UX-002","title":"Review policy and bootstrap the agent-ready factory","status":"unchecked","paths":["plugins/zzzops/skills/bootstrap-zzzops-repository/SKILL.md","plugins/zzzops/zzzops/references/bootstrap","plugins/zzzops/skills/review-zzzops-policy/SKILL.md","plugins/zzzops/rules/INITIALIZATION.md",".agents/skills/run-zzzops-acceptance/SKILL.md"],"surfaces":["plugins/zzzops/skills/bootstrap-zzzops-repository","plugins/zzzops/skills/review-zzzops-policy"],"fingerprint":null,"notes":"The shared acceptance runner changed; rerun this checkpoint before release."},{"id":"UX-003","title":"Capture a realistic follow-up goal","status":"unchecked","paths":["plugins/zzzops/skills/add-zzzops-goal/SKILL.md","plugins/zzzops/rules/BACKENDS.md",".agents/skills/run-zzzops-acceptance/SKILL.md"],"surfaces":["plugins/zzzops/skills/add-zzzops-goal"],"fingerprint":null,"notes":"The shared acceptance runner changed; rerun this checkpoint before release."},{"id":"UX-004","title":"Execute, review, interrupt, and resume","status":"unchecked","paths":["plugins/zzzops/skills/execute-zzzops/SKILL.md","plugins/zzzops/skills/execute-zzzops/references/EXECUTE.md","plugins/zzzops/skills/execute-zzzops/references/UNBLOCK.md","plugins/zzzops/skills/execute-zzzops/references/BRANCH_REVIEW.md","plugins/zzzops/skills/execute-zzzops/references/REVIEW_QUEUE.md","plugins/zzzops/skills/execute-zzzops/references/ENTROPY_OBSERVATIONS.md","plugins/zzzops/skills/review-zzzops-entropy/SKILL.md","plugins/zzzops/skills/review-zzzops-entropy/references/RECENT.md","plugins/zzzops/skills/review-zzzops-entropy/references/FULL.md","plugins/zzzops/skills/suggest-zzzops-work/SKILL.md","plugins/zzzops/zzzops/entropy.py","plugins/zzzops/zzzops/entropy_review.py","plugins/zzzops/rules/GOAL_SYSTEM.md","plugins/zzzops/rules/BACKENDS.md","plugins/zzzops/rules/DELEGATION.md","plugins/zzzops/rules/EXECUTION_STRATEGY.md",".agents/skills/run-zzzops-acceptance/SKILL.md",".agents/test_zzzops.py","docs/EXECUTION.md","docs/ADVANCED.md","docs/SKILLS.md"],"surfaces":["plugins/zzzops/skills/execute-zzzops","plugins/zzzops/skills/review-zzzops-entropy"],"automated_evidence":[{"scenario":"interruption, changed-head drift, exact coverage, and loop prevention","path":".agents/test_zzzops.py","tests":["EntropyModuleTests.test_entropy_review_exact_lifecycle_is_idempotent_and_changed_heads_stay_due","EntropyModuleTests.test_entropy_review_rejects_stale_completion_and_malformed_state","WorkflowContractTests.test_execute_entropy_protocol_is_closed_ordered_and_runtime_backed"]}],"fingerprint":null,"notes":"Delegation and entropy-review contracts changed; deterministic drift mechanics pass, but rerun UX-004 for supported-host behavior before release."}],"automated_surfaces":[{"surface":"plugins/zzzops/skills/migrate-to-zzzops","evidence":[".agents/test_zzzops.py"]},{"surface":"plugins/zzzops/skills/suggest-zzzops-work","evidence":[".agents/test_zzzops.py"]},{"surface":"plugins/zzzops/skills/review-agentic-engineering","evidence":[".agents/test_zzzops.py"]},{"surface":"plugins/zzzops/skills/send-zzzops-feedback","evidence":[".agents/test_zzzops.py"]}]}
zzzops-acceptance-plan -->

## UX-001 — Install ZzzOps and begin onboarding

Prerequisite: complete the canonical setup through creation of the disposable repository.

Human action: add this checkout as a local Codex marketplace, install or refresh `zzzops@zzzops`, open a fresh Codex task in the disposable repository, and invoke `bootstrap-zzzops-repository` with the canonical specification above.

Expected: Codex discovers the release-candidate plugin; first-use installation validation runs once if required and resumes bootstrap; no legacy cleanup or repository change occurs without a specific preview and confirmation.

UX questions: Was the correct plugin/version obvious? Did the transition from installation validation into bootstrap feel continuous? Were side effects and any confirmation request understandable?

## UX-002 — Review policy and bootstrap the agent-ready factory

Prerequisite: continue the same bootstrap invocation from UX-001.

Human action: answer only consequential policy or architecture questions using the canonical answers, approve the concise policy/harness proposal, and allow bootstrap to create and execute its ordinary harness goals. Approve exact reviewed PR checkpoints as requested until bootstrap reports the harness complete.

Expected: ZzzOps classifies the empty repository as greenfield, avoids irrelevant enterprise questions, creates a proportionate verified harness through ordinary goals, and leaves the greeting milestone unimplemented and dependent on that harness. The canonical verification command actually passes, CI uses the same contract, and a repeated bootstrap invocation is a no-op.

UX questions: Did every question earn the interruption? Could you understand the proposed architecture, goal DAG, progress, review boundaries, and final handoff without reading internal machinery? Did the number of approvals or amount of ceremony feel disproportionate?

## UX-003 — Capture a realistic follow-up goal

Prerequisite: the bootstrap harness and its review gates from UX-002 are complete.

Human action: invoke `add-zzzops-goal` with: `Add an optional --uppercase flag to the greeting command; when supplied, the complete greeting is uppercase.` Answer only consequential clarification and accept the proposed goal.

Expected: capture recognizes the relationship to the seeded greeting milestone, produces observable examples and scope without an exhaustive interview, creates one durable goal, and makes no Git change.

UX questions: Were the questions and examples useful? Was the relationship to existing work obvious? Did the final goal accurately express intent without feeling like a form-filling exercise?

## UX-004 — Execute, review, interrupt, and resume

Prerequisite: UX-003 is complete and no task is holding an unrecorded user decision.

Human action: first add and commit one clearly marked stale README sentence that contradicts the fixture's Python 3.12 support policy. Treat it as a bounded out-of-scope observation for this test; do not ask ZzzOps to repair it. Invoke `execute-zzzops` and stop the task as soon as automatic recent-review activity begins. If completion appears before the stop takes effect, finish one additional bounded goal to create a new exact batch and retry the interruption once; record that timing as UX evidence. Open a fresh task and invoke execution again: confirm the interrupted exact batch remains due, the README lead is visibly validated rather than silently repaired, and review finishes before any refill action or final PR review queue. Allow the reviewed refill to capture fixed eligible findings. Confirm creation occurs only after the successful review receipt, creates no more than the reviewed cap, uses only allowed categories with `zzzops-refill` provenance, and makes no source edit. Leave the resulting PR unapproved and end the task. Open one more fresh task, resume, approve, and continue until the greeting and uppercase goals reach their next policy-permitted terminal state. Confirm execution does not review that covered batch again or run a second refill. Run the documented canonical verification command once at the final reviewed checkpoint.

At the final stable state, add and commit a second clearly marked stale documentation fact. Invoke `$review-zzzops-entropy full` without `apply` or `complete` wording and confirm the repository-wide preview makes no write. Then explicitly invoke `$review-zzzops-entropy full apply` and authorize capture of only that fixed documentation finding. Confirm it creates exactly one category-eligible ordinary goal, creates no source change, and does not advance review coverage merely because apply ran.

Expected: execution prioritizes dependencies, provides proportionate progress, persists interrupted review and unanswered approval without guessing, resumes from durable state, and never merges before approval. Recent review clearly reports the exact scope and either findings or an explicit no-findings result before refill and handoff; interruption or the linked automated head/revision drift evidence leaves that batch due with an actionable recovery path. The bounded inbox fact grants no authority or goal by itself: any resulting goal appears only after a successful receipt and through reviewed category, cap, and refill authority. Repeated exhaustion at a covered frontier is a cheap no-op. The final full review is explicitly repository-wide and defaults to a read-only preview with no goal, source, or coverage write; its later explicit apply is separately bounded to the authorized fixed finding.

UX questions: Could the fresh task explain exactly where work stopped and why? Was the difference between recent and full scope obvious? Could you tell interruption left the batch due, the inbox fact granted no authority, and review occurred before refill and PR handoff? Did resume avoid repeating completed review or refill? Were verification evidence, approval consequences, failures, and next actions understandable? Did any repetition, latency, or ceremony make you want to bypass ZzzOps?

## Optional risk-triggered spot checks

These are not part of every human pass. Run the relevant short exploratory check when its workflow changed materially or before a release whose risk warrants it:

- Brownfield bootstrap: confirm existing architecture and agent instructions are preserved.
- TODO migration: judge preview clarity and confidence that nothing is silently omitted.
- Feedback submission: judge the exact-payload confirmation and recovery from cancellation/provider failure.
- Agent-use coaching: judge whether advice is concise, evidence-based, and aimed at the correct cause.
- Delegation (required when the delegation contract changes): provide two independent bounded read-only investigations. When the host exposes workers, record the eligible task IDs, visible worker IDs/status, dispatched count versus reviewed capacity, coordinator-only mutations and communication, concise evidence summaries, and cleanup state—not worker transcripts. If workers or capacity are unavailable, finish sequentially, record the fixed fallback reason, and do not claim delegation occurred. A writable variant runs only under reviewed worktree mode with disjoint resources: workers stay inside assigned worktrees, the coordinator alone claims and integrates, and every tree is removed or verified clean for reuse.

Run `python .agents/manual_acceptance.py coverage` to ensure every shipped surface still has either a core human checkpoint or an automated contract with present evidence. Automated CI remains authoritative for the mechanical behavior named above.
