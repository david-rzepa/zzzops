"""G1039 sync cards: bounded previews and composable shrink, with real Git evidence."""
import copy
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import engine_fixtures as fx
import merge_sync_fixtures as msf
import test_engine_card_budget as cb
from engine import card as C, render
from engine.schemas import build_graph
from engine_sim import Sim


class SyncShrinkTests(unittest.TestCase):
    def card(self):
        c = cb.pre_card('review_impl', previous={'unchanged': 'previous ' * 700})
        c['sync'] = {'from': cb.h('old'), 'to': cb.h('new'), 'commits': 2, 'files': 40,
                     'touching': [{'path': 'tests/' + str(i) + '.py', 'why': 'shared file ' * 20} for i in range(12)],
                     'more': 28, 'all': cb.READER.blob_view('all paths ' * 100),
                     'diff': 'git diff old new -- tests', 'log': 'git log --oneline --first-parent old..new'}
        return c

    def test_touching_blob_is_size_sorted_and_fold_follows_all_blobs(self):
        c = self.card()
        steps = C._steps(c)
        touch = ('blob', 'sync', 'touching')
        self.assertIn(touch, steps)
        self.assertNotIn(('fold', 'sync'), steps)
        c = C._apply(c, touch, cb.READER)
        steps = C._steps(c)
        self.assertIn(('fold', 'sync'), steps)
        self.assertTrue(all(steps.index(s) < steps.index(('fold', 'sync')) for s in steps if s[0] == 'blob'))
        folded = C._apply(c, ('fold', 'sync'), cb.READER)
        self.assertEqual({'from', 'to', 'diff', 'log', 'detail'}, set(folded['sync']))
        self.assertIn('blob', folded['sync']['detail'])
        self.assertNotIn(('fold', 'sync'), C._steps(folded))

    def test_shrink_is_monotone_and_fixed_with_large_previous_and_final_80_preview(self):
        c = self.card()
        c['context']['long_preview'] = cb.READER.blob_view('x' * 350)
        old = copy.deepcopy(c)
        out = C.shrink(c, cb.READER)
        self.assertLessEqual(cb.size(out), cb.size(old))
        self.assertEqual({'from', 'to', 'diff', 'log', 'detail'}, set(out['sync']))
        self.assertEqual(old['previous'], out['previous'])
        self.assertEqual(out, C.shrink(copy.deepcopy(out), cb.READER))
        self.assertLessEqual(len(out['context']['long_preview']['summary']), 80)
        self.assertNotIn(('fold', 'sync'), C.shrink_candidates(out))

    def test_small_sync_card_remains_inline(self):
        c = {'sync': {'from': 'a', 'to': 'b', 'touching': [], 'diff': 'd', 'log': 'l'}}
        self.assertEqual(c, C.shrink(copy.deepcopy(c), cb.READER))


class SyncCardTests(msf.OpFixture):
    def test_real_diffs_prioritize_hand_resolutions_and_semantic_hits_and_cap_at_twelve(self):
        # One tiny Git world serves the actual card builder, not a standalone heuristic clone.
        wf = fx.load_template('workflow.json')
        wf['graphs']['default']['nodes']['review_impl']['inputs']['base'] = {'from': 'base.base_commit'}
        graph = build_graph('default', wf['graphs']['default'])
        names = [f'src/file{i:02d}.py' for i in range(40)]
        before = self.publish({p: b'old_call();\n' for p in names}, 'test: common files')
        # Publish the common file inventory as trunk's starting point.
        self.w.seed.git('fetch', '-q', 'origin', 'zzzops/work/g1000')
        self.w.seed.git('merge', '--ff-only', 'FETCH_HEAD')
        trunk_files = {p: b'trunk_call();\n' for p in names}
        trunk_files[names[0]] = b'old_call();\nnewName();\n'
        onto = self.trunk(trunk_files)
        goal_files = {p: b'trunk_call();\ngoal_call();\n' for p in names}
        goal_files[names[0]] = b'old_call();\ngoal_call();\n'
        current = self.publish(goal_files, 'feat: goal lines')
        old = {'base': before, 'commit': before, 'change': self.ident.change(before, before)}
        new = {'base': onto, 'commit': current, 'change': self.ident.change(onto, current)}
        sim = Sim(workflow=wf)
        doc = sim.goal(1000)
        sim.drive(1000, until='review_impl')
        doc['records']['review_impl']['reviewed'] = {'code': old}
        doc['records']['implement']['output']['code'] = new
        doc['records']['base']['output']['base_commit'] = onto
        doc['records']['base']['output']['synced'] = {
            'old': before, 'onto': onto, 'work': before, 'tip': current,
            'merge': current, 'resolved': [names[-1]]}
        res = sim.eval().goals[1000]
        reader = render.Reader()
        reader.prompt = lambda n: ''
        reader.human_decisions = lambda *a: []
        reader.diffstat = lambda *a: None
        reader.blob_view = lambda text: cb.READER.blob_view(text)
        ctx = render.Ctx('zzzops', sim.now, sim.settings, {'current': True}, reader=reader)
        session = SimpleNamespace(git=self.git, settings=sim.settings,
                                  state=SimpleNamespace(policy={'instructions': {}}, coordinator={'current': True}),
                                  snap=SimpleNamespace(integration=onto, goals={}),
                                  ctx=lambda **kw: ctx, portfolio=lambda: sim.eval(),
                                  mirror_path=lambda: self.repo.path, fetch_work_of=lambda g: None)
        state = dict(res.st['review_impl'], stale_because=['inputs.base'], record_stale=['inputs.base'],
                     parts=doc['records']['review_impl']['fp_parts'])
        lease = {'timeout': 120, 'attempt': 2, 'holder': 'test:review', 'expires_at': sim.now + 7200,
                 'card_reason': 'stale', 'workspace': None, 'parts': state['parts']}
        # Inspect build's bounded inline section before the separately tested shrink pipeline.
        with patch.object(C, 'shrink', side_effect=lambda card, reader: card):
            card = C.build(session, res, 'review_impl', state, lease)
        self.assertIn('sync', card)
        sync = card['sync']
        self.assertEqual((before, onto), (sync['from'], sync['to']))
        self.assertEqual(40, sync['files'])
        self.assertEqual(1, sync['commits'])
        self.assertNotIn('ask', sync)
        # This fixture is small enough to retain the bounded 12-entry inline list.
        self.assertEqual(12, len(sync['touching']))
        self.assertEqual(names[-1], sync['touching'][0]['path'])
        self.assertIn('resolved by hand', sync['touching'][0]['why'])
        self.assertEqual(28, sync['more'])
        self.assertIn('blob', sync['all'])
        self.assertIn('--first-parent', sync['log'])
        self.assertIn(':(top,exclude).zzzops/reviews', sync['diff'])
        self.assertEqual(names[0], sync['touching'][1]['path'])
        self.assertIn('newName', sync['touching'][1]['why'])


class SyncTemplateTests(unittest.TestCase):
    def test_review_impl_base_is_fingerprinted_but_test_review_and_filter_are_unchanged(self):
        wf = json.loads((fx.SHIPPED / 'workflow.json').read_text())
        nodes = wf['graphs']['default']['nodes']
        self.assertEqual({'from': 'base.base_commit'}, nodes['review_impl']['inputs'].get('base'))
        self.assertNotIn('base', nodes['review_tests']['inputs'])
        self.assertNotIn('base', nodes['filter_impl']['inputs'])
        self.assertIn('After a trunk sync', (fx.SHIPPED / 'prompts/review.md').read_text())
