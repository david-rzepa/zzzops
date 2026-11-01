# G1001 design: make `zzzops new` idempotent

## Outcome

Running `zzzops new --file F` again for the same request returns the goal that already exists. It does not allocate a second id. This holds for an exact retry, for a push that landed but reported failure, and for two identical `new` calls racing from different clones. When a request reuses a key with different contents, it is refused. Goals that are meant to be distinct, such as two with the same title and different specs, still get separate ids.

## Current behaviour (read at 54d7e83)

`cli.cmd_new` allocates `gid = max(known)+1` and builds a fresh root commit (`goal_commit(..., parent=None, ...)`). It then calls `push_atomic` with a create-only lease (`--force-with-lease=refs/heads/zzzops/goal/g<gid>:`). The result is handled in three ways:

- **`ok`**: it reports the goal as created.
- **`remote`**: it raises `Refused("remote")` straight away. It never checks whether the push landed. A client that retries then creates a duplicate.
- **`rejected`**: it refetches, and if `gid` is now taken it loops and allocates `gid+1`. Two identical concurrent calls therefore both succeed, as G_n and G_n+1. The loser never notices that the winner's goal is the same request.

Nothing in a goal records which request created it.

## Approach

### 1. Request identity

- The new-goal file gains an optional `request_key` field.
  - `schemas.validate_new_file` adds it to the allowed keys.
  - It must match `^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$`. Colons are not allowed, so an explicit key can never look like an automatic one.
- When `request_key` is absent, the default key is `"sha256:" + canon.H({"v": 1, "title": title, "spec": spec, "depends_on": norm(depends_on)})`.
  - `norm` sorts and deduplicates `depends_on` when it is a list of ints. Otherwise it passes the value through unchanged, and `validate_goal` rejects it later.
  - Title and spec are hashed exactly as given, with no trimming.
  - `graph`, `priority`, `release`, `skip`, `links` and `state` are not part of the default key, as the spec requires. They are covered by the contents check in step 3.

### 2. Where the key is recorded: a trailer on the goal's root commit

- `store.goal_message` gains an optional `request_key` argument. It writes a `Request-Key: <key>` trailer line before `Engine:`.
- `cmd_new` passes the key. No other verb writes this trailer.
- The root commit of `zzzops/goal/g<N>` is the `new` commit. It is immutable, and edits, submits and closes never change it.
- Recovery therefore still works after the goal has been edited or closed.
- No goal-schema change is needed.

### 3. Scan: `store.find_request_key(git, snap, key) -> list[(gid, root_oid, root_doc)]`

- **Scope**: the accepted tips in `snap.goals`, excluding `snap.deleted`. For a rewritten goal, the accepted (old) tip is used, so its root is unchanged.
- **Mechanism**: one git invocation, `git log --stdin --max-parents=0 --format=%H%x1f%B%x1e`, with the tips fed on stdin so argv stays bounded.
- **Matching**: keep the roots whose `Request-Key` trailer equals `key`. Take the id from the head line `zzzops: new G<n>`. Keep only ids in the scanned set.
- **Cross-check**: for each match, read the root's `goal.json` (`read_goal_json(root)`) and require `doc["id"] == n`. A root without the trailer, such as a goal created before this change, never matches.
- **Contents check**: compare the lowest-id match against the request. Compare `title`, `spec` and `norm(depends_on)`, plus every other field the request file explicitly sets (`graph`, `state`, `priority`, `release`, `skip`, `links`). Compare against the root document, not the current one. Fields the request leaves out are not compared. This prevents spurious conflicts when a default such as `releases.current` has changed between the call and its retry.

### 4. `cmd_new` control flow

```
key = request_key_of(spec)
s.open()
loop:
    if s.snap.current:
        hits = find_request_key(git, s.snap, key)
        if hits: return recover_or_refuse(hits)          # no write
    s.require_writable()
    allocate gid, build doc (validate as today), commit with Request-Key trailer
    r = push_atomic(...)
    if r == "ok": emit created (recovered: false); return
    try: s.refetch()
    except RemoteError: Refused("remote", ..., hint="rerun the same `new`: it is safe to retry")
    hits = find_request_key(...)
    if hits: return recover_or_refuse(hits)              # landed but reported failure, or a racing twin won
    if r == "remote": Refused("remote", as today, same hint)
    if gid not in s.snap.goals: Refused("push_refused", as today)
    deadline check -> Refused("contention", as today)
```

- **Recovery output**: the same shape as a fresh create.
  - `created` is built from the root document, and `goal_commit` is the root oid. This is the response the first call would have printed.
  - `created` also gets `"recovered": true` and `"request_key": key`. A fresh create carries `"recovered": false` and the key, so clients can always read both fields.
  - `next` is `s.render_next(scope=[gid])` over the refetched state.
  - A recovered goal is returned whatever its state: open, held, closed or invalid.
- **Writes**: the scan runs before `require_writable`, because recovering writes nothing. An exact retry therefore succeeds even while a policy branch pauses writes, as long as the snapshot is current. An offline snapshot skips the scan and falls through to `require_writable`, which refuses exactly as it does today.
- **Conflict**: if the key matches but the contents differ, `cmd_new` refuses with `Refused("validation", "request_key <k> already created G<n> with different contents: <fields>", details={"goal": n, "fields": [...]}, hint="use a different request_key, or `zzzops edit G<n>`")`. Using the existing `validation` code avoids a new entry in the error-code list (SPEC §3.17).
- **Several matches**: if more than one goal matches (see Risks), return the lowest id and add a `warnings` entry of kind `duplicate_request_key` that lists all of them.

