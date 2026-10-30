"""Behavioral contract for resumable, authority-preserving PR stack integration."""
from __future__ import annotations

import copy
import importlib.util
import unittest
from pathlib import Path


MODULE = Path(__file__).parents[1] / "plugins" / "zzzops" / "zzzops" / "stack_integration.py"


def subject():
    spec = importlib.util.spec_from_file_location("stack_integration_subject", MODULE)
    if spec is None or spec.loader is None:
        raise AssertionError("stack integration product module is missing")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def member(number, branch, base, head, base_head, *, authorization=True,
           review=True, checks=True, release=True, owner=None):
    return {
        "goal": number, "pr": number, "branch": branch, "base": base,
        "head": head, "base_head": base_head,
        "implementation_review": "current" if review else "stale",
        "ci": "verified" if checks else "unverified",
        "release": "eligible" if release else "blocked",
        "authorization": f"auth-{number}" if authorization else None,
        "owner": owner,
    }


def chain(count=3):
    names = [chr(ord("A") + i) for i in range(count)]
    rows, base, base_head = [], "dev", "d" * 40
    for index, name in enumerate(names, 1):
        head = format(index, "040x")
        rows.append(member(index, name, base, head, base_head))
        base, base_head = name, head
    return rows


def request(rows=None, request_id="prepare-abc"):
    return {"operation": "stack_prepare", "request_id": request_id,
            "repository": "owner/repo", "target": "dev",
            "method": "merge", "members": copy.deepcopy(rows or chain())}


class StackPlanningContractTests(unittest.TestCase):
    def setUp(self):
        self.s = subject()

    def test_complete_provider_topology_freezes_base_first_order_and_heads(self):
        rows = chain()
        result = self.s.prepare_plan(request(rows), observed=copy.deepcopy(rows), revision=0)
        self.assertEqual([1, 2, 3], [row["goal"] for row in result["members"]])
        self.assertEqual([row["head"] for row in rows], [row["head"] for row in result["members"]])
        self.assertEqual("sha256:", result["plan_id"][:7])
        self.assertEqual("pending", result["members"][0]["status"])

    def test_provider_membership_not_caller_order_defines_verified_chain(self):
        rows = chain()
        shuffled = [rows[2], rows[0], rows[1]]
        plan = self.s.prepare_plan(request(shuffled), observed=rows, revision=0)
        self.assertEqual([1, 2, 3], [row["goal"] for row in plan["members"]])

    def test_incomplete_duplicate_foreign_branch_and_cycle_reject_before_effect(self):
        rows = chain()
        cases = {
            "omitted middle": ([rows[0], rows[2]], rows),
            "duplicate": ([rows[0], rows[0], rows[1], rows[2]], rows),
            "unexpected descendant": (rows, rows + [member(4, "D", "C", "4" * 40, rows[2]["head"])]),
            "cycle": ([{**rows[0], "base": "C"}, rows[1], rows[2]],
                      [{**rows[0], "base": "C"}, rows[1], rows[2]]),
            "wrong repository": ([{**rows[0], "repository": "other/repo"}, *rows[1:]], rows),
        }
        for label, (submitted, observed) in cases.items():
            with self.subTest(label=label), self.assertRaisesRegex(ValueError,
                    r"(?i)complete|duplicate|member|cycle|repository|topology|linear"):
                self.s.prepare_plan(request(submitted), observed=observed, revision=0)

    def test_middle_member_review_ci_release_and_live_owner_block_entire_preflight(self):
        for field, value in (("implementation_review", "stale"), ("ci", "unverified"),
                             ("release", "blocked"), ("owner", "live-worker")):
            rows = chain(); rows[1][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError,
                    r"(?i)review|CI|check|release|owner|lease|member"):
                self.s.prepare_plan(request(rows), observed=rows, revision=0)

    def test_large_and_partial_membership_is_paged_without_effect_or_total_ceiling(self):
        rows = chain(51)
        first = self.s.prepare_plan(request(rows), observed=rows[:50], revision=0,
                                    page={"complete": False, "cursor": "page-2"})
        self.assertEqual("collecting_membership", first["state"])
        self.assertEqual(50, len(first["members"]))
        self.assertEqual("page-2", first["continuation"])
        complete = self.s.prepare_plan(request(rows), observed=rows, revision=0,
                                       page={"complete": True, "cursor": None})
        self.assertEqual(51, complete["member_count"])

    def test_same_request_replays_exactly_and_payload_conflict_or_stale_revision_rejects(self):
        rows = chain(); proposal = request(rows, "stable-request")
        first = self.s.prepare_plan(proposal, observed=rows, revision=3)
        replay = self.s.prepare_plan(proposal, observed=rows, revision=3, existing=first)
        self.assertEqual(first, replay)
        changed = copy.deepcopy(proposal); changed["method"] = "rebase"
        with self.assertRaisesRegex(ValueError, r"(?i)request|payload|conflict"):
            self.s.prepare_plan(changed, observed=rows, revision=3, existing=first)
        with self.assertRaisesRegex(ValueError, r"(?i)revision|stale"):
            self.s.prepare_plan(proposal, observed=rows, revision=2, existing={**first, "revision": 3})


