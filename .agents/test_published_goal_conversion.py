"""Published conversion targets through the public CLI and bounded Git resolver."""
import copy
import hashlib
import json
import os
import subprocess
from pathlib import Path
import unittest
import test_evidence_dag_journeys as dag
import test_goal_schema_conversion as conversion_fixtures


class PublishedConversionTests(dag.DagFixture):
    entry = conversion_fixtures.MigrationEntryPublicTests.entry
    migration_result = conversion_fixtures.MigrationEntryPublicTests.migration_result

    def publish(self, files):
        repo = self.fixture.repo
        env = os.environ.copy()
        env['GIT_INDEX_FILE'] = str(Path(self.session.control) / 'published-index')
        parent = getattr(self, 'published_head', None) or subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip()
        subprocess.run(['git', 'read-tree', parent], cwd=repo, env=env, check=True)
        refs = {}
        for name, value in files.items():
            raw = value if isinstance(value, bytes) else json.dumps(
                value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
            blob = subprocess.check_output(['git', 'hash-object', '-w', '--stdin'], cwd=repo, input=raw).decode().strip()
            path = '.zzzops/published/' + name
            subprocess.run(['git', 'update-index', '--add', '--cacheinfo', f'100644,{blob},{path}'], cwd=repo, env=env, check=True)
            refs[name] = {'hash': 'sha256:' + hashlib.sha256(raw).hexdigest(), 'path': path}
        tree = subprocess.check_output(['git', 'write-tree'], cwd=repo, env=env, text=True).strip()
        head = subprocess.check_output(['git', 'commit-tree', tree, '-p', parent], cwd=repo,
                                      input='test: publish immutable conversion artifacts\n', text=True).strip()
        self.published_head = head
        return {name: {'hash': ref['hash'], 'uri': f"git:{head}:{ref['path']}"} for name, ref in refs.items()}

    def prepare(self):
        source, _graph = self.entry()
        self.session.finish(self.session.acquire('analyze'), {'source': source})
        source_ref = self.migration_result('analyze')[1]['source']
        payload = copy.deepcopy(self.target_payload)
        refs = self.publish({'graph.json': self.read_blob(payload['graph']),
                             'spec.json': self.read_blob(payload['spec'])})
        payload.update(graph=refs['graph.json'], spec=refs['spec.json'])
        target = copy.deepcopy(self.target_envelope)
        target['payload'] = self.publish({'payload.json': payload})['payload.json']
        target_ref = self.publish({'envelope.json': target})['envelope.json']
        work = self.session.acquire('convert')
        return work, {'source': source_ref, 'target': target_ref, 'mapped_evidence': [],
                      'missing_obligations': ['Fresh normal workflow evidence']}, target

    def test_nested_published_target_is_accepted_through_public_submit(self):
        work, conversion, _target = self.prepare()
        result = self.session.finish(work, {'conversion': conversion})
        self.assertEqual('checkpoint', result['next_steps'][0]['kind'])
        self.assertIn('result', result['next_steps'][0])
        self.assertEqual({'conversion_review'}, self.names())

    def test_published_target_bounds_and_integrity_rejected_without_provider_writes(self):
        work, conversion, target = self.prepare()
        valid = conversion['target']
        duplicate = json.dumps(target).replace('"schema_version": 2', '"schema_version": 2, "schema_version": 2').encode()
        cases = [
            ({**valid, 'uri': 'git:HEAD:.zzzops/published/envelope.json'}, 'exact commit'),
            ({**valid, 'uri': f"git:{self.published_head}:../envelope.json"}, 'repository path'),
            ({**valid, 'hash': 'sha256:' + '0' * 64}, 'hash'),
            (self.publish({'duplicate.json': duplicate})['duplicate.json'], 'Duplicate'),
            (self.publish({'oversized.json': b' ' * 1048577})['oversized.json'], 'size bound'),
        ]
        for index, (reference, reason) in enumerate(cases):
            with self.subTest(reason=reason):
                candidate = {**conversion, 'target': reference}
                before = copy.deepcopy((self.provider.issues, self.provider.comments))
                request = self.session.submission(work, {'conversion': candidate}, f'invalid-published-{index}')
                response = self.session.call(100, request, expected=2)
                self.assertIn(reason.lower(), response['next_steps'][0]['reason'].lower())
                self.assertEqual(before, (self.provider.issues, self.provider.comments))


if __name__ == '__main__':
    unittest.main()
