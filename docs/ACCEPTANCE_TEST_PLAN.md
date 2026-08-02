# Human acceptance plan

Run this plan conversationally: ask for the next item, perform its human action, then explicitly say `check A-001`. A checked item becomes stale when one of its mapped paths changes.

This plan, the `run-zzzops-acceptance` skill, and `.agents/manual_acceptance.py` belong only to the ZzzOps base repository's maintenance and release process. Neither native installer copies them into target projects; both install exactly `add-zzzops-goal`, `execute-zzzops`, `migrate-to-zzzops`, `review-zzzops-policy`, `send-zzzops-feedback`, and `suggest-zzzops-work`.

Maintainers must map each shipped user-facing surface to a human item. For ZzzOps that means only the native installer CLI modes and installed skills. Internal control commands, backend mechanics, policy plumbing, reservations, prompt accounting, CI, documentation, and individual test cases are not separate human acceptance surfaces; inspect or automate them proportionately instead. Reusable acceptance-harness behavior needs focused regression coverage, but no human item unless the harness itself ships to users. Run `<python> .agents/manual_acceptance.py coverage` with one resolved Python 3.10 or newer interpreter to report required unmapped user surfaces without changing the plan.

<!-- zzzops-acceptance-plan
{"version":1,"items":[{"id":"A-001","title":"Native disposable-install preview is non-mutating","status":"checked","paths":["install.ps1","install.sh",".agents/zzzops/installer.py"],"fingerprint":"6b69c22b50bf4a60d09f979dbf4e443a784506c280c0df9c00b64be70da88fdf","notes":""},{"id":"A-002","title":"Native installer reconstructs ignored machinery","status":"unchecked","paths":["install.ps1","install.sh",".agents/zzzops/installer.py"],"fingerprint":null,"notes":""},{"id":"A-003","title":"Review and initialize project policy","status":"unchecked","paths":[".agents/skills/review-zzzops-policy/SKILL.md",".zzzops/rules/INITIALIZATION.md"],"fingerprint":null,"notes":""},{"id":"A-006","title":"Migrate TODOs with approval","status":"unchecked","paths":[".agents/skills/migrate-to-zzzops/SKILL.md",".zzzops/rules/BACKENDS.md"],"fingerprint":null,"notes":""},{"id":"A-008","title":"Capture a durable goal","status":"unchecked","paths":[".agents/skills/add-zzzops-goal/SKILL.md",".zzzops/rules/BACKENDS.md"],"fingerprint":null,"notes":""},{"id":"A-009","title":"Suggest work in dry-run mode","status":"unchecked","paths":[".agents/skills/suggest-zzzops-work/SKILL.md",".zzzops/rules/BACKENDS.md"],"fingerprint":null,"notes":""},{"id":"A-010","title":"Execute goals through review and resume","status":"unchecked","paths":[".agents/skills/execute-zzzops/SKILL.md",".agents/skills/execute-zzzops/references/EXECUTE.md",".agents/skills/execute-zzzops/references/UNBLOCK.md",".agents/skills/execute-zzzops/references/BRANCH_REVIEW.md",".zzzops/rules/BACKENDS.md",".zzzops/rules/GOAL_SYSTEM.md"],"fingerprint":null,"notes":""},{"id":"A-011","title":"Send feedback with exact confirmation and safe report cleanup","status":"unchecked","paths":[".agents/skills/send-zzzops-feedback/SKILL.md",".zzzops/rules/FEEDBACK.md"],"fingerprint":null,"notes":""},{"id":"A-012","title":"Native installer repairs machinery and cleans legacy tracking","status":"unchecked","paths":["install.ps1","install.sh",".agents/zzzops/installer.py"],"fingerprint":null,"notes":""},{"id":"A-013","title":"Native installer restores the project lock's pinned version","status":"unchecked","paths":["install.ps1","install.sh",".agents/zzzops/installer.py"],"fingerprint":null,"notes":""}]}
zzzops-acceptance-plan -->

## A-001 - Native install preview is non-mutating

Prerequisite: use a clean disposable Git repository and a Python 3.10 or newer interpreter.

Human action: from a normal terminal outside any agent harness, run `install.ps1 TARGET -DryRun` on Windows or `install.sh TARGET --dry-run` on macOS/Linux, then inspect the target and Git status.

Expected: it identifies a fresh disposable install and incoming ZzzOps version, reports the exact root/file counts, explains wipe/reconstruct/validate/ignore/lock-last behavior, states that `.zzzops/init/` is preserved local scratch, defaults confirmation to no, and changes neither files nor Git index.

