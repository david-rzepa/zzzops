"""G1039: material review rounds, independent stages, and audited historical replay.

Literal replay records were extracted from the immutable source commits named in
fixtures/g1039_round_replays.json. Ordinary CI never depends on historical refs.
"""
import copy
import json
import unittest

import engine_fixtures as fx
from engine import frontier, records, render
from engine.schemas import build_graph
from engine_sim import Sim


class RoundBudgetTests(unittest.TestCase):
    def setUp(self):
        self.graph = build_graph('default', fx.load_template('workflow.json')['graphs']['default'])
        self.settings = copy.deepcopy(fx.load_template('POLICY.json')['settings'])
        self.settings.setdefault('engine', {})['requires'] = ['round_budget']
        self.parts = {'def': 'definition', 'inputs': {'base': 'old', 'code': 'same'}, 'policy': {}}

    def charge(self, node='review_impl', reason='stale', before=None, after=None,
               findings=None, attempt=2, previous=True):
        before = copy.deepcopy(before or self.parts)
        old = {'status': 'done', 'attempt': 1, 'correction_runs': 0,
               'fp_parts': before, 'findings': []} if previous else None
        return frontier.counts(old, reason, before if old else None, after or before,
                               graph=self.graph, node=node, findings=findings or [],
                               attempt=attempt, settings=self.settings)

    def test_material_round_matrix(self):
        cases = [
            ('first material finding', None, [{'id': 'review_impl:1:1', 'target': 'implement'}], 1, 1),
            ('several material findings', True, [{'id': 'review_impl:2:1'}, {'id': 'review_impl:2:2'}], 2, 1),
            ('no findings', True, [], 2, 0),
            ('note', True, [{'id': 'review_impl:2:1', 'material': False}], 2, 0),
            ('carried finding', True, [{'id': 'review_impl:1:1'}], 2, 0),
            ('follow-up', True, [{'id': 'review_impl:2:1', 'follows': 'review_impl:1:1'}], 2, 0),
            ('foreign finding', True, [{'id': 'review_tests:2:1'}], 2, 0),
        ]
        for label, previous, findings, attempt, want in cases:
            with self.subTest(label=label):
                self.assertEqual(want, self.charge(findings=findings, attempt=attempt,
                                                 previous=bool(previous), reason='retry'))
        for node in ('base', 'approve_design', 'run_tests'):
            with self.subTest(kind=node):
                self.assertEqual(0, self.charge(node=node, findings=[{'id': f'{node}:2:1'}]))

    def test_base_only_exemption_requires_no_checkpoint_output(self):
        for node, want in [('review_impl', 0), ('review_tests', 0), ('test_design', 1), ('implement', 1)]:
            before = {'def': 'd', 'inputs': {'base': 'old'}, 'policy': {}}
            after = copy.deepcopy(before)
            after['inputs']['base'] = 'new'
            # review_tests lacks a base selector in graph12: test the generic selector rule
            # using a copied graph with an explicitly base-selecting input.
            wf = fx.load_template('workflow.json')
            wf['graphs']['default']['nodes'][node].setdefault('inputs', {})['base'] = {'from': 'base.base_commit'}
            self.graph = build_graph('default', wf['graphs']['default'])
            with self.subTest(node=node):
                self.assertEqual(want, self.charge(node=node, before=before, after=after,
                                                 findings=[{'id': f'{node}:2:1'}]))
        changed = copy.deepcopy(self.parts)
        changed['inputs'].update(base='new', code='changed')
        self.assertEqual(1, self.charge(after=changed, findings=[{'id': 'review_impl:2:1'}]))

    def test_definition_candidate_lens_and_policy_changes_remain_exempt(self):
        for key in ('def', 'candidates', 'lenses', 'policy'):
            before = {'def': 'old', 'inputs': {}, 'candidates': 'a', 'lenses': 'a', 'policy': {'routing': 'a'}}
            after = copy.deepcopy(before)
            after[key] = {'routing': 'b'} if key == 'policy' else 'b'
            with self.subTest(key=key):
                self.assertEqual(0, self.charge(before=before, after=after,
                                                 findings=[{'id': 'review_impl:2:1'}]))

    def test_record_counts_only_done_agent_submissions_and_keeps_schema(self):
        for status, node, want in [('done', 'review_impl', 1), ('blocked', 'review_impl', 0),
                                  ('done', 'approve_design', 0), ('done', 'base', 0)]:
            with self.subTest(status=status, node=node):
                out = records.record(status, True, 1, 'test:worker', 'new', None, 'fp', self.parts,
                                     {}, [{'id': f'{node}:1:1'}], 1800000000,
                                     graph=self.graph, node=node, settings=self.settings)
                self.assertEqual(want, out['correction_runs'])
                self.assertTrue({'graph', 'node', 'settings'}.isdisjoint(out))

    def test_legacy_four_argument_counting_is_unchanged(self):
        self.assertEqual(0, frontier.counts(None, 'new', None, self.parts))
        self.assertEqual(1, frontier.counts({'status': 'done'}, 'retry', self.parts, self.parts))

    def test_literal_historical_acceptance_replays(self):
        raw = (fx.ROOT / '.agents/fixtures/g1039_round_replays.json').read_bytes()
        replay = json.loads(raw)
        self.assertEqual(54, len(replay['rows']))
        totals = {g: {'discovery': 0, 'delivery': 0} for g in ('1026', '1027')}
        for row in replay['rows']:
            old = row['previous']
            charge = frontier.counts(old, row['reason'], old and old['fp_parts'], row['parts'],
                                     graph=self.graph, node=row['node'], findings=row['findings'],
                                     attempt=row['attempt'], settings=self.settings)
            self.assertIn(charge, (0, 1))
            totals[str(row['goal'])][row['stage']] += charge
            self.assertRegex(row['source_commit'], r'^[0-9a-f]{40}$')
        self.assertEqual({'1026': {'discovery': 3, 'delivery': 4},
                          '1027': {'discovery': 1, 'delivery': 4}}, totals)

    def test_stage_budgets_are_separate_and_trip_at_limit(self):
        sim = Sim()
        sim.settings.setdefault('engine', {})['requires'] = ['round_budget']
        doc = sim.goal(1000)
        sim.drive(1000, until='review_tests')
        # This checks the real portfolio/frontier path with persisted counters.
        for record in doc['records'].values():
            record['correction_runs'] = 0
        doc['records']['review_design']['correction_runs'] = 10
        doc['records']['test_design']['correction_runs'] = 9
        budget = sim.eval().goals[1000].budget
        self.assertEqual(10, budget['limit'])
        self.assertTrue({'used', 'agents', 'over'}.isdisjoint(budget))
        self.assertEqual({'used': 10, 'over': True, 'per_node': {'review_design': 10}}, budget['stages']['discovery'])
        self.assertEqual({'used': 9, 'over': False, 'per_node': {'test_design': 9}}, budget['stages']['delivery'])
        doc['budget'] = 9
        self.assertTrue(sim.eval().goals[1000].budget['stages']['delivery']['over'])
        # Continue's persisted +10 limit applies independently to both stages.
        doc['budget'] = 20
        self.assertFalse(any(s['over'] for s in sim.eval().goals[1000].budget['stages'].values()))

    def test_next_suppresses_only_exhausted_stage_agents_and_continue_adds_ten(self):
        sim = Sim()
        sim.settings.setdefault('engine', {})['requires'] = ['round_budget']
        doc = sim.goal(1000)
        sim.drive(1000, until='review_tests')
        for record in doc['records'].values():
            record['correction_runs'] = 0
        doc['records']['test_design']['correction_runs'] = 10
        portfolio = sim.eval()
        res = portfolio.goals[1000]
        # A snapshot with ready work in both stages and a root operation.
        res.st['design'] = dict(res.st['design'], name='ready', reason='reopened')
        res.st['base'] = dict(res.st['base'], name='ready', reason='stale')
        ctx = render.Ctx('zzzops', sim.now, sim.settings, {'current': True})
        actions, waiting = render.goal_actions(ctx, portfolio, res)
        nodes = {a['node'] for _, a in actions}
        self.assertIn('design', nodes)
        self.assertIn('base', nodes)
        self.assertNotIn('implement', nodes)
        item = render.budget_item(ctx, res, 'implement', True)
        self.assertIn('delivery', item['question'])
        self.assertIn('material findings', item['question'])
        self.assertEqual(20, item['options'][0]['file']['set']['budget'])
        # Reclaim has the same stage gate as a fresh start.
        res.st['implement']['name'] = 'reclaimable'
        actions, _ = render.goal_actions(ctx, portfolio, res)
        self.assertNotIn('implement', {a['node'] for _, a in actions})

    def test_legacy_portfolio_budget_retains_original_shape(self):
        sim = Sim()
        sim.goal(1000)
        budget = sim.eval().goals[1000].budget
        self.assertIn('used', budget)
        self.assertIn('agents', budget)
        self.assertNotIn('stages', budget)


