"""Disposable #498 design probe. In-memory synthetic evidence, no provider I/O.

Not a production schema or security boundary. Agents/authorities are fixture IDs.
Collections are authoritative input snapshots, not arbitrary executable scripts.
"""
import copy
import hashlib
import json
import unittest
from dataclasses import dataclass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


@dataclass(frozen=True)
class Node:
    inputs: tuple = ()
    needs: tuple = ()
    joins: tuple = ()
    independent: bool = False
    gate: bool = False
    capability: str = 'base'
    root_only: bool = False
    permits: tuple = ()  # (typed decision, exact target scope); reviewed configuration


class Model:
    def __init__(self, nodes, inputs):
        self.nodes = dict(nodes)
        self.inputs = copy.deepcopy(inputs)
        self.results = {}
        self.findings = {}
        self.finding_history = {}
        self.withdrawals = {}
        self.retirements = set()
        self.resolutions = {}
        self.members = {}
        self.generations = {}
        self.expansion_sources = {}
        self.output_values = {}
        self.capabilities = {'base'}
        self.evidence = {}  # accepted immutable result evidence, insertion ordered
        self.receipts = {}  # operational replay protection, not semantic inputs
        self.history = []
        self.validate()

    def validate(self):
        def visit(name, path):
            if name in path:
                raise ValueError('cycle')
            if name not in self.nodes:
                raise ValueError('missing node')
            dependencies = list(self.dependencies(self.nodes[name]) or ())
            dependencies += [source for group, (source, _) in self.expansion_sources.items()
                             if name in self.members.get(group, ())]
            for dep in dependencies:
                visit(dep, path + (name,))
        for name in self.nodes:
            visit(name, ())

    def _expand(self, collection, items, template, expected=None):
        # Stable per-item identity/input: adding B does not rerun unchanged A.
        if expected is not None and expected != self.collection_version(collection):
            raise ValueError('stale collection revision')
        if any(not key or '/' in key for key in items):
            raise ValueError('invalid instance identity')
        previous = self.members.get(collection, ())
        current = tuple(sorted(f'{collection}/{key}' for key in items))
        for name in set(previous) - set(current):
            if any(f['target'] == name and not self.resolved(key)
                   for key, f in self.findings.items()):
                if (name, self.generations[name]) not in self.retirements:
                    raise ValueError('cannot retire unresolved work')
        original = copy.deepcopy((self.inputs, self.nodes, self.members, self.generations))
        try:
            for key, value in items.items():
                name = f'{collection}/{key}'
                if name not in previous:
                    self.generations[name] = self.generations.get(name, 0) + 1
                self.inputs[name] = copy.deepcopy(value)
                self.nodes[name] = Node(inputs=(name,), **template)
            self.members[collection] = current
            self.validate()
        except ValueError:
            self.inputs, self.nodes, self.members, self.generations = original
            raise

    def collection_version(self, collection):
        return digest({name: self.inputs[name] for name in self.members.get(collection, ())})

    def expand_from(self, collection, source, template):
        self.expansion_sources[collection] = (source, template)
        self.refresh_expansions()

    def refresh_expansions(self):
        for collection, (source, template) in self.expansion_sources.items():
            if self.current(source):
                manifest = self.output_values[source]
                if (not isinstance(manifest, dict) or set(manifest) != {'items', 'rationale'}
                        or not isinstance(manifest['items'], dict) or not manifest['rationale']):
                    raise ValueError('selection requires explicit items and rationale')
                self._expand(collection, manifest['items'], template)

    def active(self, name):
        return all(name not in self.nodes or not name.startswith(group + '/')
                   or name in members for group, members in self.members.items())

    def dependencies(self, node):
        deps = list(node.needs)
        for group in node.joins:
            if group not in self.members:
                return None
            if group in self.expansion_sources and not self.current(self.expansion_sources[group][0]):
                return None
            deps.extend(self.members[group])
        return deps

    def fingerprint(self, name, path=()):
        cache = getattr(self, '_evaluation_cache', None)
        if cache is None:
            return self._fingerprint(name, path)
        if name not in cache:
            cache[name] = self._fingerprint(name, path)
        return cache[name]

    def _fingerprint(self, name, path=()):
        if name in path:
            raise ValueError('cycle')
        node = self.nodes[name]
        for group, (source, _) in self.expansion_sources.items():
            if name in self.members.get(group, ()) and not self.current(source):
                return None
        if node.gate and any(f['target'] in self.ancestors(name) and not self.resolved(key)
                             for key, f in self.findings.items()):
            return None
        if not self.active(name):
            return None
        if any(key not in self.inputs for key in node.inputs):
            return None
        deps = self.dependencies(node)
        if deps is None:
            return None
        upstream = {}
        for dep in deps:
            expected = self.fingerprint(dep, path + (name,))
            result = self.results.get(dep)
            if expected is None or not result or result['input'] != expected:
                return None
            upstream[dep] = ({'output': result['output'], 'generation': self.generations.get(dep, 1)}
                             if node.independent else result['output'])
        corrections = {key: f for key, f in self.findings.items() if f['target'] == name
                       and f['generation'] == self.generations.get(name, 1)
                       and self.withdrawals.get(key) != digest(f)}
        # Resolution bookkeeping intentionally absent from producer inputs.
        return digest({'contract': node.__dict__, 'generation': self.generations.get(name),
                       'inputs': {k: self.inputs[k] for k in node.inputs},
                       'upstream': upstream, 'corrections': corrections})

    def ancestors(self, name):
        seen = set()
        def scoped_dependencies(item):
            node = self.nodes[item]
            return list(self.dependencies(node) or ()) + [old for old in self.generations
                    if any(old.startswith(group + '/') for group in node.joins)]
        pending = scoped_dependencies(name)
        while pending:
            item = pending.pop()
            if item in seen:
                continue
            seen.add(item)
            pending.extend(scoped_dependencies(item))
        return seen

    def current(self, name):
        fingerprint = self.fingerprint(name)
        return fingerprint is not None and self.results.get(name, {}).get('input') == fingerprint

    def ready(self):
        self._evaluation_cache = {}  # one immutable evaluation only; never cross writes
        try:
            return sorted(name for name, node in self.nodes.items()
                          if node.capability in self.capabilities
                          and self.fingerprint(name) is not None and not self.current(name))
        finally:
            del self._evaluation_cache

    def begin(self, name):
        if name not in self.ready():
            raise ValueError('not ready')
        return self.fingerprint(name)

    def _finish(self, name, token, value, actor='worker'):
        if name not in self.ready() or token != self.fingerprint(name):
            raise ValueError('stale attempt')
        if self.nodes[name].root_only and actor != 'root':
            raise ValueError('root-only action')
        if self.nodes[name].independent:
            if any(self.results[d]['actor'] == actor for d in self.dependencies(self.nodes[name])):
                raise ValueError('self review')
        record = {'input': token, 'output': digest(value), 'actor': actor}
        self.results[name] = record
        self.output_values[name] = copy.deepcopy(value)
        self.history.append((name, copy.deepcopy(record), copy.deepcopy(value)))

    def run(self, name, value, actor='worker'):
        self.submit(name, self.begin(name), value, actor)

    def submit(self, name, token, value, actor='worker', decisions=(), request=None):
        """Only acceptance path. Fixture actor is authenticated by the host in production.

        Validate an isolated candidate, then publish its complete evidence bundle.
        Decision types are closed contracts, not scripts or arbitrary field writes.
        """
        payload = digest([name, token, value, actor, decisions])
        request = request or 'attempt_' + str(len(self.evidence))
        if request in self.receipts:
            prior, ref = self.receipts[request]
            if prior != payload:
                raise ValueError('conflicting request replay')
            return ref
        candidate = copy.deepcopy(self)
        candidate._finish(name, token, value, actor)
        accepted = []
        for decision in decisions:
            if not isinstance(decision, dict) or set(decision) != {'kind', 'scope', 'args'}:
                raise ValueError('invalid decision record')
            kind, scope, args = decision['kind'], decision['scope'], decision['args']
            if (kind, scope) not in self.nodes[name].permits:
                raise ValueError('undeclared output type or scope')
            if kind == 'admit':
                key, target, subject, change = args
                if target != scope: raise ValueError('scope mismatch')
                # Applicability is checked against the acquired pre-bundle state.
                # Other admissions must not make this inspected subject look late.
                inspected = copy.deepcopy(self)
                inspected._correct(key, target, subject, change, actor)
                finding = inspected.findings[key]
                # Combined revisions still must agree in the prospective state.
                if key in candidate.findings and candidate.findings[key] != finding:
                    raise ValueError('conflicting findings within bundle')
                candidate.findings[key] = copy.deepcopy(finding)
                accepted.append({'kind': kind, 'key': key, 'finding': copy.deepcopy(candidate.findings[key])})
            elif kind == 'replace':
                key, expected, change, coverage, reason, generation = args
                if candidate.findings[key]['target'] != scope: raise ValueError('scope mismatch')
                candidate._supersede(key, expected, change, actor, coverage, reason, generation)
                accepted.append({'kind': kind, 'key': key, 'finding': copy.deepcopy(candidate.findings[key])})
            elif kind == 'withdraw':
                key, expected, reason = args
                if candidate.findings[key]['target'] != scope: raise ValueError('scope mismatch')
                candidate._withdraw(key, expected, actor, reason)
                accepted.append({'kind': kind, 'key': key, 'finding_hash': expected})
            elif kind == 'retire':
                target, reason = args
                if target != scope: raise ValueError('scope mismatch')
                candidate._authorize_retirement(target, actor, reason)
                accepted.append({'kind': kind, 'target': target, 'generation': candidate.generations[target]})
            elif kind == 'resolve':
                key, review = args
                if candidate.findings[key]['target'] != scope: raise ValueError('scope mismatch')
                if actor != candidate.results[review]['actor']:
                    raise ValueError('resolution must be submitted by its reviewer')
                candidate._resolve(key, review)
                accepted.append({'kind': kind, 'key': key, 'resolution': copy.deepcopy(candidate.resolutions[key])})
            else:
                raise ValueError('unsupported decision type')
        candidate.refresh_expansions()  # prospective membership/cycle validation
        selections = {group: {'items': copy.deepcopy(candidate.output_values[source]['items']),
                              'template': copy.deepcopy(template)}
                      for group, (source, template) in candidate.expansion_sources.items()
                      if candidate.current(source)}
        result = copy.deepcopy(candidate.results[name])
        event = {'type': 'result', 'node': name,
                 'generation': candidate.generations.get(name, 1),
                 'attempt': request, 'contract': digest(self.nodes[name].__dict__),
                 'result': result, 'value': copy.deepcopy(value), 'accepted': accepted,
                 'selections': selections}
        ref = digest(event)
        candidate.evidence[ref] = event
        candidate.receipts[request] = (payload, ref)
        self.__dict__.update(candidate.__dict__)
        return ref

    def finish(self, name, token, value, actor='worker'):
        return self.submit(name, token, value, actor)

    def rebuild(self):
        """Rebuild disposable indexes from previously accepted evidence, not imports.

        Acceptance is a host trust boundary. A dict supplied by a caller is NOT a
        result import API. Membership/inputs are derived from current graph/evidence.
        """
        self.results, self.output_values, self.history = {}, {}, []
        self.findings, self.finding_history = {}, {}
        self.resolutions, self.withdrawals, self.retirements = {}, {}, set()
        self.members, self.generations = {}, {}
        for ref, event in self.evidence.items():
            if digest(event) != ref: raise ValueError('corrupt accepted evidence')
            name, record, value = event['node'], event['result'], event['value']
            self.results[name] = copy.deepcopy(record)
            self.output_values[name] = copy.deepcopy(value)
            self.history.append((name, copy.deepcopy(record), copy.deepcopy(value)))
            for fact in event['accepted']:
                kind = fact['kind']
                if kind in ('admit', 'replace'):
                    key = fact['key']
                    if kind == 'replace':
                        self.finding_history.setdefault(key, []).append(copy.deepcopy(self.findings[key]))
                        self.resolutions.pop(key, None); self.withdrawals.pop(key, None)
                    self.findings[key] = copy.deepcopy(fact['finding'])
                elif kind == 'withdraw': self.withdrawals[fact['key']] = fact['finding_hash']
                elif kind == 'retire': self.retirements.add((fact['target'], fact['generation']))
                elif kind == 'resolve': self.resolutions[fact['key']] = copy.deepcopy(fact['resolution'])
            for group, selection in event['selections'].items():
                self._expand(group, selection['items'], selection['template'])
        # Accepted corrections remain effective even if their emitting task is stale.
        # Review resolution is still checked against current subjects by resolved().
        self.refresh_expansions()

    def _correct(self, key, target, subject, change, authority='root'):
        if authority != 'root':
            raise ValueError('unadmitted correction')
        if target not in self.nodes or not any(n == target and r['output'] == subject for n, r, _ in self.history):
            raise ValueError('unknown subject')
        finding = {'target': target, 'generation': self.generations.get(target, 1),
                   'revision': 1, 'subject': subject, 'change': copy.deepcopy(change)}
        if key in self.findings:
            if self.findings[key] != finding:
                raise ValueError('conflicting retry')
            return
        if not self.current(target) or self.results[target]['output'] != subject:
            raise ValueError('late finding needs explicit applicability assessment')
        self.findings[key] = finding

    def _supersede(self, key, expected, change, authority, coverage, reason, generation=None):
        old = self.findings[key]
        if authority != 'root' or coverage not in {'carried', 'narrowed'} or not reason:
            raise ValueError('authorized coverage disposition required')
        if expected != digest(old):
            raise ValueError('conflicting revision')
        generation = generation or old['generation']
        if generation != self.generations.get(old['target'], 1):
            raise ValueError('target generation unavailable')
        new = {**copy.deepcopy(old), 'revision': old['revision'] + 1,
               'generation': generation, 'change': copy.deepcopy(change),
               'supersedes': expected, 'coverage': coverage, 'coverage_reason': reason}
        # One atomic in-memory admission; production uses cooperative write ownership.
        self.finding_history.setdefault(key, []).append(copy.deepcopy(old))
        self.findings[key] = new
        self.resolutions.pop(key, None)
        self.withdrawals.pop(key, None)

    def _withdraw(self, key, expected, authority, reason):
        if authority != 'root' or not reason or expected != digest(self.findings[key]):
            raise ValueError('authorized exact withdrawal required')
        self.withdrawals[key] = expected

    def _authorize_retirement(self, name, authority, reason):
        if authority != 'root' or not reason:
            raise ValueError('authorized retirement required')
        self.retirements.add((name, self.generations[name]))

    def exact_member(self, expansion, item, generation):
        name = f'{expansion}/{item}'
        if type(generation) is not int or not 1 <= generation <= self.generations.get(name, 0):
            raise ValueError('unknown member generation')
        return {'kind': 'member', 'goal': 498, 'expansion': expansion,
                'item': item, 'generation': generation}

    def _resolve(self, key, review):
        target = self.findings[key]['target']
        if self.findings[key]['generation'] != self.generations.get(target, 1):
            raise ValueError('resolution subject generation requires explicit transfer')
        if not self.current(target) or not self.current(review):
            raise ValueError('stale resolution')
        if (not self.nodes[review].independent or self.nodes[review].gate
                or target not in self.dependencies(self.nodes[review])):
            raise ValueError('resolution lacks reviewed subject')
        self.resolutions[key] = (review, copy.deepcopy(self.results[review]))

    def resolved(self, key):
        if self.withdrawals.get(key) == digest(self.findings[key]):
            return True
        if key not in self.resolutions:
            return False
        review, record = self.resolutions[key]
        return self.current(review) and self.results[review] == record


