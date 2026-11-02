"""G1027: declared engine capabilities replace ENGINE_VERSION and engine.min (design revision 2, §6).

The numbered comments follow the design's test list. Tests that need an engine without one of its capabilities, or
with a damaged package, run a copy of the plugin (the real fail-closed path: a capability is a file)."""

from __future__ import annotations

import copy
import json
import os
import re
import runpy
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import engine_fixtures as fx

NODE_ID = re.compile(r"^[a-z][a-z0-9_]*$")
CAPS_DIR = fx.PLUGIN_CODE / "engine" / "capabilities"
PLUGIN_ROOT = fx.PLUGIN_CODE.parent
# Every capability shipped so far. A goal that adds a capability appends its name here (G1027 §3.1): a capability is
# never removed. (G1022's `lenses` joins when it merges; it had not merged when these tests were written.)
# finding_follows added at rebase onto G1028 (merged first); lenses added at rebase onto G1022 (merged first)
SHIPPED = {"lens_findings", "finding_follows", "lenses", "release_lines"}


def expected_build_id(plugin_code: Path = fx.PLUGIN_CODE) -> str:
    prov = runpy.run_path(str(plugin_code / "package.py"))["package_provenance"]()
    return f"{prov['version']} {prov['revision'][:12]}"


def plugin_copy(tmp: str) -> Path:
    """A copy of the plugin (plugins/zzzops) in tmp; returns its engine code directory (…/zzzops)."""
    dst = Path(tmp) / "plugin-copy"
    shutil.copytree(PLUGIN_ROOT, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    return dst / "zzzops"


def engine_attr(code: Path, expr: str) -> str:
    """Evaluate `expr` (with `engine` and `legacy` imported) in a fresh interpreter running the given plugin code."""
    script = (f"import sys; sys.path.insert(0, {str(code)!r}); import engine; from engine import legacy; "
              f"print({expr})")
    p = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    if p.returncode:
        raise AssertionError(p.stderr)
    return p.stdout.strip()


class CapWorld(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.w = fx.World(self.tmp)
        self.gh = fx.FakeGitHub(self.w)
        self.w.bootstrap()

    def set_engine(self, block: dict):
        p = copy.deepcopy(self.w.policy)
        p["settings"]["engine"] = block
        self.w.push_dev({".zzzops/POLICY.json": json.dumps(p, indent=2) + "\n"}, "chore(zzzops): engine floor")

    def new_file(self, title="t"):
        self.w.news += 1
        return self.w.file({"title": title, "spec": f"spec {self.w.news}"})

    def run_with(self, code: Path, clone: str, *argv):
        p = subprocess.run([sys.executable, str(code / "zzzops.py"), *argv], cwd=self.w.clones[clone].path,
                           capture_output=True, text=True, env=self.w.cli_env())
        try:
            out = json.loads(p.stdout) if p.stdout.strip().startswith("{") else {"_stdout": p.stdout}
        except json.JSONDecodeError:
            out = {"_stdout": p.stdout}
        out.setdefault("_stderr", p.stderr)
        return p.returncode, out

    def without(self, *names) -> Path:
        code = plugin_copy(self.tmp)
        for n in names:
            (code / "engine" / "capabilities" / f"{n}.txt").unlink(missing_ok=True)
        return code

    def floor(self, out):
        return [b for b in out["blockers"] if b["kind"] in ("engine_too_old", "policy_invalid")]

    def kinds(self, warnings):
        return [x["kind"] for x in warnings]

    def validate(self, clone="b"):
        rc, out = self.w.run(clone, "validate")
        self.assertIn("warnings", out, out)
        return out


# --------------------------------------------------------------------------------------------- 1, 2: requires


class RequiresTests(CapWorld):
    def test_missing_capability_refuses_and_names_it(self):
        self.w.new(title="before")
        self.set_engine({"requires": ["no_such_cap", "lens_findings"]})
        out = self.w.ok("b", "next")
        self.assertEqual(["engine_too_old"], [b["kind"] for b in self.floor(out)], out["blockers"])
        b = self.floor(out)[0]
        self.assertEqual(["no_such_cap"], b["missing"])
        self.assertIn("no_such_cap", b["message"])
        self.assertNotIn("lens_findings", b["message"])
        self.assertIn("upgrade the plugin", b["message"])
        self.assertEqual([], out["actions"])                                    # paused
        rc, err = self.w.run("b", "new", "--file", self.new_file())
        self.assertEqual((1, "engine_too_old"), (rc, err["error"]["code"]), err)
        self.assertEqual(["no_such_cap"], err["error"]["details"]["missing"])
        self.assertIn("no_such_cap", err["error"]["message"])
        self.assertEqual("upgrade the plugin", err["error"]["hint"])
        self.w.ok("b", "show", "1000")                                          # reads still work
        v = self.validate()
        self.assertFalse(v["ok"])
        self.assertTrue(any("no_such_cap" in e for e in v["policy"]), v["policy"])

    def test_missing_capabilities_are_sorted_and_unknown_names_are_just_missing(self):
        self.set_engine({"requires": ["zz_cap", "aa_cap", "lens_findings"]})
        b = self.floor(self.w.ok("b", "next"))
        self.assertEqual(["aa_cap", "zz_cap"], b[0]["missing"])

    def test_present_capability_proceeds(self):
        for block in ({"requires": ["lens_findings"]}, {"requires": []}):
            self.set_engine(block)
            out = self.w.ok("b", "next")
            self.assertEqual([], self.floor(out), block)
            self.w.ok("b", "new", "--file", self.new_file())

    def test_a_damaged_install_without_the_file_fails_closed(self):
        self.set_engine({"requires": ["lens_findings"]})
        code = self.without("lens_findings")
        rc, out = self.run_with(code, "b", "next")
        self.assertEqual(0, rc, out)
        self.assertEqual(["lens_findings"], self.floor(out)[0]["missing"])
        rc, err = self.run_with(code, "b", "new", "--file", self.new_file())
        self.assertEqual((1, "engine_too_old"), (rc, err["error"]["code"]), err)


# --------------------------------------------------------------------------------------------- 3: the engine.min map


class LegacyMinTests(CapWorld):
    def test_mapping(self):
        from engine import schemas
        self.assertEqual((), tuple(schemas.LEGACY_VERSIONS["1.0.0"]))
        self.assertEqual(("lens_findings",), tuple(schemas.LEGACY_VERSIONS["1.1.0"]))
        caps = getattr(schemas, "legacy_caps", None)
        if caps is None:
            from engine import store
            caps = store.legacy_caps
        for mn in ("0.0.0", "1.0.0", "1.0.7"):
            self.assertEqual(set(), set(caps(mn)), mn)
        self.assertEqual({"lens_findings"}, set(caps("1.1.0")))
        self.assertEqual({"engine_min_99.0.0"}, set(caps("99.0.0")))

    def test_mapping_covers_the_rollouts_of_g1028_and_g1022(self):
        """1.2.0 (G1028) and 1.3.0 (G1022) floors keep working through the fixed map (review_impl:1:1)."""
        from engine import schemas
        self.assertEqual(("lens_findings", "finding_follows"), tuple(schemas.LEGACY_VERSIONS["1.2.0"]))
        self.assertEqual(("lens_findings", "finding_follows", "lenses"), tuple(schemas.LEGACY_VERSIONS["1.3.0"]))
        caps = schemas.legacy_caps
        self.assertEqual({"lens_findings", "finding_follows"}, set(caps("1.2.5")))
        self.assertEqual({"engine_min_1.3.1"}, set(caps("1.3.1")))
        self.assertTrue(schemas.follows_required({"engine": {"min": "1.2.0"}}))
        self.assertFalse(schemas.follows_required({"engine": {"min": "1.1.0"}}))

    def test_old_floors_proceed_and_validate_warns(self):
        for mn in ("0.0.0", "1.0.0", "1.1.0"):
            self.set_engine({"min": mn})
            out = self.w.ok("b", "next")
            self.assertEqual([], self.floor(out), mn)
            self.assertNotIn("engine_min_deprecated", self.kinds(out["warnings"]), mn)       # next stays quiet
            self.w.ok("b", "new", "--file", self.new_file())
            v = self.validate()
            warn = [x for x in v["warnings"] if x["kind"] == "engine_min_deprecated"]
            self.assertEqual(1, len(warn), (mn, v["warnings"]))
            self.assertIn("settings.engine.requires", warn[0]["message"])
            self.assertIn("policy branch", warn[0]["message"])
            if mn == "1.1.0":
                self.assertIn("lens_findings", warn[0]["message"])

    def test_policy_dir_validate_warns_too(self):
        nowhere = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, nowhere, True)
        rc, out = self.w.run("a", "validate", "--policy", "--dir", str(fx.TEMPLATES), cwd=nowhere)   # min 0.0.0
        self.assertEqual(0, rc, out)
        self.assertIn("engine_min_deprecated", self.kinds(out["warnings"]))

    def test_min_above_the_map_refuses_with_the_last_numbered_engine(self):
        from engine import schemas
        highest = max(schemas.LEGACY_VERSIONS, key=lambda v: tuple(int(x) for x in v.split(".")))
        self.set_engine({"min": "99.0.0"})
        b = self.floor(self.w.ok("b", "next"))
        self.assertEqual(["engine_too_old"], [x["kind"] for x in b])
        self.assertEqual(["engine_min_99.0.0"], b[0]["missing"])
        self.assertIn("last numbered engine", b[0]["message"])
        self.assertIn(highest, b[0]["message"])
        self.assertIn("settings.engine.requires", b[0]["message"])
        rc, err = self.w.run("b", "new", "--file", self.new_file())
        self.assertEqual((1, "engine_too_old"), (rc, err["error"]["code"]))

    def test_min_1_1_0_refuses_an_engine_without_lens_findings(self):
        self.set_engine({"min": "1.1.0"})
        code = self.without("lens_findings")
        rc, out = self.run_with(code, "b", "next")
        self.assertEqual(0, rc, out)
        b = self.floor(out)
        self.assertEqual(["engine_too_old"], [x["kind"] for x in b])
        self.assertEqual(["lens_findings"], b[0]["missing"])
        self.assertIn("lens_findings", b[0]["message"])

    def test_min_and_requires_combine(self):
        self.set_engine({"min": "1.1.0", "requires": ["no_such_cap"]})
        self.assertEqual(["no_such_cap"], self.floor(self.w.ok("b", "next"))[0]["missing"])
        code = self.without("lens_findings")
        rc, out = self.run_with(code, "b", "next")
        self.assertEqual(["lens_findings", "no_such_cap"], self.floor(out)[0]["missing"])


# --------------------------------------------------------------------------------------------- 4: schema


class SchemaTests(unittest.TestCase):
    def errs(self, engine_block):
        from engine import schemas
        p = fx.load_template("POLICY.json")
        p["settings"]["engine"] = engine_block
        return schemas.validate_policy(p)

    def test_valid_engine_blocks(self):
        for block in ({"requires": ["lens_findings"]}, {"requires": []}, {}, {"min": "1.1.0"},
                      {"min": "1.0.0", "requires": ["a_b", "c9"]}):
            self.assertEqual([], self.errs(block), block)

    def test_invalid_requires(self):
        for bad in (["Bad"], ["dup", "dup"], "lens_findings", [1], ["9lead"], ["has-dash"], None, {"x": 1}):
            self.assertTrue(self.errs({"requires": bad}), bad)

    def test_engine_block_stays_required_and_unknown_keys_fail(self):
        from engine import schemas
        p = fx.load_template("POLICY.json")
        p["settings"].pop("engine")
        self.assertTrue(schemas.validate_policy(p))
        self.assertTrue(self.errs({"requires": [], "max": "1.0.0"}))
        self.assertTrue(any("MAJOR.MINOR.PATCH" in e for e in self.errs({"min": "1.0"})))


# --------------------------------------------------------------------------------------------- 5, 6: declared files


class DeclaredFileTests(unittest.TestCase):
    def test_every_file_is_a_named_non_empty_paragraph(self):
        self.assertTrue(CAPS_DIR.is_dir(), CAPS_DIR)
        files = sorted(CAPS_DIR.iterdir())
        self.assertTrue(files)
        for f in files:
            self.assertEqual(".txt", f.suffix, f)
            self.assertRegex(f.stem, NODE_ID)
            self.assertTrue(f.read_text(encoding="utf-8").strip(), f)
        self.assertIn("G1000", (CAPS_DIR / "lens_findings.txt").read_text(encoding="utf-8"))

    def test_loaded_set_is_the_files_and_nothing_is_removed(self):
        import engine
        self.assertIsInstance(engine.CAPABILITIES, frozenset)
        self.assertEqual({f.stem for f in CAPS_DIR.glob("*.txt")}, set(engine.CAPABILITIES))
        self.assertLessEqual(SHIPPED, set(engine.CAPABILITIES))

    def test_two_goals_add_capabilities_without_a_merge_conflict(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        code = plugin_copy(tmp)
        repo = fx.GitDir(str(code.parent), fx.isolated_env(tmp))
        repo.git("init", "-q", "-b", "dev")
        repo.git("add", "-A")
        repo.git("commit", "-q", "-m", "base")
        for name in ("alpha_cap", "beta_cap"):
            repo.git("checkout", "-q", "-b", name, "dev")
            repo.commit({f"zzzops/engine/capabilities/{name}.txt": f"{name}: test capability (G0).\n"}, name)
        repo.git("checkout", "-q", "dev")
        repo.git("merge", "-q", "--no-edit", "alpha_cap")
        repo.git("merge", "-q", "--no-edit", "beta_cap")                    # a clean merge, or git(check=True) raises
        self.assertEqual("", repo.git("status", "--porcelain").strip())
        caps = json.loads(engine_attr(code, "__import__('json').dumps(sorted(engine.CAPABILITIES))"))
        self.assertLessEqual({"alpha_cap", "beta_cap"} | SHIPPED, set(caps))


# --------------------------------------------------------------------------------------------- 7: build id


class BuildIdTests(CapWorld):
    def trailer(self, gid):
        msg = self.w.remote_git("log", "-1", "--format=%B", f"refs/heads/zzzops/goal/g{gid}")
        lines = [l for l in msg.splitlines() if l.startswith("Engine: ")]
        self.assertEqual(1, len(lines), msg)
        return lines[0]

    def test_goal_commits_carry_the_build_id(self):
        import engine
        want = expected_build_id()
        self.assertRegex(want, r"^\S+ [0-9a-f]{12}$")
        self.assertEqual(want, engine.build_id())
        gid = self.w.new(title="x")["created"]["id"]
        self.assertEqual(f"Engine: {want}", self.trailer(gid))

    def test_version_prints_the_build_id(self):
        rc, out = self.w.run("a", "--version")
        self.assertEqual(0, rc)
        self.assertEqual(expected_build_id(), out["_stdout"].strip())

    def test_a_damaged_provenance_writes_unknown_and_the_write_succeeds(self):
        code = plugin_copy(self.tmp)
        with open(code / "package.py", "a", encoding="utf-8") as fh:
            fh.write("\n\ndef package_provenance(_repo=None):\n    raise RuntimeError('damaged install')\n")
        rc, out = self.run_with(code, "a", "new", "--file", self.new_file())
        self.assertEqual(0, rc, out)
        self.assertEqual("Engine: unknown", self.trailer(out["created"]["id"]))

    def test_validate_shows_build_and_capabilities(self):
        import engine
        v = self.validate()
        self.assertEqual({"build": expected_build_id(), "capabilities": sorted(engine.CAPABILITIES)}, v["engine"])


# --------------------------------------------------------------------------------------------- 8: legacy key


class DetectorTests(unittest.TestCase):
    def test_detector_hashes_the_detection_sources(self):
        from engine import legacy
        self.assertRegex(legacy.DETECTOR, r"^[0-9a-f]{12}$")
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        code = plugin_copy(tmp)
        self.assertEqual(legacy.DETECTOR, engine_attr(code, "legacy.DETECTOR"))
        # CRLF-normalised: line endings alone do not change it
        lp = code / "engine" / "legacy.py"
        lp.write_bytes(lp.read_bytes().replace(b"\n", b"\r\n"))
        self.assertEqual(legacy.DETECTOR, engine_attr(code, "legacy.DETECTOR"))
        with open(code.parent / "scripts" / "cleanup_legacy.py", "a", encoding="utf-8") as fh:
            fh.write("\n# a changed root list\n")
        after_script = engine_attr(code, "legacy.DETECTOR")
        self.assertNotEqual(legacy.DETECTOR, after_script)
        with open(lp, "a", encoding="utf-8") as fh:
            fh.write("\n# a changed rule\n")
        self.assertNotIn(engine_attr(code, "legacy.DETECTOR"), (legacy.DETECTOR, after_script))

    def test_a_new_build_with_the_same_detector_keeps_the_key(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        code = plugin_copy(tmp)
        (code / "rules_note.txt").write_text("a change elsewhere in the package\n", encoding="utf-8")
        from engine import build_id, legacy
        self.assertNotEqual(build_id(), engine_attr(code, "engine.build_id()"))
        self.assertEqual(legacy.DETECTOR, engine_attr(code, "legacy.DETECTOR"))


# --------------------------------------------------------------------------------------------- 9: template


class TemplateTests(unittest.TestCase):
    def test_default_template_requires_lens_findings(self):
        # lenses added at rebase onto G1022 (merged first): the template requires it too
        p = json.loads((fx.SHIPPED / "POLICY.json").read_text(encoding="utf-8"))
        self.assertEqual({"requires": ["lens_findings", "lenses"]}, p["settings"]["engine"])
        nowhere = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, nowhere, True)
        r = subprocess.run([sys.executable, str(fx.PLUGIN_CODE / "zzzops.py"), "validate", "--policy", "--dir",
                            str(fx.SHIPPED)], cwd=nowhere, capture_output=True, text=True)
        out = json.loads(r.stdout)
        self.assertEqual(0, r.returncode, out)
        self.assertNotIn("engine_min_deprecated", [x["kind"] for x in out["warnings"]])

    def test_a_bootstrap_from_the_template_writes(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        w = fx.World(tmp)
        fx.FakeGitHub(w)
        w.bootstrap(policy=json.loads((fx.SHIPPED / "POLICY.json").read_text(encoding="utf-8")),
                    workflow=json.loads((fx.SHIPPED / "workflow.json").read_text(encoding="utf-8")), prompts=False)
        w.push_dev({f".zzzops/prompts/{p.name}": p.read_text(encoding="utf-8")
                    for p in sorted((fx.SHIPPED / "prompts").iterdir())}, "chore(zzzops): prompts")
        self.assertEqual({"requires": ["lens_findings", "lenses"]}, w.policy["settings"]["engine"])
        out = w.ok("a", "next")
        self.assertEqual([], [b for b in out["blockers"] if b["kind"] in ("engine_too_old", "policy_invalid")])
        w.new(title="from the template")


# --------------------------------------------------------------------------------------------- 10: no stale references


class NoStaleReferenceTests(unittest.TestCase):
    def test_old_names_are_gone(self):
        """Over plugins/, docs/design/ and the shared .agents helpers. docs/design/HISTORY.md and
        docs/design/IMPLEMENTATION_PLAN.md are historical records and keep the old names (review_tests:2:1). Test modules are left out: other goals' tests may
        name the old constant behind getattr or a lazy import to work in either merge order (review_tests:1:1), and an
        unguarded import of a removed name fails on its own."""
        pattern = "ENGINE_" + "VERSION|REQUIRES_" + "MIN|requires_" + "min|engine_too_" + "new|engine\\.min " + "bump"
        p = subprocess.run(["git", "grep", "-nE", pattern, "--", "plugins/", ".agents/", "docs/design/",
                            ":(exclude)docs/design/HISTORY.md", ":(exclude)docs/design/IMPLEMENTATION_PLAN.md",
                            ":(exclude,glob).agents/test_*.py"],
                           cwd=fx.ROOT, capture_output=True, text=True)
        self.assertIn(p.returncode, (0, 1), p.stderr)
        self.assertEqual("", p.stdout)

    def test_errors_no_longer_know_engine_too_new(self):
        from engine.errors import EXIT
        self.assertIn("engine_too_old", EXIT)
        self.assertNotIn("engine_too_" + "new", EXIT)


if __name__ == "__main__":
    unittest.main()
