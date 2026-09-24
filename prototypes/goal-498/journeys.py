"""Composed witnesses: scripted agent outputs, one unchanged generic Model.

These are not real agents or a complete normative-schema implementation.
"""
import copy
import unittest
from dataclasses import replace
from probe import Fixture as Model, Node, digest
from cooperative_migration import Store


def entry(envelope, provider, reviewed_policy):
    if provider['state'] == 'closed':
        return 'archived', None  # body is deliberately not accessed
    if not isinstance(envelope, dict) or type(envelope.get('schema_version')) is not int:
        return 'invalid_envelope', None
    if envelope.get('repository', provider['repository']) != provider['repository']:
        return 'identity_mismatch', None
    if envelope.get('issue', provider['issue']) != provider['issue']:
        return 'identity_mismatch', None
    version = envelope['schema_version']
    if version == 2:
        return 'normal', reviewed_policy['normal']
    if version == 1:
        return 'migration', reviewed_policy['migration']  # never body-provided graph
    return 'unsupported_version', None


class Journeys(unittest.TestCase):
    def test_understanding_synthesis_grill_bucket_revision(self):
        m = Model({'frame': Node(inputs=('spec',)),
                   'synthesis': Node(needs=('frame',), joins=('investigate',), independent=True),
                   'grill': Node(needs=('synthesis',), root_only=True),
                   'approve': Node(needs=('grill',), root_only=True, gate=True)}, {'spec': 'request'})
        m.expand_from('investigate', 'frame', {})
        self.assertEqual(m.ready(), ['frame'])
        m.run('frame', {'items': {'requirements': 'scope?', 'migration': 'compatibility?'}, 'rationale': 'initial buckets'})
        m.run('investigate/requirements', 'requirements', 'analyst1')
        m.run('investigate/migration', 'assume v1 retention', 'analyst2')
        m.run('synthesis', 'ask retention policy', 'synthesizer')
        with self.assertRaisesRegex(ValueError, 'root-only'):
            m.run('grill', 'unauthorized answer', 'analyst1')
        m.run('grill', 'human: preserve v1 history', 'root')
        m.correct('human-answer', 'frame', m.results['frame']['output'],
                  'migration bucket must investigate preservation')
        self.assertEqual(m.ready(), ['frame'])
        m.run('frame', {'items': {'requirements': 'scope?', 'migration': 'preserve historical evidence'}, 'rationale': 'human answer'})
        self.assertTrue(m.current('investigate/requirements'))
        self.assertEqual(m.ready(), ['investigate/migration'])
        m.run('investigate/migration', 'explicit preservation plan', 'analyst2')
        m.run('synthesis', 'complete understanding', 'synthesizer')
        m.run('grill', 'no unanswered human questions', 'root')
        self.assertNotIn('approve', m.ready())
        self.assertFalse(m.current('approve'))
        m.resolve('human-answer', 'synthesis')
        m.run('approve', 'exact understanding approved', 'root')
        self.assertTrue(m.current('approve'))
        self.assertTrue(all(m.resolved(k) for k in m.findings))
        self.assertEqual(m.ready(), [])

    def test_risk_review_regression_test_and_reimplementation(self):
        m = Model({'tests': Node(inputs=('spec',)), 'test_review': Node(needs=('tests',), independent=True),
                   'code': Node(needs=('test_review',)), 'verify': Node(needs=('code',)),
                   'correctness': Node(needs=('code', 'verify'), independent=True),
                   'concurrency': Node(needs=('code', 'verify'), independent=True),
                   'publish': Node(needs=('correctness', 'concurrency'), gate=True)}, {'spec': 'counter'})
        m.run('tests', 'sequential test'); m.run('test_review', 'baseline accepted', 'test-reviewer')
        m.run('code', 'unsynchronized increment'); m.run('verify', 'sequential pass')
        self.assertEqual(m.ready(), ['concurrency', 'correctness'])
        m.run('correctness', 'ordinary behavior ok', 'reviewer1')
        m.run('concurrency', 'race: add interleaving regression', 'reviewer2')
        m.correct('race-coverage', 'tests', m.results['tests']['output'], 'interleaving regression')
        self.assertEqual(m.ready(), ['tests'])
        m.run('tests', 'sequential + race regression')
        m.run('test_review', 'new test demonstrates failure', 'test-reviewer')
        m.run('code', 'synchronized increment'); m.run('verify', 'all checks pass')
        m.run('correctness', 'accepted corrected behavior', 'reviewer1')
        m.run('concurrency', 'synchronization and regression inspected', 'reviewer2')
        self.assertNotIn('publish', m.ready())
        m.resolve('race-coverage', 'test_review')
        self.assertEqual(m.ready(), ['publish'])

    def test_edited_feedback_is_new_revision_not_mutable_retry(self):
        m = Model({'code': Node(inputs=('spec',)),
                   'integrate': Node(needs=('code',), independent=True),
                   'merge': Node(needs=('integrate',), gate=True)}, {'spec': 'request'})
        m.run('code', 'v1'); m.run('integrate', 'comment1', 'reviewer')
        m.correct('comment1-r1', 'code', m.results['code']['output'], 'fix error')
        with self.assertRaisesRegex(ValueError, 'conflicting retry'):
            m.correct('comment1-r1', 'code', m.results['code']['output'], 'edited request')
        m.run('code', 'v2'); m.run('integrate', 'fix verified', 'reviewer')
        m.resolve('comment1-r1', 'integrate')
        m.correct('comment1-r2', 'code', m.results['code']['output'], 'also cover recovery')
        m.run('code', 'v3'); m.run('integrate', 'both revisions verified', 'reviewer')
        self.assertNotIn('merge', m.ready())
        m.resolve('comment1-r1', 'integrate'); m.resolve('comment1-r2', 'integrate')
        self.assertIn('merge', m.ready())

    def test_parent_change_requires_root_admission(self):
        m = Model({'parent': Node(inputs=('spec',)), 'child': Node(needs=('parent',))}, {'spec': 'scope'})
        m.run('parent', 'approved contract'); m.run('child', 'child design')
        with self.assertRaisesRegex(ValueError, 'unadmitted'):
            m.correct('scope-change', 'parent', m.results['parent']['output'], 'expand contract', 'child-reviewer')
        self.assertTrue(m.current('parent'))
        m.correct('scope-change', 'parent', m.results['parent']['output'], 'root-approved scope change')
        self.assertEqual(m.ready(), ['parent'])

    def test_exclusion_is_authorized_and_capability_wait_not_invalidation(self):
        m = Model({'base': Node(inputs=('spec',)),
                   'select': Node(needs=('base',), root_only=True),
                   'join': Node(needs=('base',), joins=('risk',))}, {'spec': 'request'})
        m.expand_from('risk', 'select', {'capability': 'special'})
        m.run('base', 'done')
        self.assertEqual(m.ready(), ['select'])
        with self.assertRaisesRegex(ValueError, 'root-only'):
            m.run('select', {'items': {}, 'rationale': 'not relevant'}, 'worker')
        m.run('select', {'items': {}, 'rationale': 'reviewed no risk'}, 'root')
        self.assertEqual(m.ready(), ['join'])
        m.correct('risk', 'select', m.results['select']['output'], 'new risk')
        m.run('select', {'items': {'specialist': 'required'}, 'rationale': 'new risk'}, 'root')
        self.assertEqual(m.ready(), [])
        self.assertTrue(m.current('base'))
        m.capabilities.add('special'); self.assertEqual(m.ready(), ['risk/specialist'])

    def test_migration_entry_uses_same_nodes_and_preserves_gaps(self):
        nodes = {'analyze': Node(inputs=('source',)), 'convert': Node(needs=('analyze',)),
                 'review': Node(needs=('convert',), independent=True),
                 'approve': Node(needs=('review',), root_only=True),
                 'activate': Node(needs=('approve',))}
        policy = {'normal': {'ordinary': Node()}, 'migration': nodes}
        provider = {'state': 'open', 'repository': 'fixture', 'issue': 498}
        status, graph = entry({'schema_version': 1, 'graph': 'untrusted'}, provider, policy)
        self.assertEqual(status, 'migration'); self.assertEqual(graph, nodes)
        s = Store(); s.acquire('root')
        m = Model(graph, {'source': copy.deepcopy(s.body)})
        m.run('analyze', 'v1 source inspected')
        converted = {'schema': 2, 'human': s.body['human'], 'historical': s.body['evidence'], 'missing': ['new review']}
        m.run('convert', converted); m.run('review', 'mapping independently inspected', 'reviewer')
        plan = s.stage(converted)
        with self.assertRaisesRegex(ValueError, 'root-only'): m.run('approve', digest(plan), 'worker')
        m.run('approve', digest(plan), 'root')
        s.apply('root', plan, digest(plan)); m.run('activate', 'readback verified', 'root')
        self.assertEqual(s.body['missing'], ['new review'])
        self.assertEqual(entry(None, {**provider, 'state': 'closed'}, policy)[0], 'archived')
        self.assertEqual(entry({'schema_version': 99}, provider, policy)[0], 'unsupported_version')
        self.assertEqual(entry({'schema_version': 2}, provider, policy)[0], 'normal')

    def test_authorized_exclusion_then_retirement_preserves_history(self):
        m = Model({'join': Node(joins=('work',))}, {})
        m.expand('work', {'a': 'obsolete investigation'}, {})
        m.run('work/a', 'historical work')
        before = copy.deepcopy(m.history)
        m.expand('work', {}, {})
        self.assertEqual(m.history[:len(before)], before)
        self.assertIn('join', m.ready())
        self.assertNotIn('work/a', m.ready())

    def test_identity_and_version_fail_closed(self):
        provider = {'state': 'open', 'repository': 'fixture', 'issue': 498}
        policy = {'normal': {}, 'migration': {}}
        for bad in (None, {'schema_version': True}, {'schema_version': '1'}):
            self.assertEqual(entry(bad, provider, policy)[0], 'invalid_envelope')
        self.assertEqual(entry({'schema_version': 1, 'issue': 499}, provider, policy)[0], 'identity_mismatch')

    def test_unresolved_findings_cannot_be_retired_by_membership_change(self):
        m = Model({'join': Node(joins=('work',), gate=True)}, {})
        m.expand('work', {'a': 'investigate'}, {})
        m.run('work/a', 'answer')
        m.correct('f', 'work/a', m.results['work/a']['output'], 'contradiction')
        with self.assertRaisesRegex(ValueError, 'unresolved'): m.expand('work', {}, {})
        self.assertIn('f', m.findings)
        self.assertEqual(m.ready(), ['work/a'])

    def test_conflicting_findings_need_interpretation_before_dispatch(self):
        m = Model({'interpret': Node(inputs=('findings',), root_only=True),
                   'code': Node(needs=('interpret',))},
                  {'findings': ['reviewer A: preserve API', 'reviewer B: remove API']})
        self.assertEqual(m.ready(), ['interpret'])
        with self.assertRaisesRegex(ValueError, 'root-only'):
            m.run('interpret', 'silently choose B', 'reviewer B')
        m.run('interpret', 'root decision: preserve API and deprecate separately', 'root')
        self.assertEqual(m.ready(), ['code'])

    def test_resolver_obligation_edges_are_checked_for_cycles(self):
        nodes = {'code': Node(), 'gate': Node(needs=('code',)),
                 'resolver': Node(needs=('gate',), independent=True)}
        # Generic configuration compilation materializes obligation requirements.
        compiled = {**nodes, 'gate': replace(nodes['gate'], needs=('code', 'resolver'))}
        with self.assertRaisesRegex(ValueError, 'cycle'): Model(compiled, {})

    def test_single_finding_revision_transfer_and_resolution(self):
        m = Model({'code': Node(inputs=('spec',)), 'review': Node(needs=('code',), independent=True),
                   'publish': Node(needs=('review',), gate=True)}, {'spec': 'request'})
        m.run('code', 'v1'); m.run('review', 'finding', 'reviewer')
        m.correct('comment-1', 'code', m.results['code']['output'], 'fix A')
        rev1 = digest(m.findings['comment-1'])
        with self.assertRaisesRegex(ValueError, 'authorized'):
            m.supersede('comment-1', rev1, 'drop A', 'commenter', 'narrowed', 'comment edited')
        self.assertEqual(m.findings['comment-1']['revision'], 1)
        m.supersede('comment-1', rev1, 'fix A and recovery B', 'root', 'carried', 'A retained and B added')
        with self.assertRaisesRegex(ValueError, 'conflicting'):
            m.supersede('comment-1', rev1, 'competing edit', 'root', 'carried', 'stale proposal')
        self.assertEqual(set(m.findings), {'comment-1'})
        self.assertEqual(m.finding_history['comment-1'][0]['revision'], 1)
        self.assertFalse(m.resolved('comment-1'))
        m.run('code', 'A and B fixed'); m.run('review', 'both fixes verified', 'reviewer')
        self.assertNotIn('publish', m.ready())
        m.resolve('comment-1', 'review')
        m.run('publish', 'published')
        self.assertTrue(m.current('publish'))
        self.assertTrue(m.resolved('comment-1'))

    def test_narrowing_and_withdrawal_need_exact_authority(self):
        m = Model({'code': Node(inputs=('spec',))}, {'spec': 'request'})
        m.run('code', 'v1'); m.correct('f', 'code', m.results['code']['output'], 'A and B')
        original = digest(m.findings['f'])
        m.supersede('f', original, 'A only', 'root', 'narrowed', 'root explicitly retires B')
        self.assertFalse(m.resolved('f'))
        with self.assertRaisesRegex(ValueError, 'authorized'):
            m.withdraw('f', digest(m.findings['f']), 'commenter', 'thread deleted')
        with self.assertRaisesRegex(ValueError, 'exact withdrawal'):
            m.withdraw('f', original, 'root', 'stale version')
        m.withdraw('f', digest(m.findings['f']), 'root', 'root explicitly retires A')
        self.assertTrue(m.resolved('f'))
        self.assertEqual(m.finding_history['f'][0]['change'], 'A and B')

    def test_member_obligation_survives_retirement_and_explicit_generation_transfer(self):
        m = Model({'publish': Node(joins=('work',), gate=True)}, {})
        m.expand('work', {'a': 'migration', 'b': 'requirements'}, {})
        m.run('work/a', 'migration assumption'); m.run('work/b', 'stable requirements')
        sibling = copy.deepcopy(m.results['work/b'])
        exact = m.exact_member('work', 'a', 1)
        self.assertEqual(exact['item'], 'a'); self.assertEqual(exact['generation'], 1)
        m.correct('migration-gap', 'work/a', m.results['work/a']['output'], 'preserve history')
        with self.assertRaisesRegex(ValueError, 'unresolved'): m.expand('work', {'b': 'requirements'}, {})
        m.authorize_retirement('work/a', 'root', 'pause member, retain its obligation in work scope')
        m.expand('work', {'b': 'requirements'}, {})
        self.assertNotIn('publish', m.ready())
        self.assertFalse(m.resolved('migration-gap'))
        m.expand('work', {'a': 'migration', 'b': 'requirements'}, {})
        self.assertEqual(m.generations['work/a'], 2)
        self.assertEqual(m.exact_member('work', 'a', 1), exact)  # historical address retained
        self.assertEqual(m.results['work/b'], sibling)
        self.assertTrue(m.current('work/b'))
        m.run('work/a', 'new generation without inherited correction')
        m.nodes['review_a'] = Node(needs=('work/a',), independent=True)
        m.run('review_a', 'new generation reviewed', 'reviewer')
        with self.assertRaisesRegex(ValueError, 'generation'):
            m.resolve('migration-gap', 'review_a')
        self.assertFalse(m.resolved('migration-gap'))
        self.assertNotIn('publish', m.ready())
        m.supersede('migration-gap', digest(m.findings['migration-gap']), 'preserve history',
                    'root', 'carried', 'explicitly inherit old obligation', generation=2)
        m.run('work/a', 'history preserved')
        m.nodes['review_a'] = Node(needs=('work/a',), independent=True)
        m.run('review_a', 'inherited obligation verified', 'reviewer')
        self.assertNotIn('publish', m.ready())
        m.resolve('migration-gap', 'review_a')
        self.assertEqual(m.finding_history['migration-gap'][0]['generation'], 1)
        m.run('publish', 'ready')
        self.assertTrue(m.current('publish'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
