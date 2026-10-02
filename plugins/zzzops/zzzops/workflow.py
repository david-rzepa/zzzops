"""Public workflow orchestration. Backend evidence is authority, not a cursor.

Mutation serialization is short-lived; phase ownership is durable on the goal.
The module receives the existing command services to keep provider I/O injectable.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import subprocess
import time
import uuid
import re
from contextlib import contextmanager, nullcontext
from pathlib import Path
import zzzops_comment_store as comment_store


_OBSERVED_ARTIFACT_INDEXES = {}
_GIT_ARTIFACT_SNAPSHOTS = {}


class ObservedArtifactIndex(comment_store.ArtifactIndex):
    """Discover immutable locations; hydrate only a requested delta closure.

    Each envelope is decoded with the shared limits during discovery. Its
    location/base metadata does not make any artifact valid. A read charges the
    complete selected envelopes and reconstructs every representation/base with
    the shared codec. Unrelated retained history is not an active working set.
    """
    def __init__(self, comments, previous=None):
        self.comments = [dict(row) for row in comments]
        self._limits = (comment_store.MAX_ARTIFACT_BYTES, comment_store.MAX_DELTA_DEPTH,
                        comment_store.MAX_RECONSTRUCTION_WORK_BYTES, comment_store.MAX_ARTIFACT_RECORDS)
        same = previous is not None and getattr(previous, '_limits', None) == self._limits
        prior = previous if same else None
        self._catalog = {}
        self.decoded = dict(getattr(prior, 'decoded', {}))
        self.decode_sizes = dict(getattr(prior, 'decode_sizes', {}))
        self._checks = dict(getattr(prior, '_checks', {}))
        self._values = dict(getattr(prior, '_values', {}))
        self._value_costs = dict(getattr(prior, '_value_costs', {}))
        self.records, self._locations = {}, {}
        self.envelopes, self.envelope_comments = [], []
        for row in self.comments:
            body = row.get('body', '')
            catalog = getattr(prior, '_catalog', {}).get(body)
            if catalog is None:
                envelope, legacy = self._decode(body)
                records = envelope['artifacts'] if envelope is not None else ([legacy] if legacy else [])
                metadata = {key: value for key, value in envelope.items() if key != 'artifacts'} if envelope is not None else None
                catalog = {'envelope': metadata, 'records': [(record['hash'], record.get('base') if record.get('kind') == 'delta' else None, index)
                                                          for index, record in enumerate(records)]}
            self._catalog[body] = catalog
            if catalog['envelope'] is not None:
                self.envelopes.append(catalog['envelope'])
                self.envelope_comments.append((row, catalog['envelope']))
            for identity, base, index in catalog['records']:
                self.records.setdefault(identity, None)
                self._locations.setdefault(identity, []).append((body, index, base))
        present = {row.get('body', '') for row in self.comments}
        self.decoded = {body: value for body, value in self.decoded.items() if body in present}
        self.decode_sizes = {body: size for body, size in self.decode_sizes.items() if body in present}
        self.decode_work = 0  # A particular read computes its selected working set.

    def _decode(self, body):
        if body not in self.decoded:
            one = comment_store.ArtifactIndex([{'body': body}])
            self.decoded[body] = one.decoded[body]
            self.decode_sizes[body] = one.decode_sizes[body]
        value = self.decoded[body]
        while sum(self.decode_sizes[key] for key in self.decoded) > comment_store.MAX_RECONSTRUCTION_WORK_BYTES:
            self.decoded.pop(next(iter(self.decoded)))
        return value

    @staticmethod
    def _frozen(value):
        if isinstance(value, dict): return ('object', tuple((key, ObservedArtifactIndex._frozen(child)) for key, child in sorted(value.items())))
        if isinstance(value, list): return ('array', tuple(ObservedArtifactIndex._frozen(child) for child in value))
        return (type(value).__name__, value)

    def _closure(self, identity):
        selected, bodies = set(), set()
        def visit(key, active):
            if not isinstance(key, str): raise ValueError('Invalid artifact/base identity')
            if key in active: raise ValueError('Cyclic artifact base')
            if len(active) > comment_store.MAX_DELTA_DEPTH: raise ValueError('Artifact delta depth limit exceeded')
            if key not in self.records: raise ValueError('Missing artifact/base; persist complete immutable content')
            selected.add(key)
            staged = self.records[key]
            if staged is not None:
                bases = [record.get('base') for record in staged if record.get('kind') == 'delta']
                signature = self._frozen(staged)
            else:
                locations = self._locations[key]
                bodies.update(body for body, _, _ in locations)
                bases = [base for _, _, base in locations if base is not None]
                signature = tuple((body, index) for body, index, _ in locations)
            return (signature, tuple(visit(base, active | {key}) for base in bases))
        signature = visit(identity, frozenset())
        decoded = sum(self.decode_sizes[body] for body in bodies)
        if decoded > comment_store.MAX_RECONSTRUCTION_WORK_BYTES:
            raise ValueError('Selected artifact envelope decode work limit exceeded')
        return signature, selected, decoded

    def _checked(self, identity, value_required, *, borrowed=False):
        signature, selected, decoded = self._closure(identity)
        cached = self._checks.get(identity)
        if cached and cached[:2] == (signature, self._limits):
            depth, cost = cached[2:]
            if decoded + cost > comment_store.MAX_RECONSTRUCTION_WORK_BYTES:
                raise ValueError('Selected artifact reconstruction work limit exceeded')
            if not value_required: return None
            if identity in self._values:
                value = self._values.pop(identity); self._values[identity] = value
                return (value if borrowed else copy.deepcopy(value)), depth, decoded + cost
        view = comment_store.ArtifactIndex([])
        view.decode_work = decoded
        for key in selected:
            staged = self.records[key]
            if staged is not None:
                view.records[key] = staged
                continue
            rows = []
            for body, index, _ in self._locations[key]:
                envelope, legacy = self._decode(body)
                rows.append(envelope['artifacts'][index] if envelope is not None else legacy)
            view.records[key] = rows
        value, depth, spent = view.resolve(identity)
        self._checks[identity] = (signature, self._limits, depth, spent - decoded)
        # Validation has already reconstructed the value. Retain it under the
        # same bounded cache as reads, avoiding a second decode after publication.
        # Each later read still checks its exact closure and charges its work.
        cost = max(1, len(comment_store.canonical(value).encode('utf-8')))
        if identity in self._values:
            self._values.pop(identity); self._value_costs.pop(identity)
        while self._values and sum(self._value_costs.values()) + cost > comment_store.MAX_RECONSTRUCTION_WORK_BYTES:
            oldest = next(iter(self._values)); self._values.pop(oldest); self._value_costs.pop(oldest)
        self._values[identity] = value; self._value_costs[identity] = cost
        if value_required:
            return (value if borrowed else copy.deepcopy(value)), depth, spent
        return None

    def resolve(self, identity):
        return self._checked(identity, True)

    def observe(self, identity):
        """Internal read-only view; callers must copy before any mutation.

        Public resolve/read still returns detached values. Exact provider-body
        and delta-base validation is identical for this borrowed observation.
        """
        return self._checked(identity, True, borrowed=True)

    def validate(self, identity):
        self._checked(identity, False)

# Public submissions are intentionally enumerated here, before any context or
# provider work.  A misspelled operation must be repaired as such rather than
# being routed through an unrelated installation, policy, lease, or portfolio
# gate.
PUBLIC_OPERATIONS = frozenset({
    'batch', 'bind', 'block',
    'capture', 'capture_propose', 'complete', 'feedback_prepare',
    'feedback_submit', 'heartbeat', 'installation_record', 'integrate',
    'policy_approve', 'policy_propose', 'read', 'recover', 'renew',
    'start', 'reconcile', 'submit',
})


class RenewalBudget:
    """Bound provider work while reserving independent time to release storage."""
    def __init__(self, work_seconds=30, cleanup_seconds=10):
        if any(not math.isfinite(v) or v <= 0 for v in (work_seconds, cleanup_seconds)):
            raise ValueError('Renewal work and cleanup budgets must be finite and positive')
        self.deadline = time.monotonic() + work_seconds
        self.cleanup_seconds = cleanup_seconds

    def timeout(self, maximum):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise ValueError('Heartbeat renewal deadline exhausted; retry the same lease after cleanup')
        return min(maximum, remaining)

    @contextmanager
    def cleanup(self):
        previous = self.deadline
        self.deadline = time.monotonic() + self.cleanup_seconds
        try:
            yield
        finally:
            self.deadline = previous


def digest(value):
    return 'sha256:' + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def explicit_approval(value):
    return isinstance(value, str) and bool(value.strip()) and value == value.strip() and '<' not in value and '>' not in value


def preflight_policy_proposal(api, repo, proposal):
    if not isinstance(proposal, dict):
        raise ValueError('Policy proposal must be a JSON object')
    prospective = copy.deepcopy(proposal)
    prospective['confirmed'] = True
    errors = api.validate_plan(repo, prospective)
    if errors:
        raise ValueError('Invalid policy proposal: ' + '; '.join(errors))
    unresolved = [
        section.get('id', '<unknown>')
        for section in prospective['policy']['sections']
        if section.get('unresolved')
    ]
    if unresolved:
        raise ValueError('Resolve policy choices before approval: ' + ', '.join(unresolved))
    return prospective


def policy_section(project, section_id):
    sections = ((project.get('policy') or {}).get('sections') if isinstance(project.get('policy'), dict) else None)
    section = next((item for item in sections or [] if isinstance(item, dict) and item.get('id') == section_id), None)
    if not isinstance(section, dict) or not isinstance(section.get('configuration'), dict):
        raise ValueError(f'Reviewed project policy is missing {section_id} configuration')
    return section


def worker_limit(project):
    value = policy_section(project, 'autonomy_approval_parallelism')['configuration'].get('max_workers')
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError('Reviewed project policy max_workers must be a positive integer')
    return value


def unresolved_lease_count(goals):
    return sum(
        1
        for goal in goals
        if goal.get('status') not in {'done', 'cancelled'}
        for _lease in (goal.get('operational_leases', []) if goal.get('schema_version') == 2 else state(goal)['leases'].values())
    )


def state(goal):
    result = copy.deepcopy(goal.get('workflow') or {'leases': {}, 'receipts': {}, 'workers': {}, 'assessments': {}, 'artifacts': {}})
    result.setdefault('routing_choices', {})
    return result


def validate_state(value):
    def text(item):
        return isinstance(item, str) and bool(item) and item == item.strip()

    def sha256(item):
        return (
            isinstance(item, str) and len(item) == 71 and item.startswith('sha256:')
            and all(character in '0123456789abcdef' for character in item[7:])
        )

    def selection(item):
        return (
            isinstance(item, dict) and set(item) == {'model', 'effort'}
            and all(text(entry) for entry in item.values())
        )

    required = {'leases', 'receipts', 'workers', 'assessments', 'artifacts'}
    if not isinstance(value, dict) or set(value) not in (required, required | {'routing_choices'}):
        return ['workflow must contain leases, receipts, workers, assessments, artifacts and optional routing choices']
    if any(not isinstance(v, dict) for v in value.values()):
        return ['workflow collections must be objects']
    for phase, choice in value.get('routing_choices', {}).items():
        if not text(phase) or not isinstance(choice, dict) or set(choice) not in ({'choice', 'root_pair', 'requested_pair', 'approved_by'}, {'choice', 'root_pair', 'requested_pair', 'approved_by', 'selection'}):
            return ['workflow routing choice is invalid']
        if choice['choice'] not in {'use_requested_pair', 'downgrade_to_root', 'delegate_at_root'} or not selection(choice['root_pair']) or (choice['requested_pair'] is not None and not selection(choice['requested_pair'])) or ('selection' in choice and not selection(choice['selection'])) or not explicit_approval(choice['approved_by']):
            return ['workflow routing choice is invalid']
    for key, lease in value['leases'].items():
        if not text(key) or ':' not in key:
            return ['workflow lease map identity is invalid']
        fields = {'token', 'owner', 'worker', 'selection', 'kind', 'input_hash', 'expires_at', 'group', 'record_hash', 'review_hash'}
        if not isinstance(lease, dict) or set(lease) not in (fields, fields | {'acquisition'}):
            return ['workflow lease fields are invalid']
        phase, separator, kind = key.rpartition(':')
        if not separator or not text(phase) or kind not in {'execute', 'review', 'human_approval'} or lease['kind'] != kind:
            return ['workflow lease map identity is invalid']
        expiry = lease['expires_at']
        if (
            not isinstance(expiry, (int, float)) or isinstance(expiry, bool)
            or not -float('inf') < expiry < float('inf') or expiry <= 0
            or not all(text(lease[f]) for f in ('token', 'owner', 'group'))
            or not sha256(lease['input_hash'])
            or (lease['worker'] is not None and not text(lease['worker']))
        ):
            return ['workflow lease identity is invalid']
        if not selection(lease['selection']):
            return ['workflow lease selection is invalid']
        if kind == 'execute':
            if lease['record_hash'] is not None or lease['review_hash'] is not None:
                return ['workflow lease evidence binding is invalid']
            acquisition = lease.get('acquisition')
            if 'acquisition' in lease and (
                not valid_acquisition(acquisition, envelope=True)
                or digest(acquisition['input_envelope']) != lease['input_hash']
                or acquisition['input_envelope'].get('phase') != phase
            ):
                return ['workflow lease acquisition is invalid']
        elif not sha256(lease['record_hash']) or (kind == 'review' and lease['review_hash'] is not None) or (kind == 'human_approval' and not sha256(lease['review_hash'])):
            return ['workflow lease evidence binding is invalid']
        elif 'acquisition' in lease:
            return ['Only execution leases carry acquisition evidence']
    for request_id, receipt in value['receipts'].items():
        if not text(request_id) or not isinstance(receipt, dict) or set(receipt) != {'hash'} or not sha256(receipt['hash']):
            return ['workflow receipt is invalid']
    for identifier, worker in value['workers'].items():
        if (
            not text(identifier) or not isinstance(worker, dict) or set(worker) != {'id', 'group', 'selection'}
            or worker.get('id') != identifier or not text(worker.get('group')) or not selection(worker.get('selection'))
        ):
            return ['workflow worker is invalid']
    for phase, assessment in value['assessments'].items():
        allowed = {'dimensions', 'goal_spec', 'policy'}
        if (
            not text(phase) or not isinstance(assessment, dict) or set(assessment) not in (allowed, allowed | {'files'})
            or not sha256(assessment.get('goal_spec')) or not sha256(assessment.get('policy'))
        ):
            return ['workflow assessment is invalid']
        dimensions = assessment.get('dimensions')
        if (
            not isinstance(dimensions, dict)
            or set(dimensions) != {'consequence', 'boundedness', 'engineering_rigor'}
            or any(not text(item) for item in dimensions.values())
        ):
            return ['workflow assessment dimensions are invalid']
        files = assessment.get('files', [])
        if not isinstance(files, list) or any(not text(path) for path in files) or len(files) != len(set(files)):
            return ['workflow assessment files are invalid']
    for phase, artifact in value['artifacts'].items():
        fields = {'commands', 'workspace', 'passed'}
        if not text(phase) or not isinstance(artifact, dict) or set(artifact) not in (fields, fields | {'acquisition', 'phase', 'lease', 'actor', 'outputs'}):
            return ['workflow verification artifact is invalid']
        if 'acquisition' in artifact and (
            not valid_acquisition(artifact['acquisition']) or artifact['phase'] != phase
            or not all(text(artifact[field]) for field in ('lease', 'actor'))
            or not isinstance(artifact['outputs'], dict)
            or any(not text(path) or (value != 'missing' and not sha256(value)) for path, value in artifact['outputs'].items())
        ):
            return ['workflow verification acquisition/output evidence is invalid']
        commands = artifact.get('commands')
        if not sha256(artifact.get('workspace')) or not isinstance(artifact.get('passed'), bool) or not isinstance(commands, list) or not commands:
            return ['workflow verification artifact is invalid']
        for result in commands:
            if not isinstance(result, dict) or set(result) != {'command', 'exit_code', 'log_hash', 'log'}:
                return ['workflow verification command is invalid']
            command, exit_code, log_hash = result.get('command'), result.get('exit_code'), result.get('log_hash')
            if (
                not isinstance(command, list) or not command or any(not text(argument) for argument in command)
                or not isinstance(exit_code, int) or isinstance(exit_code, bool)
                or not isinstance(log_hash, str) or len(log_hash) != 64
                or any(character not in '0123456789abcdef' for character in log_hash)
                or not text(result.get('log'))
            ):
                return ['workflow verification command is invalid']
        if artifact['passed'] != all(result['exit_code'] == 0 for result in commands):
            return ['workflow verification result is inconsistent']
    return []


def valid_predecessor_reference(value):
    return (isinstance(value, dict) and set(value) == {'reference', 'hash'}
            and isinstance(value['hash'], str)
            and re.fullmatch(r'sha256:[0-9a-f]{64}', value['hash']) is not None
            and value['reference'] == 'urn:' + value['hash'])


def valid_acquisition(value, *, envelope=False):
    fields = {'git_commit', 'workspace_digest', 'input_envelope' if envelope else 'input_hash'}
    return (
        isinstance(value, dict) and set(value) in (fields, fields | {'predecessor'}, fields | {'checkout_overrides'}, fields | {'predecessor', 'checkout_overrides'})
        and ('checkout_overrides' not in value or (isinstance(value['checkout_overrides'], dict) and all(isinstance(k, str) and bool(k) and not k.startswith('/') and '\\' not in k and all(part not in ('', '.', '..') for part in k.split('/')) and not k.startswith('.zzzops/') and isinstance(v, str) and re.fullmatch(r'sha256:[0-9a-f]{64}', v) for k, v in value['checkout_overrides'].items())))
        and ('predecessor' not in value or valid_predecessor_reference(value['predecessor']))
        and isinstance(value['git_commit'], str)
        and re.fullmatch(r'[0-9a-f]{40,64}', value['git_commit']) is not None
        and isinstance(value['workspace_digest'], str)
        and re.fullmatch(r'sha256:[0-9a-f]{64}', value['workspace_digest']) is not None
        and (isinstance(value['input_envelope'], dict) and value['input_envelope'].get('schema_version') == 2
             and isinstance(value['input_envelope'].get('repository'), dict) if envelope else
             isinstance(value['input_hash'], str) and re.fullmatch(r'sha256:[0-9a-f]{64}', value['input_hash']) is not None)
    )


class Workflow:
    def __init__(self, api, repo, project, runtime=None):
        self.api, self.repo, self.project = api, repo, project
        self.runtime = runtime
        self.repository = api._project_repository_identity(project)
        self.adapter = api.GitHubGoalTransitionAdapter(repo, self.repository)
        self.budget = getattr(api, 'renewal_budget', None)
        if self.budget:
            self.adapter.timeout_budget = self.budget.timeout
        self._read_cache = {}
        self._portfolio_cache = None

    def invalidate(self):
        getattr(self, '_read_cache', {}).clear()
        self._read_cache = {}
        self._portfolio_cache = None
        self._artifact_indexes = {}

    def read(self, number):
        if number not in self._read_cache:
            self.portfolio(allow_invalid=True)
            records = {item.get('key'): item for item in self._portfolio_cache.get('goals', []) if isinstance(item, dict)}
            goal = records.get(number)
            if not isinstance(goal, dict):
                raise ValueError(f'Goal #{number} is absent from the current portfolio gateway')
            goal = {
                **goal,
                'engineering_rigor': copy.deepcopy(goal.get('engineering_rigor_inputs', goal.get('engineering_rigor'))),
                'children': [row['key'] for row in records.values()
                             if row.get('parent') == number and row.get('status') != 'cancelled'],
                "human_spec": goal.get("human_spec") or f"Archived goal #{number}; body unavailable.",
                "acceptance_criteria": goal.get("acceptance_criteria", []),
                "phase_evidence": goal.get("phase_evidence") or self.api.empty_phase_evidence(),
            }
            # Workflow context is allowed to consume only the portfolio gateway.
            # Mutations still use their provider adapter at the write boundary.
            self._read_cache[number] = ({'number': number}, copy.deepcopy(goal))
        return copy.deepcopy(self._read_cache[number])

    def artifact(self, number, content):
        identity = comment_store.digest(content)
        index = self.artifact_index(number)
        record = index.record(content)
        if record is not None:
            bodies = comment_store.pack_envelopes({'goal': number, 'transaction': identity}, [record])
            comments = self.adapter.get_issue_comments(number)
            prospective = self.node_preflight(comments, bodies, [identity], index)
            body = bodies[0]
            stored = self.adapter.create_issue_comment(number, body)
            if stored.get('body') != body:
                raise ValueError('Provider did not confirm the exact artifact')
            confirmed = ObservedArtifactIndex(self.adapter.get_issue_comments(number), previous=prospective)
            confirmed.resolve(identity)
            self._artifact_indexes[number] = confirmed
        return {'reference': 'urn:' + identity, 'hash': identity}

    def node_ref(self, identity, number):
        return {'hash': identity, 'uri': f'zzzops:{self.repository}:goal:{number}:{identity}'}

    def node_ref_goal(self, reference, local):
        """A locator selects storage only; content hash and graph grant authority."""
        identity, uri = reference['hash'], reference['uri']
        if uri == 'urn:' + identity: return local
        match = re.fullmatch(r'zzzops:([^:]+):goal:([1-9][0-9]*):(sha256:[0-9a-f]{64})', uri)
        if not match or match[1] != self.repository or match[3] != identity:
            raise ValueError('Artifact locator must bind its exact hash and same repository goal identity')
        return int(match[2])

    def artifact_index(self, number):
        if not hasattr(self, '_artifact_indexes'):
            self._artifact_indexes = {}
        if number not in self._artifact_indexes:
            key = (str(self.repo.resolve()), self.repository, number)
            previous = _OBSERVED_ARTIFACT_INDEXES.get(key)
            comments = self.adapter.get_issue_comments(number)
            limits = (comment_store.MAX_ARTIFACT_BYTES, comment_store.MAX_DELTA_DEPTH,
                      comment_store.MAX_RECONSTRUCTION_WORK_BYTES, comment_store.MAX_ARTIFACT_RECORDS)
            # Reuse only an exact fresh provider observation with no locally
            # staged records. Edits, deletions and changed decoder bounds rebuild.
            reusable = (previous is not None and previous._limits == limits
                        and previous.comments == comments
                        and all(value is None for value in previous.records.values()))
            observed = previous if reusable else ObservedArtifactIndex(comments, previous=previous)
            self._artifact_indexes[number] = observed
            if key not in _OBSERVED_ARTIFACT_INDEXES and len(_OBSERVED_ARTIFACT_INDEXES) >= 4:
                _OBSERVED_ARTIFACT_INDEXES.pop(next(iter(_OBSERVED_ARTIFACT_INDEXES)))
            _OBSERVED_ARTIFACT_INDEXES[key] = observed
        return self._artifact_indexes[number]

    def stage_artifact(self, number, content, base=None):
        self._referenced_artifacts.add((number, comment_store.digest(content)))
        index = self.artifact_index(number)
        record = index.record(content, base)
        if record is not None:
            self._pending_artifacts.append(record)
            index.records.setdefault(record['hash'], []).append(record)
        return {'reference': 'urn:' + comment_store.digest(content), 'hash': comment_store.digest(content)}

    def resolve_selector(self, number, selector):
        if not isinstance(selector, dict) or set(selector) - {'phase', 'slot', 'revision'} or not isinstance(selector.get('phase'), str) or selector.get('slot') not in {'output', 'review', 'verification'}:
            raise ValueError('Logical artifact selector requires phase, slot and optional revision')
        _, goal = self.read(number)
        revision = selector.get('revision', goal['revision'])
        if 'revision' in selector:
            goal = self.api._goals.reconstruct_goal_history(self.adapter, number, revision)['goal']
        evidence = goal.get('phase_evidence') or {}
        phase, slot = selector['phase'], selector['slot']
        if slot == 'review':
            reference = (evidence.get('reviews', {}).get(phase) or {}).get('artifact')
        else:
            reference = (evidence.get('records', {}).get(phase) or {}).get(slot)
        if not reference:
            raise ValueError('Logical artifact has no committed value at the requested revision')
        return reference, {'goal': number, 'phase': phase, 'slot': slot, 'revision': revision, **reference}

    def resolve_node_selector(self, number, selector):
        ev = self.api._phase_evidence
        if set(selector) - {'node', 'output', 'revision'} or not isinstance(selector.get('output'), str):
            raise ValueError('Logical node selector requires exact node and output')
        ev.task_key(selector['node'])
        if selector['node']['goal'] != number: raise ValueError('Logical selector goal mismatch')
        issue = self.adapter.get_issue(number)
        envelope = self.api._goals.parse_managed_goal(issue['body'], number)
        index = self.artifact_index(number)
        revision = selector.get('revision', envelope['revision'])
        if envelope['revision'] != revision:
            current = index.resolve(envelope['payload']['hash'])[0]
            receipts = {(row['request'], row['payload']) for row in current['operational']['receipts']}
            candidates = {}
            for entry in index.envelopes:
                context = entry.get('context', {})
                if (context.get('request_id'), context.get('request_hash')) not in receipts: continue
                historical = context.get('target_envelope')
                if isinstance(historical, dict) and historical.get('revision') == revision:
                    candidates[digest(historical)] = historical
            if len(candidates) != 1: raise ValueError('Unknown or ambiguous historical revision')
            envelope = next(iter(candidates.values()))
        payload = index.resolve(envelope['payload']['hash'])[0]
        for ref in reversed(payload['evidence']):
            result = index.resolve(ref['hash'])[0]['content']
            if result['node'] == selector['node']:
                reference = result['outputs'].get(selector['output'])
                if reference is None: raise ValueError('Unknown output slot')
                return reference, {**selector, **reference, 'revision': revision}
        raise ValueError('Logical node output has no committed value')

    def read_artifact(self, number, artifact):
        if isinstance(artifact, dict) and 'node' in artifact:
            artifact, _ = self.resolve_node_selector(number, artifact)
        if isinstance(artifact, dict) and 'uri' in artifact:
            self.api._phase_evidence.validate_ref(artifact)
            artifact = {'hash': artifact['hash'], 'reference': artifact['uri']}
        if isinstance(artifact, dict) and 'phase' in artifact:
            artifact, _ = self.resolve_selector(number, artifact)
        # Content-addressed successful reads may be reused within this invocation.
        # Live records/review bindings are still checked independently each time.
        key = (number, digest(artifact))
        cache = getattr(self, '_immutable_artifacts', {})
        if key not in cache:
            cache[key] = self._read_artifact(number, artifact)
            self._immutable_artifacts = cache
        return copy.deepcopy(cache[key])

    def _read_artifact(self, number, artifact):
        if isinstance(artifact, dict) and set(artifact) == {'reference', 'hash'} and str(artifact['reference']).startswith('zzzops:'):
            ref = {'hash': artifact['hash'], 'uri': artifact['reference']}
            self.api._phase_evidence.validate_ref(ref)
            self.node_ref_goal(ref, number)
        else:
            artifact = self.api._phase_evidence._artifact(artifact, 'artifact', required=True)
        reference, expected = artifact['reference'], artifact['hash']
        if reference.startswith('git:'):
            content = subprocess.run(['git', 'show', reference[4:]], cwd=self.repo, capture_output=True, check=True).stdout
            if 'sha256:' + hashlib.sha256(content).hexdigest() != expected:
                raise ValueError('Git artifact content does not match its declared hash')
            return content.decode('utf-8')
        owner = self.node_ref_goal({'hash': expected, 'uri': reference}, number)
        if hasattr(self, '_referenced_artifacts'):
            self._referenced_artifacts.add((number, expected))
        return self.artifact_index(owner).observe(expected)[0]

    def portfolio(self, *, allow_invalid=True):
        if self._portfolio_cache is None:
            self._portfolio_cache = self.api.portfolio_snapshot(self.repo)
            for goal in self._portfolio_cache.get('goals', []):
                if goal.get('schema_version') == 2 and goal.get('envelope') and goal.get('status') not in {'done', 'cancelled'}:
                    try:
                        payload = self.artifact_index(goal['key']).resolve(goal['envelope']['payload']['hash'])[0]
                        goal['operational_leases'] = copy.deepcopy(payload['operational']['leases'])
                    except (ValueError, KeyError):
                        pass
        portfolio = self._portfolio_cache
        findings = portfolio.get('findings', [])
        # A provider/inventory failure is global. Fully attributed goal findings
        # are not: their exact prerequisite closure is checked before dispatch.
        scoped = (isinstance(findings, list) and bool(findings)
                  and all(isinstance(f, dict) and type(f.get('goal')) is int for f in findings)
                  and isinstance(portfolio.get('goals'), list)
                  and not portfolio.get('error'))
        if not portfolio.get('complete') and not (allow_invalid and scoped):
            findings = portfolio.get('findings') if isinstance(portfolio, dict) else None
            if isinstance(findings, list) and findings:
                details = '; '.join(
                    f"goal {item.get('goal', '?')}: {item.get('code', 'validation_error')} — {item.get('detail', 'inspect the goal record')}"
                    for item in findings if isinstance(item, dict)
                )
                raise ValueError(
                    'Repair the goal portfolio before starting or submitting work. '
                    f"Observed validation findings: {details}. Correct the cited goal records and retry."
                )
            raise ValueError('Repair the goal portfolio before starting or submitting work; no detailed findings were returned by the portfolio validator.')
        return copy.deepcopy(portfolio['goals'])

    def reconciliation_step(self, goal):
        # Generic reconciliation is derived from current declared publication
        # evidence in node_checkpoint. Legacy PR/phase fields grant no effects.
        return None

    def validation_blockers(self, goal):
        """Return findings that affect this goal or one of its prerequisites."""
        self.portfolio(allow_invalid=True)
        portfolio = getattr(self, '_portfolio_cache', None)
        if not isinstance(portfolio, dict):
            return []
        records = {record['key']: record for record in portfolio['goals']}
        affected = set()
        pending = [goal['key']]
        while pending:
            key = pending.pop()
            if key in affected:
                continue
            affected.add(key)
            record = records.get(key, {})
            pending.extend(record.get('depends_on', []))
            if record.get('parent') is not None:
                pending.append(record['parent'])
        return sorted(
            (finding for finding in portfolio.get('findings', [])
             if isinstance(finding, dict) and finding.get('goal') in affected),
            key=lambda finding: (str(finding.get('goal')), finding.get('code', ''), finding.get('detail', '')),
        )

    @contextmanager
    def locked(self):
        api = self.api
        adapter = api.GitHubReservationAdapter(self.repo, self.repository)
        owner, run = 'workflow', uuid.uuid4().hex
        if getattr(self, '_storage_reservation', None) is not None:
            raise ValueError('Nested workflow storage reservations are not supported')
        budget = getattr(self, 'budget', None)
        if budget:
            adapter.timeout_budget = budget.timeout
        deadline = time.monotonic() + 10
        reservation = None
        attempted = False
        try:
            while True:
                if budget:
                    budget.timeout(10)
                # Even a lost acquisition confirmation may leave our label behind.
                attempted = True
                acquired = api.acquire_storage_lock(adapter, self.repository, 'workflow', owner, run, 300)
                if acquired.get('acquired'):
                    break
                if time.monotonic() >= deadline:
                    raise ValueError('Another coordinator is updating goals; retry the same request')
                time.sleep(min(.2, budget.timeout(.2)) if budget else .2)
            expires_at = acquired.get('expires_at')
            if not isinstance(expires_at, (int, float)) or isinstance(expires_at, bool):
                raise ValueError('Provider did not confirm the storage reservation expiry; no write is allowed')
            reservation = {
                'adapter': adapter, 'owner': owner, 'run': run,
                'expires_at': expires_at, 'valid': True,
            }
            self._storage_reservation = reservation
            self.invalidate()
            yield
        finally:
            if getattr(self, '_storage_reservation', None) is reservation:
                self._storage_reservation = None
            if attempted:
                # This checks exact owner/run and never deletes another holder.
                # Unconfirmed remote writes remain uncertain, not safe takeover evidence.
                with budget.cleanup() if budget else nullcontext():
                    api.release_storage_lock(adapter, self.repository, 'workflow', owner, run)

    def save(self, issue, goal, desired, *, human_spec=None):
        reservation = getattr(self, '_storage_reservation', None)
        if reservation is not None:
            if not reservation['valid']:
                raise ValueError('A current workflow storage reservation is required before writing')
            if time.time() >= reservation['expires_at']:
                reservation['valid'] = False
                raise ValueError('The workflow storage reservation expired before writing; re-read and retry')
            renewed = self.api.renew_storage_lock(
                reservation['adapter'], self.repository, 'workflow',
                reservation['owner'], reservation['run'], 300,
            )
            if not renewed.get('acquired'):
                reservation['valid'] = False
                raise ValueError('The workflow storage reservation was lost before writing; re-read and retry')
            expires_at = renewed.get('expires_at')
            if not isinstance(expires_at, (int, float)) or isinstance(expires_at, bool) or expires_at <= time.time():
                reservation['valid'] = False
                raise ValueError('Provider did not confirm a live workflow storage reservation; no write is allowed')
            reservation['expires_at'] = expires_at
        desired['revision'] = goal['revision'] + 1
        def before_publish():
            if reservation is not None and (not reservation['valid'] or time.time() >= reservation['expires_at']):
                raise ValueError('Storage reservation expired before publication')
            token = getattr(self, '_mutation_payload', {}).get('lease')
            previous = next((v for v in state(goal)['leases'].values() if v['token'] == token), None)
            if previous is not None and time.time() >= previous['expires_at'] and getattr(self, '_mutation_payload', {}).get('operation') not in {'recover', 'release', 'renew'}:
                raise ValueError('Phase lease expired before publication')
            if getattr(self, '_mutation_payload', {}):
                raise ValueError('Historical storage transport cannot execute retired phase operations')
        result = self.api.apply_goal_transition(self.adapter, self.repository, goal['key'], {
            'schema_version': self.api.GOAL_TRANSITION_SCHEMA_VERSION,
            'expected_revision': goal['revision'], 'expected_digest': goal['digest'], 'goal': desired,
            **({'human_spec': human_spec} if human_spec is not None else {}),
        }, artifact_records=getattr(self, '_pending_artifacts', []),
           transaction_context=getattr(self, '_transaction_context', None), before_publish=before_publish,
           observed_issue=issue, observed_comments=self.artifact_index(goal['key']).comments,
           observed_index=self.artifact_index(goal['key']),
           artifact_hashes={identity for number, identity in getattr(self, '_referenced_artifacts', set()) if number == goal['key']})
        self.invalidate()
        return result

    def inputs(self, goal, graph):
        live = self.api.workflow_live_inputs(self.repo, self.project, goal, 'execute', graph)
        normalizer = getattr(self.api, 'normalize_phase_evidence', None)
        evidence = normalizer(goal.get('phase_evidence')) if callable(normalizer) else (
            goal.get('phase_evidence') or self.api.empty_phase_evidence()
        )
        def completion_identity(completed):
            records = (completed.get('phase_evidence') or {}).get('records', {})
            return {
                phase: {
                    'status': record.get('status'),
                    'output': record.get('output'),
                    'not_required': record.get('not_required'),
                }
                for phase, record in sorted(records.items())
            }
        # Only explicitly consumed files invalidate a phase. HEAD/revision and
        # other operational bookkeeping must not invalidate a reviewed design.
        migration_observation = None
        for phase, envelope in live.items():
            versions = self.owned_versions(goal, phase)
            node = next(node for node in graph['phases'] if node['id'] == phase)
            if goal.get('parent'):
                _, parent = self.read(goal['parent'])
                parent_records = (parent.get('phase_evidence') or {}).get('records', {})
                for gate in node.get('parent_gates', []):
                    record = parent_records.get(gate)
                    if record:
                        artifact = record.get('output') or {'reference': 'urn:sha256:' + digest(record.get('not_required'))[7:], 'hash': digest(record.get('not_required'))}
                        envelope['parents'].append({'goal': parent['key'], 'artifact': artifact})
            for dependency in goal.get('depends_on', []):
                _, required = self.read(dependency)
                identity = digest({
                    'status': required['status'],
                    'spec': self.api.goal_spec_digest(required, title=required['title'], human_spec=required['human_spec']),
                    'results': completion_identity(required),
                })
                envelope['dependencies'].append({'goal': dependency, 'artifact': {'reference': 'urn:sha256:' + identity[7:], 'hash': identity}})
            prior = evidence['records'].get(phase, {}).get('input_envelope', {})
            assessment = state(goal)['assessments'].get(phase)
            paths = assessment.get('files', []) if assessment else prior.get('repository', {}).get('snapshot', {}).get('files', {})
            actual = self.file_hashes(paths)
            migration_path = f".zzzops/migration/{goal['key']}.json"
            migration_paths = [path for path in paths if path.startswith('.zzzops/migration/')]
            if migration_paths:
                if migration_paths == [migration_path]:
                    if migration_observation is None:
                        migration_observation = self.api.migration_assessment(self.repo, self.project, goal)
                    envelope['provider']['snapshot']['migration'] = copy.deepcopy(migration_observation)
                else:
                    envelope['provider']['snapshot']['migration'] = {'decision': {
                        'action': 'block', 'scope': 'none', 'reason': 'foreign_migration_evidence'}}
            lease = state(goal)['leases'].get(phase + ':execute', {})
            acquisition = self.acquisition(goal, phase, lease)
            frozen = acquisition.get('input_envelope', {}) if acquisition else prior
            before = frozen.get('repository', {}).get('snapshot', {}).get('files', {})
            review = evidence['reviews'].get(phase)
            if not acquisition and review and review['decision'] == 'changes_requested':
                # Correction reads the actual produced baseline, not the rejected
                # execution's historical input map. Prerequisites stay historical.
                before = {}
            for path, value in before.items():
                if path in actual and value in versions.get(path, set()):
                    actual[path] = value
            envelope['repository']['snapshot'] = {'files': actual}
            # Acquisition and result publication can reclassify an older
            # verification as history. Retain the marker in the acquired input
            # or completed record so bookkeeping does not change its fingerprint.
            # A newly observed output drift below replaces this older marker.
            frozen_snapshot = frozen.get('repository', {}).get('snapshot', {})
            if 'output_drift' in frozen_snapshot:
                envelope['repository']['snapshot']['output_drift'] = frozen_snapshot['output_drift']
            if assessment:
                envelope['capabilities']['snapshot'] = {'assessment': assessment}
            if phase == 'publish':
                children = [self.read(g['key'])[1] for g in self.portfolio()
                            if g.get('parent') == goal['key'] and g.get('status') != 'cancelled']
                envelope['dependencies'] += [
                    {'goal': child['key'], 'artifact': {'reference': 'urn:sha256:' + digest({'status': child['status'], 'results': completion_identity(child), 'spec': self.api.goal_spec_digest(child, title=child['title'], human_spec=child['human_spec'])})[7:],
                     'hash': digest({'status': child['status'], 'results': completion_identity(child), 'spec': self.api.goal_spec_digest(child, title=child['title'], human_spec=child['human_spec'])})}}
                    for child in sorted(children, key=lambda g: g['key'])]
            if phase == 'publish' and (goal.get('implementation') or {}).get('branch'):
                envelope['provider']['snapshot']['publication'] = self.publication_identity(goal)
            proof = state(goal)['artifacts'].get(phase)
            withdrawn = any(item['phase'] == phase for item in evidence['withdrawals'])
            # An abandoned verification is history, not a produced result whose
            # validity can drift. Otherwise acquiring a replacement lease makes
            # historical_proof suppress this field and invalidates that lease.
            if evidence['records'].get(phase) and not withdrawn and proof and proof.get('workspace') and proof['workspace'] != self.workspace_digest() and not (versions and self.historical_proof(goal, phase, proof)):
                envelope['repository']['snapshot']['output_drift'] = self.workspace_digest()
        return live

    def historical_proof(self, goal, phase, proof):
        if phase not in {'test_design', 'implement'}:
            return False
        lease = state(goal)['leases'].get(phase + ':execute')
        if lease and self.acquisition(goal, phase, lease):
            return True
        return proof.get('workspace') in getattr(self, '_connected_workspaces', set())

    def scope_phase(self, *, composition=False):
        phases = policy_section(self.project, 'workflow_adherence')['configuration']['phase_dag']['phases']
        if any(node['id'] == 'plan' for node in phases):
            return 'plan'  # Compatibility until the reviewed default is adopted.
        return 'decompose' if composition else 'understand'

    def reviewed_scope(self, goal):
        """Reviewed understanding owns leaf scope; decomposition allocates children."""
        parent = goal.get('parent') or goal['key']
        scopes = []
        owners = (self.read(parent)[1], goal) if goal.get('parent') else (goal,)
        for current in owners:
            phase = self.scope_phase(composition=current['key'] != goal['key'])
            evidence = current.get('phase_evidence') or self.api.empty_phase_evidence()
            record, review = evidence['records'].get(phase), evidence['reviews'].get(phase)
            if not record or not review or review['decision'] != 'approved' or review['reviewer'] == record['actor']:
                return None
            if any(item['phase'] == phase for item in evidence['withdrawals']):
                return None
            if review['record_hash'] != digest(record) or review['input_hash'] != record['input_hash']:
                return None
            graph, _ = self.api._workflow_phase_configuration(self.project, current)
            live = self.api.workflow_live_inputs(self.repo, self.project, current, 'execute', graph)[phase]
            if any(record['input_envelope'][field] != live[field] for field in ('goal_spec', 'policy', 'phase_dag')):
                return None
            content = self.read_artifact(current['key'], record['output'])
            scope = content.get('output_scope') if isinstance(content, dict) else None
            if current['key'] == goal.get('parent') and isinstance(content, dict) and 'output_scopes' in content:
                entries = content['output_scopes']
                if scope is not None or not isinstance(entries, list) or any(not isinstance(x, dict) for x in entries):
                    return None
                identifiers = [x.get('child') for x in entries]
                if any(not isinstance(x, int) or isinstance(x, bool) for x in identifiers) or len(identifiers) != len(set(identifiers)):
                    return None
                scope = next((x for x in entries if x.get('child') == goal['key']), None)
            if not isinstance(scope, dict) or set(scope) != {'parent', 'child', 'test_design', 'implement'}:
                return None
            if scope['parent'] != parent or scope['child'] != goal['key']:
                return None
            paths = scope['test_design'] + scope['implement'] if all(isinstance(scope[p], list) for p in ('test_design', 'implement')) else []
            if not all(isinstance(scope[p], list) for p in ('test_design', 'implement')) or any(not isinstance(p, str) for p in paths) or len(paths) != len(set(paths)):
                raise ValueError('Reviewed output scope must contain distinct finite paths')
            for path in paths:
                if not isinstance(path, str) or Path(path).is_absolute() or Path(path).as_posix() != path or '..' in Path(path).parts or path.startswith('.zzzops/') or path == 'AGENTS.md':
                    raise ValueError('Output scope paths must be canonical repository files')
            self.file_hashes(paths)  # Resolves symlinks and rejects worktree escapes.
            scopes.append(scope)
        if any(scope != scopes[0] for scope in scopes[1:]):
            return None
        return scopes[0]

    def git_files(self, commit):
        if not isinstance(commit, str) or not re.fullmatch(r'[0-9a-f]{40}', commit): raise ValueError('Acquisition Git commit must be an exact immutable object identity')
        identity = (str(self.repo.resolve()), commit)
        if identity in _GIT_ARTIFACT_SNAPSHOTS: return dict(_GIT_ARTIFACT_SNAPSHOTS[identity])
        cache = getattr(self, '_git_snapshots', {})
        if commit in cache:
            return copy.deepcopy(cache[commit])
        result = {}
        raw = subprocess.run(['git', 'ls-tree', '-rz', '--full-tree', commit], cwd=self.repo, capture_output=True, check=True).stdout
        for entry in raw.split(b'\0'):
            if not entry:
                continue
            metadata, name = entry.split(b'\t', 1)
            path = name.decode('utf-8')
            if path.startswith('.zzzops/'):
                continue
            _, kind, oid = metadata.split()
            if kind != b'blob':
                raise ValueError('Acquisition snapshot requires ordinary Git file entries')
            content = subprocess.run(['git', 'cat-file', 'blob', oid.decode()], cwd=self.repo, capture_output=True, check=True).stdout
            result[path] = 'sha256:' + hashlib.sha256(content).hexdigest()
        self._git_snapshots = {**cache, commit: result}
        if len(_GIT_ARTIFACT_SNAPSHOTS) >= 32: _GIT_ARTIFACT_SNAPSHOTS.pop(next(iter(_GIT_ARTIFACT_SNAPSHOTS)))
        _GIT_ARTIFACT_SNAPSHOTS[identity] = dict(result)
        return copy.deepcopy(result)

    def acquisition_files(self, acquisition):
        baseline = self.git_files(acquisition['git_commit'])
        overrides = acquisition.get('checkout_overrides', {})
        if set(overrides) - set(baseline) or any(baseline.get(p) == h for p, h in overrides.items()):
            raise ValueError('Acquisition checkout identities name unknown Git paths')
        return {**baseline, **overrides}

    def clean_checkout_overrides(self, commit, baseline, actual):
        if set(baseline) != set(actual):
            raise ValueError('Owned phase acquisition requires a clean committed worktree baseline')
        overrides = {}
        for path in baseline:
            if baseline[path] == actual[path]:
                continue
            expected = subprocess.run(['git', 'rev-parse', commit + ':' + path], cwd=self.repo, capture_output=True, text=True, check=True).stdout.strip()
            content = (self.repo / path).read_bytes()
            if 'sha256:' + hashlib.sha256(content).hexdigest() != actual[path]:
                raise ValueError('Checkout bytes changed during acquisition')
            cleaned = subprocess.run(['git', 'hash-object', '--path=' + path, '--stdin'], input=content, cwd=self.repo, capture_output=True, check=True).stdout.decode().strip()
            if expected != cleaned:
                raise ValueError('Owned phase acquisition requires a clean committed worktree baseline')
            overrides[path] = actual[path]
        return overrides

    def workspace_files(self):
        paths = subprocess.run(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'], cwd=self.repo, capture_output=True, text=True, check=True).stdout.split('\0')
        ordinary, files = [], {}
        for relative in paths:
            if not relative or relative.startswith('.zzzops/'): continue
            path = self.repo / relative
            if path.is_symlink():
                # Observe link identity without following it. A declared owned
                # or consumed path still rejects symlinks in its scope guard.
                files[relative] = 'sha256:' + hashlib.sha256(os.fsencode(os.readlink(path))).hexdigest()
            else: ordinary.append(relative)
        files.update(self.file_hashes(ordinary))
        # Missing is an input/output identity, not a file in a produced tree.
        # Thus committing a deletion does not change the workspace identity.
        return {path: value for path, value in files.items() if value != 'missing'}

    def acquisition(self, goal, phase, lease):
        return lease.get('acquisition') or getattr(self, '_recovered_acquisitions', {}).get((goal['key'], phase))

    def check_workspace(self, acquisition, outputs):
        baseline = self.acquisition_files(acquisition)
        if digest(baseline) != acquisition['workspace_digest']:
            raise ValueError('Acquisition Git snapshot does not match its baseline workspace')
        actual = self.workspace_files()
        changed = {path for path in baseline.keys() | actual.keys() if baseline.get(path, 'missing') != actual.get(path, 'missing')}
        if changed - set(outputs):
            raise ValueError('Unexpected output or read input drift outside the reviewed phase scope')
        return baseline, actual

    def owned_versions(self, goal, input_phase=None):
        """Reconstruct connected scoped snapshots; no stored chain or cursor."""
        parent = goal.get('parent') or goal['key']
        children = [self.read(row['key'])[1] for row in self.portfolio()
                    if row.get('parent') == parent and row.get('status') != 'cancelled']
        if not goal.get('parent') and not children:
            children = [goal]
        requester = getattr(self, '_input_requester', goal['key'])
        edges = []
        for child in children:
            scope = self.reviewed_scope(child)
            if scope is None:
                continue
            durable = state(child)
            evidence = child.get('phase_evidence') or self.api.empty_phase_evidence()
            normalized = self.api._phase_evidence.normalize_phase_evidence(evidence)
            _, child_nodes = self.api._workflow_phase_configuration(self.project, child)
            for phase in ('test_design', 'implement'):
                record = evidence['records'].get(phase)
                proof = durable['artifacts'].get(phase)
                review = evidence['reviews'].get(phase)
                withdrawn = any(x['phase'] == phase for x in evidence['withdrawals'])
                if record and proof and proof.get('acquisition') and not withdrawn:
                    reference = record.get('verification') if phase == 'implement' else (record.get('test_design') or {}).get('baseline_failure')
                    accepted = bool(review and review['decision'] == 'approved'
                                    and review['record_hash'] == digest(record)
                                    and review['input_hash'] == record['input_hash']
                                    and review.get('output_hash') == (record.get('output') or {}).get('hash')
                                    and review['reviewer'] != record['actor']
                                    and (not child_nodes[phase]['review'].get('human_approval', False)
                                         or phase in normalized['human_approvals']))
                    order = {'understand': 0, 'decompose': 1, 'plan': 2, 'test_design': 3, 'implement': 4, 'publish': 5}
                    local = child['key'] == requester and input_phase != 'publish' and (
                        goal['key'] != requester or order.get(input_phase, 99) <= order[phase])
                    try:
                        if not reference or reference['hash'] != digest(proof) or self.read_artifact(child['key'], reference) != proof:
                            raise ValueError('Stored proof does not bind the current recorded result')
                        acquired = proof['acquisition']
                        if acquired['input_hash'] != record['input_hash'] or proof['actor'] != record['actor'] or proof['phase'] != phase:
                            raise ValueError('Stored proof does not bind the current recorded result')
                        before = self.acquisition_files(acquired)
                        if digest(before) != acquired['workspace_digest'] or set(proof['outputs']) != set(scope[phase]):
                            raise ValueError('Stored proof does not bind the current recorded result')
                        after = {**before, **proof['outputs']}
                        after = {p: v for p, v in after.items() if v != 'missing'}
                        if digest(after) != proof['workspace']:
                            raise ValueError('Stored proof does not bind the current recorded result')
                        # Pending/rejected output is factual only for its own review
                        # or correction, never for a sibling or downstream consumer.
                        if accepted or local:
                            edges.extend(self.predecessor_edges(child, phase, scope, acquired))
                            edges.append((digest(before), digest(after), before, after, scope[phase]))
                    except ValueError:
                        pass
                lease = durable['leases'].get(phase + ':execute', {})
                acquired = self.acquisition(child, phase, lease)
                if acquired and child['key'] == requester:
                    try:
                        before, after = self.check_workspace(acquired, scope[phase])
                    except ValueError:
                        continue
                    edges.append((digest(before), digest(after), before, after, scope[phase]))
                    edges.extend(self.predecessor_edges(child, phase, scope, acquired))
                    # Old CLI test_design proof has no acquisition. Its exact
                    # reviewed output and before map connect only at this baseline.
                    design = evidence['records'].get('test_design')
                    if phase == 'implement' and design:
                        prior_proof = self.read_artifact(child['key'], design['test_design']['baseline_failure'])
                        if prior_proof['workspace'] == digest(before) and not prior_proof.get('acquisition'):
                            old = dict(before)
                            old.update({p: v for p, v in design['input_envelope']['repository']['snapshot']['files'].items()
                                        if p in scope['test_design']})
                            old = {p: v for p, v in old.items() if v != 'missing'}
                            edges.append((digest(old), digest(before), old, before, scope['test_design']))
        if not edges:
            self._connected_workspaces = set()
            return {}
        connected, versions = {self.workspace_digest()}, {}
        pending = list(edges)
        while pending:
            matching = [edge for edge in pending if edge[1] in connected]
            if not matching:
                break
            for edge in matching:
                pending.remove(edge)
                start, end, before, after, paths = edge
                connected.add(start)
                for path in paths:
                    versions.setdefault(path, set()).update((before.get(path, 'missing'), after.get(path, 'missing')))
        self._connected_workspaces = connected
        return versions

    def predecessor_edges(self, goal, phase, scope, acquisition):
        """Authenticate the immutable correction history referenced at acquisition."""
        edges, seen = [], set()
        reference = acquisition.get('predecessor')
        expected = acquisition['workspace_digest']
        while reference is not None:
            if not valid_predecessor_reference(reference):
                raise ValueError('Malformed correction predecessor reference')
            if reference['hash'] in seen or len(seen) >= 32:
                raise ValueError('Correction predecessor chain cycle/depth limit exceeded')
            seen.add(reference['hash'])
            previous = self.read_artifact(goal['key'], reference)
            if not isinstance(previous, dict) or set(previous) != {'goal', 'phase', 'record', 'review', 'scope'}:
                raise ValueError('Malformed correction predecessor artifact')
            if previous['goal'] != goal['key'] or previous['phase'] != phase or previous['scope'] != scope:
                raise ValueError('Correction predecessor goal, phase or scope differs')
            record, review = previous['record'], previous['review']
            if (not isinstance(record, dict) or not isinstance(review, dict)
                or digest(record.get('input_envelope')) != record.get('input_hash')
                or review.get('decision') != 'changes_requested'
                or review.get('record_hash') != digest(record)
                or review.get('input_hash') != record['input_hash']
                or review.get('output_hash') != (record.get('output') or {}).get('hash')
                or review.get('reviewer') == record.get('actor')):
                raise ValueError('Correction predecessor record/review binding is invalid')
            proof_reference = record.get('verification') if phase == 'implement' else (record.get('test_design') or {}).get('baseline_failure')
            if not proof_reference:
                raise ValueError('Correction predecessor verification proof is missing')
            proof = self.read_artifact(goal['key'], proof_reference)
            acquired = proof.get('acquisition')
            if (not valid_acquisition(acquired) or proof.get('phase') != phase
                or proof.get('actor') != record.get('actor') or not isinstance(proof.get('lease'), str) or not proof['lease']
                or acquired['input_hash'] != record['input_hash']
                or proof.get('workspace') != expected
                or set(proof.get('outputs', {})) != set(scope[phase])):
                raise ValueError('Correction predecessor proof/acquisition snapshot is disconnected')
            before = self.acquisition_files(acquired)
            if digest(before) != acquired['workspace_digest']:
                raise ValueError('Correction predecessor baseline snapshot is invalid')
            after = {**before, **proof['outputs']}
            after = {p: v for p, v in after.items() if v != 'missing'}
            if digest(after) != expected:
                raise ValueError('Correction predecessor output snapshot is disconnected')
            edges.append((digest(before), digest(after), before, after, scope[phase]))
            expected, reference = acquired['workspace_digest'], acquired.get('predecessor')
        return edges

    def correction_predecessor(self, goal, phase, scope, baseline):
        evidence = goal.get('phase_evidence') or self.api.empty_phase_evidence()
        record, review = evidence['records'].get(phase), evidence['reviews'].get(phase)
        if (not review or review['decision'] != 'changes_requested'
            or any(item['phase'] == phase for item in evidence['withdrawals'])):
            return None
        if not record or review['record_hash'] != digest(record):
            raise ValueError('Correction requires exact rejected record/review')
        proof_reference = record.get('verification') if phase == 'implement' else (record.get('test_design') or {}).get('baseline_failure')
        if not proof_reference:
            raise ValueError('Correction verification proof is missing')
        proof = self.read_artifact(goal['key'], proof_reference)
        if proof != state(goal)['artifacts'].get(phase) or proof.get('workspace') != baseline:
            raise ValueError('Correction baseline differs from exact recorded verification')
        previous = {'goal': goal['key'], 'phase': phase, 'record': record, 'review': review, 'scope': scope}
        reference = self.stage_artifact(goal['key'], previous)
        self.predecessor_edges(goal, phase, scope, {'workspace_digest': baseline, 'predecessor': reference})
        return reference

    def recover_acquisition(self, goal, phase, lease, envelope):
        if not isinstance(envelope, dict) or digest(envelope) != lease['input_hash']:
            raise ValueError('Legacy acquisition requires the exact original input envelope/hash')
        if phase != 'implement':
            raise ValueError('Legacy acquisition has no reviewed implementation baseline')
        evidence = goal.get('phase_evidence') or self.api.empty_phase_evidence()
        record, review = evidence['records'].get('test_design'), evidence['reviews'].get('test_design')
        if not record or not review or review['decision'] != 'approved' or review['record_hash'] != digest(record) or any(item['phase'] == 'test_design' for item in evidence['withdrawals']):
            raise ValueError('Legacy acquisition requires a current reviewed test-design baseline')
        proof = self.read_artifact(goal['key'], record['test_design']['baseline_failure'])
        commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=self.repo, capture_output=True, text=True, check=True).stdout.strip()
        baseline = self.git_files(commit)
        if proof['passed'] or digest(baseline) != proof['workspace']:
            raise ValueError('Candidate Git acquisition snapshot differs from the reviewed baseline')
        tests = self.read_artifact(goal['key'], record['output']).get('files', {})
        if not tests or any(baseline.get(path, 'missing') != value for path, value in tests.items()):
            raise ValueError('Candidate snapshot does not contain the exact reviewed test outputs')
        if any(baseline.get(path, 'missing') != value for path, value in envelope['repository']['snapshot']['files'].items()):
            raise ValueError('Candidate acquisition snapshot differs from the original consumed inputs')
        return {'input_envelope': copy.deepcopy(envelope), 'git_commit': commit, 'workspace_digest': proof['workspace']}

    def execution_preflight(self, goal, phase, lease, payload):
        if lease['kind'] != 'execute' or lease['expires_at'] <= time.time() or lease['owner'] != (self.runtime or {}).get('root_id'):
            raise ValueError('A current owned execution lease is required')
        scope = self.reviewed_scope(goal) if phase in {'test_design', 'implement'} else None
        acquired = self.acquisition(goal, phase, lease)
        if phase in {'test_design', 'implement'} and scope is None:
            raise ValueError('Policy or scope evidence changed; current reviewed output scope is unavailable')
        if scope:
            if not acquired:
                acquired = self.recover_acquisition(goal, phase, lease, payload.get('input_envelope'))
                self._recovered_acquisitions = {(goal['key'], phase): acquired}
            if payload.get('input_envelope') is not None and payload['input_envelope'] != acquired['input_envelope']:
                raise ValueError('Verification input envelope differs from the acquired input hash')
            branch = (goal.get('implementation') or {}).get('branch')
            current = subprocess.run(['git', 'branch', '--show-current'], cwd=self.repo, capture_output=True, text=True, check=True).stdout.strip()
            if not branch or current != branch:
                raise ValueError('Execution checkout does not match the assigned implementation branch')
            self.check_workspace(acquired, scope[phase])
            self.predecessor_edges(goal, phase, scope, acquired)
        graph, nodes, live, related = self.context(goal)
        if live[phase].get('provider', {}).get('snapshot', {}).get('migration', {}).get('decision', {}).get('action') == 'block':
            raise ValueError('Affected contract evidence requires investigation before execution')
        frontier = self.api.derive_phase_steps(goal, graph, live, related, review_policy=nodes)
        if phase not in {item['phase'] for item in frontier['execute']}:
            raise ValueError('Ancestor/review inputs changed; assignment is no longer eligible')
        if digest(live[phase]) != lease['input_hash']:
            raise ValueError('Phase inputs changed while work was in flight')
        return acquired, scope

    def pull_request(self, goal):
        value = goal.get('pull_request')
        if not isinstance(value, dict):
            raise ValueError('Current provider PR evidence is unavailable')
        return copy.deepcopy(value)

    def publication_identity(self, goal):
        implementation = goal['implementation']
        if implementation.get('pr'):
            current = self.pull_request(goal)
            return {field: current[field] for field in ('head_oid', 'base_oid', 'base_ref')}
        def rev(ref):
            return subprocess.run(['git', 'rev-parse', ref], cwd=self.repo, capture_output=True, text=True, check=True).stdout.strip()
        return {'head_oid': rev(implementation['branch']), 'base_oid': rev(implementation['base']), 'base_ref': implementation['base']}

    def ci_checks_required(self, pull_request):
        section = policy_section(self.project, 'verification_testing')
        mode = section['configuration'].get('required_ci')
        if mode == 'disabled':
            return False
        if mode == 'existing_only':
            present = pull_request.get('checks_present')
            if not isinstance(present, bool):
                raise ValueError('Provider evidence does not distinguish absent CI checks for existing_only policy')
            return present
        if mode != 'inspect_exact_pr_head':
            raise ValueError('Reviewed verification policy required_ci is unsupported')
        return True

    def classify_merge(self, goal, pull_request):
        evidence = pull_request
        if not self.ci_checks_required(pull_request):
            evidence = {**pull_request, 'checks_verified': True}
        return self.api.classify_pr_merge(goal, evidence, self.repository)

    def workspace_digest(self):
        return digest(self.workspace_files())

    def file_hashes(self, paths):
        result = {}
        for relative in sorted(paths):
            path = (self.repo / relative).resolve()
            if not path.is_relative_to(self.repo.resolve()):
                raise ValueError('Evidence paths must remain inside the repository')
            result[relative] = 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else 'missing'
        return result

    def implementation_children(self, goal):
        """Retain reviewed ownership when a completed child leaves the open index."""
        rows = {row['key']: row for row in self.portfolio()}
        children = {key for key, row in rows.items()
                    if row.get('parent') == goal['key'] and row.get('status') != 'cancelled'}
        evidence = goal.get('phase_evidence') or {}
        phase = self.scope_phase(composition=True)
        record = evidence.get('records', {}).get(phase)
        review = evidence.get('reviews', {}).get(phase)
        if (record and record.get('status') == 'completed' and record.get('output')
                and review and review.get('decision') == 'approved'
                and review.get('record_hash') == digest(record)
                and not any(item['phase'] == phase for item in evidence.get('withdrawals', []))):
            content = self.read_artifact(goal['key'], record['output'])
            for scope in content.get('output_scopes', []) if isinstance(content, dict) else []:
                child = scope.get('child') if isinstance(scope, dict) else None
                if (isinstance(child, int) and not isinstance(child, bool)
                        and child != goal['key'] and scope.get('parent') == goal['key']
                        and (child not in rows or (rows[child].get('parent') == goal['key']
                                                 and rows[child].get('status') != 'cancelled'))):
                    children.add(child)
        return sorted(children)

    def context(self, goal):
        self._input_requester = goal['key']
        goal = {**goal, 'children': self.implementation_children(goal)}
        graph, nodes = self.api._workflow_phase_configuration(self.project, goal)
        related = {}
        if goal.get('parent'):
            _, parent = self.read(goal['parent'])
            parent['children'] = self.implementation_children(parent)
            parent_graph, _ = self.api._workflow_phase_configuration(self.project, parent)
            related[goal['parent']] = {'goal': parent, 'live_inputs': self.inputs(parent, parent_graph)}
        return graph, nodes, self.inputs(goal, graph), related

    def migration_preparation(self, goal, envelope, migration):
        """Link a small, truthful preparation contract; cache by exact content."""
        snapshot = migration.get('release_snapshot', {'status': 'unavailable', 'releases': None})
        bindings = {'goal': goal['key'], 'goal_spec': envelope['goal_spec'],
                    'release_snapshot': snapshot}
        scoped = {**bindings, 'author': None, 'contract': '', 'boundary': '', 'scope': []}
        document = {
            'instructions': (
                'Use this resource only for the affected persistent-state or API compatibility work identified in the goal. '
                'Investigate the actual contract, compatible-state boundary and distribution channels first. '
                'Fill the local file from inspected facts; blank templates are not evidence. '
                'Use a scoped agent investigation OR an actually available owner statement; never invent either or require a new human statement when investigation resolves the facts. '
                'Set contract status to shipped, unreleased or unknown. Preserve or migrate shipped behavior. '
                'Only sufficiently evidenced unreleased project-owned state is eligible for bounded replacement within existing authority; unrelated user, external and deployment state is excluded. '
                'Keep unknown or unavailable facts unresolved: do not infer contract absence from missing releases. '
                'Bind every evidence item to the same goal, goal_spec, release_snapshot, contract ID, boundary and scope. '
                'Fill nonempty action, contract ID and boundary; scope lists bounded project-owned state identities. Investigations require author, rationale, distribution_boundary and observations, with conclusion equal to contract status. Owner evidence requires attributable author and actual statement. '
                'Current release_snapshot must be complete and contains releases with integer id, tag, immutable resolved commit and published_at. '
                'After preparing or correcting the local file, request the existing checkpoint; do not submit the file as a new backend operation. '
                'If evidence remains unresolved after investigation, use the emitted block submission and continue independent work. '
                'Changed goal scope or release facts require reassessment. Replace revoked/contradicted evidence with unknown or remove it; old recorded facts are historical. '
                'Optional discussion links are provenance only, not monitored authority.'),
            'template': {'schema_version': 1, 'repository': self.repository, **bindings, 'action': '',
                         'contracts': [{'id': '', 'boundary': '', 'status': 'unknown', 'scope': [], 'evidence': []}]},
            'evidence_templates': {
                'owner_attestation': {**scoped, 'kind': 'owner_attestation', 'statement': None},
                'contract_investigation': {**scoped, 'kind': 'contract_investigation', 'conclusion': None,
                    'rationale': None, 'distribution_boundary': None,
                    'observations': [
                        {'commit': None, 'path': None, 'release_id': None, 'contract_present': None},
                        {'commit': None, 'path': None, 'finding': None}]},
            },
            'observation_guidance': {
                'development': 'Use release_id null for inspected development observations; fill immutable commit and contract_present from actual inspection. A published commit cannot be hidden behind the development label.',
                'published': 'For each published release, copy release_id and commit exactly from current release_snapshot and inspect the scoped path. Set contract_present to the observed boolean; presence at a published commit contradicts an unreleased conclusion. Cover every current release.',
                'distribution': 'Inspect an immutable commit/path defining the actual distribution boundary and capture its finding. Explain why these observed channels cover this contract; a bare SHA or no releases is insufficient.',
                'path': 'Use a repository-relative inspected path, never an absolute or parent-traversal path. Presence facts for the same immutable contract/commit/path must agree across evidence items.',
            },
        }
        return self.api._policy_context.cached_file(
            self.repo, (json.dumps(document, sort_keys=True, indent=2) + '\n').encode('utf-8'))

    def step(self, number):
        return self.node_checkpoint(number)


    def publication_gate(self, goal):
        child_ids = self.implementation_children(goal)
        missing = sorted(set(child_ids) - {row['key'] for row in self.portfolio()})
        if missing:
            return {'kind': 'dependency', 'assignment': 'root', 'children': missing,
                    'action': 'Resolve the exact child completion evidence named by the reviewed plan before aggregate publication; absence from the open index is not completion proof.'}
        children = [self.read(g['key'])[1] for g in self.portfolio()
                    if g.get('parent') == goal['key'] and g.get('status') != 'cancelled']
        legacy_aggregate = False
        if not children and not goal.get('parent'):
            _, nodes, _, _ = self.context(goal)
            legacy_aggregate = 'implement' not in nodes
        if children or legacy_aggregate:
            skipped = False
            record = (goal.get('phase_evidence') or {}).get('records', {}).get('decompose', {})
            if record.get('status') == 'not_required':
                graph, nodes, live, related = self.context(goal)
                frontier = self.api.derive_phase_steps(goal, graph, live, related, review_policy=nodes)
                pending = frontier['execute'] + frontier['review'] + frontier['blocked']
                skipped = (
                    'decompose' not in frontier['stale']
                    and not any(item.get('phase') == 'decompose' for item in pending)
                    and not any(item == 'decompose:missing_live_input' for item in frontier['diagnostics'])
                )
            if (not children and not skipped) or any(g['status'] != 'done' or not (g.get('phase_evidence') or {}).get('records') for g in children):
                return {'kind': 'dependency', 'assignment': 'root', 'action': 'Complete all implementation child goals before aggregate publication review.', 'children': [g['key'] for g in children]}
        implementation = goal.get('implementation') or {}
        if not implementation.get('branch'):
            if goal.get('parent'):
                return {'kind': 'publication_setup', 'assignment': 'root', 'action': 'Record the implementation branch, base and target before publication.'}
            return None
        managed = {(g.get('implementation') or {}).get('branch') for g in self.portfolio()}
        return self.publication_topology(implementation, self.publication_identity(goal), managed - {None})

    def publication_topology(self, implementation, identity, managed_branches):
        """Validate provider ancestry without changing refs or publication state."""
        # Read provider topology here, never accept a caller-supplied topology as
        # proof that another coordinator has not published in the meantime.
        trunk = 'dev'
        def topology_repair(reason, rows=(), branches=()):
            identities = []
            for row in rows:
                if isinstance(row.get('headRefName'), str) and row['headRefName']:
                    identities.append(row['headRefName'])
                if isinstance(row.get('baseRefName'), str) and row['baseRefName']:
                    identities.append(row['baseRefName'])
                if isinstance(row.get('headRefOid'), str) and row['headRefOid']:
                    identities.append(row['headRefOid'])
                number = row.get('number')
                if type(number) is int and number > 0:
                    identities.append(f'#{number}')
            identities.extend(branch for branch in branches if isinstance(branch, str) and branch)
            identities = list(dict.fromkeys(identities))
            detail = ', '.join(identities) or 'provider PR topology'
            return {
                'kind': 'repair_stack', 'assignment': 'root',
                'action': f'Cannot verify publication topology ({reason}) for {detail}. Preserve each immediate base; follow PROJECT\'s fallback or block publication.',
                'continuation': f'Continue from dev after the root resolves the observed topology for {detail}, preserving immediate base identities.',
                'identities': identities,
            }
        try:
            result = subprocess.run(['gh', 'pr', 'list', '--state', 'open', '--limit', '1000', '--json', 'number,headRefName,baseRefName,headRefOid'], cwd=self.repo, capture_output=True, text=True, check=True)
            observed = json.loads(result.stdout)
        except (subprocess.SubprocessError, OSError, ValueError, TypeError):
            return topology_repair('the provider observation is unavailable or malformed')
        if not isinstance(observed, list) or len(observed) >= 1000:
            return topology_repair('the provider returned an incomplete PR list')
        managed_branches = set(managed_branches(observed) if callable(managed_branches) else managed_branches)
        managed_branches.add(implementation['branch'])
        # An incomplete row makes the provider snapshot unsafe to reason from,
        # even when its relationship to this candidate cannot be established.
        for row in observed:
            if (not isinstance(row, dict) or
                    not isinstance(row.get('headRefName'), str) or not row['headRefName'] or
                    not isinstance(row.get('baseRefName'), str) or not row['baseRefName'] or
                    not isinstance(row.get('headRefOid'), str) or not re.fullmatch('[0-9a-f]{40}', row['headRefOid']) or
                    ('number' in row and (type(row['number']) is not int or row['number'] <= 0))):
                return topology_repair('the provider returned a malformed or incomplete PR row',
                                       [row] if isinstance(row, dict) else [])
        by_head = {}
        for row in observed:
            by_head.setdefault(row['headRefName'], []).append(row)
        candidate_rows = by_head.get(implementation['branch'], [])
        if len(candidate_rows) > 1:
            return topology_repair('multiple open PRs claim the candidate head', candidate_rows)
        candidate_row = candidate_rows[0] if candidate_rows else None
        if candidate_row and (candidate_row['headRefOid'] != identity['head_oid'] or
                              candidate_row['baseRefName'] != identity['base_ref']):
            return topology_repair('the published candidate head or base differs from provider PR evidence',
                                   [candidate_row], [implementation['branch'], identity['base_ref']])

        # Build the candidate ancestry, every open managed stack, and all of
        # their successors. At dev, unmanaged roots are independent work and
        # stay out; below dev, any successor is a relevant fork or continuation.
        path_rows = []
        seeds = {candidate_row['baseRefName'] if candidate_row else
                 implementation.get('base') or implementation.get('target') or trunk}
        seeds.update(row['headRefName'] for row in observed
                     if row['headRefName'] in managed_branches)
        relevant_by_head = {}
        def add_ancestor_chain(branch):
            cursor = branch
            chain_seen = set()
            while cursor != trunk:
                if cursor in chain_seen:
                    return topology_repair('a relevant PR ancestry contains a cycle',
                                           relevant_by_head.values(), [cursor])
                chain_seen.add(cursor)
                matches = by_head.get(cursor, [])
                if len(matches) > 1:
                    return topology_repair('multiple open PRs claim one relevant head', matches)
                if not matches:
                    return topology_repair('a relevant PR ancestor is missing before dev',
                                           relevant_by_head.values(), [cursor, branch])
                row = matches[0]
                relevant_by_head[row['headRefName']] = row
                cursor = row['baseRefName']
            return None
        for seed in sorted(seeds):
            if seed == trunk:
                continue
            problem = add_ancestor_chain(seed)
            if problem:
                return problem
        branches = set(relevant_by_head) | {implementation['branch']}
        if candidate_row:
            relevant_by_head[implementation['branch']] = candidate_row
        pending = list(branches)
        while pending:
            base_branch = pending.pop()
            for row in observed:
                if row['baseRefName'] != base_branch:
                    continue
                if base_branch == trunk or row is candidate_row:
                    continue
                if row['headRefName'] in relevant_by_head:
                    if relevant_by_head[row['headRefName']] is not row:
                        return topology_repair('multiple open PRs claim one relevant head',
                                               [relevant_by_head[row['headRefName']], row])
                    continue
                relevant_by_head[row['headRefName']] = row
                pending.append(row['headRefName'])
        relevant = list(relevant_by_head.values())
        duplicates = [row for matches in by_head.values() if len(matches) > 1
                      for row in matches if row in relevant]
        if duplicates:
            return topology_repair('multiple open PRs claim the same head branch', duplicates)
        children = {}
        for row in relevant:
            children.setdefault(row['baseRefName'], []).append(row)
        forks = [row for matches in children.values() if len(matches) > 1 for row in matches]
        if forks:
            return topology_repair('the relevant PR graph has multiple successors from one base', forks)

        # Order the whole relevant provider chain so an unpublished candidate
        # cannot bypass an already-open successor of its declared base. An
        # observed candidate is removed only after every row has been validated.
        ordered, base = [], trunk
        remaining = list(relevant)
        while remaining:
            matches = [row for row in remaining if row['baseRefName'] == base]
            if len(matches) != 1:
                return topology_repair('the relevant managed PR graph is disconnected from dev',
                                       remaining, [base])
            row = matches[0]
            remaining.remove(row)
            ordered.append({'branch': row['headRefName'], 'base': row['baseRefName'],
                            'head': row['headRefOid']})
            base = row['headRefName']
        published = next((i for i, row in enumerate(ordered)
                          if row['branch'] == implementation['branch']), None)
        if published is not None:
            ordered = ordered[:published]
        def rev(ref):
            return subprocess.run(['git', 'rev-parse', ref], cwd=self.repo, capture_output=True, text=True, check=True).stdout.strip()
        candidate = {'branch': implementation['branch'], 'base': identity['base_ref'], 'base_head': identity['base_oid'], 'head': identity['head_oid']}
        if implementation.get('pr') and (rev(implementation['branch']) != identity['head_oid'] or rev(implementation['base']) != identity['base_oid']):
            return {'kind': 'repair_stack', 'assignment': 'root',
                    'action': f"Local {implementation['branch']} / {implementation['base']} do not match provider candidate {identity['head_oid']} and base {identity['base_oid']}; Synchronize the exact refs before publication.",
                    'continuation': f"The root continues from dev after reconciling {implementation['branch']} onto its declared immediate base {implementation['base']}; preserve existing PR heads and re-run exact-head checks.",
                    'identities': [implementation['branch'], implementation['base'], identity['head_oid'], identity['base_oid'],
                                   *(row['baseRefName'] for row in relevant if row['headRefName'] == implementation['base'])],
                    'head': identity['head_oid'], 'base': identity['base_oid']}
        directive = self.api.linear_publication_next_step(ordered, candidate, trunk=trunk)
        if directive['action'] != 'publish_linear':
            tip = directive.get('tip') or {}
            tip_rows = [row for row in relevant if row.get('headRefName') == tip.get('branch')]
            details = [tip.get('branch'), *(row.get('baseRefName') for row in tip_rows)]
            return {**directive,
                    **topology_repair('the candidate base does not match the exact current PR tip', tip_rows, details),
                    'publication_directive': directive}
        return None


    def mutate(self, number, payload, *, _proof=None):
        return self.node_mutate(number, payload)


    def stop_completed_heartbeat(self, number, payload, durable, response):
        token = payload.get('lease')
        leases = durable.get('leases', [])
        if isinstance(leases, dict): leases = leases.values()
        if not token or any(v['token'] == token for v in leases):
            return response
        try:
            self.api._heartbeat.stop_heartbeat(repo=self.repo, root_id=(self.runtime or {}).get('root_id'),
                goal=number, phase=json.dumps(payload.get('node'), sort_keys=True), token=token)
        except (OSError, ValueError) as exc:
            # The durable operation already succeeded. Its exact replay retries
            # this local, idempotent cleanup without reapplying goal evidence.
            response['next_steps'].append({'kind': 'repair', 'assignment': 'root',
                'goal': number, 'node': payload.get('node'), 'actor': payload.get('actor'),
                'action': 'The durable submission succeeded. Resolve the local heartbeat error, then replay this exact request to stop monitoring the completed lease.',
                'reason': str(exc), 'submission': copy.deepcopy(payload),
                'command': ['--intent', 'execute', '--goal', str(number), '--runtime', '<runtime.json>', '--input', '<submission.json>']})
        return response



    def node_snapshot(self, number, *, publication_probe=False):
        """Read exact scoped records; only relationship consumers request closure."""
        ev = self.api._phase_evidence
        snapshots, artifacts, issues, bootstrap = {}, {}, {}, {}
        published, validated = {}, set()
        def remember(value):
            key = digest(value); artifacts[key] = value
            return {'hash': key, 'uri': 'urn:' + key}
        def load(n):
            if n in snapshots: return snapshots[n]
            issue = self.adapter.get_issue(n); issues[n] = issue
            envelope = self.api.parse_managed_goal(issue.get('body', ''), n)
            if not envelope: raise ValueError(f'Goal {n} has no readable identity envelope')
            if envelope['schema_version'] == 1:
                if str(issue.get('state', '')).lower() == 'closed': raise ValueError(f'Archived predecessor {n} requires reviewed historical evidence equivalence')
                entries = policy_section(self.project, 'workflow_adherence')['configuration'].get('migration_entries', [])
                entry = next((r['graph'] for r in entries if r.get('from') == 1 and r.get('to') == 2), None)
                if entry is None: raise ValueError('Schema version 1 requires trusted reviewed migration entry; no legacy execution')
                if envelope.get('workflow', {}).get('leases'): raise ValueError('Predecessor worker ownership must be observed stopped before conversion')
                ev.validate_graph(entry)
                source = {'type': 'migration_source', 'content': copy.deepcopy(issue), 'producer': None,
                          'provenance': {'actor': (self.runtime or {}).get('root_id', ''), 'source': None, 'policy': digest(self.project['policy'])}}
                payload = {'spec': remember(source), 'graph': remember(entry), 'evidence': [], 'operational': {'leases': [], 'receipts': []}}
                envelope = {'schema_version': 2, 'repository': self.repository, 'issue': n, 'revision': envelope['revision'], 'state': 'open', 'parent': envelope['parent'], 'payload': remember(payload)}
                bootstrap[n] = copy.deepcopy(issue)
            if envelope['repository'] != self.repository: raise ValueError('Goal repository identity mismatch')
            def resolve(ref):
                ev.validate_ref(ref)
                if ref['uri'].startswith('git:'):
                    match = re.fullmatch(r'git:([0-9a-f]{40}):(.+)', ref['uri'])
                    if not match or match[2].startswith('/') or '..' in Path(match[2]).parts: raise ValueError('Published artifact locator requires exact commit and repository path')
                else:
                    owner = self.node_ref_goal(ref, n)
                if ref['hash'] not in artifacts:
                    if ref['uri'].startswith('git:'):
                        result = subprocess.run(['git', 'show', match[1] + ':' + match[2]], cwd=self.repo, capture_output=True, check=False)
                        if result.returncode: raise ValueError('Published artifact read failed')
                        raw = result.stdout
                        if len(raw) > 1048576 or 'sha256:' + hashlib.sha256(raw).hexdigest() != ref['hash']: raise ValueError('Published artifact bytes hash or semantic size bound rejected')
                        artifacts[ref['hash']] = comment_store.strict_json(raw.decode('utf-8'))
                        published[ref['hash']] = raw
                    else:
                        artifacts[ref['hash']] = self.artifact_index(owner).observe(ref['hash'])[0]
                value = artifacts[ref['hash']]
                if ref['hash'] not in published and ref['hash'] not in validated:
                    if digest(value) != ref['hash']: raise ValueError('Artifact checksum mismatch')
                    validated.add(ref['hash'])
                return value
            payload = resolve(envelope['payload'])
            ev.contract_fields(payload, {'spec', 'graph', 'evidence', 'operational'}, 'Payload')
            ev.contract_fields(payload['operational'], {'leases', 'receipts'}, 'Operational payload')
            if not isinstance(payload['evidence'], list): raise ValueError('Evidence must be an ordered Ref array')
            graph = resolve(payload['graph']); ev.validate_graph(graph)
            source_artifact = resolve(payload['spec'])
            if source_artifact.get('type') == 'migration_source':
                entries = policy_section(self.project, 'workflow_adherence')['configuration'].get('migration_entries', [])
                if not any(row.get('from') == 1 and row.get('to') == 2 and row.get('graph') == graph for row in entries):
                    raise ValueError('Prepared migration graph differs from trusted current policy entry')
            snapshot = {'envelope': envelope, 'payload': payload, 'graph': graph, 'resolve': resolve}
            snapshots[n] = snapshot
            # Current ownership needs its exact durable start receipt, not
            # every historical response. Metadata only locates candidates;
            # payload membership and immutable Ref validation establish the pin.
            receipt_refs = {row['result']['hash']: row['result'] for row in payload['operational']['receipts']}
            tokens = {row['token'] for row in payload['operational']['leases']}
            acquisition_receipts = {}
            if tokens:
                for envelope_record in self.artifact_index(n).envelopes:
                    context = envelope_record.get('context') or {}
                    response = context.get('response')
                    if not isinstance(response, dict): continue
                    if set(response) == {'hash', 'uri'}:
                        token = (context.get('ownership') or {}).get('token')
                        if context.get('acquisition') and token in tokens and response['hash'] in receipt_refs:
                            acquisition_receipts[token] = receipt_refs[response['hash']]
                    else:
                        for step in response.get('next_steps', []):
                            token = step.get('lease', {}).get('token')
                            if token not in tokens or not step.get('bind'): continue
                            identity = digest(response)
                            if identity in receipt_refs: acquisition_receipts[token] = receipt_refs[identity]
            snapshot['acquisition_receipts'] = acquisition_receipts
            pending = [(ref, n) for ref in [payload['spec'], *payload['evidence'], *acquisition_receipts.values()]]
            visited = set()
            def references(value):
                if isinstance(value, dict):
                    if value.get('schema_version') == 2 and 'payload' in value and 'repository' in value: return
                    if set(value) == {'hash', 'uri'} and isinstance(value['hash'], str):
                        if isinstance(value['uri'], str) and value['uri'].startswith(('urn:', 'zzzops:', 'git:')): yield value
                    else:
                        for child in value.values(): yield from references(child)
                elif isinstance(value, list):
                    for child in value: yield from references(child)
            while pending:
                ref, origin = pending.pop()
                owner = origin if ref['uri'].startswith('git:') else self.node_ref_goal(ref, origin)
                located = self.node_ref(ref['hash'], owner) if ref['uri'] == 'urn:' + ref['hash'] else ref
                if ref['hash'] in visited: continue
                visited.add(ref['hash']); value = resolve(located)
                pending.extend((child, owner) for child in references(value))
            return snapshot
        selected = load(number)
        def selectors(value):
            if isinstance(value, dict):
                if value.get('kind') in ('node', 'member', 'join') and 'goal' in value: yield value
                else:
                    for child in value.values(): yield from selectors(child)
            elif isinstance(value, list):
                for child in value: yield from selectors(child)
        pending = [number]; visited = set()
        while pending:
            n = pending.pop()
            if n in visited: continue
            visited.add(n); snapshot = snapshots[n]; envelope = snapshot['envelope']
            children, known = {}, False
            refs = list(selectors(snapshot['graph']))
            if any(ref['goal'] == '#children' for ref in refs):
                metadata = getattr(self.adapter, 'list_issue_metadata', None)
                if metadata:
                    cursor, cursors, candidates = None, set(), set()
                    try:
                        while True:
                            page = metadata(cursor)
                            if page.get('repository') != self.repository: raise ValueError('Relationship repository mismatch')
                            candidates.update(row['number'] for row in page['issues'])
                            info = page['page_info']
                            if not info['has_next_page']: break
                            cursor = info['end_cursor']
                            if cursor is None or cursor in cursors: raise ValueError('Incomplete relationship pagination')
                            cursors.add(cursor)
                        for candidate in sorted(candidates):
                            if type(candidate) is not int or candidate <= 0: raise ValueError('Invalid relationship candidate identity')
                            if candidate in snapshots:
                                child_envelope = snapshots[candidate]['envelope']
                            else:
                                candidate_issue = self.adapter.get_issue(candidate)
                                child_envelope = self.api.parse_managed_goal(candidate_issue.get('body', ''), candidate)
                                if not child_envelope or child_envelope.get('repository') != self.repository:
                                    raise ValueError('Unknown canonical relationship envelope for ' + str(candidate))
                            parent_reader = getattr(self.adapter, 'get_parent_issue', None)
                            if parent_reader and parent_reader(candidate) != child_envelope['parent']: raise ValueError('Provider/canonical parent relationship mismatch for ' + str(candidate))
                            if child_envelope['parent'] == n: children[str(candidate)] = remember(child_envelope)
                        native = getattr(self.adapter, 'get_sub_issues', None)
                        if native and {row['number'] for row in native(n)} != {int(key) for key in children}: raise ValueError('Native/canonical parent relationship mismatch')
                        known = True
                    except (ValueError, KeyError, RuntimeError, OSError) as exc:
                        snapshot['relationship_error'] = str(exc)
                        children, known = {}, False
            relation = {'repository': self.repository, 'subject': n, 'subject_envelope': remember(envelope),
                        'parent': {'known': True, 'value': envelope['parent']}, 'children': {'known': known, 'envelopes': children}}
            snapshot['relationship'] = relation
            snapshot['context_ref'] = remember({'type': 'relationship_context', 'content': relation, 'producer': None,
                'provenance': {'actor': 'host', 'source': None, 'policy': digest(self.project['policy'])}})
            related = {ref['goal'] for ref in refs if type(ref['goal']) is int}
            if any(ref['goal'] == '#parent' for ref in refs) and envelope['parent'] is not None: related.add(envelope['parent'])
            related.update(int(key) for key in children)
            for target in related:
                if target == n: continue
                try: load(target); pending.append(target)
                except (ValueError, KeyError, OSError) as exc:
                    snapshot['relationship_error'] = 'Required related evidence is unknown: ' + str(exc)
        # Missing historical payload content does not hide a cycle already
        # proven by the current addressed graphs and canonical parent edges.
        # This diagnostic grants no membership completeness or missing evidence.
        edges = {}
        for n, snapshot in snapshots.items():
            for node in snapshot['graph']['nodes']:
                refs = [*node['requires'], *(binding['producer']['node'] for binding in node['inputs'].values() if 'node' in binding['producer'])]
                dependencies = set()
                for ref in refs:
                    if ref['kind'] != 'node': continue
                    selected_goals = ([ref['goal']] if type(ref['goal']) is int else [n] if ref['goal'] == '#this' else
                                      [snapshot['envelope']['parent']] if ref['goal'] == '#parent' else
                                      [child for child, value in snapshots.items() if value['envelope']['parent'] == n])
                    dependencies.update((target, ref['node']) for target in selected_goals if target in snapshots)
                edges[(n, node['id'])] = dependencies
        def graph_cycle(key, active, completed):
            if key in active: return active[active.index(key):] + [key]
            if key in completed: return None
            for dependency in edges.get(key, set()):
                cycle = graph_cycle(dependency, active + [key], completed)
                if cycle: return cycle
            completed.add(key)
            return None
        for n, snapshot in snapshots.items():
            if 'relationship' not in snapshot: continue
            cycle = next((cycle for key in edges if key[0] == n and (cycle := graph_cycle(key, [], set()))), None)
            if cycle:
                snapshot['relationship_error'] = snapshot.get('relationship_error', '') + '; Projected dependency cycle: ' + ' -> '.join(str(goal) + '/' + node for goal, node in cycle)
                snapshot['relationship'] = copy.deepcopy(snapshot['relationship'])
                snapshot['relationship']['children']['known'] = False
                snapshot['context_ref'] = remember({'type': 'relationship_context', 'content': snapshot['relationship'], 'producer': None,
                    'provenance': {'actor': 'host', 'source': None, 'policy': digest(self.project['policy'])}})
        # Some scoped discovery candidates were needed only for parent coverage.
        # They are not evaluated unless referenced by the selected graph closure.
        closure = {n: snapshots[n] for n in visited}
        context = {'goal': number, 'policy': self.project['policy'], 'runtime': self.runtime, 'artifacts': artifacts, 'goals': closure, 'published_bytes': published, 'workspace_probe': True}
        result = ev.derive_task_steps(selected['graph'], selected['payload'], context)
        workspaces = self.node_workspace_context(closure, result, result['artifacts'])
        publications = {} if publication_probe else self.node_publication_context(closure, result, result['artifacts'])
        context.update(workspace_probe=False, workspaces=workspaces, artifacts=result['artifacts'])
        if not publication_probe: context['publications'] = publications
        result = ev.derive_task_steps(selected['graph'], selected['payload'], context)
        return {'number': number, 'issue': issues[number], **selected, 'snapshots': snapshots, 'issues': issues, 'bootstrap': bootstrap,
                'projection': result, 'artifacts': result['artifacts'], 'published': published, 'workspaces': workspaces, 'publications': publications}

    def node_publication_context(self, snapshots, projection, artifacts):
        """Observe provider facts only for explicitly declared publication work."""
        ev = self.api._phase_evidence
        owners = {ref['hash']: (key, result) for key, (_, result) in projection['current'].items() for ref in result['outputs'].values()}
        contexts, observations = {}, {}
        for key, state in projection['states'].items():
            if 'repository_publication' not in state['contract']['executor']['resources'] or state['state'] == 'blocked': continue
            try:
                selected = [(binding, artifacts[binding['source']['hash']]) for binding in state['inputs']
                            if artifacts[binding['source']['hash']].get('type') == 'repository_context']
                if len(selected) != 1: raise ValueError('Publication requires one exact declared repository context input')
                binding, blob = selected[0]; reference = binding['source']; value = blob['content']
                owner_key, owner = owners[reference['hash']]
                root = (self.runtime or {}).get('root_id')
                if binding['mode'] != 'identity' or binding['path'] or owner['executor'] != root or projection['states'][owner_key]['contract']['executor']['role'] != 'root': raise ValueError('Repository context requires authenticated current root output')
                declared = state['contract']['executor']['authority']
                targets = [target for row in state['resolutions'] if row['selector'] == declared['subject'] for target in row['targets']]
                if owner['node'] not in targets or owner['outputs'].get(declared['output']) != reference: raise ValueError('Publication context differs from declared authority selector')
                permits = []
                for item in state['inputs']:
                    artifact = artifacts[item['source']['hash']]
                    if artifact.get('type') not in {'repository_authorization', 'publication_authorization'}: continue
                    issuer = owners.get(item['source']['hash'])
                    if item['mode'] != 'identity' or item['path'] or not issuer or issuer[1]['executor'] != root or projection['states'][issuer[0]]['contract']['executor']['role'] != 'root': continue
                    content = artifact['content']
                    if content.get('policy') != digest(self.project['policy']) or content.get('decision') != 'approved': continue
                    if artifact['type'] == 'repository_authorization' and content.get('context') != reference: continue
                    if artifact['type'] == 'publication_authorization':
                        subject = owners.get(content.get('subject', {}).get('hash'))
                        if not subject or not any(row['source'] == reference for row in subject[1]['inputs']): continue
                    permits.append(item['source'])
                if len(permits) != 1: raise ValueError('Publication requires current reviewed root authorization for exact context')
                if set(value) != {'branch', 'base', 'target', 'pr'} or any(not isinstance(value[name], str) or not value[name] for name in ('branch', 'base', 'target')): raise ValueError('Invalid repository context')
                if value['pr'] is not None and (not isinstance(value['pr'], str) or not re.fullmatch(r'https://github.com/' + re.escape(self.repository) + r'/pull/[1-9][0-9]*', value['pr'])): raise ValueError('Publication requires an exact same-repository PR')
                cache_key = (key[0], reference['hash'])
                if value['pr'] is None:
                    def local_oid(ref):
                        return subprocess.run(['git', 'rev-parse', '--verify', 'refs/heads/' + ref], cwd=self.repo, capture_output=True, text=True, check=True).stdout.strip()
                    observations[cache_key] = {'repository': self.repository, 'head_oid': local_oid(value['branch']), 'base_oid': local_oid(value['base']), 'base_ref': value['base']}
                if cache_key not in observations:
                    facts, _, _ = self.api._github_pull_request_states(self.repo, 'gh', [{'number': key[0]}], {key[0]: {'repository_context': value}})
                    observations[cache_key] = facts.get(key[0])
                facts = observations[cache_key]
                if not isinstance(facts, dict) or facts.get('repository') != self.repository or facts.get('base_ref') != value['base']: raise ValueError('Provider publication repository/base identity mismatch or unknown')
                for name in ('head_oid', 'base_oid'):
                    if not isinstance(facts.get(name), str) or not re.fullmatch('[0-9a-f]{40}', facts[name]): raise ValueError('Provider publication head/base is unknown')
                if not facts.get('merged'):
                    repair = self.publication_topology(value, facts, self.node_managed_publication_branches)
                    if repair:
                        contexts[key] = {'error': repair['action'], 'repair': repair}
                        continue
                ci = 'verified' if facts.get('checks_verified') is True else 'absent' if facts.get('checks_present') is False else 'unverified' if facts.get('checks_present') is True else 'unknown'
                observed = {name: facts[name] for name in ('repository', 'head_oid', 'base_oid', 'base_ref')}
                observed.update(pr=value['pr'], ci=ci)
                semantic = {**observed, 'context': reference}
                if policy_section(self.project, 'verification_testing')['configuration']['required_ci'] == 'disabled': semantic.pop('ci')
                artifact = {'type': 'publication_snapshot', 'content': semantic, 'producer': None,
                            'provenance': {'actor': 'host', 'source': None, 'policy': digest(self.project['policy'])}}
                identity = digest(artifact); artifacts[identity] = artifact
                contexts[key] = {'binding': {'hash': identity, 'uri': 'urn:' + identity}, 'context': value, 'context_ref': reference,
                                 'observed': observed, 'provider': facts, 'base_branch': value['base'], 'base_commit': facts['base_oid']}
            except (ValueError, KeyError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
                contexts[key] = {'error': 'Publication provider/authority: ' + str(exc)}
        return contexts

    def node_managed_publication_branches(self, observed):
        """Discover managed heads from current authenticated generic root evidence."""
        branches = set()
        heads = {row['headRefName'] for row in observed if isinstance(row, dict) and isinstance(row.get('headRefName'), str)}
        root = (self.runtime or {}).get('root_id')
        for goal in self.portfolio():
            if goal.get('schema_version') != 2 or goal.get('status') in {'done', 'cancelled'}: continue
            number = goal['key']
            def read(ref):
                value = self.read_artifact(number, ref)
                return json.loads(value) if isinstance(value, str) else value
            envelope = self.api.parse_managed_goal(self.adapter.get_issue(number)['body'], number)
            payload = read(envelope['payload']); graph = read(payload['graph'])
            # Locate possible context outputs without evaluating unrelated
            # workspace/relationship consumers. This filter grants no authority.
            declarations = [*graph['nodes'], *(row['template'] for row in graph['task_sets'])]
            slots = {node['id']: {name for name, contract in node['outputs'].items()
                                 if contract.get('type') == 'repository_context'}
                     for node in declarations}
            if not any(slots.values()): continue
            candidate = False
            for ref in payload['evidence']:
                result = read(ref)
                if result.get('type') != 'result': continue
                result = result['content']
                for name in slots.get(result['node']['node'], set()):
                    if name not in result['outputs']: continue
                    context = read(result['outputs'][name])
                    if context.get('type') == 'repository_context' and context['content'].get('branch') in heads: candidate = True
            if not candidate: continue
            snapshot = self.node_snapshot(number, publication_probe=True)
            projection = snapshot['projection']; artifacts = snapshot['artifacts']
            owners = {ref['hash']: (key, result) for key, (_, result) in projection['current'].items() for ref in result['outputs'].values()}
            for identity, (key, result) in owners.items():
                artifact = artifacts[identity]
                if artifact.get('type') != 'repository_authorization': continue
                if result['executor'] != root or projection['states'][key]['contract']['executor']['role'] != 'root': continue
                value = artifact['content']; reference = value.get('context', {})
                if value.get('decision') != 'approved' or value.get('policy') != digest(self.project['policy']): continue
                owner = owners.get(reference.get('hash'))
                if not owner or owner[1]['executor'] != root or projection['states'][owner[0]]['contract']['executor']['role'] != 'root': continue
                if not any(row['source'] == reference and row['mode'] == 'identity' and not row['path'] for row in result['inputs']): continue
                context = artifacts[reference['hash']]
                if context.get('type') == 'repository_context' and isinstance(context['content'].get('branch'), str): branches.add(context['content']['branch'])
        return branches

    def node_ci_required(self, observed):
        if observed.get('pr') is None: raise ValueError('An unpublished context has no provider CI or merge authority')
        mode = policy_section(self.project, 'verification_testing')['configuration']['required_ci']
        if mode == 'disabled': return
        if observed.get('ci') == 'verified' or mode == 'existing_only' and observed.get('ci') == 'absent': return
        raise ValueError('Current exact provider CI/checks are unknown, incomplete or unverified')

    def node_workspace_paths(self, paths, *, consumed=False):
        if not isinstance(paths, list) or len(paths) != len(set(paths)): raise ValueError('Workspace allocation requires distinct finite paths')
        for relative in paths:
            if not isinstance(relative, str) or not relative or relative.startswith(('/', '.git/')) or (relative.startswith('.zzzops/') and not (consumed and re.fullmatch(r'\.zzzops/migration/[1-9][0-9]*\.json', relative))) or relative in {'.git', '.zzzops', 'AGENTS.md'} or any(c in relative for c in ('\\', '*', '?', '[', ']')) or any(part in ('', '.', '..') for part in relative.split('/')):
                raise ValueError('Workspace allocation path is protected, noncanonical or contains traversal/glob')
            path = self.repo / relative
            if not path.resolve().is_relative_to(self.repo.resolve()) or path.is_symlink() or path.is_dir(): raise ValueError('Workspace allocation path escapes or names a symlink/directory')
        return self.file_hashes(paths)

    def node_workspace_context(self, snapshots, projection, artifacts):
        """Observe repository facts and bind the explicit workspace adapter.

        The graph supplies all semantic prerequisites. This adapter checks the
        selected allocation and authenticated evidence, then supplies immutable
        raw snapshots to the same pure evaluator.
        """
        ev = self.api._phase_evidence
        states = projection['states']; work = {key: state for key, state in states.items() if 'repository_workspace' in state['contract']['executor']['resources']}
        actual = self.workspace_files()
        head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=self.repo, capture_output=True, text=True, check=True).stdout.strip()
        committed = self.git_files(head)
        current_outputs = {ref['hash']: (key, result) for key, (_, result) in projection['current'].items() for ref in result['outputs'].values()}
        all_results = [(ref, artifacts[ref['hash']]['content']) for snapshot in snapshots.values() for ref in snapshot['payload']['evidence']]
        def remember(value):
            identity = digest(value); artifacts[identity] = value
            return {'hash': identity, 'uri': 'urn:' + identity}
        verified_content = set()
        def content(ref):
            value = artifacts[ref['hash']]
            if ref['hash'] not in verified_content:
                if digest(value) != ref['hash']: raise ValueError('Workspace immutable proof checksum mismatch')
                verified_content.add(ref['hash'])
            return value
        def authority(state):
            selected = []
            for binding in state['inputs']:
                value = content(binding['source'])
                if value.get('type') == 'workspace_allocation' and binding['path']:
                    entry = ev.selected_path(value['content'], binding['path'])
                    selected.append((binding, entry))
            local = [(binding, entry) for binding, entry in selected if current_outputs.get(binding['source']['hash'], (None,))[0] and current_outputs[binding['source']['hash']][0][0] == state['node']['goal']]
            if len(local) != 1 or local[0][1].get('task') != state['node']: raise ValueError('Workspace requires one exact allocation input for this task generation')
            binding, entry = local[0]; manifest = binding['source']
            declared = state['contract']['executor']['authority']
            permitted = [target for resolution in state['resolutions'] if resolution['selector'] == declared['subject'] for target in resolution['targets']]
            producer_key, producer = current_outputs[manifest['hash']]
            if producer['node'] not in permitted or producer['outputs'].get(declared['output']) != manifest: raise ValueError('Workspace allocation differs from declared authority selector')
            self.node_workspace_paths(entry['owned']); self.node_workspace_paths(entry['consumed'], consumed=True)
            def approvals(reference, expected_entry, goal):
                matches = []
                for candidate in state['inputs']:
                    blob = content(candidate['source'])
                    if blob.get('type') != 'workspace_authorization': continue
                    value = blob['content']; owner = current_outputs.get(candidate['source']['hash'])
                    if not owner or owner[0][0] != goal or value.get('manifest') != reference: continue
                    if candidate['mode'] != 'identity' or value.get('policy') != digest(self.project['policy']) or expected_entry['task'] not in value.get('tasks', []) or value.get('decision') != 'approved': raise ValueError('Workspace authorization policy/task/manifest mismatch')
                    matches.append((candidate['source'], owner[1], states[owner[0]]))
                roots = [row for row in matches if row[2]['contract']['executor']['role'] == 'root' and row[1]['executor'] == (self.runtime or {}).get('root_id')]
                reviewers = [row for row in matches if row[1]['executor'] != producer['executor'] and row[2]['contract']['independent_of']]
                if len(roots) != 1 or len(reviewers) != 1 or roots[0][0] == reviewers[0][0]: raise ValueError('Workspace requires current independent authorization and root approval')
                return reviewers[0][0], roots[0][0]
            authorization, approval = approvals(manifest, entry, state['node']['goal'])
            parent = snapshots[state['node']['goal']]['envelope']['parent']
            if parent is not None:
                grants = [(b, e) for b, e in selected if current_outputs.get(b['source']['hash'], (None,))[0] and current_outputs[b['source']['hash']][0][0] == parent]
                if len(grants) != 1 or grants[0][1] != entry: raise ValueError('Immediate parent allocation grant is missing or mismatched')
                approvals(grants[0][0]['source'], grants[0][1], parent)
            return {'allocation': manifest, 'authorization': authorization, 'approval': approval, 'entry': entry}
        def raw(acquisition):
            required = {'git_commit', 'workspace_digest', 'input_hash', 'checkout_overrides', 'files', 'inputs', 'resolutions', 'contract'}
            if not isinstance(acquisition, dict) or not required <= set(acquisition): raise ValueError('Workspace acquisition raw pins are missing or partial')
            files = acquisition['files']; overrides = acquisition['checkout_overrides']
            if not isinstance(files, dict) or digest(files) != acquisition['workspace_digest'] or not isinstance(overrides, dict): raise ValueError('Workspace acquisition raw snapshot mismatch')
            git = self.git_files(acquisition['git_commit'])
            for path, value in overrides.items():
                self.node_workspace_paths([path])
                if path not in git or not re.fullmatch(r'sha256:[0-9a-f]{64}', str(value)) or files.get(path) != value or git[path] == value: raise ValueError('Acquisition checkout overrides are invalid')
            return files
        candidates = []
        for result_ref, result in all_results:
            key = ev.task_key(result['node'])
            if key not in work: continue
            for output in result['outputs'].values():
                source = content(output).get('provenance', {}).get('source')
                if not source: continue
                try:
                    proof = content(source); acquisition = proof['acquisition']; before = raw(acquisition)
                    if proof['acquisition_hash'] != digest(acquisition) or proof['input_hash'] != acquisition['input_hash'] or proof['actor'] != result['executor'] or proof['node'] != result['node']: raise ValueError('Workspace proof/result acquisition identity differs')
                    after = {p: v for p, v in {**before, **proof['outputs']}.items() if v != 'missing'}
                    if digest(after) != proof['workspace']: raise ValueError('Workspace proof output snapshot differs')
                    reviews = [(r, item) for r, item in all_results if item['executor'] != result['executor'] and any(binding['source'] in result['outputs'].values() for binding in item['inputs']) and ev.task_key(item['node']) in states and states[ev.task_key(item['node'])]['contract']['independent_of']]
                    candidates.append({'key': key, 'result': result_ref, 'value': result, 'proof': source, 'data': proof, 'before': before, 'after': after, 'reviews': reviews})
                except (ValueError, KeyError, subprocess.SubprocessError):
                    candidates.append({'key': key, 'result': result_ref, 'error': 'Workspace proof/acquisition snapshot is invalid'})
                break
        # Only complete before/after edges connect versions. A bag of previously
        # seen file hashes cannot authorize a disconnected mixed checkout.
        edges = [(row['before'], row['after']) for row in candidates if 'error' not in row]
        accepted_edges = [(row['before'], row['after']) for row in candidates if 'error' not in row and row['reviews']]
        for snapshot in snapshots.values():
            for lease in snapshot['payload']['operational']['leases']:
                key = ev.task_key(lease['node'])
                if key not in work: continue
                try:
                    grant = authority(work[key]); before = raw(lease['acquisition'])
                    changed = {p for p in before.keys() | actual.keys() if before.get(p, 'missing') != actual.get(p, 'missing')}
                    if not changed - set(grant['entry']['owned']): edges.append((before, actual))
                except (ValueError, KeyError, subprocess.SubprocessError): pass
        def connected(start, *, accepted_only=False):
            pending, seen = [start], set()
            while pending:
                value = pending.pop(); identity = digest(value)
                if value == actual: return True
                if identity in seen: continue
                seen.add(identity)
                pending.extend(after for before, after in (accepted_edges if accepted_only else edges) if before == value)
            return False
        # Ordinary repository readers bind Git-clean content identity. Resource
        # acquisitions below retain raw bytes, including CRLF checkout overrides.
        # Normalize only exact host-validated raw/Git pairs, never arbitrary
        # historical hashes or a disconnected combination of accepted outputs.
        clean_pairs = {}
        for path in actual.keys() & committed.keys():
            if actual[path] == committed[path]: continue
            try:
                self.clean_checkout_overrides(head, {path: committed[path]}, {path: actual[path]})
                clean_pairs[(path, actual[path])] = committed[path]
            except ValueError: pass
        for row in candidates:
            if 'error' in row: continue
            acquisition = row['data']['acquisition']
            git = self.git_files(acquisition['git_commit'])
            for path, raw_hash in acquisition['checkout_overrides'].items():
                clean_pairs[(path, raw_hash)] = git[path]
        for snapshot in snapshots.values():
            for lease in snapshot['payload']['operational']['leases']:
                reference = snapshot['acquisition_receipts'].get(lease['token'])
                if reference is None: continue
                acquisition = lease.get('acquisition')
                try:
                    receipt = content(reference)
                    pins = [step['lease']['acquisition'] for step in receipt.get('next_steps', []) if step.get('lease', {}).get('token') == lease['token'] and step['lease'].get('acquisition')]
                    if not pins or acquisition != pins[0]: continue
                    raw(acquisition)
                    git = self.git_files(acquisition['git_commit'])
                    for path, raw_hash in acquisition['checkout_overrides'].items(): clean_pairs[(path, raw_hash)] = git[path]
                except (ValueError, KeyError, subprocess.SubprocessError): continue
        def read_snapshot(files):
            return {path: clean_pairs.get((path, value), value) for path, value in files.items()}
        read_actual = read_snapshot(actual)
        def read_connected(start):
            # Completed ordinary evidence retains its read identity across
            # unrelated paths. Relevant allocated paths must still be joined by
            # exact whole-snapshot proof/owned-acquisition edges; work itself
            # continues to validate every raw acquisition path above.
            def selected(files): return {path: value for path, value in files.items() if path in allocated_paths}
            pending, seen = [selected(read_snapshot(start))], set()
            while pending:
                value = pending.pop(); identity = digest(value)
                if value == selected(read_actual): return True
                if identity in seen: continue
                seen.add(identity)
                pending.extend(selected(read_snapshot(after)) for before, after in edges if selected(read_snapshot(before)) == value)
            return False
        contexts = {}; migrations = {}
        for key, state in work.items():
            if state['state'] == 'blocked': continue
            try:
                grant = authority(state)
                migration = None
                migration_paths = [path for path in grant['entry']['consumed'] if path.startswith('.zzzops/migration/')]
                if migration_paths:
                    expected_path = f'.zzzops/migration/{key[0]}.json'
                    if migration_paths != [expected_path]: raise ValueError('Foreign migration assessment path cannot bind this goal')
                    if key[0] not in migrations:
                        migrations[key[0]] = self.api.migration_assessment(self.repo, self.project, {'key': key[0], 'schema_version': 2, 'spec_ref': snapshots[key[0]]['payload']['spec']})
                    migration = migrations[key[0]]
                    if migration['decision']['action'] == 'block':
                        contexts[key] = {'error': 'Migration release/assessment evidence: ' + migration['decision']['reason'], 'migration': migration, 'path': expected_path}
                        continue
                lease = next((l for l in snapshots[key[0]]['payload']['operational']['leases'] if ev.task_key(l['node']) == key), None)
                matches = [row for row in candidates if row['key'] == key]
                prior = matches[-1] if matches else None
                current_ref = projection['current'].get(key, (None,))[0]
                if lease:
                    acquisition = lease.get('acquisition'); baseline = raw(acquisition)
                    receipts = [content(reference) for token, reference in snapshots[key[0]]['acquisition_receipts'].items() if token == lease['token']]
                    pinned = [step['lease']['acquisition'] for receipt in receipts for step in receipt.get('next_steps', []) if step.get('lease', {}).get('token') == lease['token'] and step['lease'].get('acquisition')]
                    if not pinned or acquisition != pinned[0] or acquisition['input_hash'] != lease['fingerprint']: raise ValueError('Host acquisition differs from immutable start receipt')
                    changed = {p for p in baseline.keys() | actual.keys() if baseline.get(p, 'missing') != actual.get(p, 'missing')}
                    if changed - set(grant['entry']['owned']): raise ValueError('Workspace consumed/unowned file drift outside allocation')
                    if head != acquisition['git_commit']:
                        original_git = self.git_files(acquisition['git_commit'])
                        if any(original_git.get(p, 'missing') != committed.get(p, 'missing') for p in original_git.keys() | committed.keys() if p not in grant['entry']['owned']): raise ValueError('Acquired Git baseline changed outside owned scope')
                elif prior and current_ref == prior['result']:
                    if 'error' in prior: raise ValueError(prior['error'])
                    if not connected(prior['after']): raise ValueError('Completed workspace proof output/consumed drift or disconnected snapshot')
                    acquisition = prior['data']['acquisition']; baseline = prior['before']
                else:
                    baseline = actual
                    acquisition = {'git_commit': head, 'workspace_digest': digest(baseline), 'checkout_overrides': {}}
                    try: acquisition['checkout_overrides'] = self.clean_checkout_overrides(head, committed, actual)
                    except ValueError:
                        anchors = [row for row in candidates if 'error' not in row and row['reviews'] and connected(row['after'], accepted_only=True)]
                        if not anchors: raise ValueError('Workspace acquisition requires clean Git or exact reviewed connected output baseline') from None
                        anchor = anchors[-1]
                        acquisition['checkout_overrides'] = {path: value for path, value in anchor['data']['acquisition']['checkout_overrides'].items()
                                                             if baseline.get(path) == value}
                    if prior and 'error' not in prior and prior['reviews'] and connected(prior['after']):
                        previous = prior['data']['acquisition'].get('predecessor')
                        cursor, seen = previous, set()
                        while cursor is not None:
                            ev.validate_ref(cursor)
                            if cursor['hash'] in seen: raise ValueError('Workspace predecessor provenance cycle')
                            seen.add(cursor['hash']); historical = content(cursor)
                            if set(historical) != {'node', 'allocation', 'authorization', 'approval', 'result', 'proof', 'reviews', 'prior'} or historical['node'] != state['node']: raise ValueError('Workspace predecessor chain identity differs')
                            cursor = historical['prior']
                        acquisition['predecessor'] = remember({'node': state['node'], **{k: grant[k] for k in ('allocation', 'authorization', 'approval')}, 'result': prior['result'], 'proof': prior['proof'], 'reviews': [r for r, _ in prior['reviews']], 'prior': previous})
                        acquisition['predecessor_outputs'] = prior['value']['outputs']
                        acquisition['predecessor_proof'] = prior['proof']
                if not lease and not (prior and current_ref == prior['result']):
                    reachable, pending_refs = set(), [item['source'] for item in state['inputs']]
                    # Prerequisites remain currentness gates, but their exact
                    # accepted proof ancestry is acquisition provenance. This
                    # does not turn their Result IDs into semantic input hashes.
                    pending_refs.extend(projection['current'][parent][0] for parent in state.get('prerequisites', []) if parent in projection['current'])
                    def refs(value):
                        if isinstance(value, dict):
                            if set(value) == {'hash', 'uri'}: yield value
                            else:
                                for child in value.values(): yield from refs(child)
                        elif isinstance(value, list):
                            for child in value: yield from refs(child)
                    while pending_refs:
                        reference = pending_refs.pop()
                        if reference['hash'] in reachable: continue
                        reachable.add(reference['hash'])
                        if reference['hash'] in artifacts: pending_refs.extend(refs(artifacts[reference['hash']]))
                    # One latest reachable accepted anchor per qualified task;
                    # older transitions remain addressed through each proof's
                    # predecessor chain rather than expanding every old anchor.
                    selected_anchors = {}
                    for row in candidates:
                        if 'error' not in row and row['reviews'] and row['proof']['hash'] in reachable and connected(row['after']): selected_anchors[row['key']] = row
                    acquisition['baseline_proofs'] = [{'result': row['result'], 'proof': row['proof'], 'reviews': [ref for ref, _ in row['reviews']]}
                        for row in selected_anchors.values()]
                binding = remember({'type': 'workspace_snapshot', 'content': {'files': baseline, **{k: grant[k] for k in ('allocation', 'authorization', 'approval')}, **({'migration': migration} if migration is not None else {})}, 'producer': None, 'provenance': {'actor': 'host', 'source': None, 'policy': digest(self.project['policy'])}})
                contexts[key] = {'binding': binding, 'files': baseline, 'acquisition': acquisition, **grant}
            except (ValueError, KeyError, subprocess.SubprocessError) as exc:
                contexts[key] = {'error': 'Workspace authority/acquisition: ' + str(exc)}
        allocated_paths = set()
        for state in work.values():
            try:
                entry = authority(state)['entry']; allocated_paths.update(entry['owned']); allocated_paths.update(entry['consumed'])
            except (ValueError, KeyError): pass
        for key, state in states.items():
            if key in work or state['state'] == 'blocked': continue
            lease = next((item for item in snapshots[key[0]]['payload']['operational']['leases'] if ev.task_key(item['node']) == key), None)
            baseline = read_actual
            if lease and 'files' in lease['acquisition']:
                baseline = lease['acquisition']['files']
                if baseline != read_actual:
                    contexts[key] = {'error': 'Read-only task workspace changed outside empty write scope'}
                    continue
            elif key in projection['current']:
                previous = projection['current'][key][1]
                binding = next((item for item in previous['inputs'] if item['name'] == '__workspace'), None)
                if binding:
                    observed = content(binding['source'])['content']['files']
                    changed = {path for path in observed.keys() | read_actual.keys() if observed.get(path, 'missing') != read_actual.get(path, 'missing')}
                    unrelated_clean_commit = read_actual == read_snapshot(committed) and not changed.intersection(allocated_paths)
                    if observed == read_actual or unrelated_clean_commit or (work and read_connected(observed)): baseline = observed
            binding = remember({'type': 'workspace_snapshot', 'content': {'files': baseline}, 'producer': None,
                                'provenance': {'actor': 'host', 'source': None, 'policy': digest(self.project['policy'])}})
            contexts[key] = {'binding': binding, 'files': baseline, 'acquisition': {}, 'readonly': True}
        return contexts

    def node_workspace_proof(self, snapshot, state, lease, request):
        workspace = state.get('workspace')
        if workspace is None or workspace.get('readonly'):
            if request.get('workspace_checks'): raise ValueError('Workspace commands require explicit reviewed resource authority')
            return None
        pending = snapshot.get('pending')
        if pending and pending.get('proof'):
            ref = pending['proof']; proof = self.artifact_index(snapshot['number']).resolve(ref['hash'])[0]
            if proof.get('workspace') != self.workspace_digest() or proof.get('acquisition_hash') != digest(lease['acquisition']) or proof.get('actor') != lease['worker'] or proof.get('lease') != lease['token']: raise ValueError('Pending workspace proof/acquisition/output drift')
            for record in proof['commands']:
                if hashlib.sha256(Path(record['log']).read_bytes()).hexdigest() != record['log_hash']: raise ValueError('Pending verification log changed')
            snapshot['artifacts'][ref['hash']] = proof; snapshot['workspace_proof'] = ref
            return ref
        commands = request.get('workspace_checks', [])
        if not isinstance(commands, list) or any(not isinstance(c, list) or not c or any(not isinstance(a, str) or not a for a in c) for c in commands): raise ValueError('Workspace checks require nonempty argument arrays')
        before = self.workspace_files(); results = []
        if before != lease['acquisition']['files'] and not commands: raise ValueError('Changed workspace outputs require observed verification checks before publishing a candidate proof')
        logs = self.repo / '.zzzops' / 'diagnostics'; logs.mkdir(parents=True, exist_ok=True)
        for i, command in enumerate(commands):
            log = logs / f'node-{lease["token"]}-{i}.log'
            with log.open('w') as output:
                process = subprocess.run(command, cwd=self.repo, stdout=output, stderr=subprocess.STDOUT, timeout=300, check=False)
            results.append({'command': command, 'exit_code': process.returncode, 'log': str(log), 'log_hash': hashlib.sha256(log.read_bytes()).hexdigest()})
        if self.workspace_files() != before: raise ValueError('Workspace checks changed source/output bytes; inspect before retry')
        proof = {'node': state['node'], 'acquisition': lease['acquisition'], 'acquisition_hash': digest(lease['acquisition']),
                 'input_hash': lease['fingerprint'], 'actor': lease['worker'], 'lease': lease['token'],
                 'outputs': self.node_workspace_paths(workspace['entry']['owned']),
                 'consumed': {p: workspace['files'].get(p, 'missing') for p in workspace['entry']['consumed']},
                 'workspace': digest(before), 'commands': results, 'passed': all(r['exit_code'] == 0 for r in results)}
        identity = digest(proof); snapshot['artifacts'][identity] = proof
        snapshot['workspace_proof'] = self.node_ref(identity, snapshot['number'])
        return snapshot['workspace_proof']

    def node_policy(self, state):
        receipt = digest({'policy': self.project['policy'], 'contract': state['contract_hash']})
        raw = json.dumps({'policy_receipt': receipt, 'sections': self.project['policy']['sections']}, sort_keys=True).encode()
        ref = self.api._policy_context.cached_file(self.repo, raw)
        return ref, receipt

    def node_route(self, state):
        executor = state['contract']['executor']; runtime = self.runtime or {}
        config = policy_section(self.project, 'model_routing')['configuration']
        pairs = config['model_inventory']['reviewed_pairs']
        tiers = [item['id'] for item in config['tiers']]
        required = executor['capability']
        if required not in tiers: raise ValueError('Unknown reviewed capability tier')
        available = runtime.get('available_pairs', [])
        root = runtime.get('root_pair', {})
        if executor['role'] == 'root':
            if not any(all(row.get(k) == root.get(k) for k in ('model', 'effort')) for row in pairs): raise ValueError('Current root pair is not reviewed')
            return 'root', {k: root[k] for k in ('model', 'effort')}
        delegation = runtime.get('delegation', {})
        if not delegation.get('available') or not delegation.get('discovery_complete') or not delegation.get('tool'): raise ValueError('Delegation capability discovery is unavailable')
        choices = [row for row in pairs if tiers.index(row['tier']) >= tiers.index(required) and any(all(p.get(k) == row.get(k) for k in ('model', 'effort')) for p in available)]
        if not choices: raise ValueError('Reviewed capability/model inventory unavailable')
        chosen = min(choices, key=lambda row: (row['cost'], tiers.index(row['tier']), row['model'], row['effort']))
        return 'delegate', {k: chosen[k] for k in ('model', 'effort')}

    def node_step(self, state):
        executor = state['contract']['executor']; runtime = self.runtime or {}
        config = policy_section(self.project, 'model_routing')['configuration']
        tiers = [row['id'] for row in config['tiers']]
        root = runtime.get('root_pair', {})
        root_record = next((row for row in config['model_inventory']['reviewed_pairs'] if all(row.get(k) == root.get(k) for k in ('model', 'effort'))), None)
        if root_record is None: raise ValueError('Actual root pair requires current model policy review')
        if executor['capability'] not in tiers: raise ValueError('Unknown reviewed capability tier')
        if tiers.index(root_record['tier']) < tiers.index(executor['capability']):
            choices = [row for row in config['model_inventory']['reviewed_pairs'] if tiers.index(row['tier']) >= tiers.index(executor['capability']) and any(all(pair.get(k) == row.get(k) for k in ('model', 'effort')) for pair in runtime.get('available_pairs', []))]
            if not choices: raise ValueError('Required reviewed capability/model is unavailable')
            requested = min(choices, key=lambda row: (row['cost'], tiers.index(row['tier']), row['model'], row['effort']))
            return {'kind': 'capability_choice', 'goal': state['node']['goal'], 'node': state['node'],
                    'root_pair': root, 'requested_pair': {k: requested[k] for k in ('model', 'effort')},
                    'choices': ['use_requested_pair', 'delegate_at_root' if executor['role'] == 'worker' else 'downgrade_to_root'],
                    'action': 'Use the required actual root capability, or explicitly review the declared capability/policy alternative before acquisition. This choice grants no work authority.'}
        assignment, selection = self.node_route(state); policy, _ = self.node_policy(state)
        return {'kind': 'execute', 'goal': state['node']['goal'], 'node': state['node'], 'assignment': assignment, 'selection': selection,
                'instruction': state['contract']['prompt'], 'policy': policy, 'input_hash': state['input_hash'],
                'input_envelope': {'node': state['node'], 'contract': state['contract_hash'], 'inputs': state['inputs'], 'resolutions': state['resolutions']},
                'start': {'operation': 'start', 'node': state['node'], 'input_hash': state['input_hash'], 'policy_receipt': '<read policy.path>'},
                'action': 'Acquire this exact declared task and follow its prompt.',
                **({name: state['publication'][name] for name in ('base_branch', 'base_commit')} if 'publication' in state else {})}

    def node_checkpoint(self, number):
        _, goal = self.read(number)
        if goal.get('status') in ('done', 'cancelled') or str(goal.get('state', '')).lower() == 'closed': return []
        issue = self.adapter.get_issue(number)
        predecessor = self.api.parse_managed_goal(issue['body'], number)
        if predecessor.get('schema_version') == 1 and predecessor.get('workflow', {}).get('leases'):
            return [{'kind': 'await_worker', 'goal': number, 'reason': 'Predecessor ownership requires exact observed stopped recovery before migration',
                     'lease': lease, 'recovery_contract': {'operation': 'recover', 'request_id': uuid.uuid4().hex, 'predecessor': True,
                         'lease': lease['token'], 'expected_source': digest(issue['body']), 'worker_status': '<observed status>', 'evidence': '<terminal observation>'}}
                    for lease in predecessor['workflow']['leases'].values()]
        try: snapshot = self.node_snapshot(number)
        except (ValueError, KeyError, OSError) as exc: return [{'kind': 'blocker', 'goal': number, 'reason': str(exc), 'action': 'Resolve the exact missing schema, evidence or authority.'}]
        projection = snapshot['projection']; steps = []
        for state in projection['states'].values():
            if state['node']['goal'] != number: continue
            lease = projection['leases'].get(self.api._phase_evidence.task_key(state['node']))
            if lease:
                stale = state.get('input_hash') != lease['fingerprint']
                step = {'kind': 'await_worker', 'goal': number, 'node': state['node'], 'lease': lease, 'resume_worker': lease['worker'],
                        'reason': ('stale_input: ' + state.get('reason', 'substantive inputs changed')) if stale else lease.get('blocker', {}).get('reason', 'owned'), 'action': 'Continue or observe exact owner stopped; expiry alone is not stopped evidence.'}
                if stale or lease['expires_at'] <= time.time():
                    step['recovery_contract'] = {'operation': 'recover', 'node': state['node'], 'lease': lease['token'], 'actor': lease['worker'], 'worker_status': '<observed status>', 'evidence': '<terminal observation>'}
                steps.append(step)
            elif state['state'] == 'ready':
                resources = set(state['contract']['executor']['resources'])
                occupied = any(resources.intersection(projection['states'][key]['contract']['executor']['resources']) for key in projection['leases'] if key in projection['states'])
                if occupied:
                    steps.append({'kind': 'await_worker', 'goal': number, 'node': state['node'], 'reason': 'Declared resource is owned by another task'})
                    continue
                try: steps.append(self.node_step(state))
                except ValueError as exc: steps.append({'kind': 'blocker', 'goal': number, 'node': state['node'], 'reason': str(exc)})
            elif state['state'] == 'blocked' and 'repair' in snapshot['publications'].get(self.api._phase_evidence.task_key(state['node']), {}):
                steps.append({**snapshot['publications'][self.api._phase_evidence.task_key(state['node'])]['repair'], 'goal': number, 'node': state['node']})
            elif state['state'] == 'blocked': steps.append({'kind': 'blocked' if state.get('reason', '').startswith('Workspace') else 'dependency', 'goal': number, 'node': state['node'], 'reason': state.get('reason', 'Required evidence unknown')})
        for step in steps:
            observed = snapshot['workspaces'].get(self.api._phase_evidence.task_key(step['node']), {}) if step.get('node') else {}
            if 'migration' in observed:
                step['path'] = observed['path']
                step['preparation'] = self.migration_preparation({'key': number}, {'goal_spec': snapshot['payload']['spec']['hash']}, observed['migration'])
        if not projection['leases']:
            publications = [state['publication'] for state in projection['states'].values() if 'publication' in state]
            merged = next((value for value in publications if value['provider'].get('merged')), None)
            if merged:
                steps.append({'kind': 'reconcile', 'goal': number, 'assignment': 'root', 'submission': {'operation': 'reconcile', 'request_id': uuid.uuid4().hex,
                              'expected_digest': digest(snapshot['envelope']), 'expected_merge': digest(merged['provider'])}})
            else:
                for authority, publication in self.node_publication_authorities(snapshot):
                    try: self.node_ci_required(publication['observed'])
                    except ValueError: continue
                    steps.append({'kind': 'integrate', 'goal': number, 'assignment': 'root', 'submission': {'operation': 'integrate', 'request_id': uuid.uuid4().hex,
                                  'authorization': authority, 'expected_head': publication['provider']['head_oid']}})
        if not steps and not projection['complete']: steps.append({'kind': 'dependency', 'goal': number, 'reason': 'Required terminals or retained findings remain unresolved'})
        if not steps and projection['complete']:
            steps.append({'kind': 'complete', 'goal': number, 'assignment': 'root', 'action': 'All configured generic terminals are current.', 'submission': {'operation': 'complete'}})
        return steps

    def node_publication_authorities(self, snapshot):
        projection = snapshot['projection']; artifacts = snapshot['artifacts']; found = []
        owners = {output['hash']: (key, result) for key, (_, result) in projection['current'].items() for output in result['outputs'].values()}
        for identity, (key, result) in owners.items():
            blob = artifacts[identity]
            if blob.get('type') != 'publication_authorization': continue
            value = blob['content']; issuer = projection['states'][key]
            if issuer['contract']['executor']['role'] != 'root' or result['executor'] != (self.runtime or {}).get('root_id'): continue
            if value.get('policy') != digest(self.project['policy']) or value.get('decision') != 'approved': continue
            subject = owners.get(value.get('subject', {}).get('hash')); review = owners.get(value.get('review', {}).get('hash'))
            if not subject or not review: continue
            observed = projection['states'][subject[0]].get('publication')
            if not observed or 'error' in observed: continue
            if not all(any(row['source'] == value[name] and row['mode'] == 'identity' for row in result['inputs']) for name in ('subject', 'review')): continue
            if review[1]['executor'] == subject[1]['executor'] or not any(row['source'] == value['subject'] for row in review[1]['inputs']): continue
            found.append((next(ref for ref in result['outputs'].values() if ref['hash'] == identity), observed))
        return found

    def node_publication_operation(self, snapshot, payload, request):
        operation = request['operation']; projection = snapshot['projection']
        if not (self.runtime or {}).get('root_id'): raise ValueError('Operational publication belongs to authenticated root')
        allowed = {'operation', 'request_id'} | ({'authorization', 'expected_head'} if operation == 'integrate' else {'authorization'} if operation == 'complete' else {'expected_digest', 'expected_merge'})
        if set(request) - allowed: raise ValueError('Publication operation contains unknown authority fields')
        if payload['operational']['leases']: raise ValueError('Publication requires observed stopped/reconciled worker ownership')
        authorities = self.node_publication_authorities(snapshot)
        publication = None
        if operation in {'integrate', 'complete'}:
            reference = request.get('authorization')
            match = [(ref, value) for ref, value in authorities if ref == reference]
            resource_declared = any('repository_publication' in state['contract']['executor']['resources'] for state in projection['states'].values())
            if operation == 'integrate' or resource_declared:
                if len(match) != 1: raise ValueError('Exact current authenticated root publication authorization is required')
                publication = match[0][1]; self.node_ci_required(publication['observed'])
        else:
            candidates = [state['publication'] for state in projection['states'].values() if state.get('publication', {}).get('provider', {}).get('merged')]
            if not candidates: raise ValueError('Current provider merge observation is unavailable')
            publication = candidates[0]
            if request.get('expected_digest') != digest(snapshot['envelope']) or request.get('expected_merge') != digest(publication['provider']): raise ValueError('Stale expected source digest or merge evidence')
        if operation == 'integrate':
            facts = publication['provider']
            if request.get('expected_head') != facts['head_oid']: raise ValueError('Expected head differs from current provider head')
            if not facts.get('merged'):
                result = subprocess.run(['gh', 'pr', 'merge', publication['context']['pr'], '--squash', '--match-head-commit', facts['head_oid']], cwd=self.repo, capture_output=True, text=True, check=True)
                observed, _, _ = self.api._github_pull_request_states(self.repo, 'gh', [{'number': snapshot['number']}], {snapshot['number']: {'repository_context': publication['context']}})
                after = observed.get(snapshot['number'], {})
                if not after.get('merged') or any(after.get(name) != facts.get(name) for name in ('repository', 'head_oid', 'base_oid', 'base_ref')): raise ValueError('Provider did not confirm exact authorized merge; retry same request')
            response = {'next_steps': [{'kind': 'checkpoint', 'goal': snapshot['number'], 'action': 'Provider merge observed; configured post-effect evidence remains required.'}]}
        else:
            complete = projection['complete']
            if operation == 'complete' and not complete: raise ValueError('Completion requires all current configured terminal evidence and findings')
            close = complete
            if publication:
                if not publication['provider'].get('merged'):
                    if operation == 'complete': raise ValueError('Provider merge evidence is required before completion')
                    close = False
                if close:
                    if not authorities: raise ValueError('Current root authorization is required for closure')
                    self.node_ci_required(publication['observed'])
            if close: snapshot['archive'] = True
            response = {'next_steps': [{'kind': 'checkpoint', 'goal': snapshot['number'], 'provider_state': 'closed' if close else 'open',
                                        'action': 'Observed merge reconciled; semantic Results preserved.'}]}
        return self.node_persist(snapshot, payload, response, request)

    def node_pending(self, snapshot, request):
        index = self.artifact_index(snapshot['number'])
        pending = [row for row in index.envelopes if (row.get('context') or {}).get('request_id') == request['request_id']]
        if not pending: return None
        context = pending[0]['context']
        if any(row.get('context') != context for row in pending): raise ValueError('Conflicting pending checkpoint context')
        if context.get('request_hash') != digest(request): raise ValueError('Pending request identity conflicts with exact prior payload')
        if context.get('source_hash') != digest(snapshot['issue']['body']): raise ValueError('Pending checkpoint predecessor source changed')
        if context.get('root') != (self.runtime or {}).get('root_id'): raise ValueError('Pending checkpoint belongs to another root owner')
        snapshot['pending'] = context
        if set(context.get('response', {})) == {'hash', 'uri'}:
            return {**context, 'response': {'next_steps': [{'lease': context.get('ownership')}]}}
        return context

    def node_preflight(self, comments, bodies, references, previous):
        """Validate new records and all old closures their append can affect."""
        existing = {row.get('body', '') for row in comments}
        added = [body for body in bodies if body not in existing]
        stored = ObservedArtifactIndex(comments, previous=previous)
        prospective = ObservedArtifactIndex(list(comments) + [{'body': body} for body in added], previous=stored)
        if sum(prospective.decode_sizes[body] for body in added) > comment_store.MAX_RECONSTRUCTION_WORK_BYTES:
            raise ValueError('Transaction envelope decode work limit exceeded')
        changed = {identity for body in added for identity, _, _ in prospective._catalog[body]['records']}
        reverse = {}
        for identity, locations in prospective._locations.items():
            for _, _, base in locations:
                if base is not None:
                    if not isinstance(base, str): raise ValueError('Invalid artifact/base identity')
                    reverse.setdefault(base, set()).add(identity)
        affected, pending = set(changed), list(changed)
        while pending:
            for child in reverse.get(pending.pop(), set()) - affected:
                affected.add(child); pending.append(child)
        required = set(references) | changed
        for identity in affected & set(stored.records):
            try: stored.validate(identity)
            except ValueError: continue
            required.add(identity)
        prospective._checks.update(stored._checks)
        for identity in required: prospective.validate(identity)
        return prospective

    def node_artifact_record(self, index, content, base=None):
        raw = content if isinstance(content, str) else comment_store.canonical(content)
        if len(raw.encode('utf-8')) > comment_store.MAX_ARTIFACT_BYTES: raise ValueError('Artifact decoded size limit exceeded; use a published Git content reference')
        identity = digest(content)
        if identity in index.records:
            index.validate(identity)
            return None
        # Build once; the shared prospective decoder still validates every
        # emitted full/delta representation before publication.
        record = {'hash': identity, 'kind': 'full', 'type': 'text' if isinstance(content, str) else 'json', 'text': raw}
        if not base or base not in index.records:
            return record
        previous, depth, work = index.observe(base)
        if not isinstance(content, dict):
            return index.record(content, base)
        if not isinstance(previous, dict) or set(previous) != set(content) or depth >= comment_store.MAX_DELTA_DEPTH:
            return record
        # Typed output provenance changes independently of its possibly large
        # content. Patch each canonical top-level value with the existing bounded
        # codec rather than enclosing all intervening unchanged content.
        before, after = comment_store.canonical(previous), comment_store.canonical(content)
        patch = comment_store.make_text_patch(before, after)
        edits = []
        def fields(old_value, new_value, offset):
            if isinstance(old_value, dict) and isinstance(new_value, dict) and set(old_value) == set(new_value):
                offset += 1
                for key in sorted(old_value):
                    prefix = comment_store.canonical(key) + ':'
                    fields(old_value[key], new_value[key], offset + len(prefix))
                    offset += len(prefix) + len(comment_store.canonical(old_value[key])) + 1
            else:
                local = comment_store.make_text_patch(comment_store.canonical(old_value), comment_store.canonical(new_value))
                edits.extend([[offset + start, length, value] for start, length, value in local['edits']])
        fields(previous, content, 0)
        patch['edits'] = edits
        if len(edits) > comment_store.MAX_PATCH_EDITS: return record
        if comment_store.apply_text_patch(before, patch) != after: raise ValueError('Typed artifact patch reconstruction mismatch')
        delta = {'hash': digest(content), 'kind': 'delta', 'type': 'json', 'base': base, 'patch': patch}
        cost = work + len(comment_store.canonical(delta).encode()) + len(after.encode())
        if cost <= comment_store.MAX_RECONSTRUCTION_WORK_BYTES and comment_store.encoded_size(delta) < comment_store.encoded_size(record):
            return delta
        return record

    def node_persist(self, snapshot, payload, response, request):
        number = snapshot['number']; artifacts = snapshot['artifacts']
        def add(value):
            key = digest(value); artifacts[key] = value
            return self.node_ref(key, number)
        payload['operational']['receipts'].append({'request': request['request_id'], 'payload': digest(request), 'result': add(response)})
        entry_payload = add(payload)
        envelope = {**snapshot['envelope'], 'revision': snapshot['envelope']['revision'] + 1, 'payload': entry_payload}
        if 'activation' in snapshot:
            activation = snapshot['activation']
            target_payload = activation['payload']
            target_payload['operational'] = copy.deepcopy(payload['operational'])
            envelope = {**activation['envelope'], 'revision': envelope['revision'], 'payload': add(target_payload)}
        if 'parent_change' in snapshot: envelope['parent'] = snapshot['parent_change']
        if snapshot.get('archive'): envelope['state'] = 'archived'
        issue = snapshot['issue']; prefix = issue['body'].split(self.api._goals.GOAL_BLOCK_START, 1)[0]
        body = prefix + self.api._goals.GOAL_BLOCK_START + '\n' + json.dumps(envelope, sort_keys=True) + '\n' + self.api._goals.GOAL_BLOCK_END
        if self.adapter.get_issue(number)['body'] != issue['body']: raise ValueError('Concurrent predecessor source revision changed before write')
        comments = self.adapter.get_issue_comments(number)
        pending = snapshot.get('pending')
        index = ObservedArtifactIndex([row for row in comments if not (comment_store.decode_envelope(row.get('body', '')) or {}).get('context', {}).get('request_id') == request['request_id']], previous=self.artifact_index(number)) if pending else self.artifact_index(number)
        # Complete artifact validation precedes any provider mutation.
        reachable = set()
        def retain(value):
            if isinstance(value, dict):
                if value.get('schema_version') == 2 and 'payload' in value and 'repository' in value: return
                if set(value) == {'hash', 'uri'} and isinstance(value['hash'], str):
                    identity = value['hash']
                    if value['uri'].startswith('zzzops:') and self.node_ref_goal(value, number) != number: return
                    if identity in reachable or identity in snapshot.get('published', {}): return
                    reachable.add(identity)
                    if identity in artifacts: retain(artifacts[identity])
                else:
                    for child in value.values(): retain(child)
            elif isinstance(value, list):
                for child in value: retain(child)
        retain(envelope['payload'])
        retain(entry_payload)
        proof = snapshot.get('workspace_proof')
        ordered = sorted(reachable, key=lambda identity: (identity != (proof or {}).get('hash'), identity))
        payload_identity = envelope['payload']['hash']
        # Prefer a shallow addressed payload base while its encoded delta
        # remains comfortably within one provider comment. Always choosing the
        # immediately prior payload exhausts depth8 and forces oversized full
        # checkpoints; this keeps depth bounded without discarding receipts.
        by_depth = {}
        payload_bases = [snapshot['envelope']['payload']['hash']]
        payload_bases.extend((row.get('context') or {}).get('payload', {}).get('hash') for row in reversed(index.envelopes))
        seen_bases = set()
        for candidate in payload_bases:
            if not candidate or candidate in seen_bases: continue
            seen_bases.add(candidate)
            checked = index._checks.get(candidate)
            if checked is not None and (checked[2] >= comment_store.MAX_DELTA_DEPTH or checked[2] in by_depth): continue
            try:
                depth = index.observe(candidate)[1]
                if depth < comment_store.MAX_DELTA_DEPTH: by_depth.setdefault(depth, candidate)
            except ValueError: continue
            if len(by_depth) == comment_store.MAX_DELTA_DEPTH: break
        payload_record = self.node_artifact_record(index, artifacts[payload_identity])
        budget = comment_store.MAX_COMMENT_CHARACTERS * 3 // 4
        if payload_record is not None:
            for depth, candidate in sorted(by_depth.items()):
                proposed = self.node_artifact_record(index, artifacts[payload_identity], candidate)
                if proposed is not None and comment_store.encoded_size(proposed) < comment_store.encoded_size(payload_record):
                    payload_record = proposed
                if payload_record is not None and comment_store.encoded_size(payload_record) <= budget: break
        records = []
        for identity in ordered:
            if identity not in artifacts: continue
            # A borrowed value was checksum-validated for these exact provider
            # bytes. Revalidate its closure, without serializing unchanged
            # historical content again merely to decide it needs no append.
            if identity in index.records and artifacts[identity] is index.observe(identity)[0]: continue
            record = payload_record if identity == payload_identity else self.node_artifact_record(index, artifacts[identity], snapshot.get('output_bases', {}).get(identity))
            if record is not None: records.append(record)
        response_lease = response['next_steps'][0].get('lease', {})
        if not isinstance(response_lease, dict):
            response_lease = next((lease for lease in payload['operational']['leases'] if lease['token'] == response_lease), {})
        context = {'request_id': request['request_id'], 'request_hash': digest(request), 'source_hash': digest(issue['body']), 'human_hash': digest(prefix), 'root': (self.runtime or {}).get('root_id'), 'response': self.node_ref(digest(response), number), 'ownership': {key: value for key, value in response_lease.items() if key != 'acquisition'}, 'acquisition': bool(response['next_steps'][0].get('bind')), 'payload': envelope['payload'], 'proof': proof, 'source_envelope': snapshot['envelope'], 'target_envelope': envelope, 'entry_payload': entry_payload}
        if pending and pending != context: raise ValueError('Pending checkpoint exact response/payload/proof identity changed')
        bodies = comment_store.pack_envelopes({'goal': number, 'transaction': digest({'request': request, 'source': issue['body']}), 'context': context}, records)
        prospective = self.node_preflight(comments, bodies, [envelope['payload']['hash']], index)
        for encoded in bodies:
            if any(row.get('body') == encoded for row in comments): continue
            try:
                actual = self.adapter.create_issue_comment(number, encoded)
            except (RuntimeError, OSError) as exc:
                actual = next((row for row in self.adapter.get_issue_comments(number) if row.get('body') == encoded), None)
                if actual is None: raise ValueError('Unconfirmed checkpoint comment append; retry exact request') from exc
            if actual.get('body') != encoded: raise ValueError('Provider did not confirm exact source backup/artifact content')
        confirmed = ObservedArtifactIndex(self.adapter.get_issue_comments(number), previous=prospective)
        confirmed.resolve(envelope['payload']['hash'])
        _OBSERVED_ARTIFACT_INDEXES[(str(self.repo.resolve()), self.repository, number)] = confirmed
        observed = self.adapter.get_issue(number)
        if observed['body'] != issue['body']: raise ValueError('Concurrent source edit before body publication')
        if str(observed.get('state', '')).lower() == 'closed' and not snapshot.get('archive'):
            raise ValueError('Goal closed before body publication; explicit reopening is required')
        # Ordinary checkpoints own only the managed body. Resending snapshot
        # labels/state would overwrite unrelated edits or reopen a closed goal.
        update = {'body': body}
        if snapshot.get('archive'): update['state'] = 'closed'
        try:
            updated = self.adapter.update_issue(number, update)
        except (RuntimeError, OSError) as exc:
            updated = self.adapter.get_issue(number)
            if updated.get('body') != body: raise ValueError('Unconfirmed provider body publication; retry exact request') from exc
        if updated.get('body') != body: raise ValueError('Provider did not confirm exact goal body; retry same request')
        if snapshot.get('archive') and str(updated.get('state', '')).lower() != 'closed': raise ValueError('Provider did not confirm goal closure; repair partial state')
        if not snapshot.get('archive') and str(updated.get('state', '')).lower() == 'closed':
            raise ValueError('Goal closed during body publication; execution cannot resume without explicit reopening')
        self.invalidate()
        return self.stop_completed_heartbeat(number, request, payload['operational'], copy.deepcopy(response))

    def node_mutate(self, number, request):
        ev = self.api._phase_evidence
        if not isinstance(request.get('request_id'), str) or not request['request_id']: raise ValueError('Exact request_id is required')
        with self.locked():
            self.invalidate()
            issue = self.adapter.get_issue(number)
            envelope = self.api._goals.parse_managed_goal(issue['body'], number)
            if envelope.get('schema_version') == 1 and request.get('operation') == 'recover' and request.get('predecessor') is True:
                if not (self.runtime or {}).get('root_id') or request.get('expected_source') != digest(issue['body']): raise ValueError('Predecessor recovery source/owner identity changed')
                if request.get('worker_status') != 'stopped' or not isinstance(request.get('evidence'), str) or not request['evidence'].strip(): raise ValueError('Exact predecessor worker must be observed stopped; expiry is not evidence')
                leases = envelope.get('workflow', {}).get('leases', {})
                matches = [key for key, lease in leases.items() if lease['token'] == request.get('lease')]
                if len(matches) != 1: raise ValueError('Wrong predecessor owner/lease token')
                desired = copy.deepcopy(envelope); del desired['workflow']['leases'][matches[0]]
                desired['revision'] += 1
                self.artifact(number, {'type': 'predecessor_recovery', 'source': issue, 'request': request, 'root': self.runtime['root_id']})
                if self.adapter.get_issue(number)['body'] != issue['body']: raise ValueError('Predecessor recovery source changed before write')
                prefix = issue['body'].split(self.api._goals.GOAL_BLOCK_START, 1)[0]
                body = self.api.render_managed_goal(desired, prefix, number)
                try: updated = self.adapter.update_issue(number, {'body': body, 'state': issue['state'], 'labels': [row['name'] if isinstance(row, dict) else row for row in issue['labels']]})
                except (RuntimeError, OSError): updated = self.adapter.get_issue(number)
                if updated.get('body') != body: raise ValueError('Predecessor recovery body readback is unconfirmed')
                self.invalidate()
                return {'next_steps': [{'kind': 'checkpoint', 'goal': number}]}
            if envelope.get('schema_version') == 2:
                durable = self.artifact_index(number).resolve(envelope['payload']['hash'])[0]
                for receipt in durable['operational']['receipts']:
                    if receipt['request'] == request['request_id']:
                        if receipt['payload'] != digest(request): raise ValueError('Request receipt payload conflict')
                        response = copy.deepcopy(self.artifact_index(number).resolve(receipt['result']['hash'])[0])
                        if any(step.get('provider_state') == 'closed' for step in response['next_steps']) and str(issue.get('state', '')).lower() != 'closed': raise ValueError('Stored closure receipt conflicts with partial provider state; repair required')
                        if str(issue.get('state', '')).lower() == 'closed' and not any(step.get('provider_state') == 'closed' for step in response['next_steps']):
                            raise ValueError('Closed goal cannot resume an execution receipt without explicit reopening')
                        return self.stop_completed_heartbeat(number, request, durable['operational'], response)
            snapshot = self.node_snapshot(number)
            if snapshot['envelope']['state'] != 'open' or str(snapshot['issue'].get('state', '')).lower() == 'closed': raise ValueError('Archived goal cannot execute or mutate')
            payload = copy.deepcopy(snapshot['payload']); projection = snapshot['projection']
            for receipt in payload['operational']['receipts']:
                if receipt['request'] == request['request_id']:
                    if receipt['payload'] != digest(request): raise ValueError('Request receipt payload conflict')
                    return copy.deepcopy(snapshot['artifacts'][receipt['result']['hash']])
            pending = self.node_pending(snapshot, request)
            if request['operation'] in {'integrate', 'reconcile', 'complete'}:
                return self.node_publication_operation(snapshot, payload, request)
            node = request.get('node')
            if not isinstance(node, dict): raise ValueError('Generic operation requires exact qualified node identity')
            key = ev.task_key(node)
            state = projection['states'].get(key)
            if state is None: raise ValueError('Unknown or retired task generation')
            operation = request['operation']; leases = payload['operational']['leases']
            lease = next((item for item in leases if item['node'] == node), None)
            root = (self.runtime or {}).get('root_id')
            if operation == 'start':
                if lease: raise ValueError('Task already has an owner; observed-stop recovery is required')
                if state['state'] != 'ready' or request.get('input_hash') != state.get('input_hash'): raise ValueError('Stale input or prerequisite prevents acquisition')
                if any(set(state['contract']['executor']['resources']).intersection(projection['states'][other]['contract']['executor']['resources']) for other in projection['leases'] if other in projection['states']): raise ValueError('Declared resource is already owned')
                if unresolved_lease_count(self.portfolio()) >= worker_limit(self.project): raise ValueError('Reviewed max_workers capacity occupied by unresolved owner')
                step = self.node_step(state)
                if step['kind'] != 'execute': raise ValueError('Capability choice must be resolved before acquisition')
                _, receipt = self.node_policy(state)
                if request.get('policy_receipt') != receipt: raise ValueError('Exact policy receipt is required')
                lease = {'node': node, 'attempt': uuid.uuid4().hex, 'token': uuid.uuid4().hex, 'owner': root,
                         'worker': root if step['assignment'] == 'root' else None, 'fingerprint': state['input_hash'], 'expires_at': time.time() + 600,
                         'selection': step['selection'], 'acquisition': {'resolutions': state['resolutions'], 'inputs': state['inputs'], 'contract': state['contract_hash']}}
                aggregates = {}
                for binding in state['inputs']:
                    declared = state['contract']['inputs'].get(binding['name'], {})
                    selector = declared.get('producer', {}).get('node', {})
                    if selector.get('goal') == '#children' or selector.get('kind') == 'join':
                        aggregates[binding['name']] = copy.deepcopy(snapshot['artifacts'][binding['source']['hash']]['content']['sources'])
                if aggregates: lease['acquisition']['aggregate_sources'] = aggregates
                if 'workspace' in state:
                    workspace = state['workspace']
                    lease['acquisition'].update(copy.deepcopy(workspace['acquisition']))
                    lease['acquisition'].update(files=workspace['files'], input_hash=state['input_hash'])
                lease['acquisition'].update(inputs=copy.deepcopy(state['inputs']), resolutions=copy.deepcopy(state['resolutions']), contract=state['contract_hash'])
                if pending: lease.update(copy.deepcopy(pending['response']['next_steps'][0]['lease']))
                leases.append(lease)
                response = {'next_steps': [{**step, 'kind': 'perform', 'lease': lease, 'acquisition': lease['acquisition'],
                    'bind': {'operation': 'bind', 'node': node, 'lease': lease['token'], 'actor': '<actual worker>', 'selection': lease['selection'], 'policy_receipt': '<read policy.path>'},
                    'submission': {'operation': 'submit', 'node': node}}]}
            else:
                if not lease or request.get('lease') != lease['token'] or lease['owner'] != root: raise ValueError('Exact current owner/lease token required')
                if operation == 'recover':
                    if request.get('worker_status') != 'stopped' or not isinstance(request.get('evidence'), str) or not request['evidence'].strip(): raise ValueError('Observed stopped worker evidence required; unknown liveness cannot recover')
                    leases.remove(lease)
                    response = {'next_steps': [{'kind': 'checkpoint', 'goal': number}]}
                elif operation == 'bind':
                    _, receipt = self.node_policy(state)
                    if request.get('policy_receipt') != receipt or request.get('selection') != lease['selection']: raise ValueError('Exact policy receipt and actual model/effort required')
                    actor = request.get('actor')
                    if not isinstance(actor, str) or not actor or lease['worker'] not in (None, actor): raise ValueError('Worker identity already bound or invalid')
                    self.node_independence(snapshot, state, actor)
                    lease['worker'] = actor
                    response = {'next_steps': [{'kind': 'perform', 'goal': number, 'node': node, 'lease': lease}]}
                else:
                    if request.get('actor') != lease['worker'] or not lease['worker']: raise ValueError('Exact bound actor required')
                    if state.get('input_hash') != lease['fingerprint'] or state['state'] != 'ready': raise ValueError('Stale substantive input/contract/prerequisite; owner remains bound: ' + state.get('reason', 'workspace or input identity drift'))
                    if lease['expires_at'] <= time.time(): raise ValueError('Lease expired; observe stopped owner before recovery')
                    if operation == 'renew':
                        lease['expires_at'] = pending['response']['next_steps'][0]['lease']['expires_at'] if pending else time.time() + 600
                        response = {'next_steps': [{'kind': 'renewed', 'goal': number, 'node': node, 'lease': lease['token'], 'actor': lease['worker'], 'expires_at': lease['expires_at']}]}
                    elif operation == 'block':
                        if request.get('category') != 'external-dependency' or not isinstance(request.get('reason'), str) or not request['reason'].strip(): raise ValueError('Infrastructure blocker requires factual external dependency reason')
                        lease['blocker'] = {'category': request['category'], 'reason': request['reason']}
                        response = {'next_steps': [{'kind': 'await_worker', 'goal': number, 'node': node, 'reason': request['reason'], 'lease': lease}]}
                    elif operation == 'submit':
                        if set(request) - {'operation', 'node', 'lease', 'actor', 'request_id', 'outputs', 'workspace_checks'}: raise ValueError('Unknown submission fields; host acquisition cannot be replaced')
                        self.node_independence(snapshot, state, lease['worker'])
                        bundle = request.get('outputs'); contracts = state['contract']['outputs']
                        if not isinstance(bundle, dict) or set(bundle) != set(contracts): raise ValueError('Submission must supply exactly declared output slots')
                        for slot, content in bundle.items():
                            if not ev.value_matches(contracts[slot]['schema'], content): raise ValueError('Output type contract rejected slot ' + slot)
                        self.node_validate_bundle(snapshot, state, bundle, lease['worker'])
                        proof_ref = self.node_workspace_proof(snapshot, state, lease, request)
                        outputs = {}
                        previous = next((snapshot['artifacts'][ref['hash']]['content']['outputs'] for ref in reversed(snapshot['payload']['evidence']) if snapshot['artifacts'][ref['hash']]['content']['node'] == node), {})
                        for slot, content in bundle.items():
                            output = {'type': contracts[slot]['type'], 'content': content, 'producer': lease['attempt'], 'provenance': {'actor': lease['worker'], 'source': proof_ref, 'policy': digest(self.project['policy'])}}
                            identity = digest(output); snapshot['artifacts'][identity] = output; outputs[slot] = self.node_ref(identity, number)
                            if slot in previous: snapshot.setdefault('output_bases', {})[identity] = previous[slot]['hash']
                        result = {'node': node, 'attempt': lease['attempt'], 'contract': state['contract_hash'], 'inputs': lease['acquisition']['inputs'], 'executor': lease['worker'], 'outputs': outputs, 'resolutions': lease['acquisition']['resolutions']}
                        artifact = {'type': 'result', 'content': result, 'producer': lease['attempt'], 'provenance': {'actor': lease['worker'], 'source': None, 'policy': digest(self.project['policy'])}}
                        identity = digest(artifact); snapshot['artifacts'][identity] = artifact
                        ref = self.node_ref(identity, number); payload['evidence'].append(ref); leases.remove(lease)
                        response = {'next_steps': [{'kind': 'checkpoint', 'goal': number, 'node': node, 'result': ref}]}
                    else: raise ValueError('Unsupported generic operation; semantic evidence uses submit')
            return self.node_persist(snapshot, payload, response, request)

    def node_validate_bundle(self, snapshot, state, bundle, actor):
        """Validate semantic evidence as one candidate before appending any output."""
        ev = self.api._phase_evidence; projection = snapshot['projection']; artifacts = snapshot['artifacts']
        current = {ref['hash']: result for ref, result in projection['current'].values()}
        subject_results = {ref['hash']: result for result in current.values() for ref in result['outputs'].values()}
        history = [(ref, artifacts[ref['hash']]) for item in snapshot['payload']['evidence'] for ref in artifacts[item['hash']]['content']['outputs'].values()]
        proposed = [(state['contract']['outputs'][slot]['type'], value) for slot, value in bundle.items()]
        def read(ref, kind=None):
            ev.validate_ref(ref)
            if ref['hash'] not in artifacts: raise ValueError('Unknown immutable evidence reference' + (': ' + kind if kind else ''))
            value = artifacts[ref['hash']]
            if kind and value.get('type') != kind: raise ValueError('Evidence type/authority mismatch: ' + kind)
            return value.get('content', value)
        def load(ref):
            ev.validate_ref(ref)
            if ref['hash'] not in artifacts:
                artifacts[ref['hash']] = snapshot['resolve'](ref)
            return artifacts[ref['hash']]
        def conversion(value):
            source = load(value['source'])
            original = artifacts[snapshot['payload']['spec']['hash']]
            if source.get('type') != 'migration_source' or original.get('type') != 'migration_source' or source['content'] != original['content']:
                raise ValueError('Conversion source differs from exact historical source')
            target = load(value['target'])
            if set(target) != {'schema_version', 'repository', 'issue', 'revision', 'state', 'parent', 'payload'} or target['schema_version'] != 2 or target['repository'] != self.repository or target['issue'] != snapshot['number'] or target['parent'] != snapshot['envelope']['parent']:
                raise ValueError('Conversion target repository/goal/parent identity mismatch')
            payload = load(target['payload']); graph = load(payload['graph']); ev.validate_graph(graph)
            load(payload['spec'])
            for reference in payload['evidence']: load(reference)
            historical = self.api._goals.parse_managed_goal(source['content']['body'], snapshot['number'])
            for reference in value['mapped_evidence']:
                mapping = load(reference)
                record = historical.get('phase_evidence', {}).get('records', {}).get(mapping.get('source_phase'))
                node = next((node for node in graph['nodes'] if node['id'] == mapping.get('target', {}).get('node')), None)
                if mapping.get('source') != value['source'] or not record or digest(record) != mapping.get('source_record_hash'):
                    raise ValueError('Historical mapping source record hash differs')
                if mapping.get('contract') != {'node': node, 'policy': digest(self.project['policy'])} or mapping['target'] != {'goal': snapshot['number'], 'node': node['id'], 'item': None, 'generation': 1}:
                    raise ValueError('Historical mapping current contract differs')
                if mapping.get('inputs') != [] or node['inputs'] or len(mapping.get('outputs', {})) != 1:
                    raise ValueError('Historical mapping input equivalence is not established')
                output = next(iter(mapping['outputs'].values()))
                if output['hash'] != record['output']['hash'] or output['uri'] != record['output']['reference']:
                    raise ValueError('Historical mapping output identity differs')
                content = load(output)
                if not ev.value_matches(next(iter(node['outputs'].values()))['schema'], content): raise ValueError('Historical mapping output contract differs')
            return target, payload, graph
        def authority(ref):
            result = read(ref, 'result')
            if ref['hash'] not in current: raise ValueError('Stale authority result')
            selected = projection['states'].get(ev.task_key(result['node']))
            if not selected or selected['contract']['executor']['role'] != 'root' or result['executor'] != (self.runtime or {}).get('root_id'):
                raise ValueError('Current authenticated root authority is required')
            return result
        def permit(kind, scope):
            ev.validate_scope(scope)
            target = scope['subject']
            if type(target.get('goal')) is not int or target['kind'] == 'join' or target.get('generation') == 'current': raise ValueError('Finding target must freeze one literal exact producer; plural/symbolic targets are forbidden')
            for allowed in state['contract']['permits']:
                if allowed['type'] != kind or allowed['scope']['output'] != scope['output']: continue
                selector = allowed['scope']['subject']
                resolutions = [r for r in state['resolutions'] if r['selector'] == selector]
                for resolution in resolutions:
                    for node in resolution['targets']:
                        if node['goal'] != target['goal']: continue
                        if target['kind'] == 'node' and node['node'] == target['node'] and node['item'] is None: return
                        if target['kind'] == 'member' and node['item'] == target['item'] and node['generation'] == target['generation']:
                            instance = projection['states'].get(ev.task_key(node))
                            if instance and instance.get('expansion') == target['expansion']: return
            raise ValueError('Output target exceeds configured permit/type/scope authority')
        def obligation(finding):
            return projection['obligations'].get((finding['target']['subject']['goal'], finding['id']))
        def exact_input(reference):
            return any(item['source'] == reference and item['mode'] == 'identity' and not item['path'] for item in state['inputs'])
        def reviewed(reference, review=None):
            producer = subject_results.get(reference['hash'])
            if not producer: raise ValueError('Current subject evidence is required')
            candidates = [review] if review is not None else [item['source'] for item in state['inputs']]
            for candidate in candidates:
                reviewer = subject_results.get(candidate['hash'])
                if not reviewer or not exact_input(candidate) or reviewer['executor'] == producer['executor']: continue
                reviewer_state = projection['states'][ev.task_key(reviewer['node'])]
                independent = any(producer['node'] in row['targets'] for row in reviewer_state['resolutions'] if row['selector'] in reviewer_state['contract']['independent_of'])
                if independent and any(item['source'] == reference for item in reviewer['inputs']): return
            raise ValueError('Exact current independent review is required')
        for kind, value in proposed:
            if kind == 'repository_context':
                if actor != (self.runtime or {}).get('root_id') or state['contract']['executor']['role'] != 'root': raise ValueError('Repository context must be issued by authenticated root')
                if set(value) != {'branch', 'base', 'target', 'pr'} or any(not isinstance(value[name], str) or not value[name].strip() for name in ('branch', 'base', 'target')): raise ValueError('Invalid repository context')
            elif kind in {'repository_authorization', 'publication_authorization'}:
                if actor != (self.runtime or {}).get('root_id') or state['contract']['executor']['role'] != 'root': raise ValueError('Authorization requires authenticated root')
                if value.get('policy') != digest(self.project['policy']) or value.get('decision') != 'approved': raise ValueError('Authorization policy or decision mismatch')
                reference = value['context'] if kind == 'repository_authorization' else value['subject']
                read(reference, 'repository_context' if kind == 'repository_authorization' else 'publication_evidence')
                if not exact_input(reference): raise ValueError('Authorization subject differs from exact declared input')
                reviewed(reference, value.get('review'))
                if kind == 'publication_authorization':
                    producer = subject_results[reference['hash']]
                    publication = projection['states'][ev.task_key(producer['node'])].get('publication')
                    if not publication or 'error' in publication: raise ValueError('Current provider publication evidence is required')
                    self.node_ci_required(publication['observed'])
            elif kind == 'publication_evidence':
                publication = state.get('publication')
                if not publication or publication['observed'].get('pr') is None or value != publication['observed']: raise ValueError('Publication evidence differs from current exact provider head/base/CI')
            elif kind == 'merge_observation':
                publication = state.get('publication')
                if not publication or not publication['provider'].get('merged'): raise ValueError('Provider merge is not observed')
                reference = value.get('authorization'); read(reference, 'publication_authorization')
                if not exact_input(reference) or reference['hash'] not in subject_results: raise ValueError('Merge observation requires current exact root authorization input')
                expected = {key: publication['observed'][key] for key in ('repository', 'pr', 'head_oid', 'base_oid', 'base_ref')}
                expected.update(authorization=reference, merge_commit=publication['provider'].get('merge_commit'), merged_at=publication['provider'].get('merged_at'))
                if value != expected or not expected['merge_commit'] or not expected['merged_at']: raise ValueError('Merge observation differs from exact provider facts')
                self.node_ci_required(publication['observed'])
            elif kind == 'migration_source':
                source = artifacts[snapshot['payload']['spec']['hash']]
                if source.get('type') != 'migration_source' or value != source['content']: raise ValueError('Migration source must preserve exact original provider bytes')
            elif kind == 'selection':
                if set(value) != {'items', 'rationale'} or not isinstance(value['items'], dict) or not value['rationale'].strip(): raise ValueError('Selection requires explicit items and rationale')
                if any(not ev.task_identifier(item) for item in value['items']): raise ValueError('Selection item keys must be identifiers')
                for debt in projection['obligations'].values():
                    target = debt['content']['target']['subject']
                    if target['kind'] == 'member' and target['item'] not in value['items']:
                        retired = any(output['type'] == 'retirement' and output['content'].get('decision') == 'retire_member' and output['content']['finding'] == debt['finding'] for _, output in history)
                        if not retired: raise ValueError('Selection retirement cannot erase an unresolved finding obligation')
            elif kind == 'migration_source':
                original = artifacts[snapshot['payload']['spec']['hash']]
                if original.get('type') != 'migration_source' or value != original['content']: raise ValueError('Migration source must preserve exact predecessor provider bytes')
            elif kind == 'conversion':
                conversion(value)
            elif kind == 'schema_activation':
                slot = next(name for name, contract in state['contract']['outputs'].items() if contract['type'] == kind)
                permit(kind, {'subject': {'kind': 'node', 'goal': snapshot['number'], 'node': state['node']['node']}, 'output': slot})
                receipt = snapshot['payload']['operational']['receipts'][-1]['result']
                matching = [row.get('context', {}) for row in self.artifact_index(snapshot['number']).envelopes if row.get('context', {}).get('response') == receipt]
                prefix = snapshot['issue']['body'].split(self.api._goals.GOAL_BLOCK_START, 1)[0]
                if not matching or any(row.get('target_envelope') != snapshot['envelope'] or row.get('human_hash') != digest(prefix) for row in matching):
                    raise ValueError('Migration activation entry revision/source changed after current host receipt')
                conversion_blob = load(value['conversion'])
                if conversion_blob.get('type') != 'conversion' or value['conversion']['hash'] not in subject_results:
                    raise ValueError('Activation requires current exact conversion')
                approval = authority(value['approval'])
                producer = subject_results[value['conversion']['hash']]
                if actor != (self.runtime or {}).get('root_id') or not any(row['source'] == value['conversion'] and row['mode'] == 'identity' for row in approval['inputs']):
                    raise ValueError('Activation requires exact root approval of conversion')
                reviews = [ref for ref, result in projection['current'].values() if result['executor'] != producer['executor'] and any(producer['node'] in resolution['targets'] for resolution in projection['states'][ev.task_key(result['node'])]['resolutions'] if resolution['selector'] in projection['states'][ev.task_key(result['node'])]['contract']['independent_of']) and ev.task_key(result['node']) in projection['states'][ev.task_key(approval['node'])].get('prerequisites', []) and any(row['source'] == value['conversion'] and row['mode'] == 'identity' for row in result['inputs'])]
                if not reviews: raise ValueError('Activation requires current independent conversion review')
                target, payload, graph = conversion(conversion_blob['content'])
                payload = copy.deepcopy(payload)
                if conversion_blob['content']['mapped_evidence']:
                    target_view = {**snapshot, 'envelope': target, 'payload': payload, 'graph': graph}
                    goals = {snapshot['number']: target_view}
                    context = {'goal': snapshot['number'], 'policy': self.project['policy'], 'runtime': self.runtime,
                               'artifacts': artifacts, 'goals': goals, 'workspace_probe': True}
                    candidate = ev.derive_task_steps(graph, payload, context)
                    workspaces = self.node_workspace_context(goals, candidate, candidate['artifacts'])
                    context.update(workspace_probe=False, workspaces=workspaces, artifacts=candidate['artifacts'])
                    candidate = ev.derive_task_steps(graph, payload, context)
                    artifacts.update(candidate['artifacts'])
                    source_goal = self.api.parse_managed_goal(load(conversion_blob['content']['source'])['content']['body'], snapshot['number'])
                    for mapping_ref in conversion_blob['content']['mapped_evidence']:
                        mapping = load(mapping_ref); mapped_state = candidate['states'][ev.task_key(mapping['target'])]
                        if mapped_state['state'] != 'ready': raise ValueError('Mapped task still has missing current prerequisites')
                        historical = source_goal['phase_evidence']['records'][mapping['source_phase']]
                        attempt = 'mapped-' + mapping_ref['hash'][7:]
                        outputs = {}
                        for slot, original in mapping['outputs'].items():
                            output = {'type': mapped_state['contract']['outputs'][slot]['type'], 'content': load(original), 'producer': attempt,
                                      'provenance': {'actor': historical['actor'], 'source': mapping_ref, 'policy': digest(self.project['policy'])}}
                            identity = digest(output); artifacts[identity] = output; outputs[slot] = self.node_ref(identity, snapshot['number'])
                        mapped = {'node': mapping['target'], 'attempt': attempt, 'contract': mapped_state['contract_hash'], 'inputs': mapped_state['inputs'],
                                  'executor': historical['actor'], 'outputs': outputs, 'resolutions': mapped_state['resolutions']}
                        result_blob = {'type': 'result', 'content': mapped, 'producer': attempt,
                                       'provenance': {'actor': historical['actor'], 'source': None, 'policy': digest(self.project['policy'])}}
                        identity = digest(result_blob); artifacts[identity] = result_blob
                        payload['evidence'].append(self.node_ref(identity, snapshot['number']))
                snapshot['activation'] = {'envelope': target, 'payload': payload, 'graph': graph, 'conversion': conversion_blob['content'], 'review': reviews[0], 'approval': value['approval']}
            elif kind == 'workspace_allocation':
                owned = set()
                for entry in value['allocations'].values():
                    for field in ('owned', 'consumed'):
                        self.node_workspace_paths(entry[field], consumed=field == 'consumed')
                    if owned.intersection(entry['owned']): raise ValueError('Workspace allocation owned paths overlap')
                    owned.update(entry['owned'])
            elif kind == 'workspace_authorization':
                # A typed review may record a stale or mismatched proposition.
                # Only the resource adapter can use a current, independently
                # reviewed and root-approved exact manifest as edit authority.
                pass
            elif kind == 'parent_change':
                if actor != (self.runtime or {}).get('root_id') or state['contract']['executor']['role'] != 'root': raise ValueError('Parent change requires actual root authority')
                if value['repository'] != self.repository or value['subject'] != snapshot['number']: raise ValueError('Parent change repository/subject identity differs')
                slot = next(name for name, contract in state['contract']['outputs'].items() if contract['type'] == kind and bundle[name] == value)
                permit(kind, {'subject': {'kind': 'node', 'goal': snapshot['number'], 'node': state['node']['node']}, 'output': slot})
                try: predecessor = snapshot['resolve'](value['expected'])
                except (ValueError, KeyError): raise ValueError('Parent predecessor reference is missing or stale') from None
                if predecessor != snapshot['envelope']: raise ValueError('Parent change requires exact current predecessor envelope revision')
                parent, seen = value['parent'], {snapshot['number']}
                while parent is not None:
                    if not ev.positive_integer(parent) or parent in seen: raise ValueError('Parent self/ancestor cycle is forbidden')
                    seen.add(parent)
                    try: ancestor = self.api.parse_managed_goal(self.adapter.get_issue(parent).get('body', ''), parent)
                    except (ValueError, KeyError): raise ValueError('Parent ancestor is unknown or missing') from None
                    if not ancestor or ancestor.get('schema_version') != 2: raise ValueError('Parent ancestor evidence is unknown')
                    if ancestor['repository'] != self.repository: raise ValueError('Parent ancestor repository differs')
                    parent = ancestor['parent']
                snapshot['parent_change'] = value['parent']
            elif kind == 'finding':
                permit(kind, value['target'])
                if not ev.task_identifier(value['id']) or not ev.positive_integer(value['revision']): raise ValueError('Finding identity/revision invalid')
                if not value['request'].strip() or not value['rationale'].strip(): raise ValueError('Finding request and evidence rationale required')
                read(value['source'])
                if not value['subjects'] or any(ref['hash'] not in subject_results for ref in value['subjects']): raise ValueError('Finding subject is stale or unknown')
                previous = [(ref, output['content']) for ref, output in history if output['type'] == 'finding' and output['content']['id'] == value['id']]
                if previous:
                    prior_ref, prior = max(previous, key=lambda item: item[1]['revision'])
                    if value['revision'] == prior['revision']:
                        if value != prior: raise ValueError('Conflicting finding identity/revision')
                    elif value['revision'] != prior['revision'] + 1 or value['supersedes'] != prior_ref: raise ValueError('Finding supersession requires exact preceding revision')
                elif value['revision'] != 1 or value['supersedes'] is not None: raise ValueError('First finding must start at revision one without supersession')
            elif kind == 'admission':
                finding = read(value['finding'], 'finding'); permit(kind, finding['target']); authority(value['authority'])
                if any(ref['hash'] not in subject_results for ref in finding['subjects']): raise ValueError('Admission inspected subject is stale')
                if not any(subject_results[ref['hash']]['inputs'] == value['target_inputs'] for ref in finding['subjects']): raise ValueError('Admission target inputs mismatch exact subject')
                if value['applicability'] not in ('applicable', 'not_applicable', 'unresolved'): raise ValueError('Unknown admission applicability')
                prior = obligation(finding)
                if prior and prior['finding'] != value['finding'] and not any(k == 'supersession' and v['prior'] == prior['finding'] and v['replacement'] == value['finding'] for k, v in proposed): raise ValueError('Supersession requires atomic exact coverage transfer')
            elif kind == 'supersession':
                prior = read(value['prior'], 'finding'); replacement = read(value['replacement'], 'finding')
                permit(kind, replacement['target']); authority(value['authority']); authority(value['coverage_evidence'])
                existing = obligation(prior)
                if not existing or existing['finding'] != value['prior'] or replacement['supersedes'] != value['prior'] or replacement['id'] != prior['id'] or value['coverage'] not in ('carried', 'narrowed'): raise ValueError('Supersession expected current revision/coverage mismatch')
            elif kind in ('withdrawal', 'retirement'):
                finding = read(value['finding'], 'finding'); permit(kind, finding['target']); authority(value['authority'])
                prior = obligation(finding)
                if not prior or prior['finding'] != value['finding'] or value['target'] != finding['target']: raise ValueError('Retirement requires exact current finding and target')
            elif kind == 'resolution':
                finding = read(value['finding'], 'finding'); permit(kind, finding['target']); prior = obligation(finding)
                reviewer = read(value['reviewer_result'], 'result')
                if not prior or prior['finding'] != value['finding'] or value['reviewer_result']['hash'] not in current: raise ValueError('Resolution requires current finding revision and reviewer result')
                if not value['subjects'] or any(ref['hash'] not in subject_results for ref in value['subjects']): raise ValueError('Resolution subject is stale')
                inspected = {binding['source']['hash'] for binding in reviewer['inputs']}
                if any(ref['hash'] not in inspected for ref in value['subjects']): raise ValueError('Reviewer did not inspect exact resolution subjects')
                if any(subject_results[ref['hash']]['executor'] == reviewer['executor'] for ref in value['subjects']): raise ValueError('Resolution reviewer must be independent of subject executor')
            elif kind == 'source':
                for _, old in history:
                    if old['type'] == kind and old['content'].get('id') == value.get('id') and old['content'].get('revision') == value.get('revision') and old['content'] != value: raise ValueError('Conflicting immutable source identity/revision')

    def node_independence(self, snapshot, state, actor):
        if state['contract']['executor']['role'] == 'root' and actor != (self.runtime or {}).get('root_id'): raise ValueError('Root-only task requires actual coordinator')
        subjects = state['contract']['independent_of']
        for resolution in state['resolutions']:
            if resolution['selector'] not in subjects: continue
            for node in resolution['targets']:
                current = snapshot['projection']['current'].get(self.api._phase_evidence.task_key(node))
                if current and current[1]['executor'] == actor: raise ValueError('Independent reviewer cannot be the actual subject executor')


def checkpoint(api, repo, project, runtime, number=None, *, engine=None):
    engine = engine or Workflow(api, repo, project, runtime)
    goals = engine.portfolio(allow_invalid=True)
    ordering_policy = next(
        (
            section.get('configuration', {}).get('portfolio_order')
            for section in project.get('policy', {}).get('sections', [])
            if isinstance(section, dict) and section.get('id') == 'autonomy_approval_parallelism'
        ),
        None,
    )
    limit = worker_limit(project)
    remaining_starts = max(0, limit - unresolved_lease_count(goals))
    capacity_blocked = False
    def partition(steps, runnable, waiting):
        nonlocal remaining_starts, capacity_blocked
        for step in steps:
            starts_worker = step.get('kind') in {'execute', 'review', 'human_approval'} and isinstance(step.get('start'), dict)
            if starts_worker:
                if remaining_starts:
                    runnable.append(step)
                    if number is None: remaining_starts -= 1
                else:
                    capacity_blocked = True
            elif step.get('kind') in {'blocker', 'blocked', 'dependency', 'await_worker'}:
                waiting.append(step)
            else:
                runnable.append(step)
    def capacity_step():
        return {
            'kind': 'await_worker', 'assignment': 'root',
            'action': 'Reviewed max_workers capacity is occupied. Reconcile, release, or recover an existing task lease before starting another worker.',
            'active_leases': unresolved_lease_count(goals), 'max_workers': limit,
            'recheck': {
                'after_seconds': 30,
                'command': ['--intent', 'execute', '--runtime', '<runtime.json>'],
                'action': 'Recheck active leases after the interval; do not start work beyond the reviewed capacity.',
            },
        }
    if number is not None:
        if number not in {g['key'] for g in goals}:
            raise ValueError('Requested goal is not in the validated portfolio')
        goal = next(goal for goal in goals if goal['key'] == number)
        reconciliation = engine.reconciliation_step(goal)
        if isinstance(reconciliation, dict):
            return {'next_steps': [reconciliation]}
        findings = engine.validation_blockers(goal)
        if isinstance(findings, list) and findings:
            return {'next_steps': [{'kind': 'blocker', 'assignment': 'root', 'goal': number,
                'action': 'Repair this goal or one of its prerequisites before continuing.',
                'findings': findings}]}
        runnable_steps, waiting_steps = [], []
        partition(engine.step(number), runnable_steps, waiting_steps)
        if capacity_blocked and len(runnable_steps) < limit:
            runnable_steps.append(capacity_step())
        generic = any('node' in row for row in runnable_steps + waiting_steps)
        steps = runnable_steps + waiting_steps if generic else (runnable_steps or waiting_steps)[:limit]
        if not steps:
            steps = [{'kind': 'terminal_report', 'assignment': 'root', 'goal': number,
                      'state': 'complete', 'action': 'This goal has no remaining workflow work. Report completion; no CLI command is required.'}]
        return {'next_steps': steps}
    runnable_steps = []
    waiting_steps = []
    ordered_goals = api.effective_goal_order(goals, ordering_policy)
    for item in ordered_goals:
        goal = next(goal for goal in goals if goal['key'] == item['goal'])
        if goal['status'] in {'done', 'cancelled'}:
            continue
        reconciliation = engine.reconciliation_step(goal)
        if isinstance(reconciliation, dict):
            runnable_steps.append(reconciliation)
            if len(runnable_steps) >= limit:
                break
            continue
        findings = engine.validation_blockers(goal)
        if isinstance(findings, list) and findings:
            waiting_steps.append({'kind': 'blocker', 'assignment': 'root', 'goal': goal['key'],
                'action': 'Repair this goal or one of its prerequisites before continuing.',
                'findings': findings})
            continue
        blocked = [g for g in goals if g['key'] in goal.get('depends_on', []) and g['status'] != 'done']
        if blocked:
            waiting_steps.append({'kind': 'dependency', 'assignment': 'root', 'goal': goal['key'], 'action': 'Complete or repair the prerequisite goals.', 'dependencies': [g['key'] for g in blocked]})
            continue
        partition(engine.step(goal['key']), runnable_steps, waiting_steps)
        if len(runnable_steps) >= limit:
            break
    if capacity_blocked and len(runnable_steps) < limit:
        runnable_steps.append(capacity_step())
    steps = (runnable_steps or waiting_steps)[:limit]
    if not steps:
        steps = [{'kind': 'terminal_report', 'assignment': 'root', 'state': 'complete',
                  'action': 'All goals are complete or the portfolio is empty. Report workflow exhaustion; no CLI command is required.'}]
    return {'next_steps': steps}


def _public_run(api, repo, intent, source, runtime, payload, number, *, policy_snapshot=None, skip_installation_validation=False, payload_supplied=False):
    """Route every intent through context gates; repairs use the same entrypoint."""
    if payload_supplied and payload is None:
        raise ValueError('Submission must be a JSON object; explicit JSON null is not omitted input')
    if payload is not None and not isinstance(payload, dict):
        raise ValueError('Submission must be a JSON object')
    if runtime is not None and not isinstance(runtime, dict):
        raise ValueError('Runtime evidence must be a JSON object')
    if intent not in api.WORKFLOW_SKILL_INTENTS.get(source, set()):
        raise ValueError('The source skill cannot initiate this intent')
    package = api._package.package_status()
    if not package.get('ok'):
        raise ValueError('Repair or reinstall the invalid ZzzOps package')
    operation = payload.get('operation') if isinstance(payload, dict) else None
    readonly = intent == 'preview'
    if readonly and payload is not None:
        raise ValueError('Preview never accepts mutations')
    if payload is not None and payload.get('operation') not in PUBLIC_OPERATIONS:
        raise ValueError('Submission operation is missing or unsupported')
    provenance = {f: package.get(f) for f in ('version', 'revision')}
    gate = api.workflow_context_step(repo, package, skip_installation_validation=skip_installation_validation)
    # These operations repair only the prerequisite they own. Other intents do
    # not skip gates merely because their skill name was supplied by a caller.
    installation = api._installation.validation_status(repo, provenance) if all(isinstance(v, str) for v in provenance.values()) else {'required': False}
    if installation.get('required') and not skip_installation_validation:
        audit = api._installation.installation_audit(repo)
        if operation == 'installation_record':
            api._installation.record_validation(repo, provenance, outcome=payload['outcome'], audit_signature=payload['audit_signature'])
            return {'next_steps': [{'kind': 'checkpoint', 'action': 'Reinvoke the original intent after installation validation.'}]}
        return {'next_steps': [{'kind': 'installation_validation', 'assignment': 'root', 'instruction': api.workflow_instruction('installation-validation'), 'action': 'Validate the installed package and record the observed outcome.', 'audit': audit, 'submission': {'operation': 'installation_record', 'outcome': '<validated outcome>', 'audit_signature': audit.get('signature', audit.get('audit_signature'))}}]}
    if operation in {'policy_propose', 'policy_approve'}:
        if not (runtime or {}).get('root_id'):
            raise ValueError('Policy design and human approval belong to the root agent')
        directory = repo / '.zzzops' / 'proposals'
        if operation == 'policy_propose':
            proposal = payload['plan']
            prospective = preflight_policy_proposal(api, repo, proposal)
            old_state = api.read_project_state(repo)[2]
            target = api.prepare_policy_defaults(repo, prospective['policy'], (old_state or {}).get('policy'))
            target['evidence'] = prospective['evidence']
            artifacts = {}
            for name, path in (('project', api.project_path(repo)), ('audit', api.project_audit_path(repo))):
                try:
                    artifacts[name] = path.read_text(encoding='utf-8-sig')
                except FileNotFoundError:
                    artifacts[name] = ''
            classification = api._policy.classify_policy_upgrade(old_state, target, artifacts)
            if (old_state and old_state.get('initialized') is True
                    and classification['classification'] == 'representation_only'
                    and all(item['authority_retained'] for item in classification['sections'])
                    and all(api._policy._exact(old_state.get(key), prospective.get(key)) for key in ('backend', 'repository', 'charter'))):
                return {'next_steps': [{'kind': 'checkpoint', 'action': 'The exact policy is already reviewed.',
                                        'classification': classification}]}
            proposal_hash = digest(proposal)
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / (proposal_hash.split(':')[1] + '.json')
            api.atomic_text(path, json.dumps(proposal, ensure_ascii=False, sort_keys=True))
            return {'next_steps': [{'kind': 'human_approval', 'assignment': 'root', 'action': 'Review this exact project/policy proposal with the user before approving.', 'proposal': str(path), 'hash': proposal_hash, 'classification': classification, 'submission': {'operation': 'policy_approve', 'proposal_hash': proposal_hash, 'approved_by': '<user>'}}]}
        proposal_hash = payload['proposal_hash']
        if not explicit_approval(payload.get('approved_by')) or not isinstance(proposal_hash, str) or not __import__('re').fullmatch(r'sha256:[0-9a-f]{64}', proposal_hash):
            raise ValueError('Explicit human approval of the exact proposal hash is required')
        proposal = json.loads((directory / (proposal_hash.split(':')[1] + '.json')).read_text())
        if digest(proposal) != proposal_hash:
            raise ValueError('Policy proposal changed after review')
        prospective = preflight_policy_proposal(api, repo, proposal)
        applied = api.apply_plan(repo, prospective)
        if not applied.get('initialized'):
            api.confirm_project(repo, applied['policy_digest'], payload['approved_by'], [], True)
        if number is not None:
            reviewed = api.read_project_state(repo)[2]
            graph = policy_section(reviewed, 'workflow_adherence')['configuration']['phase_dag']
            if isinstance(graph, dict) and set(graph) == {'nodes', 'task_sets', 'terminals'}:
                engine = Workflow(api, repo, reviewed, runtime)
                with engine.locked():
                    snapshot = engine.node_snapshot(number)
                    if snapshot['graph'] != graph:
                        updated = copy.deepcopy(snapshot['payload'])
                        reference = {'hash': digest(graph), 'uri': 'urn:' + digest(graph)}
                        snapshot['artifacts'][reference['hash']] = graph; updated['graph'] = reference
                        engine.node_persist(snapshot, updated, {'next_steps': [{'kind': 'checkpoint', 'goal': number}]}, payload)
        return {'next_steps': [{'kind': 'checkpoint', 'action': 'Reinvoke the original intent against the newly reviewed policy.'}]}
    if gate and gate.get('id') in {'bootstrap', 'policy-review'}:
        inspection = api.inspect_initialization(repo)
        reference = api._policy_context.write_inspection(repo, inspection)
        return {'next_steps': [{**gate, 'inspection': reference['path'], 'inspection_sha256': reference['sha256'], 'submission': {'operation': 'policy_propose', 'plan': '<complete initialization plan>'}, 'template': str(Path(api.__file__).parent / 'templates/project-goals/INIT_PLAN.json')}]}
    project = api.reviewed_project_state(repo)
    if policy_snapshot is not None:
        policy_snapshot['project'] = project
    if runtime and runtime.get('delegation', {}).get('discovery_complete'):
        configuration = api._workflow_section(project, 'model_routing')['configuration']
        freshness = api._policy.model_inventory_freshness(configuration['model_inventory']['reviewed_pairs'], {'status': 'complete', 'pairs': runtime['available_pairs']})
        if freshness['stale']:
            return {'next_steps': [{'kind': 'policy_review', 'assignment': 'root', 'action': 'Review policy tier mappings for newly discovered model/effort pairs before proceeding.', 'added': freshness['added'], 'submission': {'operation': 'policy_propose', 'plan': '<updated reviewed policy plan>'}}]}
    engine = Workflow(api, repo, project, runtime)
    if operation not in {'read', 'renew'}: engine.portfolio(allow_invalid=True)
    if operation == 'read' and number is not None:
        artifact = payload.get('artifact')
        resolved = None
        if artifact:
            if 'node' in artifact:
                artifact, resolved = engine.resolve_node_selector(number, artifact)
            if 'uri' in artifact:
                api._phase_evidence.validate_ref(artifact)
                artifact = {'hash': artifact['hash'], 'reference': artifact['uri']}
            content = engine.read_artifact(number, artifact)
        elif payload.get('node'):
            snapshot = engine.node_snapshot(number); requested = payload['node']
            result = next(((ref, snapshot['artifacts'][ref['hash']]['content']) for ref in reversed(snapshot['payload']['evidence']) if snapshot['artifacts'][ref['hash']]['content']['node'] == requested), None)
            if result is None:
                selected = snapshot['projection']['states'].get(api._phase_evidence.task_key(payload['node']))
                if selected is None: raise ValueError('Unknown qualified node')
                return {'next_steps': [{'kind': 'read', 'goal': number, 'content': {'inputs': selected['values'], 'resolutions': selected['resolutions']}}]}
            content = {'result': result[0], 'outputs': result[1]['outputs']}
        else:
            _, goal = engine.read(number)
            content = {'specification': goal['human_spec'], 'acceptance_criteria': goal.get('acceptance_criteria', [])}
        return {'next_steps': [{'kind': 'inspect_evidence', 'goal': number, 'content': content, **({'resolved': resolved} if resolved else {})}]}
    administrative = api._workflow_admin.handle(api, repo, project, source, runtime, payload) if operation not in {'capture_propose', 'capture'} else None
    if administrative is not None:
        return administrative
    if operation == 'heartbeat':
        snapshot = engine.node_snapshot(number)
        key = api._phase_evidence.task_key(payload.get('node'))
        lease = snapshot['projection']['leases'].get(key)
        if not lease or lease['token'] != payload.get('lease') or lease['worker'] != payload.get('actor') or lease['owner'] != (runtime or {}).get('root_id'):
            raise ValueError('Heartbeat requires the exact generic node, bound actor and current owner token')
        return {'next_steps': [{'kind': 'await_worker', 'goal': number, 'node': lease['node'], 'lease': lease,
            'action': 'Observe actual worker liveness; while running renew this same ownership through the returned public contract. Recovery requires observed stopped evidence.',
            'renewal': {'operation': 'renew', 'node': lease['node'], 'lease': lease['token'], 'actor': lease['worker'], 'request_id': '<unique renewal request>'}}]}
    if operation == 'capture_propose':
        request = payload['request']
        errors = api.validate_goal_create(request, allow_deferred=True)
        if errors:
            raise ValueError('; '.join(errors))
        if not api._goals.goal_acceptance_criteria(request['body']):
            raise ValueError('Goal design must contain explicit acceptance bullets covering its required behavior')
        return {'next_steps': [{'kind': 'human_approval', 'assignment': 'root', 'action': 'Review the captured goal design with the user, then approve these exact contents.', 'proposal': request, 'proposal_hash': digest(request), 'submission': {'operation': 'capture', 'request': request, 'proposal_hash': digest(request), 'approved_by': '<user>'}}]}
    if operation == 'capture':
        if not (runtime or {}).get('root_id'):
            raise ValueError('Goal design approval must be coordinated by root')
        if not explicit_approval(payload.get('approved_by')) or payload.get('proposal_hash') != digest(payload['request']):
            raise ValueError('Explicit approval of this exact goal design is required; parent relationships do not confer capture authority')
        with engine.locked():
            created = api.apply_goal_create(engine.adapter, engine.repository, payload['request'], allow_deferred=True)
        engine.invalidate()
        # Capture occurs while the human who approved the goal is present.
        # Surface its required understanding work now instead of losing that
        # review opportunity behind a generic later checkpoint.
        return checkpoint(api, repo, project, runtime, engine=engine)
    if operation == 'batch':
        items = payload.get('items')
        if not isinstance(items, list) or not items or len(items) > 20:
            raise ValueError('A batch must contain between one and twenty independent items')
        for item in items:
            if not isinstance(item, dict):
                raise ValueError('Each batch item must be a JSON object')
            if not isinstance(item.get('id'), str) or not item['id']:
                raise ValueError('Each batch item must have a non-empty string id')
            goal = item.get('goal')
            if isinstance(goal, bool) or not isinstance(goal, int) or goal <= 0:
                raise ValueError('Each batch item must target a positive integer goal')
            if not isinstance(item.get('payload'), dict):
                raise ValueError('Each batch item payload must be a JSON object')
            if 'depends_on' in item and not isinstance(item['depends_on'], list):
                raise ValueError('Each batch item depends_on value must be a JSON array')
        goals = {item['goal'] for item in items}
        if len(goals) != len(items):
            raise ValueError('Batch items must target distinct goals; submit same-goal transitions separately')
        records = {}
        def relations(number):
            if number not in records:
                _, records[number] = engine.read(number)
            current = records[number]
            return list(current.get('depends_on', [])) + ([current['parent']] if current.get('parent') is not None else [])
        for number in goals:
            pending = relations(number)
            visited = set()
            while pending:
                related = pending.pop()
                if related in goals:
                    raise ValueError('Dependent or parent/child goals cannot share a mutation batch')
                if related in visited:
                    continue
                visited.add(related)
                pending.extend(relations(related))
        def apply(item):
            try:
                result = engine.mutate(item['goal'], item['payload'])
                return {'ok': True, 'next_steps': result['next_steps']}
            except (ValueError, OSError) as exc:
                return {'ok': False, 'action': 'Retry this item with its original request_id after fixing the error.', 'reason': str(exc)}
        result = api.apply_independent_batch(items, apply)
        steps = [{'kind': 'batch_item', 'id': item['id'], **item['result']} for item in result.get('results', [])]
        if result.get('error'):
            steps.append({'kind': 'repair', 'action': result['error']})
        return {'next_steps': steps}
    if payload is not None and number is not None:
        return engine.mutate(number, payload)
    if payload is not None:
        raise ValueError('Unknown operation or missing goal; request an intent checkpoint for its submission contract')
    if source == '$add-zzzops-goal' or intent == 'capture':
        return {'next_steps': [{'kind': 'capture', 'assignment': 'root', 'instruction': api.workflow_instruction('$add-zzzops-goal'), 'action': 'Interview the user and submit the approved goal design.', 'submission': {'operation': 'capture', 'request': '<validated goal-create request>'}, 'request_fields': ['schema_version', 'request_id', 'title', 'human_body', 'goal']}]}
    if source in {'$bootstrap-zzzops-repository', '$review-zzzops-policy', '$validate-zzzops-installation'}:
        return {'next_steps': []}
    if source == '$migrate-to-zzzops':
        return checkpoint(api, repo, project, runtime, number, engine=engine)
    if source in {'$send-zzzops-feedback', '$suggest-zzzops-work'}:
        return {'next_steps': [{'kind': 'dispatch', 'assignment': 'root', 'instruction': api.workflow_instruction(source), 'action': api.WORKFLOW_SOURCE_ACTIONS[source]}]}
    return checkpoint(api, repo, project, runtime, number, engine=engine)


def public_run(api, repo, intent, source, runtime, payload, number, *, skip_installation_validation=False, payload_supplied=False):
    snapshot = {}
    options = {'skip_installation_validation': True} if skip_installation_validation else {}
    if payload_supplied:
        options['payload_supplied'] = True
    result = _public_run(
        api, repo, intent, source, runtime, payload, number,
        policy_snapshot=snapshot, **options,
    )
    if any('node' in step and 'policy' in step for step in result.get('next_steps', [])):
        return result
    if api._policy_context.needs_context(result):
        return api._policy_context.attach(
            result, repo, snapshot['project'], source=source,
        )
    return result