class RoundBudgetCliTests(unittest.TestCase):
    def test_done_finding_trips_only_its_stage_and_start_enforces_the_gate(self):
        import tempfile
        from engine import schemas
        with tempfile.TemporaryDirectory() as tmp:
            wf = fx.load_template('workflow.json')
            source = wf['graphs']['default']['nodes']
            nodes = {n: copy.deepcopy(source[n]) for n in ('design', 'review_design')}
            nodes['design']['inputs'] = {'spec': {'from': 'goal.spec'}}
            nodes['delivery'] = copy.deepcopy(nodes['design'])
            nodes['delivery']['stage'] = 'delivery'
            # A small independent delivery lane proves start is stage specific.
            wf['graphs']['default'] = {'terminal': ['review_design', 'delivery'], 'nodes': nodes}
            policy = fx.load_template('POLICY.json')
            policy['settings']['engine']['requires'] = ['round_budget']
            self.assertEqual([], schemas.validate_workflow(wf, policy))
            world = fx.World(tmp)
            world.bootstrap(workflow=wf, policy=policy)
            goal = world.new()['created']['id']
            tip = world.ok('a', 'show', str(goal), '--json')['goal_commit']
            world.ok('a', 'edit', str(goal), '--set', 'budget=1', '--base', tip)
            writer = fx.Agent(world, 'a', 'codex:test/writer')
            reviewer = fx.Agent(world, 'b', 'codex:test/reviewer')
            card = writer.start(goal, 'design')
            writer.submit(goal, 'design', card, {'summary': 'plan'}, artifact='# Plan\n')
            card = reviewer.start(goal, 'review_design')
            reviewer.submit(goal, 'review_design', card,
                            {'decision': 'changes_requested', 'summary': 'repair',
                             'findings': [{'target': 'design', 'text': 'A concrete missing case.'}]},
                            artifact='# Review\n')
            nxt = world.ok('a', 'next', '--goal', str(goal))
            self.assertNotIn('design', {a['node'] for a in nxt['actions']})
            self.assertIn('delivery', {a['node'] for a in nxt['actions']})
            budget = next(i for i in nxt['needs_human'] if i['kind'] == 'budget')
            self.assertIn('discovery', budget['question'])
            rc, out = writer.start(goal, 'design', ok=False)
            self.assertNotEqual(0, rc)
            self.assertEqual('budget_exceeded', out['error']['code'])
            card = writer.start(goal, 'delivery')
            world.ok('a', 'abandon', str(goal), 'delivery', '--attempt', str(card['lease']['attempt']))
            card = reviewer.start(goal, 'delivery', '--reclaim')
            self.assertEqual(2, card['lease']['attempt'])
