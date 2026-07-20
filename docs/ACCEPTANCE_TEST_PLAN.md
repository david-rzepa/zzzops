# Human acceptance plan

Run this plan conversationally: ask for the next item, perform its human action, then explicitly say `check A-001`. A checked item becomes stale when one of its mapped paths changes.

Maintainers must map each new shipped user-facing functional surface to a human item. Documentation and individual test cases are not functional surfaces and need no item solely to test their prose or test code; inspect documentation and run changed tests instead. Reusable test/acceptance harness behavior needs focused regression coverage, and needs a human item only when that harness itself exposes a shipped user-facing workflow. If a scenario cannot safely be manually tested, add an evidence-backed exemption in the item notes explaining the safety boundary and automated coverage; do not silently omit it. Run `<python> .agents/manual_acceptance.py coverage` with one resolved Python 3 interpreter to report required unmapped surfaces without changing the plan.

<!-- zzzops-acceptance-plan
{"version":1,"items":[{"id":"A-001","title":"Install preview is non-mutating","status":"unchecked","paths":[".agents/skills/install-zzzops/scripts/install_zzzops.py"],"fingerprint":null,"notes":""},{"id":"A-002","title":"Execute workflow is discoverable","status":"unchecked","paths":[".agents/skills/execute-zzzops/SKILL.md"],"fingerprint":null,"notes":""},{"id":"A-003","title":"Preferences CLI preserves local choices","status":"unchecked","paths":[".agents/zzzops.py",".agents/templates/project-goals/PREFERENCES.json"],"fingerprint":null,"notes":""},{"id":"A-004","title":"Agent-led project initialization","status":"unchecked","paths":[".zzzops/rules/INITIALIZATION.md",".agents/zzzops.py"],"fingerprint":null,"notes":""},{"id":"A-005","title":"GitHub Issues backend","status":"unchecked","paths":[".zzzops/rules/BACKENDS.md"],"fingerprint":null,"notes":""},{"id":"A-007","title":"Capture a durable goal","status":"unchecked","paths":[".agents/skills/add-zzzops-goal/SKILL.md"],"fingerprint":null,"notes":""},{"id":"A-008","title":"Migrate TODOs with approval","status":"unchecked","paths":[".agents/skills/migrate-to-zzzops/SKILL.md"],"fingerprint":null,"notes":""},{"id":"A-009","title":"Suggest work in dry-run mode","status":"unchecked","paths":[".agents/skills/suggest-zzzops-work/SKILL.md"],"fingerprint":null,"notes":""},{"id":"A-010","title":"Execute, unblock, watch, and resume","status":"unchecked","paths":[".agents/skills/execute-zzzops/SKILL.md",".agents/skills/execute-zzzops/references/EXECUTE.md",".agents/skills/execute-zzzops/references/UNBLOCK.md",".zzzops/rules/BLOCKERS.md",".zzzops/rules/CONTINUATION.md",".zzzops/rules/EXECUTION_STRATEGY.md"],"fingerprint":null,"notes":""},{"id":"A-011","title":"Branch review and merge gate","status":"unchecked","paths":[".agents/skills/execute-zzzops/references/BRANCH_REVIEW.md"],"fingerprint":null,"notes":""},{"id":"A-012","title":"Concurrent goal reservation","status":"unchecked","paths":[".agents/zzzops.py",".zzzops/rules/GOAL_SYSTEM.md",".zzzops/rules/BACKENDS.md"],"fingerprint":null,"notes":""},{"id":"A-013","title":"Prompt budget is current","status":"unchecked","paths":[".agents/prompt_stats.py"],"fingerprint":null,"notes":""},{"id":"A-014","title":"PR validation and release boundaries","status":"unchecked","paths":[".github/workflows"],"fingerprint":null,"notes":""}]}
zzzops-acceptance-plan -->

## A-001 — Install preview is non-mutating

Prerequisite: use a disposable Git repository.

Human action: ask the installed `install-zzzops` skill for a dry run, then inspect Git status.

Expected: it explains the skills, workflow rules/control CLI, and blank setup templates it would install; identifies any conflict requiring action; binds apply to that exact preview; and changes nothing.

## A-002 — Execute workflow is discoverable

Prerequisite: mechanics installed in a disposable repository.

Human action: open a fresh Codex or Claude Code session and invoke `execute-zzzops` in dry-run mode.

Expected: it reports the durable queue without source or Git changes.

## A-003 — Preferences CLI preserves local choices

Prerequisite: initialized disposable repository with ZzzOps mechanics installed.

Human action: run `<python> .agents/zzzops.py` with the resolved Python 3 interpreter, change one refill preference, exit, then reopen the panel.

Expected: the selected preference remains user-local in `.zzzops/PREFERENCES.json`; it is not staged or committed.

## A-004 to A-014 — Core ZzzOps workflow coverage

Run each in a disposable repository and record the result in the matching ledger item.

| ID | Human action | Expected observable result |
| --- | --- | --- |
| A-004 | Start a non-install workflow and review the generated `PROJECT.md`. | The agent interviews consequential unknowns, proposes outcome-first communication as an overridable default, and waits for explicit policy review. |
| A-005 | Initialize with GitHub Issues selected. | A human-first issue is the canonical goal; repository visibility is explained. |
| A-007 | Capture a small goal. | It is durable but creates no branch, commit, or PR. |
| A-008 | Preview a TODO migration, then inspect the plan. | Existing TODOs are summarized; no goal is created before approval. |
| A-009 | Run work suggestion in dry-run mode. | Evidence-backed suggestions are shown without changing the backlog. |
| A-010 | Exhaust the queue on one merge-ready PR, merge it during the announced watch, and repeat once without a wait-capable surface. | The agent asks for one clear action without narrating polling mechanics, observes and resumes once; unsupported waiting hands off plainly with the blocker intact. |
| A-011 | Complete a source-changing test goal. | The agent says the change is ready, provides the review action/link, and does not expose internal hashes or merge without authority. |
| A-012 | Have two runs contend for one goal, then two different goals contend for one declared resource; repeat with distinct resources and after expiry. | Each overlap has one bundle winner, losers reselect, distinct work proceeds, only owners renew/release, and expiry cannot delete a replacement. |
| A-013 | Run prompt statistics and its check mode. | The byte/token estimate is deterministic and check mode succeeds. |
| A-014 | Open a PR and inspect its validation/release behavior. | PR checks are read-only; `main` release behavior remains restricted. |