## A-002 - Native installer confirms and applies once

Prerequisite: complete A-001 in the same disposable repository.

Human action: run the platform installer without its dry-run option, inspect its preview, answer yes at the default-no prompt, inspect the installed files and target Git status, then run the normal installer again.

Expected: the same invocation rechecks and applies the preview; installation succeeds concisely and directs you to reopen the harness. `.agents/skills/` and `.claude/skills/` contain discoverable local skills, harness support is under `.agents/zzzops/`, and rules are under `.zzzops/rules/`. Git shows only `.zzzops/ZZZOPS_LOCK.json` plus scoped `.gitignore` and `.zzzops/.gitignore` changes; machinery is present but ignored and project policy is not initialized. A repeated normal install identifies a reinstall, defaults to no, and a confirmed rerun reconstructs the same validated bytes.

## A-012 - Native installer repairs machinery and cleans legacy tracking

Human action: install an older tracked ZzzOps revision into a disposable repository, then run the newer installer. Inspect the exact tracked-path list and press Enter at the cleanup prompt. Rerun, approve cleanup and installation, then edit and delete installed files and rerun once more. Also create a file under `.zzzops/init/` before repair.

Expected: the newer installer identifies upgrade/repair, shows the installed and incoming ZzzOps versions, lists only provenance-backed tracked machinery, and asks separately before index cleanup; Enter leaves files, index, lock, and ignores unchanged. Approval removes exactly those paths from the index while reconstruction leaves validated ignored working files present, writes the new lock last, and confirms the installed version. Later local edits and missing files are treated as disposable and repaired by the regular installer. The `.zzzops/init/` file remains present and ignored. PowerShell and shell behavior match; staged managed changes block before mutation.

## A-013 - Native installer restores the project lock's pinned version

Human action: in a disposable repository, save a valid lock from an older ZzzOps installation, upgrade normally from the current ZzzOps clone, then put the saved lock back and run the current installer with `-Restore -DryRun` on Windows or `--restore --dry-run` on macOS/Linux. Inspect the preview and both repositories, then confirm the restore and repeat it once.

Expected: preview identifies a pinned restore and shows the locked version and full revision without changing the target. Confirmation reconstructs machinery matching every saved-lock digest, preserves the saved lock exactly, and reports the restored version. Repetition is idempotent; the current ZzzOps checkout, branch, tracked files, and worktree list remain unchanged. If the revision is absent locally, restore fetches only from that clone's `origin`; an unreachable revision or source/hash mismatch stops before target mutation.

## A-003 - Review and initialize project policy

Prerequisite: A-002 completed in the disposable repository.

Human action: open a fresh Codex or Claude Code session, invoke `review-zzzops-policy`, answer consequential setup questions, approve the proposed policy, then invoke it again.

Expected: the installed skill is discovered; it proposes overridable project defaults, including outcome-first communication, and waits for explicit approval before continuing. The second invocation re-summarizes the meaningful current policy and invites adjustments rather than reporting only that setup is complete.

## Installed skill workflows

Run each in a disposable repository and record the result in the matching ledger item.

| ID | Human action | Expected observable result |
| --- | --- | --- |
| A-006 | Preview a TODO migration, approve it, and inspect the resulting queue. | Existing TODOs are summarized before approval, then become durable GitHub goals with nothing silently omitted. |
| A-008 | Capture an initially vague small goal, answer the adaptive requirements questions, and inspect the result. | Questions stop once the policy-selected depth is actionable and verifiable, skip already answered areas, assume the requesting user owns acceptance, and create one durable goal without a branch, commit, or PR. |
| A-009 | Run work suggestion in dry-run mode. | Evidence-backed suggestions are shown without changing the backlog. |
| A-010 | Invoke `execute-zzzops` in dry-run mode, then run one small source-changing goal that encounters an unanswered authority or specification gate; later supply the answer and resume through review and merge. | Dry run changes nothing; normal execution asks no live question, persists the gate on the issue, continues independent work, presents the durable blocker at handoff, and resumes from the later answer without merging early. |
| A-011 | With one archived synthetic report, invoke `send-zzzops-feedback` with innocuous user feedback. Inspect the exact public payload, then separately cancel, enter a wrong digest, and force one provider failure before restoring authentication and confirming the current digest. | Every preview is human-readable and labels the public issue `zzzops-feedback`. Cancellation, digest mismatch, and provider failure retain the immutable report. The successful confirmed submission creates exactly the previewed issue and deletes only its confirmed report. |
