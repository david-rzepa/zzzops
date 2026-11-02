"""G1024: observable default-policy notices, provenance and version skew.

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


class DefaultsCase(unittest.TestCase):
    def setUp(self):
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        self.tmp = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="default policy ")))
        self.shipped = self.tmp / "plugin defaults"
        self.here = self.tmp / "repository policy"
        self.history = self.tmp / "history store"
        shutil.copytree(fx.TEMPLATES, self.shipped)
        for name in ["optional", "also-optional", "deleted"]:
            put(self.shipped, f"prompts/{name}.md", f"{name} guidance\n")
        shutil.copytree(self.shipped, self.here)
        self.history.mkdir()
        self.old = {str(p.relative_to(self.shipped)).replace(os.sep, "/"): p.read_bytes()
                    for p in self.shipped.rglob("*") if p.is_file()}
        self.record = {"schema": 1, "template": "default", "files": {p: blob(b) for p, b in self.old.items()}}
        for rel, content in self.old.items():
            self.store(rel, content)
        # These two locations are the design's test seam; no comparison API is prescribed.
        defaults = importlib.import_module("engine.defaults")
        stack.enter_context(patch.object(defaults, "TEMPLATE_DIR", self.shipped))
        stack.enter_context(patch.object(defaults, "HISTORY_DIR", self.history))
        self.write_record()

    def store(self, rel, content):
        put(self.history, blob(content) + Path(rel).suffix, content)

    def write_record(self, record=None):
        put(self.here, "TEMPLATE.json", json.dumps(self.record if record is None else record))

    def change(self, rel="prompts/test_design.md", content=None):
        content = content if content is not None else self.old[rel] + b"\nNew upstream guidance.\n"
        put(self.shipped, rel, content)
        self.store(rel, content)
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
        # including paths containing spaces, rather than reconstructing argv.
        return subprocess.run(command, shell=True, capture_output=True, text=True, cwd=self.tmp)


class DefaultComparisonTests(DefaultsCase):
    def test_reviewed_bootstrap_has_no_notice_and_normalised_ids(self):
        self.assertNotIn("policy_update", self.validate())
        for rel, content in self.old.items():
            put(self.here, rel, content.replace(b"\n", b"\r\n"))
            put(self.shipped, rel, content.replace(b"\n", b"\r\n"))
        self.assertNotIn("policy_update", self.validate())

    def test_changed_prompt_has_working_diff_and_merge_commands(self):
        new = self.change()
        item = self.item()
        self.assertRegex(item["template"], r"^[0-9a-f]{12}$")
        row = self.row(item)
        self.assertEqual(("changed", "unchanged"), (row["upstream"], row["local"]))
        diff = self.run_command(row["diff"])
        self.assertEqual(1, diff.returncode, diff.stderr)
        self.assertIn("+New upstream guidance.", diff.stdout)
        merge = self.run_command(row["apply"]["merge"])
        self.assertEqual(0, merge.returncode, merge.stderr)
        self.assertEqual(new, (self.here / "prompts/test_design.md").read_bytes())
        # Neither validate nor the advisory merge silently advances provenance.
        self.assertEqual(self.record, json.loads((self.here / "TEMPLATE.json").read_text()))
        self.write_record(item["record"]["reviewed"])
        self.assertNotIn("policy_update", self.validate())

    def test_three_way_merge_keeps_nonoverlapping_local_edits(self):
        rel = "prompts/test_design.md"
        base = b"first\n" + b"middle\n" * 20 + b"last\n"
        put(self.here, rel, base.replace(b"first", b"local first"))
        self.store(rel, base)
        self.record["files"][rel] = blob(base)
        self.write_record()
        self.change(rel, base.replace(b"last", b"upstream last"))
        row = self.row(self.item())
        self.assertEqual("changed", row["local"])
        merge = self.run_command(row["apply"]["merge"])
        self.assertEqual(0, merge.returncode, merge.stderr)
        merged = (self.here / rel).read_text()
        self.assertIn("local first", merged)
        self.assertIn("upstream last", merged)

    def test_overlap_leaves_markers_and_validation_warns(self):
        rel = "prompts/test_design.md"
        put(self.here, rel, self.old[rel] + b"\nLocal guidance.\n")
        self.change()
        result = self.run_command(self.row(self.item())["apply"]["merge"])
        self.assertGreater(result.returncode, 0)
        self.assertIn("<<<<<<<", (self.here / rel).read_text())
        warnings = self.validate()["warnings"]
        self.assertTrue(any(w["kind"] == "policy_merge_markers" for w in warnings), warnings)

    def test_decline_is_quiet_until_another_upstream_change(self):
        rel = "prompts/test_design.md"
        self.change()
        reviewed = self.item()["record"]["reviewed"]
        self.write_record(reviewed)
        self.assertEqual(self.old[rel], (self.here / rel).read_bytes())
        self.assertNotIn("policy_update", self.validate())
        self.change(content=b"A different upstream version.\n")
        self.assertEqual("changed", self.row(self.item())["local"])

    def test_missing_record_infers_history_matches_and_unknown_files(self):
        rel = "prompts/test_design.md"
        self.change()
        put(self.here, "TEMPLATE.json", None)
        put(self.here, "POLICY.json", (self.here / "POLICY.json").read_bytes() + b"\n")
        item = self.item("no_record")
        inferred = item["record"]["inferred"]
        self.assertEqual(blob(self.old[rel]), inferred["files"][rel])
        self.assertIsNone(inferred["files"]["POLICY.json"])
        self.write_record(inferred)
        rows = self.item()["files"]
        self.assertEqual({self.here / rel, self.here / "POLICY.json"}, {Path(r["path"]) for r in rows})
        unknown = self.row({"files": rows}, "POLICY.json")
        self.assertEqual("unknown", unknown["local"])
        self.assertIn("manual", unknown["apply"])
        self.assertEqual(1, self.run_command(unknown["diff"]).returncode)

    def test_added_removed_deleted_and_private_files(self):
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
        item = self.item()
        added = self.row(item, "prompts/new.md")
        self.assertEqual(("added", "absent"), (added["upstream"], added["local"]))
        self.assertEqual(self.shipped / "prompts/new.md", Path(added["apply"]["copy"]))
        self.assertEqual("changed", self.row(item, "prompts/also-new.md")["local"])
        self.assertTrue(self.row(item, removed[0])["apply"]["delete"])
        self.assertEqual("unchanged", self.row(item, removed[0])["local"])
        self.assertIn("manual", self.row(item, removed[1])["apply"])
        self.assertEqual("deleted", self.row(item, "prompts/deleted.md")["local"])
        self.assertIn("manual", self.row(item, "prompts/deleted.md")["apply"])
        self.assertNotIn(self.here / "prompts/private.md", {Path(r["path"]) for r in item["files"]})

    def test_invalid_and_newer_records_are_advisory(self):
        invalid = ["{broken", {**self.record, "extra": True},
                   {**self.record, "files": {"../escape.md": "0" * 40}},
                   {**self.record, "files": {"/absolute": "0" * 40}},
                   {**self.record, "files": {"prompts\\wrong.md": "0" * 40}},
                   {**self.record, "files": {"a.md": "NOT-A-BLOB"}},
                   {**self.record, "removed": {"POLICY.json": self.record["files"]["POLICY.json"]}}]
        for record in invalid:
            with self.subTest(record=record):
                put(self.here, "TEMPLATE.json", record if isinstance(record, str) else json.dumps(record))
                item = self.item("invalid_record")
                self.assertTrue(item["errors"])
                self.assertIn("inferred", item["record"])
        self.write_record({**self.record, "schema": 2})
        item = self.item("newer_record")
        self.assertNotIn("record", item)
        self.assertFalse(item.get("files"))

    def test_unknown_provenance_equal_to_shipped_is_not_drift(self):
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

    def test_newer_base_is_not_offered_as_a_downgrade(self):
        rel = "prompts/test_design.md"
        newer = blob("not shipped by this older engine\n")
        self.record["files"][rel] = newer
        self.write_record()
        item = self.item()
        row = self.row(item)
        self.assertEqual(("unknown_base", "unknown"), (row["upstream"], row["local"]))
        self.assertNotIn("diff", row)
        self.assertNotIn("apply", row)
        self.assertIn("upgrade", row["note"])
        self.assertNotIn("record", item)  # only unknown bases: no offer to review an older default
        self.change("prompts/design.md")
        reviewed = self.item()["record"]["reviewed"]
        self.assertEqual(newer, reviewed["files"][rel])
        self.write_record(reviewed)
        self.change(rel, "not shipped by this older engine\n")
        self.assertNotIn("policy_update", self.validate())

    def test_removed_file_tombstone_does_not_ping_pong_between_plugins(self):
        rel = "prompts/review_design.md"
        base = self.record["files"][rel]
        put(self.shipped, rel, None)
        record = self.item()["record"]["reviewed"]
        self.assertNotIn(rel, record["files"])
        self.assertEqual(base, record["removed"][rel])
        serialised = json.dumps(record, sort_keys=True)
        for round_ in range(4):
            with self.subTest(round=round_):
                self.write_record(record)
                self.assertNotIn("policy_update", self.validate())
                # Another real update makes both engines offer a reviewed record,
                # allowing us to check that neither resurrects the removed entry.
                self.change("prompts/design.md", f"round {round_}\n")
                new = self.item()["record"]["reviewed"]
                self.assertEqual(base, new["removed"][rel])
                self.assertNotIn(rel, new["files"])
                # Keep unrelated provenance fixed for byte-identity of the tombstone round trip.
                new["files"]["prompts/design.md"] = record["files"]["prompts/design.md"]
                self.assertEqual(serialised, json.dumps(new, sort_keys=True))
                put(self.shipped, "prompts/design.md", self.old["prompts/design.md"])
                put(self.shipped, rel, self.old[rel] if round_ % 2 == 0 else None)

    def test_unknown_tombstone_waits_for_upgrade_or_explicit_manual_fix(self):
        rel = "prompts/review_design.md"
        del self.record["files"][rel]
        self.record["removed"] = {rel: "1" * 40}
        self.write_record()
        row = self.row(self.item(), rel)
        self.assertEqual("unknown_base", row["upstream"])
        self.assertNotIn("apply", row)
        self.record["removed"] = {}
        self.write_record()
        self.assertEqual("added", self.row(self.item(), rel)["upstream"])


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

    def test_design_contract_and_history_are_amended(self):
        spec = (fx.ROOT / "docs/design/SPEC.md").read_text()
        design = (fx.ROOT / "docs/design/DESIGN.md").read_text()
        history = (fx.ROOT / "docs/design/HISTORY.md").read_text()
        for term in ["TEMPLATE.json", "templates/history/", "policy_update", "policy_merge_markers"]:
            self.assertTrue(term in spec, f"SPEC lacks {term}")
        self.assertIn("policy_update", design)
        self.assertIn("G1024", history)
        import test_design_docs as design_docs
        # Reuse the existing guard instead of coupling to the pending row's prose.
        design_docs.DesignDocsTests("test_no_landed_goal_is_pending").test_no_landed_goal_is_pending()


if __name__ == "__main__":
    unittest.main()
