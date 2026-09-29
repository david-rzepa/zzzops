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




# Module-qualified fixture reuse avoids unittest discovering imported TestCases.
import test_evidence_dag_journeys as dag_fixtures
from unittest import mock
import sys


class GenericMigrationInputTests(dag_fixtures.DagFixture):
    """Existing migration adapter with explicitly consumed goal-bound evidence.

    The repository_workspace allocation declares the exact migration path.
    No node name or old phase assessment chooses scope. In the v2 adapter the
    document's goal_spec binds Payload.spec.hash (a required v2 adapter change,
    not a monkeypatch of migration_assessment); its remaining closed v1
    assessment schema is retained as provider evidence, not an active goal schema.
    Provider observations are refreshed once per projection, shared among its
    affected consumers, and never confer write/migration authority by themselves.
    """
    workspace_graph = dag_fixtures.WorkspaceAuthorityPublicTests.workspace_graph
    setup_workspace = dag_fixtures.WorkspaceAuthorityPublicTests.setup_workspace
    acquire_workspace = dag_fixtures.WorkspaceAuthorityPublicTests.acquire_workspace
    review_candidate = dag_fixtures.WorkspaceAuthorityPublicTests.review_candidate

    def setUp(self):
        super().setUp()
        self.setup_migration()

    def setup_migration(self, mutate=None):
        self.observation = releases()
        release_patch = mock.patch.object(zzzops, 'github_release_evidence',
            side_effect=lambda *a, **k: copy.deepcopy(self.observation))
        self.release_probe = release_patch.start()
        self.addCleanup(release_patch.stop)
        repository_patch = mock.patch.object(zzzops, 'github_repository_probe',
                          return_value={'identity': 'owner/repo', 'visibility': 'PUBLIC'})
        repository_patch.start()
        self.addCleanup(repository_patch.stop)
        self.path = self.fixture.repo / '.zzzops/migration/100.json'
        self.relative = '.zzzops/migration/100.json'
        def consumed(graph, allocation):
            allocation['allocations']['alpha']['owned'] = []
            allocation['allocations']['alpha']['consumed'].append(self.relative)
            spectator = dag_fixtures.task('spectator')
            graph['nodes'].append(spectator)
            alpha = next(node for node in graph['nodes'] if node['id'] == 'alpha')
            mirror = copy.deepcopy(alpha)
            mirror['id'] = 'mirror'
            mirror['inputs']['allocation']['path'][-1] = 'mirror'
            graph['nodes'].append(mirror)
            allocation['allocations']['mirror'] = copy.deepcopy(allocation['allocations']['alpha'])
            allocation['allocations']['mirror']['task']['node'] = 'mirror'
            if mutate:
                mutate(graph, allocation)
        self.setup_workspace(consumed)
        self.document = assessment(100, self.payload()[1]['spec']['hash'])
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.write_document(self.document)

    def write_document(self, document):
        self.path.write_text(json.dumps(document))
        self.session.git('add', '-f', self.relative)
        self.session.git('commit', '--allow-empty', '-qm', 'exact migration input fixture')

    def current(self):
        return {step['node']['node']: step for step in self.session.ready()}

    def blocked_with_unrelated_control(self, prior):
        response = self.session.call(100, expected=None)
        ready = {step['node']['node']: step for step in response['next_steps']
                 if step.get('kind') == 'execute'}
        self.assertNotIn('alpha', ready)
        self.assertNotIn('mirror', ready)
        self.assertIn('spectator', ready)
        self.assertEqual(prior['spectator']['input_hash'], ready['spectator']['input_hash'])
        self.assertRegex(json.dumps(response), r'(?i)migration|release|assessment|attestation|evidence')
        return response

    def publish_alpha(self):
        work = self.acquire_workspace('alpha')
        request = self.session.submission(work, {'value': 'Same substantive migration conclusion'},
                                          'migration-candidate-' + str(self.session.sequence))
        request['workspace_checks'] = [[sys.executable, '-c', 'raise SystemExit(0)']]
        self.session.call(100, request)
        self.review_candidate('alpha', 0)
        return self.produced('alpha'), self.result('accept_alpha')[0]

    def test_release_commit_drift_blocks_exact_consumers_with_unchanged_document_and_policy(self):
        before = self.current()
        self.assertIn('alpha', before)
        original = self.path.read_bytes()
        policy_hash = dag_fixtures.content_hash(self.session.project['policy'])
        self.observation['releases'][0]['commit'] = 'e' * 40
        self.blocked_with_unrelated_control(before)
        self.assertEqual(original, self.path.read_bytes())
        self.assertEqual(policy_hash, dag_fixtures.content_hash(self.session.project['policy']))
        self.observation = releases()
        self.assertEqual(before['alpha']['input_hash'], self.current()['alpha']['input_hash'])

    def test_public_dispatch_exposes_new_current_release_binding_after_reassessment(self):
        before = self.current()
        self.assertIn('alpha', before)
        old_hash = before['alpha']['input_hash']
        self.observation['releases'][0]['commit'] = 'e' * 40
        updated = copy.deepcopy(self.document)
        updated['release_snapshot'] = copy.deepcopy(self.observation)
        updated['contracts'][0]['evidence'][0]['release_snapshot'] = copy.deepcopy(self.observation)
        self.write_document(updated)
        after = self.current()
        self.assertIn('alpha', after)
        self.assertNotEqual(old_hash, after['alpha']['input_hash'])
        self.assertEqual(before['spectator']['input_hash'], after['spectator']['input_hash'])
        acquired = self.acquire_workspace('alpha')
        self.assertEqual(after['alpha']['input_hash'], acquired['input_hash'])
        stable = copy.deepcopy((self.provider.issues, self.provider.comments))
        self.observation['releases'][0]['commit'] = 'f' * 40
        request = self.session.submission(acquired, {'value': 'Cannot ignore later provider drift'}, 'stale-release-binding')
        request['workspace_checks'] = [[sys.executable, '-c', 'raise SystemExit(0)']]
        rejected = self.session.call(100, request, expected=2)
        self.assertRegex(json.dumps(rejected), r'(?i)provider|migration|release|stale|input')
        self.assertEqual(stable, (self.provider.issues, self.provider.comments))
        self.observation['releases'][0]['commit'] = 'e' * 40
        self.session.call(100, request)

    def test_unavailable_provider_is_unknown_and_restoration_reuses_exact_input(self):
        before = self.current()
        self.assertIn('alpha', before)
        self.observation = {'status': 'unavailable', 'releases': None}
        self.blocked_with_unrelated_control(before)
        self.observation = releases()
        self.assertEqual(before['alpha']['input_hash'], self.current()['alpha']['input_hash'])

    def test_revoked_or_deleted_attestation_blocks_only_its_consumers_then_exact_restore(self):
        before = self.current()
        self.assertIn('alpha', before)
        original = self.path.read_bytes()
        revoked = copy.deepcopy(self.document)
        revoked['contracts'][0]['status'] = 'unknown'
        revoked['contracts'][0]['evidence'][0]['statement'] = 'Owner explicitly revoked this claim.'
        self.write_document(revoked)
        self.blocked_with_unrelated_control(before)
        self.path.unlink()
        self.session.git('add', '-u', self.relative)
        self.session.git('commit', '-qm', 'removed attestation fixture')
        self.blocked_with_unrelated_control(before)
        self.path.write_bytes(original)
        self.session.git('add', '-f', self.relative)
        self.session.git('commit', '-qm', 'restored attestation fixture')
        self.assertEqual(before['alpha']['input_hash'], self.current()['alpha']['input_hash'])

    def test_foreign_goal_assessment_never_substitutes_for_exact_goal_spec(self):
        before = self.current()
        self.assertIn('alpha', before)
        other = self.path.with_name('101.json')
        other.write_text(json.dumps(assessment(101, self.document['goal_spec'])))
        self.session.git('add', '-f', '.zzzops/migration/101.json')
        self.session.git('commit', '-qm', 'unrelated goal assessment')
        self.assertEqual(before['alpha']['input_hash'], self.current()['alpha']['input_hash'])
        self.write_document(json.loads(other.read_text()))
        response = self.blocked_with_unrelated_control(before)
        self.assertRegex(json.dumps(response), r'(?i)goal|foreign|binding|assessment')
        self.write_document(self.document)
        self.assertEqual(before['alpha']['input_hash'], self.current()['alpha']['input_hash'])

    def test_current_reassessment_requires_new_review_even_for_identical_conclusion(self):
        first, review = self.publish_alpha()
        content = self.read_blob(first)['content']
        self.observation['releases'][0]['commit'] = 'e' * 40
        updated = copy.deepcopy(self.document)
        updated['release_snapshot'] = copy.deepcopy(self.observation)
        updated['contracts'][0]['evidence'][0]['release_snapshot'] = copy.deepcopy(self.observation)
        self.write_document(updated)
        work = self.acquire_workspace('alpha')
        request = self.session.submission(work, {'value': content}, 'new-current-migration-conclusion')
        request['workspace_checks'] = [[sys.executable, '-c', 'raise SystemExit(0)']]
        self.session.call(100, request)
        current = self.produced('alpha')
        self.assertNotEqual(first, current, 'Same content must retain new attempt/provenance identity')
        self.assertEqual(content, self.read_blob(current)['content'])
        self.assertIn('observe_alpha', self.current())
        self.assertNotIn('beta', self.current())
        self.review_candidate('alpha', 0)
        self.assertNotEqual(review, self.result('accept_alpha')[0])
        self.assertEqual(content, self.read_blob(first)['content'])

    def test_two_declared_consumers_share_one_observation_per_projection_then_refresh(self):
        self.release_probe.reset_mock()
        first = self.current()
        self.assertTrue({'alpha', 'mirror'} <= set(first))
        self.assertEqual(1, self.release_probe.call_count)
        self.observation['releases'][0]['commit'] = 'e' * 40
        self.blocked_with_unrelated_control(first)
        self.assertEqual(2, self.release_probe.call_count, 'Next public projection must refresh provider facts')


