# Human acceptance journey

Use this release check to experience ZzzOps as a new user would, not to repeat CI by hand. The mandatory path is one four-checkpoint journey in a disposable private GitHub repository. Target at most 20 minutes of human attention; autonomous implementation and CI wait time are excluded. If the journey exceeds that target, record the excess ceremony or repetition as UX evidence instead of silently extending the estimate.

Ask for the next test, perform only that action, and explicitly say `check UX-001` when its expected result is satisfied. Report confusion, repetition, surprising writes, or unclear next steps before marking a checkpoint. A checked checkpoint becomes stale when behavior mapped to it changes.

## What the human judges

Pay attention to whether skills are easy to discover, questions feel consequential, summaries are comprehensible, approvals and side effects are obvious, progress is proportionate, recovery guidance is actionable, and a fresh task can explain what happens next. Exact inventories, policy matrices, idempotence, file preservation, cleanup safety, and exhaustive failure cases belong to automated validation.

## Canonical setup and input

Prerequisites: a current Codex CLI, authenticated `gh`, Python 3.10 or newer for the local runner, and clean disposable Codex marketplace/plugin state. Create a new private GitHub repository with Issues enabled and a single README commit, then open Codex at its root. Do not reuse a real project or put secrets in the fixture.

Use this exact project specification when prompted:

> Bootstrap a Python 3.12 command-line application supported on Linux and Windows. Its first product milestone will print a greeting for a supplied name. Use structured engineering rigor. It has no authentication, persistence, network access, deployment target, or compatibility commitment. Establish only the proportionate agent-ready harness and leave greeting behavior unimplemented.

Accept the recommended structured policy and automatic risk escalation. Retain explicit human approval before PR merges. Routine reversible implementation choices may remain agent-led.

<!-- zzzops-acceptance-plan
{"version":2,"items":[{"id":"UX-001","title":"Install ZzzOps and begin onboarding","status":"checked","paths":[".agents/plugins/marketplace.json","plugins/zzzops/plugin.json","plugins/zzzops/skills/validate-zzzops-installation/SKILL.md","plugins/zzzops/zzzops/installation.py",".agents/skills/run-zzzops-acceptance/SKILL.md"],"surfaces":["plugins/zzzops/plugin.json",".agents/plugins/marketplace.json","plugins/zzzops/skills/validate-zzzops-installation"],"fingerprint":"4681c501d357cec775ab9a12a7138dd86cc8235acf7ee8591d53e2bbd0006fd3","notes":""},{"id":"UX-002","title":"Review policy and bootstrap the agent-ready factory","status":"checked","paths":["plugins/zzzops/skills/bootstrap-zzzops-repository/SKILL.md","plugins/zzzops/zzzops/references/bootstrap","plugins/zzzops/skills/review-zzzops-policy/SKILL.md","plugins/zzzops/rules/INITIALIZATION.md",".agents/skills/run-zzzops-acceptance/SKILL.md"],"surfaces":["plugins/zzzops/skills/bootstrap-zzzops-repository","plugins/zzzops/skills/review-zzzops-policy"],"fingerprint":"6921503c808467e592e52f385c61c6e35e182f53d4749552d68037563bb1ce06","notes":""},{"id":"UX-003","title":"Capture a realistic follow-up goal","status":"checked","paths":["plugins/zzzops/skills/add-zzzops-goal/SKILL.md","plugins/zzzops/rules/BACKENDS.md",".agents/skills/run-zzzops-acceptance/SKILL.md"],"surfaces":["plugins/zzzops/skills/add-zzzops-goal"],"fingerprint":"06c5d410a8435e47ad0d302965d5718d97d42352bb13e3780d2fedcb3c13d8ec","notes":""},{"id":"UX-004","title":"Execute, review, interrupt, and resume","status":"checked","paths":["plugins/zzzops/skills/execute-zzzops/SKILL.md","plugins/zzzops/skills/execute-zzzops/references/EXECUTE.md","plugins/zzzops/skills/execute-zzzops/references/UNBLOCK.md","plugins/zzzops/skills/execute-zzzops/references/BRANCH_REVIEW.md","plugins/zzzops/rules/GOAL_SYSTEM.md","plugins/zzzops/rules/BACKENDS.md",".agents/skills/run-zzzops-acceptance/SKILL.md"],"surfaces":["plugins/zzzops/skills/execute-zzzops"],"fingerprint":"f2db94c720c30ca0774cbe10fa30a61cbb1111cd5eae2a548573cc8c6194b6a4","notes":""}],"automated_surfaces":[{"surface":"plugins/zzzops/skills/migrate-to-zzzops","evidence":[".agents/test_zzzops.py"]},{"surface":"plugins/zzzops/skills/suggest-zzzops-work","evidence":[".agents/test_zzzops.py"]},{"surface":"plugins/zzzops/skills/review-agentic-engineering","evidence":[".agents/test_zzzops.py"]},{"surface":"plugins/zzzops/skills/send-zzzops-feedback","evidence":[".agents/test_zzzops.py"]}]}
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

Human action: invoke `execute-zzzops`. At the first human review boundary, leave the PR unapproved and end the task. Open a fresh task, invoke `execute-zzzops` again, inspect the explanation of the pending state, then approve and continue until the greeting and uppercase goals reach their next policy-permitted terminal state. Run the documented canonical verification command once at the final reviewed checkpoint.

Expected: execution prioritizes dependencies, provides proportionate progress, persists the unanswered approval without guessing, resumes from durable state in the fresh task, never merges before approval, and presents observable verification and a clear final handoff.

UX questions: Could the fresh task explain exactly where work stopped and why? Were verification evidence, approval consequences, failures, and next actions understandable? Did any repetition, latency, or ceremony make you want to bypass ZzzOps?

## Optional risk-triggered spot checks

These are not part of every human pass. Run the relevant short exploratory check when its workflow changed materially or before a release whose risk warrants it:

- Brownfield bootstrap: confirm existing architecture and agent instructions are preserved.
- TODO migration: judge preview clarity and confidence that nothing is silently omitted.
- Feedback submission: judge the exact-payload confirmation and recovery from cancellation/provider failure.
- Agent-use coaching: judge whether advice is concise, evidence-based, and aimed at the correct cause.

Run `python .agents/manual_acceptance.py coverage` to ensure every shipped surface still has either a core human checkpoint or an automated contract with present evidence. Automated CI remains authoritative for the mechanical behavior named above.
