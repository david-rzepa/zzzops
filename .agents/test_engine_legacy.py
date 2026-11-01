"""G1015: detection of pre-reset ZzzOps state, the bounded legacy check and its disclosure (design revision 2, §7)."""

from __future__ import annotations

import json
import os
import re
import runpy
import shutil
import tempfile
import unittest

import engine_fixtures as fx

HOUR = 3600
DAY = 24 * HOUR
SKILL = "migrate-zzzops-repository"
LABELLED = "repo:test/repo is:issue is:open label:zzzops,zzzops:schema:v1,zzzops:schema:v2"
MARKED = 'repo:test/repo is:issue is:open "zzzops-goal" in:body -label:zzzops'
OLD_REF = "refs/heads/zzzops/attempts/566/x"

# the shape of the pre-reset .zzzops/POLICY.json at 64d5196 (abridged: the real one is 160 KB)
OLD_POLICY = {"schema_version": 1,
              "approval": {"date": "2026-10-26", "digest": "sha256:" + "0" * 64, "reviewer": "Owner"},
              "backend": "github_issues",
              "bindings": {"audit": {"digest": "sha256:" + "1" * 64, "path": ".zzzops/PROJECT_AUDIT.md"}},
              "charter": {"acceptance_criteria": ["x"], "beneficiaries": ["y"]},
              "history": [], "initialized": True, "policy": {}, "repository": {}, "revision": 7}


def issue(number, labels=("zzzops",), marker=False, open=True, comments=0):
    return {"number": number, "labels": list(labels), "body_marker": marker, "open": open, "comments": comments}


class LegacyCase(unittest.TestCase):
    fake_gh = True
    bootstrap = True
    policy = None

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.w = fx.World(self.tmp, clones=("a",))
        self.gh = fx.FakeGitHub(self.w) if self.fake_gh else None
        if self.bootstrap:
            self.w.bootstrap(policy=self.policy)

    # ------------------------------------------------------------------ helpers
    def issues(self, *items):
        self.gh.update(lambda st: st.__setitem__("legacy_issues", [dict(i) for i in items]))

    def close_all(self):
        self.gh.update(lambda st: [i.update(open=False) for i in st["legacy_issues"]])

    def faults(self, **kw):
        self.gh.update(lambda st: st.setdefault("faults", {}).update(kw))

    def measure(self, *argv, now=None, ok=True):
        """Run one verb; return (output, git network commands, gh argvs) from ZZZOPS_TRACE."""
        self.w.reset_trace()
        if ok:
            out = self.w.ok("a", *argv, now=now)
        else:
            out = self.w.run("a", *argv, now=now)
        lines = self.w.trace_lines()
        git = [l["cmd"][1] for l in lines if l["cmd"][0] == "git"]
        gh = [l["cmd"][1:] for l in lines if l["cmd"][0] == "gh"]
        return out, git, gh

    def assert_no_check(self, git, gh):
        self.assertEqual([], gh)
        self.assertNotIn("ls-remote", git)

    def assert_one_check(self, git, gh):
        self.assertEqual(1, git.count("ls-remote"), git)
        self.assertEqual(1, len(gh), gh)
        self.assertEqual(["api", "graphql"], gh[0][:2])

    def cache(self):
        with open(self.w.legacy_cache("a"), encoding="utf-8") as fh:
            return json.load(fh)

    def iso(self, t):
        from engine.canon import iso
        return iso(t)

    def old_ref(self):
        self.w.remote_git("update-ref", OLD_REF, self.w.remote_git("rev-parse", "refs/heads/dev"))

    def local_audit_file(self):
        self.w.push_dev({".zzzops/PROJECT_AUDIT.md": "# old audit\n"}, "chore: old audit file")


# --------------------------------------------------------------------------------------------- 1, 2, 3: cache and cost


