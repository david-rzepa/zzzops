"""Explore append-only activation without assuming provider compare-and-swap.

Synthetic store only. Does not establish a GitHub comment as immutable/trusted.
Human issue text is never overwritten. Competing activation is an explicit conflict.
"""
import copy
import unittest
from probe import digest


class AppendActivation:
    def __init__(self, source):
        self.source = copy.deepcopy(source)
        self.events = []

    def stage(self, destination):
        return {'source': copy.deepcopy(self.source), 'source_hash': digest(self.source),
                'destination': copy.deepcopy(destination)}

    def append(self, staged, approval, interrupt=None, edit=None):
        if approval != digest(staged):
            raise ValueError('unapproved activation')
        if digest(self.source) != staged['source_hash']:
            raise ValueError('stale source')
        if edit is not None:
            self.source = copy.deepcopy(edit)  # non-cooperating edit after read
        event = {'id': digest(staged), 'staged': copy.deepcopy(staged), 'approval': approval}
        self.events.append(event)
        if interrupt == 'after_append':
            raise RuntimeError('response lost after write')
        return self.read()

    def read(self):
        if not self.events:
            return 'needs_migration', None
        distinct = {e['id']: e for e in self.events}
        if len(distinct) != 1:
            return 'activation_conflict', None
        event = next(iter(distinct.values()))
        staged = event['staged']
        if digest(staged) != event['id'] or event['approval'] != event['id']:
            return 'corrupt_evidence', None
        if digest(self.source) != staged['source_hash']:
            return 'source_drift', None
        return 'active', copy.deepcopy(staged['destination'])


class Probe(unittest.TestCase):
    def test_edit_between_read_and_write_is_not_lost(self):
        s = AppendActivation({'schema': 1, 'spec': 'old'})
        p = s.stage({'schema': 2, 'missing': ['review']})
        state, _ = s.append(p, digest(p), edit={'schema': 1, 'spec': 'human change'})
        self.assertEqual(state, 'source_drift')
        self.assertEqual(s.source['spec'], 'human change')
        self.assertEqual(s.events[0]['staged']['source']['spec'], 'old')

    def test_uncertain_write_retry_deduplicates_semantically(self):
        s = AppendActivation({'schema': 1}); p = s.stage({'schema': 2})
        with self.assertRaises(RuntimeError): s.append(p, digest(p), 'after_append')
        s.append(p, digest(p))
        self.assertEqual(len(s.events), 2)  # at-least-once transport, one logical event
        self.assertEqual(s.read(), ('active', {'schema': 2}))

    def test_competing_adoptions_block_not_last_writer_wins(self):
        s = AppendActivation({'schema': 1})
        a, b = s.stage({'schema': 2, 'spec': 'A'}), s.stage({'schema': 2, 'spec': 'B'})
        s.append(a, digest(a)); s.append(b, digest(b))
        self.assertEqual(s.read(), ('activation_conflict', None))

    def test_tampered_migration_evidence_blocks(self):
        s = AppendActivation({'schema': 1}); p = s.stage({'schema': 2})
        s.append(p, digest(p)); s.events[0]['staged']['destination']['forged'] = True
        self.assertEqual(s.read(), ('corrupt_evidence', None))

    def test_one_incompatible_goal_does_not_block_another(self):
        a, b = AppendActivation({'schema': 1}), AppendActivation({'schema': 1})
        p = b.stage({'schema': 2}); b.append(p, digest(p))
        self.assertEqual(a.read()[0], 'needs_migration')
        self.assertEqual(b.read()[0], 'active')


if __name__ == '__main__':
    unittest.main(verbosity=2)
