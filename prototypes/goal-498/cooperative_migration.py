"""Selected migration model: cooperative writers, separate durable writes.

No CAS, cross-write transaction or protection from a writer ignoring ownership.
This model tests retry/recovery semantics, not remote-provider integration.
"""
import copy
import unittest
from probe import digest


class Store:
    def __init__(self):
        self.body = {'schema': 1, 'human': 'keep', 'evidence': ['old']}
        self.labels = {'schema': 1}
        self.owner = None
        self.backups = {}
        self.intents = {}
        self.receipts = set()

    def acquire(self, owner):
        if self.owner not in (None, owner):
            raise ValueError('writer already owns issue')
        self.owner = owner

    def stage(self, destination):
        return {'source': copy.deepcopy(self.body), 'destination': copy.deepcopy(destination),
                'policy': 'reviewed-policy', 'repository': 'fixture', 'goal': 498}

    def recover(self, expected_owner, observed_worker_status):
        if self.owner != expected_owner or observed_worker_status != 'stopped':
            raise ValueError('exact owner and observed stopped worker required')
        self.owner = None

    def apply(self, owner, plan, approval, crash=None):
        def checkpoint(boundary):
            if crash == boundary:
                raise RuntimeError(boundary)
        if self.owner != owner:
            raise ValueError('not current owner')
        key = digest(plan)
        if approval != key:
            raise ValueError('unapproved exact plan')
        if self.body not in (plan['source'], plan['destination']):
            raise ValueError('observed drift; preserve current body')
        if self.body == plan['destination'] and key not in self.intents:
            raise ValueError('cannot attribute destination to this migration')
        self.backups.setdefault(key, copy.deepcopy(plan['source']))
        checkpoint('backup')
        self.intents.setdefault(key, copy.deepcopy(plan))
        checkpoint('intent')
        if self.body == plan['source']:
            self.body = copy.deepcopy(plan['destination'])
        checkpoint('body')
        self.labels['schema'] = plan['destination']['schema']
        checkpoint('labels')
        self.receipts.add(key)
        checkpoint('receipt')


class Probe(unittest.TestCase):
    def test_each_write_boundary_is_retryable(self):
        for boundary in ('backup', 'intent', 'body', 'labels', 'receipt'):
            with self.subTest(boundary=boundary):
                s = Store(); s.acquire('root')
                p = s.stage({'schema': 2, 'human': 'keep', 'missing': ['independent review']})
                with self.assertRaises(RuntimeError): s.apply('root', p, digest(p), boundary)
                s.apply('root', p, digest(p)); s.apply('root', p, digest(p))
                self.assertEqual(s.body, p['destination'])
                self.assertEqual(s.labels, {'schema': 2})
                self.assertEqual(s.backups[digest(p)], p['source'])
                self.assertEqual(len(s.receipts), 1)

    def test_competing_cooperative_writer_denied(self):
        s = Store(); s.acquire('first')
        with self.assertRaisesRegex(ValueError, 'already owns'): s.acquire('second')

    def test_observed_external_drift_is_not_overwritten(self):
        s = Store(); s.acquire('root'); p = s.stage({'schema': 2})
        s.body['human'] = 'external edit'
        with self.assertRaisesRegex(ValueError, 'drift'): s.apply('root', p, digest(p))
        self.assertEqual(s.body['human'], 'external edit')

    def test_old_owner_cannot_resume(self):
        s = Store(); s.acquire('old'); p = s.stage({'schema': 2})
        s.owner = 'new'
        with self.assertRaisesRegex(ValueError, 'owner'): s.apply('old', p, digest(p))

    def test_changed_plan_needs_new_approval(self):
        s = Store(); s.acquire('root'); p = s.stage({'schema': 2}); approval = digest(p)
        p['destination']['fabricated_approval'] = True
        with self.assertRaisesRegex(ValueError, 'unapproved'): s.apply('root', p, approval)

    def test_recovery_requires_observed_stop_not_expiry_or_unknown(self):
        s = Store(); s.acquire('old')
        for status in ('expired', 'unknown', 'active'):
            with self.assertRaisesRegex(ValueError, 'stopped'): s.recover('old', status)
        with self.assertRaisesRegex(ValueError, 'exact owner'): s.recover('wrong', 'stopped')
        s.recover('old', 'stopped'); s.acquire('new')
        self.assertEqual(s.owner, 'new')


if __name__ == '__main__':
    unittest.main(verbosity=2)