class CacheTests(LegacyCase):
    def test_fixture_seeds_a_clean_cache_with_the_engine_key(self):
        from engine import ENGINE_VERSION, legacy
        c = self.cache()
        self.assertEqual(legacy.cache_key(ENGINE_VERSION, fx.REMOTE_URL, ()), c["key"])
        self.assertEqual(("ok", None, 0), (c["github"], c["retry_after"], c["issue_count"]))
        _, git, gh = self.measure("next")
        self.assertEqual((["fetch"], []), (git, gh))

    def test_cache_key_is_pure_and_sensitive_to_each_part(self):
        from engine import legacy
        k = legacy.cache_key("1.0.0", fx.REMOTE_URL, ())
        self.assertRegex(k, r"^[0-9a-f]{64}$")
        self.assertEqual(k, legacy.cache_key("1.0.0", fx.REMOTE_URL, ()))
        self.assertNotEqual(k, legacy.cache_key("0.9.0", fx.REMOTE_URL, ()))
        self.assertNotEqual(k, legacy.cache_key("1.0.0", "https://github.com/other/repo.git", ()))
        self.assertNotEqual(k, legacy.cache_key("1.0.0", fx.REMOTE_URL, (".zzzops/PROJECT_AUDIT.md",)))

    def test_legacy_repo_cold_cache_checks_once_then_on_key_change(self):
        self.issues(issue(1), issue(2, labels=("zzzops:schema:v1",)), issue(3, labels=("zzzops:schema:v2",)),
                    issue(4, labels=("bug",)))
        self.old_ref()
        self.w.new(title="New-style goal")                       # its goal/lease refs are not legacy refs
        self.w.drop_legacy_cache("a")
        out, git, gh = self.measure("next")
        self.assert_one_check(git, gh)
        item = out["legacy"]
        self.assertEqual({"issues": 3, "files": 0, "refs": 1}, item["counts"])
        self.assertEqual(SKILL, item["skill"])
        self.assertIn(SKILL, item["message"])
        self.assertEqual("zzzops validate", item["recheck"])
        from engine import ENGINE_VERSION
        self.assertEqual({"engine": ENGINE_VERSION, "at": self.iso(self.w.now), "github": "ok"}, item["checked"])
        self.assertIn("settings.legacy.ignore", item["dismiss"])
        for key in ("queries", "linked", "truncated"):
            self.assertNotIn(key, item)                           # validate only
        self.assertLess(len(json.dumps(item)), 8192)
        out, git, gh = self.measure("next")
        self.assert_no_check(git, gh)
        self.assertEqual(3, out["legacy"]["counts"]["issues"])   # shown from the cache
        c = self.cache()
        from engine import legacy
        c["key"], c["engine"] = legacy.cache_key("0.9.0", fx.REMOTE_URL, ()), "0.9.0"
        legacy.write_cache(os.path.join(self.w.clones["a"].path, ".git"), c)
        _, git, gh = self.measure("next")
        self.assert_one_check(git, gh)
        _, git, gh = self.measure("next")
        self.assert_no_check(git, gh)

    def test_cache_record_shape(self):
        self.issues(issue(7))
        self.old_ref()
        self.w.drop_legacy_cache("a")
        self.w.ok("a", "next")
        c = self.cache()
        from engine import ENGINE_VERSION
        self.assertEqual(1, c["schema"])
        self.assertEqual(ENGINE_VERSION, c["engine"])
        self.assertEqual(self.iso(self.w.now), c["checked_at"])
        self.assertEqual(("ok", None), (c["github"], c["error"]))
        self.assertEqual(([7], 1, [], 1), (c["issues"], c["issue_count"], c["linked"], c["refs"]))
        self.assertEqual(self.iso(self.w.now + DAY), c["retry_after"])   # active: re-checked daily

    def test_clean_repo_cold_cache_checks_once_and_never_expires(self):
        self.w.drop_legacy_cache("a")
        out, git, gh = self.measure("next")
        self.assert_one_check(git, gh)
        self.assertNotIn("legacy", out)
        self.assertEqual(("ok", None), (self.cache()["github"], self.cache()["retry_after"]))
        out, git, gh = self.measure("next")
        self.assert_no_check(git, gh)
        out, git, gh = self.measure("next", now=self.w.now + 30 * DAY)
        self.assert_no_check(git, gh)
        self.assertNotIn("legacy", out)

    def test_cold_cache_budget_of_next(self):
        self.w.drop_legacy_cache("a")
        _, git, gh = self.measure("next")
        self.assertEqual(["fetch", "ls-remote"], git)
        self.assertEqual(1, len(gh), gh)
        self.assertEqual(["api", "graphql"], gh[0][:2])
        for word in ("issue", "view", "list"):
            self.assertNotIn(word, gh[0])
        self.assertFalse(any("comments" in a for a in gh[0]), gh[0])

    def test_validate_runs_one_check_on_a_warm_cache(self):
        _, git, gh = self.measure("validate")
        self.assertEqual(1, git.count("fetch"), git)
        self.assertEqual(1, git.count("ls-remote"), git)
        self.assertEqual(1, len(gh), gh)
        self.assertEqual(["api", "graphql"], gh[0][:2])

    def test_validate_shows_the_item_without_changing_ok(self):
        self.issues(issue(9))
        rc, out = self.w.run("a", "validate")
        self.assertEqual(0, rc, out)
        self.assertTrue(out["ok"])
        self.assertEqual(1, out["legacy"]["counts"]["issues"])


