# G1041 design: primary worktree discovery survives concurrent `git worktree` changes

Revision 1.

## Outcome

`Git.discover` stops refusing with `environment: cannot find the primary worktree` when another process is adding or removing a linked worktree at the same moment. A real missing primary worktree is still refused with the same message. The same fix covers `registered_worktrees` (engine/worktree.py), which runs the same command during `start` and has the same race.

## The race (reproduced)

`git worktree list --porcelain` is not safe against a concurrent `git worktree add` or `remove`. It reads `.git/worktrees/<id>/` while the other process is still writing or deleting it. Then it dies with exit 128, sometimes before it prints anything. `discover` ignores the exit status, so when stdout is empty it finds no `worktree` line and refuses.

In the failing test, the concurrent process is ZzzOps itself. `next` calls `update_mirror` (store.py), and the first `next` to take `coordinator.lock` runs `git worktree add --detach <common>/zzzops/coordinator`. The other 19 `next` calls run `discover` at that moment. The lock only orders mirror updates against each other, not against `worktree list`.

Local reproduction (Git 2.55, a Python loop of 8 to 20 threads running `git worktree list --porcelain` while one thread adds, or removes and re-adds, a worktree at `.git/zzzops/coordinator`):

| Concurrent operation | Failures seen | Exit, stdout, stderr |
|---|---|---|
| add only (what `next` does), 400 to 600 repos | 1 to 10 per run | 128, main entry printed, `fatal: failed to read '.git/worktrees/coordinator/locked': No such file or directory` (add creates the `locked` file and then deletes it) |
| remove then add, 200 repos | 17 | 128, mostly main entry printed, `fatal: Invalid path '<repo>/.git/worktrees'`; once **nothing printed**, `fatal: Invalid path '<repo>/.git/worktrees/coordinator'` |

In 100 local runs of the test itself (60 unpinned, 40 pinned to 2 CPUs) it never failed. With Git 2.55, the add-only failure prints the main entry before Git dies, so the current parser still finds a primary worktree. CI ran Git **2.56.0** (ubuntu-24.04 image 20261025; job log of run 41466563005 attempt 1). There, 2 of 20 calls got empty stdout. So on 2.56 the die happens before anything is printed (or the output is not flushed). In both versions the cause is the same: `worktree list` exits non-zero while a linked worktree is mid-change. No lock file of ours or temporary worktree is involved beyond the mirror's own `worktree add`. Git's own `locked` marker during add is one of the files it trips on.

## Approach

One helper on `Git`, used by both callers:

```python
def worktree_paths(cwd, env) -> list[str] | None:
    """Paths from `git worktree list --porcelain`, retried while Git fails (a concurrent add/remove)."""
    for attempt in range(6):
        p = subprocess.run(["git", "-C", str(cwd), "worktree", "list", "--porcelain"], ...)
        if p.returncode == 0:
            return [line[len("worktree "):] for line in p.stdout.splitlines() if line.startswith("worktree ")]
        time.sleep(0.02 * 2 ** attempt * random.uniform(0.5, 1.5))     # about 1.3 s worst case in total
    return None    # last stderr kept for the refusal details
```

- **Exit status is checked.** Output is used only when the exit code is 0. A non-zero exit can leave partial output, so it is never parsed.
- **Bounded retry with jittered backoff.** A concurrent add or remove takes milliseconds. Six tries over about 1.3 s are plenty, and a healthy repository pays nothing (the first try succeeds). The jitter pattern is the one already in store.py:133 and session.py:271.
- **`discover`:** if the helper returns `None`, or a list with no entries, it refuses `environment`, "cannot find the primary worktree" as today. Details now carry `{"git": <last stderr, at most 500 chars>}`, as the not-a-repository refusal already does.
- **`registered_worktrees(git)`** (worktree.py) calls the same helper with `git.primary`. On `None` it raises the `GitError` that `git.run(..., check=True)` raises today, so its failure path does not change. Only the transient case now succeeds.

The primary worktree is still the first entry of `git worktree list --porcelain`, so SPEC's definition (SPEC.md line 35) and every printed `--repo <primary>` path keep exactly the form Git prints.

## Alternatives rejected

- **Derive the primary from the common directory** (its parent when it ends in `.git`). This skips the race in the common layout, but it is a second source of truth. The path form differs from Git's on Windows (`C:\…` from `Path.resolve` against `C:/…` from Git), and the printed `--repo` and the realpath comparisons in worktree.py would change with it. It is also wrong for `--separate-git-dir`, submodule `.git/modules/…` and `core.worktree` layouts, so it would still need the worktree list as a fallback. That means more code and two behaviours for a P2.
- **Parse output even on a non-zero exit.** With Git 2.55 this would often work, because the main entry prints first. It fails on 2.56 (empty stdout), and it trusts output from a process that died partway.
- **Hold `coordinator.lock` around `worktree list`.** This serializes every verb on a file lock. It also does not cover worktree changes by users or by `start` and `abandon` in other processes.
- **Make `update_mirror` not use a worktree.** That is out of scope: the mirror is a SPEC §4.3 contract, and users can add worktrees themselves.

## Interfaces and data

- No CLI, output, stored-format or SPEC contract change. The refusal code and message are unchanged; `details` gains a `git` key (additive). So no SPEC or HISTORY edit is needed. If the reviewer reads the `details` key as a contract, a one-line SPEC §1.5 note can carry it.
- Code: engine/gitrun.py (the helper and its use in `discover`); engine/worktree.py (`registered_worktrees` uses the helper).

## Risks

- **A real, persistent `worktree list` failure** (for example, a corrupt `.git/worktrees/<id>`) now costs about 1.3 s before the same refusal. This is acceptable: it is rare, and the refusal now shows Git's stderr, which makes it easier to fix.
- **Retry exhausted under extreme churn** (worktrees changing continuously for more than a second). This is still possible, but far less likely than one bad read, and the refusal is unchanged.

## Tests

In `.agents/test_engine_environment.py` (in-process, no network):

1. **Transient failure recovers.** Patch `engine.gitrun.subprocess.run` with a wrapper that makes the first two `worktree list` calls return exit 128, empty stdout and Git's real stderr text, then delegates to the real function. `Git.discover` returns the real primary, and the wrapper saw three `worktree list` calls. Patch `time.sleep` to keep the test fast.
2. **Persistent failure refuses.** The wrapper always fails. `discover` raises `Refused("environment")` with the message "cannot find the primary worktree" and `details["git"]` containing the stderr.
3. **Non-zero exit with partial output is not parsed.** The first call returns exit 128 with a bogus `worktree /nope` line, the second succeeds. The real primary is used, not `/nope`.
4. **`registered_worktrees` retries.** The same wrapper with one failure returns the real list.
5. **Real race (no mocks).** Using the race above: one thread adds and removes a linked worktree in a loop while others call `Git.discover`. Every call returns the primary. This test is bounded: about 50 add/remove cycles, under 5 s.

Existing: `test_engine_store.PolicyTests.test_twenty_concurrent_next_after_dev_moves` unchanged. For acceptance, the implementer runs it 50 times in a loop (`for i in $(seq 50); do python3 -m unittest test_engine_store.PolicyTests.test_twenty_concurrent_next_after_dev_moves || break; done`, from `.agents`), and CI's normal run covers Git 2.56.

## Out of scope

- Hardening other Git reads against concurrent worktree changes (none are known to fail).
- Changing how or where the coordinator mirror is created.
- Reporting the `worktree list` atomicity problem upstream to Git (worth a note, not this goal).
