"""G1016: cards and lease verbs explain restarts, staleness and findings (design .zzzops/reviews/1016/design.md).

Covers: `abandon` prints the restart command; reclaim cards carry `stale_because` (lease and record staleness) and a
`changed` pointer; capability keys on record staleness only; `submit` refusals list the findings to answer;
`output_schema` wording; the single renew entry; full-sha checkpoint overrides (submit and edit); the docs lines.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import unittest

import engine_fixtures as fx
from engine import schemas
from test_engine_lifecycle import Journey

T = fx.NOW


class CardJourney(Journey):
    def at(self, agent, k, *argv):
        """Run a CLI verb for `agent` at NOW + k minutes (the goal-commit pointer needs distinct commit times)."""
        return self.w.ok(agent.clone, *argv, now=T + 60 * k)

    def start_at(self, agent, k, g, node, *extra):
        return self.at(agent, k, "start", str(g), self.n(node), "--as", agent.label, *extra)

    def abandon_at(self, agent, k, g, node, attempt):
        return self.at(agent, k, "abandon", str(g), self.n(node), "--attempt", str(attempt))

    def edit_spec_at(self, k, g, text):
        tip = self.show(g)["goal_commit"]
        return self.w.ok("b", "edit", str(g), "--set", "spec=" + json.dumps(text), "--base", tip, now=T + 60 * k)

    def run_pointer(self, clone, cmd):
        p = subprocess.run(shlex.split(cmd), cwd=self.w.clones[clone].path, capture_output=True, text=True, env=self.w.env)
        self.assertEqual(0, p.returncode, p.stderr)
        return p.stdout

    def restack_base(self, g, k, agent=None):
        """Move dev, reopen `base` and re-run it with the new base commit (the stub base is an agent node)."""
        agent = agent or self.B
        moved = self.w.push_dev({f"other-{k}.txt": f"{k}\n"})
        self.w.ok("a", "reopen", str(g), self.n("base"), "--note", "restack", now=T + 60 * k)
        c = self.start_at(agent, k + 1, g, "base")
        out = {"base_commit": moved, "stack": [], "branch": f"zzzops/work/g{g}",
               "responses": {f["id"]: "fixed: restacked" for f in c["corrections"]}}
        argv = ["submit", str(g), self.n("base"), "--attempt", str(c["lease"]["attempt"]), "--as", agent.label,
                "--output", self.w.file(out)]
        self.w.ok(agent.clone, *argv, now=T + 60 * (k + 2))
        return moved


# --------------------------------------------------------------------------------------------- 1. abandon


class AbandonRestartTests(CardJourney):
    def test_abandon_prints_the_restart_command(self):
        g = self.goal()
        self.A.start(g, self.n("design"))
        out = self.w.ok("a", "abandon", str(g), self.n("design"), "--attempt", "1")
        self.assertEqual(["start", str(g), self.n("design"), "--as", "<LABEL>", "--reclaim", "--repo"],
                         out["restart"]["argv"][:-1])          # G1028: worker commands carry --repo <primary>
        self.assertIn("--reclaim", out["restart"]["command"])
        self.assertIn("restart", out["hint"])
        rc, err = self.w.run("b", "start", str(g), self.n("design"), "--as", self.B.label)
        self.assertEqual("not_ready", err["error"]["code"])
        argv = [self.B.label if a == "<LABEL>" else a for a in out["restart"]["argv"]]
        c = self.w.ok("b", *argv)
        self.assertEqual((2, "reclaim"), (c["lease"]["attempt"], c["reason"]))

    def test_forced_abandon_prints_the_same_restart(self):
        g = self.goal()
        self.A.start(g, self.n("design"))
        out = self.w.ok("b", "abandon", str(g), self.n("design"), "--force", "--note", "stuck")
        self.assertEqual(["start", str(g), self.n("design"), "--as", "<LABEL>", "--reclaim", "--repo"],
                         out["restart"]["argv"][:-1])          # G1028: worker commands carry --repo <primary>


# --------------------------------------------------------------------------------------------- 2. stale_because / changed


class ReclaimStalenessTests(CardJourney):
    def test_reclaim_after_a_spec_edit_says_what_changed(self):
        g = self.goal()
        self.start_at(self.A, 0, g, "design")
        self.edit_spec_at(1, g, "spec for Cut\n\nNEW LINE: handle empty input")
        self.abandon_at(self.A, 2, g, "design", 1)
        c = self.start_at(self.B, 3, g, "design", "--reclaim")
        self.assertEqual("reclaim", c["reason"])
        self.assertEqual(["inputs.spec"], c["stale_because"])
        diff = c["changed"]["inputs.spec"]["diff"]
        self.assertTrue(diff.startswith("git diff "), diff)
        self.assertIn("NEW LINE: handle empty input", self.run_pointer("b", diff))

    def test_reclaim_with_no_edit_has_no_staleness(self):
        g = self.goal()
        self.start_at(self.A, 0, g, "design")
        self.abandon_at(self.A, 1, g, "design", 1)
        c = self.start_at(self.B, 2, g, "design", "--reclaim")
        self.assertEqual("reclaim", c["reason"])
        self.assertNotIn("stale_because", c)
        self.assertNotIn("changed", c)

    def test_reclaim_keeps_record_staleness_of_the_abandoned_attempt(self):
        """Union: attempt 3 never saw attempt 2's card, so it must still learn the record-stale keys."""
        g = self.goal()
        c = self.A.start(g, self.n("design"))
        self.A.submit(g, self.n("design"), c, {"summary": "D"}, artifact="# D\n")
        self.edit_spec_at(1, g, "spec for Cut\n\nUNION LINE")
        c2 = self.start_at(self.A, 2, g, "design")
        self.assertEqual(["inputs.spec"], c2["stale_because"])
        self.abandon_at(self.A, 3, g, "design", 2)
        c3 = self.start_at(self.B, 4, g, "design", "--reclaim")
        self.assertEqual((3, "reclaim"), (c3["lease"]["attempt"], c3["reason"]))
        self.assertIn("inputs.spec", c3["stale_because"])
        self.assertIn("UNION LINE", self.run_pointer("b", c3["changed"]["inputs.spec"]["diff"]))

    def test_crash_loop_reclaim_after_an_edit(self):
        """N4: a lease crash loop taken with --force --reclaim gets the lease-side staleness too."""
        g = self.goal()
        self.start_at(self.A, 0, g, "design")
        for i in (1, 2):
            self.abandon_at(self.A, 2 * i - 1, g, "design", i)
            self.start_at(self.A, 2 * i, g, "design", "--reclaim")
        self.abandon_at(self.A, 5, g, "design", 3)
        rc, err = self.w.run("b", "start", str(g), self.n("design"), "--as", self.B.label, "--reclaim", now=T + 360)
        self.assertEqual("crash_loop", err["error"]["code"])
        self.edit_spec_at(7, g, "spec for Cut\n\nLOOP LINE")
        c = self.start_at(self.B, 8, g, "design", "--force", "--reclaim")
        self.assertEqual(["inputs.spec"], c["stale_because"])