# --------------------------------------------------------------------------------------------- 4: old-format policy


class OldPolicyTests(LegacyCase):
    bootstrap = False

    def push_old(self, policy):
        self.w.push_dev({".zzzops/POLICY.json": json.dumps(policy, indent=2) + "\n"}, "chore: pre-reset policy")

    def assert_legacy_policy(self):
        out = self.w.ok("a", "next")
        kinds = [b["kind"] for b in out["blockers"]]
        self.assertIn("legacy_policy", kinds)
        self.assertNotIn("not_bootstrapped", kinds)
        b = next(b for b in out["blockers"] if b["kind"] == "legacy_policy")
        self.assertIn(SKILL, b["message"])
        rc, err = self.w.run("a", "start", "1000", "design", "--as", "claude:aaaa/w-1")
        self.assertEqual((4, "legacy_policy"), (rc, err["error"]["code"]))
        rc, err = self.w.run("a", "new", "--file", self.w.file({"title": "t", "spec": "s"}))
        self.assertEqual((4, "legacy_policy"), (rc, err["error"]["code"]))
        rc, out = self.w.run("a", "validate")
        self.assertEqual(1, rc)
        self.assertFalse(out["ok"])
        self.assertTrue(any(SKILL in m for m in out["policy"]), out["policy"])

    def test_schema_version_1_policy_is_a_legacy_blocker(self):
        self.push_old(OLD_POLICY)
        self.assert_legacy_policy()

    def test_unversioned_old_policy_is_a_legacy_blocker(self):
        p = {k: v for k, v in OLD_POLICY.items() if k != "schema_version"}
        self.push_old(p)
        self.assert_legacy_policy()

    def test_new_format_but_invalid_policy_is_not_legacy(self):
        self.w.push_dev({".zzzops/POLICY.json": json.dumps({"schema_version": 2, "nope": 1}),
                         ".zzzops/workflow.json": json.dumps(fx.load_template("workflow.json"))})
        out = self.w.ok("a", "next")
        self.assertNotIn("legacy_policy", [b["kind"] for b in out["blockers"]])

    def test_schema_1_message_names_the_skill(self):
        from engine import schemas
        errs = schemas.validate_policy(OLD_POLICY)
        self.assertTrue(any(SKILL in e for e in errs), errs)


# --------------------------------------------------------------------------------------------- 5, 6: re-detection