class GenericMigrationDiscoveryTests(dag_fixtures.DagFixture):
    workspace_graph = GenericMigrationInputTests.workspace_graph
    setup_workspace = GenericMigrationInputTests.setup_workspace
    setup_migration = GenericMigrationInputTests.setup_migration
    write_document = GenericMigrationInputTests.write_document
    current = GenericMigrationInputTests.current

    def setUp(self):
        super().setUp()
        self.setup_migration(self.add_report_node)
        self.assertIn('alpha', self.current(), 'Valid exact assessment is the positive discovery control')
        self.path.unlink()
        self.session.git('add', '-u', self.relative)
        self.session.git('commit', '-qm', 'missing consumed migration evidence')

    def add_report_node(self, graph, _allocation):
        # Factual root report, not a reserved provider slot or eligibility grant.
        # Its actual root provenance and exact spec input are authenticated; the
        # reported preparation/status remain observed factual content. Freshness
        # is enforced independently by the real workspace/preparation adapter.
        report = dag_fixtures.task('report_boundary', role='root')
        report['inputs'] = {'request': dag_fixtures.spec_input()}
        schema = {'kind': 'object', 'fields': {
            'preparation': dag_fixtures.REF_TYPE,
            'release_status': {'kind': 'enum', 'values': ['complete', 'unavailable']},
            'assessment_status': {'kind': 'enum', 'values': ['missing', 'invalid', 'valid']},
            'reason': {'kind': 'string'}}}
        report['outputs'] = {'value': dag_fixtures.output('migration_boundary_report', schema)}
        graph['nodes'].append(report)

    def test_factual_root_report_replays_exactly_without_granting_missing_evidence_authority(self):
        self.observation = {"status": "unavailable", "releases": None}
        step = self.step()
        self.resource(step)
        link = step['preparation']
        digest = link['sha256'] if link['sha256'].startswith('sha256:') else 'sha256:' + link['sha256']
        value = {'preparation': {'hash': digest, 'uri': Path(link['path']).as_uri()},
                 'release_status': 'unavailable', 'assessment_status': 'missing',
                 'reason': 'Independent migration evidence is required before this workspace task.'}
        work = self.session.acquire('report_boundary')
        self.assertIn(self.payload()[1]['spec']['hash'], json.dumps(work['lease']['acquisition']))
        request = self.session.submission(work, {'value': value}, 'exact-migration-boundary-report')
        self.session.call(100, request)
        reference = self.produced('report_boundary')
        artifact = self.read_blob(reference)
        self.assertEqual(value, artifact['content'])
        self.assertEqual('root-thread', artifact['provenance']['actor'])
        self.step()  # A persisted report cannot turn unknown assessment into approval.
        stable = copy.deepcopy((self.provider.issues, self.provider.comments))
        self.session.call(100, request)
        self.assertEqual(stable, (self.provider.issues, self.provider.comments))
        changed = copy.deepcopy(request)
        changed['outputs']['value']['reason'] = 'Changed content under old receipt'
        self.session.call(100, changed, expected=2)
        self.assertEqual(stable, (self.provider.issues, self.provider.comments))
        self.observation = releases()
        self.write_document(self.document)
        self.assertIn('alpha', self.current())
        self.assertEqual(reference, self.produced('report_boundary'))
        self.assertEqual(value, self.read_blob(reference)['content'])

    def step(self):
        response = self.session.call(100, expected=None)
        self.assertFalse(any(step.get('kind') == 'execute' and step.get('node', {}).get('node') == 'alpha'
                             for step in response['next_steps']))
        candidates = [step for step in response['next_steps'] if step.get('path') == self.relative and 'preparation' in step]
        self.assertTrue(candidates, 'Exact missing consumed evidence must expose complete preparation guidance')
        self.assertEqual('alpha', candidates[0]['node']['node'])
        return candidates[0]

    def observation_shapes(self, resource):
        from test_workflow_integration import MigrationDiscoveryJourneyTests
        return MigrationDiscoveryJourneyTests.observation_shapes(self, resource)

    def filled(self, resource, kind='contract_investigation'):
        from test_workflow_integration import MigrationDiscoveryJourneyTests
        return MigrationDiscoveryJourneyTests.filled(self, resource, kind)

    def resource(self, step):
        import hashlib
        link = step['preparation']
        raw = Path(link['path']).read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), link['sha256'].removeprefix('sha256:'))
        value = json.loads(raw)
        self.assertTrue(value.get('instructions'))
        template = value['template']
        self.assertEqual({'schema_version', 'repository', 'goal', 'goal_spec', 'action', 'release_snapshot', 'contracts'}, set(template))
        self.assertEqual('owner/repo', template['repository'])
        self.assertEqual(100, template['goal'])
        self.assertEqual(self.payload()[1]['spec']['hash'], template['goal_spec'])
        self.assertEqual(self.observation, template['release_snapshot'])
        self.assertEqual('unknown', template['contracts'][0]['status'])
        self.assertEqual([], template['contracts'][0]['evidence'])
        examples = value['evidence_templates']
        self.assertTrue({'contract_investigation', 'owner_attestation'} <= set(examples))
        for example in examples.values():
            self.assertFalse(example.get('author'))
        self.assertFalse(examples['owner_attestation'].get('statement'))
        self.assertFalse(examples['contract_investigation'].get('rationale'))
        self.observation_shapes(value)
        return value

    def test_disclosed_preparation_keeps_unknown_facts_and_both_evidence_alternatives_resume(self):
        step = self.step()
        resource = self.resource(step)
        self.write_document(resource['template'])
        self.step()  # An unfilled template cannot manufacture eligibility.
        for kind in ('contract_investigation', 'owner_attestation'):
            with self.subTest(kind=kind):
                self.write_document(self.filled(resource, kind))
                self.assertIn('alpha', self.current())
                self.assertIn('mirror', self.current())

    def test_preparation_identity_stable_then_changes_with_provider_and_exact_spec(self):
        first = self.step()
        resource = self.resource(first)
        same = self.step()
        self.assertEqual(first['preparation'], same['preparation'])
        self.observation['releases'][0]['commit'] = 'e' * 40
        changed = self.step()
        refreshed = self.resource(changed)
        self.assertNotEqual(first['preparation'], changed['preparation'])
        self.assertNotEqual(resource['template']['release_snapshot'], refreshed['template']['release_snapshot'])
        previous_spec = self.payload()[1]['spec']
        self.replace_spec('Additional exact migration compatibility obligation')
        self.session.finish(self.session.acquire('charter'), {'grant': self.allocations})
        self.permit['manifest'] = self.produced('charter', 'grant')
        self.session.finish(self.session.acquire('inspect_charter', actor='fresh-allocation-reviewer'), {'permit': self.permit})
        self.session.finish(self.session.acquire('consent'), {'permit': self.permit})
        rebound = self.step()
        current = self.resource(rebound)
        self.assertNotEqual(changed['preparation'], rebound['preparation'])
        self.assertNotEqual(previous_spec['hash'], current['template']['goal_spec'])

    def test_foreign_stale_ambiguous_and_unknown_provider_block_after_valid_prepared_control(self):
        resource = self.resource(self.step())
        valid = self.filled(resource)
        self.write_document(valid)
        self.assertIn('alpha', self.current())
        for mutate in (lambda d: d.update(goal=101), lambda d: d.update(goal_spec='sha256:' + 'f' * 64),
                       lambda d: d['contracts'][0].update(status='unknown')):
            document = copy.deepcopy(valid)
            mutate(document)
            self.write_document(document)
            self.step()
        self.write_document(valid)
        self.assertIn('alpha', self.current())
        self.observation = {'status': 'unavailable', 'releases': None}
        unknown = self.resource(self.step())
        self.assertEqual({'status': 'unavailable', 'releases': None}, unknown['template']['release_snapshot'])
        self.observation = releases()
        self.assertIn('alpha', self.current())


if __name__ == '__main__':
    unittest.main()