class Fixture(Model):
    """Test-only graph authoring; every helper uses the same Model.submit path.

    Fixture policy explicitly permits installing/removing one-shot decision tasks.
    Production graph edits require reviewed authority, never worker self-permission.
    """
    def emit(self, kind, scope, args, actor='root', needs=()):
        name = 'request_' + str(len(self.evidence))
        self.nodes[name] = Node(needs=needs, permits=((kind, scope),))
        try:
            return self.submit(name, self.begin(name), {'rationale': 'fixture decision'}, actor,
                               ({'kind': kind, 'scope': scope, 'args': args},))
        finally:
            self.nodes.pop(name, None)

    def expand(self, collection, items, template, expected=None):
        if expected is not None and expected != self.collection_version(collection):
            raise ValueError('stale collection revision')
        before = copy.deepcopy(self.__dict__)
        source, slot = 'select_' + collection, 'selection_' + collection
        self.nodes[source] = Node(inputs=(slot,), root_only=True)
        self.inputs[slot] = copy.deepcopy(items)
        self.expansion_sources[collection] = (source, template)
        try:
            self.run(source, {'items': items, 'rationale': 'explicit fixture membership'}, 'root')
        except (ValueError, TypeError):
            self.__dict__.clear(); self.__dict__.update(before)
            raise

    def correct(self, key, target, subject, change, authority='root'):
        return self.emit('admit', target, (key, target, subject, change), authority)

    def supersede(self, key, expected, change, authority, coverage, reason, generation=None):
        return self.emit('replace', self.findings[key]['target'],
                         (key, expected, change, coverage, reason, generation), authority)

    def withdraw(self, key, expected, authority, reason):
        return self.emit('withdraw', self.findings[key]['target'], (key, expected, reason), authority)

    def authorize_retirement(self, name, authority, reason):
        return self.emit('retire', name, (name, reason), authority)

    def resolve(self, key, review):
        return self.emit('resolve', self.findings[key]['target'], (key, review), self.results[review]['actor'])


