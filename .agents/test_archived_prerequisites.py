"""Archived prerequisites need a reviewable candidate, never implicit authority."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest


MODULE = Path(__file__).parents[1] / 'plugins/zzzops/zzzops/archived_prerequisites.py'
SPEC = importlib.util.spec_from_file_location('archived_prerequisites_test_subject', MODULE)
archived = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(archived)


class ArchivedPrerequisiteTests(unittest.TestCase):
    def candidate_inputs(self, repository='owner/repo', goal=100):
        source = {'type': 'migration_source', 'content': {'number': goal,
                  'body': 'Old goal\n<!-- zzzops-goal\n{}\nzzzops-goal -->\n'},
                  'producer': None, 'provenance': {'actor': 'manual-schema-reconciliation-522',
                                                  'source': None, 'policy': 'sha256:' + 'd' * 64}}
        policy = {'sections': []}
        source_bytes = json.dumps(source, sort_keys=True).encode()
        policy_bytes = json.dumps(policy, sort_keys=True).encode()
        source_ref = {'hash': 'sha256:' + hashlib.sha256(source_bytes).hexdigest(),
                      'uri': 'git:' + 'a' * 40 + ':.zzzops/migration/100-source.json'}
        policy_ref = {'hash': 'sha256:' + hashlib.sha256(policy_bytes).hexdigest(),
                      'uri': 'git:' + 'a' * 40 + ':.zzzops/migration/policy.json'}
        def ref(value):
            h = archived.digest(value)
            return {'hash': h, 'uri': f'zzzops:{repository}:goal:{goal}:{h}'}
        target_payload = {'spec': source_ref, 'graph': policy_ref, 'evidence': [],
                          'operational': {'leases': [], 'receipts': []}}
        target_intent = {'schema_version': 2, 'repository': repository, 'issue': goal,
                         'state': 'open', 'revision': 9, 'parent': None,
                         'payload': ref(target_payload)}
        receipt = {'type': 'schema_migration', 'converter': 'manual-reconciliation-522/1',
                   'repository': repository, 'goal': goal,
                   'source': source_ref, 'policy': policy_ref,
                   'target_intent': ref(target_intent),
                   'target_payload': ref(target_payload),
                   'reason': 'Preserve historical source without inherited authority',
                   'missing_obligations': ['Normal phase evidence remains required']}
        migration_response = {'next_steps': [{'kind': 'schema_migration', 'goal': goal,
            'status': 'migrated', 'receipt': ref(receipt)}]}
        archived_payload = copy.deepcopy(target_payload)
        archived_payload['operational']['receipts'].append({
            'request': 'manual-migrate-' + archived.digest({'goal': goal})[7:],
            'payload': 'sha256:' + 'f' * 64,
            'result': ref(migration_response)})
        envelope = {'schema_version': 2, 'repository': repository, 'issue': goal,
                    'state': 'archived', 'revision': 10, 'parent': None,
                    'payload': ref(archived_payload)}
        issue = {'number': goal, 'state': 'closed', 'closed_at': '2026-10-01T00:00:00Z',
                 'labels': [{'name': 'zzzops:status:done'}],
                 'body': 'Reviewed work in PR #7 is archived.\n<!-- zzzops-goal\n'
                         + json.dumps(envelope) + '\nzzzops-goal -->'}
        pull = {'number': 7, 'baseRepository': repository, 'state': 'MERGED', 'baseRefName': 'dev',
                'mergedAt': '2026-10-01T00:01:00Z', 'headRefOid': 'c' * 40,
                'mergeCommit': {'oid': 'e' * 40}, 'body': f'Refs #{goal}.'}
        return {'repository': repository, 'goal': goal, 'integration_branch': 'dev',
                'issue': issue, 'envelope': envelope, 'archived_payload': archived_payload,
                'receipt': receipt, 'migration_response': migration_response,
                'target_intent': target_intent, 'target_payload': target_payload,
                'source_bytes': source_bytes, 'policy_bytes': policy_bytes, 'pull_number': 7,
                'pull': pull, 'merge_reachable': True}

    def test_exact_archive_and_merge_form_review_candidate_without_grant(self):
        inputs = self.candidate_inputs()
        candidate = archived.candidate(**inputs)
        self.assertEqual('archived_prerequisite_candidate', candidate['kind'])
        self.assertTrue(candidate['requires_independent_review'])
        self.assertNotIn('approved', candidate)
        self.assertEqual('e' * 40, candidate['observation']['merge_commit'])
        self.assertEqual(candidate, archived.candidate(**inputs))
        changed = copy.deepcopy(inputs)
        changed['pull']['body'] += ' Additional linked context.'
        self.assertNotEqual(candidate['identity'], archived.candidate(**changed)['identity'])
        changed = copy.deepcopy(inputs)
        changed['issue']['body'] += '\nAdditional linked context.'
        self.assertNotEqual(candidate['identity'], archived.candidate(**changed)['identity'])

    def test_closed_label_or_unrelated_merge_cannot_form_candidate(self):
        original = self.candidate_inputs()
        cases = [
            lambda data: data['pull'].update(body='Refs #101.'),
            lambda data: data.update(merge_reachable=False),
            lambda data: data['issue'].update(state='open'),
            lambda data: data['issue']['labels'].append({'name': 'zzzops:status:cancelled'}),
            lambda data: data['envelope'].update(repository='foreign/repo'),
            lambda data: data.update(source_bytes=data['source_bytes'] + b' '),
            lambda data: data['pull'].update(baseRefName='main'),
            lambda data: data['issue'].update(body=data['issue']['body'] + '\n'
                + data['issue']['body'][data['issue']['body'].index('<!-- zzzops-goal'):]),
            lambda data: data['issue'].update(body=data['issue']['body'].replace(
                '"issue": 100', '"issue": 100, "issue": 100')),
        ]
        for mutate in cases:
            inputs = copy.deepcopy(original)
            mutate(inputs)
            with self.subTest(inputs=inputs), self.assertRaises(archived.ArchivedPrerequisiteError):
                archived.candidate(**inputs)


if __name__ == '__main__':
    unittest.main()
