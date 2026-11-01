# G1021 implementation review (8cc435a)

**Verdict: approved.** No findings.

## Scope and tests

- Between the frozen tests (280a301) and 8cc435a, outside `.zzzops/reviews`, only `ops/integrate.py` and `references/REPAIR.md` changed. The fake gh and the test files are untouched, so the tests were not weakened.
- `context.checks` passed: the 9 new tests, the engine suite, and the full `.agents` suite (532 tests).

## Step 5b against the design

- **Order.** The order is local `merge-tree`, then head-not-seen wait (`headRefOid != H`), then GitHub `CONFLICTING`/`DIRTY`, then `UNKNOWN` wait, then required checks. That matches the design and implementer note 1 of the design review. The GitHub conflict branch only runs once `headRefOid == H`, so a stale conflicting head cannot send a goal that was already rebased back to `base`.
- **Only into I.** Step 5a (`target != I`) returns before 5b. So `merge-tree` never runs for stacked targets (`zzzops/pr/gD`, `zzzops/stack/gG`), and the stacked path is unchanged.
- **merge-tree call.** `merge-tree --write-tree --name-only --no-messages <snap.integration> H` with `check=False`. Exit 0 means clean. Exit 1 means conflict, and the files are stdout lines after the tree OID. Any other exit raises `EngineError` with stderr capped at 300 characters, the same way `base.combine` handles it. `EngineError` is already imported. The comparison uses this invocation's fetched tip, as designed.
- **Bounded waits.** Both new waits use `ctx.wait(..., 60)`. That carries `{pending_since, polls}` and escalates to a human at `ci_timeout_minutes`, and an answer resets it. The checks wait still reads `op_state` only when `op_state.head == H`.
- **No-checks question.** It fires only when `pending` is set, the whole rollup for head H is empty (head equality is now guaranteed before this point), and `now - pending_since >= min(15, ci_timeout_minutes)` minutes. With the unchanged 5/10/20 backoff, polls land at t = 0, 5 and 15, so it fires on the third poll. It comes before the 120-minute check and carries the same `op_state` (`keep`). An answer clears `st`, which re-arms the window. A non-empty rollup with the required check pending keeps the 120-minute path.
- **Reason text.** The text is now `required checks pending: X (mergeable: M/MS)`. The no-checks question includes the same merge state.
- **GitHub calls.** No new calls. The added work is one local git call. The single `pr view` and its fields are unchanged.
- **Conflict finding.** The key is still `conflict` on input `base`, and the outputs are unchanged. Both paths go through the shared `conflict()` helper. The local path's text names the tip and the files.

## REPAIR.md

The new section is accurate. The local check and GitHub's `mergeable` both raise `conflict` on `base`, as `merge` does. `base` rebases or blocks with `rebase conflict in <files>`, which is the exact reason text in `base.py`. The hand-recovery command `zzzops reopen <id> base --note ...` matches the CLI. It shortens some details, but the blocked card supplies them: the recipe says `git rebase --continue`, where the card says `git -c core.editor=true rebase --continue`, and it says `start <id> base`, where the card adds `--as <LABEL>`. This is not material.

## Non-material observations

- When a run goes from a checks wait (whose `op_state` has `head`) to an `UNKNOWN` or head-not-seen `ctx.wait`, it inherits `pending_since`/`polls`. That only shortens the time to escalation, which stays bounded. The design review already accepted this.
