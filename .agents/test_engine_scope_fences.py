"""G1049 safety checks for observed work and producer provenance across clones."""
import unittest

import test_engine_scope_recovery as recovery
import test_engine_blocked_scope as blocked


class ScopeFences(unittest.TestCase):
    def test_low_level_unregistered_push_refuses_work_update(self):
        import engine_fixtures as fx
        from engine.errors import Refused
        from engine.session import Session
        from engine.store import push_atomic

        journey = blocked.BlockedScopeJourney("test_before_capability_pending_blocked_work_is_not_published")
        journey.setUp()
        self.addCleanup(journey.doCleanups)
        journey.enable_capability()
        ref = f"refs/heads/zzzops/work/g{journey.g}"
        before = journey.w.remote_git("rev-parse", ref)
        proposed = journey.wt.commit({"src/new.py": "value = 1\n"}, "fix: unregistered writer")
        with fx.env_of(journey.w.cli_env()):
            session = Session(cwd=journey.w.clones["a"].path, now=fx.NOW)
            self.addCleanup(session.git.close)
            session.open(goals=[journey.g])
            with self.assertRaises(Refused):
                push_atomic(session.git, session.R, [(ref, before, proposed)])
        self.assertEqual(before, journey.w.remote_git("rev-parse", ref))

    def test_recovery_refuses_changed_work_since_preview(self):
        journey = recovery.RecoveryJourney("test_apply_proposal_requires_capability_and_retains_test_history")
        journey.setUp()
        self.addCleanup(journey.doCleanups)
        journey.damaged_history()
        proposal = journey.diagnostic()["proposal"]
        journey.activate_capability()
        tip = journey.tip()
        changed = journey.wt.commit({"src/new.py": "value = 1\n"}, "feat: work after preview")
        journey.wt.git("push", "-q", "origin", f"{changed}:refs/heads/zzzops/work/g{journey.g}")
        rc, out = journey.w.run("a", "edit", str(journey.g), "--file", journey.w.file(proposal["edit"]),
                                "--base", proposal["base"])
        self.assertNotEqual(0, rc, out)
        self.assertEqual(tip, journey.tip())

    def test_mixed_pending_candidates_require_and_show_explicit_selection(self):
        journey = blocked.BlockedScopeJourney("test_ambiguous_blocked_source_and_gitlink_are_not_silently_frozen")
        journey.setUp()
        self.addCleanup(journey.doCleanups)
        journey.accept_tests()
        journey.enable_capability()
        journey.w.ok("a", "reopen", str(journey.g), "test_design", "--note", "mixed candidates")
        first = journey.a.start(journey.g, "test_design")
        journey.wt.commit({"tests/new.py": "assert 3\n", "src/extra.py": "value = 1\n"}, "test: mixed candidates")
        journey.a.submit(journey.g, "test_design", first, blocked={"waiting_for": "agent", "instructions": "resume"})
        retry = journey.a.start(journey.g, "test_design")
        responses = {f["id"]: "fixed: tests" for f in retry.get("corrections", [])}
        rc, out = journey.a.submit(journey.g, "test_design", retry, {"commands": ["true"], "responses": responses}, ok=False)
        self.assertNotEqual(0, rc, out)
        self.assertEqual(["src/extra.py", "tests/new.py"], out["error"]["details"]["candidates"])
        journey.a.submit(journey.g, "test_design", retry,
                         {"commands": ["true"], "responses": responses, "scope_selection": ["tests/new.py"]})
        record = journey.record()
        self.assertNotIn("src/extra.py", record["frozen"])
        card = journey.b.start(journey.g, "review_tests")
        self.assertEqual(["src/extra.py"], card["context"]["scope_review"]["excluded"])

    def test_producer_attempt_evidence_survives_a_different_clone(self):
        journey = blocked.BlockedScopeJourney("test_capability_enabled_two_blocked_attempts_then_noop_retry_protects_all_tests")
        journey.setUp()
        self.addCleanup(journey.doCleanups)
        journey.accept_tests()
        journey.enable_capability()
        journey.w.ok("a", "reopen", str(journey.g), "test_design", "--note", "additional test")
        first = journey.a.start(journey.g, "test_design")
        journey.wt.commit({"tests/three.py": "assert 3\n"}, "test: blocked test")
        journey.a.submit(journey.g, "test_design", first,
                         blocked={"waiting_for": "agent", "instructions": "resume"})
        resumed = journey.b.start(journey.g, "test_design")
        responses = {f["id"]: "fixed: accepted test" for f in resumed.get("corrections", [])}
        journey.b.submit(journey.g, "test_design", resumed, {"commands": ["true"], "responses": responses})
        self.assertIn("tests/three.py", journey.record()["frozen"])


if __name__ == "__main__":
    unittest.main()
