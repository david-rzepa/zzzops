"""Step 3: startup environment checks (SPEC §1.5, §4.1; DESIGN §10 item 23, Git part)."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import tempfile
import threading
import time
import unittest
from unittest import mock

import engine_fixtures as fx
from engine.errors import Refused
from engine.gitrun import Git, GitError, check_environment, parse_version, require_environment
from engine.worktree import registered_worktrees


class EnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(self.cleanup)
        self.repo = fx.make_repo(self.tmp)
        self.repo.commit({"a": "1\n"}, "chore: a")

    def cleanup(self):
        for root, dirs, _ in os.walk(self.tmp):
            for d in dirs:
                try:
                    os.chmod(os.path.join(root, d), 0o755)
                except OSError:
                    pass
        shutil.rmtree(self.tmp, True)

    def problems(self, env=None, repo=None):
        repo = repo or self.repo
        with fx.env_of(env or repo.env):
            return check_environment(Git.discover(repo.path, 1))

    def test_usable_environment(self):
        self.assertEqual([], self.problems())

    def test_version_parsing(self):
        self.assertEqual((2, 55, 0), parse_version("git version 2.55.0"))
        self.assertEqual((2, 39, 5), parse_version("git version 2.39.5 (Apple Git-154)"))
        self.assertEqual((2, 47, 1), parse_version("git version 2.47.1.windows.1"))

    def test_old_git_is_refused(self):
        bindir = os.path.join(self.tmp, "fakebin")
        os.makedirs(bindir)
        real = shutil.which("git")
        fake = os.path.join(bindir, "git")
        with open(fake, "w") as fh:
            fh.write(f'#!/bin/sh\nif [ "$1" = version ]; then echo "git version 2.39.5"; exit 0; fi\nexec {real} "$@"\n')
        os.chmod(fake, 0o755)
        env = dict(self.repo.env, PATH=bindir + os.pathsep + self.repo.env["PATH"])
        p = self.problems(env)
        self.assertTrue(p and "2.39.5 is too old" in p[0], p)

    def test_codex_sandbox_is_environment_not_remote(self):
        env = dict(self.repo.env, CODEX_SANDBOX_NETWORK_DISABLED="1")
        with fx.env_of(env):
            with self.assertRaises(Refused) as e:
                require_environment(Git.discover(self.repo.path, 1))
        self.assertEqual("environment", e.exception.code)
        self.assertIn("SETUP", e.exception.message)

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root ignores permissions")
    def test_read_only_git_directory_is_environment(self):
        d = os.path.join(self.repo.path, ".git", "zzzops")
        os.makedirs(d, exist_ok=True)
        os.chmod(d, stat.S_IRUSR | stat.S_IXUSR)
        p = self.problems()
        self.assertTrue(p and "cannot write the Git directory" in p[0], p)

    def test_shallow_clone_is_refused(self):
        self.repo.commit({"b": "2\n"}, "chore: b")
        shallow = os.path.join(self.tmp, "shallow")
        subprocess.run(["git", "clone", "-q", "--depth", "1", "file://" + self.repo.path, shallow], check=True,
                       env=self.repo.env)
        p = self.problems(repo=fx.GitDir(shallow, self.repo.env))
        self.assertTrue(any("shallow clone" in x for x in p), p)


# Git's real stderr when `worktree list` races a concurrent `worktree add` (G1041 design, reproduced on 2.55)
RACE_STDERR = "fatal: failed to read '.git/worktrees/coordinator/locked': No such file or directory\n"


class FlakyWorktreeList:
    """Wraps subprocess.run: the first `failures` `git worktree list` calls exit 128 with `stdout` and Git's
    race stderr (failures=None: every call fails); everything else, and later calls, run for real."""

    def __init__(self, failures, stdout=""):
        self.real = subprocess.run
        self.failures, self.stdout, self.calls = failures, stdout, 0

    def __call__(self, cmd, *args, **kw):
        if "worktree" in cmd and "list" in cmd:
            self.calls += 1
            if self.failures is None or self.calls <= self.failures:
                text = kw.get("text") or kw.get("universal_newlines") or kw.get("encoding")
                out, err = (self.stdout, RACE_STDERR) if text else (self.stdout.encode(), RACE_STDERR.encode())
                return subprocess.CompletedProcess(cmd, 128, out, err)
        return self.real(cmd, *args, **kw)


class ConcurrentWorktreeChangeTests(unittest.TestCase):
    """G1041: `git worktree list` exits non-zero while another process adds or removes a linked worktree."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.repo = fx.make_repo(self.tmp)
        self.repo.commit({"a": "1\n"}, "chore: a")
        self.primary = os.path.realpath(self.repo.path)

    def flaky(self, failures, stdout=""):
        fake = FlakyWorktreeList(failures, stdout)
        for p in (mock.patch("engine.gitrun.subprocess.run", fake), mock.patch("time.sleep"), fx.env_of(self.repo.env)):
            p.__enter__()
            self.addCleanup(p.__exit__, None, None, None)
        return fake

    def test_transient_failure_recovers(self):
        fake = self.flaky(2)
        git = Git.discover(self.repo.path, 1)
        self.assertEqual(self.primary, os.path.realpath(git.primary))
        self.assertEqual(3, fake.calls)

    def test_persistent_failure_refuses_with_git_stderr(self):
        fake = self.flaky(None)
        with self.assertRaises(Refused) as e:
            Git.discover(self.repo.path, 1)
        self.assertEqual("environment", e.exception.code)
        self.assertIn("cannot find the primary worktree", e.exception.message)
        self.assertIn("failed to read '.git/worktrees/coordinator/locked'", (e.exception.details or {}).get("git", ""))
        self.assertGreater(fake.calls, 1)                  # it retried before refusing

    def test_partial_output_after_failed_exit_is_ignored(self):
        fake = self.flaky(1, stdout="worktree /nope\nHEAD " + "0" * 40 + "\n")
        git = Git.discover(self.repo.path, 1)
        self.assertEqual(self.primary, os.path.realpath(git.primary))
        self.assertNotEqual("/nope", git.primary)
        self.assertEqual(2, fake.calls)

    def test_registered_worktrees_retries(self):
        with fx.env_of(self.repo.env):
            git = Git.discover(self.repo.path, 1)
        fake = self.flaky(1)
        paths = registered_worktrees(git)
        self.assertEqual(self.primary, os.path.realpath(paths[0]))
        self.assertEqual(2, fake.calls)
        # exhausted retries keep today's failure: the GitError carrying Git's last exit code and stderr
        fake.failures, fake.calls = None, 0
        with self.assertRaises(GitError) as e:
            registered_worktrees(git)
        self.assertEqual(128, e.exception.rc)
        self.assertIn("coordinator/locked", e.exception.stderr)

    def test_real_concurrent_add_remove(self):
        """No mocks: one thread adds and removes a linked worktree (as `next`'s mirror add does) while readers
        run discover and registered_worktrees. Bounded: 50 cycles or 3 s, whichever comes first."""
        with fx.env_of(self.repo.env):
            git = Git.discover(self.repo.path, 1)
            linked = os.path.join(git.common, "zzzops", "coordinator")
            done, errors, reads = threading.Event(), [], [0]
            lock = threading.Lock()

            def churn():
                deadline = time.monotonic() + 3
                try:
                    for _ in range(50):
                        if time.monotonic() > deadline:
                            break
                        self.repo.git("worktree", "add", "-q", "--detach", linked)
                        self.repo.git("worktree", "remove", "--force", linked)
                except Exception as exc:                   # noqa: BLE001 - reported below
                    errors.append(f"churn: {exc!r}")
                finally:
                    done.set()

            def read():
                while not done.is_set():
                    try:
                        g = Git.discover(self.repo.path, 1)
                        if os.path.realpath(g.primary) != self.primary:
                            errors.append(f"discover gave {g.primary}")
                        paths = registered_worktrees(g)
                        if not paths or os.path.realpath(paths[0]) != self.primary:
                            errors.append(f"registered_worktrees gave {paths}")
                    except Exception as exc:               # noqa: BLE001 - the failure under test
                        errors.append(f"{type(exc).__name__}: {exc}")
                    with lock:
                        reads[0] += 1

            threads = [threading.Thread(target=churn)] + [threading.Thread(target=read) for _ in range(6)]
            start = time.monotonic()
            for t in threads:
                t.start()
            for t in threads:
                t.join(10)
        self.assertFalse([t for t in threads if t.is_alive()], "a thread hung")
        self.assertLess(time.monotonic() - start, 20)                # generous: load only slows it, a hang fails above
        self.assertGreater(reads[0], 0)
        self.assertEqual([], errors[:5], f"{len(errors)} failures in {reads[0]} reads")


if __name__ == "__main__":
    unittest.main()
