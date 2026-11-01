"""Step 3: startup environment checks (SPEC §1.5, §4.1; DESIGN §10 item 23, Git part)."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import tempfile
import unittest

import engine_fixtures as fx
from engine.errors import Refused
from engine.gitrun import Git, check_environment, parse_version, require_environment


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


if __name__ == "__main__":
    unittest.main()
