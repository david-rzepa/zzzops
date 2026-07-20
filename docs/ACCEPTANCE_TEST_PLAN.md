# Human acceptance plan

Run this plan conversationally: ask for the next item, perform its human action, then explicitly say `check A-001`. A checked item becomes stale when one of its mapped paths changes.

Maintainers must map each shipped user-facing surface to a human item. For ZzzOps that means only the native installer CLI modes and installed skills. Internal control commands, backend mechanics, policy plumbing, reservations, prompt accounting, CI, documentation, and individual test cases are not separate human acceptance surfaces; inspect or automate them proportionately instead. Reusable acceptance-harness behavior needs focused regression coverage, but no human item unless the harness itself ships to users. Run `<python> .agents/manual_acceptance.py coverage` with one resolved Python 3 interpreter to report required unmapped user surfaces without changing the plan.

<!-- zzzops-acceptance-plan
{"version":1,"items":[{"id":"A-001","title":"Native install preview is non-mutating","status":"unchecked","paths":["install.ps1","install.sh"],"fingerprint":null,"notes":""},{"id":"A-002","title":"Native installer confirms and applies once","status":"unchecked","paths":["install.ps1","install.sh"],"fingerprint":null,"notes":""},{"id":"A-003","title":"Initialize through an installed skill","status":"unchecked","paths":[".agents/skills/add-zzzops-goal/SKILL.md",".zzzops/rules/INITIALIZATION.md"],"fingerprint":null,"notes":""},{"id":"A-006","title":"Migrate TODOs with approval","status":"unchecked","paths":[".agents/skills/migrate-to-zzzops/SKILL.md"],"fingerprint":null,"notes":""},{"id":"A-008","title":"Capture a durable goal","status":"unchecked","paths":[".agents/skills/add-zzzops-goal/SKILL.md"],"fingerprint":null,"notes":""},{"id":"A-009","title":"Suggest work in dry-run mode","status":"unchecked","paths":[".agents/skills/suggest-zzzops-work/SKILL.md"],"fingerprint":null,"notes":""},{"id":"A-010","title":"Execute goals through review and resume","status":"unchecked","paths":[".agents/skills/execute-zzzops/SKILL.md",".agents/skills/execute-zzzops/references/EXECUTE.md",".agents/skills/execute-zzzops/references/UNBLOCK.md",".agents/skills/execute-zzzops/references/BRANCH_REVIEW.md"],"fingerprint":null,"notes":""}]}
zzzops-acceptance-plan -->

## A-001 - Native install preview is non-mutating

Prerequisite: use a disposable Git repository whose `.gitignore` ignores both `.agents/` and `.claude/`.

Human action: from a normal terminal outside any agent harness, run `install.ps1 TARGET -DryRun` on Windows or `install.sh TARGET --dry-run` on macOS/Linux, then inspect the target and Git status.

Expected: it explains the tracked project skills, rules/control CLI, and blank setup templates; warns that ignored project skills would not reach collaborators; requires no Python or Node; and changes nothing.

## A-002 - Native installer confirms and applies once

Prerequisite: complete A-001, then remove the `.agents/` and `.claude/` ignore rules.

Human action: run the platform installer without its dry-run option, inspect its preview, answer yes at the default-no prompt, inspect the installed files and target Git status, then repeat a dry run.

Expected: the same invocation rechecks and applies the preview; installation succeeds concisely; `.agents/skills/` and `.claude/skills/` contain the discoverable skills, all other harness support is grouped under `.agents/zzzops/`, shared rules stay under `.zzzops/`, and no ZzzOps file sits directly under `.agents/` or `.claude/`. Git shows only the previewed mechanics, project state is not initialized, and the repeated preview reports that ZzzOps is already up to date.

## A-003 - Initialize through an installed skill

Prerequisite: A-002 completed in the disposable repository.

Human action: open a fresh Codex or Claude Code session, start a non-install ZzzOps workflow, answer consequential setup questions, and review the generated `PROJECT.md`.

Expected: the installed skill is discovered; the agent proposes overridable project defaults, including outcome-first communication, and waits for explicit policy review before continuing.

## Installed skill workflows

Run each in a disposable repository and record the result in the matching ledger item.

| ID | Human action | Expected observable result |
| --- | --- | --- |
| A-006 | Preview a TODO migration, approve it, and inspect the resulting queue. | Existing TODOs are summarized before approval, then become durable GitHub goals with nothing silently omitted. |
| A-008 | Capture a small additional goal. | It is durable but creates no branch, commit, or PR. |
| A-009 | Run work suggestion in dry-run mode. | Evidence-backed suggestions are shown without changing the backlog. |
| A-010 | Invoke `execute-zzzops` in dry-run mode, then run one small source-changing goal through a human blocker, review, merge, and resume. | Dry run changes nothing; normal execution gives clear actions, preserves blockers, presents a review link without merging early, and resumes after the authorized merge. |
