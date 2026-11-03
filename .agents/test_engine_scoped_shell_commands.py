"""Run scoped review commands as printed, through the shells used by agents."""
import os
import shutil
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import engine_fixtures as fx
from engine import card, render
from engine.errors import Refused
from engine.identity import view_paths
from test_engine_card_budget import res_of


class ScopedShellTests(unittest.TestCase):
    def test_current_previous_and_approval_commands_preserve_literal_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = fx.make_repo(tmp)
            names = ["tests/O'Connor.py", "tests/curly’quote.py", "tests/low‚quote.py", "tests/reversed‛quote.py", "tests/space $dollar `tick`.py"]
            if os.name != "nt":
                names += ["tests/mixed' $(touch INJECTED) `touch TICK` \"quote\" [*]?.py",
                          "tests/line'\nfeed.py"]
            files = {name: "before\n" for name in names}
            files.update({"impl/own.txt": "before\n", ".zzzops/reviews/1000/review.md": "before\n"})
            base = repo.commit(files, "test: before")
            old = repo.commit({p: "middle\n" for p in files}, "test: middle")
            tip = repo.commit({p: "after\n" for p in files}, "fix: after")
            cp = {"base": base, "commit": tip, "tree": repo.git("rev-parse", tip + "^{tree}"), "change": "a" * 40}
            old_cp = dict(cp, commit=old, change="b" * 40)
            class Reader(render.Reader):
                def blob_view(self, text):
                    oid = repo.git("hash-object", "-w", "--stdin", input=text)
                    return {"blob": oid, "read": f"git cat-file -p {oid}", "summary": text[:120]}
            reader = Reader()
            ctx = render.Ctx("zzzops", 0, {}, {}, reader=reader)
            session = SimpleNamespace(git=SimpleNamespace(exists=lambda oid: True))
            def previous(cur):
                records = {"implement": {"output": {"code": cur}}, "test_design": {"frozen": names},
                           "review_impl": {"status": "done", "findings": [], "reviewed": {"code": old_cp}}}
                return card.previous(session, res_of(records=records), "review_impl", {})["interdiff"]
            commands = [
                (card.checkpoint_view(cp, scope=names)["diff"], ["diff", base, tip], names, None),
                (render.checkpoint_view(ctx, cp, exclude=names)["diff"], ["diff", base, tip], None, names),
                (previous(cp), ["diff", old, tip], None, names),
            ]
            commands += [(card.checkpoint_view(cp, scope=[name])["diff"], ["diff", base, tip], [name], None)
                         for name in names]
            moved = dict(cp, base=old)
            with patch("engine.card.Identity") as identity:
                identity.return_value.sync_merges.return_value = [tip]
                commands.append((previous(moved), ["log", "-p", "--first-parent", "--no-merges", old + ".." + tip], None, names))
                identity.return_value.sync_merges.return_value = []
                commands.append((previous(moved), ["range-diff", base + ".." + old, old + ".." + tip], None, names))
            many = names + [f"tests/absent{i}.py" for i in range(13)]
            for view in (card.checkpoint_view(cp, scope=many, reader=reader), render.checkpoint_view(ctx, cp, scope=many)):
                blob = view["diff"]
                self.assertIsInstance(blob, dict)
                command = repo.git("cat-file", "-p", blob["blob"])
                self.assertEqual(command, repo.git(*blob["read"].split()[1:]))
                commands.append((command, ["diff", base, tip], many, None))
            shells = [name for name in (("pwsh",) if os.name == "nt" else ("bash", "pwsh")) if shutil.which(name)]
            self.assertTrue(shells, "No supported shell available for command execution")
            for command, args, scope, excluded in commands:
                expected = repo.git(*args, "--", *view_paths(scope, excluded))
                self.assertTrue(expected)
                for shell in shells:
                    with self.subTest(shell=shell, args=args, scope=scope):
                        argv = ([shell, "-c", command] if shell == "bash" else
                                [shell, "-NoProfile", "-NonInteractive", "-Command", command + "; exit $LASTEXITCODE"])
                        result = subprocess.run(argv, cwd=repo.path, env=repo.env, text=True, capture_output=True)
                        self.assertEqual(0, result.returncode, result.stderr)
                        self.assertEqual(expected, result.stdout.strip())
            self.assertFalse(os.path.exists(os.path.join(repo.path, "INJECTED")))
            self.assertFalse(os.path.exists(os.path.join(repo.path, "TICK")))
            failure = render.scoped_git_command(["diff", "invalid-commit", tip], names)
            for shell in shells:
                argv = ([shell, "-c", failure] if shell == "bash" else
                        [shell, "-NoProfile", "-NonInteractive", "-Command", failure + "; exit $LASTEXITCODE"])
                result = subprocess.run(argv, cwd=repo.path, env=repo.env, text=True, capture_output=True)
                self.assertEqual(128, result.returncode, result.stderr)

    def test_native_apostrophe_path_in_host_shell(self):
        # Native Windows must exercise pwsh, not a bash/WSL executable found on PATH.
        shell = "pwsh" if os.name == "nt" else "bash"
        self.assertIsNotNone(shutil.which(shell), "The native CI shell must be installed")
        with tempfile.TemporaryDirectory() as tmp:
            repo = fx.make_repo(tmp)
            name = "tests/O'Connor.py"
            base = repo.commit({name: "before\n", "impl/own.txt": "before\n"}, "test: before")
            tip = repo.commit({name: "after\n", "impl/own.txt": "after\n"}, "fix: after")
            cp = {"base": base, "commit": tip, "tree": repo.git("rev-parse", tip + "^{tree}"), "change": "a" * 40}
            ctx = render.Ctx("zzzops", 0, {}, {})
            for command, scope, excluded in [
                (card.checkpoint_view(cp, scope=[name])["diff"], [name], None),
                (render.checkpoint_view(ctx, cp, exclude=[name])["diff"], None, [name]),
            ]:
                expected = repo.git("diff", base, tip, "--", *view_paths(scope, excluded))
                argv = ([shell, "-NoProfile", "-NonInteractive", "-Command", command + "; exit $LASTEXITCODE"]
                        if shell == "pwsh" else [shell, "-c", command])
                result = subprocess.run(argv, cwd=repo.path, env=repo.env, text=True, capture_output=True)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual(expected, result.stdout.strip())
                self.assertTrue(expected)

    def test_missing_portable_python_is_an_explicit_environment_problem(self):
        with patch("engine.render.shutil.which", return_value=None):
            with self.assertRaises(Refused) as error:
                render.scoped_git_command(["diff", "a", "b"], ["O'Connor.py"])
        self.assertEqual("environment", error.exception.code)


if __name__ == "__main__":
    unittest.main()
