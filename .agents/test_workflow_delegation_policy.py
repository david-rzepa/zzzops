"""Reviewed delegation upgrades through the public generic DAG CLI."""
import copy
import json
from pathlib import Path

from test_evidence_dag_journeys import DagFixture, z


class DelegationUpgradePolicyTests(DagFixture):
    def configure(self, permission=True, *, role="worker", capability="bounded"):
        config = z._workflow_section(self.session.project, "model_routing")["configuration"]
        if permission is None:
            config.pop("allow_above_root_delegation", None)
        else:
            config["allow_above_root_delegation"] = permission
        self.session.runtime["root_pair"] = {"model": "worker-routine", "effort": "low"}
        graph = copy.deepcopy(self.graph)
        graph["nodes"][0]["executor"].update(role=role, capability=capability)
        self.install(graph)
        return config

    def snapshot(self):
        return copy.deepcopy((self.provider.issues, self.provider.comments))

    def ready_step(self):
        steps = self.session.ready()
        self.assertEqual(1, len(steps), "Expected one policy-authorized executable task")
        return steps[0]

    def start_request(self, step):
        receipt = json.loads(Path(step["policy"]["path"]).read_text())["policy_receipt"]
        return {**step["start"], "policy_receipt": receipt}

    def assert_blocked_without_writes(self):
        before = self.snapshot()
        response = self.session.call(100, expected=None)
        self.assertFalse(any(s.get("kind") == "execute" for s in response.get("next_steps", [])), response)
        self.assertEqual(before, self.snapshot())
        self.assertRegex(json.dumps(response), "(?i)capability|model|delegat|policy")

    def test_allowed_upgrade_survives_public_start_bind_and_submit(self):
        self.configure()
        root = copy.deepcopy(self.session.runtime["root_pair"])
        selected = {"model": "worker-bounded", "effort": "medium"}
        step = self.ready_step()
        self.assertEqual(("delegate", selected), (step["assignment"], step["selection"]))
        work = self.session.acquire("produce", actor="stronger-worker")
        self.assertEqual(selected, work["lease"]["selection"])
        self.session.finish(work, {"value": "Stronger delegated reasoning"})
        _, result = self.result("produce")
        self.assertEqual("stronger-worker", result["executor"])
        self.assertEqual(work["lease"]["attempt"], result["attempt"])
        self.assertEqual(root, self.session.runtime["root_pair"])

    def test_denied_and_legacy_missing_permission_block_without_writes(self):
        for permission in (False, None):
            with self.subTest(permission=permission):
                self.configure(permission)
                self.assert_blocked_without_writes()

    def test_denied_policy_excludes_cheaper_stronger_pair_for_routine_task(self):
        config = self.configure(False, capability="routine")
        stronger = next(p for p in config["model_inventory"]["reviewed_pairs"] if p["tier"] == "bounded")
        stronger["cost"] = 0
        step = self.ready_step()
        self.assertEqual(self.session.runtime["root_pair"], step["selection"])
        self.assertEqual("delegate", step["assignment"])

    def test_same_model_higher_effort_obeys_permission(self):
        config = self.configure()
        config["model_inventory"]["reviewed_pairs"] = [
            {"model": "one-model", "effort": "low", "tier": "routine", "cost": 1},
            {"model": "one-model", "effort": "high", "tier": "bounded", "cost": 2},
        ]
        low = {"model": "one-model", "effort": "low"}
        high = {"model": "one-model", "effort": "high"}
        self.session.runtime.update(root_pair=low, available_pairs=[low, high])
        self.assertEqual(high, self.ready_step()["selection"])
        config["allow_above_root_delegation"] = False
        self.assert_blocked_without_writes()

    def test_root_role_does_not_gain_delegation_authority(self):
        self.configure(role="root")
        self.assert_blocked_without_writes()

    def test_unavailable_unreviewed_and_undiscovered_workers_remain_blocked(self):
        self.configure()
        original = copy.deepcopy(self.session.runtime)
        scenarios = [
            {"available_pairs": [original["root_pair"]]},
            {"available_pairs": [original["root_pair"], {"model": "unreviewed", "effort": "high"}]},
            {"delegation": {"available": True, "tool": "spawn_agent", "discovery_complete": False}},
            {"delegation": {"available": False, "tool": "spawn_agent", "discovery_complete": True}},
        ]
        for change in scenarios:
            with self.subTest(change=change):
                self.session.runtime = {**copy.deepcopy(original), **change}
                self.assert_blocked_without_writes()

    def test_policy_revocation_between_preview_and_start_prevents_lease(self):
        config = self.configure()
        request = self.start_request(self.ready_step())
        config["allow_above_root_delegation"] = False
        before = self.snapshot()
        response = self.session.call(100, request, expected=None)
        self.assertNotEqual(0, self.session.calls[-1]["code"], response)
        self.assertEqual(before, self.snapshot())

    def test_binding_requires_selected_pair_after_allowed_upgrade(self):
        self.configure()
        step = self.ready_step()
        request = self.start_request(step)
        work = self.session.call(100, request)["next_steps"][0]
        bind = {**work["bind"], "actor": "stronger-worker", "policy_receipt": request["policy_receipt"]}
        bind["selection"] = copy.deepcopy(self.session.runtime["root_pair"])
        before = self.snapshot()
        response = self.session.call(100, bind, expected=None)
        self.assertNotEqual(0, self.session.calls[-1]["code"], response)
        self.assertEqual(before, self.snapshot())
        bind["selection"] = work["lease"]["selection"]
        self.session.call(100, bind)
        work["bound_actor"] = "stronger-worker"
        self.session.finish(work, {"value": "Actual selected pair bound"})