## Why concurrent identical calls end up as one goal

Every `new` pushes `max(known)+1` with a create-only lease. In the usual race, both callers compute the same id. One push is rejected, the loser refetches, its scan finds the winner's key, and it returns `recovered`. Both calls can land, on different ids a < b, only if a was free on the remote below an id that b's caller already saw. Such a gap exists only when goal branches have been deleted from the remote (REPAIR territory), because ids are never reused while a clone remembers them. In that case the lowest-id rule plus the warning keeps the outcome deterministic and visible.

## Alternatives rejected

- **Store `request_key` in `goal.json`.** This needs a goal-schema change. `edit` could change or drop the key. The scan would also have to read every closed goal's document, because `read_state` only loads open ones. The root trailer is immutable and costs nothing to keep.
- **A create-only claim ref per key (`zzzops/key/<hash>`) pushed atomically with the goal.** This gives strict exclusion even with id gaps. The cost is a new permanent ref namespace: fetch specs, `ENGINE_REFS`, branch-rule guidance and cleanup. That is more than this narrow fix warrants, and the spec asks for a scan of goal tips.
- **Checking only the tip commit's trailers.** The tip changes on every later write, so a retry after any edit or submit would miss the key.
- **Including every field in the default key.** A retry whose resolved `release` default had changed would then get a new key and create a duplicate. The spec fixes the default to title, spec and depends_on.
- **Treating `remote` as final.** This is the current bug: a push that landed is reported as failed, and a retry then duplicates it.

## Interfaces and data that change

- **New-goal file**: optional `request_key`. Update `validate_new_file`, the `new` row in `references/CLI_USAGE.md`, and the `add-zzzops-goal` skill. The skill should say that rerunning `new` after an error is safe, and that `request_key` should be set when a caller wants two goals with identical title, spec and depends_on.
- **Root goal commit message**: new `Request-Key:` trailer.
- **`new` output**: `created.recovered` (bool), `created.request_key`, and an optional `warnings[]` entry `duplicate_request_key`.
- **New helpers**:
  - `store.find_request_key`.
  - `request_key_of` and the field-comparison helper. These go in `cli.py` beside `cmd_new`, or in `schemas.py`. The implementer can choose.
- **Unchanged**: the goal schema, the error codes, every other verb, and `next`'s single fetch.

## Risks

- **Existing tests that create identical goals.** Some tests call `new` with the same title and spec and expect two goals; for example, `test_engine_lifecycle.goal()` always uses title "Cut". Those calls will now recover the first goal. The implementer must run the full `.agents/test_engine_*` suite. Wherever a test means distinct goals, it should give them distinct specs or explicit `request_key`s. Tests must not be weakened to do this.
- **Scan cost.** `git log --max-parents=0` walks all goal history on every `new`. This is negligible at current scale, roughly thousands of commits. If it ever matters, caching root oid and key per goal locally is a follow-up, safe because roots are immutable.
- **Legacy goals** have no trailer, so a retry of a request made before this change can still duplicate. That is acceptable.
- **The id-gap duplicate** described above remains possible after manual remote deletions. It is surfaced by the warning.

## Tests (in `.agents/test_engine_store.py`, using the `World` fixtures)

1. **Exact retry.** Run `new` twice with the same file. The second call returns the same id with `recovered: true` and the same `goal_commit`. The remote has one goal ref, and the second call makes no push (check the trace).
2. **Push lands but reports failure.** Run `cli.main(["new", ...])` in process under `fx.EnvScope` with `engine.store.push_atomic` patched. The patch performs the real push and then returns `("remote", "simulated")`. Expect `ok` with `recovered: true` and one goal ref. A variant where the patched push does not push and returns `remote` must still exit with code 2 (`remote`).
3. **Concurrent identical calls.** Run ten threads across clones a and b with the same file. All exit 0, all report one id, the remote has exactly one new goal ref, and at least one result has `recovered: true`. Keep the existing distinct-titles concurrency test as it is.
4. **Key reused with different contents.**
   - The same explicit `request_key` with a different spec is refused with `validation`, and `details.goal` is the existing id.
   - The default key with an explicitly different `priority` is also refused.
   - A retry that omits an optional field the original set is recovered.
5. **Same title, distinct specs.** These produce two goals.
6. **Recovery after edit and after close.** Change the goal's title with `zzzops edit`, then rerun the original file. The original goal is recovered. This shows the key is read from the root, not the tip.
7. **Schema.** `validate_new_file` accepts a valid `request_key`. It rejects a key containing `:`, an empty key, and a key of 129 characters or more.

## Out of scope

Issue-based discovery, lock release and capture checkpoints (dropped by the spec, R1 and R12). Idempotency for verbs other than `new`. Per-key claim refs. Backfilling keys onto legacy goals.

## Decision record

- **Root-commit trailer instead of a goal-document field.** The spec allows either. The trailer needs no schema change and cannot be edited away.
- **Conflicts are reported as `validation`** rather than a new error code.

Neither needs a human decision.
