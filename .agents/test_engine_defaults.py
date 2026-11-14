"""G1047: read-only current-default comparison and opaque review receipts.

Most cases exercise the public directory-validation verb in process: no Git
journey is needed to compare three sets of files. The repository test covers
the separate committed-policy/preview/next/write wiring once.
"""
from __future__ import annotations

import contextlib
import hashlib
import importlib
import io
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import engine_fixtures as fx
from engine import cli


def blob(content):
    data = content.encode() if isinstance(content, str) else content
    data = data.replace(b"\r\n", b"\n")
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def put(root, rel, content):
    p = Path(root) / rel
    if content is None:
        p.unlink(missing_ok=True)
    else:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content.encode() if isinstance(content, str) else content)


def call(*args, env=None):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), (fx.env_of(env) if env else contextlib.nullcontext()):
        rc = cli.main(list(args))
    return rc, json.loads(out.getvalue())


def run_printed_command(command, cwd):
    if os.name == "nt":
        powershell = shutil.which("pwsh") or shutil.which("powershell")
        if powershell is None:
            raise RuntimeError("PowerShell is required to verify printed Windows commands")
        # A quoted executable path needs the PowerShell call operator. Applying
        # it to an unquoted command name is valid too; preserve an existing one.
        invocation = command if command.lstrip().startswith("&") else "& " + command
        return subprocess.run([powershell, "-NoProfile", "-NonInteractive", "-Command", invocation],
                              shell=False, capture_output=True, text=True, cwd=cwd)
    return subprocess.run(command, shell=True, capture_output=True, text=True, cwd=cwd)


class DefaultsCase(unittest.TestCase):
    def setUp(self):
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        self.tmp = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="default policy's ")))
        self.shipped = self.tmp / "plugin defaults"
        self.here = self.tmp / "repository policy"
        shutil.copytree(fx.TEMPLATES, self.shipped)
        for name in ["optional", "also-optional", "deleted"]:
            put(self.shipped, f"prompts/{name}.md", f"{name} guidance\n")
        shutil.copytree(self.shipped, self.here)
        self.old = {str(p.relative_to(self.shipped)).replace(os.sep, "/"): p.read_bytes()
                    for p in self.shipped.rglob("*") if p.is_file()}
        self.record = {"schema": 1, "template": "default", "files": {p: blob(b) for p, b in self.old.items()}}
        # The current template directory is the only comparison source.
        defaults = importlib.import_module("engine.defaults")
        stack.enter_context(patch.object(defaults, "TEMPLATE_DIR", self.shipped))
        self.write_record()

    def write_record(self, record=None):
        put(self.here, "TEMPLATE.json", json.dumps(self.record if record is None else record))

    def change(self, rel="prompts/test_design.md", content=None):
        content = content if content is not None else self.old[rel] + b"\nNew upstream guidance.\n"
        put(self.shipped, rel, content)
        return content

    def validate(self):
        # Impact is unrelated to a directory comparison and would otherwise discover the developer's repo.
        with patch.object(cli, "policy_impact", return_value={}):
            rc, out = call("validate", "--policy", "--dir", str(self.here))
        self.assertEqual(0, rc, out)
        self.assertTrue(out["ok"], out)
        return out

    def item(self, kind="update"):
        out = self.validate()
        self.assertIn("policy_update", out)
        self.assertEqual(kind, out["policy_update"]["kind"])
        return out["policy_update"]

    def row(self, item, rel="prompts/test_design.md"):
        return next(r for r in item["files"] if Path(r["path"]) == self.here / rel)

    def run_command(self, command):
        # Commands are an agent-facing contract, so execute their quoted bytes,
        # including spaces and apostrophes, with their documented platform shell.
        return run_printed_command(command, self.tmp)


class PrintedCommandTests(unittest.TestCase):
    def test_printed_git_command_preserves_spaces_and_apostrophes(self):
        with tempfile.TemporaryDirectory(prefix="printed command's ") as tmp:
            old, new = Path(tmp) / "old file's.md", Path(tmp) / "new file's.md"
            old.write_text("old guidance\n")
            new.write_text("new guidance\n")
            quote = (lambda value: "'" + value.replace("'", "''") + "'") if os.name == "nt" else shlex.quote
            command = "git diff --no-index -- " + quote(str(old)) + " " + quote(str(new))
            result = run_printed_command(command, tmp)
            self.assertEqual(1, result.returncode, result.stderr)
            self.assertIn("-old guidance", result.stdout)
            self.assertIn("+new guidance", result.stdout)

    def test_windows_uses_powershell_and_preserves_the_printed_command(self):
        command = "'C:/Program Files/Git/bin/git.exe' diff -- 'path''s file.md' 'new file.md'"
        # Check the Windows launch even on POSIX; the command itself is executed
        # by the native platform shell in the preceding quoting probe.
        with patch.object(os, "name", "nt"), patch.object(shutil, "which", side_effect=[None, "powershell.exe"]), \
                patch.object(subprocess, "run") as run:
            run_printed_command(command, "working directory")
            run.assert_called_once_with(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", "& " + command],
                                        shell=False, capture_output=True, text=True, cwd="working directory")


