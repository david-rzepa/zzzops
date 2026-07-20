# Human acceptance plan

Run this plan conversationally: ask for the next item, perform its human action, then explicitly say `check A-001`. A checked item becomes stale when one of its mapped paths changes.

Maintainers must map each new shipped user-facing functional surface to a human item. Documentation and individual test cases are not functional surfaces and need no item solely to test their prose or test code; inspect documentation and run changed tests instead. Reusable test/acceptance harness behavior needs focused regression coverage, and needs a human item only when that harness itself exposes a shipped user-facing workflow. If a scenario cannot safely be manually tested, add an evidence-backed exemption in the item notes explaining the safety boundary and automated coverage; do not silently omit it. Run `<python> .agents/manual_acceptance.py coverage` with one resolved Python 3 interpreter to report required unmapped surfaces without changing the plan.

<!-- zzzops-acceptance-plan
{"version":1,"items":[{"id":"A-001","title":"Native install preview is non-mutating","status":"checked","paths":["install.ps1","install.sh"],"fingerprint":"85fa9e13180c211bfac70c5d1d502cd95b4442d1f79ecfb72a17b96797daacd4","notes":""},{"id":"A-002","title":"Native installer confirms and applies once","status":"unchecked","paths":["install.ps1","install.sh"],"fingerprint":null,"notes":""},{"id":"A-003","title":"Agent-led project initialization","status":"unchecked","paths":[".zzzops/rules/INITIALIZATION.md",".agents/zzzops/zzzops.py"],"fingerprint":null,"notes":""},{"id":"A-004","title":"Reviewed execution defaults","status":"unchecked","paths":[".agents/zzzops/zzzops.py",".agents/zzzops/templates/project-goals/INIT_PLAN.json",".zzzops/rules/EXECUTION_STRATEGY.md",".zzzops/rules/GOAL_SYSTEM.md"],"fingerprint":null,"notes":""},{"id":"A-005","title":"GitHub Issues backend","status":"unchecked","paths":[".zzzops/rules/BACKENDS.md"],"fingerprint":null,"notes":""},{"id":"A-006","title":"Migrate TODOs with approval","status":"unchecked","paths":[".agents/skills/migrate-to-zzzops/SKILL.md"],"fingerprint":null,"notes":""},{"id":"A-007","title":"Execute workflow is discoverable","status":"unchecked","paths":[".agents/skills/execute-zzzops/SKILL.md"],"fingerprint":null,"notes":""},{"id":"A-008","title":"Capture a durable goal","status":"unchecked","paths":[".agents/skills/add-zzzops-goal/SKILL.md"],"fingerprint":null,"notes":""},{"id":"A-009","title":"Suggest work in dry-run mode","status":"unchecked","paths":[".agents/skills/suggest-zzzops-work/SKILL.md"],"fingerprint":null,"notes":""},{"id":"A-010","title":"Execute, unblock, watch, and resume","status":"unchecked","paths":[".agents/skills/execute-zzzops/SKILL.md",".agents/skills/execute-zzzops/references/EXECUTE.md",".agents/skills/execute-zzzops/references/UNBLOCK.md",".zzzops/rules/BLOCKERS.md",".zzzops/rules/CONTINUATION.md",".zzzops/rules/EXECUTION_STRATEGY.md"],"fingerprint":null,"notes":""},{"id":"A-011","title":"Branch review and merge gate","status":"unchecked","paths":[".agents/skills/execute-zzzops/references/BRANCH_REVIEW.md"],"fingerprint":null,"notes":""},{"id":"A-012","title":"Concurrent goal reservation","status":"unchecked","paths":[".agents/zzzops/zzzops.py",".zzzops/rules/GOAL_SYSTEM.md",".zzzops/rules/BACKENDS.md"],"fingerprint":null,"notes":""},{"id":"A-013","title":"Prompt budget is current","status":"unchecked","paths":[".agents/prompt_stats.py"],"fingerprint":null,"notes":""},{"id":"A-014","title":"PR validation and release boundaries","status":"unchecked","paths":[".github/workflows"],"fingerprint":null,"notes":""}]}
zzzops-acceptance-plan -->

## A-001 - Native install preview is non-mutating

Prerequisite: use a disposable Git repository whose `.gitignore` ignores both `.agents/` and `.claude/`.

Human action: from a normal terminal outside any agent harness, run `install.ps1 TARGET -DryRun` on Windows or `install.sh TARGET --dry-run` on macOS/Linux, then inspect the target and Git status.

Expected: it explains the tracked project skills, rules/control CLI, and blank setup templates; warns that ignored project skills would not reach collaborators; requires no Python or Node; and changes nothing.

## A-002 - Native installer confirms and applies once

Prerequisite: complete A-001, then remove the `.agents/` and `.claude/` ignore rules.

Human action: run the platform installer without its dry-run option, inspect its preview, answer yes at the default-no prompt, inspect the installed files and target Git status, then repeat a dry run.

Expected: the same invocation rechecks and applies the preview; installation succeeds concisely; `.agents/skills/` and `.claude/skills/` contain the discoverable skills, all other harness support is grouped under `.agents/zzzops/`, shared rules stay under `.zzzops/`, and no ZzzOps file sits directly under `.agents/` or `.claude/`. Git shows only the previewed mechanics, project state is not initialized, and the repeated preview reports that ZzzOps is already up to date.

## A-003 - Agent-led project initialization

Prerequisite: A-002 completed in the disposable repository.

Human action: open a fresh Codex or Claude Code session, start a non-install ZzzOps workflow, answer consequential setup questions, and review the generated `PROJECT.md`.

Expected: the installed skill is discovered; the agent proposes overridable project defaults, including outcome-first communication, and waits for explicit policy review before continuing.

## A-004 - Reviewed execution defaults

Prerequisite: initialized disposable repository with ZzzOps mechanics installed.

Human action: run `<python> .agents/zzzops/zzzops.py --repo . init inspect`, then inspect the proposed execution settings in the initialization plan and reviewed `PROJECT.md`.

Expected: the size report uses existing Git-tracked file bytes; refill is enabled for documentation, test coverage, and non-behavioral code quality with a three-goal cap; the small disposable repository selects at most three worktree workers; writable dependent goals wait for completed dependencies while read-only investigation remains allowed; completed worktrees must be removed or deliberately retained clean for safe reuse. These are visible reviewed defaults rather than hidden local state.

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
