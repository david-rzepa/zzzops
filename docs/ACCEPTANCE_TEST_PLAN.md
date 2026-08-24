# Human acceptance plan

Run this plan conversationally: ask for the next item, perform its human action, then explicitly say `check A-001`. A checked item becomes stale when one of its mapped paths changes.

This plan, the `run-zzzops-acceptance` skill, and `.agents/manual_acceptance.py` belong only to the ZzzOps base repository's maintenance and release process. The Agent Plugin contains exactly `add-zzzops-goal`, `bootstrap-zzzops-repository`, `execute-zzzops`, `migrate-to-zzzops`, `review-zzzops-policy`, `send-zzzops-feedback`, and `suggest-zzzops-work`.

Maintainers must map each shipped user-facing surface to a human item. For ZzzOps that means Codex marketplace/package behavior and the seven plugin skills. Internal control commands, backend mechanics, policy plumbing, reservations, prompt accounting, CI, documentation, and individual test cases are not separate human acceptance surfaces; inspect or automate them proportionately instead. Reusable acceptance-harness behavior needs focused regression coverage, but no human item unless the harness itself ships to users. Run `<python> .agents/manual_acceptance.py coverage` with one resolved Python 3.10 or newer interpreter to report required unmapped user surfaces without changing the plan.

<!-- zzzops-acceptance-plan
{"version":1,"items":[{"id":"A-001","title":"Codex discovers the ZzzOps marketplace package","status":"checked","paths":[".agents/plugins/marketplace.json","plugins/zzzops/plugin.json"],"fingerprint":"16e5661d44a08b415d4ddf1e7ca48b0ac61d1cf855fe03135126be12210f1381","notes":""},{"id":"A-002","title":"Codex installs and discovers the complete Agent Plugin","status":"unchecked","paths":[".agents/plugins/marketplace.json","plugins/zzzops/plugin.json","plugins/zzzops/skills"],"fingerprint":null,"notes":""},{"id":"A-003","title":"Review and initialize project policy","status":"unchecked","paths":["plugins/zzzops/skills/review-zzzops-policy/SKILL.md","plugins/zzzops/rules/INITIALIZATION.md"],"fingerprint":null,"notes":""},{"id":"A-006","title":"Migrate TODOs with approval","status":"unchecked","paths":["plugins/zzzops/skills/migrate-to-zzzops/SKILL.md","plugins/zzzops/rules/BACKENDS.md"],"fingerprint":null,"notes":""},{"id":"A-008","title":"Capture a durable goal","status":"unchecked","paths":["plugins/zzzops/skills/add-zzzops-goal/SKILL.md","plugins/zzzops/rules/BACKENDS.md"],"fingerprint":null,"notes":""},{"id":"A-009","title":"Suggest work in dry-run mode","status":"unchecked","paths":["plugins/zzzops/skills/suggest-zzzops-work/SKILL.md","plugins/zzzops/rules/BACKENDS.md"],"fingerprint":null,"notes":""},{"id":"A-010","title":"Execute goals through review and resume","status":"unchecked","paths":["plugins/zzzops/skills/execute-zzzops/SKILL.md","plugins/zzzops/skills/execute-zzzops/references/EXECUTE.md","plugins/zzzops/skills/execute-zzzops/references/UNBLOCK.md","plugins/zzzops/skills/execute-zzzops/references/BRANCH_REVIEW.md","plugins/zzzops/rules/BACKENDS.md","plugins/zzzops/rules/GOAL_SYSTEM.md"],"fingerprint":null,"notes":""},{"id":"A-011","title":"Send feedback with exact confirmation and safe report cleanup","status":"unchecked","paths":["plugins/zzzops/skills/send-zzzops-feedback/SKILL.md","plugins/zzzops/rules/FEEDBACK.md"],"fingerprint":null,"notes":""},{"id":"A-012","title":"Codex reinstalls and updates the plugin cleanly","status":"unchecked","paths":[".agents/plugins/marketplace.json","plugins/zzzops/plugin.json","plugins/zzzops/zzzops/package.py"],"fingerprint":null,"notes":""},{"id":"A-013","title":"Bootstrap a repository into an agent-ready harness","status":"unchecked","paths":["plugins/zzzops/skills/bootstrap-zzzops-repository/SKILL.md","plugins/zzzops/zzzops/references/bootstrap"],"fingerprint":null,"notes":""}]}
zzzops-acceptance-plan -->

