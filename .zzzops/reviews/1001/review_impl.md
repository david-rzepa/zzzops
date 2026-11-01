# G1001 review_impl (re-review): 62196dd

**Decision: approved**

## Scope
- I compared the range-diff of `54d7e83..0e491ec` with `54d7e83..62196dd`. Commits 1-10 are identical, so 0e491ec is unchanged.
- Four commits were added on top:
  - 93211eb: the prior review document
  - 53e7b5e: the fix
  - b81fe97: the test
  - 62196dd: the review_tests document
- Outside `.zzzops/reviews`, the diff `0e491ec..62196dd` touches only `engine/store.py` (+5/-3) and `.agents/test_engine_store.py` (+24).
- The run_tests tree 851e522 matches 62196dd exactly once `.zzzops/reviews` is excluded, so the passing checks cover this code: 53, 315 and the full suite all passed.

## Prior finding
- **review_impl:1:1: resolved.** `find_request_key` now raises `EngineError("request-key scan failed: <stderr[:200]>")` when the exit code is non-zero, instead of returning `[]`. The docstring states the contract.
  - Both call sites go through `cli.scan_request_key`: before allocation, and after a failed or rejected push.
  - `cli.main` catches `EngineError` at line 587 and returns `engine_bug` with exit 1.
  - Before allocation, nothing has been written. After a rejected push, nothing of ours landed. After an uncertain `remote` push, a rerun recovers through the scan once the repository is healthy.
  - The new test makes the real `git log --stdin --max-parents=0` fail by appending an invalid option. It then checks `(1, engine_bug)`, that the scan ran, that no new goal ref exists and that no push happened.

## New findings
None.
