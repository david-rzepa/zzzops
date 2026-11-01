# G1001 review_impl: commit 0e491ec against design attempt 3

**Decision: changes_requested** (one finding, small fix)

Reviewed: `git diff 54d7e83 0e491ec` (excluding `.zzzops/reviews`). The implementer's own diff (`c2a6bcc..0e491ec`) touches only `cli.py`, `store.py`, `schemas.py`, `CLI_USAGE.md` and the add-zzzops-goal skill. The frozen tests (`test_engine_store.py`, `engine_fixtures.py`) are unchanged since test_design, so no test was weakened. run_tests passed all three commands.

## Design conformance

The design is followed point by point:
- §1 key: `request_key_of`, `norm_depends_on` (bools excluded) and the colon-free `REQUEST_KEY` regex.
- §2 trailer: `goal_message(request_key=)` writes the `Request-Key:` trailer before `Engine:`, and only `cmd_new` passes it.
- §3 scan:
  - one `git log --stdin --max-parents=0` over the non-deleted accepted tips;
  - the head line is parsed with `^zzzops: new G(\d+)$`;
  - the root `goal.json` id is cross-checked;
  - `scan_request_key` refetches once when nothing matched and `snap.deleted` is non-empty.
- §4 control flow:
  - `session(a)` is still called before `s.open()` and the scan, so `--policy-ref` is still refused first;
  - the scan runs before `require_writable`, and only when the snapshot is current;
  - `up_to_date` is treated as a recovery;
  - a failed or rejected push refetches, then rescans, then falls back to today's refusals, now with the retry hint;
  - a conflict returns `validation` with `details.goal` and `details.fields`;
  - when several goals match, the lowest id wins and a `duplicate_request_key` warning is added;
  - `created.recovered` and `created.request_key` are present on both paths.
- `push_atomic(report_up_to_date=)` defaults to false, so other callers are unchanged.

Concurrency and recovery paths, checked:
- **Rejected push, twin won**: the rescan after the refetch finds the twin and returns recovered. A rejection by an unrelated goal loops to `gid+1`, and every failed push rescans before the next allocation.
- **`remote` push that landed**: the refetch and rescan recover it. One that did not land still refuses with `remote` (exit 2).
- **Identical clock**: the `up_to_date` porcelain check (exit 0 and every ref line `=`) is reported only when `cmd_new` asks for it.
- **Spurious conflicts**: the contents check compares against the root document. `cmd_new` stores `links`, `skip`, `release`, `graph`, `state` and `priority` exactly as given, and `depends_on` is normalised on both sides, so an exact retry cannot conflict with itself.

**The extra ancestor check** (`git.is_ancestor(oid, tips[g])`) is sound. A single `git log` over every tip loses which tip reached a root, so the check confirms that the root claiming `new G<n>` really lies in G<n>'s own history. That only matters for hand-crafted or cross-linked histories. It costs one subprocess per match, and matches are rare. It can only drop a hit, never add a wrong one, so I'm keeping it.

The code reads like its surroundings: `from engine import store` replaces the scattered local imports, and the helpers are small and docstringed. The docs are updated (the CLI_USAGE `new` row and skill step 3).

## Finding 1 (implement): a failed scan is treated as "no match", so `new` allocates a duplicate

`store.find_request_key` runs `git log ... check=False`, and on a non-zero exit it returns `[]`. A `read_goal_json`/`is_ancestor` failure on a match is also dropped silently, but those are per hit and acceptable as the design's cross-check. Every caller reads `[]` as "nothing matched":
- **Pre-allocation scan**: a retry after a push that landed allocates a fresh id and pushes a second goal for the same request.
- **Scan after a `rejected` push**: the loop allocates `gid+1` beside the twin that won the race.

**Consequence**: the guarantee this goal exists for ("does not allocate a second id") silently fails, with no error and no warning. That is exactly the duplicate the goal is meant to stop. It also contradicts design §3 ("Only then may the caller allocate an id"), and it goes against the engine's own convention: `errors.EngineError` is documented as "an internal failure that must never be mistaken for an empty result (for example a failing git diff)". It is unlikely in practice (it needs missing objects, a corrupt store or a broken partial clone), but refusing costs nothing. The user reruns once the repository is healthy, and nothing has been written.

**Fix**: in `find_request_key`, on `p.returncode != 0` raise `EngineError(f"request-key scan failed: {p.stderr.strip()[:200]}")` instead of returning `[]`. `main` already maps it to `engine_bug` (exit 1) before anything is written. Equivalently, use `check=True` and convert the `GitError` in `scan_request_key`. Note that a bare `GitError` is not caught by `main`, so it must not be left to propagate. No test change is needed. A one-line unit test (patch `git.run` to fail and expect `engine_bug` with no push) would be welcome but is optional.

## Non-blocking note

REPAIR.md's "Purge data from a goal's history" writes a new parentless root `zzzops: purge G<id>` without the `Request-Key:` trailer. After a purge, rerunning the original request creates a new goal. This is rare, manual, and in the same class as the design's accepted "legacy goals" risk. A half-sentence in that recipe (copy the `Request-Key:` line, or accept that retries no longer recover) would close it, but it is not required for this goal.
