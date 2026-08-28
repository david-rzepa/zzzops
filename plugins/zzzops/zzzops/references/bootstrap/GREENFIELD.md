# Execute a greenfield bootstrap

After the product brief, policy approval, root goal, and canonical DAG are established, run the entire authorized DAG through `$execute-zzzops`. Bootstrap coordinates ordinary execution; it does not scaffold from a private checklist or weaken goal review, Git, blocker, or verification policy.

## Journey

1. Confirm the repository is still greenfield or early scaffold and the approved proposal, portfolio revisions, and target branch have not drifted. Re-analyze on consequential drift.
2. Create or reuse the top-level product goal, then create harness and product goals/edges through `PLAN.md`. Invoke the normal loop for claims, branches, commits, PRs, gates, blockers, and resumability.
3. Execute harness/scaffold outcomes and continue directly into authorized product milestones. Low [[bounded commitment]](../../../concepts/bounded-commitment.md) choices follow reviewed autonomy; high commitment uses early evidence and blocks only when materially ambiguous or outside authority.
4. Reconcile `AGENTS.md` rather than overwrite it. Preserve unrelated instructions and the workflow-adherence block owned by `$review-zzzops-policy`. Keep stable purpose, pinned stack, canonical commands, hard invariants, definition of done, and deeper-context links; use deterministic enforcement where practical.
5. For each goal, run and inspect its real probe. A script, test, CI file, or guardrail that merely exists is not acceptance evidence. The canonical verification command must exercise every required local gate, and CI must call that same contract rather than duplicate it.
6. After harness goals reach verified checkpoints, run canonical verification at the exact combined checkpoint and inspect required CI there. Failures return to their owning goal; success releases dependent product work.
7. Continue product goals until true exhaustion. Report the product root, working factory, product evidence, ordered PR review queue, deferred unauthorized scope, and blockers. Harness completion alone is not a stopping condition.

## Disposable fixture

Use an empty temporary repository with reviewed `structured` rigor and this specification: a Python 3.12 command-line application, supported on Linux and Windows, with a later milestone that prints a greeting for a supplied name. No authentication, persistence, deployment, or compatibility commitment is present.

Expected bootstrap evidence:

- mode is `greenfield`; no irrelevant enterprise questions;
- Python is pinned and a minimal package/test layout is scaffolded without greeting behavior;
- formatting/lint/type/test choices are justified by the structured bar;
- one documented verification command runs those gates successfully;
- CI invokes the same verification command on the supported platforms;
- concise `AGENTS.md` points to commands and architecture context without generic Python documentation;
- the greeting milestone is a canonical product goal depending on the required harness leaves and is implemented, observed, and queued in its own stacked PR;
- rerunning bootstrap reuses goals and makes no source or dependency change.

The fixture fails if no top-level product goal exists, safe greeting behavior remains unimplemented, required output is unobserved, CI/local verification diverges, generic machinery appears without evidence, or files are reported as proof without execution.