class StackAdvanceContractTests(unittest.TestCase):
    def setUp(self):
        self.s = subject(); self.rows = chain()
        self.plan = self.s.prepare_plan(request(self.rows), observed=self.rows, revision=0)

    def capability(self, **changes):
        value = {"installed": True, "membership_verified": True,
                 "atomic_prefix": True, "expected_head_guard": True,
                 "method": "merge", "admin_required": False}
        value.update(changes)
        return value

    def advance(self, **changes):
        facts = {"members": copy.deepcopy(self.rows), "reservation": "owned",
                 "prior_process": "stopped", "root": "current"}
        facts.update(changes)
        return self.s.advance_plan(copy.deepcopy(self.plan), facts=facts,
                                   capability=self.capability())

    def test_guarded_native_requires_all_members_simultaneously_effect_ready(self):
        result = self.advance(all_effect_ready=True)
        self.assertEqual("native", result["transport"])
        self.assertEqual([1, 2, 3], result["dispatch"]["goals"])
        self.assertEqual([row["head"] for row in self.rows], result["dispatch"]["expected_heads"])

    def test_unguarded_unavailable_or_admin_native_uses_declared_sequential_fallback(self):
        for changes in ({"installed": False}, {"expected_head_guard": False},
                        {"membership_verified": False}, {"admin_required": True}):
            with self.subTest(changes=changes):
                result = self.s.advance_plan(copy.deepcopy(self.plan),
                    facts={"members": self.rows, "reservation": "owned",
                           "prior_process": "stopped", "root": "current"},
                    capability=self.capability(**changes))
                self.assertEqual("sequential", result["transport"])
                self.assertEqual(1, result["dispatch"]["goal"])
                self.assertEqual("merge", result["dispatch"]["method"])
                self.assertNotIn("--admin", result["dispatch"].get("command", []))

    def test_sequential_admin_effect_requires_exact_scoped_authorization(self):
        with self.assertRaisesRegex(ValueError, r"(?i)admin|authorization|scope"):
            self.advance(repository_requires_admin=True, admin_authorization=None)
        result = self.advance(repository_requires_admin=True,
                              admin_authorization={"repository": "owner/repo", "pr": 1,
                                                   "expected_head": self.rows[0]["head"]})
        self.assertIn("--admin", result["dispatch"]["command"])

    def test_dependency_chain_pauses_after_a_for_reconciliation_and_fresh_b_authority(self):
        first = self.advance(all_effect_ready=False)
        observed = self.s.observe_attempt(first, provider={"1": "merged"})
        self.assertEqual("reconcile", observed["next_action"])
        reconciled = self.s.reconcile_plan(observed, goal=1, semantic_complete=False)
        self.assertEqual("await_phase_evidence", reconciled["next_action"])
        self.assertEqual("pending", reconciled["members"][1]["status"])
        self.assertNotIn("dispatch", reconciled)

    def test_external_merge_is_observed_and_never_dispatched_again(self):
        observed = self.s.observe_attempt(copy.deepcopy(self.plan), provider={"1": "merged"})
        self.assertEqual("observed", observed["members"][0]["status"])
        next_plan = self.s.advance_plan(observed,
            facts={"members": self.rows, "reservation": "owned",
                   "prior_process": "stopped", "root": "current"},
            capability=self.capability())
        self.assertNotEqual(1, next_plan.get("dispatch", {}).get("goal"))

    def test_uncertain_or_queued_dispatch_only_observes_until_definitive_provider_state(self):
        for outcome in ("timeout", "unknown", "queued"):
            with self.subTest(outcome=outcome):
                attempted = self.advance(provider_outcome=outcome)
                self.assertEqual("observe", attempted["next_action"])
                self.assertNotIn("retry", attempted)

    def test_reconciliation_failure_prevents_next_effect(self):
        observed = self.s.observe_attempt(self.advance(), provider={"1": "merged"})
        failed = self.s.reconcile_plan(observed, goal=1, error="storage unavailable")
        self.assertEqual("retry_reconciliation", failed["next_action"])
        self.assertNotIn("dispatch", failed)

    def test_changed_head_base_review_ci_release_or_root_blocks_remaining_effects(self):
        cases = {
            "head": [{**self.rows[0], "head": "f" * 40}, *self.rows[1:]],
            "base": [{**self.rows[0], "base_head": "f" * 40}, *self.rows[1:]],
            "review": [{**self.rows[0], "implementation_review": "stale"}, *self.rows[1:]],
            "ci": [{**self.rows[0], "ci": "unverified"}, *self.rows[1:]],
            "release": [{**self.rows[0], "release": "blocked"}, *self.rows[1:]],
        }
        for label, rows in cases.items():
            with self.subTest(label=label), self.assertRaisesRegex(ValueError,
                    r"(?i)head|base|review|CI|release|stale|changed"):
                self.advance(members=rows)
        with self.assertRaisesRegex(ValueError, r"(?i)root|authorization|current"):
            self.advance(root="replacement")

    def test_repository_reservation_and_live_expired_process_are_hard_gates(self):
        for facts in ({"reservation": "contended"},
                      {"reservation": "owned", "prior_process": "live-expired"}):
            with self.subTest(facts=facts), self.assertRaisesRegex(ValueError,
                    r"(?i)reservation|owner|process|live|stopped"):
                self.advance(**facts)

    def test_pre_dispatch_capacity_failure_writes_no_dispatch_and_post_dispatch_outage_stays_unresolved(self):
        blocked = self.advance(storage_capacity=False)
        self.assertEqual("storage_blocked", blocked["next_action"])
        self.assertNotIn("dispatch", blocked)
        uncertain = self.advance(storage_capacity=True, provider_outcome="merged",
                                 receipt_write="failed")
        self.assertEqual("observe", uncertain["next_action"])
        self.assertEqual("unresolved", uncertain["attempt"]["status"])

    def test_bounded_diagnostics_status_and_provider_limits(self):
        result = self.advance(provider_output="x" * (70 * 1024), response_bytes=1024 * 1024)
        self.assertLessEqual(len(result["attempt"]["diagnostic"]), 64 * 1024)
        self.assertTrue(result["attempt"]["diagnostic_truncated"])
        page = self.s.status_page(result, limit=50)
        self.assertLessEqual(len(page["members"]), 50)
        with self.assertRaisesRegex(ValueError, r"(?i)1 MiB|response|oversize|limit"):
            self.advance(response_bytes=1024 * 1024 + 1)
        with self.assertRaisesRegex(ValueError, r"(?i)body|budget|storage|capacity"):
            self.advance(control_body_bytes=1024 * 1024)


if __name__ == "__main__":
    unittest.main()