class RedetectionTests(LegacyCase):
    def test_item_disappears_after_migration(self):
        self.issues(issue(1), issue(2))
        self.w.drop_legacy_cache("a")
        self.assertEqual(2, self.w.ok("a", "next")["legacy"]["counts"]["issues"])
        self.close_all()
        out, git, gh = self.measure("validate")
        self.assertIn(["api", "graphql"], [a[:2] for a in gh])
        self.assertNotIn("legacy", out)
        out, git, gh = self.measure("next")
        self.assert_no_check(git, gh)
        self.assertNotIn("legacy", out)

    def test_a_local_signal_changes_the_key(self):
        self.local_audit_file()
        out, git, gh = self.measure("next")
        self.assert_one_check(git, gh)
        self.assertEqual(1, out["legacy"]["counts"]["files"])
        self.assertIn(".zzzops/PROJECT_AUDIT.md", out["legacy"]["files"])
        out, git, gh = self.measure("next")
        self.assert_no_check(git, gh)
        self.assertEqual(1, out["legacy"]["counts"]["files"])

    def test_old_ignore_blocks_are_local_signals(self):
        self.w.push_dev({".gitignore": "# BEGIN ZZZOPS DISPOSABLE MACHINERY\n.agents/zzzops/\n"
                                       "# END ZZZOPS DISPOSABLE MACHINERY\n",
                         ".zzzops/.gitignore": "# BEGIN ZZZOPS LOCAL STATE\nstate/\n# END ZZZOPS LOCAL STATE\n"})
        out = self.w.ok("a", "next")
        self.assertEqual(2, out["legacy"]["counts"]["files"])
        self.assertEqual({".gitignore", ".zzzops/.gitignore"}, set(out["legacy"]["files"]))

    def test_old_files_at_the_policy_commit_are_local_signals(self):
        self.w.push_dev({".zzzops/BOOTSTRAP.json": "{}\n", ".zzzops/ZZZOPS_LOCK.json": "{}\n",
                         ".zzzops/rules/a.md": "x\n"})
        out = self.w.ok("a", "next")
        self.assertEqual(3, out["legacy"]["counts"]["files"])
        self.assertEqual({".zzzops/BOOTSTRAP.json", ".zzzops/ZZZOPS_LOCK.json", ".zzzops/rules"},
                         set(out["legacy"]["files"]))

    def test_retired_install_roots_in_the_primary_worktree(self):
        cleanup = runpy.run_path(str(fx.ROOT / "plugins" / "zzzops" / "scripts" / "cleanup_legacy.py"))
        roots = list(cleanup["LEGACY_ROOTS"])
        self.assertGreater(len(roots), 10)
        primary = self.w.clones["a"].path
        for r in roots:
            os.makedirs(os.path.join(primary, r), exist_ok=True)
            with open(os.path.join(primary, r, "x"), "w") as fh:
                fh.write("x\n")
        out, git, gh = self.measure("next")
        self.assert_one_check(git, gh)
        item = out["legacy"]
        self.assertEqual(len(roots), item["counts"]["files"])
        self.assertEqual(10, len(item["files"]))                  # capped
        self.assertTrue(set(item["files"]) <= set(roots), item["files"])
        self.assertLess(len(json.dumps(item)), 8192)


# --------------------------------------------------------------------------------------------- 7: dismissal


def ignoring_policy():
    p = fx.load_template("POLICY.json")
    p["settings"]["legacy"] = {"ignore": True}
    return p


class IgnoreTests(LegacyCase):
    policy = ignoring_policy()

    def test_ignore_makes_no_check_and_shows_no_item(self):
        self.issues(issue(1), issue(2))
        self.local_audit_file()
        self.w.drop_legacy_cache("a")
        out, git, gh = self.measure("next")
        self.assert_no_check(git, gh)
        self.assertNotIn("legacy", out)
        self.assertEqual([], out["blockers"])
        out, git, gh = self.measure("validate")
        self.assertNotIn(["api", "graphql"], [a[:2] for a in gh])
        self.assertNotIn("ls-remote", git)
        self.assertNotIn("legacy", out)
        self.assertEqual([], out["policy"])


