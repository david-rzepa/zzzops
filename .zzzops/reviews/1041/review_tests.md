# G1041 review_tests (attempt 1)

Tests: 61edb9c, `ConcurrentWorktreeChangeTests` in `.agents/test_engine_environment.py`.

## What I ran

- Current code (Git 2.55, Python 3.14): all five new tests fail (2 errors, 3 failures); the real-race test failed 10 of 20 runs. So the tests do catch the bug.
- I applied a throwaway prototype of the design's helper (retry six times with jittered backoff, exit status checked, `details.git`, `registered_worktrees` raises `GitError` when retries run out) to a scratch copy. All 11 tests pass. The race test passed 30 of 30 runs unloaded (about 0.4 s), 10 of 10 pinned to one CPU (about 1.3 s) and 40 of 40 as 8 parallel runs on 2 CPUs (4.1 to 4.4 s).

## Assessment

- Mocking `engine.gitrun.subprocess.run` replaces `run` on the shared `subprocess` module, so it catches every caller: the helper in gitrun, `Git.run` and `check_output`. The wrapper matches on list elements (`"worktree"`, `"list"`), so it works whatever `-C` or `-c` prefix the implementation uses, and it handles both text and bytes. It keeps the real function from before the patch. The tests do not over-specify the helper. They require only exit-status checking, at least one retry, the call counts from the design (3, 2, 2), `details["git"]` and the existing `GitError`. They do not fix a name, a backoff schedule or a retry count, except that persistent failure must retry more than once.
- `time.sleep` is patched globally. That is fine, and it would only slow the tests down, not break them, if the implementation imported `sleep` directly.
- The recorded commands run from the worktree root (`python3 -m unittest discover -s .agents ...`, then `cd .agents && for ...`) and are correct.
- On CI, this test runs only on Linux (3.10 and 3.14). The Windows and macOS jobs run only `NATIVE_COVERAGE`, so cross-platform file-locking behaviour of `worktree remove` is not a concern.

## Finding

1. (test_design) `test_real_concurrent_add_remove` asserts `time.monotonic() - start < 5`, but its own churn deadline is 4 s, so under load the margin is the last add/remove cycle plus each reader's last discover and `registered_worktrees`. With a correct implementation (the prototype) under load (16 parallel runs on 2 CPUs), it took 4.4 to 5.3 s and failed once: `AssertionError: 5.135... not less than 5`. A loaded CI shard can reach this. Since the wall time is a budget and not a property of the fix, remove the wall-clock assertion, or make it generous (for example 20 s). Detect hangs with `assertFalse(any(t.is_alive() for t in threads))` after the joins. Optionally, lower the churn deadline (for example 3 s) so the test stays near its budget.

Decision: changes_requested (one finding).
