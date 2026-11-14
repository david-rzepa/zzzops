# What the reset removed

The pre-reset engine's features, the R id of their removal, and what replaces them. Use it for triage: an issue whose subject appears in a row is OBSOLETE when the row says "removed" for that part, and DONE or MIGRATE when there is a replacement. Cite the R id in the closing comment.

| Old feature (issue subjects to look for) | R | Now |
|---|---|---|
| Comment envelopes, receipts, transaction manifests, state caches, hydration, the label storage lock, the v1/v2 converters, `zzzops:schema:v1/v2` labels | R1 | Goal documents on `zzzops/goal/g<id>` branches. Tamper evidence and per-mutation receipts: removed. |
| Correction compiler, admission/interpret/retain/resolve nodes, finding intake | R2 | A finding reopens its target directly; root can waive it by an edit. The admission gate: removed. |
| Policy approval ceremony: approval digest, bindings, history, proposal store, upgrade classification, `PROJECT_AUDIT.md` | R3 | Review of `zzzops/policy/*` branches as PRs; structural validation. |
| Whole-policy contract hash, historical-policy walk, projection forms, CI compatibility, DAG cutover, per-goal compiled graphs | R4 | Declared policy inputs; the graph read from the integration branch. Automatic staleness on instruction edits: removed (bump `rev` or `reopen`). |
| `CODEX_THREAD_ID` and root attestation, `bind`, model evidence, inventory gates, `routing.py`, `route_choice` approvals | R5 | Holder labels; advisory `routing.tiers`. Session and model checks: removed. |
| Allocation and authorization grants, owned paths, per-file inventories, finish intents, single-commit topology, draft chains | R6 | Per-goal worktree; `tree` and `change` identities; the frozen-tests (`preserve`) rule. Path whitelists: removed. |
| Dependency, blocker, archived-prerequisite, checkpoint-reconcile and graph-repair protocols | R7 | `zzzops edit` with validation, the `--base` fence and an impact preview. |
| Retained attempt refs, compaction, restack machine, publication topology, certificates, stack B-tree, terminal reconciliation, cleanup variants | R8 | The `base`, `integrate` and `merge` operations; stacked PRs only for dependencies. RED/GREEN commits and native atomic stack merges: removed. |
| Release-plan issue, release coordinator, lock and receipts | R9 | The goal's `release` field, `releases.current` and the release gate. The propose/freeze ceremony: removed. |
| Heartbeat daemon, capacity ledger, label phase leases, `reserve`, observed-stop recovery, response store | R10 | Lease branches; reclaim on expiry. Automatic renewal: removed. |
| Installation-validation gate, `plugin_freshness`, the legacy-cleanup gate | R11 | `validate` and the package self-check; retired installs are detected again by the `legacy` item (no gate). |
| v1 goal and phase model, intent/skill routing, the 52-operation dispatcher | R12 | The 11-verb CLI. |
| Ceremony nodes, the 37-node INIT_PLAN graph, repository/publication authorization nodes | R13 | The 12-node default graph (`approve_understanding` became `approve_design`). |
| Revision 5 runtime guards: engine self-test, verb-scoped diff check, clock-skew refusal, `edit --yes`, orphan-lease pruning, WIP push in `renew` | R14 | CI tests; engine floor and ceiling; warnings instead of refusals. |
| `bootstrap.py`, `--intent bootstrap`, `BOOTSTRAP.json` provenance and review checkpoint | R15 | The bootstrap skill, a checklist over `validate` and the shipped templates. |
| `zzzops-feedback` issues | D9 | The feedback feature was dropped. Triage each issue on its content. |
