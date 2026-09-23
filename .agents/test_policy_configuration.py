"""Schema-v2 separation of agent instructions from typed runtime configuration."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest
from unittest import mock

import test_zzzops as fixtures


z = fixtures.zzzops


EXPECTED_CONFIGURATION_KEYS = {
    "backend": {"authority", "repository_identity", "capability_evidence"},
    "git_review_release": {
        "review_pending_dependency", "pull_request_mode", "legacy_migration",
    },
    "verification_testing": {"required_ci"},
    "code_quality": set(),
    "dependencies_tooling": set(),
    "security_privacy_compliance": set(),
    "documentation_style": set(),
    "deployment_resources": set(),
    "engineering_rigor": {"level", "minimums", "overrides"},
    "model_routing": {"tiers", "assessment_tree", "model_inventory"},
    "workflow_adherence": {"phase_dag"},
    "automated_design": set(),
    "autonomy_approval_parallelism": {
        "max_workers", "execution_reports", "resource_reservations", "refill",
    },
}


class PolicyConfigurationSchemaTests(unittest.TestCase):
    def template_policy(self):
        path = fixtures.PLUGIN_ROOT / "zzzops" / "templates" / "project-goals" / "INIT_PLAN.json"
        return json.loads(path.read_text(encoding="utf-8"))["policy"]

    def test_template_has_one_typed_configuration_authority_per_instruction_section(self):
        policy = self.template_policy()
        self.assertEqual(2, policy["schema_version"])
        sections = {section["id"]: section for section in policy["sections"]}
        self.assertEqual(set(EXPECTED_CONFIGURATION_KEYS), set(sections))
        for identifier, expected in EXPECTED_CONFIGURATION_KEYS.items():
            section = sections[identifier]
            self.assertNotIn("decision", section)
            self.assertNotIn("settings", section)
            self.assertIsInstance(section["instructions"], str)
            self.assertTrue(section["instructions"].strip())
            self.assertEqual(expected, set(section["configuration"]))
        self.assertEqual(set(), set(z.validate_policy(policy, require_pending=True)))

    def test_unknown_configuration_and_empty_instructions_are_rejected(self):
        for mutation, expected in (
            (lambda section: section["configuration"].update({"unused_switch": True}), "unsupported configuration fields"),
            (lambda section: section.update({"instructions": ""}), "instructions is required"),
            (lambda section: section.update({"settings": {}}), "unsupported fields"),
        ):
            policy = self.template_policy()
            mutation(policy["sections"][0])
            with self.subTest(expected=expected):
                self.assertTrue(any(expected in error for error in z.validate_policy(policy, require_pending=True)))

    def test_schema_v1_cannot_retain_review_or_default_provenance(self):
        policy = self.template_policy()
        policy["schema_version"] = 1
        section = policy["sections"][0]
        section["review"] = {"approved": True, "reviewer": "legacy", "date": "2026-01-01", "reviewed_digest": "sha256:" + "1" * 64}
        section["default_provenance"] = {
            "status": "adopted", "default_id": "zzzops.policy.backend", "schema_version": 1,
            "source": {"version": "1", "revision": "legacy"}, "digest": "sha256:" + "2" * 64,
            "snapshot": {"decision": "legacy", "settings": {}},
        }
        errors = z.validate_policy(policy, require_pending=False)
        self.assertTrue(any("schema_version must be 2" in error for error in errors))
        self.assertTrue(any("default_provenance.schema_version must be 2" in error for error in errors))

        proposal = self.template_policy()
        legacy = copy.deepcopy(proposal)
        legacy["schema_version"] = 1
        for legacy_section in legacy["sections"]:
            legacy_section["review"] = {
                "approved": True, "reviewer": "legacy", "date": "2026-01-01",
                "reviewed_digest": "sha256:" + "1" * 64,
            }
            legacy_section["default_provenance"] = {"status": "unknown"}
        source = {"version": "2.0.0", "revision": "a" * 40}
        with mock.patch.object(z._policy, "machinery_provenance", return_value=source):
            prepared = z.prepare_policy_defaults(Path("/synthetic/repository"), proposal, legacy)
        self.assertTrue(all(item["review"] == {"approved": False} for item in prepared["sections"]))
        self.assertTrue(all(item["default_provenance"]["schema_version"] == 2 for item in prepared["sections"]))

    def test_runtime_configuration_types_and_enums_are_strict(self):
        cases = (
            ("verification_testing", lambda value: value.update({"required_ci": "assume_green"}), "required_ci is invalid"),
            ("engineering_rigor", lambda value: value.update({"level": "maximum"}), "level is invalid"),
            ("autonomy_approval_parallelism", lambda value: value.update({"max_workers": True}), "max_workers must be an integer"),
            ("autonomy_approval_parallelism", lambda value: value["refill"].update({"max_suggestions": 0}), "max_suggestions must be a positive integer"),
        )
        for identifier, mutation, expected in cases:
            policy = self.template_policy()
            section = next(item for item in policy["sections"] if item["id"] == identifier)
            mutation(section["configuration"])
            with self.subTest(section=identifier, expected=expected):
                self.assertTrue(any(expected in error for error in z.validate_policy(policy, require_pending=True)))

    def test_security_policy_cannot_be_marked_optional_or_inapplicable(self):
        for field in ("required", "applicable"):
            policy = self.template_policy()
            section = next(item for item in policy["sections"] if item["id"] == "security_privacy_compliance")
            section[field] = False
            with self.subTest(field=field):
                self.assertTrue(any(
                    "security_privacy_compliance must be required and applicable" in error
                    for error in z.validate_policy(policy, require_pending=True)
                ))

    def test_default_and_review_hash_inputs_bind_instructions_and_configuration(self):
        policy = self.template_policy()
        section = next(item for item in policy["sections"] if item["id"] == "verification_testing")
        original = z._policy.policy_default_content(section)
        changed_instructions = copy.deepcopy(section)
        changed_instructions["instructions"] += " Additional reviewed guidance."
        changed_configuration = copy.deepcopy(section)
        changed_configuration["configuration"]["required_ci"] = "disabled"
        self.assertNotEqual(z.policy_content_digest(original), z.policy_content_digest(z._policy.policy_default_content(changed_instructions)))
        self.assertNotEqual(z.policy_content_digest(original), z.policy_content_digest(z._policy.policy_default_content(changed_configuration)))
        evidence = [{"id": "E-002", "source": "synthetic", "finding": "reviewed"}]
        self.assertNotEqual(
            z._policy.policy_section_review_content(section, evidence),
            z._policy.policy_section_review_content(changed_configuration, evidence),
        )

    def test_review_table_exposes_ci_and_worker_configuration_changes(self):
        policy = self.template_policy()
        changed = copy.deepcopy(policy)
        verification = next(item for item in changed["sections"] if item["id"] == "verification_testing")
        autonomy = next(item for item in changed["sections"] if item["id"] == "autonomy_approval_parallelism")
        verification["configuration"]["required_ci"] = "disabled"
        autonomy["configuration"]["max_workers"] = 7
        original = z._policy.render_policy_review_table(policy, proposal=True)
        rendered = z._policy.render_policy_review_table(changed, proposal=True)
        self.assertIn("required_ci=\"inspect_exact_pr_head\"", original)
        self.assertIn("required_ci=\"disabled\"", rendered)
        self.assertIn("max_workers=3", original)
        self.assertIn("max_workers=7", rendered)
        self.assertNotEqual(original, rendered)


if __name__ == "__main__":
    unittest.main()