class IgnoreSchemaTests(unittest.TestCase):
    def policy(self, legacy=None):
        p = fx.load_template("POLICY.json")
        p["settings"]["integration_branch"] = "dev"
        if legacy is not None:
            p["settings"]["legacy"] = legacy
        return p

    def test_legacy_is_optional(self):
        from engine import schemas
        self.assertEqual([], schemas.validate_policy(self.policy()))
        self.assertEqual([], schemas.validate_policy(self.policy({"ignore": True})))
        self.assertEqual([], schemas.validate_policy(self.policy({"ignore": False})))

    def test_ignore_must_be_a_boolean(self):
        from engine import schemas
        for bad in ("yes", 1, None, []):
            self.assertNotEqual([], schemas.validate_policy(self.policy({"ignore": bad})), bad)

    def test_unknown_subkeys_are_refused(self):
        from engine import schemas
        self.assertNotEqual([], schemas.validate_policy(self.policy({"ignore": True, "extra": 1})))
        self.assertNotEqual([], schemas.validate_policy(self.policy("on")))

    def test_shipped_template_has_no_legacy_key(self):
        self.assertNotIn("legacy", fx.load_template("POLICY.json")["settings"])


# --------------------------------------------------------------------------------------------- 8: embedded and offline


class EmbeddedAndOfflineTests(LegacyCase):
    def test_writes_never_check(self):
        self.issues(issue(1))
        self.w.drop_legacy_cache("a")
        out, git, gh = self.measure("new", "--file", self.w.file({"title": "G", "spec": "s"}))
        self.assert_no_check(git, gh)
        g = out["created"]["id"]
        A = fx.Agent(self.w, "a", "claude:aaaa/w-1")
        self.w.reset_trace()
        card = A.start(g, "design")
        A.submit(g, "design", card, {"summary": "D"}, artifact="# D\n")
        lines = self.w.trace_lines()
        self.assertEqual([], [l for l in lines if l["cmd"][0] == "gh"])
        self.assertNotIn("ls-remote", [l["cmd"][1] for l in lines if l["cmd"][0] == "git"])
        self.assertEqual([], self.gh.load().get("graphql_searches", []))

    def test_offline_next_makes_no_check_and_writes_no_cache(self):
        self.issues(issue(1))
        self.w.ok("a", "next")
        self.w.drop_legacy_cache("a")
        shutil.move(self.w.remote, self.w.remote + ".away")
        try:
            out, git, gh = self.measure("next")
        finally:
            shutil.move(self.w.remote + ".away", self.w.remote)
        self.assertFalse(out["coordinator"]["current"])
        self.assert_no_check(git, gh)
        self.assertFalse(os.path.exists(self.w.legacy_cache("a")))


# --------------------------------------------------------------------------------------------- 9, 10: retries


