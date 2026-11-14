"""G1039 carry identity: real small Git DAGs, never a second carry algorithm."""
import copy
import tempfile
import unittest
from unittest.mock import patch

import engine_fixtures as fx
from engine import carry
from engine.schemas import build_graph
from engine_sim import Sim
from types import SimpleNamespace
from engine.identity import DIFF, Identity


class CleanSyncIdentityTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = fx.make_repo(tmp.name)
        self.env = fx.env_of(self.repo.env)
        self.env.__enter__()
        self.addCleanup(self.env.__exit__, None, None, None)
        self.git = fx.engine_git(self.repo)
        self.ident = Identity(self.git)
        self.root = self.repo.commit({'seed': b'root\n'}, 'chore: root')

    def commit(self, parent, content, message='test: fixture'):
        self.repo.git('checkout', '-q', '--detach', parent)
        return self.repo.commit({'file.txt': content}, message)

    def dag(self, base, work, onto, result):
        b = self.commit(self.root, base, 'chore: base')
        w = self.commit(b, work, 'test: goal')
        o = self.commit(b, onto, 'chore: trunk')
        resolved = self.commit(w, result, 'test: resolution')
        tree = self.repo.git('rev-parse', resolved + '^{tree}')
        m = self.git.commit_tree(tree, [w, o], f'chore(sync): merge dev into G1000\n\nZzzops-Old-Base: {b}\n')
        return b, w, o, m

    def unchanged(self, dag, scope=None):
        b, w, o, m = dag
        old = {'base': b, 'commit': w, 'change': self.ident.change(b, w)}
        new = {'base': o, 'commit': m, 'change': old['change']}
        return carry.unchanged(self.ident, 'test_design', 'tests', old, new, scope)

    def required(self, name):
        f = getattr(carry, name, None)
        self.assertTrue(callable(f), f'G1039 requires carry.{name}')
        return f

    def test_context_only_trunk_edit_carries_without_changing_stored_u3_identity(self):
        lines = [f'line {i}\n' for i in range(35)]
        goal = lines.copy()
        goal[19] = 'goal changed\n'
        trunk = lines.copy()
        trunk[21] = 'trunk changed\n'
        trunk.insert(0, 'trunk prefix\n')
        merged = trunk.copy()
        merged[20] = 'goal changed\n'
        dag = self.dag(*[''.join(v).encode() for v in (lines, goal, trunk, merged)])
        b, w, o, m = dag
        before = copy.deepcopy(DIFF)
        legacy = self.ident.change(b, w)
        self.assertNotEqual(legacy, self.ident.change(o, m))
        self.assertEqual(legacy, self.ident.change(b, w, unified=3))
        self.assertEqual(self.ident.change(b, w, unified=0), self.ident.change(o, m, unified=0))
        self.assertTrue(self.unchanged(dag, ['file.txt']))
        self.assertEqual(before, DIFF)
        self.assertEqual(legacy, self.ident.change(b, w))

    def test_both_whole_file_union_orders_keep_history_and_code(self):
        union = self.required('union_kept')
        resolved = self.required('resolved_paths')
        for work, onto in [(b'head\ngoal row\ntail\n', b'head\ntrunk row\ntail\n'),
                           (b'head\ngoal_call();\ntail\n', b'head\ntrunk_call();\ntail\n')]:
            for middle in (work.splitlines(keepends=True)[1] + onto.splitlines(keepends=True)[1],
                           onto.splitlines(keepends=True)[1] + work.splitlines(keepends=True)[1]):
                with self.subTest(middle=middle):
                    dag = self.dag(b'head\ntail\n', work, onto, b'head\n' + middle + b'tail\n')
                    self.assertEqual(['file.txt'], resolved(self.ident, dag[3]))
                    self.assertTrue(union(self.ident, dag[3], 'file.txt'))
                    self.assertTrue(self.unchanged(dag))

    def test_interleaved_and_dropped_resolutions_fail_closed(self):
        union = self.required('union_kept')
        for result in (b'head\ngoal1\ntrunk\ngoal2\ntail\n', b'head\ngoal1\ngoal2\ntail\n'):
            with self.subTest(result=result):
                dag = self.dag(b'head\ntail\n', b'head\ngoal1\ngoal2\ntail\n',
                               b'head\ntrunk\ntail\n', result)
                self.assertFalse(union(self.ident, dag[3], 'file.txt'))
                self.assertFalse(self.unchanged(dag))
                # Frozen tests outside this implementation conflict still carry.
                self.assertTrue(self.unchanged(dag, ['seed']))

    def test_moved_goal_line_is_rejected_even_when_u0_matches(self):
        dag = self.dag(b'head\na\nb\nc\nd\ntail\n',
                       b'head\ngoal\na\nb\nc\nd\ntail\n',
                       b'head\ntrunk\na\nb\nc\nd\ntail\n',
                       b'head\ntrunk\na\nb\nc\nd\ngoal\ntail\n')
        b, w, o, m = dag
        self.assertEqual(self.ident.change(b, w, unified=0), self.ident.change(o, m, unified=0),
                         'This fixture must expose the position information lost by U0')
        self.assertFalse(self.unchanged(dag))

    def test_wrong_duplicate_and_mixed_hunk_orders_are_not_a_whole_file_union(self):
        union = self.required('union_kept')
        gap = b''.join(f'gap {i}\n'.encode() for i in range(20))
        cases = [
            (b'head\ncopy\ntail\n' + gap + b'copy\nend\n',
             b'head\ntail\n' + gap + b'copy\nend\n',
             b'head\ntrunk\ntail\n' + gap + b'copy\nend\n',
             b'head\ntrunk\ntail\n' + gap + b'end\n'),
            (b'head\noldA\n' + gap + b'oldB\nend\n',
             b'head\ngoalA\n' + gap + b'goalB\nend\n',
             b'head\ntrunkA\n' + gap + b'trunkB\nend\n',
             b'head\ngoalA\ntrunkA\n' + gap + b'trunkB\ngoalB\nend\n'),
        ]
        for index, values in enumerate(cases):
            dag = self.dag(*values)
            if index == 0:
                self.assertEqual(self.ident.change(dag[0], dag[1], unified=0),
                                 self.ident.change(dag[2], dag[3], unified=0))
            self.assertFalse(union(self.ident, dag[3], 'file.txt'))
            self.assertFalse(self.unchanged(dag))

    def test_missing_versions_and_binary_conflicts_are_conservative(self):
        union = self.required('union_kept')
        for values in [(b'', b'goal\n', None, b'goal\n'),
                       (b'base\n', b'goal\n', None, b'goal\n'),
                       (b'base\n', None, b'trunk\n', b'trunk\n'),
                       (b'base\0\n', b'goal\0\n', b'trunk\0\n', b'goal\0\ntrunk\0\n')]:
            with self.subTest(values=values):
                dag = self.dag(*values)
                self.assertFalse(union(self.ident, dag[3], 'file.txt'))
                self.assertFalse(self.unchanged(dag))

    def test_contained_checkpoint_does_not_recheck_old_conflict(self):
        dag = self.dag(b'head\ntail\n', b'head\ngoal\ntail\n', b'head\ntrunk\ntail\n', b'head\ngoal\ntail\n')
        b, w, o, m = dag
        old = {'base': o, 'commit': m, 'change': self.ident.change(o, m)}
        with patch.object(carry, 'union_kept', create=True, side_effect=AssertionError('contained commit')):
            self.assertTrue(carry.unchanged(self.ident, 'implement', 'code', old, dict(old), None))

    def test_context_sync_carry_loop_preserves_reviews_and_reruns_tree_checks(self):
        lines = [f'line {i}\n' for i in range(35)]
        goal = lines.copy()
        goal[19] = 'goal changed\n'
        trunk = lines.copy()
        trunk[21] = 'trunk changed\n'
        merged = trunk.copy()
        merged[19] = 'goal changed\n'
        b, w, o, m = self.dag(*[''.join(v).encode() for v in (lines, goal, trunk, merged)])
        wf = fx.load_template('workflow.json')
        wf['graphs']['default']['nodes']['review_impl']['inputs']['base'] = {'from': 'base.base_commit'}
        sim = Sim(workflow=wf)
        doc = sim.goal(1000)
        sim.drive(1000, until='approve_design')
        sim.op(1000, 'base', outputs={'base_commit': b, 'branch': 'zzzops/work/g1000', 'stack': []})
        cp = {'base': b, 'commit': w, 'tree': self.ident.code_tree(w), 'change': self.ident.change(b, w)}
        sim.step(1000, 'test_design', outputs={'tests': cp, 'commands': []})
        doc['records']['test_design']['frozen'] = ['file.txt']
        sim.step(1000, 'review_tests')
        sim.step(1000, 'implement', outputs={'code': cp, 'summary': 'goal'})
        sim.step(1000, 'run_tests')
        sim.step(1000, 'review_impl')
        before = copy.deepcopy(doc['records'])
        base_record = copy.deepcopy(doc['records']['base'])
        base_record['output'].update(base_commit=o, replay_map={}, replay_pos={}, synced={
            'old': b, 'onto': o, 'work': w, 'tip': m, 'merge': m, 'resolved': []})
        nodes = carry.carry_forward(SimpleNamespace(git=self.git), sim.graph(1000), doc,
                                    'base', base_record, None, {})
        self.assertEqual(['test_design', 'implement'], nodes)
        doc['records']['base'] = base_record
        for node, key in [('test_design', 'tests'), ('implement', 'code')]:
            record = doc['records'][node]
            self.assertEqual('base', record['carried_by'])
            self.assertEqual(m, record['output'][key]['commit'])
            self.assertEqual(cp['change'], record['output'][key]['change'])
            self.assertEqual(before[node]['correction_runs'], record['correction_runs'])
        self.assertEqual(['file.txt'], doc['records']['test_design']['frozen'])
        for node in ('design', 'review_design', 'approve_design', 'review_tests'):
            self.assertEqual('current', sim.st(1000, node)['name'], node)
        self.assertEqual('ready', sim.st(1000, 'run_tests')['name'])
        sim.step(1000, 'run_tests')
        review = sim.st(1000, 'review_impl')
        self.assertEqual('ready', review['name'])
        self.assertEqual(['inputs.base'], review['stale_because'])

    def test_nonmerge_and_clean_merge_have_no_edited_resolution_paths(self):
        resolved = self.required('resolved_paths')
        dag = self.dag(b'a\nb\nc\nd\ne\nf\ng\nh\ni\n',
                       b'goal\nb\nc\nd\ne\nf\ng\nh\ni\n',
                       b'a\nb\nc\nd\ne\nf\ng\nh\ntrunk\n',
                       b'goal\nb\nc\nd\ne\nf\ng\nh\ntrunk\n')
        self.assertEqual([], resolved(self.ident, dag[1]))
        self.assertEqual([], resolved(self.ident, dag[3]))
        # Repeated frozen scopes share the same merge-tree calculation.
        with patch.object(self.git, 'run', wraps=self.git.run) as run:
            resolved(self.ident, dag[3])
            resolved(self.ident, dag[3])
        self.assertFalse(any('merge-tree' in c.args for c in run.call_args_list))