class DefaultComparisonTests(DefaultsCase):
    def snapshot(self):
        return {p.relative_to(self.here).as_posix(): p.read_bytes()
                for p in self.here.rglob("*") if p.is_file()}

    def current_receipt(self):
        return {"schema": 1, "template": "default", "files": {
            p.relative_to(self.shipped).as_posix(): blob(p.read_bytes())
            for p in self.shipped.rglob("*") if p.is_file()}}

    def assert_manual(self, row):
        self.assertEqual({"manual"}, set(row["apply"]), row)
        self.assertNotIn("merge-file", json.dumps(row))
        self.assertNotIn("templates/history", json.dumps(row))

    def test_reviewed_bootstrap_has_no_notice_and_normalised_ids(self):
        self.assertNotIn("policy_update", self.validate())
        for rel, content in self.old.items():
            put(self.here, rel, content.replace(b"\n", b"\r\n"))
            put(self.shipped, rel, content.replace(b"\n", b"\r\n"))
        self.assertNotIn("policy_update", self.validate())

    def test_changed_prompt_offers_executable_read_only_two_way_comparison(self):
        self.change()
        before = self.snapshot()
        item = self.item()
        self.assertRegex(item["template"], r"^[0-9a-f]{12}$")
        row = self.row(item)
        self.assertEqual(("changed", "unchanged"), (row["upstream"], row["local"]))
        self.assert_manual(row)
        diff = self.run_command(row["diff"])
        self.assertEqual(1, diff.returncode, diff.stderr)
        self.assertIn("+New upstream guidance.", diff.stdout)
        self.assertEqual(before, self.snapshot())
        self.assertEqual(self.current_receipt(), item["record"]["reviewed"])
        self.write_record(item["record"]["reviewed"])
        self.assertNotIn("policy_update", self.validate())

    def test_customization_is_compared_to_current_without_reconstruction_or_apply(self):
        rel = "prompts/test_design.md"
        put(self.here, rel, b"local choice\n")
        self.record["files"][rel] = blob(b"opaque previous default\n")
        self.write_record()
        self.change(rel, b"current shipped choice\n")
        before = self.snapshot()
        item = self.item()
        row = self.row(item)
        self.assertEqual("changed", row["local"])
        self.assert_manual(row)
        diff = self.run_command(row["diff"])
        self.assertEqual(1, diff.returncode, diff.stderr)
        self.assertIn("-local choice", diff.stdout)
        self.assertIn("+current shipped choice", diff.stdout)
        self.assertNotIn("opaque previous default", diff.stdout)
        self.assertEqual(before, self.snapshot())

    def test_preexisting_merge_markers_are_still_advisory(self):
        put(self.here, "prompts/test_design.md", b"<<<<<<< local\nlocal\n=======\nother\n>>>>>>> other\n")
        before = self.snapshot()
        warnings = self.validate()["warnings"]
        self.assertTrue(any(w["kind"] == "policy_merge_markers" for w in warnings), warnings)
        self.assertEqual(before, self.snapshot())

    def test_decline_keeps_customization_quiet_until_shipped_hash_changes(self):
        rel = "prompts/test_design.md"
        put(self.here, rel, b"repository guidance\n")
        self.change()
        self.write_record(self.item()["record"]["reviewed"])
        self.assertNotIn("policy_update", self.validate())
        self.assertEqual(b"repository guidance\n", (self.here / rel).read_bytes())
        self.change(content=b"A different current default.\n")
        row = self.row(self.item())
        self.assertEqual("changed", row["local"])
        self.assert_manual(row)

    def test_missing_record_offers_current_snapshot_without_inference_or_writes(self):
        self.change()
        put(self.here, "TEMPLATE.json", None)
        put(self.here, "POLICY.json", (self.here / "POLICY.json").read_bytes() + b"\n")
        before = self.snapshot()
        item = self.item("no_record")
        self.assertNotIn("inferred", item["record"])
        self.assertEqual(self.current_receipt(), item["record"]["reviewed"])
        self.assertEqual(before, self.snapshot())
        for row in item["files"]:
            self.assert_manual(row)

    def test_added_removed_deleted_and_private_files_need_explicit_manual_choice(self):
        put(self.shipped, "prompts/new.md", "a new default\n")
        put(self.shipped, "prompts/also-new.md", "another default\n")
        put(self.here, "prompts/also-new.md", "private content\n")
        put(self.here, "prompts/private.md", "owned by this repository\n")
        removed = ["prompts/optional.md", "prompts/also-optional.md"]
        for rel in removed:
            put(self.shipped, rel, None)
        put(self.here, removed[1], b"edited here\n")
        put(self.here, "prompts/deleted.md", None)
        self.change("prompts/deleted.md")
        before = self.snapshot()
        item = self.item()
        added = self.row(item, "prompts/new.md")
        self.assertEqual(("added", "absent"), (added["upstream"], added["local"]))
        self.assertEqual("changed", self.row(item, "prompts/also-new.md")["local"])
        self.assertEqual("unchanged", self.row(item, removed[0])["local"])
        self.assertEqual("deleted", self.row(item, "prompts/deleted.md")["local"])
        for row in item["files"]:
            self.assert_manual(row)
        self.assertNotIn(self.here / "prompts/private.md", {Path(r["path"]) for r in item["files"]})
        self.assertEqual(before, self.snapshot())
        self.assertEqual(self.current_receipt(), item["record"]["reviewed"])

    def test_invalid_and_newer_schema_receipts_remain_advisory_and_read_only(self):
        invalid = ["{broken", {**self.record, "extra": True},
                   {**self.record, "files": {"../escape.md": "0" * 40}},
                   {**self.record, "files": {"/absolute": "0" * 40}},
                   {**self.record, "files": {"prompts\\wrong.md": "0" * 40}},
                   {**self.record, "files": {"a.md": "NOT-A-BLOB"}},
                   {**self.record, "removed": {"POLICY.json": self.record["files"]["POLICY.json"]}}]
        for record in invalid:
            with self.subTest(record=record):
                put(self.here, "TEMPLATE.json", record if isinstance(record, str) else json.dumps(record))
                before = self.snapshot()
                item = self.item("invalid_record")
                self.assertTrue(item["errors"])
                self.assertNotIn("inferred", item["record"])
                self.assertEqual(self.current_receipt(), item["record"]["reviewed"])
                self.assertEqual(before, self.snapshot())
        self.write_record({**self.record, "schema": 2})
        before = self.snapshot()
        item = self.item("newer_record")
        self.assertNotIn("record", item)
        self.assertFalse(item.get("files"))
        self.assertEqual(before, self.snapshot())

    def test_null_provenance_equal_to_shipped_is_not_drift(self):
        self.record["files"]["prompts/test_design.md"] = None
        self.write_record()
        self.assertNotIn("policy_update", self.validate())

    def test_notice_failure_is_isolated_and_invalid_policy_has_no_notice(self):
        class Unreadable:
            def __fspath__(self):
                raise OSError("unavailable plugin defaults")
        defaults = importlib.import_module("engine.defaults")
        with patch.object(defaults, "TEMPLATE_DIR", Unreadable()):
            self.assertNotIn("policy_update", self.validate())
        self.change()
        put(self.here, "POLICY.json", "{broken policy")
        with patch.object(cli, "policy_impact", return_value={}):
            rc, out = call("validate", "--policy", "--dir", str(self.here))
        self.assertEqual(1, rc)
        self.assertNotIn("policy_update", out)

    def test_opaque_schema_one_hash_is_reviewable_without_version_order_claim(self):
        rel = "prompts/test_design.md"
        self.record["files"][rel] = "1" * 40
        self.write_record()
        item = self.item()
        self.assertNotIn("upgrade", item["message"].lower())
        row = self.row(item)
        self.assertEqual("changed", row["upstream"])
        self.assert_manual(row)
        self.assertEqual(0, self.run_command(row["diff"]).returncode)
        self.assertEqual(self.current_receipt(), item["record"]["reviewed"])
        self.write_record(item["record"]["reviewed"])
        self.assertNotIn("policy_update", self.validate())

    def test_legacy_tombstone_is_reviewed_absence_then_reappearance_is_added(self):
        rel = "prompts/optional.md"
        old_hash = self.record["files"].pop(rel)
        self.record["removed"] = {rel: old_hash}
        self.write_record()
        put(self.shipped, rel, None)
        self.assertNotIn("policy_update", self.validate())
        put(self.shipped, rel, self.old[rel])
        row = self.row(self.item(), rel)
        self.assertEqual("added", row["upstream"])
        self.assert_manual(row)
        reviewed = self.item()["record"]["reviewed"]
        self.assertEqual(self.current_receipt(), reviewed)
        self.assertNotIn("removed", reviewed)

    def test_opaque_tombstone_cannot_claim_newer_plugin(self):
        rel = "prompts/optional.md"
        self.record["files"].pop(rel)
        self.record["removed"] = {rel: "1" * 40}
        self.write_record()
        item = self.item()
        self.assertNotIn("upgrade", item["message"].lower())
        self.assertEqual("added", self.row(item, rel)["upstream"])
        self.assert_manual(self.row(item, rel))
        self.assertEqual(self.current_receipt(), item["record"]["reviewed"])

    def test_declining_changed_default_preserves_local_deletion(self):
        rel = "prompts/deleted.md"
        put(self.here, rel, None)
        self.change(rel)
        row = self.row(self.item(), rel)
        self.assertEqual("deleted", row["local"])
        self.assert_manual(row)
        self.write_record(self.item()["record"]["reviewed"])
        self.assertNotIn("policy_update", self.validate())
        self.assertFalse((self.here / rel).exists())
        self.change(rel, b"another current default\n")
        self.assertEqual("deleted", self.row(self.item(), rel)["local"])