class CapabilityTests(CardJourney):
    """F1 and review_tests:2:2: lease-side staleness never changes capability; `routine` needs record staleness
    exactly ["inputs.base"] and no live corrections (design section 2, attempt 4)."""

    def test_reclaimed_first_attempt_after_base_moved_keeps_its_capability(self):
        g = self.goal()
        self.through_design(g)
        self.start_at(self.A, 1, g, "test_design")
        self.restack_base(g, 2)
        self.abandon_at(self.A, 5, g, "test_design", 1)
        c = self.start_at(self.A, 6, g, "test_design", "--reclaim")
        self.assertEqual("reclaim", c["reason"])
        self.assertEqual(["inputs.base"], c["stale_because"])
        self.assertEqual("reasoning", c["run"]["capability"])          # test_design's own, not routine
        self.assertNotIn("inputs.base", c.get("changed") or {})        # plain node outputs get no pointer

    def next_action(self, agent, k, g, node):
        """The `next --goal g` action for `node` at NOW + k minutes (implement:3:1: next and the card share one rule)."""
        acts = [a for a in self.at(agent, k, "next", "--goal", str(g))["actions"] if a["node"] == self.n(node)]
        self.assertEqual(1, len(acts), acts)
        return acts[0]

    def _reopen_test_design(self, g):
        """Submit test_design, then have review_tests request a change on it (a live correction)."""
        self.through_design(g)
        c = self.A.start(g, self.n("test_design"))
        self.A.worktree(g).commit({"tests/test_cut.py": "def test_cut():\n    assert cut() == 1\n"}, "test: cut")
        self.A.submit(g, self.n("test_design"), c, {"commands": ["python -m pytest tests"]})
        self.review(self.B, g, "review_tests", "changes_requested", [{"target": self.n("test_design"), "text": "more"}])

    def test_reclaimed_reopened_correction_keeps_its_capability(self):
        """review_tests:2:2 (reclaim path): base moves during a reopened correction run, then abandon and reclaim.
        The record was produced on the old base, so record_stale is also ["inputs.base"]; the live correction
        is what keeps the node's own capability."""
        g = self.goal()
        self._reopen_test_design(g)
        c = self.start_at(self.A, 1, g, "test_design")
        self.assertEqual("reopened", c["reason"])
        self.assertNotIn("stale_because", c)
        self.restack_base(g, 2)
        self.abandon_at(self.A, 5, g, "test_design", c["lease"]["attempt"])
        a = self.next_action(self.A, 6, g, "test_design")
        self.assertEqual(("reasoning", 1), (a["capability"], a.get("corrections")))
        c = self.start_at(self.A, 6, g, "test_design", "--reclaim")
        self.assertEqual("reclaim", c["reason"])
        self.assertEqual(["inputs.base"], c["stale_because"])
        self.assertTrue(c["corrections"])
        self.assertEqual("reasoning", c["run"]["capability"])          # live correction: own capability, not routine

    def test_plain_start_of_reopened_node_after_base_moved_keeps_its_capability(self):
        """review_tests:2:2 (no-lease path, deliberate change): a reopened test_design whose base has since moved
        starts as ready-stale on ["inputs.base"] with its corrections; it keeps its own capability."""
        g = self.goal()
        self._reopen_test_design(g)
        self.restack_base(g, 1)
        a = self.next_action(self.A, 4, g, "test_design")
        self.assertEqual(("reasoning", 1), (a["capability"], a.get("corrections")))
        c = self.start_at(self.A, 4, g, "test_design")
        self.assertEqual("stale", c["reason"])
        self.assertEqual(["inputs.base"], c["stale_because"])
        self.assertTrue(c["corrections"])
        self.assertEqual("reasoning", c["run"]["capability"])          # open finding is real work, not a rebase

    def test_record_stale_only_on_base_is_routine_on_start_and_after_reclaim(self):
        """Control: no corrections and a record stale only on base is a rebase, so `routine`."""
        g = self.goal()
        self.through_tests(g)
        self.restack_base(g, 1)
        a = self.next_action(self.A, 4, g, "test_design")
        self.assertEqual("routine", a["capability"])
        self.assertNotIn("corrections", a)
        c = self.start_at(self.A, 4, g, "test_design")
        self.assertEqual(["inputs.base"], c["stale_because"])
        self.assertFalse(c.get("corrections"))
        self.assertEqual("routine", c["run"]["capability"])
        self.abandon_at(self.A, 5, g, "test_design", c["lease"]["attempt"])
        c = self.start_at(self.A, 6, g, "test_design", "--reclaim")
        self.assertEqual("reclaim", c["reason"])
        self.assertEqual(["inputs.base"], c["stale_because"])
        self.assertEqual("routine", c["run"]["capability"])


