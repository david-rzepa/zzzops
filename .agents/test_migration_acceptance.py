"""Contract-bound migration decisions, using only synthetic evidence."""
import copy
import json
import unittest
from pathlib import Path

import test_zzzops as fixtures
zzzops = fixtures.zzzops


def policy():
    value = json.loads((fixtures.PLUGIN_ROOT / 'zzzops/templates/project-goals/INIT_PLAN.json').read_text())['policy']
    section = next(s for s in value['sections'] if s['id'] == 'git_review_release')
    section['configuration'].pop('legacy_migration', None)
    return value


def releases():
    return {'status': 'complete', 'releases': [
        {'id': 1, 'tag': 'v1', 'commit': 'a' * 40, 'published_at': '2026-01-01T00:00:00Z'}]}


def assessment(goal=42, spec='sha256:' + 'b' * 64, status='unreleased'):
    return {'schema_version': 1, 'repository': 'owner/repo', 'goal': goal,
            'goal_spec': spec, 'action': 'Replace the experimental synthetic cache format',
            'release_snapshot': releases(), 'contracts': [{
                'id': 'cache-v2', 'boundary': 'Only experimental project cache records',
                'status': status, 'scope': ['project-cache/v2'],
                'evidence': [{'kind': 'owner_attestation', 'author': 'synthetic-owner',
                              'statement': 'This cache format has never shipped.',
                              'goal': goal, 'goal_spec': spec,
                              'release_snapshot': releases(),
                              'contract': 'cache-v2', 'boundary': 'Only experimental project cache records',
                              'scope': ['project-cache/v2']}]}]}


def context(document=None):
    return {'status': 'released', 'repository': 'owner/repo', 'goal': 42,
            'goal_spec': 'sha256:' + 'b' * 64, 'contract_id': 'cache-v2',
            'release_snapshot': releases(),
            'assessment': assessment() if document is None else document}


