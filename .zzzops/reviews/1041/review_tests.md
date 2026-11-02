# G1041 review_tests (attempt 2)

Tests: ca9e80d (fix for review_tests:1:1 on top of 61edb9c), `ConcurrentWorktreeChangeTests` in `.agents/test_engine_environment.py`.

## Prior finding

- review_tests:1:1: **resolved**. `test_real_concurrent_add_remove` now uses a 3 s churn deadline. After the `join(10)` calls it asserts that no thread is still alive (`"a thread hung"`), so a hang is detected by thread liveness. The wall-clock bound is now 20 s, a safety net and not a budget. The diff changes only these three lines and the docstring.

## What I ran

- The recorded commands, on an export of ca9e80d (current code, no implementation): `python3 -m unittest discover -s .agents -p 'test_engine_environment.py'` failed 5 of the new tests (2 errors, 3 failures, counting the race test when it fails). The 20-run race loop failed 7 of 20. So the tests still catch the bug.
- With a throwaway prototype of the design's helper (six retries, jittered backoff, exit status checked, `details["git"]`, `GitError` from `registered_worktrees`): all 11 tests pass, and the race loop passed 20 of 20.
- Under load (3 rounds of 16 parallel runs pinned to 2 CPUs, the setup that failed in round 1): 48 of 48 passed, each taking 3.4 to 3.8 s. That is well under 20 s.

## Notes (not findings)

- If a reader really hung, its non-daemon thread would keep the test process alive after the assertion fails. CI's job timeout would still end the run, and the failure message would already be printed. That is acceptable for a test whose readers stop on `done`.

Decision: approved (no open findings).
