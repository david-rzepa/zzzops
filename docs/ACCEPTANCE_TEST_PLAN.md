# Human acceptance plan

Run this plan conversationally: ask for the next item, perform its human action, then explicitly say `check A-001`. A checked item becomes stale when one of its mapped paths changes.

Maintainers must map each new shipped user-facing functional surface to a human item. Documentation and individual test cases are not functional surfaces and need no item solely to test their prose or test code; inspect documentation and run changed tests instead. Reusable test/acceptance harness behavior needs focused regression coverage, and needs a human item only when that harness itself exposes a shipped user-facing workflow. If a scenario cannot safely be manually tested, add an evidence-backed exemption in the item notes explaining the safety boundary and automated coverage; do not silently omit it. Run `<python> .agents/manual_acceptance.py coverage` with one resolved Python 3 interpreter to report required unmapped surfaces without changing the plan.

<!-- zzzops-acceptance-plan
{"version":1,"items":[{"id":"A-001","title":"CLI install preview is non-mutating","status":"unchecked","paths":["zzzops.py"],"fingerprint":null,"notes":""},{"id":"A-002","title":"CLI applies the previewed installation","status":"unchecked","paths":["zzzops.py"],"fingerprint":null,"notes":""},{"id":"A-003","title":"Agent-led project initialization","status":"unchecked","paths":[".zzzops/rules/INITIALIZATION.md",".agents/zzzops.py"],"fingerprint":null,"notes":""},{"id":"A-004","title":"Preferences CLI preserves local choices","status":"unchecked","paths":[".agents/zzzops.py",".agents/templates/project-goals/PREFERENCES.json"],"fingerprint":null,"notes":""},{"id":"A-005","title":"GitHub Issues backend","status":"unchecked","paths":[".zzzops/rules/BACKENDS.md"],"fingerprint":null,"notes":""},{"id":"A-006","title":"Migrate TODOs with approval","status":"unchecked","paths":[".agents/skills/migrate-to-zzzops/SKILL.md"],"fingerprint":null,"notes":""},{"id":"A-007","title":"Execute workflow is discoverable","status":"unchecked","paths":[".agents/skills/execute-zzzops/SKILL.md"],"fingerprint":null,"notes":""},{"id":"A-008","title":"Capture a durable goal","status":"unchecked","paths":[".agents/skills/add-zzzops-goal/SKILL.md"],"fingerprint":null,"notes":""},{"id":"A-009","title":"Suggest work in dry-run mode","status":"unchecked","paths":[".agents/skills/suggest-zzzops-work/SKILL.md"],"fingerprint":null,"notes":""},{"id":"A-010","title":"Execute, unblock, watch, and resume","status":"unchecked","paths":[".agents/skills/execute-zzzops/SKILL.md",".agents/skills/execute-zzzops/references/EXECUTE.md",".agents/skills/execute-zzzops/references/UNBLOCK.md",".zzzops/rules/BLOCKERS.md",".zzzops/rules/CONTINUATION.md",".zzzops/rules/EXECUTION_STRATEGY.md"],"fingerprint":null,"notes":""},{"id":"A-011","title":"Branch review and merge gate","status":"unchecked","paths":[".agents/skills/execute-zzzops/references/BRANCH_REVIEW.md"],"fingerprint":null,"notes":""},{"id":"A-012","title":"Concurrent goal reservation","status":"unchecked","paths":[".agents/zzzops.py",".zzzops/rules/GOAL_SYSTEM.md",".zzzops/rules/BACKENDS.md"],"fingerprint":null,"notes":""},{"id":"A-013","title":"Prompt budget is current","status":"unchecked","paths":[".agents/prompt_stats.py"],"fingerprint":null,"notes":""},{"id":"A-014","title":"PR validation and release boundaries","status":"unchecked","paths":[".github/workflows"],"fingerprint":null,"notes":""}]}
zzzops-acceptance-plan -->

## A-001 - CLI install preview is non-mutating

Prerequisite: use a disposable Git repository whose `.gitignore` ignores both `.agents/` and `.claude/`.

Human action: from a normal terminal outside any agent harness, run `<python> zzzops.py install TARGET`, then inspect the target and Git status.

Expected: it explains the tracked project skills, rules/control CLI, and blank setup templates; warns that ignored project skills would not reach collaborators; prints an approval code; and changes nothing.

## A-002 - CLI applies the previewed installation

Prerequisite: complete A-001, then remove the `.agents/` and `.claude/` ignore rules and rerun the preview to obtain a current approval code.

Human action: run `<python> zzzops.py install TARGET --apply APPROVAL_CODE`, then inspect the installed files and target Git status.

Expected: installation succeeds concisely; `.agents/` and `.claude/` contain tracked project skills; Git shows only the previewed ZzzOps mechanics; project state is not initialized.

## A-003 - Agent-led project initialization

Prerequisite: A-002 completed in the disposable repository.

Human action: open a fresh Codex or Claude Code session, start a non-install ZzzOps workflow, answer consequential setup questions, and review the generated `PROJECT.md`.

Expected: the installed skill is discovered; the agent proposes overridable project defaults, including outcome-first communication, and waits for explicit policy review before continuing.

## A-004 - Preferences CLI preserves local choices

Prerequisite: initialized disposable repository with ZzzOps mechanics installed.

Human action: run `<python> .agents/zzzops.py` with the resolved Python 3 interpreter, change one refill preference, exit, then reopen the panel.

Expected: the selected preference remains user-local in `.zzzops/PREFERENCES.json`; it is not staged or committed.

## A-005 to A-014 - Core ZzzOps workflow coverage

Run each in a disposable repository and record the result in the matching ledger item.

| ID | Human action | Expected observable result |
| --- | --- | --- |
| A-005 | Initialize with GitHub Issues selected. | A human-first issue is the canonical goal; repository visibility is explained. |
| A-006 | Preview a TODO migration, approve it, and inspect the resulting queue. | Existing TODOs are summarized before approval, then become durable GitHub goals with nothing silently omitted. |
| A-007 | In a fresh session, invoke `execute-zzzops` in dry-run mode against the migrated queue. | It discovers and reports the durable queue without source or Git changes. |
| A-008 | Capture a small additional goal. | It is durable but creates no branch, commit, or PR. |
| A-009 | Run work suggestion in dry-run mode. | Evidence-backed suggestions are shown without changing the backlog. |
| A-010 | Exhaust the queue on one merge-ready PR, merge it during the announced watch, and repeat once without a wait-capable surface. | The agent asks for one clear action without narrating polling mechanics, observes and resumes once; unsupported waiting hands off plainly with the blocker intact. |
| A-011 | Complete a source-changing test goal. | The agent says the change is ready, provides the review action/link, and does not expose internal hashes or merge without authority. |
| A-012 | Have two runs contend for one goal, then two different goals contend for one declared resource; repeat with distinct resources and after expiry. | Each overlap has one bundle winner, losers reselect, distinct work proceeds, only owners renew/release, and expiry cannot delete a replacement. |
| A-013 | Run prompt statistics and its check mode. | The byte/token estimate is deterministic and check mode succeeds. |
| A-014 | Open a PR and inspect its validation/release behavior. | PR checks are read-only; `main` release behavior remains restricted. |
