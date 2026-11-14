# G1045: adopt the tested release summaries

Port the existing improvement from `4ff4e3f188f613adbd22a0726c1bbde69eed9d1b` (base `c455b09914b49fd65e169f91a4f79110e3e2540b`, source build `0.0.0-dev a81bbe0dd4ce`) into dev through this goal. Inclusion is already authorized by the goal specification; no new product choice is made.

Reuse the implementation unchanged: `next.releases.summaries` derives line identity, observed branch/head, production target, member counts/unfinished references, workflow progress, existing action/blocker references and recorded production/back-merge evidence. Preserve existing output fields and execution behavior. Reject a redesign, new command or persistent report: the settled derived view already meets the requested outcome.

`test_design` first copies `.agents/test_engine_release_summary.py` from the pinned source and runs its 15 tests against the missing feature. It records the expected failures, then submits the test checkpoint. `implement` ports the four engine files (`release_summary.py`, `render.py`, `session.py`, `store.py`), SPEC amendment and original design/plan from that same source. Add only necessary DESIGN rationale and a HISTORY §4 amendment row, without renumbering sections. Compare the final product files against the source to confirm fidelity.

Run focused summary tests locally first, including their real bare-Git/CLI journeys and remote-ref read-only comparison. Then run unchanged required repository validation and exact-head CI. The original plan records 1,136 passing frozen-source tests; that historical evidence does not replace fresh integration checks. Complete independent reviews and routine delegated approvals. Prepare the dev PR; if normal GitHub rules block merging, report its ready head and actionable prerequisite promptly.

## Sourced constraints and risks

The pinned seven-line design and implementation plan under `docs/superpowers/{specs,plans}/2026-11-13-release-summary*` define the adopted behavior, including review fixes. Preserve operation-based node identification, local hydration of closed line evidence while ordinary closed members remain ledger-only, and `item_kind` advisory references. Closure alone never proves publication; missing evidence is unknown, and malformed back-merge mappings remain unknown without losing valid production-merge evidence. Paused/offline views offer no executable actions. Trim advisory summary detail before existing actionable output; `next --all` retains full detail. Do not strengthen the base renderer's universal size guarantees.

Out of scope: new state, scheduler, policy, approvals, deployment gates, dependencies, release publication, whitepaper/release-pin changes and unrelated backlog. Repository deployment remains external. These boundaries and exact-source reuse limit regression and scope risk.
