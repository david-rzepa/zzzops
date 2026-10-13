"""Publication discovery must not churn its bounded derived history cache."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock

from test_evidence_dag_journeys import z


class PublicationCacheScanTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        patch = mock.patch.dict(os.environ, {
            'XDG_CACHE_HOME': directory.name, 'LOCALAPPDATA': directory.name})
        patch.start()
        self.addCleanup(patch.stop)
        self.cache = z._workflow.state_cache
        self.repository = 'owner/repo'
        self.comments = [{'id': 1, 'body': 'retained immutable observation'}]
        self.goals = [{'key': number, 'schema_version': 2, 'status': 'in_progress'}
                      for number in range(1, 95)]
        self.bodies, self.blobs = {}, {}
        for goal in self.goals:
            number = goal['key']
            graph = {'nodes': [], 'task_sets': []}
            graph_ref = self.ref(graph)
            payload_ref = self.ref({'graph': graph_ref, 'evidence': []})
            envelope = {'schema_version': 2, 'repository': self.repository,
                        'issue': number, 'revision': 1, 'state': 'open',
                        'parent': None, 'payload': payload_ref}
            self.bodies[number] = '<!-- zzzops-goal\n' + json.dumps(envelope) + '\nzzzops-goal -->'

    def ref(self, value):
        identity = z._comment_store.digest(value)
        self.blobs[identity] = value
        return {'hash': identity, 'uri': 'urn:' + identity}

    def issue_hash(self, number):
        return z._comment_store.text_hash(self.bodies[number])

    def store(self, number):
        self.cache.store(self.repository, number, self.issue_hash(number),
                         self.comments, self.comments, {}, time.time())

    def scan(self, *, require_broadphase=False):
        engine = z._workflow.Workflow.__new__(z._workflow.Workflow)
        engine.repository, engine.runtime, engine.api = self.repository, {'root_id': 'root'}, z
        engine.repo = Path('/unused-test-repository')
        engine.portfolio = lambda: self.goals
        engine.adapter = mock.Mock()
        engine.adapter.get_issue.side_effect = lambda number: {'body': self.bodies[number]}
        visited, hits, misses = [], [], []
        def read(number, ref):
            if number not in visited:
                visited.append(number)
                cached = self.cache.load(self.repository, number, self.issue_hash(number), {})
                (hits if cached is not None else misses).append(number)
                self.store(number)
            return self.blobs[ref['hash']]
        engine.read_artifact = read
        with mock.patch.object(z, 'provider_issue_snapshot',
                               side_effect=lambda repo, repository, number: {'body': self.bodies[number]}):
            self.assertEqual(set(), engine.node_managed_publication_branches([]))
        if require_broadphase:
            engine.adapter.get_issue.assert_not_called()
            self.assertEqual(set(range(1, 95)), set(engine._issue_observations))
        self.assertEqual(set(range(1, 95)), set(visited), 'every eligible goal is still read')
        return hits, misses

    def test_discovery_reuses_current_broadphase_bodies_without_rest_issue_reads(self):
        for number in range(1, 95):
            self.store(number)
        hits, misses = self.scan(require_broadphase=True)
        self.assertEqual(64, len(hits))
        self.assertEqual(30, len(misses))

    def test_repeated_scan_larger_than_cache_preserves_hits_without_expanding_capacity(self):
        for number in range(1, 95):
            self.store(number)
        for _ in range(2):
            hits, misses = self.scan()
            self.assertEqual(64, len(hits))
            self.assertEqual(30, len(misses))
            self.assertEqual(64, len(list(self.cache._root().glob('*.json'))))

    def test_cache_hint_never_skips_corrupt_or_changed_identity_reads(self):
        for number in range(1, 95):
            self.store(number)
        number = 94
        self.cache._path(self.repository, number, self.issue_hash(number)).write_text('{corrupt')
        hits, misses = self.scan()
        self.assertIn(number, misses, 'a positive presence hint does not validate cached data')
        self.assertEqual(63, len(hits))
        self.bodies[number] += '\nnew current provider body'
        self.assertFalse(self.cache.has_entry(self.repository, number, self.issue_hash(number)))

    def test_presence_hint_respects_repository_and_body_partition_and_rejects_symlink(self):
        self.store(1)
        identity = self.issue_hash(1)
        self.assertTrue(self.cache.has_entry(self.repository, 1, identity))
        self.assertFalse(self.cache.has_entry('another/repo', 1, identity))
        self.assertFalse(self.cache.has_entry(self.repository, 1, 'sha256:' + '0' * 64))
        path = self.cache._path(self.repository, 1, identity)
        target = Path(tempfile.gettempdir()) / 'zzzops-unused-scan-hint-target'
        path.unlink()
        try:
            path.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest('symlink creation unavailable')
        self.assertFalse(self.cache.has_entry(self.repository, 1, identity))


if __name__ == '__main__':
    unittest.main()
