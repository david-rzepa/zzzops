"""Git-backed workspace identity at the public fresh-goal boundary."""

import json
import copy

from test_evidence_dag_journeys import DagFixture, z
from test_workflow_journey import fixtures


class FreshGoalGitCheckpointTests(DagFixture):
    def default_graph(self):
        template = json.loads((fixtures.PLUGIN_ROOT / 'zzzops/templates/project-goals/INIT_PLAN.json').read_text())
        self.install(z._workflow_section(template, 'workflow_adherence')['configuration']['phase_dag'])

    def test_first_acquisition_with_many_files_is_bounded_and_replayable(self):
        paths = self.fixture.repo / 'many'
        paths.mkdir()
        for index in range(624):
            (paths / f'fixture_{index:04d}.txt').write_text(f'file {index}\n')
        self.session.git('add', 'many')
        self.session.git('commit', '-qm', 'fresh repository with many files')
        self.default_graph()

        work = self.session.acquire('requirements')
        acquisition = work['lease']['acquisition']
        self.assertEqual(self.session.git('rev-parse', 'HEAD').strip(), acquisition['read_commit'])
        self.assertNotIn('files', acquisition)
        self.assertNotIn('read_files', acquisition)
        self.assertTrue(all(len(comment['body']) <= 65536 for comment in self.provider.comments[100]))

        request = self.session.submission(work, {'value': {
            'statements': ['Preserve the fresh goal evidence.'], 'questions': [],
            'investigations': {'items': {}, 'rationale': 'No unknowns.'},
        }}, 'fresh-git-checkpoint-result')
        first = self.session.call(100, request)
        comments = len(self.provider.comments[100])
        second = self.session.call(100, request)
        self.assertEqual(first, second)
        self.assertEqual(comments, len(self.provider.comments[100]))
        self.assertEqual([100], sorted(self.provider.issues))
        self.assertEqual(1, len(self.payload()[1]['evidence']))
        next_work = self.session.acquire('spec')
        self.assertEqual(acquisition['read_commit'], next_work['lease']['acquisition']['read_commit'])
        self.assertTrue(all(len(comment['body']) <= 65536 for comment in self.provider.comments[100]))

    def test_moved_commit_cannot_accept_a_readonly_result(self):
        self.default_graph()
        work = self.session.acquire('requirements')
        (self.fixture.repo / 'product.txt').write_text('changed after acquisition\n')
        self.session.git('add', 'product.txt')
        self.session.git('commit', '-qm', 'move the input commit')
        before = copy.deepcopy((self.provider.issues, self.provider.comments))
        request = self.session.submission(work, {'value': {
            'statements': ['Stale evidence must be rejected.'], 'questions': [],
            'investigations': {'items': {}, 'rationale': 'No unknowns.'},
        }}, 'stale-commit-result')
        response = self.session.call(100, request, expected=2)
        self.assertIn('Git commit changed', json.dumps(response))
        self.assertEqual(before, (self.provider.issues, self.provider.comments))

    def test_same_tree_new_commit_keeps_readonly_evidence_current(self):
        self.default_graph()
        work = self.session.acquire('requirements')
        pinned = work['lease']['acquisition']['read_commit']
        self.session.git('commit', '--allow-empty', '-qm', 'ancestry only')
        self.assertNotEqual(pinned, self.session.git('rev-parse', 'HEAD').strip())
        request = self.session.submission(work, {'value': {
            'statements': ['Ancestry-only movement retains this evidence.'], 'questions': [],
            'investigations': {'items': {}, 'rationale': 'No unknowns.'},
        }}, 'equivalent-tree-result')
        self.session.call(100, request)
        self.assertEqual(1, len(self.payload()[1]['evidence']))
        next_work = self.session.acquire('spec')
        self.assertEqual(self.session.git('rev-parse', 'HEAD').strip(),
                         next_work['lease']['acquisition']['read_commit'])


if __name__ == '__main__':
    import unittest
    unittest.main()
