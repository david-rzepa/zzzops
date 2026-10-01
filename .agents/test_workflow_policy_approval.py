"""Public policy proposal and exact-approval lifecycle regressions."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import test_zzzops as fixtures


z = fixtures.zzzops

DOCUMENTATION_SUFFIX = (
    "Follow repository documentation and style conventions. Communicate outcomes first. "
    "Include technical detail for decisions, risks, failures, or when requested. "
    "When user action is needed, give one clear action, its reason, and the next step."
)


def nested_values(value):
    """Find retained evidence without prescribing its eventual storage layout."""
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from nested_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from nested_values(child)


class WorkflowPolicyApprovalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        (self.repo / ".zzzops").mkdir()

    def plan(self):
        template = fixtures.PLUGIN_ROOT / "zzzops" / "templates" / "project-goals" / "INIT_PLAN.json"
        plan = json.loads(template.read_text(encoding="utf-8"))
        plan["base_digest"] = z.initialization_base_digest(self.repo)
        plan["repository"] = {"identity": "synthetic/project", "remote": "local"}
        plan["github"] = {"usable": True}
        backend = next(section for section in plan["policy"]["sections"] if section["id"] == "backend")
        backend["instructions"] = "Store canonical goals in GitHub Issues."
        backend["configuration"]["authority"] = "github_issues"
        backend["configuration"]["repository_identity"] = "synthetic/project"
        backend["default_disposition"] = "changed"
        return plan

    def public(self, payload):
        with (
            mock.patch.object(z._package, "package_status", return_value={"ok": True, "version": "1", "revision": "abc"}),
            mock.patch.object(z._installation, "validation_status", return_value={"required": False}),
            mock.patch.object(z, "workflow_context_step", return_value={"id": "policy-review"}),
        ):
            return z._workflow.public_run(
                z, self.repo, "inspect", "$review-zzzops-policy",
                {"root_id": "root-thread"}, payload, None,
            )

    def approve(self, proposal_result, reviewer="approved-user"):
        step = proposal_result["next_steps"][0]
        return self.public({
            "operation": "policy_approve",
            "proposal_hash": step["hash"],
            "approved_by": reviewer,
        })

    def test_exact_public_approval_applies_and_confirms_real_project_state(self):
        proposed = self.public({"operation": "policy_propose", "plan": self.plan()})
        self.assertEqual("human_approval", proposed["next_steps"][0]["kind"])

        result = self.approve(proposed)

        self.assertEqual("checkpoint", result["next_steps"][0]["kind"])
        state = z.read_project_state(self.repo)[2]
        self.assertTrue(state["initialized"])
        self.assertEqual("approved-user", state["approval"]["reviewer"])
        self.assertEqual([], z.validate_project_state(state))
        self.assertEqual([], z.validate_project_artifacts(self.repo, state))

    def test_tampered_stored_proposal_is_rejected_before_policy_write(self):
        proposed = self.public({"operation": "policy_propose", "plan": self.plan()})
        path = Path(proposed["next_steps"][0]["proposal"])
        changed = json.loads(path.read_text(encoding="utf-8"))
        changed["charter"]["outcome"] = "Changed after review"
        path.write_text(json.dumps(changed), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "changed after review"):
            self.approve(proposed)
        self.assertFalse((self.repo / ".zzzops" / "POLICY.json").exists())

    def test_invalid_proposal_preserves_existing_reviewed_policy_files(self):
        first = self.public({"operation": "policy_propose", "plan": self.plan()})
        self.approve(first, reviewer="initial-reviewer")
        paths = [
            self.repo / ".zzzops" / "PROJECT.md",
            self.repo / ".zzzops" / "PROJECT_AUDIT.md",
            self.repo / ".zzzops" / "POLICY.json",
        ]
        before = {path: path.read_bytes() for path in paths}
        invalid = copy.deepcopy(self.plan())
        invalid["charter"]["outcome"] = ""

        with self.assertRaisesRegex(ValueError, "charter.outcome is required"):
            self.public({"operation": "policy_propose", "plan": invalid})

        self.assertEqual(before, {path: path.read_bytes() for path in paths})

    def test_public_approval_repairs_legacy_invalid_routing_state(self):
        first = self.public({"operation": "policy_propose", "plan": self.plan()})
        self.approve(first, reviewer="initial-reviewer")
        policy_path = self.repo / ".zzzops" / "POLICY.json"
        legacy = json.loads(policy_path.read_text(encoding="utf-8"))
        routing = next(section for section in legacy["policy"]["sections"] if section["id"] == "model_routing")
        routing["configuration"]["model_inventory"]["reviewed_pairs"] = "legacy-invalid-value"
        policy_path.write_text(json.dumps(legacy, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        self.assertNotEqual([], z.validate_project_state(legacy))

        repaired = self.public({"operation": "policy_propose", "plan": self.plan()})
        self.approve(repaired, reviewer="repair-reviewer")

        state = z.read_project_state(self.repo)[2]
        self.assertTrue(state["initialized"])
        self.assertEqual("repair-reviewer", state["approval"]["reviewer"])
        self.assertEqual([], z.validate_project_state(state))
        self.assertEqual([], z.validate_project_artifacts(self.repo, state))

    def test_release_observations_preserve_exact_approved_policy(self):
        plan = self.plan()
        git = next(s for s in plan['policy']['sections'] if s['id'] == 'git_review_release')
        git['configuration'].pop('legacy_migration', None)
        errors = z.validate_policy(plan['policy'], require_pending=True)
        self.assertEqual([], errors, 'Standing migration rule must not require stored release facts')
        self.approve(self.public({'operation': 'policy_propose', 'plan': plan}))
        policy_file = self.repo / '.zzzops/POLICY.json'
        original = policy_file.read_bytes()
        approval = copy.deepcopy(z.read_project_state(self.repo)[2]['approval'])
        for count in (0, 1, 2):
            observed = [{'id': i + 1, 'tag_name': 'v' + str(i + 1), 'draft': False,
                         'published_at': '2026-01-01T00:00:00Z'} for i in range(count)]
            with self.subTest(releases=count), \
                 mock.patch.object(z, 'github_repository_probe', return_value={'identity': 'synthetic/project', 'visibility': 'PUBLIC'}), \
                 mock.patch.object(z, 'github_release_evidence', return_value={'available': True, 'releases': observed}), \
                 mock.patch.object(z, 'github_stack_probe', return_value={}), \
                 mock.patch.object(z, 'command_probe', return_value={'available': True}), \
                 mock.patch.object(z._plugin_freshness, 'native_plugin_inventory', return_value={'cache_path': str(self.repo / 'absent-cache')}):
                inspection = z.inspect_initialization(self.repo)
                self.assertTrue(inspection['initialized'], inspection['decision_blockers'])
                self.assertFalse(any('first_release' in str(x) for x in inspection['decision_blockers']))
                self.assertEqual(original, policy_file.read_bytes())
                self.assertEqual(approval, z.read_project_state(self.repo)[2]['approval'])

    def canonical_files(self):
        return {
            name: (self.repo / '.zzzops' / name).read_bytes()
            for name in ('POLICY.json', 'PROJECT.md', 'PROJECT_AUDIT.md')
        }

    def install_legacy_fixture(self, fixture=None):
        fixture = copy.deepcopy(fixtures.LEGACY_POLICY_UPGRADE_FIXTURE if fixture is None else fixture)
        (self.repo / '.zzzops/POLICY.json').write_text(
            json.dumps(fixture['state'], ensure_ascii=False), encoding='utf-8',
        )
        (self.repo / '.zzzops/PROJECT.md').write_text(fixture['project'], encoding='utf-8')
        (self.repo / '.zzzops/PROJECT_AUDIT.md').write_text(fixture['audit'], encoding='utf-8')
        return fixture['state']

    def mapped_legacy_plan(self, source):
        plan = self.plan()
        plan['charter'] = copy.deepcopy(source['charter'])
        plan['evidence'] = copy.deepcopy(source['policy']['evidence'])
        old = next(s for s in source['policy']['sections'] if s['id'] == 'documentation_style')
        mapped = copy.deepcopy(old)
        mapped['instructions'] = mapped.pop('decision') + '\n\n' + DOCUMENTATION_SUFFIX
        mapped.pop('settings')
        mapped.pop('default_provenance', None)
        mapped['default_id'] = 'zzzops.policy.documentation_style'
        mapped['configuration'] = {}
        mapped['review'] = {'approved': False}
        plan['policy']['sections'] = [
            mapped if s['id'] == 'documentation_style' else s
            for s in plan['policy']['sections']
        ]
        self.assertEqual([], z.validate_policy(plan['policy'], require_pending=True))
        return plan

    def test_equivalent_serialization_has_no_new_approval_and_repeat_is_idempotent(self):
        self.approve(self.public({'operation': 'policy_propose', 'plan': self.plan()}), 'original-reviewer')
        before = self.canonical_files()
        # Reverse JSON object insertion order only; list order and scalar types stay exact.
        def reordered(value):
            if isinstance(value, dict):
                return {key: reordered(value[key]) for key in reversed(value)}
            if isinstance(value, list):
                return [reordered(item) for item in value]
            return value
        for attempt in range(2):
            with self.subTest(attempt=attempt):
                result = self.public({'operation': 'policy_propose', 'plan': reordered(self.plan())})
                self.assertFalse(any(step['kind'] == 'human_approval' for step in result['next_steps']))
                self.assertEqual(before, self.canonical_files())
                self.assertEqual([], z.validate_project_state(z.read_project_state(self.repo)[2]))

    def test_cross_version_supported_section_retains_real_authority_after_reload(self):
        source = self.install_legacy_fixture()
        old = next(s for s in source['policy']['sections'] if s['id'] == 'documentation_style')
        plan = self.mapped_legacy_plan(source)
        plan['confirmed'] = True
        z.apply_plan(self.repo, plan)
        state = z.read_project_state(self.repo)[2]
        doc = next(s for s in state['policy']['sections'] if s['id'] == 'documentation_style')
        self.assertTrue(doc['review']['approved'], 'Known finite mapping must retain validated source authority')
        self.assertEqual('historical-reviewer', doc['review']['reviewer'])
        self.assertEqual('2026-08-30', doc['review']['date'])
        self.assertNotEqual(old['review']['reviewed_digest'], doc['review']['reviewed_digest'])
        values = list(nested_values(state))
        self.assertIn(old, values, 'Retain complete source section, including review and provenance')
        self.assertEqual(old['decision'] + '\n\n' + DOCUMENTATION_SUFFIX, doc['instructions'])
        self.assertEqual({}, doc['configuration'])
        for field in ('id', 'title', 'required', 'applicable', 'rationale', 'confidence',
                      'exceptions', 'unresolved', 'source_ids'):
            self.assertEqual(old[field], doc[field], field)
        self.assertIn(source['policy']['evidence'], list(nested_values(state)))
        self.assertEqual([], z.validate_project_state(state))
        self.assertEqual([], z.validate_project_artifacts(self.repo, state))
        self.assertFalse(state['initialized'], 'Other v1/v2 sections still need exact human approval')
        for section in state['policy']['sections']:
            if section['id'] != 'documentation_style':
                self.assertFalse(section['review']['approved'], section['id'])
        with self.assertRaises(ValueError):
            z.reviewed_project_state(self.repo)

    def test_public_mixed_upgrade_does_not_reapprove_equivalent_documentation(self):
        source = self.install_legacy_fixture()
        before = self.canonical_files()
        proposed = self.public({'operation': 'policy_propose', 'plan': self.mapped_legacy_plan(source)})
        self.assertEqual('human_approval', proposed['next_steps'][0]['kind'])
        self.assertNotIn('Policy Format', json.dumps(proposed))
        self.assertEqual(before, self.canonical_files(), 'Proposal alone cannot adopt mixed policy')
        self.approve(proposed, 'substantive-change-reviewer')
        state = z.read_project_state(self.repo)[2]
        doc = next(s for s in state['policy']['sections'] if s['id'] == 'documentation_style')
        self.assertEqual('historical-reviewer', doc['review']['reviewer'])
        self.assertEqual('2026-08-30', doc['review']['date'])
        self.assertTrue(state['initialized'])
        self.assertEqual([], z.validate_project_state(state))
        self.assertEqual([], z.validate_project_artifacts(self.repo, state))

    def test_repeating_public_upgrade_after_exact_mixed_approval_preserves_lineage(self):
        source = self.install_legacy_fixture()
        plan = self.mapped_legacy_plan(source)
        self.approve(self.public({'operation': 'policy_propose', 'plan': plan}), 'mixed-reviewer')
        before = self.canonical_files()
        prior = z.read_project_state(self.repo)[2]
        prior_doc = next(s for s in prior['policy']['sections'] if s['id'] == 'documentation_style')
        self.assertEqual('historical-reviewer', prior_doc['review']['reviewer'])
        self.assertIn('migration_lineage', prior_doc)
        plan['base_digest'] = z.initialization_base_digest(self.repo)
        result = self.public({'operation': 'policy_propose', 'plan': plan})
        self.assertFalse(any(step['kind'] == 'human_approval' for step in result['next_steps']))
        self.assertEqual(before, self.canonical_files())
        state = z.read_project_state(self.repo)[2]
        doc = next(s for s in state['policy']['sections'] if s['id'] == 'documentation_style')
        for field in ('review', 'migration_lineage', 'default_provenance'):
            self.assertEqual(prior_doc[field], doc[field], field)
        self.assertEqual([], z.validate_project_state(state))
        self.assertEqual([], z.validate_project_artifacts(self.repo, state))

    def test_cited_evidence_change_after_legacy_upgrade_accepts_fresh_exact_review(self):
        source = self.install_legacy_fixture()
        plan = self.mapped_legacy_plan(source)
        self.approve(self.public({'operation': 'policy_propose', 'plan': plan}), 'mixed-reviewer')
        prior = z.read_project_state(self.repo)[2]
        prior_doc = next(s for s in prior['policy']['sections'] if s['id'] == 'documentation_style')
        self.assertEqual('historical-reviewer', prior_doc['review']['reviewer'])
        self.assertIn('migration_lineage', prior_doc)
        plan['base_digest'] = z.initialization_base_digest(self.repo)
        evidence = next(item for item in plan['evidence'] if item['id'] == 'E-002')
        self.assertIn(evidence['id'], prior_doc['source_ids'])
        evidence['finding'] = 'New reviewed evidence about documentation conventions.'
        before = self.canonical_files()

        proposed = self.public({'operation': 'policy_propose', 'plan': plan})
        step = proposed['next_steps'][0]
        self.assertEqual('human_approval', step['kind'])
        decision = next(item for item in step['classification']['sections']
                        if item['section_id'] == 'documentation_style')
        self.assertFalse(decision['authority_retained'])
        self.assertNotEqual('representation_only', decision['classification'])
        self.assertEqual(before, self.canonical_files(), 'Changed evidence needs explicit exact approval')

        result = self.approve(proposed, 'fresh-evidence-reviewer')

        self.assertEqual('checkpoint', result['next_steps'][0]['kind'])
        state = z.read_project_state(self.repo)[2]
        doc = next(s for s in state['policy']['sections'] if s['id'] == 'documentation_style')
        self.assertTrue(state['initialized'])
        self.assertTrue(doc['review']['approved'])
        self.assertEqual('fresh-evidence-reviewer', doc['review']['reviewer'])
        self.assertNotEqual(prior_doc['review']['reviewed_digest'], doc['review']['reviewed_digest'])
        self.assertEqual(plan['evidence'], state['policy']['evidence'])
        self.assertEqual(prior_doc['instructions'], doc['instructions'])
        self.assertEqual(prior_doc['configuration'], doc['configuration'])
        self.assertEqual([], z.validate_project_state(state))
        self.assertEqual([], z.validate_project_artifacts(self.repo, state))
        self.assertEqual(state, z.reviewed_project_state(self.repo))

    def test_changed_target_or_retained_source_invalidates_derived_authority(self):
        for changed in ('target', 'source'):
            with self.subTest(changed=changed):
                source = self.install_legacy_fixture()
                old = next(s for s in source['policy']['sections'] if s['id'] == 'documentation_style')
                plan = self.mapped_legacy_plan(source)
                plan['confirmed'] = True
                z.apply_plan(self.repo, plan)
                state = z.read_project_state(self.repo)[2]
                doc = next(s for s in state['policy']['sections'] if s['id'] == 'documentation_style')
                self.assertTrue(doc['review']['approved'], 'First establish an actual derived approval')
                if changed == 'target':
                    doc['instructions'] += ' Grant extra authority.'
                else:
                    retained = [value for value in nested_values(state) if value == old]
                    self.assertTrue(retained, 'Source evidence must survive canonical reload')
                    retained[0]['decision'] += ' Grant extra authority.'
                self.assertNotEqual([], z.validate_project_state(state), 'Changed proof must invalidate derived review')

    def test_source_approval_and_artifact_tampering_never_silently_transfer_authority(self):
        for changed in ('approval_digest', 'source_evidence', 'artifact'):
            with self.subTest(changed=changed):
                source = self.install_legacy_fixture()
                if changed == 'approval_digest':
                    source['approval']['digest'] = 'sha256:' + '0' * 64
                elif changed == 'source_evidence':
                    source['policy']['evidence'][0]['finding'] += ' tampered'
                else:
                    (self.repo / '.zzzops/PROJECT.md').write_text('Unreviewed replacement', encoding='utf-8')
                (self.repo / '.zzzops/POLICY.json').write_text(json.dumps(source), encoding='utf-8')
                plan = self.mapped_legacy_plan(source)
                plan['confirmed'] = True
                before = self.canonical_files()
                try:
                    z.apply_plan(self.repo, plan)
                except ValueError:
                    self.assertEqual(before, self.canonical_files())
                else:
                    state = z.read_project_state(self.repo)[2]
                    doc = next(s for s in state['policy']['sections'] if s['id'] == 'documentation_style')
                    self.assertFalse(doc['review']['approved'])
                    self.assertFalse(state['initialized'])

    def test_boolean_is_not_an_equivalent_integer_configuration(self):
        original = self.plan()
        section = next(s for s in original['policy']['sections'] if s['id'] == 'autonomy_approval_parallelism')
        section['configuration']['max_workers'] = 1
        section['default_disposition'] = 'changed'
        self.approve(self.public({'operation': 'policy_propose', 'plan': original}))
        before = self.canonical_files()
        plan = self.plan()
        section = next(s for s in plan['policy']['sections'] if s['id'] == 'autonomy_approval_parallelism')
        section['configuration']['max_workers'] = True
        section['default_disposition'] = 'changed'
        with self.assertRaises(ValueError):
            self.public({'operation': 'policy_propose', 'plan': plan})
        self.assertEqual(before, self.canonical_files())

    def test_unreviewed_legacy_source_mutations_do_not_transfer_authority(self):
        cases = {
            'changed_legacy_setting': lambda old, target: old['settings'].update(documentation='ignore_repository'),
            'extra_legacy_setting': lambda old, target: old['settings'].update(custom_constraint='Keep every example'),
            'unknown_metadata': lambda old, target: old.update(custom_constraint='Ask before publishing'),
            'unknown_source_schema': lambda old, target: None,
        }
        for name, mutate in cases.items():
            with self.subTest(case=name):
                source = self.install_legacy_fixture()
                plan = self.mapped_legacy_plan(source)
                old = next(s for s in source['policy']['sections'] if s['id'] == 'documentation_style')
                target = next(s for s in plan['policy']['sections'] if s['id'] == 'documentation_style')
                mutate(old, target)
                if name == 'unknown_source_schema':
                    source['policy']['schema_version'] = 999
                (self.repo / '.zzzops/POLICY.json').write_text(json.dumps(source), encoding='utf-8')
                plan['base_digest'] = z.initialization_base_digest(self.repo)
                plan['confirmed'] = True
                before = self.canonical_files()
                try:
                    z.apply_plan(self.repo, plan)
                except ValueError:
                    self.assertEqual(before, self.canonical_files())
                else:
                    state = z.read_project_state(self.repo)[2]
                    doc = next(s for s in state['policy']['sections'] if s['id'] == 'documentation_style')
                    self.assertFalse(doc['review']['approved'])
                    self.assertFalse(state['initialized'])

    def test_valid_reviewed_unsupported_source_settings_cannot_be_dropped(self):
        # Digests pin complete persisted states accepted by the released v2.1.0
        # validator after real apply_plan/confirm_project approval, not resealed
        # mutations of an old approval or fixture-only pending snapshots.
        expected = {
            'changed_setting': 'sha256:8342e974b6ff8bd2f58da357a9bf760fd521d8203b65868df312c5c0fcdec7d4',
            'extra_setting': 'sha256:f5a9d6fb72588214315432c109850bd7016aadfd23c89b2d0eb54d6f25c64758',
        }
        for name, approved_digest in expected.items():
            with self.subTest(source=name):
                source = self.install_legacy_fixture(fixtures.legacy_reviewed_settings_fixture(name))
                self.assertTrue(source['initialized'])
                self.assertEqual(1, source['policy']['schema_version'])
                self.assertEqual(approved_digest, source['approval']['digest'])
                self.assertEqual(approved_digest, z.policy_review_digest(source))
                self.assertEqual([], z.validate_project_artifacts(self.repo, source))
                old = next(s for s in source['policy']['sections'] if s['id'] == 'documentation_style')
                self.assertTrue(old['review']['approved'])
                self.assertEqual('historical-custom-settings-reviewer', old['review']['reviewer'])
                if name == 'changed_setting':
                    self.assertEqual('always_include_full_reasoning', old['settings']['communication']['technical_detail'])
                else:
                    self.assertEqual('Keep every CLI example verbatim.', old['settings']['custom_constraint'])
                plan = self.mapped_legacy_plan(source)
                # The standard suffix omits the reviewed custom setting. Every
                # other document metadata field still matches the trusted source.
                before = self.canonical_files()
                proposed = self.public({'operation': 'policy_propose', 'plan': plan})
                self.assertEqual('human_approval', proposed['next_steps'][0]['kind'])
                self.assertEqual(before, self.canonical_files())
                plan['confirmed'] = True
                try:
                    z.apply_plan(self.repo, plan)
                except ValueError:
                    self.assertEqual(before, self.canonical_files())
                else:
                    state = z.read_project_state(self.repo)[2]
                    doc = next(s for s in state['policy']['sections'] if s['id'] == 'documentation_style')
                    self.assertFalse(doc['review']['approved'], 'Unsupported reviewed settings cannot be silently discarded')
                    self.assertFalse(state['initialized'])
                    with self.assertRaises(ValueError):
                        z.reviewed_project_state(self.repo)

    def test_changed_instructions_configuration_and_defaults_require_exact_approval(self):
        self.approve(self.public({'operation': 'policy_propose', 'plan': self.plan()}), 'original-reviewer')
        before = self.canonical_files()
        for case in ('instructions', 'configuration', 'list_order', 'default'):
            with self.subTest(case=case):
                plan = self.plan()
                section = next(s for s in plan['policy']['sections'] if s['id'] == 'autonomy_approval_parallelism')
                section['default_disposition'] = 'changed'
                if case == 'instructions':
                    section['instructions'] += ' Ask before every write.'
                elif case == 'configuration':
                    section['configuration']['max_workers'] += 1
                elif case == 'list_order':
                    section['configuration']['refill']['allowed_categories'].reverse()
                else:
                    section = next(s for s in plan['policy']['sections'] if s['id'] == 'documentation_style')
                    section['instructions'] = 'A newly shipped default is not the old reviewed choice.'
                    section['default_disposition'] = 'changed'
                result = self.public({'operation': 'policy_propose', 'plan': plan})
                self.assertEqual('human_approval', result['next_steps'][0]['kind'])
                self.assertEqual(before, self.canonical_files())

    def test_target_metadata_and_unsupported_configuration_cannot_inherit_source_authority(self):
        cases = {
            'custom_prefix_changed': lambda target: target.update(instructions=target['instructions'].replace('British', 'American')),
            'custom_prefix_trimmed': lambda target: target.update(instructions=target['instructions'].replace('\n\n', '\n', 1)),
            'new_instruction': lambda target: target.update(instructions=target['instructions'] + ' Publish automatically.'),
            'title': lambda target: target.update(title='Changed reviewed meaning'),
            'rationale': lambda target: target.update(rationale='A different justification'),
            'source_ids': lambda target: target.update(source_ids=['E-001']),
            'required': lambda target: target.update(required=False),
            'extra_configuration': lambda target: target['configuration'].update(publish_automatically=True),
            'legacy_settings_in_target': lambda target: target.update(settings={'documentation': 'repository_conventions'}),
        }
        for name, mutate in cases.items():
            with self.subTest(case=name):
                source = self.install_legacy_fixture()
                plan = self.mapped_legacy_plan(source)
                target = next(s for s in plan['policy']['sections'] if s['id'] == 'documentation_style')
                mutate(target)
                plan['confirmed'] = True
                # The canonical source remains exactly the authentic reviewed fixture.
                before = self.canonical_files()
                try:
                    z.apply_plan(self.repo, plan)
                except ValueError:
                    self.assertEqual(before, self.canonical_files())
                else:
                    state = z.read_project_state(self.repo)[2]
                    doc = next(s for s in state['policy']['sections'] if s['id'] == 'documentation_style')
                    self.assertFalse(doc['review']['approved'])
                    self.assertFalse(state['initialized'])

    def test_stale_baseline_approval_preserves_newer_reviewed_policy(self):
        self.approve(self.public({'operation': 'policy_propose', 'plan': self.plan()}))
        older = self.plan()
        older['charter']['outcome'] = 'Old proposed charter'
        old_proposal = self.public({'operation': 'policy_propose', 'plan': older})
        newer = self.plan()
        newer['charter']['outcome'] = 'Newer reviewed charter'
        self.approve(self.public({'operation': 'policy_propose', 'plan': newer}), 'newer-reviewer')
        before = self.canonical_files()
        with self.assertRaises(ValueError):
            self.approve(old_proposal, 'stale-reviewer')
        self.assertEqual(before, self.canonical_files())


if __name__ == "__main__":
    unittest.main()
