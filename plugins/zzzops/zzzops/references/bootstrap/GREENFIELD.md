# Execute a greenfield bootstrap

After the proposal and canonical harness DAG are established, run bootstrap goals through `$execute-zzzops`. Bootstrap coordinates existing execution; it does not directly scaffold from an internal checklist or weaken goal review, Git, blocker, or verification policy.

## Journey

1. Confirm the repository is still greenfield or early scaffold and the approved proposal, portfolio revisions, and target branch have not drifted. Re-analyze on consequential drift.
2. Create all planned harness goals and product-goal dependency edges through `PLAN.md`, then invoke the normal goal loop. Let `$execute-zzzops` own claims, branches, commits, PRs, review gates, blockers, and resumability.
3. Execute only harness/scaffold outcomes: pinned toolchain, justified structure and architecture boundaries, test/static-analysis surfaces, canonical verification, equivalent CI, concise context, and documentation. Routine reversible choices follow reviewed autonomy; consequential architecture changes remain blockers.
4. Reconcile `AGENTS.md` rather than overwrite it. Preserve unrelated instructions and the workflow-adherence block owned by `$review-zzzops-policy`. Keep stable purpose, pinned stack, canonical commands, hard invariants, definition of done, and deeper-context links; use deterministic enforcement where practical.
5. For each goal, run and inspect its real probe. A script, test, CI file, or guardrail that merely exists is not acceptance evidence. The canonical verification command must exercise every required local gate, and CI must call that same contract rather than duplicate it.
6. After harness goals reach their policy-required review state, run canonical verification once at the exact combined checkpoint and inspect the output. If required CI exists, inspect it at that same head. Failures return to their owning ordinary goal.
7. Stop before the first product milestone. Confirm seeded product goals remain unimplemented and depend on the harness outcomes they need. Report the working factory, verification evidence, review queue, deferred decisions, and the next product goal.

## Disposable fixture

Use an empty temporary repository with reviewed `structured` rigor and this specification: a Python 3.12 command-line application, supported on Linux and Windows, with a later milestone that prints a greeting for a supplied name. No authentication, persistence, deployment, or compatibility commitment is present.

Expected bootstrap evidence:

- mode is `greenfield`; no irrelevant enterprise questions;
- Python is pinned and a minimal package/test layout is scaffolded without greeting behavior;
- formatting/lint/type/test choices are justified by the structured bar;
- one documented verification command runs those gates successfully;
- CI invokes the same verification command on the supported platforms;
- concise `AGENTS.md` points to commands and architecture context without generic Python documentation;
- the greeting milestone is a canonical unimplemented product goal depending on the completed harness leaves;
- rerunning bootstrap reuses goals and makes no source or dependency change.

The fixture fails if product behavior is implemented, required output is unobserved, CI and local verification diverge, generic machinery appears without evidence, or files are reported as proof without execution.