class ArtifactPointerTests(CardJourney):
    def _reclaim_review_after_redesign(self, g, drop_old_blob=False):
        c = self.A.start(g, self.n("design"))
        self.A.submit(g, self.n("design"), c, {"summary": "D"}, artifact="# Design one\n")
        old = self.show(g)["goal"]["records"][self.n("design")]["output"]["doc"]["blob"]
        self.start_at(self.B, 1, g, "review_design")
        self.edit_spec_at(2, g, "spec for Cut\n\nREDESIGN")
        c = self.start_at(self.A, 3, g, "design")
        argv = ["submit", str(g), self.n("design"), "--attempt", str(c["lease"]["attempt"]), "--as", self.A.label,
                "--output", self.w.file({"summary": "D2"})]
        art = os.path.join(self.w.tmp, "files", "redesign.md")
        with open(art, "w", encoding="utf-8") as fh:
            fh.write("# Design two\n")
        self.w.ok("a", *argv, "--artifact", art, now=T + 240)
        new = self.show(g)["goal"]["records"][self.n("design")]["output"]["doc"]["blob"]
        self.assertNotEqual(old, new)
        self.abandon_at(self.B, 5, g, "review_design", 1)
        if drop_old_blob:
            drop_object(self.w.clones["b"], old)
        self.w.reset_trace()
        card = self.start_at(self.B, 6, g, "review_design", "--reclaim")
        return card, old, new

    def test_artifact_input_gets_a_blob_diff(self):
        g = self.goal()
        c, old, new = self._reclaim_review_after_redesign(g)
        self.assertIn("inputs.doc", c["stale_because"])
        self.assertEqual({"diff": f"git diff {old} {new}"}, c["changed"]["inputs.doc"])
        self.assertIn("Design two", self.run_pointer("b", c["changed"]["inputs.doc"]["diff"]))

    def test_missing_old_blob_gives_a_note_and_no_fetch(self):
        g = self.goal()
        c, old, new = self._reclaim_review_after_redesign(g, drop_old_blob=True)
        entry = c["changed"]["inputs.doc"]
        self.assertNotIn("diff", entry)
        self.assertIn("not available", entry["note"])
        fetches = [t for t in self.w.trace_lines() if t["cmd"][:2] == ["git", "fetch"]
                   and any(a.startswith(f"+refs/heads/zzzops/work/g{g}:") for a in t["cmd"])]
        self.assertEqual([], fetches)


