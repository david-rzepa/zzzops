"""Adversarial tests for one submission path and derived zero/one/many work."""
import copy
import unittest
from probe import Model, Fixture, Node, digest


def decision(kind, scope, *args):
    return {'kind': kind, 'scope': scope, 'args': args}


class Simplification(unittest.TestCase):
    def correction_model(self):
        m = Model({'code': Node(inputs=('spec',)),
                   'admit': Node(needs=('code',), root_only=True,
                                 permits=(('admit', 'code'),)),
                   'review': Node(needs=('code',), independent=True,
                                  permits=(('resolve', 'code'),)),
                   'publish': Node(needs=('review',), gate=True)}, {'spec': 'request'})
        m.run('code', 'v1')
        return m

    def test_admission_survives_its_own_subject_invalidation_and_rebuild(self):
        m = self.correction_model()
        correction = decision('admit', 'code', 'f', 'code', m.results['code']['output'], 'fix')
        m.submit('admit', m.begin('admit'), 'admitted', 'root', [correction])
        self.assertFalse(m.current('admit'))  # its inspected v1 is now stale
        self.assertIn('f', m.findings)  # accepted revision does not oscillate away
        self.assertIn('code', m.ready())
        before = copy.deepcopy(m.findings)
        m.rebuild()
        self.assertEqual(m.findings, before)
        self.assertFalse(m.current('code'))
        m.run('code', 'fixed')
        before = m.fingerprint('code')
        resolution = decision('resolve', 'code', 'f', 'review')
        m.submit('review', m.begin('review'), 'verified', 'reviewer', [resolution])
        self.assertEqual(m.fingerprint('code'), before)
        self.assertTrue(m.resolved('f'))
        self.assertIn('publish', m.ready())
        m.rebuild()
        self.assertTrue(m.resolved('f'))
        self.assertIn('publish', m.ready())

    def test_atomic_mixed_bundle_and_undeclared_scope(self):
        m = self.correction_model()
        token = m.begin('admit')
        valid = decision('admit', 'code', 'f', 'code', m.results['code']['output'], 'fix')
        invalid = decision('withdraw', 'code', 'f', 'wrong', 'hide it')
        before = copy.deepcopy(m.__dict__)
        with self.assertRaisesRegex(ValueError, 'undeclared'):
            m.submit('admit', token, 'bundle', 'root', [valid, invalid])
        self.assertEqual(m.__dict__, before)
        with self.assertRaisesRegex(ValueError, 'scope'):
            m.submit('admit', token, 'bundle', 'root',
                     [decision('admit', 'code', 'f', 'admit', 'hash', 'expand authority')])
        self.assertEqual(m.__dict__, before)

    def test_exact_retry_survives_staleness_and_rejects_payload_change(self):
        m = self.correction_model(); token = m.begin('admit')
        args = [decision('admit', 'code', 'f', 'code', m.results['code']['output'], 'fix')]
        first = m.submit('admit', token, 'admitted', 'root', args, request='request1')
        size = len(m.evidence)
        self.assertEqual(m.submit('admit', token, 'admitted', 'root', args, request='request1'), first)
        self.assertEqual(len(m.evidence), size)
        with self.assertRaisesRegex(ValueError, 'conflicting request'):
            m.submit('admit', token, 'changed', 'root', args, request='request1')

    def test_fake_result_output_cannot_grant_authority(self):
        m = self.correction_model()
        m.nodes['untrusted'] = Node()
        m.run('untrusted', {'type': 'result', 'actor': 'root', 'approved': True})
        self.assertFalse(m.current('admit'))
        self.assertEqual(m.findings, {})
        with self.assertRaisesRegex(ValueError, 'root-only'):
            m.submit('admit', m.begin('admit'), 'approval', 'commenter')

    def test_zero_one_many_missing_and_unavailable_are_distinct(self):
        m = Model({'select': Node(inputs=('risks',), root_only=True, capability='assess'),
                   'join': Node(joins=('risks',))}, {})
        m.expand_from('risks', 'select', {})
        self.assertEqual(m.ready(), [])  # missing AND unavailable, not excluded
        m.inputs['risks'] = 'reviewed input'
        self.assertEqual(m.ready(), [])  # capability missing, not empty
        m.capabilities.add('assess')
        self.assertEqual(m.ready(), ['select'])
        with self.assertRaisesRegex(ValueError, 'rationale'):
            m.run('select', {'items': {}, 'rationale': ''}, 'root')
        self.assertNotIn('risks', m.members)
        m.run('select', {'items': {}, 'rationale': 'no applicable risk'}, 'root')
        m.run('join', 'empty set complete')
        m.inputs['risks'] = 'one risk'
        self.assertFalse(m.current('join'))
        m.run('select', {'items': {'a': 'risk A'}, 'rationale': 'A needed'}, 'root')
        m.run('risks/a', 'review A'); m.run('join', 'one complete')
        sibling = copy.deepcopy(m.results['risks/a'])
        m.inputs['risks'] = 'two risks'
        m.run('select', {'items': {'a': 'risk A', 'b': 'risk B'}, 'rationale': 'B discovered'}, 'root')
        self.assertEqual(m.ready(), ['risks/b'])
        self.assertEqual(m.results['risks/a'], sibling)
        self.assertFalse(m.current('join'))
        m.rebuild()
        self.assertEqual(m.ready(), ['risks/b'])

    def test_selection_cannot_supply_template_or_change_authority(self):
        m = Model({'select': Node(root_only=True), 'join': Node(joins=('work',))}, {})
        m.expand_from('work', 'select', {'independent': True})
        with self.assertRaisesRegex(ValueError, 'selection'):
            m.run('select', {'items': {}, 'rationale': 'none', 'template': {'independent': False}}, 'root')
        self.assertEqual(m.evidence, {})

    def test_rebuild_preserves_generations_obligations_and_transfers(self):
        m = Fixture({'join': Node(joins=('work',), gate=True)}, {})
        m.expand('work', {'a': 'task'}, {}); old = m.begin('work/a'); m.run('work/a', 'old')
        m.correct('f', 'work/a', m.results['work/a']['output'], 'fix')
        m.authorize_retirement('work/a', 'root', 'retain obligation')
        m.expand('work', {}, {}); m.expand('work', {'a': 'task'}, {})
        with self.assertRaisesRegex(ValueError, 'stale'): m.finish('work/a', old, 'old worker')
        m.run('work/a', 'new'); m.nodes['review'] = Node(needs=('work/a',), independent=True)
        m.run('review', 'new review', 'reviewer')
        with self.assertRaisesRegex(ValueError, 'generation'): m.resolve('f', 'review')
        before = (copy.deepcopy(m.findings), copy.deepcopy(m.generations), m.ready())
        m.rebuild()
        self.assertEqual((m.findings, m.generations, m.ready()), before)
        self.assertFalse(m.resolved('f'))
        m.supersede('f', digest(m.findings['f']), 'fix', 'root', 'carried', 'inherit', generation=2)
        m.run('work/a', 'fixed'); m.run('review', 'fixed review', 'reviewer'); m.resolve('f', 'review')
        m.rebuild()
        self.assertTrue(m.resolved('f')); self.assertIn('join', m.ready())

    def test_reviewed_graph_edit_expresses_same_fanout_without_expansion(self):
        m = Model({'a': Node(inputs=('a',)), 'join': Node(needs=('a',))}, {'a': 'A'})
        m.run('a', 'answer A'); m.run('join', 'one')
        # Explicit fixture policy grants this graph edit, not worker output.
        m.nodes['b'] = Node(inputs=('b',)); m.inputs['b'] = 'B'
        m.nodes['join'] = Node(needs=('a', 'b')); m.validate()
        self.assertEqual(m.ready(), ['b']); self.assertTrue(m.current('a'))
        m.run('b', 'answer B'); self.assertEqual(m.ready(), ['join'])

    def test_old_review_not_reused_for_identical_new_generation(self):
        m = Fixture({}, {})
        m.expand('work', {'a': 'task'}, {}); m.run('work/a', 'same')
        m.nodes['review'] = Node(needs=('work/a',), independent=True)
        m.run('review', 'accepted', 'reviewer')
        m.expand('work', {}, {}); m.expand('work', {'a': 'task'}, {})
        m.run('work/a', 'same')
        self.assertFalse(m.current('review'))
        self.assertIn('review', m.ready())


if __name__ == '__main__': unittest.main()
