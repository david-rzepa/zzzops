"""Small real-Git op fixture for G1038; avoids repeating whole goal journeys."""
from __future__ import annotations

import copy
import json
import os
import shutil
import tempfile
from types import SimpleNamespace
import unittest

import engine_fixtures as fx
from engine import worktree
from engine.gh import Gh
from engine.identity import Identity
from engine.ops.run import OpContext, Done
from engine.schemas import build_graph


class OpFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.w = fx.World(self.tmp, clones=("a",))
        self.fake = fx.FakeGitHub(self.w)
        self.w.bootstrap(settings={"verification.required_ci": []})
        self.env = self.w.cli_env()
        self.env_scope = fx.env_of(self.env)
        self.env_scope.__enter__()
        self.addCleanup(self.env_scope.__exit__, None, None, None)
        self.repo = self.w.clones["a"]
        self.repo.git("fetch", "-q", "origin", "dev")
        self.base = self.repo.git("rev-parse", "FETCH_HEAD")
        self.git = fx.engine_git(self.repo, self.w.now)
        self.ident = Identity(self.git)
        self.graph = build_graph("default", fx.load_template("workflow.json")["graphs"]["default"])
        self.doc = {"id": 1000, "title": "Merge sync probe", "skip": {}, "records": {}}
        self.snap = SimpleNamespace(R="origin", I="dev", integration=self.base,
                                    work={1000: self.base}, stack={}, pr={}, goals={})
        self.path = worktree.ensure_worktree(self.git, self.snap, 1000)
        self.wt = fx.GitDir(self.path, self.env)
        self.git.run("push", "-q", "origin", f"{self.base}:refs/heads/zzzops/work/g1000")
        self.settings = copy.deepcopy(self.w.policy["settings"])
        self.settings["engine"] = {"requires": ["merge_sync"]}
        self.session = SimpleNamespace(git=self.git, R="origin", settings=self.settings)

    def ctx(self, node="base", inputs=None, record=None):
        return OpContext(goal=1000, doc=self.doc, node=node, node_def=self.graph.nodes[node],
                         inputs=inputs or {}, producers={"code": "implement", "pr": "integrate"},
                         dep_kinds={}, record=record, corrections=[], answer=None, settings=self.settings,
                         snap=self.snap, git=self.git, gh=Gh(self.session), worktree=self.path,
                         now=self.w.now, renew=lambda: None, graph=self.graph)

    def publish(self, files, subject, timestamp=None):
        previous_env = self.wt.env
        if timestamp is not None:
            self.wt.env = dict(previous_env, GIT_AUTHOR_DATE=f"@{timestamp} +0000",
                               GIT_COMMITTER_DATE=f"@{timestamp} +0000")
        try:
            tip = self.wt.commit(files, subject)
        finally:
            self.wt.env = previous_env
        self.wt.git("push", "-q", "origin", f"{tip}:refs/heads/zzzops/work/g1000")
        self.snap.work[1000] = tip
        return tip

    def trunk(self, files, subject="chore: trunk moves"):
        tip = self.w.push_dev(files, subject)
        self.repo.git("fetch", "-q", "origin", "dev")
        self.snap.integration = tip
        return tip

    def run_base(self, old=None, record=None, inputs=None, target=None, dep_kinds=None):
        from engine.ops import base
        rec = record or {"status": "done", "output": {"base_commit": old or self.base}}
        ctx = self.ctx(inputs=inputs, record=rec)
        ctx.target = target
        ctx.dep_kinds = dep_kinds or {}
        return base.run(ctx)

    def apply(self, out):
        """Apply the op's declared writes as the root op runner does, then its callback."""
        self.assertIsInstance(out, Done, getattr(out, "blocked", out))
        self.assertTrue(out.ok, out)
        from engine.store import push_atomic
        if out.ref_updates:
            result, _ = push_atomic(self.git, self.snap.R, out.ref_updates)
            self.assertEqual("ok", result)
        for ref, _, new in out.ref_updates:
            if ref == "refs/heads/zzzops/work/g1000":
                self.snap.work[1000] = new
        if out.after_push:
            out.after_push()
        return out.output

    def checkpoint_record(self, commit, frozen=("tests/probe.txt",)):
        cp = {"commit": commit, "base": self.base, "tree": self.ident.code_tree(commit),
              "change": self.ident.change(self.base, commit)}
        self.doc["records"]["test_design"] = {"status": "done", "frozen": list(frozen),
                                               "output": {"tests": cp, "commands": ["true"]}}
        return cp

    def integrate(self):
        from engine.ops import integrate
        tip = self.snap.work[1000]
        ctx = self.ctx("integrate", {"base": self.base, "code": self.ident.code_tree(tip),
                                      "stack": [], "summary": "Probe"})
        return integrate.run(ctx)

    def pr_commits(self, out):
        self.assertIsInstance(out, Done, getattr(out, "blocked", out))
        self.assertTrue(out.ok, out)
        tip = out.output["pr"]["head"]
        return self.git.out("rev-list", "--reverse", f"{self.base}..{tip}").split()