def drop_object(repo: fx.GitDir, sha: str):
    """Make one object unavailable locally: unpack every pack, then delete that loose object."""
    gitdir = repo.git("rev-parse", "--git-common-dir")
    gitdir = gitdir if os.path.isabs(gitdir) else os.path.join(repo.path, gitdir)
    packdir = os.path.join(gitdir, "objects", "pack")
    for name in sorted(os.listdir(packdir)) if os.path.isdir(packdir) else []:
        if name.endswith(".pack"):
            full = os.path.join(packdir, name)
            moved = full + ".old"
            os.rename(full, moved)
            os.remove(full[:-5] + ".idx")
            with open(moved, "rb") as fh:
                subprocess.run(["git", "-C", repo.path, "unpack-objects", "-q"], stdin=fh, check=True, env=repo.env)
            os.remove(moved)
    loose = os.path.join(gitdir, "objects", sha[:2], sha[2:])
    if os.path.exists(loose):
        os.chmod(loose, 0o644)
        os.remove(loose)
    p = subprocess.run(["git", "-C", repo.path, "cat-file", "-e", sha], env=repo.env, capture_output=True)
    assert p.returncode != 0, "the object is still available"


# --------------------------------------------------------------------------------------------- 3. submit refusal


class SubmitRefusalTests(CardJourney):
    def test_refusal_lists_findings_that_arrived_while_running(self):
        g = self.goal()
        c = self.A.start(g, self.n("design"))
        self.A.submit(g, self.n("design"), c, {"summary": "D"}, artifact="# D\n")
        self.review(self.B, g, "review_design", "changes_requested", [{"text": "handle the empty spec"}])
        c = self.A.start(g, self.n("design"))
        first = c["corrections"][0]["id"]
        late = self.w.ok("b", "reopen", str(g), self.n("design"), "--note", "also cover the CLI help text")["finding"]
        rc, err = self.A.submit(g, self.n("design"), c, {"summary": "D", "responses": {first: "fixed: done"}},
                                artifact="# D\n", ok=False)
        self.assertEqual("validation", err["error"]["code"])
        d = err["error"]["details"]
        self.assertEqual([late["id"]], [x["id"] for x in d["respond_to"]])
        item = d["respond_to"][0]
        self.assertEqual((self.n("design"), self.n("design"), "also cover the CLI help text", False),
                         (item["from"], item["target"], item["text"], item["upheld"]))
        self.assertIn("no_longer_live", err["error"]["hint"])
        rc, err = self.A.submit(g, self.n("design"), c, {"summary": "D"}, artifact="# D\n", ok=False)
        by_id = {x["id"]: x for x in err["error"]["details"]["respond_to"]}
        self.assertEqual({first, late["id"]}, set(by_id))
        self.assertEqual((self.n("review_design"), self.n("design"), "handle the empty spec"),
                         (by_id[first]["from"], by_id[first]["target"], by_id[first]["text"]))

    def test_refusal_names_responses_that_are_no_longer_live(self):
        g = self.goal()
        c = self.A.start(g, self.n("design"))
        self.A.submit(g, self.n("design"), c, {"summary": "D"}, artifact="# D\n")
        self.review(self.B, g, "review_design", "changes_requested", [{"text": "simpler"}])
        c = self.A.start(g, self.n("design"))
        fid = c["corrections"][0]["id"]
        gone = f"{self.n('review_design')}:9:9"
        rc, err = self.A.submit(g, self.n("design"), c, {"summary": "D", "responses": {fid: "fixed: x", gone: "fixed: y"}},
                                artifact="# D\n", ok=False)
        self.assertEqual("validation", err["error"]["code"])
        self.assertEqual([gone], err["error"]["details"]["no_longer_live"])
        self.assertEqual([], err["error"]["details"].get("respond_to") or [])

    def test_long_finding_text_is_clipped_with_a_full_view(self):
        g = self.goal()
        c = self.A.start(g, self.n("design"))
        self.A.submit(g, self.n("design"), c, {"summary": "D"}, artifact="# D\n")
        long_text = "x" * 900
        self.review(self.B, g, "review_design", "changes_requested", [{"text": long_text}])
        c = self.A.start(g, self.n("design"))
        rc, err = self.A.submit(g, self.n("design"), c, {"summary": "D"}, artifact="# D\n", ok=False)
        item = err["error"]["details"]["respond_to"][0]
        self.assertLess(len(item["text"]), len(long_text))
        self.assertIn("full", item)


