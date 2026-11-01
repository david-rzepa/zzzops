# G1001 design review (attempt 2)

**Verdict: changes requested, for one small ordering fix.** The core design is sound and meets the spec. A request key goes in a `Request-Key:` trailer on the immutable root commit. The tips are scanned before allocation and after any failed push. The two additions in attempt 2 hold up against the engine at 54d7e83. One control-flow line contradicts a test that is already written, and should be corrected before implementation starts.

## Prior findings

The card lists no prior open findings. The two issues raised by test_design are resolved:

- **Same-clone fetch race: resolved.** `coordinator_fetch` builds the goal set from the fetch's porcelain lines. `build_snapshot` then runs `local_goal_refs`, and any local ref the fetch did not list goes into `snap.deleted` (store.py:189-193). `cmd_new` also puts `deleted` into `known` (cli.py:335), so a twin whose local ref was written by a parallel fetch in the same clone would currently push G<N+1>. One refetch and rescan, only when nothing matched and `deleted` is not empty, closes this. The argument that one refetch is enough is correct: the local ref exists only because some fetch listed it on the remote, and `new` never deletes goal refs. The test `test_a_goal_whose_local_ref_outran_this_fetch_is_recovered_not_duplicated` and `test_a_deleted_goal_is_not_recovered` pin both sides.
- **Identical root bytes: resolved.** I checked this against git directly. A create-only lease push (`--force-with-lease=<ref>:`) of an oid the remote ref already holds exits 0 with porcelain `=\t...\t[up to date]`. A different oid gets `!` (stale info). Git's up-to-date check runs before the lease check, so today `push_atomic` reports `ok`, and both callers would say they created the goal. A scoped `report_up_to_date` keyword that only `cmd_new` passes keeps every other caller unchanged. Skipping the contents check on that path is safe, because identical bytes mean an identical document and an identical trailer.

## Claims checked against 54d7e83

- `cmd_new` raises `remote` without a refetch. It loops to `gid+1` on `rejected` and records no request identity. The goal fetch refspec has no `+`, so a rewritten goal keeps its old accepted tip and its root is unchanged. All of this is as described.
- `require_writable` holds both the write block and the `--policy-ref` refusal (session.py:185-189). `s.open()` in `cmd_new` is not readonly, so an unreachable remote raises `remote` before any scan. The design's "offline snapshot skips the scan" branch is therefore unreachable in `new`. This is harmless.

## New finding

1. **The scan-before-`require_writable` ordering also skips the `--policy-ref` refusal.** The design says the scan runs before `s.require_writable()`, so that a retry recovers while writes are paused. But `require_writable` is also where `--policy-ref` is refused as a read-only preview. Implemented as written, `new --policy-ref dev --file F` for an existing request returns `recovered: true` (exit 0). The written test `test_policy_ref_is_refused_even_for_a_retry` expects `usage` (exit 1), so a literal implementation fails that test. It also lets a preview-only flag through a write verb. **Fix:** state that `cmd_new` refuses `--policy-ref` (the same `usage` refusal) before the scan, and that only the write-block and engine checks are deferred until after it.

## Non-blocking notes

- **Tests lag the attempt-2 additions.** The work branch has no test for design test 9 (an `up_to_date` push, and `push_atomic` without the keyword still returning `ok`). `test_concurrent_identical_new_creates_one_goal` runs only with distinct clocks, and the shared-`ZZZOPS_NOW` variant is missing. The test node should add both, or the design should drop them.
- **A residual compound race.** The refetch rule handles one same-clone overtaking. Suppose the refetched snapshot again has a `deleted` id that a parallel same-clone fetch wrote during the refetch, and that id is a twin created after this call's first scan. Then the call allocates above it and both goals land. This needs an unrelated deleted ref plus a new twin plus a second overtaking inside one refetch window. It does not arise in the identical-request test, where only one goal can ever be pushed. The cheap hardening is to repeat the refetch while `deleted` gains ids (bounded by the existing 30 s deadline). Alternatively, name it under Risks. Either is acceptable.
