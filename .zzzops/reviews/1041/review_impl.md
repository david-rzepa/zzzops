# G1041 review_impl (attempt 1)

Decision: approved.

## Compliance with the design
- `Git.worktree_paths(cwd, env=None, tries=6)` in engine/gitrun.py follows the design. It uses output only on exit 0, retries with backoff `0.02 * 2**attempt * U(0.5, 1.5)` (the same jitter pattern as store.py and session.py), and returns `(paths | None, rc, stderr)` from the last try.
- `Git.discover` refuses `environment` "cannot find the primary worktree" for both `None` and `[]` (`if not paths`). The message and code are unchanged. `details.git` is the last stderr, stripped and cut to 500 characters, as the design says.
- `registered_worktrees` raises `GitError(["worktree", "list", "--porcelain"], rc, stderr)` when every try fails. That is the same shape `git.run(..., check=True)` raised before. On exit 0 with no entries it still returns `[]`, as before.

## Correctness
- Backoff: the last try does not sleep, so there are 5 sleeps. That is 0.62 s nominal and 0.93 s worst case. The docstring's "about 1.3 s" (copied from the design, which counted 6 sleeps) overstates it. This is harmless.
- Env: discover passes its `base_env()`. registered_worktrees gets `base_env()` by default. That matches the git.run environment (no identity or commit overrides applied to this read). Dropping git.run's `-c maintenance.auto/gc.auto/core.hooksPath` has no effect on `worktree list`.
- Paths keep the exact form Git prints, so Windows `C:/...` forms and the realpath comparisons in `ensure_worktree` do not change.
- Non-blocking note: the helper decodes with `text=True` (the locale encoding), as discover already did. git.run decodes UTF-8 with "replace". For registered_worktrees, this changes the decoding only for non-ASCII paths on a non-UTF-8 locale (Windows). It now matches how discover decodes the primary path, so the two stay consistent. Making both use `encoding="utf-8", errors="replace"` would be a reasonable later hardening. It is not a defect of this goal.

## Missing
- `git grep` on read_dev f4eaf746 finds exactly two `worktree list` callers in the engine, discover and registered_worktrees. Both now use the helper.

## Tests
- Frozen tests are unedited. `git diff ca9e80d1 210b1ca6` touches only gitrun.py, worktree.py and the review artifact.
- The checks passed: the environment tests (11), the real race test 20 times in a row, and the full suite.

## Craft
The change is small and focused, with no dead code and accurate docstrings apart from the backoff figure above.
