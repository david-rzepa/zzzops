# Review of tests for G1001 (re-review, attempt 2)

Subject: tests checkpoint b81fe97 (base 54d7e83). Previous approved tests: c2a6bcc.

## Scope of change
- `git diff c2a6bcc b81fe97 -- .agents` touches only `.agents/test_engine_store.py`: +24 lines, one new test
  `IdempotentNewTests.test_a_failed_request_key_scan_is_an_engine_bug_and_pushes_nothing`. No other test changed.
- The `commands` list is the same as for c2a6bcc and e760a14: the `test_engine_store.py` discover and the `test_engine_*.py` discover.

## The new test
- It creates one existing goal (G1000) so `find_request_key` has a tip and actually runs `git log`.
- It patches `Git.run` so that only the call with `log`, `--stdin` and `--max-parents=0` gets `--no-such-option` added. Real git then exits non-zero. Other git calls go through unchanged. Each matching call is recorded, and `len(scans) >= 1` proves the patch reached the scan.
- It asserts `(rc, error.code) == (1, "engine_bug")`, that the remote goal refs are still only `refs/heads/zzzops/goal/g1000`, and that `self.pushes() == []` after `reset_trace()`, so nothing was pushed.

## Evidence (run on a git-archive of b81fe97)
- `python3 -m unittest discover -s .agents -p 'test_engine_*.py'` gives `Ran 315 tests ... OK`.
- `python3 -m unittest discover -s .agents -p 'test_engine_store.py'` gives `Ran 53 tests ... OK`.
- I replaced only `engine/store.py` with the 0e491ec version (pre-fix: `if p.returncode != 0: return []`). The store suite then gives `Ran 53 tests ... FAILED (errors=1)`, and the only failure is the new test, with `KeyError: 'error'`: `new` succeeded and allocated a goal instead of refusing. The test is red without the fix and green with it, and no other test depends on the change.

## Findings
None. The test is targeted and uses a real git failure, not a faked return code. The only other thing it relies on is the scan's argv shape, and the `scans` assertion would catch it if that shape changed. Minor, not blocking: against the pre-fix code it fails with a KeyError rather than a clean assertion. It still fails, and the cause is clear.

## Decision
approved
