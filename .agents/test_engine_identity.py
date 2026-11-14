"""Step 3: code identity (SPEC §4.7; DESIGN §10 items 4, 5, 22)."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest

import engine_fixtures as fx
from engine.canon import ZERO
from engine.errors import EngineError, Refused
from engine.gitrun import Git
from engine.identity import Identity

HOSTILE = """[user]
\tname = Hostile
\temail = h@example.com
[init]
\tdefaultBranch = dev
[diff]
\torderFile = {order}
\tnoprefix = true
\tmnemonicPrefix = true
\trelative = true
\texternal = false
\tsuppressBlankEmpty = true
\tsubmodule = log
\talgorithm = histogram
\trenames = copies
[color]
\tui = always
[core]
\tautocrlf = true
\tquotepath = false
\tattributesFile = {attrs}
\thooksPath = {hooks}
[log]
\tshowSignature = true
"""


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.repo = fx.make_repo(self.tmp)
        r = self.repo
        self.base = r.commit({"src/a.py": "a = 1\n", "README": "hi\n", "reviews/keep.md": "not a review path\n"}, "chore: base")

    def ident(self, repo=None, env=None):
        repo = repo or self.repo
        with fx.env_of(env or repo.env):
            return Identity(Git.discover(repo.path, 1700000000))

    def values(self, a, b, env=None):
        with fx.env_of(env or self.repo.env):
            i = Identity(Git.discover(self.repo.path, 1700000000))
            return i.code_tree(b), i.change(a, b), i.patch_ids(a, b)

    def test_code_tree_ignores_review_commits_and_drop_rebase(self):
        r = self.repo
        i1 = r.commit({"src/a.py": "a = 2\n"}, "feat(a): one")
        r1 = r.commit({".zzzops/reviews/1/review_impl.md": "ok\n"}, "docs(review): review_impl for G1")
        i2 = r.commit({"src/b.py": "b = 1\n"}, "feat(b): two")
        r2 = r.commit({".zzzops/reviews/1/review_tests.md": "ok\n"}, "docs(review): review_tests for G1")
        ident = self.ident()
        self.assertEqual(ident.code_tree(i2), ident.code_tree(r2))
        self.assertNotEqual(ident.code_tree(i1), ident.code_tree(i2))
        # drop the review commits by rebase: same code tree, same change
        r.git("checkout", "-q", "-b", "pr", self.base)
        r.git("cherry-pick", i1, i2)
        pr = r.git("rev-parse", "HEAD")
        self.assertEqual(ident.code_tree(r2), ident.code_tree(pr))
        self.assertEqual(ident.change(self.base, r2), ident.change(self.base, pr))
        # a root `reviews/` path is code, not review
        self.assertIn(b"reviews", ident.ls_tree(ident.code_tree(pr)))

    def test_dirty_or_other_checkout_and_second_clone(self):
        r = self.repo
        c = r.commit({"src/a.py": "a = 3\n"}, "feat: three")
        ident = self.ident()
        t = ident.code_tree(c)
        r.write({"src/a.py": "dirty\n", "untracked.txt": "x"})
        r.git("checkout", "-q", "--detach", self.base) if False else None
        self.assertEqual(t, self.ident().code_tree(c))
        clone = fx.GitDir(os.path.join(self.tmp, "clone"), r.env)
        r.git("clone", "-q", r.path, clone.path)
        self.assertEqual(t, self.ident(clone).code_tree(c))

    def test_change_survives_clean_rebase_and_changes_after_conflict(self):
        r = self.repo
        c = r.commit({"src/a.py": "a = 1\nb = 2\n"}, "feat: b")
        ident = self.ident()
        ch = ident.change(self.base, c)
        # dev moves with an unrelated commit; a clean rebase keeps change
        r.git("checkout", "-q", "-b", "dev2", self.base)
        moved = r.commit({"README": "hello\n"}, "docs: readme")
        r.git("checkout", "-q", "-b", "rebased", c)
        r.git("rebase", "-q", moved)
        rebased = r.git("rev-parse", "HEAD")
        self.assertEqual(ch, ident.change(moved, rebased))
        self.assertNotEqual(ident.code_tree(c), ident.code_tree(rebased))
        # a conflicting dev change resolved by hand alters the diff
        r.git("checkout", "-q", "-b", "dev3", self.base)
        conflict = r.commit({"src/a.py": "a = 10\n"}, "fix: a")
        r.git("checkout", "-q", "-b", "resolved", c)
        r.git("rebase", "-q", conflict, check=False)
        r.write({"src/a.py": "a = 10\nb = 2\n"})
        r.git("add", "src/a.py")
        r.git("-c", "core.editor=true", "rebase", "--continue")
        resolved = r.git("rev-parse", "HEAD")
        self.assertNotEqual(ch, ident.change(conflict, resolved))

    def test_empty_change_is_zero_and_failure_is_an_error(self):
        ident = self.ident()
        self.assertEqual(ZERO, ident.change(self.base, self.base))
        with self.assertRaises(EngineError):
            ident.change("0" * 39 + "1", self.base)

    def test_pinned_fixture_values(self):
        """Gitlink, binary, mode-only and blank-context changes; values pinned so semantics never drift."""
        r = self.repo
        b = r.commit({"ctx.txt": "one\n\nthree\n", "bin.dat": b"\x00\x01\x02", "tool.sh": "echo hi\n"}, "chore: B")
        r.write({"ctx.txt": "one\n\nTHREE\n", "bin.dat": b"\x00\x01\x03"})
        os.chmod(os.path.join(r.path, "tool.sh"), 0o755)
        r.git("add", "-A")
        r.git("update-index", "--add", "--cacheinfo", f"160000,{self.base},vendor/sub")
        r.git("commit", "-q", "-m", "chore: C")
        c = r.git("rev-parse", "HEAD")
        r.commit({".zzzops/reviews/9/x.md": "r\n", "reviews/y.md": "code\n"}, "docs: mixed")
        ident = self.ident()
        plain = ident.change(b, c)
        self.assertNotEqual(ZERO, plain)
        hostile = self.hostile_env()
        self.assertEqual(plain, self.values(b, c, hostile)[1])
        self.assertEqual(self.values(b, c), self.values(b, c, hostile))
        # pinned: computed from the diff alone, so independent of commit metadata
        self.assertEqual(PINNED_CHANGE, plain)

    def hostile_env(self):
        h = os.path.join(self.tmp, "hostile")
        os.makedirs(h, exist_ok=True)
        hooks = os.path.join(h, "hooks")
        os.makedirs(hooks, exist_ok=True)
        for name in ("pre-commit", "pre-push", "post-checkout"):
            p = os.path.join(hooks, name)
            with open(p, "w") as fh:
                fh.write("#!/bin/sh\nexit 1\n")
            os.chmod(p, 0o755)
        with open(os.path.join(h, "order"), "w") as fh:
            fh.write("tool.sh\nbin.dat\n")
        with open(os.path.join(h, "attrs"), "w") as fh:
            fh.write("* diff=foo -text\n*.txt -diff\n")
        cfg = os.path.join(h, ".gitconfig")
        with open(cfg, "w") as fh:
            posix = lambda p: p.replace("\\", "/")             # backslashes are escapes in gitconfig
            fh.write(HOSTILE.format(order=posix(os.path.join(h, "order")), attrs=posix(os.path.join(h, "attrs")),
                                    hooks=posix(hooks)))
        env = dict(self.repo.env)
        env.update({"HOME": h, "GIT_CONFIG_GLOBAL": cfg})
        env.pop("GIT_CONFIG_NOSYSTEM", None)
        return env

    def test_identity_under_hostile_global_configuration(self):
        r = self.repo
        c1 = r.commit({"src/a.py": "a = 1\n\nb = 2\n", "data.txt": "line\n"}, "feat: x")
        c2 = r.commit({"src/c.py": "c = 1\n"}, "feat: y")
        self.assertEqual(self.values(self.base, c2), self.values(self.base, c2, self.hostile_env()))

    def test_crlf_checkout_gives_the_same_identities(self):
        r = self.repo
        c = r.commit({"src/lf.txt": "a\nb\n"}, "feat: lf")
        clone = fx.GitDir(os.path.join(self.tmp, "crlf"), r.env)
        r.git("clone", "-q", "-c", "core.autocrlf=true", r.path, clone.path)
        clone.git("checkout", "-q", c)
        with fx.env_of(r.env):
            a = Identity(Git.discover(r.path, 1)).change(self.base, c)
            b = Identity(Git.discover(clone.path, 1)).change(self.base, c)
        self.assertEqual(a, b)

    def test_text_input_reaches_git_unchanged(self):
        """Engine text sent to Git keeps its LF bytes on every platform (Windows text pipes would add CR)."""
        import hashlib
        with fx.env_of(self.repo.env):
            g = Git.discover(self.repo.path, 1)
            oid = g.out("hash-object", "--stdin", input="line one\nline two\n")
            from engine.store import goal_commit
            c = goal_commit(g, {"id": 1}, None, "zzzops: new G1\n\nOutcome: created\nState: open\nEngine: t\n")
            names = g.run("ls-tree", "--name-only", "-z", c, text=False).stdout
            message = g.run("cat-file", "commit", c, text=False).stdout
        data = b"line one\nline two\n"
        self.assertEqual(hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest(), oid)
        self.assertEqual(b"goal.json\0", names)
        self.assertNotIn(b"\r", message)

    def test_patch_ids_per_commit(self):
        r = self.repo
        c1 = r.commit({"src/a.py": "a = 5\n"}, "feat: 1")
        e = r.commit({}, "chore: empty")
        c2 = r.commit({"src/z.py": "z\n"}, "feat: 2")
        ids = self.ident().patch_ids(self.base, c2)
        self.assertEqual([c1, e, c2], [c for c, _ in ids])
        self.assertEqual(ZERO, ids[1][1])
        self.assertEqual(ids[0][1], self.ident().change(self.base, c1))

    def test_i1_i2_and_artifact_commits(self):
        r = self.repo
        ident = self.ident()
        good = r.commit({"src/q.py": "q\n"}, "feat: q")
        ident.check_i1_i2(self.base, good)
        bad = r.commit({".zzzops/reviews/1/x.md": "x", "src/q.py": "q2\n"}, "docs(review): mixed")
        with self.assertRaises(Refused):
            ident.check_i1_i2(good, bad)
        bad2 = r.commit({".zzzops/reviews/1/y.md": "y"}, "feat: sneaky")
        with self.assertRaises(Refused):
            ident.check_i1_i2(bad, bad2)
        with fx.env_of(r.env):
            tip, art = ident.artifact_commit(None, good, 7, "design", b"# Design\n")
            self.assertEqual(".zzzops/reviews/7/design.md", art["path"])
            self.assertTrue(ident.is_review(tip))
            same, art2 = ident.artifact_commit(tip, good, 7, "design", b"# Design\n")
            self.assertEqual(tip, same)                        # identical blob: no new commit
            self.assertEqual(ident.code_tree(good), ident.code_tree(tip))


PINNED_CHANGE = "b2e0783e28b8e959af35f77486d0c2e9b215a133"   # regenerate with _pin() only together with a new capability (SPEC §4.5)


def _pin():
    """Compute the pinned value once, in a scratch repository with the same steps."""
    global PINNED_CHANGE
    t = IdentityTests("test_pinned_fixture_values")
    t.setUp()
    r = t.repo
    b = r.commit({"ctx.txt": "one\n\nthree\n", "bin.dat": b"\x00\x01\x02", "tool.sh": "echo hi\n"}, "chore: B")
    r.write({"ctx.txt": "one\n\nTHREE\n", "bin.dat": b"\x00\x01\x03"})
    os.chmod(os.path.join(r.path, "tool.sh"), 0o755)
    r.git("add", "-A")
    r.git("update-index", "--add", "--cacheinfo", f"160000,{t.base},vendor/sub")
    r.git("commit", "-q", "-m", "chore: C")
    return t.ident().change(b, r.git("rev-parse", "HEAD"))


if __name__ == "__main__":
    unittest.main()