class MigrationAcceptanceTests(unittest.TestCase):
    def decide(self, value):
        # Existing public helper remains the decision boundary; no evaluator fake.
        return zzzops.migration_boundary(policy(), value)

    def assert_blocked(self, value):
        result = self.decide(value)
        self.assertEqual('block', result['action'])
        self.assertEqual('none', result['scope'])

    def test_released_project_with_unreleased_contract_has_bounded_eligibility(self):
        value = context()
        before = copy.deepcopy(value)
        result = self.decide(value)
        self.assertEqual('replace_reset', result['action'])
        self.assertEqual('affected_project_owned', result['scope'])
        self.assertEqual(before, value, 'classification must not rewrite supplied facts')

    def test_shipped_contract_preserves_state_and_mixed_batch_never_resets_all(self):
        value = context()
        shipped = copy.deepcopy(value['assessment']['contracts'][0])
        shipped['id'] = 'shipped-cache'
        shipped['status'] = 'shipped'
        shipped['boundary'] = 'Released cache records'
        shipped['scope'] = ['project-cache/v1']
        shipped['evidence'][0].update(
            contract='shipped-cache', boundary='Released cache records',
            scope=['project-cache/v1'], statement='This cache format shipped in v1.')
        value['assessment']['contracts'].insert(0, shipped)
        # Both entries are valid within the same assessment, including every
        # attestation binding. A blanket malformed-document block cannot pass.
        value['contract_id'] = 'shipped-cache'
        self.assertEqual('preserve', self.decide(value)['action'])
        value['contract_id'] = 'cache-v2'
        eligible = self.decide(value)
        self.assertEqual('replace_reset', eligible['action'])
        self.assertEqual('affected_project_owned', eligible['scope'])
        value.pop('contract_id')
        batch = self.decide(value)
        self.assertEqual('preserve', batch['action'], 'Valid mixed batch must preserve its shipped member')
        self.assertNotEqual('none', batch['scope'], 'This is a valid preserve decision, not malformed rejection')
        # Inconsistent attestation is separately tested as a negative.
        value['contract_id'] = 'shipped-cache'
        value['assessment']['contracts'][0]['evidence'][0]['contract'] = 'cache-v2'
        self.assert_blocked(value)

    def test_first_and_later_release_do_not_change_standing_policy(self):
        configured = policy()
        original = copy.deepcopy(configured)
        for count in (0, 1, 2):
            value = context()
            snapshot = {'status': 'complete', 'releases': releases()['releases'] * count}
            if count == 2:
                snapshot['releases'][1] = dict(snapshot['releases'][1], id=2, tag='v2', commit='c' * 40)
            value['status'] = 'never_released' if count == 0 else 'released'
            value['release_snapshot'] = snapshot
            value['assessment']['release_snapshot'] = copy.deepcopy(snapshot)
            value['assessment']['contracts'][0]['evidence'][0]['release_snapshot'] = copy.deepcopy(snapshot)
            with self.subTest(releases=count):
                self.assertEqual('replace_reset', zzzops.migration_boundary(configured, value)['action'])
                self.assertEqual(original, configured)

    def test_foreign_goal_spec_repository_and_unknown_contract_are_rejected(self):
        self.assertEqual('replace_reset', self.decide(context())['action'])
        for field, other in [('goal', 43), ('repository', 'other/repo'), ('goal_spec', 'sha256:' + 'c' * 64)]:
            value = context(); value['assessment'][field] = other
            with self.subTest(field=field): self.assert_blocked(value)
        value = context(); value['contract_id'] = 'different-action'
        self.assert_blocked(value)
        self.assertEqual('replace_reset', self.decide(context())['action'])

    def test_unknown_missing_malformed_and_revoked_evidence_cannot_authorize_reset(self):
        self.assertEqual('replace_reset', self.decide(context())['action'])
        for document in (None, {}, assessment(status='unknown'), dict(assessment(), schema_version=999)):
            value = context(); value['assessment'] = document
            with self.subTest(document=document): self.assert_blocked(value)
        value = context(); value['assessment']['contracts'][0]['evidence'] = []
        self.assert_blocked(value)
        value = context(); value['assessment']['contracts'].append(copy.deepcopy(value['assessment']['contracts'][0]))
        self.assert_blocked(value)
        value = context(); value['assessment']['contracts'][0]['evidence'][0]['goal'] = 43
        self.assert_blocked(value)
        value = context(); value['assessment']['contracts'][0]['status'] = 'unknown'
        value['assessment']['contracts'][0]['evidence'][0]['statement'] = 'Owner withdrew the earlier attestation.'
        self.assert_blocked(value)

    def test_external_release_changes_require_contract_reassessment(self):
        self.assertEqual('replace_reset', self.decide(context())['action'])
        variants = [None, {'status': 'unavailable', 'releases': []},
                    {'status': 'complete', 'releases': []},
                    {'status': 'complete', 'releases': [dict(releases()['releases'][0], commit='d' * 40)]},
                    {'status': 'complete', 'releases': releases()['releases'] + [
                        {'id': 2, 'tag': 'v2', 'commit': 'c' * 40, 'published_at': '2026-02-01T00:00:00Z'}]}]
        for snapshot in variants:
            value = context(); value['release_snapshot'] = snapshot
            with self.subTest(snapshot=snapshot): self.assert_blocked(value)
        self.assertEqual('replace_reset', self.decide(context())['action'])

    def test_owner_statement_scope_cannot_expand_to_unrelated_state(self):
        self.assertEqual('replace_reset', self.decide(context())['action'])
        for scope in (['user-home'], ['external-account'], ['deployment-database']):
            value = context(); value['assessment']['contracts'][0]['scope'] = scope
            with self.subTest(scope=scope): self.assert_blocked(value)

    def test_representative_strict_types_fail_closed_after_valid_control(self):
        self.assertEqual('replace_reset', self.decide(context())['action'])
        mutations = [
            lambda d: d.update(schema_version=True),
            lambda d: d.update(goal='42'),
            lambda d: d.update(contracts={'cache-v2': d['contracts'][0]}),
            lambda d: d['contracts'][0].update(scope='project-cache/v2'),
            lambda d: d['contracts'][0].update(status=True),
            lambda d: d['contracts'][0].update(evidence='owner said never shipped'),
        ]
        for index, mutate in enumerate(mutations):
            value = context(); mutate(value['assessment'])
            with self.subTest(malformed=index): self.assert_blocked(value)
        self.assertEqual('replace_reset', self.decide(context())['action'])

    def test_no_goal_context_never_grants_reset(self):
        for observation in ({'status': 'released'}, {'status': 'never_released'}, {'status': 'unknown'}):
            self.assert_blocked(observation)