class FailureTests(LegacyCase):
    def test_transient_failure_retries_after_a_day(self):
        self.issues(issue(1), issue(2))
        self.local_audit_file()
        self.faults(transient=1)
        t0 = self.w.now
        out, git, gh = self.measure("next")
        self.assertEqual(1, len(gh))
        self.assertIsNone(out["legacy"]["counts"]["issues"])
        self.assertEqual(1, out["legacy"]["counts"]["files"])
        c = self.cache()
        self.assertEqual(("retry", self.iso(t0 + DAY)), (c["github"], c["retry_after"]))
        self.assertIn("502", c["error"])
        self.assertIsNone(c["issues"])
        out, git, gh = self.measure("next", now=t0 + HOUR)
        self.assertEqual([], gh)
        self.assertIsNone(out["legacy"]["counts"]["issues"])
        out, git, gh = self.measure("next", now=t0 + 25 * HOUR)
        self.assertEqual(1, len(gh))
        self.assertEqual(2, out["legacy"]["counts"]["issues"])
        self.assertEqual("ok", self.cache()["github"])

    def test_graphql_error_retries_after_a_day(self):
        self.local_audit_file()
        self.faults(graphql_error=True)
        t0 = self.w.now
        out, _, gh = self.measure("next")
        self.assertEqual(1, len(gh))
        self.assertEqual(("retry", self.iso(t0 + DAY)), (self.cache()["github"], self.cache()["retry_after"]))
        self.assertIsNone(out["legacy"]["counts"]["issues"])

    def test_auth_failure_retries_after_a_week(self):
        self.issues(issue(1))
        self.local_audit_file()
        self.faults(auth=True)
        t0 = self.w.now
        out, git, gh = self.measure("next")
        self.assertEqual(1, len(gh))
        self.assertIsNone(out["legacy"]["counts"]["issues"])
        c = self.cache()
        self.assertEqual(("unavailable", self.iso(t0 + 7 * DAY)), (c["github"], c["retry_after"]))
        self.assertIn("gh auth login", c["error"])
        _, git, gh = self.measure("next", now=t0 + 2 * DAY)
        self.assertEqual([], gh)
        _, git, gh = self.measure("next", now=t0 + 8 * DAY)
        self.assertEqual(1, len(gh))

    def test_a_failure_keeps_the_last_successful_counts(self):
        self.issues(issue(1), issue(2))
        self.local_audit_file()
        t0 = self.w.now
        self.assertEqual(2, self.w.ok("a", "next")["legacy"]["counts"]["issues"])
        self.faults(transient=1)
        out = self.w.ok("a", "next", now=t0 + 25 * HOUR)
        c = self.cache()
        self.assertEqual("retry", c["github"])
        self.assertEqual((2, [1, 2]), (c["issue_count"], c["issues"]))
        self.assertEqual(2, out["legacy"]["counts"]["issues"])

    def test_active_item_is_rechecked_daily(self):
        self.issues(issue(1))
        self.w.drop_legacy_cache("a")
        t0 = self.w.now
        out, git, gh = self.measure("next")
        self.assert_one_check(git, gh)
        self.assertEqual(1, out["legacy"]["counts"]["issues"])
        _, git, gh = self.measure("next", now=t0 + HOUR)
        self.assert_no_check(git, gh)
        self.close_all()
        out, git, gh = self.measure("next", now=t0 + 25 * HOUR)
        self.assert_one_check(git, gh)
        self.assertNotIn("legacy", out)
        self.assertIsNone(self.cache()["retry_after"])


class NoGhTests(LegacyCase):
    fake_gh = False

    def test_gh_not_on_path(self):
        bindir = os.path.join(self.tmp, "gitonly")
        os.makedirs(bindir)
        os.symlink(shutil.which("git"), os.path.join(bindir, "git"))
        self.w.extra_env = {"PATH": bindir}
        self.local_audit_file()
        t0 = self.w.now
        out, git, gh = self.measure("next")
        self.assertEqual([], gh)
        self.assertIsNone(out["legacy"]["counts"]["issues"])
        c = self.cache()
        self.assertEqual(("unavailable", self.iso(t0 + 7 * DAY)), (c["github"], c["retry_after"]))


# --------------------------------------------------------------------------------------------- 11, 12: the counted set


class CountedSetTests(LegacyCase):
    def seed(self):
        self.issues(issue(10), issue(11, labels=("zzzops:schema:v2",)), issue(20, labels=(), marker=True),
                    issue(21, labels=("zzzops",), marker=True), issue(30, open=False), issue(40, labels=("bug",)),
                    issue(5))
        self.w.new(title="Linked", links={"issue": 5})

    def test_validate_exposes_the_counted_set(self):
        self.seed()
        rc, out = self.w.run("a", "validate")
        self.assertEqual(0, rc, out)
        item = out["legacy"]
        self.assertEqual([10, 11, 20, 21], sorted(set(item["issues"])))
        self.assertEqual([5], item["linked"])
        self.assertEqual(4, item["counts"]["issues"])
        self.assertFalse(item["truncated"])
        self.assertEqual({"labelled": LABELLED, "marked": MARKED}, item["queries"])
        received = self.gh.load()["graphql_searches"][-1]
        self.assertEqual(sorted(item["queries"].values()), sorted(received.values()))

    def test_queries_are_module_constants(self):
        from engine import legacy
        self.assertEqual({"labelled", "marked"}, set(legacy.QUERIES))

    def test_truncated_over_100(self):
        self.issues(*[issue(n) for n in range(100, 201)])
        rc, out = self.w.run("a", "validate")
        item = out["legacy"]
        self.assertTrue(item["truncated"])
        self.assertEqual(101, item["counts"]["issues"])
        self.assertEqual(100, len(item["issues"]))
        self.assertEqual(sorted(item["issues"]), item["issues"])
        out = self.w.ok("a", "next")
        self.assertNotIn("issues", out["legacy"])
        self.assertLess(len(json.dumps(out["legacy"])), 8192)

    def test_linked_issue_is_not_counted_by_next(self):
        self.issues(issue(5), issue(6))
        self.w.new(title="Linked", links={"issue": 5})
        self.w.drop_legacy_cache("a")
        out = self.w.ok("a", "next")
        self.assertEqual(1, out["legacy"]["counts"]["issues"])
        self.assertEqual([6], self.cache()["issues"])
        self.assertEqual([5], self.cache()["linked"])

    def test_only_linked_issues_means_no_item(self):
        self.issues(issue(5))
        self.w.new(title="Linked", links={"issue": 5})
        self.w.drop_legacy_cache("a")
        self.assertNotIn("legacy", self.w.ok("a", "next"))