class Activation:
    """Synthetic single-record CAS; does not model GitHub multi-write atomicity."""
    def __init__(self, source):
        self.active = copy.deepcopy(source)
        self.archive = {}

    def stage(self, converted):
        return {'source': digest(self.active), 'destination': copy.deepcopy(converted)}

    def activate(self, stage, approval, crash=None):
        if approval != digest(stage):
            raise ValueError('approval does not bind staged conversion')
        if self.active == stage['destination']:
            return  # exact retry after activation
        if digest(self.active) != stage['source']:
            raise ValueError('source changed')
        self.archive[stage['source']] = copy.deepcopy(self.active)
        if crash == 'after_archive':
            raise RuntimeError('simulated crash')
        self.active = copy.deepcopy(stage['destination'])
        if crash == 'after_activation':
            raise RuntimeError('simulated crash')


class MigrationProbe(unittest.TestCase):
    def test_crash_after_archive_retries(self):
        m = Activation({'schema': 1, 'evidence': ['historical']})
        p = m.stage({'schema': 2, 'source': digest(m.active), 'missing': ['review']})
        with self.assertRaises(RuntimeError): m.activate(p, digest(p), 'after_archive')
        self.assertEqual(m.active['schema'], 1)
        m.activate(p, digest(p)); self.assertEqual(m.active['schema'], 2)
        self.assertEqual(len(m.archive), 1)
        self.assertEqual(m.active['missing'], ['review'])

    def test_crash_after_activation_retries(self):
        m = Activation({'schema': 1}); p = m.stage({'schema': 2})
        with self.assertRaises(RuntimeError): m.activate(p, digest(p), 'after_activation')
        m.activate(p, digest(p)); self.assertEqual(len(m.archive), 1)

    def test_concurrent_edit_preserved(self):
        m = Activation({'schema': 1}); p = m.stage({'schema': 2})
        m.active['human_edit'] = 'new requirements'
        with self.assertRaisesRegex(ValueError, 'source changed'): m.activate(p, digest(p))
        self.assertEqual(m.active['human_edit'], 'new requirements')

    def test_unapproved_conversion_cannot_activate(self):
        m = Activation({'schema': 1}); p = m.stage({'schema': 2})
        with self.assertRaisesRegex(ValueError, 'approval'): m.activate(p, 'old approval')
        self.assertEqual(m.active, {'schema': 1})