class AgentContractInvestigationTests(unittest.TestCase):
    """Captured agent investigation is an evidence alternative, not owner consent.

    The evaluator consumes auditable facts; it does not prove arbitrary prose or
    infer absence across every distribution channel from an empty release list.
    Synthetic immutable references model inspected contract/distribution files.
    """
    decide = MigrationAcceptanceTests.decide
    assert_blocked = MigrationAcceptanceTests.assert_blocked

    def investigated(self, released=True):
        value = context()
        snapshot = releases() if released else {'status': 'complete', 'releases': []}
        value['release_snapshot'] = copy.deepcopy(snapshot)
        document = value['assessment']
        document['release_snapshot'] = copy.deepcopy(snapshot)
        contract = document['contracts'][0]
        evidence = {
            'kind': 'contract_investigation', 'author': 'agent:test-investigator',
            'goal': document['goal'], 'goal_spec': document['goal_spec'],
            'release_snapshot': copy.deepcopy(snapshot), 'contract': contract['id'],
            'boundary': contract['boundary'], 'scope': copy.deepcopy(contract['scope']),
            'conclusion': 'unreleased',
            'rationale': ('Inspected the introduction and release trees. The cache-v2 schema is present '
                          'only in development; the distribution definition confines this synthetic '
                          'contract to packages from these releases, with no separate deployment.'),
            'distribution_boundary': 'This synthetic project distributes cache formats only in its published packages.',
            'observations': [
                {'commit': 'c' * 40, 'path': 'cache/schema-v2.json', 'contract_present': True, 'release_id': None},
                {'commit': 'c' * 40, 'path': 'distribution.json', 'finding': 'Only published packages distribute this contract.'},
            ],
        }
        if released:
            evidence['observations'].append({
                'commit': 'a' * 40, 'path': 'cache/schema-v2.json',
                'contract_present': False, 'release_id': 1})
        contract['evidence'] = [evidence]
        return value

    def test_agent_investigation_establishes_unreleased_without_owner_statement(self):
        for released in (False, True):
            with self.subTest(released= released):
                value = self.investigated(released)
                before = copy.deepcopy(value)
                result = self.decide(value)
                self.assertEqual('replace_reset', result['action'])
                self.assertEqual('affected_project_owned', result['scope'])
                self.assertEqual(before, value)
                self.assertNotIn('owner_attestation', json.dumps(value))

    def test_agent_investigation_insufficient_or_contradictory_facts_block(self):
        mutations = [
            lambda e: e.update(observations=[]),
            lambda e: e.update(rationale=''),
            lambda e: e.update(distribution_boundary=''),
            lambda e: e.update(conclusion='unknown'),
            lambda e: e.update(goal=43),
            lambda e: e.update(contract='different-contract'),
            lambda e: e.update(scope=['external-account']),
            lambda e: e['observations'][0].update(commit='main'),
            lambda e: e['observations'][0].update(path=''),
            lambda e: e['observations'].pop(),  # Published commit was not investigated.
            lambda e: e['observations'][-1].update(contract_present=True),
        ]
        self.assertEqual('replace_reset', self.decide(self.investigated())['action'])
        for index, mutate in enumerate(mutations):
            value = self.investigated()
            mutate(value['assessment']['contracts'][0]['evidence'][0])
            with self.subTest(invalid=index):
                self.assert_blocked(value)
        self.assertEqual('replace_reset', self.decide(self.investigated())['action'])

    def test_same_immutable_contract_commit_path_cannot_be_present_and_absent(self):
        value = self.investigated()
        self.assertEqual('replace_reset', self.decide(value)['action'])
        evidence = value['assessment']['contracts'][0]['evidence'][0]
        evidence['observations'][0]['commit'] = evidence['observations'][-1]['commit']
        self.assert_blocked(value)
        self.assertEqual('replace_reset', self.decide(self.investigated())['action'])

    def test_published_commit_presence_cannot_hide_behind_development_label(self):
        value = self.investigated()
        self.assertEqual('replace_reset', self.decide(value)['action'])
        evidence = value['assessment']['contracts'][0]['evidence'][0]
        evidence['observations'].append({'commit': 'a' * 40, 'path': 'cache/alternate-v2.json',
                                         'contract_present': True, 'release_id': None})
        self.assert_blocked(value)
        self.assertEqual('replace_reset', self.decide(self.investigated())['action'])

    def test_contradictory_presence_across_evidence_items_is_rejected(self):
        value = self.investigated()
        self.assertEqual('replace_reset', self.decide(value)['action'])
        evidence = value['assessment']['contracts'][0]['evidence']
        other = copy.deepcopy(evidence[0])
        # Each investigation independently has valid introduction/release
        # coverage, but they disagree about one immutable development file.
        other['observations'][0]['contract_present'] = False
        other['observations'].append({'commit': 'd' * 40, 'path': 'cache/schema-v2.json',
                                       'contract_present': True, 'release_id': None})
        evidence.append(other)
        self.assert_blocked(value)
        self.assertEqual('replace_reset', self.decide(self.investigated())['action'])

    def test_no_releases_and_bare_git_identity_do_not_establish_contract_absence(self):
        value = self.investigated(False)
        evidence = value['assessment']['contracts'][0]['evidence'][0]
        # Preserve actor and exact bindings: the missing inspected facts, not a
        # foreign identity, must make this insufficient.
        evidence['observations'] = [{'commit': 'c' * 40}]
        self.assert_blocked(value)
        self.assertEqual('replace_reset', self.decide(self.investigated(False))['action'])


