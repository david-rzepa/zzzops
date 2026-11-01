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
- **Deleted-ref refetch (same-clone fetch race)**: `find_request_key` is wrapped by `scan(s, key)` in `cli.py`. If the scan finds no match and `snap.deleted` is not empty, `scan` calls `s.refetch()` once and scans again. Only then may the caller allocate an id.
  - Why it is needed: another `new` in the same clone can write `refs/zzzops/goal/origin/g<N>` after this call's fetch listed the remote. `build_snapshot` then puts G<N> in `snap.deleted`, the scan skips it, and this call would allocate and push G<N+1>: a duplicate.
  - Why one refetch is enough: the matching goal's local ref was written by a fetch that saw it on the remote. Goal refs are never deleted by `new`, so the second fetch lists it, and it lands in `snap.goals`.
  - A goal that is still in `snap.deleted` after the refetch really is gone from the remote, and stays excluded.
  - The refetch costs nothing in the normal case, because `snap.deleted` is empty.
- **Contents check**: compare the lowest-id match against the request. Compare `title`, `spec` and `norm(depends_on)`, plus every other field the request file explicitly sets (`graph`, `state`, `priority`, `release`, `skip`, `links`). Compare against the root document, not the current one. Fields the request leaves out are not compared. This prevents spurious conflicts when a default such as `releases.current` has changed between the call and its retry.

### 4. `cmd_new` control flow

