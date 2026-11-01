# G1001 review_tests (attempt 1)

Reviewed: c2a6bcc on zzzops/work/g1001 (base 54d7e83; change a20de5c), `.agents/test_engine_store.py` (+517) and `.agents/engine_fixtures.py` (+7/-1), against design attempt 3 (blob e13cc44).

## Verdict: approved, no material findings

## Coverage against the design's test list
| Design test | Covered by |
|---|---|
| 1 Exact retry: same id, recovered, same goal_commit, one ref, no push | test_exact_retry_recovers_the_same_goal_without_a_push (it checks the trace for no `git push`), plus the cross-clone copy test and the trailer-placement test |
| 2 Push lands but reports `remote`, and the not-landed variant exits 2 | test_push_that_landed_but_reported_remote_failure_is_recovered, test_push_that_did_not_land_still_reports_remote (also checks the "retry" hint), test_rejected_push_recovers_a_twin_that_won_the_race |
| 3 Ten threads across a/b, distinct clocks and one shared clock | race_identical with both clock variants: all rc 0, one id, one goal_commit, one ref, exactly one recovered:false. The distinct-titles test is unchanged |
| 4 Key reuse conflict, priority conflict, omitted optional field recovers | explicit-key/spec (checks details.goal, fields, message), default-key/priority (fields == ["priority"]), omits-optional, explicit-default-value, release-moved |
| 5 Same title, distinct specs | test_same_title_with_distinct_specs, plus the distinct explicit keys and distinct depends_on tests |
| 6 Recovery after edit and after close | test_recovery_after_the_title_was_edited (root != tip, the title is the original), test_recovery_of_a_closed_goal |
| 7 Schema | NewFileSchemaTests: `:`, empty, 129/200 characters, leading punctuation, non-strings; valid up to 128; absent key |
| 8 Same-clone fetch race, plus a goal really deleted | test_a_goal_whose_local_ref_outran_this_fetch... (build_snapshot patched, at least 2 snapshots, no push), test_a_deleted_goal_is_not_recovered (exactly one extra fetch against a measured baseline, then it allocates 1002) |
| 9 Up-to-date push, and the keyword-less ok | test_an_up_to_date_create_push_counts_as_recovered, test_push_atomic_reports_up_to_date_only_when_asked (it also checks that a real create stays ok and a lost lease stays rejected) |
| 10 --policy-ref on a retry | test_policy_ref_is_refused_even_for_a_retry |
| Scan details (§3) | legacy roots without a trailer, a head id mismatch, a doc id mismatch, several matches giving the lowest id plus a duplicate_request_key warning, no tips giving no `git log`, and one `log --stdin --max-parents=0` per scan |
| Writes (§4) | test_exact_retry_recovers_while_writes_are_blocked (engine.min=99 recovers, while a new request still gets engine_too_old) |

## Fail-before-implementation (run in a temporary detached worktree at c2a6bcc, since removed)
- `test_engine_store.py`: 52 tests, 30 fail (12 failures and 18 errors). Every one is a G1001 test, and each fails for the intended reason:
  - `recovered` or `request_key` is missing from `created`.
  - `request_key` is an unknown key.
  - `find_request_key` is absent.
  - `push_atomic` has no `report_up_to_date`.
  - `remote` is returned without the retry hint.
  - The races produce duplicate ids (1000..1009).
- Five new tests pass before implementation. They are intended regression guards, not failures that are missing:
  - distinct depends_on.
  - document id mismatch.
  - policy-ref refusal (pinned on purpose).
  - invalid keys rejected (today as unknown key).
  - absent key valid.
- Full `test_engine_*.py`: 314 tests. The only failures are the same 30. The fixture change, which makes `World.new` give a unique spec per call, breaks no existing test. No existing test asserts the old spec text.

## Determinism
- The design makes the race outcomes deterministic: one id, one fresh create. Only the path a loser takes depends on timing (scan hit, rejected then rescan, `up_to_date`, or the deleted-ref refetch).
- So the threaded assertions are not timing-sensitive for a correct implementation. Under the design's rules every path ends in recovery:
  - A server-side create-only race reports `!`, which is `rejected`, then a rescan.
  - An advertised identical oid reports `=`, which is `up_to_date`.
- The shared-clock variant reaches `up_to_date` only by chance. Test 9 is the deterministic guard for it, and I agree with the test writer.
- I confirmed both clones commit with the same identity (fixture gitconfig) and the same `ZZZOPS_NOW`. Same-second roots are therefore byte-identical, and test 9's `results == ["up_to_date"]` assertion checks this itself.
- Residual CI risk: the same per-clone fetch-lock contention as the existing `test_concurrent_new_gets_distinct_ids`, which coordinator_fetch retries 4 times. That risk is not new.

## Non-blocking notes
- The mock patches on `engine.store.push_atomic`, `build_snapshot` and `find_request_key` assume that `cmd_new` keeps importing them from `engine.store` at call time, as it does today, and that `push_atomic` gets `report_up_to_date` as a keyword (test 9 asserts `kws == [{"report_up_to_date": True}]`). Both follow the design and today's code. The implementer should keep them.
- test_a_root_whose_document_id_differs_never_matches has a deliberately loose assertion: it only checks that 1000 is not recovered. That is adequate for a negative guard.