class ReleaseObservationTransportTests(unittest.TestCase):
    """Raw GitHub transport only is fake; observation and tag resolution are real."""
    def setUp(self):
        import tempfile
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.raw = {'id': 7, 'tag_name': 'v1', 'target_commitish': 'main',
                    'draft': False, 'published_at': '2026-01-01T00:00:00Z'}
        self.commit = 'a' * 40
        self.tag_object = 'b' * 40
        self.calls = []
        self.failed_endpoint = None
        self.bad_commit = None
        self.pages = [[dict(self.raw, id=8, tag_name='draft', draft=True, published_at=None)], [dict(self.raw)], []]

    def transport(self, command, **kwargs):
        from types import SimpleNamespace
        # No real process or network is invoked. Accept either GitHub's commit
        # dereference endpoint or its refs+annotated-tags endpoints.
        self.calls.append(list(command))
        endpoint = next((x for x in command if isinstance(x, str) and x.startswith('repos/')), '')
        if (self.failed_endpoint == 'tag-resolution' and endpoint != 'repos/owner/repo/releases') or (
                self.failed_endpoint == '/releases' and endpoint.endswith('/releases')):
            return SimpleNamespace(returncode=1, stdout='', stderr='synthetic unavailable')
        if endpoint == 'repos/owner/repo/releases':
            self.assertIn('--paginate', command, 'A partial release page is not complete evidence')
            data = self.pages
        elif endpoint in ('repos/owner/repo/commits/v1', 'repos/owner/repo/commits/refs/tags/v1'):
            data = {'sha': self.bad_commit if self.bad_commit is not None else self.commit}
        elif endpoint in ('repos/owner/repo/git/ref/tags/v1', 'repos/owner/repo/git/refs/tags/v1'):
            data = {'ref': 'refs/tags/v1', 'object': {'type': 'tag', 'sha': self.tag_object}}
        elif endpoint == 'repos/owner/repo/git/tags/' + self.tag_object:
            data = {'object': {'type': 'commit', 'sha': self.bad_commit if self.bad_commit is not None else self.commit}}
        else:
            raise AssertionError('Unexpected transport, must resolve release tag rather than branch: ' + repr(command))
        return SimpleNamespace(returncode=0, stdout=json.dumps(data), stderr='')

    def observe(self):
        from unittest import mock
        with mock.patch.object(zzzops.shutil, 'which', return_value='synthetic-gh'), \
             mock.patch.object(zzzops.subprocess, 'run', side_effect=self.transport):
            return zzzops.github_release_evidence(self.repo, {'identity': 'owner/repo', 'visibility': 'PUBLIC'})

    def assert_complete(self, value):
        self.assertEqual('complete', value.get('status'), 'Real release observer must establish a complete normalized snapshot')
        self.assertEqual([{'id': 7, 'tag': 'v1', 'commit': self.commit,
                          'published_at': self.raw['published_at']}], value['releases'])
        self.assertTrue(any('/commits/' in str(c) or '/git/tags/' in str(c) for c in self.calls),
                        'Mutable target_commitish or an annotated tag object is not the commit identity')

    def test_real_observer_normalizes_pages_and_resolves_retargeted_tag(self):
        raw_before = copy.deepcopy(self.pages)
        first = self.observe(); self.assert_complete(first)
        self.commit = 'c' * 40
        second = self.observe(); self.assert_complete(second)
        self.assertNotEqual(first, second)
        self.assertEqual(raw_before, self.pages, 'Release metadata stayed fixed; tag target changed')

    def test_unavailable_release_or_tag_and_malformed_observation_fail_closed(self):
        valid = self.observe(); self.assert_complete(valid)
        for endpoint in ('/releases', 'tag-resolution'):
            self.failed_endpoint = endpoint
            with self.subTest(unavailable=endpoint):
                self.assertNotEqual('complete', self.observe().get('status'))
            self.failed_endpoint = None
        for pages in ([[None]], [[dict(self.raw, id=True)]], [[dict(self.raw, tag_name=42)]],
                      [[dict(self.raw, published_at=None)]], {'incomplete': True}):
            self.pages = pages
            with self.subTest(pages=pages):
                self.assertNotEqual('complete', self.observe().get('status'))
        self.pages = [[dict(self.raw)], []]
        self.bad_commit = 'main'
        self.assertNotEqual('complete', self.observe().get('status'))
        self.bad_commit = None
        self.assert_complete(self.observe())


if __name__ == '__main__':
    unittest.main()
