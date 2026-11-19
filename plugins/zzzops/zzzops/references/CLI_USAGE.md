# ZzzOps CLI

Every verb prints one JSON object (`show` prints text unless `--json`). **Running it:** with the plugin's launcher on `PATH` (Claude Code), `zzzops <verb> …`. Otherwise run `<python> <plugin>/zzzops/zzzops.py <verb> …`, where `zzzops.py` is the file next to this reference's folder (`../zzzops.py` from here) and `<python>` is the first of `python3`, `python` and `py -3` that reports Python 3.10 or later (`<python> --version`). After the first call, run every command exactly as the CLI prints it (its `command` field); in PowerShell prefix it with `& `. Global flags: `--remote R`, `--integration B`, `--repo DIR` (find the repository from DIR, any directory inside it or one of its worktrees, instead of the working directory; file arguments stay relative to where you run; task-card, `renew` and `abandon` commands already end with `--repo <primary worktree>`, so they run from anywhere), and `--policy-ref REF` (a read-only preview for `next`, `show` and `validate`: the policy is read from `REF`, a `zzzops/policy/*` branch or its topic, a branch on the remote, or a local commit, instead of the integration branch; the previewed branch does not pause its own preview, and `validate` adds the impact on current goals; commands that change goals refuse it). Exit codes: 0 ok; 1 refused (fix the input or the state); 2 remote unreachable or the push refused by a rule; 3 lost a race (re-read and retry); 4 policy blocked (including `legacy_policy`: a pre-reset `.zzzops/POLICY.json`; run the migrate-zzzops-repository skill).