# --------------------------------------------------------------------------------------------- 13: package


class PackageTests(unittest.TestCase):
    PLUGIN = fx.ROOT / "plugins" / "zzzops"

    def test_skill_is_shipped(self):
        pkg = runpy.run_path(str(fx.PLUGIN_CODE / "package.py"))
        self.assertIn(SKILL, pkg["SHIPPED_SKILLS"])
        for rel in ("references/REMOVED.md", "references/EXAMPLE.md"):
            self.assertIn(f"skills/{SKILL}/{rel}", pkg["REQUIRED_FILES"])
        for rel in ("SKILL.md", "agents/openai.yaml", "references/REMOVED.md", "references/EXAMPLE.md"):
            self.assertTrue((self.PLUGIN / "skills" / SKILL / rel).is_file(), rel)
        status = pkg["package_status"]()
        self.assertTrue(status["ok"], status)

    def test_retired_name_is_not_reused(self):
        cleanup = runpy.run_path(str(self.PLUGIN / "scripts" / "cleanup_legacy.py"))
        self.assertNotIn(SKILL, cleanup["LEGACY_SKILLS"])

    def test_removed_table_covers_r1_to_r15(self):
        text = (self.PLUGIN / "skills" / SKILL / "references" / "REMOVED.md").read_text(encoding="utf-8")
        for n in range(1, 16):
            self.assertRegex(text, rf"\bR{n}\b")

    def test_skill_uses_the_counted_set_and_never_reads_comments(self):
        text = (self.PLUGIN / "skills" / SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("legacy.queries", text)
        self.assertIn("gh api graphql --paginate", text)
        self.assertIn("--json title,body,state,labels", text)
        self.assertNotIn("--comments", text)


# --------------------------------------------------------------------------------------------- 14: bounded cost


class BoundedCostTests(unittest.TestCase):
    def costs(self, comments):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        w = fx.World(tmp, clones=("a",))
        gh = fx.FakeGitHub(w)
        w.bootstrap()
        gh.update(lambda st: st.__setitem__("legacy_issues", [issue(n, comments=comments) for n in (1, 2, 3)]))
        w.drop_legacy_cache("a")
        result = []
        for verb in ("next", "validate"):
            w.reset_trace()
            w.ok("a", verb)
            lines = w.trace_lines()
            result.append(([l["cmd"][1] for l in lines if l["cmd"][0] == "git"],
                           [l["cmd"][1:3] for l in lines if l["cmd"][0] == "gh"]))
            for l in lines:
                self.assertFalse(any("comments" in a for a in l["cmd"]), l["cmd"])
        return result

    def test_cost_does_not_grow_with_archived_comments(self):
        small, big = self.costs(0), self.costs(2000)
        self.assertEqual(small, big)
        self.assertEqual((["fetch", "ls-remote"], [["api", "graphql"]]), small[0])


if __name__ == "__main__":
    unittest.main()