class Probe(unittest.TestCase):
    def linear(self):
        return Fixture({'design': Node(inputs=('spec',)),
                      'code': Node(needs=('design',)),
                      'review': Node(needs=('code',), independent=True),
                      'publish': Node(needs=('review',), gate=True)}, {'spec': 'v1'})

    def complete(self, m):
        m.run('design', 'tests'); m.run('code', 'implementation')
        m.run('review', 'accepted', 'reviewer')

    def test_dynamic_join_preserves_unaffected_bucket(self):
        m = Fixture({'synthesis': Node(joins=('buckets',))}, {})
        self.assertEqual(m.ready(), [])  # missing is not an empty collection
        m.expand('buckets', {'a': 'requirements'}, {})
        m.run('buckets/a', 'answer'); m.run('synthesis', 'summary')
        m.expand('buckets', {'a': 'requirements', 'b': 'migration'}, {})
        self.assertEqual(m.ready(), ['buckets/b'])
        m.run('buckets/b', 'migration answer')
        self.assertEqual(m.ready(), ['synthesis'])

    def test_human_answer_changes_only_affected_bucket(self):
        m = Fixture({'synthesis': Node(joins=('buckets',))}, {})
        m.expand('buckets', {'a': 'question', 'b': 'stable'}, {})
        m.run('buckets/a', 'assumption'); m.run('buckets/b', 'fact')
        m.expand('buckets', {'a': 'human answer', 'b': 'stable'}, {})
        self.assertEqual(m.ready(), ['buckets/a'])
        self.assertTrue(m.current('buckets/b'))

    def test_correction_resolution_converges(self):
        m = self.linear(); self.complete(m)
        before = m.results['code']['output']
        m.correct('race', 'code', before, 'synchronize writes')
        m.correct('race', 'code', before, 'synchronize writes')
        self.assertEqual(m.ready(), ['code'])
        m.run('code', 'fixed'); m.run('review', 'verified fix', 'reviewer')
        self.assertEqual(m.ready(), [])  # unresolved finding still gates publication
        m.resolve('race', 'review')
        self.assertTrue(m.current('code'))  # resolution itself does not rerun producer
        self.assertEqual(m.ready(), ['publish'])
        m.run('publish', 'PR'); self.assertEqual(m.ready(), [])

    def test_review_can_reach_understanding_without_back_edge(self):
        m = self.linear(); self.complete(m)
        m.correct('requirement', 'design', m.results['design']['output'], 'new acceptance')
        self.assertEqual(m.ready(), ['design'])

    def test_identical_output_can_preserve_downstream(self):
        m = self.linear(); self.complete(m)
        m.inputs['spec'] = 'clarified wording'
        self.assertFalse(m.current('code'))
        m.run('design', 'tests')
        self.assertTrue(m.current('code'))

    def test_stale_attempt_rejected(self):
        m = self.linear(); token = m.begin('design'); m.inputs['spec'] = 'v2'
        with self.assertRaisesRegex(ValueError, 'stale'): m.finish('design', token, 'old')

    def test_cycle_rejected(self):
        with self.assertRaisesRegex(ValueError, 'cycle'):
            Fixture({'a': Node(needs=('b',)), 'b': Node(needs=('a',))}, {})

    def test_unknown_applicability_not_ready(self):
        m = Fixture({'join': Node(joins=('risk',))}, {})
        self.assertEqual(m.ready(), [])
        m.expand('risk', {'specialist': 'required'}, {})
        self.assertEqual(m.ready(), ['risk/specialist'])

    def test_independent_review_required(self):
        m = self.linear(); m.run('design', 'tests'); m.run('code', 'code')
        with self.assertRaisesRegex(ValueError, 'self review'): m.run('review', 'ok')

    def test_retirement_cannot_erase_finding(self):
        m = Fixture({}, {}); m.expand('buckets', {'a': 'scope'}, {})
        m.run('buckets/a', 'answer')
        m.correct('f', 'buckets/a', m.results['buckets/a']['output'], 'reconsider')
        with self.assertRaisesRegex(ValueError, 'unresolved'): m.expand('buckets', {}, {})

    def test_external_comment_has_no_authority(self):
        m = self.linear(); self.complete(m)
        with self.assertRaisesRegex(ValueError, 'unadmitted'):
            m.correct('f', 'code', m.results['code']['output'], 'rewrite', 'commenter')

    def test_late_finding_requires_interpretation(self):
        m = self.linear(); self.complete(m); old = m.results['code']['output']
        m.inputs['spec'] = 'new'; m.run('design', 'new tests'); m.run('code', 'new code')
        with self.assertRaisesRegex(ValueError, 'late finding'):
            m.correct('old-thread', 'code', old, 'fix old code')

    def test_resolution_must_cover_current_review(self):
        m = self.linear(); self.complete(m)
        m.correct('race', 'code', m.results['code']['output'], 'fix race')
        m.run('code', 'fixed'); m.run('review', 'fix verified', 'reviewer')
        m.resolve('race', 'review')
        m.inputs['spec'] = 'new requirements'
        m.run('design', 'new tests'); m.run('code', 'new code')
        m.run('review', 'new general review', 'reviewer')
        self.assertNotIn('publish', m.ready(), 'old resolution does not cover new review')

    def test_independent_goal_not_blocked(self):
        m = Fixture({'a': Node(inputs=('a',)), 'b': Node(inputs=('b',)),
                   'publish_b': Node(needs=('b',), gate=True)}, {'a': 'A', 'b': 'B'})
        m.run('a', 'A'); m.run('b', 'B')
        m.correct('f', 'a', m.results['a']['output'], 'fix A')
        self.assertIn('publish_b', m.ready())

    def test_parent_correction_stales_only_consuming_child(self):
        m = Fixture({'parent': Node(inputs=('contract',)),
                   'child': Node(needs=('parent',)), 'unrelated': Node(inputs=('other',))},
                  {'contract': 'v1', 'other': 'unchanged'})
        m.run('parent', 'contract'); m.run('child', 'child'); m.run('unrelated', 'other')
        m.correct('scope', 'parent', m.results['parent']['output'], 'root-approved new contract')
        self.assertEqual(m.ready(), ['parent'])
        self.assertFalse(m.current('child')); self.assertTrue(m.current('unrelated'))

    def test_retired_worker_cannot_submit_after_reactivation(self):
        m = Fixture({}, {}); m.expand('work', {'a': 'same'}, {})
        token = m.begin('work/a')
        m.expand('work', {}, {}); m.expand('work', {'a': 'same'}, {})
        with self.assertRaisesRegex(ValueError, 'stale'): m.finish('work/a', token, 'old')

    def test_dynamic_cycle_rejected_without_partial_mutation(self):
        m = Fixture({'join': Node(joins=('work',))}, {})
        with self.assertRaisesRegex(ValueError, 'cycle'):
            m.expand('work', {'a': 'question'}, {'needs': ('join',)})
        self.assertNotIn('work/a', m.nodes); self.assertNotIn('work', m.members)

    def test_collection_conflict_rejected(self):
        m = Fixture({}, {}); m.expand('work', {'a': 'original'}, {})
        expected = m.collection_version('work')
        m.expand('work', {'a': 'new question'}, {}, expected)
        with self.assertRaisesRegex(ValueError, 'stale collection'):
            m.expand('work', {'a': 'overwrite'}, {}, expected)


if __name__ == '__main__':
    unittest.main(verbosity=2)