class DefaultRepositoryTests(DefaultsCase):
    def test_committed_policy_preview_compact_bounds_and_writes(self):
        world = fx.World(str(self.tmp / "world"), clones=("a",))
        fx.FakeGitHub(world)
        world.bootstrap()
        world.push_dev({".zzzops/TEMPLATE.json": json.dumps(self.record), **{f".zzzops/{rel}": data for rel, data in self.old.items() if "optional" in rel or "deleted" in rel}})
        repo = world.clones["a"].path

        def run(*args):
            rc, out = call(*args, "--repo", repo, env=world.cli_env())
            self.assertEqual(0, rc, out)
            return out

        self.assertNotIn("policy_update", run("next"))
        self.assertNotIn("policy_update", run("validate"))
        self.assertNotIn("policy_update", run("validate", "--policy", "--dir", str(Path(world.seed.path) / ".zzzops")))
        self.change()
        full = run("validate")["policy_update"]
        for args in [("next",), ("next", "--goal", "1000")]:
            compact = run(*args)["policy_update"]
            self.assertEqual(full["kind"], compact["kind"])
            self.assertEqual(1, compact["counts"]["files"])
            self.assertIn("validate", compact["expand"])
        # A valid preview is read at P, even when dev still has the old record.
        world.seed.commit({".zzzops/TEMPLATE.json": json.dumps(full["record"]["reviewed"])}, "chore: review defaults")
        world.seed.git("push", "-q", "origin", "HEAD:refs/heads/zzzops/policy/defaults")
        self.assertNotIn("policy_update", run("next", "--policy-ref", "defaults"))
        self.assertIn("policy_update", run("next"))
        world.seed.git("push", "-q", "origin", ":refs/heads/zzzops/policy/defaults")
        for i in range(30):
            put(self.shipped, f"prompts/new-{i}.md", f"new {i}\n")
        compact = run("next")
        self.assertEqual(31, compact["policy_update"]["counts"]["files"])
        self.assertEqual(10, len(compact["policy_update"]["files"]))
        self.assertLessEqual(len(json.dumps(compact).encode()), 8192)
        for record in [self.record, {**self.record, "schema": 2}, {"schema": 1}]:
            world.push_dev({".zzzops/TEMPLATE.json": json.dumps(record)})
            doc = run("next")
            self.assertFalse(doc["blockers"], doc)
            created = run("new", "--file", world.file({"title": "default notice", "spec": json.dumps(record)}))
            self.assertNotIn("policy_update", created.get("next", {}))
            gid = created["created"]["id"]
            card = run("start", str(gid), "design", "--as", "test:defaults/designer")
            self.assertEqual(gid, card["goal"])


class DefaultDocumentationTests(unittest.TestCase):
    def test_update_instructions_explain_review_decline_and_workflow_order(self):
        plugin = fx.PLUGIN_CODE.parent
        bootstrap = (plugin / "skills/bootstrap-zzzops-repository/SKILL.md").read_text()
        for text in ["record.reviewed", "declin", "--policy-ref", "workflow.json"]:
            self.assertTrue(text in bootstrap, f"Bootstrap lacks {text}")
        self.assertRegex(bootstrap, r"(?i)decide[^\n]{0,30}workflow\.json[^\n]{0,30}first")
        execute = (plugin / "skills/execute-zzzops/SKILL.md").read_text()
        self.assertIn("policy_update", execute)
        self.assertIn(".zzzops/TEMPLATE.json", execute)
        self.assertRegex(execute, r"(?i)never[^\n]*edit[^\n]*TEMPLATE\.json[^\n]*goal")



if __name__ == "__main__":
    unittest.main()