| Verb | Use |
|---|---|
| `next [--goal G]… [--all]` | What to do: `actions` (run their `start` command), `needs_human` (full items with `--goal`), `waiting`, `running`, `wake_at`, `blockers`. Read-only. |
| `show G [--node X] [--json]` | One goal: its document, goal commit (for `edit --base`), node states and leases. |
| `new --file F` | Create a goal from `{"title", "spec", "priority"?, "release"?, "depends_on"?, "skip"?, "links"?, "request_key"?, "flow"?}` (`release` defaults to the effective release; `flow: {"hotfix": "<x>"}` marks a hotfix member and needs `settings.branching`). Returns the goal's `design` action. Safe to rerun: the same request (its `request_key`, by default title, spec and depends_on) returns the existing goal with `created.recovered: true`; the key reused with different contents is refused. |
| `start G X --as L [--reclaim] [--force]` | Claim a node. Agent nodes print the task card; op nodes run to completion. |
| `submit G X --attempt N --as L --output F [--artifact A]` | Finish an agent phase. `--blocked F` instead records a question for the human or the agent (`{"waiting_for", "question" or "instructions", "options"?, "recommendation"?}`). |
| `renew G X --attempt N` | Keep the lease alive (every quarter of its timeout); `inputs_changed: true` means the inputs changed since start (abandon and restart, or finish knowing it re-runs). |
| `abandon G X --attempt N` | Give up a phase; the node becomes reclaimable, so the next `start` needs `--reclaim` (a plain `start` is refused); it prints `restart`, the `start … --reclaim` command to run. `--force --note T` acts on anyone's lease. |
| `answer G X --fp P --file F` | Record a human decision (the item's `answer_template`). Refused with `fp_mismatch` when the question changed. |
| `reopen G X --note T` | Re-run a done node (for example re-observe a flaky check). |
| `edit G… (--file F… \| --set PATH=JSON…) [--base C]…` | Change goals: hold, unhold, depend, skip (a node, or one lens with `skip.<node>:<lens>`), close, budget, waive. Without `--base` for every goal it is a dry run that prints the impact preview. Both the preview and the applied result list `live_leases_on_changed_nodes` (running phases whose inputs the edit changes, with `abandon` and `restart` commands). `carried_findings` lists the open findings that stay live after the edit although their review went stale, each with the `--set` lines that waive it in the same edit. |
| `release cut N --answer F` | With `settings.branching`: answer a `release_cut` item. Cuts `<release_prefix>N` from the integration tip and creates its line goal; `F` is the item's `answer_template` (`{"decision": "approved", "quote", "decided_by"}`). Safe to rerun: a cut that already happened returns its goal with `created.recovered: true`. |
| `release insert TARGET --from SOURCE [--answer F]` | With release branching and the `insertable_release_targets` capability, preview an isolated release from a previously finished release. Apply with the preview's answer template after owner approval. The source and production snapshots are checked again; changes require a fresh preview. |
| `release forward-port SOURCE --to BRANCH` | Start or resume a separate operation for a finished maintenance release. Inspect the operation with `next --goal G` and approve its exact PR or history evidence before it can complete. The source release stays closed and unchanged. |
| `hotfix start X --answer F` | With `settings.branching`: answer a `hotfix_start` item. Creates `<hotfix_prefix>X` from the production branch and its line goal; a finished hotfix name is refused (choose a new one). |
| `validate [G…]` / `validate --policy [--dir D]` | Check goals, the environment and policy files, and show the engine's `build` and `capabilities`; changes nothing. With `--policy-ref REF`, check the policy on `REF` and report its impact. |

`ZZZOPS_TRACE=<file>` appends one JSON line per network call (`git fetch`, `push`, `ls-remote`, and every `gh` call) with `cmd`, `rc` and `ms`. Local git commands are not traced.

Release targets compare as numeric components: `2.1` precedes `2.10`, and trailing zero components are aliases (`2`, `2.0`). An inserted maintenance release remains on its own line; it does not move production backwards. Production forward-ports require separate approval for each destination. GitHub guards the approved PR head but cannot atomically guard independent refs, so a detected source or base race pauses further propagation for review.

**Examples.**
```sh
zzzops next --goal 1002
zzzops start 1002 implement --as claude:9c1d/implement-1
zzzops submit 1002 implement --attempt 1 --as claude:9c1d/implement-1 --output out.json
zzzops edit 1002 --set 'state="held"' --base <goal commit from show>
zzzops validate --policy --dir .zzzops
zzzops next --policy-ref zzzops/policy/ci-lint
```

**Legacy state.** `next` and `validate` report pre-reset goals/files as `legacy`; an old policy blocks writes as `legacy_policy`. Offer `migrate-zzzops-repository` once; the legacy notice alone does not pause work. See [legacy detection and compatibility](MIGRATING.md#legacy-detection-and-compatibility) for fields, rechecks and policy-controlled dismissal.

For capability floors, response-key refusals and agent output schemas, see [engine capabilities and phase outputs](PHASE_OUTPUTS.md).

**Outputs** use the work branch's HEAD by default; an explicit checkpoint needs a full 40-hex sha. Review findings may use `follows` as described in the linked reference.

Require `blocked_findings` alongside or after the revised design step 4; see the linked reference for rollout.

**Goal sync.** Require `merge_sync` only after every writer is upgraded; otherwise base retains rebase mode. Never remove it while an open work branch has sync merges. See [REPAIR.md](REPAIR.md#goal-sync-checkpoints-and-delivery) for rollout, rollback, conventional subjects, scoped checkpoints and conflict recovery.

**Measured verification (`test_cost`).** Observed timings compare total/repository costs with one newest tested merged source; unavailable is never zero. Deltas are informational. Policy-enabled lanes share a capped CPU budget. See [adoption and local sharding](MIGRATING.md#adopting-measured-test-cost-capability-test_cost) for qualifications and settings.

**Round budgets:** `round_budget` gates per-stage limits on new material-finding rounds (default 10); see [adoption](MIGRATING.md#clean-sync-reviews-and-round-budgets).

[Defaults](MIGRATING.md#shipped-default-updates).


**Preserved test scope recovery.** `validate G` reports read-only `scope_recovery` diagnostics for the explicitly requested goal. A proposal identifies each path's accepted-history sources and includes an edit file and observed base; review and preview that file before applying it with `edit --file FILE --base BASE`. Uncertain evidence offers no edit. A producer with mixed pending test and non-test candidates supplies `scope_selection` in its output; independent review sees the selected and excluded candidate paths. See REPAIR.md for capability activation and recovery steps.