# --------------------------------------------------------------------------------------------- 4, 5. card text


class CardTextTests(CardJourney):
    def assert_renew(self, c):
        self.assertNotIn("renew", c)
        when = c["commands"]["renew"]["when"]
        self.assertIn(str(c["lease"]["renew_every_minutes"]), when)
        self.assertIn(str(c["lease"]["timeout_minutes"]), when)
        self.assertEqual(["renew", str(c["goal"]), c["node"], "--attempt", str(c["lease"]["attempt"]), "--repo"],
                         c["commands"]["renew"]["argv"][:-1])            # G1028: --repo <primary>

    def test_non_review_card_with_artifact(self):
        g = self.goal()
        c = self.A.start(g, self.n("design"))
        f = c["output_schema"]["findings"]
        self.assertIn("reopens", f)
        self.assertIn("if that ancestor's output changes", f)
        self.assertIn("artifact.path", c["output_schema"]["doc"])
        self.assertIn("--artifact", c["output_schema"]["doc"])
        self.assert_renew(c)

    def test_review_card(self):
        g = self.goal()
        c = self.A.start(g, self.n("design"))
        self.A.submit(g, self.n("design"), c, {"summary": "D"}, artifact="# D\n")
        c = self.B.start(g, self.n("review_design"))
        f = c["output_schema"]["findings"]
        self.assertIn("reopens its target", f)
        self.assertIn("responses", f)
        self.assert_renew(c)

    def test_checkpoint_card(self):
        g = self.goal()
        self.through_design(g)
        c = self.A.start(g, self.n("test_design"))
        t = c["output_schema"]["tests"]
        self.assertTrue(t.startswith("checkpoint (optional)"), t)
        self.assertIn("omit the key", t)
        self.assertIn("full 40-hex sha", t)
        self.assertIn("work branch's HEAD", t)
        self.assertIn("reopens", c["output_schema"]["findings"])
        self.assert_renew(c)


