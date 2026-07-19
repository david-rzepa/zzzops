# Human acceptance plan

Run this plan conversationally: ask for the next item, perform its human action, then explicitly say `check A-001`. A checked item becomes stale when one of its mapped paths changes.

Maintainers must map each new functional surface to a human item. If a scenario cannot safely be manually tested, add an evidence-backed exemption in the item notes explaining the safety boundary and automated coverage; do not silently omit it. Run `python .agents/manual_acceptance.py coverage` to report required unmapped surfaces without changing the plan.

<!-- zzzops-acceptance-plan
{"version":1,"items":[{"id":"A-001","title":"Install preview is non-mutating","status":"unchecked","paths":[".agents/skills/install-zzzops/scripts/install_zzzops.py"],"fingerprint":null,"notes":""},{"id":"A-002","title":"Execute workflow is discoverable","status":"unchecked","paths":[".agents/skills/execute-zzzops/SKILL.md"],"fingerprint":null,"notes":""},{"id":"A-003","title":"Preferences CLI preserves local choices","status":"unchecked","paths":[".agents/zzzops.py",".agents/templates/project-goals/PREFERENCES.json"],"fingerprint":null,"notes":""},{"id":"A-004","title":"Agent-led project initialization","status":"unchecked","paths":[".zzzops/rules/INITIALIZATION.md",".agents/zzzops.py"],"fingerprint":null,"notes":""},{"id":"A-005","title":"GitHub Issues backend","status":"unchecked","paths":[".zzzops/rules/BACKENDS.md"],"fingerprint":null,"notes":""},{"id":"A-006","title":"Local-files backend","status":"unchecked","paths":[".zzzops/rules/BACKENDS.md"],"fingerprint":null,"notes":""},{"id":"A-007","title":"Capture a durable goal","status":"unchecked","paths":[".agents/skills/add-zzzops-goal/SKILL.md"],"fingerprint":null,"notes":""},{"id":"A-008","title":"Migrate TODOs with approval","status":"unchecked","paths":[".agents/skills/migrate-zzzops-todos/SKILL.md"],"fingerprint":null,"notes":""},{"id":"A-009","title":"Suggest work in dry-run mode","status":"unchecked","paths":[".agents/skills/suggest-zzzops-work/SKILL.md"],"fingerprint":null,"notes":""},{"id":"A-010","title":"Execute, unblock, and resume","status":"unchecked","paths":[".agents/skills/execute-zzzops/SKILL.md",".zzzops/rules/CONTINUATION.md"],"fingerprint":null,"notes":""},{"id":"A-011","title":"Branch review and merge gate","status":"unchecked","paths":[".agents/skills/execute-zzzops/references/BRANCH_REVIEW.md"],"fingerprint":null,"notes":""},{"id":"A-013","title":"Prompt budget is current","status":"unchecked","paths":[".agents/prompt_stats.py","README.md"],"fingerprint":null,"notes":""},{"id":"A-014","title":"PR validation and release boundaries","status":"unchecked","paths":[".github/workflows"],"fingerprint":null,"notes":""}]}
zzzops-acceptance-plan -->

## A-001 — Install preview is non-mutating

Prerequisite: use a disposable Git repository.

Human action: ask the installed `install-zzzops` skill for a dry run, then inspect Git status.

Expected: it reports a plan and does not create mechanics or alter project state.

## A-002 — Execute workflow is discoverable

Prerequisite: mechanics installed in a disposable repository.

Human action: open a fresh Codex or Claude Code session and invoke `execute-zzzops` in dry-run mode.

Expected: it reports the durable queue without source or Git changes.

## A-003 — Preferences CLI preserves local choices

Prerequisite: initialized disposable repository with ZzzOps mechanics installed.

Human action: run `python .agents/zzzops.py`, change one refill preference, exit, then reopen the panel.

Expected: the selected preference remains user-local in `.zzzops/PREFERENCES.json`; it is not staged or committed.

## A-004 to A-014 — Core ZzzOps workflow coverage

Run each in a disposable repository and record the result in the matching ledger item.

| ID | Human action | Expected observable result |
| --- | --- | --- |
| A-004 | Start a non-install workflow and review the generated `PROJECT.md`. | The agent interviews consequential unknowns; ordinary work waits for explicit policy review. |
| A-005 | Initialize with GitHub Issues selected. | A human-first issue is the canonical goal; repository visibility is explained. |
| A-006 | Initialize with local files selected. | Canonical goal files and derived index are used without GitHub writes. |
| A-007 | Capture a small goal. | It is durable but creates no branch, commit, or PR. |
| A-008 | Preview a TODO migration, then inspect the plan. | Existing TODOs are summarized; no goal is created before approval. |
| A-009 | Run work suggestion in dry-run mode. | Evidence-backed suggestions are shown without changing the backlog. |
| A-010 | Execute a simple goal, answer one blocker, and resume. | The loop preserves state and resumes only safe same-task work. |
| A-011 | Complete a source-changing test goal. | A branch/PR/check/review gate is presented; no merge occurs without authority. |
| A-013 | Run prompt statistics and its check mode. | README counts regenerate deterministically and check succeeds. |
| A-014 | Open a PR and inspect its validation/release behavior. | PR checks are read-only; `main` release behavior remains restricted. |