## A-001 - Codex discovers the ZzzOps marketplace package

Prerequisite: use a current Codex CLI and a clean Codex marketplace state.

Human action: add this repository as a local marketplace with `codex plugin marketplace add . --json`, then run `codex plugin list`.

Expected: Codex reports a marketplace named `zzzops` and offers `zzzops@zzzops`; the repository worktree and project state are unchanged.

## A-002 - Codex installs and discovers the complete Agent Plugin

Prerequisite: complete A-001 in the same disposable repository.

Human action: run `codex plugin add zzzops@zzzops --json`, inspect the installed cache, then open a fresh Codex task.

Expected: the installed package contains `plugin.json`, seven skills, `rules/`, and `zzzops/`; Codex discovers the seven skills in the new task. Installation does not modify the target repository or initialize project policy.

## A-012 - Codex reinstalls and updates the plugin cleanly

Human action: remove and re-add `zzzops@zzzops`, inspect the refreshed package, and leave the local development marketplace installed.

Expected: Codex controls the cache lifecycle without target-repository changes; re-add restores a complete package, and the local development marketplace remains available for subsequent ZzzOps tasks.

## A-003 - Review and initialize project policy

Prerequisite: A-002 completed in the disposable repository.

Human action: open a fresh Codex task, invoke `review-zzzops-policy`, answer consequential setup questions, approve the proposed policy, then invoke it again.

Expected: the installed skill is discovered; it proposes overridable project defaults, including outcome-first communication, and waits for explicit approval before continuing. The second invocation re-summarizes the meaningful current policy and invites adjustments rather than reporting only that setup is complete.

## Installed skill workflows

Run each in a disposable repository and record the result in the matching ledger item.

| ID | Human action | Expected observable result |
| --- | --- | --- |
| A-006 | Preview a TODO migration, approve it, and inspect the resulting queue. | Existing TODOs are summarized before approval, then become durable GitHub goals with nothing silently omitted. |
| A-008 | Under a structured project default, capture one reversible low-risk goal and one authentication goal from similarly brief requests. | Capture uses standard depth for the first goal, escalates authentication to agentic/thorough, records auditable risk inputs rather than a derived value, asks only consequential extra questions, and creates no Git state. |
| A-009 | In dry-run mode, audit an agentic fixture lacking CI and containing a prose-only invariant, incomplete canonical verification, and unverified security-sensitive behavior. | ZzzOps credits existing harness evidence, proposes distinct evidence-backed gap goals for all four mismatches, makes no source/backlog changes, and does not add tools merely to satisfy a template. |
| A-010 | Execute comparable vibe, structured, and risk-escalated agentic fixtures through their verification and review boundaries; include an unanswered authority gate and later resume it. | Vibe may finish from policy-permitted observed behavior; structured runs targeted checks plus canonical verification; agentic requires relevant deterministic, regression, architecture, and risk evidence. Created-but-unrun checks never count, unanswered gates persist without live questions, and no PR merges before approval. |
| A-011 | With one archived synthetic report, invoke `send-zzzops-feedback` with innocuous user feedback. Inspect the exact public payload, then separately cancel, enter a wrong digest, and force one provider failure before restoring authentication and confirming the current digest. | Every preview is human-readable and labels the public issue `zzzops-feedback`. Cancellation, digest mismatch, and provider failure retain the immutable report. The successful confirmed submission creates exactly the previewed issue and deletes only its confirmed report. |
| A-013 | Invoke `bootstrap-zzzops-repository` once with the documented disposable greenfield specification and once against the brownfield fixture, then repeat both invocations. | Policy handoff resumes cleanly; evidence selects the mode; ordinary goals establish and verify the proportionate harness; eligible unstarted product goals depend on it; existing structure and policy-owned agent instructions survive brownfield reconciliation; seeded product behavior remains unimplemented; repeat runs are no-ops. |