# --------------------------------------------------------------------------------------------- 4a. full-sha overrides


class CheckpointSchemaTests(unittest.TestCase):
    def setUp(self):
        self.g = schemas.build_graph("default", fx.load_template("workflow.json")["graphs"]["default"])

    def test_override_must_be_a_full_lowercase_sha(self):
        for v in ("HEAD", "main", "zzzops/goal/g1", "0123456789ab", "A" * 40, "a" * 39, "a" * 41):
            errs = schemas.validate_submit_output(self.g, "implement", {"summary": "s", "code": {"commit": v}})
            self.assertTrue(errs, v)
            self.assertTrue(any("40-hex" in e for e in errs), (v, errs))
        self.assertEqual([], schemas.validate_submit_output(self.g, "implement", {"summary": "s", "code": {"commit": "a" * 40}}))
        self.assertEqual([], schemas.validate_submit_output(self.g, "implement", {"summary": "s"}))

    def test_override_message_says_to_omit_the_key(self):
        errs = schemas.validate_submit_output(self.g, "test_design", {"commands": ["t"], "tests": {"commit": "HEAD"}})
        self.assertTrue(any("omit the key" in e for e in errs), errs)


class CheckpointSubmitTests(CardJourney):
    def test_implement_override_needs_a_full_sha(self):
        g = self.goal()
        self.through_tests(g)
        c = self.A.start(g, self.n("implement"))
        wtd = self.A.worktree(g)
        head = wtd.commit({"src/cut.py": "def cut():\n    return 1\n"}, "feat: cut")
        before = self.show(g)["goal_commit"]
        for v in ("HEAD", head[:12], f"zzzops/work/g{g}"):
            rc, err = self.A.submit(g, self.n("implement"), c, {"summary": "Built.", "code": {"commit": v}}, ok=False)
            self.assertEqual("validation", err["error"]["code"], (v, err))
            self.assertIn("40-hex", json.dumps(err["error"]), v)
        self.assertEqual(before, self.show(g)["goal_commit"])          # nothing recorded
        outside = wtd.git("commit-tree", wtd.git("rev-parse", "HEAD^{tree}"), "-m", "unrelated root")
        rc, err = self.A.submit(g, self.n("implement"), c, {"summary": "Built.", "code": {"commit": outside}}, ok=False)
        self.assertEqual("validation", err["error"]["code"])
        self.assertIn("is not in the work branch", err["error"]["message"])
        rc, err = self.A.submit(g, self.n("implement"), c, {"summary": "Built.", "code": {"commit": "e" * 40}}, ok=False)
        self.assertEqual("validation", err["error"]["code"])
        self.assertIn("does not exist", err["error"]["message"])
        self.A.submit(g, self.n("implement"), c, {"summary": "Built.", "code": {"commit": head}})
        self.assertEqual(head, self.show(g)["goal"]["records"][self.n("implement")]["output"]["code"]["commit"])


