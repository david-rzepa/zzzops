"""G1038 regression: sticky policy waits retain the base needed to remove dependencies."""
from __future__ import annotations

import merge_sync_fixtures as msf
from engine.ops import base
from engine.ops.run import Blocked, Done


class StickyRecoveryTests(msf.OpFixture):
    def test_repeated_policy_blocks_keep_old_base_until_answered_dependency_drop(self):
        dep = self.w.seed.commit({"dependency-only.txt": "dependency\n"}, "feat: dependency content")
        self.w.seed.git("push", "-q", "origin", dep + ":refs/heads/zzzops/pr/g101")
        self.publish({"own.txt": "goal\n"}, "feat: goal change")
        first = self.run_base(inputs={"heads": {"101": dep}, "prs": {"101": {"number": 101}}},
                              dep_kinds={101: "open"})
        self.apply(first)
        self.assertIsNotNone(self.ident.entry(self.snap.work[1000], "dependency-only.txt"))
        self.settings["engine"] = {"requires": []}
        record = {"status": "done", "output": first.output}
        for _ in range(2):
            blocked = self.run_base(record=record)
            self.assertIsInstance(blocked, Blocked)
            self.assertEqual("policy", blocked.blocked["category"])
            self.assertEqual(dep, (blocked.blocked.get("op_state") or {}).get("old"))
            record = {"status": "blocked", "blocked": blocked.blocked}
        # The owner restores the capability and answers the existing policy item;
        # meanwhile the dependency was removed, so the original base must be kept.
        record["answer"] = {"text": "capability restored", "quote": "restored", "decided_by": "owner"}
        self.settings["engine"] = {"requires": ["merge_sync"]}
        ctx = self.ctx(record=record)
        ctx.answer = record["answer"]
        resumed = base.run(ctx)
        self.assertIsInstance(resumed, Done)
        self.assertEqual(dep, resumed.output["synced"]["old"])
        self.apply(resumed)
        self.assertIsNone(self.ident.entry(self.snap.work[1000], "dependency-only.txt"))
        self.assertEqual("goal", self.wt.git("show", "HEAD:own.txt"))
        self.assertEqual("", self.wt.git("status", "--porcelain"))
