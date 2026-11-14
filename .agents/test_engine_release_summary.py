"""Release progress is derived from the real frontier and immutable Git line records."""
from __future__ import annotations

import copy
import unittest

import engine_fixtures as fx
import test_engine_branching as branching
from engine import render
from engine.canon import canonical


class ReleaseSummaryTests(unittest.TestCase):
    def setUp(self):
        self.s = branching.BSim()
        self.s.line(9000)
        self.head = 'b' * 40

    def nxt(self, **kw):
        ctx = render.Ctx(prefix='zzzops', now=self.s.now, settings=self.s.settings,
                         coordinator={'commit': 'a' * 40, 'current': True},
                         targets={'release/1': self.head, 'main': 'c' * 40})
        ctx.goal_docs = self.s.docs
        return render.render_next(ctx, self.s.eval(), **kw)

    def summary(self, **kw):
        return self.nxt(**kw)['releases']['summaries'][0]

    def synced(self):
        self.s.answer(9000, 'approve_start')
        self.s.op(9000, 'sync', outputs={'merged': self.head, 'merge_commit': None})

    def test_counts_include_late_and_held_members_but_exclude_other_lines(self):
        self.s.goal(1)
        self.s.close(1)
        self.s.goal(2)
        self.s.close(2, 'cancelled')
        self.s.goal(3, state='held')
        self.s.goal(4)
        self.s.goal(5, release=2)
        other = self.s.goal(6)
        other.update(schema=2, flow={'hotfix': 'urgent'})
        out = self.summary()
        self.assertEqual({'total': 4, 'done': 1, 'closed_other': 1, 'open': 1, 'held': 1}, out['members'])
        self.assertEqual([3, 4], [m['goal'] for m in out['unfinished']])
        self.assertEqual((self.head, 'main'), (out['head'], out['target']))
        self.assertEqual('next --goal 4', out['unfinished'][1]['expand']['command'].split('zzzops ')[1])

    def test_existing_approval_and_finish_actions_are_visible_and_pause_removes_actions(self):
        self.synced()
        out = self.summary()
        self.assertEqual('needs_human', next(x for x in out['workflow'] if x['node'] == 'approve_finish')['state'])
        self.assertTrue(any(x['goal'] == 9000 and x['node'] == 'approve_finish' for x in out['next']))
        self.s.answer(9000, 'approve_finish')
        out = self.summary()
        self.assertTrue(any(x['goal'] == 9000 and x['node'] == 'finish' for x in out['next']))
        self.assertEqual([], self.summary(paused=True)['next'])

    def test_timed_external_block_keeps_its_reason_and_retry_time(self):
        self.synced()
        self.s.answer(9000, 'approve_finish')
        self.s.start(9000, 'finish')
        self.s.blocked(9000, 'finish', waiting_for='time', category='external', reason='required checks pending', delay=300)
        out = self.summary()
        self.assertTrue(any('required checks pending' in x['reason'] for x in out['blockers']), out)
        self.assertTrue(any(x.get('until', '').startswith('20') for x in out['blockers']), out)

    def test_missing_line_branch_is_explained_in_summary(self):
        self.head = None
        out = self.summary()
        self.assertTrue(any(x.get('item_kind') == 'line_branch_missing' for x in out['blockers']), out)

    def test_policy_pause_explains_why_next_actions_are_suppressed(self):
        out = self.summary(paused=True, blockers=[{'kind': 'policy_branch', 'message': 'Policy review pending'}])
        self.assertEqual([], out['next'])
        self.assertTrue(any(x.get('item_kind') == 'policy_branch' for x in out['blockers']), out)

    def test_closing_without_finish_evidence_does_not_claim_publication(self):
        self.s.close(9000)
        self.assertEqual('unknown', self.summary()['publication']['state'])

    def test_recorded_publication_survives_closure_and_carries_back_merge_evidence(self):
        self.synced()
        self.s.answer(9000, 'approve_finish')
        self.s.op(9000, 'finish', outputs={'production_merge': 'd' * 40, 'back_merges': {'dev': 'e' * 40}})
        self.s.close(9000)
        out = self.summary()
        self.assertEqual({'state': 'published', 'merge_commit': 'd' * 40, 'back_merges': {'dev': 'e' * 40}}, out['publication'])
        self.assertEqual([], out['next'])

    def test_malformed_back_merge_evidence_is_unknown_without_breaking_next(self):
        self.synced()
        self.s.answer(9000, 'approve_finish')
        self.s.op(9000, 'finish', outputs={'production_merge': 'd' * 40, 'back_merges': 'invalid'})
        self.s.close(9000)
        out = self.summary()
        self.assertEqual('published', out['publication']['state'])
        self.assertIsNone(out['publication']['back_merges'])

    def test_portfolio_blocker_expands_to_unscoped_next(self):
        self.head = None
        ref = next(x for x in self.summary()['next'] if x['item_kind'] == 'line_branch_missing')
        self.assertEqual(['next', '--all'], ref['expand']['argv'])
        expanded = self.nxt(all_=True)
        self.assertTrue(any(x['kind'] == 'line_branch_missing' for x in expanded['needs_human']))

    def test_closed_line_retains_recorded_workflow_progress(self):
        self.synced()
        self.s.close(9000, 'cancelled')
        steps = {x['node']: x['state'] for x in self.summary()['workflow']}
        self.assertEqual('done', steps['sync'])
        self.assertEqual('not_recorded', steps['finish'])

    def test_summary_references_do_not_duplicate_authoritative_decision_kinds(self):
        self.s.line(9001)
        out = self.nxt(all_=True)
        self.assertEqual(1, len(branching.find_kind(out, 'duplicate_line')))

    def test_same_named_hotfix_and_release_have_separate_summaries(self):
        self.s.line(9001, kind='hotfix', name='1')
        out = self.nxt()['releases']['summaries']
        self.assertEqual({('release', '1'), ('hotfix', '1')}, {(x['kind'], x['name']) for x in out})

    def test_summary_detail_does_not_hide_actions_and_all_keeps_full_membership(self):
        for g in range(1, 70):
            self.s.goal(g, state='held')
        before = copy.deepcopy(self.s.docs)
        out = self.nxt()
        self.assertLessEqual(len(canonical(out)), render.NEXT_LIMIT)
        self.assertTrue(any(x.get('goal') == 9000 for x in out['needs_human']), out)
        self.assertEqual(69, len(self.summary(all_=True)['unfinished']))
        self.assertEqual(before, self.s.docs)


class ReleaseSummaryCliTests(branching.Branching):
    def test_fresh_next_reports_finished_merge_without_writing_remote_refs(self):
        _, line = self.cut_release_1()
        self.op(line, 'sync')
        self.approve(line, 'approve_finish')
        self.op(line, 'finish')
        refs = self.w.remote_git('for-each-ref', '--format=%(refname) %(objectname)')
        out = self.nxt(clone='b')
        summary = next(x for x in out['releases']['summaries'] if x['goal'] == line)
        self.assertEqual('published', summary['publication']['state'])
        self.assertEqual(self.tip('main'), summary['publication']['merge_commit'])
        self.assertEqual(1, summary['members']['done'])
        self.assertEqual(refs, self.w.remote_git('for-each-ref', '--format=%(refname) %(objectname)'))

    def test_late_correction_is_visible_in_unscoped_next(self):
        _, line = self.cut_release_1()
        correction = self.goal(release=1)
        out = self.nxt()
        summary = next(x for x in out['releases']['summaries'] if x['goal'] == line)
        self.assertEqual([correction], [x['goal'] for x in summary['unfinished']])
        self.assertEqual('not_recorded', summary['publication']['state'])


if __name__ == '__main__':
    unittest.main()