class RecordCompletionTests(CardJourney):
    def edit_code(self, g, commit):
        tip = self.show(g)["goal_commit"]
        return self.w.run("b", "edit", str(g), "--set", f'records.{self.n("implement")}.output.code=' + json.dumps({"commit": commit}),
                          "--set", f'records.{self.n("implement")}.input_fp="current"', "--base", tip)

    def test_edit_completion_needs_a_full_existing_sha(self):
        g = self.goal()
        self.through_impl(g)
        real = self.show(g)["goal"]["records"][self.n("implement")]["output"]["code"]["commit"]
        rc, err = self.edit_code(g, "HEAD")
        self.assertEqual("validation", err["error"]["code"], err)
        self.assertIn("full 40-hex sha", err["error"]["message"])
        rc, err = self.edit_code(g, "e" * 40)
        self.assertEqual("validation", err["error"]["code"], err)
        self.assertIn("does not exist", err["error"]["message"])
        rc, out = self.edit_code(g, real)
        self.assertEqual(0, rc, out)
        cp = self.show(g)["goal"]["records"][self.n("implement")]["output"]["code"]
        self.assertEqual({"commit", "base", "tree", "change"}, set(cp))
        self.assertEqual(real, cp["commit"])


# --------------------------------------------------------------------------------------------- docs


class DocsTests(unittest.TestCase):
    def setUp(self):
        self.usage = (fx.PLUGIN_CODE / "references" / "CLI_USAGE.md").read_text(encoding="utf-8")

    def test_cli_usage_trace_line(self):
        line = next((l for l in self.usage.splitlines() if "ZZZOPS_TRACE" in l), "")
        for word in ("fetch", "push", "ls-remote", "gh", "cmd", "rc", "ms", "Local git commands are not traced"):
            self.assertIn(word, line)

    def test_cli_usage_abandon_row_mentions_restart(self):
        row = next(l for l in self.usage.splitlines() if l.startswith("| `abandon"))
        self.assertIn("restart", row)

    def test_cli_usage_outputs_paragraph(self):
        para = next(l for l in self.usage.splitlines() if l.startswith("**Outputs**"))
        self.assertIn("full 40-hex sha", para)
        self.assertIn("work branch's HEAD", para)
        self.assertNotIn("else `HEAD`", para)

    def test_prompts_name_full_shas(self):
        # Template prompts only: this repo's .zzzops/prompts follow through a separate policy change.
        for d in (fx.TEMPLATES / "prompts",):
            td = (d / "test_design.md").read_text(encoding="utf-8")
            self.assertIn('{"tests": {"commit": "<full 40-hex sha>"}}', td, d)
            im = (d / "implement.md").read_text(encoding="utf-8")
            self.assertNotIn("else HEAD.", im, d)
            self.assertIn("work branch's HEAD", im, d)


    def test_migrating_names_full_sha(self):
        text = (fx.PLUGIN_CODE / "references" / "MIGRATING.md").read_text(encoding="utf-8")
        self.assertIn('"commit": "<full 40-hex sha>"', text)

    def test_no_short_sha_checkpoint_override_shown(self):
        # Engine, references, skills and templates only; this repo's .zzzops/prompts is policy (separate change).
        roots = (fx.PLUGIN_CODE / "engine", fx.PLUGIN_CODE / "references", fx.PLUGIN_CODE / "templates",
                 fx.PLUGIN_CODE.parent / "skills")
        bad = ('"commit": "<sha>"', '\\"commit\\": \\"<sha>\\"')
        for root in roots:
            for f in sorted(root.rglob("*")):
                if not f.is_file() or f.suffix in (".pyc", ".png"):
                    continue
                text = f.read_text(encoding="utf-8", errors="ignore")
                for b in bad:
                    self.assertNotIn(b, text, str(f))


class RenamedCardTests(ReclaimStalenessTests):
    renamed = True


if __name__ == "__main__":
    unittest.main()