```
key = request_key_of(spec)
s.open()
loop:
    if s.snap.current:
        hits = scan(s, key)        # find_request_key, plus one refetch + rescan if no hit and snap.deleted
        if hits: return recover_or_refuse(hits)          # no write
    s.require_writable()
    allocate gid, build doc (validate as today), commit with Request-Key trailer
    r = push_atomic(..., report_up_to_date=True)
    if r == "up_to_date": s.refetch(); return recover(gid)  # an identical twin already pushed this exact root
    if r == "ok": emit created (recovered: false); return
    try: s.refetch()
    except RemoteError: Refused("remote", ..., hint="rerun the same `new`: it is safe to retry")
    hits = scan(s, key)
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
- **Identical root commits (`up_to_date`)**: a root commit is deterministic. The same document, message, committer and `ZZZOPS_NOW` give the same oid, so two identical calls in the same second build the same commit. The second create-only push then changes nothing, and git exits 0. Today `push_atomic` reports that as `ok`, so both calls would say `recovered: false` for the one goal.
  - `push_atomic` gains a keyword `report_up_to_date=False`. When it is true, the exit code is 0, and every porcelain ref line starts with `=`, it returns `("up_to_date", stderr)`.
  - Only `cmd_new` passes it. Every other caller sees `ok` exactly as today.
  - `cmd_new` treats `up_to_date` as a recovery. The remote ref already holds this exact oid, so the goal is the request's goal. It refetches for `next` and returns `recovered: true`, without the contents check: the bytes are identical.
  - Result: exactly one call in any identical race reports `recovered: false`, whatever the clocks.
- **Writes**: the scan runs before `require_writable`, because recovering writes nothing. An exact retry therefore succeeds even while a policy branch pauses writes, as long as the snapshot is current. An offline snapshot skips the scan and falls through to `require_writable`, which refuses exactly as it does today.
  - **`--policy-ref` stays refused first**: `cmd_new` must keep calling `session(a)` (cli.py:328) before `s.open()` and the scan. `session()` refuses `--policy-ref` with `usage` for every non-preview verb before a Session exists (cli.py:97-100), so a retry with `--policy-ref` is refused and never reaches the scan. Implementers must not move the scan ahead of that call or rely on `require_writable` for this refusal.
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
- **`store.push_atomic`**: optional keyword `report_up_to_date` (default false) and the matching `up_to_date` result. Callers that do not pass it are unchanged.
- **Unchanged**: the goal schema, the error codes, every other verb, and `next`'s single fetch.

## Risks

- **Existing tests that create identical goals.** Some tests call `new` with the same title and spec and expect two goals; for example, `test_engine_lifecycle.goal()` always uses title "Cut". Those calls will now recover the first goal. The implementer must run the full `.agents/test_engine_*` suite. Wherever a test means distinct goals, it should give them distinct specs or explicit `request_key`s. Tests must not be weakened to do this.
- **Extra refetch.** The deleted-ref rule adds one fetch to a `new` call only when `snap.deleted` is not empty and nothing matched. That is a rare state, either a same-clone race or a goal really removed from the remote.
- **Scan cost.** `git log --max-parents=0` walks all goal history on every `new`. This is negligible at current scale, roughly thousands of commits. If it ever matters, caching root oid and key per goal locally is a follow-up, safe because roots are immutable.
- **Legacy goals** have no trailer, so a retry of a request made before this change can still duplicate. That is acceptable.
- **The id-gap duplicate** described above remains possible after manual remote deletions. It is surfaced by the warning.

## Tests (in `.agents/test_engine_store.py`, using the `World` fixtures)

1. **Exact retry.** Run `new` twice with the same file. The second call returns the same id with `recovered: true` and the same `goal_commit`. The remote has one goal ref, and the second call makes no push (check the trace).
2. **Push lands but reports failure.** Run `cli.main(["new", ...])` in process under `fx.env_of(...)` with `engine.store.push_atomic` patched. The patch performs the real push and then returns `("remote", "simulated")`. Expect `ok` with `recovered: true` and one goal ref. A variant where the patched push does not push and returns `remote` must still exit with code 2 (`remote`).
3. **Concurrent identical calls.** Run ten threads across clones a and b with the same file. All exit 0, all report one id, the remote has exactly one new goal ref, and exactly one result has `recovered: false`. Run it once with a different `ZZZOPS_NOW` per call and once with one shared `ZZZOPS_NOW`, which exercises the `up_to_date` path. Keep the existing distinct-titles concurrency test as it is.
4. **Key reused with different contents.**
   - The same explicit `request_key` with a different spec is refused with `validation`, and `details.goal` is the existing id.
   - The default key with an explicitly different `priority` is also refused.
   - A retry that omits an optional field the original set is recovered.
5. **Same title, distinct specs.** These produce two goals.
6. **Recovery after edit and after close.** Change the goal's title with `zzzops edit`, then rerun the original file. The original goal is recovered. This shows the key is read from the root, not the tip.
7. **Schema.** `validate_new_file` accepts a valid `request_key`. It rejects a key containing `:`, an empty key, and a key of 129 characters or more.
8. **Same-clone fetch race.** `test_a_goal_whose_local_ref_outran_this_fetch_is_recovered_not_duplicated`: patch `engine.store.build_snapshot` so the first snapshot moves `g1000` into `deleted`. The call must refetch, recover G1000 and push nothing. Also cover a goal that really was deleted from the remote: the call refetches once, still finds no match, and allocates a new id.
9. **Up-to-date push.** Two in-process calls with the same file and the same `ZZZOPS_NOW`, where the second call's pre-allocation scan is patched to miss. The second push is `up_to_date`, and the second call returns `recovered: true` with the same `goal_commit`. `push_atomic` without the keyword still returns `ok` for an up-to-date push.
10. **`--policy-ref` on a retry.** Keep `test_policy_ref_is_refused_even_for_a_retry`: after a successful `new`, rerunning it with `--policy-ref` exits 1 with `usage`. This pins the refusal ahead of the scan.

Tests 3 (shared-`ZZZOPS_NOW` variant) and 9 are not yet in the written tests; implement and test_design must add them.

## Out of scope

Issue-based discovery, lock release and capture checkpoints (dropped by the spec, R1 and R12). Idempotency for verbs other than `new`. Per-key claim refs. Backfilling keys onto legacy goals.

## Decision record

- **Root-commit trailer instead of a goal-document field.** The spec allows either. The trailer needs no schema change and cannot be edited away.
- **Conflicts are reported as `validation`** rather than a new error code.
- **Same-clone fetch race (attempt 2)**: refetch once and rescan when nothing matched and `snap.deleted` is not empty. This is the fix the test writer validated (10 of 10 threaded runs). The alternative was to scan deleted tips and confirm a match with a refetch. It needs the same refetch and adds scope rules, so it was not chosen.
- **Up-to-date push counts as a recovery (attempt 2)**: this was handled rather than disputed. The fix is a scoped `push_atomic` keyword. It keeps `recovered` honest and lets the race test assert exactly one fresh create without varying the clock.

- **`--policy-ref` ordering (attempt 3)**: review_design:2:1 was disputed. `session(a)` already refuses `--policy-ref` before the scan (cli.py:97-100, called at cli.py:328), so the scan cannot run with it. The ordering is now stated in §4 so it is kept.

Neither needs a human decision.
