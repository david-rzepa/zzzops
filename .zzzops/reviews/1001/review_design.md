# G1001 design review: idempotent `zzzops new`

**Verdict: approved, no open findings.**

The design meets the spec. A request gets a stable key: an explicit `request_key`, or by default sha256 over title, spec and the normalised `depends_on`. The key goes in a trailer on the goal's immutable root commit. The scan before allocation, and again after any push that is not ok, covers every acceptance case in the spec. These are: exact retry, a push that landed but reported failure, concurrent identical calls, a reused key with different contents, and same-title goals with distinct specs. Each one maps to a named test.

## Claims checked against 54d7e83

- **`cmd_new`** (`engine/cli.py:318`). It allocates `max(known|goals|deleted|rewritten)+1`. It builds a parentless commit with `goal_commit(..., None, ...)` and pushes with a create-only lease. On `remote` it raises straight away, without checking whether the push landed. On `rejected` it refetches and loops. This matches the design's "Current behaviour" section.
- **Root immutability.** `goal_commit` always takes at most one parent. The engine never deletes or rewrites goal refs: the only writers are `write_goals` and `verbs.py:586`, and both add a forward commit. The fetch refspec for goals is non-forced, so a rewritten goal keeps its accepted old tip in `snap.goals`. Reading the trailer from the root is therefore sound after edits and closes.
- **Scan scope.** The fetch takes every `refs/heads/zzzops/goal/*`, including closed goals. `snap.goals` holds the accepted tips, and `snap.deleted` goals keep their local tip in `snap.goals`, so excluding them explicitly, as the design does, is needed. `read_state` loads only open documents, which supports the reason given for rejecting a `goal.json` field.
- **Trailer parsing.** `goal_message` writes trailers only from engine-controlled values, and `Commit.trailer` scans from the end. A `Request-Key:` line placed before `Engine:` parses correctly, and user text never enters a root message.
- **Concurrency argument.** Ids come from what the clone has fetched (plus local refs from earlier fetches). Without remote deletions, the remote's set of ids only grows. So a caller can compute a higher id only if it has seen a lower one that already exists on the remote, and the other caller's create-only push to that lower id is then rejected. The analysis of the id-gap case is correct, and the lowest-id rule plus the warning is a proportionate answer.
- **Test 2 patch point.** `cmd_new` imports `push_atomic` from `engine.store` inside the function, so patching `engine.store.push_atomic` takes effect.
- **Offline path.** `Session.open(readonly=False)` raises `Refused("remote")` when the remote is unreachable, so `new` never sees an offline snapshot. The `if s.snap.current` guard is harmless.

## Non-blocking notes for the implementer

None of these changes the design.

1. **Empty goal set.** `git log --stdin` with nothing on stdin falls back to `HEAD`, which would walk the user's own branch. The id cross-check would filter the results out, but `find_request_key` should return `[]` straight away when no tips are in scope.
2. **Test fixture.** `World.new` defaults to `spec = "spec for {title}"`, and many tests reuse the same title, for example `goal()` with "Cut" and the default "Goal". Some of them also vary `priority` or `depends_on`, and with the default key those will now be refused as conflicts, not just recovered. The simplest fix that keeps tests strong is to make the fixture's default spec unique per call, for example with a counter. Tests that mean "the same request" would then pass an explicit file.
3. **`next` for a closed recovered goal.** `render_next(scope=[gid])` on a goal that is not loaded gives an empty scoped result, without an error. That is acceptable, but a test should pin it down (test 6, the close variant).
4. **`--policy-ref` order.** Because the scan runs before `require_writable`, `new --policy-ref` on a retry would recover rather than raise the `usage` refusal. Keep the `policy_ref` check ahead of the scan so that a preview flag is still refused the same way every time.

## Risks

The design names the right risks: existing tests that create identical goals, scan cost, legacy goals without a trailer, and the id-gap duplicate. Each one comes with a mitigation or an explicit acceptance.
