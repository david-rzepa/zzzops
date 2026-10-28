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
import threading
import time
import uuid
import re
try:
    import fcntl
except ImportError:  # pragma: no cover - exercised on Windows hosts
    fcntl = None
    import msvcrt
from datetime import datetime
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager, nullcontext
from pathlib import Path
import zzzops_comment_store as comment_store
import zzzops_state_cache as state_cache
import zzzops_stack_integration as stack_integration
import zzzops_git_phase_state as git_phase_state
import zzzops_managed_worktrees as managed_worktrees


_OBSERVED_ARTIFACT_INDEXES = {}
_GIT_ARTIFACT_SNAPSHOTS = {}
_VERIFICATION_LOCKS = {}
_STORAGE_RENEW_INTERVAL_SECONDS = 90


class ContinuationFirstEnvelopeBudget(ValueError):
    """A fresh submission's exact retry template cannot fit its first write."""


HYDRATION_CHECKPOINT_MIN_COMMENTS = 32
HYDRATION_CHECKPOINT_MIN_BYTES = 262144
HYDRATION_CHECKPOINT_MAX_AGE_SECONDS = 86400
HYDRATION_CHECKPOINT_MAX_LATER_COMMENTS = 32


def _rename_node_selectors(value, old, new):
    """Copy a graph fragment while renaming only validated node selectors."""
    if isinstance(value, dict):
        renamed = {name: _rename_node_selectors(child, old, new)
                   for name, child in value.items()}
        if value.get('kind') == 'node' and value.get('node') == old:
            renamed['node'] = new
        return renamed
    if isinstance(value, list):
        return [_rename_node_selectors(child, old, new) for child in value]
    return value


def materialized_state_contract():
    """Exact decoder/reconstruction semantics bound into derived cache identity."""
    return {
        'envelope_codec': 2,
        'hydration_checkpoint_schema': comment_store.HYDRATION_CHECKPOINT_SCHEMA,
        'max_artifact_bytes': comment_store.MAX_ARTIFACT_BYTES,
        'max_delta_depth': comment_store.MAX_DELTA_DEPTH,
        'max_reconstruction_work_bytes': comment_store.MAX_RECONSTRUCTION_WORK_BYTES,
        'max_artifact_records': comment_store.MAX_ARTIFACT_RECORDS,
        'max_history_bytes': comment_store.MAX_HISTORY_BYTES,
    }


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
    'batch', 'bind', 'block', 'phase_finding', 'resolve_goal_blocker',
    'goal_dependency_prepare', 'goal_dependency_review', 'goal_dependency_apply',
    'goal_external_blocker_prepare', 'goal_external_blocker_review',
    'goal_external_blocker_apply',
    'policy_dag_cutover_prepare', 'policy_dag_cutover_review', 'policy_dag_cutover_apply',
    'graph_normalize', 'migration_batch', 'graph_prepare', 'graph_review', 'graph_adopt', 'graph_review_bootstrap',
    'checkpoint_reconcile_prepare', 'checkpoint_reconcile_review', 'checkpoint_reconcile_adopt',
    'capture', 'capture_propose', 'complete', 'feedback_prepare',
    'feedback_submit', 'heartbeat', 'hydration_checkpoint', 'installation_record', 'integrate',
    'publication_attempt_retire',
    'stack_attempt_retire',
    'policy_approve', 'policy_propose', 'read', 'recover', 'release', 'renew',
    'preserve_historical_draft', 'retire_stale_draft', 'route_choice', 'start', 'reconcile', 'submit',
    'stack_prepare', 'stack_status', 'stack_advance', 'compact_candidate', 'restack_continue', 'restack_abort',
})


class VerificationUncertain(ValueError):
    """A started command has no durably observed terminal outcome."""


class GoalContextResolutionAuthenticationError(ValueError):
    """A persisted blocker-resolution journal failed immutable authentication."""


class RenewalBudget:
    """Bound provider work while reserving independent time to release storage."""
    def __init__(self, work_seconds=30, cleanup_seconds=10):
        if any(not math.isfinite(v) or v <= 0 for v in (work_seconds, cleanup_seconds)):
            raise ValueError('Renewal work and cleanup budgets must be finite and positive')
        self.work_seconds = work_seconds
        self.deadline = time.monotonic() + work_seconds
        self.cleanup_seconds = cleanup_seconds

    def timeout(self, maximum=None):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise ValueError('Workflow operation deadline exhausted; retry the same request and lease after cleanup')
        return remaining if maximum is None else min(maximum, remaining)

    @contextmanager
    def cleanup(self):
        previous = self.deadline
        self.deadline = time.monotonic() + self.cleanup_seconds
        try:
            yield
        finally:
            self.deadline = previous

    @contextmanager
    def phase(self):
        """Give one provider phase its full budget, excluding local command time."""
        previous = self.deadline
        self.deadline = time.monotonic() + self.work_seconds
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


def reconcile_legacy_capacity(engine, slot, portfolio):
    """Drop an unpersisted legacy slot only behind the acquisition fence."""
    number = slot['goal']
    if (not isinstance(portfolio, dict) or portfolio.get('complete') is not True
            or portfolio.get('error')
            or any(not isinstance(row, dict) or row.get('goal') in (None, number)
                   for row in portfolio.get('findings', []))):
        raise ValueError(f'Local worker slot goal #{number} ownership inventory is unavailable')
    reservation = getattr(engine, '_storage_reservation', None)
    def renew():
        if (not isinstance(reservation, dict) or not reservation.get('valid')
                or reservation.get('expires_at', 0) <= time.time()):
            raise ValueError('Legacy capacity reconciliation requires the exact start retry under a live storage reservation')
        observed = engine.api.renew_storage_lock(
            reservation['adapter'], engine.repository, 'workflow',
            reservation['owner'], reservation['run'], 300)
        expiry = observed.get('expires_at')
        if (observed.get('acquired') is not True or not isinstance(expiry, (int, float))
                or isinstance(expiry, bool) or not math.isfinite(expiry) or expiry <= time.time()):
            reservation['valid'] = False
            raise ValueError('Legacy capacity reconciliation storage ownership is unconfirmed')
        reservation['expires_at'] = expiry
    renew()
    engine.api.invalidate_provider_reads(engine.repo, engine.repository)
    issue = engine.api.provider_issue_snapshot(engine.repo, engine.repository, number)
    if (not isinstance(issue, dict) or type(issue.get('number')) is not int
            or issue['number'] != number or str(issue.get('state', '')).lower() != 'open'):
        raise ValueError(f'Local worker slot goal #{number} exact ownership observation changed')
    legacy = engine.api.parse_managed_goal(issue.get('body'), number)
    if (not isinstance(legacy, dict) or legacy.get('schema_version') != 1
            or 'claim' not in legacy or legacy['claim'] not in (None, {'owner': None})
            or (legacy.get('workflow') or {}).get('leases')):
        raise ValueError(f'Local worker slot goal #{number} requires ownership migration or recovery')
    # A live acquisition may have reserved its slot before persisting its lease.
    # Confirm the same storage owner still excludes that acquisition before removal.
    renew()


def local_worker_count(engine):
    """Reconcile bounded local slots, then return repository/machine capacity."""
    root = (engine.runtime or {}).get('root_id')
    if not isinstance(root, str) or not root:
        return 0
    try:
        inventory = engine.api._heartbeat.capacity_inventory(repo=engine.repo)
        if not inventory['initialized']:
            goals = engine.portfolio(allow_invalid=True, include_ownership=True)
            slots = []
            for goal in goals:
                for lease in goal.get('operational_leases', []):
                    owner, node, token = lease.get('owner'), lease.get('node'), lease.get('token')
                    if isinstance(owner, str) and owner and isinstance(node, dict) and isinstance(token, str) and token:
                        slots.append({'root_id': owner, 'goal': goal['key'],
                                      'phase': json.dumps(node, sort_keys=True), 'token': token})
            engine.api._heartbeat.initialize_capacity(repo=engine.repo, slots=slots)
            inventory = engine.api._heartbeat.capacity_inventory(repo=engine.repo)
        goals = {goal['key']: goal for goal in engine.portfolio(allow_invalid=True)}
        portfolio = getattr(engine, '_portfolio_cache', {})
        for slot in inventory['slots']:
            goal = goals.get(slot['goal'])
            present = False
            if goal is None:
                findings = portfolio.get('findings', []) if isinstance(portfolio, dict) else []
                if (not isinstance(portfolio, dict) or portfolio.get('complete') is not True
                        or any(isinstance(item, dict) and item.get('goal') == slot['goal'] for item in findings)):
                    raise ValueError(f"Local worker slot goal #{slot['goal']} is malformed or unavailable")
            elif goal.get('schema_version') != 2:
                reconcile_legacy_capacity(engine, slot, portfolio)
            else:
                payload = engine.artifact_index(goal['key']).resolve(goal['envelope']['payload']['hash'])[0]
                present = any(lease.get('token') == slot['token'] for lease in payload['operational']['leases'])
            if not present:
                engine.api._heartbeat.untrack_capacity(
                    repo=engine.repo, root_id=slot['root_id'], goal=slot['goal'],
                    phase=slot['phase'], token=slot['token'])
        return engine.api._heartbeat.active_lease_count(repo=engine.repo, root_id=root)
    except (OSError, ValueError, TypeError) as exc:
        raise ValueError(f'Local worker capacity inventory unavailable: {exc}') from exc


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


class ProviderReadFlights:
    """Share an in-flight observation; failures remain retryable on the next read."""
    def __init__(self):
        self._lock = threading.Lock()
        self._inflight = {}

    def read(self, key, observe):
        with self._lock:
            future = self._inflight.get(key)
            owner = future is None
            if owner:
                future = self._inflight[key] = Future()
        if not owner:
            return future.result()
        try:
            value = observe()
            future.set_result(value)
            return value
        except BaseException as exc:
            future.set_exception(exc)
            raise
        finally:
            with self._lock:
                del self._inflight[key]


class ProviderReadGateway:
    """Context capability: observations only; no raw issue/PR or write methods."""
    def __init__(self, engine, provider):
        self.engine = engine
        self.get_issue_comments = provider.get_issue_comments
        for name in ('get_issue_comments_full', 'get_issue_comments_since', 'get_issue_comment_tail', 'get_issue_comment_tails'):
            if hasattr(provider, name):
                setattr(self, name, getattr(provider, name))
        for name in ('list_issue_metadata', 'get_parent_issue', 'get_sub_issues',
                     'archived_prerequisite_pull', 'archived_prerequisite_reachable'):
            if hasattr(provider, name):
                setattr(self, name, getattr(provider, name))

    def get_issue(self, number):
        engine = self.engine
        key = (str(engine.repo.resolve()), engine.repository, 'issue', number)
        def observe():
            cache = engine._provider_issue_cache
            if key not in cache:
                cache[key] = engine.api.provider_issue_snapshot(
                    engine.repo, engine.repository, number)
            return cache[key]
        return copy.deepcopy(engine._provider_read_flights.read(key, observe))


class Workflow:
    def __init__(self, api, repo, project, runtime=None):
        self.api, self.repo, self.project = api, repo, project
        self.runtime = runtime
        self.repository = api._project_repository_identity(project)
        self.adapter = api.GitHubGoalTransitionAdapter(repo, self.repository)
        self.budget = getattr(api, 'operation_budget', None) or getattr(api, 'renewal_budget', None)
        if self.budget:
            self.adapter.timeout_budget = self.budget.timeout
        self._read_cache = {}
        self._provider_issue_cache = {}
        self._artifact_indexes = {}
        self._provider_read_flights = ProviderReadFlights()
        self._portfolio_cache = None
        self._mutation_adapter = self.adapter

    def node_evidence_policy(self):
        return digest(self.api._phase_evidence.evidence_policy(self.project['policy']))

    def node_historical_policies(self, snapshots, artifacts):
        """Authenticate bounded first-parent policy history for recorded Results."""
        forms = ("full", "pre_static", "current", "normalized")
        projection = self.api._policy.phase_policy_projection
        current = self.project['policy']
        current_hashes = {digest(projection(current, form)) for form in forms}
        recorded = {value for snapshot in snapshots.values() for ref in snapshot['payload']['evidence']
                    for value in (artifacts[ref['hash']].get('provenance', {}).get('policy'),
                                  artifacts[ref['hash']].get('provenance', {}).get('approved_policy'))}
        needed = {value for value in recorded if isinstance(value, str) and value not in current_hashes}
        if not needed:
            return {}, None
        accepted = {}
        # Preserve the pre-existing phase-DAG adapter: an authenticated graph
        # Ref may reconstruct the sole excluded workflow field exactly.
        for snapshot in snapshots.values():
            graph_ref = snapshot['payload'].get('graph')
            old_graph = artifacts.get(graph_ref.get('hash')) if isinstance(graph_ref, dict) else None
            if not isinstance(old_graph, dict):
                continue
            reconstructed = copy.deepcopy(current)
            for section in reconstructed['sections']:
                if section['id'] == 'workflow_adherence':
                    section['configuration']['phase_dag'] = old_graph
            if projection(reconstructed, 'normalized') == projection(current, 'normalized'):
                for form in forms:
                    fingerprint = digest(projection(reconstructed, form))
                    if fingerprint in needed:
                        accepted[fingerprint] = reconstructed
        needed -= set(accepted)
        if not needed:
            return accepted, None
        command = ['git', 'rev-list', '--max-count=65', '--first-parent', 'HEAD', '--', '.zzzops/POLICY.json']
        commits = subprocess.run(command, cwd=self.repo, capture_output=True, text=True, check=True).stdout.splitlines()
        matches = {value: [] for value in needed}
        errors = []
        cache = getattr(self, '_historical_policy_cache', None)
        if cache is None:
            cache = self._historical_policy_cache = {}
        for commit in commits[:64]:
            try:
                cache_key = (commit, digest(current))
                old = cache.get(cache_key)
                if old is None:
                    files = {}
                    for name in ('POLICY.json', 'PROJECT.md', 'PROJECT_AUDIT.md'):
                        raw = subprocess.run(['git', 'show', f'{commit}:.zzzops/{name}'], cwd=self.repo,
                                             capture_output=True, check=True).stdout
                        files[name] = raw.decode('utf-8-sig')
                    state = json.loads(files['POLICY.json'])
                    invalid = self.api._policy.validate_project_state(state)
                    if state.get('initialized') is not True:
                        invalid.append('historical policy is not initialized')
                    if state.get('repository', {}).get('identity') != self.project.get('repository', {}).get('identity'):
                        invalid.append('historical policy repository identity changed')
                    bindings = state.get('bindings', {})
                    for name, file in (('project', 'PROJECT.md'), ('audit', 'PROJECT_AUDIT.md')):
                        if bindings.get(name, {}).get('digest') != self.api._policy.project_digest(files[file]):
                            invalid.append(f'historical {name} policy artifact binding changed')
                    if invalid:
                        errors.extend(invalid)
                        continue
                    old = state['policy']
                    cache[cache_key] = old
                if not self.api._policy.phase_policy_ci_compatible(old, current):
                    continue
                for form in forms:
                    fingerprint = digest(projection(old, form))
                    if fingerprint in needed:
                        matches[fingerprint].append((commit, form, old))
            except (OSError, UnicodeError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as exc:
                errors.append(f'historical policy ancestor {commit} is unavailable or malformed: {exc}')
        for fingerprint, candidates in matches.items():
            # One approved snapshot may naturally expose multiple historical
            # forms with the same digest; ambiguity concerns distinct commits.
            commits_found = {row[0] for row in candidates}
            if len(commits_found) == 1:
                accepted[fingerprint] = candidates[0][2]
            elif candidates:
                errors.append('Ambiguous approved historical policy ancestors match the Result')
            else:
                errors.append('No authenticated matching historical policy ancestor within 64 policy changes')
        return accepted, '; '.join(errors) if errors else None

    def node_authorization_policy_matches(self, value, artifact, result, artifacts):
        """Keep an exact authorization valid across later policy settings changes."""
        accepted = {
            self.node_evidence_policy(),
            digest(self.project['policy']),
            artifact.get('provenance', {}).get('policy'),
            artifact.get('provenance', {}).get('approved_policy'),
        }
        bindings = [item for item in result.get('inputs', []) if item.get('name') == '__policy']
        if len(bindings) == 1:
            binding = bindings[0]; source = binding.get('source', {})
            context = artifacts.get(source.get('hash')) if isinstance(source, dict) else None
            if (binding.get('mode') == 'identity' and not binding.get('path')
                    and isinstance(context, dict) and context.get('type') == 'policy_context'
                    and digest(context) == source.get('hash')):
                accepted.add(source['hash'])
        return value.get('policy') in accepted

    def read_only(self):
        self.adapter = ProviderReadGateway(self, self._mutation_adapter)

    def invalidate(self):
        self._normalization_snapshot = None
        if hasattr(self.api, 'invalidate_provider_reads'):
            self.api.invalidate_provider_reads(self.repo, self.repository)
        getattr(self, '_read_cache', {}).clear()
        self._read_cache = {}
        self._portfolio_cache = None
        self._artifact_indexes = {}
        self._provider_issue_cache = {}
        self.clear_publication_projection()

    def clear_publication_projection(self):
        """Discard the invocation's provider discovery and unused tail window."""
        self._publication_candidate_discovery = None
        getattr(self, '_publication_tails', {}).clear()

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

    def node_same_local_ref(self, left, right, number, resolve):
        """Compare content identity across local urn and stored goal locators."""
        for reference in (left, right):
            self.api._phase_evidence.validate_ref(reference)
            if self.node_ref_goal(reference, number) != number:
                raise ValueError('Goal-context source belongs to another goal')
        return (left['hash'] == right['hash']
                and resolve(left) == resolve(right))

    def node_published_artifact(self, reference):
        """Decode exact Git bytes using the same bound as generic node inputs."""
        self.api._phase_evidence.validate_ref(reference)
        match = re.fullmatch(r'git:([0-9a-f]{40}):(.+)', reference['uri'])
        if not match or match[2].startswith('/') or '..' in Path(match[2]).parts:
            raise ValueError('Published artifact locator requires exact commit and repository path')
        result = subprocess.run(['git', 'show', match[1] + ':' + match[2]], cwd=self.repo, capture_output=True, check=False)
        if result.returncode: raise ValueError('Published artifact read failed')
        raw = result.stdout
        if len(raw) > 1048576 or 'sha256:' + hashlib.sha256(raw).hexdigest() != reference['hash']:
            raise ValueError('Published artifact bytes hash or semantic size bound rejected')
        return comment_store.strict_json(raw.decode('utf-8')), raw

    def artifact_index(self, number):
        key = (str(self.repo.resolve()), self.repository, 'history', number)
        return self._provider_read_flights.read(key, lambda: self._artifact_index(number))

    def _artifact_index(self, number):
        if number not in self._artifact_indexes:
            key = (str(self.repo.resolve()), self.repository, number)
            previous = _OBSERVED_ARTIFACT_INDEXES.get(key)
            comments = None
            provider_comments = None
            cache_head = None
            cached = None
            complete_audit = None
            issue = getattr(self, '_issue_observations', {}).get(number)
            tail_reader = getattr(self.adapter, 'get_issue_comment_tail', None)
            if issue is None and callable(tail_reader):
                issue = self.adapter.get_issue(number)
            if issue is not None and callable(tail_reader):
                try:
                    envelope = self.api.parse_managed_goal(issue.get('body', ''), number)
                    issue_hash = comment_store.text_hash(issue['body'])
                    prefetched = getattr(self, '_publication_tails', {}).pop((number, issue_hash), None)
                    if isinstance(prefetched, Exception):
                        raise prefetched
                    tail = prefetched if prefetched is not None else tail_reader(number)
                    contract = materialized_state_contract()
                    cached = state_cache.load(self.repository, number, issue_hash, contract)
                    if cached is None and state_cache.requires_full_read(
                            self.repository, number, issue_hash, contract):
                        raise ValueError('materialized state is stale or unreadable')
                    if cached is not None:
                        audit_age = time.time() - cached['last_complete_audit']
                        if audit_age < 0 or audit_age > HYDRATION_CHECKPOINT_MAX_AGE_SECONDS:
                            raise ValueError('materialized state complete audit is stale')
                    cache_head, suffix = (state_cache.classify_head(cached['provider_head'], tail)
                                          if cached is not None else (None, []))
                    if cache_head == 'exact':
                        comments = cached['materialized_comments']
                        provider_comments = tail
                    elif cache_head == 'append':
                        marker = cached['provider_head'][-1].get('updated_at')
                        since_reader = getattr(self.adapter, 'get_issue_comments_since', None)
                        if marker and callable(since_reader):
                            incremental = since_reader(number, marker)
                            if state_cache.head(incremental) is None:
                                raise ValueError('incremental materialized state suffix is ambiguous')
                            prior = {row['id']: row for row in cached['provider_head']}
                            observed_incremental = state_cache.head(incremental)
                            for row in observed_incremental:
                                if (row['id'] in prior and
                                        row['body_hash'] != prior[row['id']]['body_hash']):
                                    raise ValueError('incremental materialized state changed cached history')
                            last_cached = cached['provider_head'][-1]['id']
                            suffix = [row for row in incremental if row['id'] > last_cached]
                            tail_suffix_ids = {row['id'] for row in tail if row['id'] > last_cached}
                            if not suffix or not tail_suffix_ids.issubset({row['id'] for row in suffix}):
                                raise ValueError('incremental materialized state suffix is incomplete')
                        checkpoint_rows, checkpoint_ids, checkpoint_last = [], set(), None
                        transaction = None
                        for row in cached['materialized_comments']:
                            envelope = comment_store.decode_envelope(row.get('body', ''))
                            context = (envelope or {}).get('context') or {}
                            checkpoint = context.get('checkpoint') if context.get('kind') == 'hydration_checkpoint' else None
                            if isinstance(checkpoint, dict):
                                transaction = envelope.get('transaction')
                                checkpoint_last = checkpoint.get('observation', {}).get('last_id')
                                break
                        if transaction is None or type(checkpoint_last) is not int:
                            raise ValueError('cached materialized state lacks its checkpoint binding')
                        for row in cached['materialized_comments']:
                            envelope = comment_store.decode_envelope(row.get('body', ''))
                            if (envelope or {}).get('transaction') == transaction:
                                checkpoint_rows.append(row); checkpoint_ids.add(row.get('id'))
                        later = [row for row in cached['materialized_comments']
                                 if row.get('id', 0) > checkpoint_last and row.get('id') not in checkpoint_ids]
                        retained_ids = {row.get('id') for row in later}
                        later.extend(row for row in suffix if row.get('id') not in retained_ids)
                        comments = comment_store.hydration_checkpoint_view(
                            checkpoint_rows, later, repository=self.repository, goal=number,
                            issue_body_hash=issue_hash)[0]
                        provider_comments = tail
                    elif cache_head in {'changed', 'invalid'}:
                        # A compact observation that is not a strict append may
                        # represent an edit, deletion, reorder, or ambiguity.
                        # Only a complete provider read can safely replace it.
                        raise ValueError('materialized state head changed')
                    discovered = ObservedArtifactIndex(tail)
                    candidates = []
                    for row, record in discovered.envelope_comments:
                        context = record.get('context') or {}
                        checkpoint = context.get('checkpoint') if context.get('kind') == 'hydration_checkpoint' else None
                        if (isinstance(checkpoint, dict) and checkpoint.get('goal') == number
                                and checkpoint.get('issue_body_hash') == comment_store.text_hash(issue['body'])
                                and envelope and envelope.get('payload', {}).get('hash') in checkpoint.get('required', [])):
                            candidates.append((row['id'], record.get('transaction'), checkpoint))
                    for _, transaction, checkpoint in sorted(candidates, reverse=True) if comments is None else []:
                        rows = [row for row, record in discovered.envelope_comments
                                if record.get('transaction') == transaction]
                        ids = {row['id'] for row in rows}
                        later = [row for row in tail if row['id'] > checkpoint['observation']['last_id'] and row['id'] not in ids]
                        created = max((row.get('created_at') or '' for row in rows), default='')
                        try:
                            age = time.time() - datetime.fromisoformat(created.replace('Z', '+00:00')).timestamp()
                        except (ValueError, TypeError):
                            continue
                        if age < 0 or age > HYDRATION_CHECKPOINT_MAX_AGE_SECONDS or len(later) > HYDRATION_CHECKPOINT_MAX_LATER_COMMENTS:
                            continue
                        comments = comment_store.hydration_checkpoint_view(
                            rows, later, repository=self.repository, goal=number,
                            issue_body_hash=comment_store.text_hash(issue['body']))[0]
                        provider_comments = tail
                        break
                except (ValueError, KeyError, TypeError, self.api.GoalHistoryReadError):
                    comments = None
            if comments is None:
                comments = self.adapter.get_issue_comments(number)
                provider_comments = comments
                complete_audit = time.time()
            limits = (comment_store.MAX_ARTIFACT_BYTES, comment_store.MAX_DELTA_DEPTH,
                      comment_store.MAX_RECONSTRUCTION_WORK_BYTES, comment_store.MAX_ARTIFACT_RECORDS)
            # Reuse only an exact fresh provider observation with no locally
            # staged records. Edits, deletions and changed decoder bounds rebuild.
            reusable = (previous is not None and previous._limits == limits
                        and previous.comments == comments
                        and all(value is None for value in previous.records.values()))
            observed = previous if reusable else ObservedArtifactIndex(comments, previous=previous)
            observed._materialized_state_cache = cache_head in {'exact', 'append'}
            if issue is not None and provider_comments is not None:
                state_cache.store(self.repository, number, comment_store.text_hash(issue['body']),
                                  provider_comments, observed.comments, materialized_state_contract(),
                                  complete_audit or (cached or {}).get('last_complete_audit'))
            self._artifact_indexes[number] = observed
            if key not in _OBSERVED_ARTIFACT_INDEXES and len(_OBSERVED_ARTIFACT_INDEXES) >= 4:
                _OBSERVED_ARTIFACT_INDEXES.pop(next(iter(_OBSERVED_ARTIFACT_INDEXES)))
            _OBSERVED_ARTIFACT_INDEXES[key] = observed
        return self._artifact_indexes[number]

    def hydration_checkpoint_candidate(self, number):
        """Prepare an idempotent compact checkpoint after an expensive full read."""
        index = self.artifact_index(number)
        if getattr(index, '_materialized_state_cache', False):
            return None
        size = sum(len(row.get('body', '').encode('utf-8')) for row in index.comments)
        if len(index.comments) < HYDRATION_CHECKPOINT_MIN_COMMENTS and size < HYDRATION_CHECKPOINT_MIN_BYTES:
            return None
        # The observed index validates individual envelopes with bounded reads.
        # Optional checkpoint generation also needs an eager aggregate index.
        decoded = sum(index.decode_sizes[row.get('body', '')] for row in index.comments)
        if decoded > comment_store.MAX_RECONSTRUCTION_WORK_BYTES:
            return None
        issue = self.adapter.get_issue(number)
        envelope = self.api.parse_managed_goal(issue.get('body', ''), number)
        if not envelope or envelope.get('schema_version') != 2:
            return None
        issue_hash = comment_store.text_hash(issue['body'])
        generation = 1
        for record in index.envelopes:
            context = record.get('context') or {}
            checkpoint = context.get('checkpoint') if context.get('kind') == 'hydration_checkpoint' else None
            if (isinstance(checkpoint, dict) and checkpoint.get('goal') == number
                    and checkpoint.get('issue_body_hash') == issue_hash
                    and envelope['payload']['hash'] in checkpoint.get('required', [])):
                generation = max(generation, checkpoint.get('generation', 0) + 1)
                transaction = record.get('transaction')
                rows = [row for row, item in index.envelope_comments if item.get('transaction') == transaction]
                comment_store.hydration_checkpoint_view(
                    rows, [], repository=self.repository, goal=number, issue_body_hash=issue_hash)
                prefix = [row for row in index.comments if row.get('id', 0) <= checkpoint['observation']['last_id']]
                if comment_store.comment_observation(prefix) == checkpoint['observation']:
                    created = max((row.get('created_at') or '' for row in rows), default='')
                    if not created:
                        return None
                    try:
                        age = time.time() - datetime.fromisoformat(created.replace('Z', '+00:00')).timestamp()
                    except (TypeError, ValueError):
                        age = HYDRATION_CHECKPOINT_MAX_AGE_SECONDS + 1
                    if 0 <= age <= HYDRATION_CHECKPOINT_MAX_AGE_SECONDS:
                        return None
        try:
            bodies, checkpoint = comment_store.hydration_checkpoint_bodies(
                self.repository, number, issue_hash, index.comments, [envelope['payload']['hash']],
                generation=generation)
        except ValueError as exc:
            # Checkpointing is an optimization. Histories whose live closure
            # cannot fit the bounded checkpoint format must continue through
            # the verified full-hydration path instead of blocking execution.
            if str(exc) in {
                'Transaction artifact record limit exceeded',
                'Transaction reconstruction work limit exceeded',
                'Artifact reconstruction work limit exceeded',
                'Artifact cannot be split within the provider comment contract; use a published Git content reference',
            }:
                return None
            raise
        present = {row.get('body', '') for row in index.comments}
        if all(body in present for body in bodies):
            return None
        identity = digest(checkpoint)
        return {'kind': 'hydration_checkpoint', 'assignment': 'root', 'goal': number,
                'action': 'Publish the prepared idempotent hydration checkpoint, then resume this goal.',
                'checkpoint': identity, 'source_comments': len(index.comments), 'source_bytes': size,
                'submission': {'operation': 'hydration_checkpoint', 'checkpoint': identity,
                               'request_id': 'hydration-' + identity[7:23]}}

    def publish_hydration_checkpoint(self, number, expected):
        """Re-observe, preflight, append and verify one exact checkpoint transaction."""
        issue = self.adapter.get_issue(number)
        envelope = self.api.parse_managed_goal(issue.get('body', ''), number)
        if not envelope or envelope.get('schema_version') != 2:
            raise ValueError('Hydration checkpoints require a current schema v2 goal')
        full_read = getattr(self.adapter, 'get_issue_comments_full', self.adapter.get_issue_comments)
        comments = full_read(number)
        existing_index = ObservedArtifactIndex(comments)
        issue_hash = comment_store.text_hash(issue['body'])
        def cache_complete(source, checkpoint, transaction):
            source_index = ObservedArtifactIndex(source)
            rows = [row for row, item in source_index.envelope_comments
                    if item.get('transaction') == transaction]
            row_ids = {row.get('id') for row in rows}
            last_id = checkpoint['observation']['last_id']
            later = [row for row in source if row.get('id', 0) > last_id and row.get('id') not in row_ids]
            materialized = comment_store.hydration_checkpoint_view(
                rows, later, repository=self.repository, goal=number, issue_body_hash=issue_hash)[0]
            state_cache.store(self.repository, number, issue_hash, source, materialized,
                              materialized_state_contract(), time.time())
        generation = 1
        for record in existing_index.envelopes:
            context = record.get('context') or {}
            checkpoint = context.get('checkpoint') if context.get('kind') == 'hydration_checkpoint' else None
            if isinstance(checkpoint, dict) and digest(checkpoint) == expected:
                rows = [row for row, item in existing_index.envelope_comments if item.get('transaction') == expected]
                comment_store.hydration_checkpoint_view(
                    rows, [], repository=self.repository, goal=number,
                    issue_body_hash=comment_store.text_hash(issue['body']))
                cache_complete(comments, checkpoint, expected)
                return {'next_steps': [{'kind': 'checkpoint', 'goal': number, 'checkpoint': expected,
                                        'action': 'Hydration checkpoint is durable; resume the goal.'}]}
            if isinstance(checkpoint, dict) and checkpoint.get('goal') == number:
                generation = max(generation, checkpoint.get('generation', 0) + 1)
        bodies, checkpoint = comment_store.hydration_checkpoint_bodies(
            self.repository, number, comment_store.text_hash(issue['body']), comments,
            [envelope['payload']['hash']],
            generation=generation)
        identity = digest(checkpoint)
        if identity != expected:
            raise ValueError('Hydration checkpoint source changed; request a fresh checkpoint')
        comment_store.preflight_comments(comments, bodies, checkpoint['required'])
        present = {row.get('body', '') for row in comments}
        for body in bodies:
            if body in present:
                continue
            stored = self.adapter.create_issue_comment(number, body)
            if stored.get('body') != body:
                raise ValueError('Provider did not confirm the exact hydration checkpoint body')
        confirmed = full_read(number)
        expected_bodies = set(bodies)
        rows = [row for row in confirmed if row.get('body') in expected_bodies]
        comment_store.hydration_checkpoint_view(
            rows, [], repository=self.repository, goal=number,
            issue_body_hash=comment_store.text_hash(issue['body']))
        cache_complete(confirmed, checkpoint, identity)
        self.invalidate()
        return {'next_steps': [{'kind': 'checkpoint', 'goal': number, 'checkpoint': identity,
                                'action': 'Hydration checkpoint is durable; resume the goal.'}]}

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

    def portfolio(self, *, allow_invalid=True, include_ownership=False):
        if self._portfolio_cache is None:
            # Context does not consume PR observations. Publication/integration
            # validate their exact provider subjects separately.
            self._portfolio_cache = self.api.portfolio_snapshot(self.repo, include_pull_requests=False)
        if include_ownership:
            if (not self._portfolio_cache.get('complete')
                    or any(row.get('code') == 'malformed_record' for row in self._portfolio_cache.get('findings', []))):
                raise ValueError('Ownership inventory unavailable: incomplete or malformed open-goal portfolio')
            # Admission must observe every unresolved owner, including expired
            # leases. Missing/corrupt payloads cannot be interpreted as free slots.
            goals = [goal for goal in self._portfolio_cache.get('goals', [])
                     if goal.get('schema_version') == 2 and goal.get('status') not in {'done', 'cancelled'}]
            def ownership(goal):
                try:
                    payload = self.artifact_index(goal['key']).resolve(goal['envelope']['payload']['hash'])[0]
                    leases = payload['operational']['leases']
                    if not isinstance(leases, list):
                        raise ValueError('Invalid operational leases')
                    return goal['key'], copy.deepcopy(leases), None
                except (ValueError, KeyError, TypeError) as exc:
                    return goal['key'], None, exc
            with ThreadPoolExecutor(max_workers=min(10, len(goals) or 1)) as pool:
                observed = {key: (leases, error) for key, leases, error in pool.map(ownership, goals)}
            for goal in goals:
                leases, error = observed[goal['key']]
                if error is not None:
                    raise ValueError(f"Ownership inventory unavailable for goal #{goal['key']}: {error}") from error
                goal['operational_leases'] = leases
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
        keepalive_stop = threading.Event()
        keepalive = None
        attempted = False
        observed_adapter = self.adapter
        if isinstance(observed_adapter, ProviderReadGateway): self.adapter = self._mutation_adapter
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
                'expires_at': expires_at, 'valid': True, 'mutex': threading.Lock(),
            }
            self._storage_reservation = reservation
            def maintain_reservation():
                while not keepalive_stop.wait(_STORAGE_RENEW_INTERVAL_SECONDS):
                    if keepalive_stop.is_set():
                        return
                    with reservation['mutex']:
                        if not reservation['valid']:
                            return
                        try:
                            renewed = api.renew_storage_lock(
                                adapter, self.repository, 'workflow', owner, run, 300,
                            )
                            renewed_expiry = renewed.get('expires_at')
                            if (not renewed.get('acquired') or not isinstance(renewed_expiry, (int, float))
                                    or isinstance(renewed_expiry, bool) or renewed_expiry <= time.time()):
                                reservation['valid'] = False
                                return
                            reservation['expires_at'] = renewed_expiry
                        except Exception:
                            # Provider uncertainty never extends write authority.
                            reservation['valid'] = False
                            return
            keepalive = threading.Thread(target=maintain_reservation, daemon=True)
            keepalive.start()
            self.invalidate()
            yield
        finally:
            keepalive_stop.set()
            if keepalive is not None:
                keepalive.join()
            self.adapter = observed_adapter
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
            with reservation['mutex']:
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
        if not isinstance(value, dict) and isinstance((goal.get('implementation') or {}).get('pr'), str):
            # Legacy publication consumers also request their exact subject;
            # a lightweight context snapshot never stands in for PR evidence.
            observed, _, _ = self.api._github_pull_request_states(
                self.repo, 'gh', [{'number': goal['key']}],
                {goal['key']: {'repository_context': goal['implementation']}},
            )
            value = observed.get(goal['key'])
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
        return self.publication_topology(implementation, self.publication_identity(goal),
                                         managed - {None}, goal_number=goal['key'])

    def publication_topology(self, implementation, identity, managed_branches, *, goal_number=None):
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
        try:
            planning = policy_section(self.project, 'git_review_release')['configuration'].get('release_planning')
        except (ValueError, KeyError):
            planning = None
        if isinstance(planning, dict) and planning.get('enabled') and goal_number is not None:
            plan = self.api.GitHubReleasePlanAdapter(self.repo, self.repository).read(self.repository)
            if plan is None:
                return topology_repair('the reviewed release plan is unavailable')
            lane = self.api._releases.target_release(plan, goal_number)
            prefix = planning.get('release_branch_prefix')
            integration = planning.get('integration_branch')
            lane_trunk = (prefix + str(lane) if isinstance(prefix, str) and prefix
                          and type(lane) is int and lane > 0 else None)
            if lane_trunk is not None and identity.get('base_ref') == lane_trunk:
                trunk = lane_trunk
            elif isinstance(integration, str) and integration and identity.get('base_ref') == integration:
                trunk = integration
            owners = {}
            for goal in self.portfolio():
                branch = (goal.get('implementation') or {}).get('branch')
                if branch:
                    if branch in owners and owners[branch] != goal['key']:
                        return topology_repair('managed branch belongs to multiple goals', branches=[branch])
                    owners[branch] = goal['key']
            unknown = sorted(branch for branch in managed_branches - {implementation['branch']}
                             if branch not in owners)
            if unknown:
                return topology_repair('managed PR release assignment is unknown', branches=unknown)
            managed_branches = {branch for branch in managed_branches
                if branch == implementation['branch']
                or self.api._releases.target_release(plan, owners[branch]) == lane}
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
                    if (candidate_row and cursor == identity['base_ref']
                            and isinstance(identity.get('base_oid'), str)
                            and re.fullmatch(r'[0-9a-f]{40}', identity['base_oid'])):
                        fetched = subprocess.run(['git', 'fetch', '--no-tags', 'origin',
                            'refs/heads/' + trunk], cwd=self.repo,
                            capture_output=True, text=True)
                        if fetched.returncode == 0:
                            tip = subprocess.run(['git', 'rev-parse', 'FETCH_HEAD'],
                                cwd=self.repo, capture_output=True, text=True)
                            if tip.returncode == 0 and re.fullmatch(r'[0-9a-f]{40}', tip.stdout.strip()):
                                try:
                                    movement = git_phase_state.classify_base_move(self.repo,
                                        old_base=identity['base_oid'], new_base=tip.stdout.strip())
                                except (ValueError, OSError, subprocess.SubprocessError):
                                    movement = None
                                if movement and movement['action'] in {'current', 'retarget_only'}:
                                    return {'kind': 'repair_stack', 'assignment': 'root',
                                        'action': (f'Retarget the PR base from integrated {cursor} to {trunk} '
                                            'without rewriting the candidate head; fetch and recheck exact provider topology.'),
                                        'continuation': 'Refresh base-bound CI and review if required, preserving equivalent-tree phase evidence.',
                                        'identities': [implementation['branch'], cursor, trunk,
                                            identity['head_oid'], identity['base_oid'], tip.stdout.strip()],
                                        'publication_directive': {'action': 'retarget_pr_base',
                                            'from': cursor, 'to': trunk, 'head': identity['head_oid']},
                                        'base_movement': movement,
                                        'requires_phase_reverification': False}
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
        local_head, local_base = ((rev(implementation['branch']), rev(implementation['base']))
                                  if implementation.get('pr') else (None, None))
        if implementation.get('pr') and local_head == identity['head_oid'] and local_base != identity['base_oid']:
            try:
                movement = git_phase_state.classify_base_move(self.repo,
                    old_base=local_base, new_base=identity['base_oid'])
            except (ValueError, OSError, subprocess.SubprocessError):
                movement = None
            if movement and movement['action'] == 'retarget_only':
                return {'kind': 'repair_stack', 'assignment': 'root',
                    'action': (f"Fetch exact provider base {identity['base_oid']} for {implementation['base']} "
                               'and recheck topology; the equivalent-tree advance preserves phase evidence and needs no branch rewrite.'),
                    'continuation': 'Recheck the exact PR head and base after fetching; preserve all current phase evidence.',
                    'identities': [implementation['branch'], implementation['base'], identity['head_oid'], identity['base_oid']],
                    'head': identity['head_oid'], 'base': identity['base_oid'],
                    'base_movement': movement, 'requires_phase_reverification': False}
            if movement and movement['action'] in {'topology_rewrite', 'rebase_and_reverify'}:
                changed_tree = movement['action'] == 'rebase_and_reverify'
                scope = ('rebase the candidate and reverify affected design, tests and implementation'
                         if changed_tree else
                         'repair candidate topology while retaining equivalent-tree phase evidence')
                return {'kind': 'repair_stack', 'assignment': 'root',
                    'action': (f"Preview {scope} for {implementation['branch']} against exact provider base "
                               f"{identity['base_oid']}; require fresh head-bound review and CI after any rewrite."),
                    'continuation': 'Use the reviewed restack path, then recheck exact PR head and base before publication.',
                    'identities': [implementation['branch'], implementation['base'], identity['head_oid'], identity['base_oid']],
                    'head': identity['head_oid'], 'base': identity['base_oid'],
                    'base_movement': movement, 'requires_phase_reverification': changed_tree}
        if implementation.get('pr') and (local_head != identity['head_oid'] or local_base != identity['base_oid']):
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


    def automatic_heartbeat(self, number, request, durable, response):
        """Local post-commit effect; never changes durable acknowledgement/authority."""
        if request.get('operation') not in {'start', 'bind'}:
            return response
        node = request.get('node')
        lease = next((v for v in durable.get('leases', []) if v['node'] == node), None)
        if not lease or lease['owner'] != (self.runtime or {}).get('root_id'):
            return response
        step = next((v for v in response.get('next_steps', []) if v.get('node') == node), None)
        if step is None or (step.get('lease') or {}).get('token') != lease['token']:
            return response
        phase = json.dumps(node, sort_keys=True)
        try:
            self.api._heartbeat.track_capacity(
                repo=self.repo, root_id=lease['owner'], goal=number,
                phase=phase, token=lease['token'])
        except (OSError, ValueError, TypeError) as exc:
            step['monitoring'] = {'status': 'unavailable', 'reason': str(exc),
                'action': 'Ownership remains held. Repair the local capacity inventory and replay this exact acquisition before starting more work.'}
            return response
        if not lease.get('worker'):
            return response
        settings = (self.runtime or {}).get('heartbeat') or {}
        probes = settings.get('probes', {}) if isinstance(settings, dict) else {}
        probe = probes.get(lease['worker']) if isinstance(probes, dict) else None
        runtime_path = getattr(self.api, 'runtime_path', None)
        if not probe or not runtime_path:
            step['monitoring'] = {'status': 'unavailable', 'action': 'Local worker liveness capability is unavailable. Finish within the lease or use exact public renewal while observing the actual worker; expiry never permits takeover.'}
            return response
        try:
            grace = float(settings.get('grace_seconds', 120))
            interval = float(settings.get('interval_seconds', 120))
            remaining = lease['expires_at'] - time.time()
            if not (0 <= grace <= 300 and 0 < interval <= 120) or remaining <= 60:
                raise ValueError('Heartbeat grace/interval or remaining lease is unsafe')
            result = self.api._heartbeat.start_heartbeat(
                repo=self.repo, root_id=lease['owner'], runtime_path=Path(runtime_path),
                cli_path=Path(__file__).with_name('zzzops.py'), goal=number, node=node,
                phase=phase, token=lease['token'], actor=lease['worker'],
                probe_argv=probe, grace_seconds=min(grace, remaining - 60), interval_seconds=interval,
                expires_at=lease['expires_at'], max_workers=worker_limit(self.project))
            step['monitoring'] = {'status': 'automatic', 'pid': result['pid']}
        except (OSError, ValueError, TypeError) as exc:
            step['monitoring'] = {'status': 'unavailable', 'reason': str(exc),
                'action': 'Ownership remains held. Repair local monitoring and replay this exact acquisition, or finish within the lease; observe stopped evidence before recovery.'}
        return response

    def stop_completed_heartbeat(self, number, payload, durable, response):
        response = self.automatic_heartbeat(number, payload, durable, response)
        token = payload.get('lease')
        leases = durable.get('leases', [])
        if isinstance(leases, dict): leases = leases.values()
        if not token or any(v['token'] == token for v in leases):
            return response
        try:
            self.api._heartbeat.untrack_capacity(repo=self.repo, root_id=(self.runtime or {}).get('root_id'),
                goal=number, phase=json.dumps(payload.get('node'), sort_keys=True), token=token)
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



    def node_snapshot(self, number, *, publication_probe=False, graph_override=None,
                      prospective=None, dependency_override=None, workspace_target=None):
        """Read exact scoped records; only relationship consumers request closure."""
        ev = self.api._phase_evidence
        snapshots, artifacts, issues, bootstrap = {}, dict((prospective or {}).get('artifacts', {})), {}, {}
        published, validated = {}, set()
        def remember(value):
            key = digest(value); artifacts[key] = value
            return {'hash': key, 'uri': 'urn:' + key}
        def load(n):
            if n in snapshots: return snapshots[n]
            issue = self.adapter.get_issue(n); issues[n] = issue
            if not hasattr(self, '_issue_observations'):
                self._issue_observations = {}
            self._issue_observations[n] = copy.deepcopy(issue)
            envelope = prospective['envelope'] if prospective and n == number else self.api.parse_managed_goal(issue.get('body', ''), n)
            if not envelope: raise ValueError(f'Goal {n} has no readable identity envelope')
            if envelope['schema_version'] == 1:
                if str(issue.get('state', '')).lower() == 'closed': raise ValueError(f'Archived predecessor {n} requires reviewed historical evidence equivalence')
                entries = policy_section(self.project, 'workflow_adherence')['configuration'].get('migration_entries', [])
                entry = next((r['graph'] for r in entries if r.get('from') == 1 and r.get('to') == 2), None)
                if entry is None: raise ValueError('Schema version 1 requires trusted reviewed migration entry; no legacy execution')
                if envelope.get('workflow', {}).get('leases'): raise ValueError('Predecessor worker ownership must be observed stopped before conversion')
                ev.validate_graph(entry)
                source = {'type': 'migration_source', 'content': copy.deepcopy(issue), 'producer': None,
                          'provenance': {'actor': (self.runtime or {}).get('root_id', ''), 'source': None, 'policy': self.node_evidence_policy()}}
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
                        artifacts[ref['hash']], published[ref['hash']] = self.node_published_artifact(ref)
                    else:
                        artifacts[ref['hash']] = self.artifact_index(owner).observe(ref['hash'])[0]
                value = artifacts[ref['hash']]
                if ref['hash'] not in published and ref['hash'] not in validated:
                    if digest(value) != ref['hash']: raise ValueError('Artifact checksum mismatch')
                    validated.add(ref['hash'])
                return value
            payload = resolve(envelope['payload'])
            ev.contract_fields(payload, {'spec', 'graph', 'evidence', 'operational'} | (set(payload) & {'phase_data', 'goal_context', 'goal_context_resolutions', 'goal_context_dependency_events', 'goal_context_archived_prerequisites', 'workflow', 'stack_integration', 'publication_certificate'}), 'Payload')
            if 'publication_certificate' in payload:
                certificate = resolve(payload['publication_certificate'])
                if (not isinstance(certificate, dict) or certificate.get('type') != 'publication_certificate'
                        or certificate.get('content', {}).get('goal') != n):
                    raise ValueError('Stored publication certificate is invalid')
            ev.contract_fields(payload['operational'], {'leases', 'receipts'}, 'Operational payload')
            if not isinstance(payload['evidence'], list): raise ValueError('Evidence must be an ordered Ref array')
            historical_graph = resolve(payload['graph'])
            policy_graph = copy.deepcopy(policy_section(
                self.project, 'workflow_adherence')['configuration']['phase_dag'])
            if payload['evidence'] and policy_graph != historical_graph:
                old_nodes = {node['id']: node for node in historical_graph['nodes']}
                new_ids = {node['id'] for node in policy_graph['nodes']}
                for index, candidate in enumerate(policy_graph['nodes']):
                    matches = []
                    for old_id, old_node in old_nodes.items():
                        if old_id in new_ids or old_id == candidate['id']:
                            continue
                        comparable = copy.deepcopy(candidate); comparable['id'] = old_id
                        if comparable == old_node:
                            matches.append(old_id)
                    if len(matches) == 1:
                        policy_graph['nodes'][index] = _rename_node_selectors(
                            candidate, matches[0], candidate['id'])
            definition = self.api._static_workflow.definition(policy_graph, self.api._graph_compiler)
            stored_workflow_graph = None
            if 'workflow' in payload:
                ev.contract_fields(payload['workflow'], {'version', 'graph'}, 'Workflow definition')
                if payload['workflow']['version'] != self.api._static_workflow.VERSION:
                    raise ValueError('Unsupported stored workflow definition version')
                stored_workflow_graph = resolve(payload['workflow']['graph'])
                ev.validate_graph(stored_workflow_graph)
            graph = definition['graph'] if envelope['state'] == 'open' else historical_graph
            source_artifact = resolve(payload['spec'])
            if source_artifact.get('type') == 'migration_source':
                # A reviewed schema-conversion entry is a policy-defined protocol,
                # not a goal-specific override of the product workflow.
                entries = policy_section(self.project, 'workflow_adherence')['configuration'].get('migration_entries', [])
                if not any(row.get('from') == 1 and row.get('to') == 2 and row.get('graph') == historical_graph for row in entries):
                    raise ValueError('Prepared migration graph differs from trusted current policy entry')
                graph, definition = historical_graph, None
            if n == number and graph_override is not None:
                graph = copy.deepcopy(graph_override)
                # Recovery must retain the exact acquired definition, even when
                # policy has since changed. It grants no new execution authority.
                definition = None
            ev.validate_graph(graph)
            snapshot = {'envelope': envelope, 'payload': payload, 'graph': graph, 'resolve': resolve,
                        'historical_graph': historical_graph, 'workflow_definition': definition}
            if (definition is not None and payload['evidence'] and stored_workflow_graph is not None
                    and definition['graph'] != stored_workflow_graph):
                recorded_old_graph = remember(stored_workflow_graph)
                for receipt_row in reversed(payload['operational']['receipts']):
                    try:
                        prior_response = resolve(receipt_row['result'])
                        prior_step = next(item for item in prior_response.get('next_steps', [])
                                          if item.get('kind') == 'policy_dag_cutover_applied')
                        prior_receipt = resolve(prior_step['receipt'])['content']
                        if prior_receipt.get('new_graph') == recorded_old_graph:
                            recorded_old_graph = prior_receipt['new_policy_graph']
                            break
                    except (KeyError, StopIteration, TypeError, ValueError):
                        continue
                snapshot['policy_dag_cutover'] = {
                    'old_graph': recorded_old_graph,
                    'old_execution_graph': remember(stored_workflow_graph),
                    'new_graph': remember(definition['graph']),
                    'new_policy_graph': remember(policy_section(
                        self.project, 'workflow_adherence')['configuration']['phase_dag']),
                    'old_policy_revision': digest(stored_workflow_graph),
                    'new_policy_revision': digest(self.project['policy']),
                }
                # Keep pre-cutover currentness and ownership anchored to the
                # authenticated old graph. The reviewed new graph may rename
                # nodes that historical Results cannot resolve yet.
                graph = stored_workflow_graph
                snapshot['graph'] = graph
            journal = payload.get('phase_data', {'version': 1, 'events': []})
            if (not isinstance(journal, dict) or set(journal) != {'version', 'events'}
                    or journal['version'] != 1 or not isinstance(journal['events'], list)):
                raise ValueError('Unsupported phase data version or malformed event journal')
            events = []
            for reference in journal['events']:
                event = resolve(reference)
                provenance = event.get('provenance', {})
                if (event.get('type') != 'phase_event' or provenance.get('repository') != self.repository
                        or provenance.get('goal') != n or not provenance.get('actor')
                        or not provenance.get('request_id')):
                    raise ValueError('Phase event provenance does not match this goal')
                event_request = {key: event['content'][key] for key in
                                 ('id', 'target', 'subject', 'source', 'rationale')}
                event_request.update(operation='phase_finding', request_id=provenance['request_id'],
                                     actor=provenance['actor'])
                receipts = [row for row in payload['operational']['receipts']
                            if row['request'] == provenance['request_id'] and row['payload'] == digest(event_request)]
                if len(receipts) != 1:
                    raise ValueError('Phase event lacks its exact committed intake receipt')
                receipt_steps = resolve(receipts[0]['result']).get('next_steps', [])
                if not receipt_steps or receipt_steps[0] != {'kind': 'phase_data_recorded', 'goal': n,
                        'event': reference, 'revision': event['content']['revision']}:
                    raise ValueError('Phase event receipt does not authenticate the exact event revision')
                events.append(event['content'])
            snapshot['phase_data'] = self.api._static_workflow.phase_data(events, graph, n)
            lineage = {'number': n, 'payload': payload}
            if source_artifact.get('type') != 'migration_source':
                self.node_committed_legacy_requests(lineage, migration_context_only=True)
            recovered = lineage.get('historical_goal_context')
            if 'goal_context' in payload:
                metadata = resolve(payload['goal_context'])
                direct_provenance = metadata.get('provenance')
                direct = False
                if (isinstance(direct_provenance, dict)
                        and direct_provenance.get('actor') == 'direct-v2-capture/1'
                        and direct_provenance.get('source') is None
                        and direct_provenance == source_artifact.get('provenance')
                        and isinstance(direct_provenance.get('policy'), dict)):
                    try:
                        policy_ref = direct_provenance['policy']
                        self.api._phase_evidence.validate_ref(policy_ref)
                        original_policy = resolve(policy_ref)
                        direct = digest(original_policy) == policy_ref['hash']
                    except (KeyError, ValueError):
                        direct = False
                if (metadata.get('type') != 'goal_context' or metadata.get('producer') is not None
                        or metadata.get('content', {}).get('version') != 1
                        or not (direct or (recovered is not None
                            and metadata['content'] == recovered
                            and metadata.get('provenance') in lineage.get('goal_context_provenances', [])))):
                    raise ValueError('Goal context lacks its exact authenticated migration source/policy lineage')
                snapshot['goal_context'] = metadata['content']
                snapshot['goal_context_ref'] = copy.deepcopy(payload['goal_context'])
                snapshot['goal_context_provenance'] = copy.deepcopy(metadata['provenance'])
            elif recovered is not None:
                snapshot['goal_context'] = copy.deepcopy(recovered)
                snapshot['goal_context_provenance'] = lineage['goal_context_provenances'][-1]
                context_artifact = {'type': 'goal_context', 'content': copy.deepcopy(snapshot['goal_context']),
                    'producer': None, 'provenance': snapshot['goal_context_provenance']}
                snapshot['goal_context_ref'] = remember(context_artifact)
            elif (source_artifact.get('provenance', {}).get('actor') in
                    ('lossless-v1-v2/1', self.api._migration_batch.LEGACY_COMPILED_CONVERTER)
                    or any(row['id'] == 'legacy_blockers'
                           or any(name.startswith('legacy_dependency_') for name in row['inputs'])
                           or 'Preserved engineering requirement:' in row['prompt']
                           for row in historical_graph['nodes'])):
                raise ValueError('Historical goal constraints require the exact committed migration lineage; restore missing history')
            if 'goal_context' in snapshot:
                snapshot['original_goal_context'] = copy.deepcopy(snapshot['goal_context'])
                resolution_journal = payload.get('goal_context_resolutions', {'version': 1, 'events': []})
                if (not isinstance(resolution_journal, dict)
                        or set(resolution_journal) != {'version', 'events'}
                        or resolution_journal.get('version') != 1
                        or not isinstance(resolution_journal.get('events'), list)):
                    raise GoalContextResolutionAuthenticationError(
                        'Unsupported or malformed goal-context resolution journal')
                resolved, seen = [], set()
                for reference in resolution_journal['events']:
                    try:
                        ev.validate_ref(reference)
                        foreign = self.node_ref_goal(reference, n) != n
                    except (ValueError, KeyError) as exc:
                        raise GoalContextResolutionAuthenticationError(
                            'Goal-context resolution event reference is malformed or foreign') from exc
                    if foreign or reference['hash'] in seen:
                        raise GoalContextResolutionAuthenticationError(
                            'Goal-context resolution journal contains a foreign or duplicate event')
                    seen.add(reference['hash'])
                    try:
                        event = resolve(reference)
                    except (ValueError, KeyError) as exc:
                        raise GoalContextResolutionAuthenticationError(
                            'Goal-context resolution artifact checksum or content is unavailable') from exc
                    provenance = event.get('provenance', {}) if isinstance(event, dict) else {}
                    content = event.get('content', {}) if isinstance(event, dict) else {}
                    required_content = {'context_hash', 'blocker_hash', 'rationale', 'resolution_basis', 'evidence'}
                    if content.get('human_approval') is not None:
                        required_content.add('human_approval')
                    if (event.get('type') != 'goal_blocker_resolution' or event.get('producer') is not None
                            or set(content) != required_content
                            or set(provenance) != {'actor', 'repository', 'goal', 'request_id'}
                            or provenance.get('repository') != self.repository or provenance.get('goal') != n
                            or not isinstance(provenance.get('actor'), str) or not provenance['actor']
                            or not isinstance(provenance.get('request_id'), str) or not provenance['request_id']
                            or content.get('context_hash') != snapshot['goal_context_ref']['hash']
                            or not isinstance(content.get('rationale'), str) or not content['rationale'].strip()
                            or not isinstance(content.get('resolution_basis'), str) or not content['resolution_basis'].strip()
                            or not isinstance(content.get('evidence'), list) or not content['evidence']):
                        raise GoalContextResolutionAuthenticationError(
                            'Goal-context resolution artifact or provenance is malformed')
                    matches = [row for row in snapshot['original_goal_context']['blockers']
                               if digest(row) == content.get('blocker_hash')]
                    if len(matches) != 1:
                        raise GoalContextResolutionAuthenticationError(
                            'Goal-context resolution identifies an unknown or ambiguous blocker')
                    human = matches[0].get('category') == 'human-action'
                    approval = content.get('human_approval')
                    if human and (not isinstance(approval, dict) or set(approval) != {'approved_by', 'attribution'}
                                  or not all(isinstance(approval.get(key), str) and approval[key].strip()
                                             for key in ('approved_by', 'attribution'))):
                        raise GoalContextResolutionAuthenticationError(
                            'Human-action blocker resolution lacks explicit approval attribution')
                    if not human and approval is not None:
                        raise GoalContextResolutionAuthenticationError(
                            'Nonhuman blocker resolution contains fabricated human approval')
                    for evidence in content['evidence']:
                        try:
                            ev.validate_ref(evidence)
                            if evidence['uri'].startswith('git:') or self.node_ref_goal(evidence, n) != n:
                                raise ValueError('foreign evidence')
                            resolve(evidence)
                        except (ValueError, KeyError) as exc:
                            raise GoalContextResolutionAuthenticationError(
                                'Goal-context resolution evidence is missing, forged, or foreign') from exc
                    request = {'operation': 'resolve_goal_blocker', 'request_id': provenance['request_id'],
                               'actor': provenance['actor'], **copy.deepcopy(content)}
                    receipts = [row for row in payload['operational']['receipts']
                                if row['request'] == provenance['request_id'] and row['payload'] == digest(request)]
                    expected = {'next_steps': [{'kind': 'goal_blocker_resolved', 'goal': n,
                                                'resolution': reference}]}
                    try:
                        receipt_response = resolve(receipts[0]['result']) if len(receipts) == 1 else None
                    except (ValueError, KeyError) as exc:
                        raise GoalContextResolutionAuthenticationError(
                            'Goal-context resolution committed receipt response is missing or forged') from exc
                    if receipt_response != expected:
                        raise GoalContextResolutionAuthenticationError(
                            'Goal-context resolution lacks its exact committed receipt')
                    resolved.append(content['blocker_hash'])
                snapshot['goal_context_resolution_events'] = copy.deepcopy(resolution_journal['events'])
                snapshot['goal_context'] = self.api._static_workflow.resolved_goal_context(
                    snapshot['original_goal_context'], resolved)
                dependency_journal = payload.get('goal_context_dependency_events',
                                                 {'version': 1, 'events': []})
                if (not isinstance(dependency_journal, dict)
                        or set(dependency_journal) != {'version', 'events'}
                        or dependency_journal.get('version') != 1
                        or not isinstance(dependency_journal.get('events'), list)):
                    raise GoalContextResolutionAuthenticationError(
                        'Unsupported or malformed goal dependency journal')
                seen_dependencies = set()
                for reference in dependency_journal['events']:
                    try:
                        ev.validate_ref(reference)
                        if (self.node_ref_goal(reference, n) != n
                                or reference['hash'] in seen_dependencies):
                            raise ValueError('foreign or duplicate event')
                        seen_dependencies.add(reference['hash'])
                        event = resolve(reference)
                        content = event['content']
                        provenance = event['provenance']
                        proposal_ref, review_ref = content['proposal'], content['review']
                        for item in (proposal_ref, review_ref):
                            ev.validate_ref(item)
                            if self.node_ref_goal(item, n) != n:
                                raise ValueError('foreign proposal or review')
                        proposal, review = resolve(proposal_ref), resolve(review_ref)
                        proposal_content = proposal.get('content', {})
                        proposal_provenance = proposal.get('provenance', {})
                        review_content = review.get('content', {})
                        review_provenance = review.get('provenance', {})
                        expected = self.api._static_workflow.changed_goal_dependencies(
                            snapshot['goal_context'], [{'old': content['old'],
                                                        'replacement': content['replacement']}])
                        approval = content['human_approval']
                        if (set(event) != {'type', 'content', 'producer', 'provenance'}
                                or event['type'] != 'goal_dependency_change'
                                or event['producer'] is not None
                                or set(content) != {'context', 'old', 'replacement', 'before', 'after',
                                                    'proposal', 'review', 'human_approval'}
                                or set(provenance) != {'actor', 'repository', 'goal', 'request_id'}
                                or provenance['repository'] != self.repository or provenance['goal'] != n
                                or not isinstance(provenance['actor'], str) or not provenance['actor']
                                or not isinstance(provenance['request_id'], str) or not provenance['request_id']
                                or content['context'] != snapshot['goal_context_ref']
                                or content['before'] != snapshot['goal_context']['depends_on']
                                or content['after'] != expected['depends_on']
                                or not isinstance(approval, dict)
                                or set(approval) != {'approved_by', 'attribution'}
                                or not all(isinstance(approval[key], str) and approval[key].strip()
                                           for key in approval)
                                or proposal.get('type') != 'goal_dependency_proposal'
                                or proposal_content.get('context') != content['context']
                                or proposal_content.get('before') != content['before']
                                or proposal_content.get('after') != content['after']
                                or proposal_content.get('old') != content['old']
                                or proposal_content.get('replacement') != content['replacement']
                                or proposal_content.get('repository') != self.repository
                                or proposal_content.get('goal') != n
                                or proposal_provenance.get('actor') != provenance['actor']
                                or proposal_provenance.get('source') != content['context']
                                or proposal_provenance.get('policy') != proposal_content.get('policy')
                                or review.get('type') != 'goal_dependency_review'
                                or not explicit_approval(review_provenance.get('actor'))
                                or review_provenance['actor'] == provenance['actor']
                                or review_provenance.get('source') != proposal_ref
                                or review_provenance.get('policy') != proposal_content.get('policy')
                                or not isinstance(review_provenance.get('request_id'), str)
                                or review_content.get('decision') != 'approved'
                                or not isinstance(review_content.get('report'), str)
                                or not review_content['report'].strip()):
                            raise ValueError('dependency event, proposal, review or approval is malformed')
                        if (not isinstance(proposal_content['policy'], str)
                                or re.fullmatch(r'sha256:[0-9a-f]{64}',
                                                proposal_content['policy']) is None):
                            raise ValueError('dependency review policy identity is malformed')
                        review_request = {'operation': 'goal_dependency_review',
                            'request_id': review_provenance['request_id'],
                            'actor': review_provenance['actor'], 'proposal': proposal_content,
                            'decision': 'approved', 'report': review_content['report']}
                        review_receipts = [row for row in payload['operational']['receipts']
                                           if row['request'] == review_request['request_id']
                                           and row['payload'] == digest(review_request)]
                        request = {'operation': 'goal_dependency_apply',
                            'request_id': provenance['request_id'], 'actor': provenance['actor'],
                            'proposal': proposal_ref, 'review': review_ref,
                            'human_approval': approval}
                        receipts = [row for row in payload['operational']['receipts']
                                    if row['request'] == provenance['request_id']
                                    and row['payload'] == digest(request)]
                        response = {'next_steps': [{'kind': 'goal_dependency_changed',
                            'goal': n, 'event': reference, 'before': content['before'],
                            'after': content['after']}]}
                        index = self.artifact_index(n)
                        review_edge = (self.node_receipt_edge(n, index, review_receipts[0])
                                       if len(review_receipts) == 1 else None)
                        apply_edge = (self.node_receipt_edge(n, index, receipts[0])
                                      if len(receipts) == 1 else None)
                        if (review_edge is None or apply_edge is None
                                or review_edge['source'] != proposal_content.get('source', {}).get('envelope')
                                or apply_edge['source'] != review_edge['target']
                                or review_edge['response'].get('next_steps', [{}])[0].get('review') != review_ref
                                or apply_edge['response'] != response):
                            raise ValueError('dependency event lacks exact committed receipt')
                        snapshot['goal_context'] = expected
                    except (KeyError, TypeError, ValueError) as exc:
                        raise GoalContextResolutionAuthenticationError(
                            'Goal dependency journal authentication failed: ' + str(exc)) from exc
                snapshot['goal_context_dependency_events'] = copy.deepcopy(dependency_journal['events'])
                archived_journal = payload.get('goal_context_archived_prerequisites',
                                               {'version': 1, 'events': []})
                if (not isinstance(archived_journal, dict)
                        or set(archived_journal) != {'version', 'events'}
                        or archived_journal.get('version') != 1
                        or not isinstance(archived_journal.get('events'), list)):
                    raise GoalContextResolutionAuthenticationError(
                        'Unsupported archived prerequisite journal')
                archived = {}
                seen_archived = set()
                for reference in archived_journal['events']:
                    try:
                        ev.validate_ref(reference)
                        if (self.node_ref_goal(reference, n) != n
                                or reference['hash'] in seen_archived):
                            raise ValueError('foreign or duplicate archived event')
                        seen_archived.add(reference['hash'])
                        event = resolve(reference)
                        content = event['content']
                        provenance = event['provenance']
                        proposal_ref, review_ref = content['proposal'], content['review']
                        for item in (proposal_ref, review_ref):
                            ev.validate_ref(item)
                            if self.node_ref_goal(item, n) != n:
                                raise ValueError('foreign proposal or review')
                        proposal_artifact, review_artifact = resolve(proposal_ref), resolve(review_ref)
                        proposal = proposal_artifact['content']
                        review = review_artifact['content']
                        review_provenance = review_artifact['provenance']
                        approval = content['human_approval']
                        prerequisite = content['prerequisite']
                        if (set(event) != {'type', 'content', 'producer', 'provenance'}
                                or event['type'] != 'archived_prerequisite_resolution'
                                or event['producer'] is not None
                                or set(content) != {'context_hash', 'blocker_hash', 'prerequisite',
                                                    'candidate', 'proposal', 'review', 'human_approval'}
                                or set(provenance) != {'actor', 'repository', 'goal', 'request_id'}
                                or provenance['repository'] != self.repository
                                or provenance['goal'] != n
                                or not explicit_approval(provenance['actor'])
                                or not isinstance(provenance['request_id'], str)
                                or not provenance['request_id']
                                or type(prerequisite) is not int
                                or content['context_hash'] != snapshot['goal_context_ref']['hash']
                                or not isinstance(approval, dict)
                                or set(approval) != {'approved_by', 'attribution'}
                                or not all(explicit_approval(approval[key]) for key in approval)
                                or proposal_artifact.get('type') != 'archived_prerequisite_proposal'
                                or proposal_artifact.get('producer') is not None
                                or proposal_artifact.get('provenance', {}).get('actor') != provenance['actor']
                                or not self.node_same_local_ref(
                                    proposal_artifact.get('provenance', {}).get('source'),
                                    snapshot['goal_context_ref'], n, resolve)
                                or review_artifact.get('type') != 'archived_prerequisite_review'
                                or review_artifact.get('producer') is not None
                                or review_provenance.get('source') != proposal_ref
                                or not explicit_approval(review_provenance.get('actor'))
                                or review_provenance['actor'] == provenance['actor']
                                or review.get('decision') != 'approved'
                                or not isinstance(review.get('report'), str)
                                or not review['report'].strip()
                                or not isinstance(review.get('adoption'), dict)
                                or set(review['adoption']) != {'manual_request',
                                    'terminal_equivalence', 'retained_obligations'}
                                or review['adoption']['manual_request'] != 'opaque'
                                or not all(isinstance(review['adoption'].get(key), str)
                                    and review['adoption'][key].strip() for key in
                                    ('terminal_equivalence', 'retained_obligations'))
                                or proposal.get('manual_request') !=
                                    'opaque_requires_reviewed_adoption'):
                            raise ValueError('archived event, proposal, review or approval is malformed')
                        prepared = {'operation': 'goal_external_blocker_prepare',
                            'request_id': provenance['request_id'],
                            'context_hash': content['context_hash'],
                            'blocker_hash': content['blocker_hash'],
                            'prerequisite': prerequisite,
                            'pull_number': proposal['pull_number']}
                        expected_proposal = self.node_external_blocker_proposal(
                            {'number': n, 'envelope': envelope, **snapshot}, prepared,
                            historical_edge=True)
                        expected_proposal['source_envelope'] = proposal['source_envelope']
                        expected_proposal['policy'] = proposal['policy']
                        if (proposal != expected_proposal
                                or proposal['candidate'] != content['candidate']
                                or proposal_artifact['provenance'].get('policy') != proposal['policy']
                                or review_provenance.get('policy') != proposal['policy']):
                            raise ValueError('archived prerequisite evidence changed')
                        review_request = {'operation': 'goal_external_blocker_review',
                            'request_id': review_provenance['request_id'],
                            'actor': review_provenance['actor'], 'proposal': proposal,
                            'decision': 'approved', 'report': review['report'],
                            'adoption': review['adoption']}
                        apply_request = {'operation': 'goal_external_blocker_apply',
                            'request_id': provenance['request_id'], 'actor': provenance['actor'],
                            'proposal': proposal_ref, 'review': review_ref,
                            'human_approval': approval}
                        review_receipts = [row for row in payload['operational']['receipts']
                            if row['request'] == review_request['request_id']
                            and row['payload'] == digest(review_request)]
                        apply_receipts = [row for row in payload['operational']['receipts']
                            if row['request'] == apply_request['request_id']
                            and row['payload'] == digest(apply_request)]
                        index = self.artifact_index(n)
                        review_edge = (self.node_receipt_edge(n, index, review_receipts[0])
                                       if len(review_receipts) == 1 else None)
                        apply_edge = (self.node_receipt_edge(n, index, apply_receipts[0])
                                      if len(apply_receipts) == 1 else None)
                        response = {'next_steps': [{'kind': 'archived_prerequisite_applied',
                            'goal': n, 'prerequisite': prerequisite, 'resolution': reference}]}
                        if (review_edge is None or apply_edge is None
                                or review_edge['source'] != proposal['source_envelope']
                                or apply_edge['source'] != review_edge['target']
                                or review_edge['response'].get('next_steps', [{}])[0].get('review') != review_ref
                                or apply_edge['response'] != response):
                            raise ValueError('archived event lacks exact committed receipt')
                        snapshot['goal_context'] = self.api._static_workflow.resolved_goal_context(
                            snapshot['goal_context'], [content['blocker_hash']])
                        archived.setdefault(prerequisite, reference)
                    except (KeyError, TypeError, ValueError) as exc:
                        raise GoalContextResolutionAuthenticationError(
                            'Archived prerequisite journal authentication failed: ' + str(exc)) from exc
                snapshot['archived_prerequisites'] = archived
                if n == number and dependency_override is not None:
                    snapshot['goal_context'] = copy.deepcopy(dependency_override)
            elif 'goal_context_dependency_events' in payload:
                raise GoalContextResolutionAuthenticationError(
                    'Goal dependency journal has no authenticated context')
            elif 'goal_context_archived_prerequisites' in payload:
                raise GoalContextResolutionAuthenticationError(
                    'Archived prerequisite journal has no authenticated context')
            retired_nodes = {row['id']: row for row in historical_graph['nodes']} \
                .keys() - {row['id'] for row in graph['nodes']}
            # Compiler-generated routes are historical evidence, not additional
            # product requirements. Unknown custom phases remain explicit debt.
            mapped_context_nodes = {'legacy_blockers'} if snapshot.get('goal_context') else set()
            mapped_cutover_nodes = set()
            for receipt_row in reversed(payload['operational']['receipts']):
                try:
                    response = resolve(receipt_row['result'])
                    applied = next(item for item in response.get('next_steps', [])
                                   if item.get('kind') == 'policy_dag_cutover_applied')
                    cutover_receipt = resolve(applied['receipt'])['content']
                    mapped_cutover_nodes = {item['old']['node'] for item in cutover_receipt['mapping']}
                    break
                except (KeyError, StopIteration, TypeError, ValueError):
                    continue
            evidenced_nodes = {resolve(reference)['content']['node']['node']
                               for reference in payload['evidence']}
            unmapped = sorted(name for name in retired_nodes
                             if (not name.startswith(('gc_', 'sw_'))
                                 and name not in mapped_context_nodes
                                 and name not in mapped_cutover_nodes
                                 and name in evidenced_nodes))
            if unmapped:
                snapshot['workflow_migration_blocker'] = 'Unmapped historical phase contracts require policy/data mapping: ' + ', '.join(unmapped)
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
            # Metadata locates operational drafts, but only a committed receipt
            # can activate one. Historical source payloads never activate drafts.
            draft_responses = {}
            for record in self.artifact_index(n).envelopes:
                context = record.get('context') or {}
                reference = context.get('response', {})
                if not context.get('workspace_draft') or reference.get('hash') not in receipt_refs: continue
                if reference['hash'] in draft_responses: continue
                receipt = next(row for row in payload['operational']['receipts'] if row['result'] == reference)
                if receipt['request'] != context.get('request_id') or receipt['payload'] != context.get('request_hash'):
                    raise ValueError('Workspace draft recovery receipt provenance differs')
                try: response = resolve(reference)
                except (ValueError, KeyError) as exc: raise ValueError('Workspace draft receipt artifact is corrupt: ' + str(exc)) from exc
                draft_ref = response['next_steps'][0].get('workspace_draft')
                if draft_ref != context['workspace_draft']: raise ValueError('Workspace draft receipt identity differs')
                draft = resolve(draft_ref)
                source = resolve(draft['source_payload'])
                lease = next((row for row in source['operational']['leases'] if row['token'] == draft['lease']['token']), None)
                source_acquisition = draft.get('source_acquisition', draft.get('acquisition'))
                historical = draft.get('historical_recovery')
                historical_context = None
                if historical is not None:
                    if not isinstance(historical, dict) or set(historical) != {'request', 'response'}:
                        raise ValueError('Historical workspace draft recovery provenance is malformed')
                    matches = [row.get('context') or {} for row in self.artifact_index(n).envelopes
                               if (row.get('context') or {}).get('response') == historical.get('response')]
                    matches = [row for row in matches
                               if row.get('request_id') == historical['request'].get('request_id')
                               and row.get('request_hash') == digest(historical['request'])
                               and row.get('source_envelope', {}).get('payload') == draft['source_payload']]
                    if len(matches) != 1:
                        raise ValueError('Historical workspace draft recovery transaction is missing or ambiguous')
                    historical_context = matches[0]
                    recovery = resolve(historical['response'])
                    if (historical['response']['hash'] not in receipt_refs or
                            recovery.get('next_steps') != [{'kind': 'checkpoint', 'goal': n}] or
                            historical['request'].get('operation') != 'recover' or
                            historical['request'].get('node') != draft.get('node') or
                            historical['request'].get('lease') != draft.get('lease', {}).get('token') or
                            historical['request'].get('actor') != draft.get('lease', {}).get('worker') or
                            historical['request'].get('worker_status') != 'stopped' or
                            not isinstance(historical['request'].get('evidence'), str) or
                            not historical['request']['evidence'].strip()):
                        raise ValueError('Historical workspace draft lacks an exact committed stopped-owner recovery')
                if (draft.get('type') != 'workspace_draft' or not lease or
                    any(lease.get(k) != v for k, v in draft['lease'].items()) or
                    lease['node'] != draft['node'] or lease['acquisition'] != source_acquisition or
                    (historical is None and lease['fingerprint'] != draft['input_hash']) or
                    digest(draft['acquisition']) != draft['acquisition_hash'] or
                    draft['contract'] != draft['acquisition']['contract'] or
                    (historical is None and context.get('root') != lease['owner']) or
                    (historical is not None and historical_context.get('root') != lease['owner']) or
                    (historical is None and context.get('source_envelope', {}).get('payload') != draft['source_payload'])):
                    raise ValueError('Workspace draft source lease/acquisition provenance differs')
                acquisition_ref = draft['acquisition_receipt']
                if not any(row['result'] == acquisition_ref for row in source['operational']['receipts']):
                    raise ValueError('Workspace draft acquisition receipt is not committed')
                started = resolve(acquisition_ref)
                pins = [step['lease'] for step in started.get('next_steps', [])
                        if step.get('bind') and step.get('lease', {}).get('token') == lease['token']]
                if (len(pins) != 1 or pins[0]['acquisition'] != source_acquisition or
                    any(pins[0][k] != lease[k] for k in ('node', 'attempt', 'owner', 'fingerprint'))):
                    raise ValueError('Workspace draft differs from immutable acquisition receipt')
                if historical is not None:
                    raw_fields = {'git_commit', 'workspace_digest', 'checkout_overrides', 'files'}
                    if (draft['acquisition'].get('recovered_from') != historical['response'] or
                            any(draft['acquisition'].get(name) != source_acquisition.get(name) for name in raw_fields)):
                        raise ValueError('Historical workspace draft changed its original raw acquisition')
                draft_responses[reference['hash']] = (draft_ref, draft)
            snapshot['workspace_drafts'] = [draft_responses[row['result']['hash']]
                for row in payload['operational']['receipts'] if row['result']['hash'] in draft_responses]
            # Retirement changes operational selection only. Its exact committed
            # transaction remains reachable alongside every original draft.
            snapshot['retired_workspace_drafts'] = set()
            known_drafts = {ref['hash']: (ref, draft) for ref, draft in snapshot['workspace_drafts']}
            retired_responses = set()
            for record in self.artifact_index(n).envelopes:
                context = record.get('context') or {}; reference = context.get('response', {})
                if (not context.get('workspace_draft_retirement') or reference.get('hash') not in receipt_refs
                        or reference['hash'] in retired_responses): continue
                retired_responses.add(reference['hash'])
                receipt = next(row for row in payload['operational']['receipts'] if row['result'] == reference)
                response = resolve(reference)
                edge = self.node_receipt_edge(n, self.artifact_index(n), receipt)
                fields = {'type', 'version', 'node', 'draft', 'source_payload', 'recovery_request',
                          'subject', 'root', 'next_steps'}
                if (not edge or set(response) != fields or response.get('type') != 'workspace_draft_retirement'
                        or context.get('workspace_draft_retirement') != response.get('draft')
                        or type(response.get('version')) is not int
                        or response['version'] != 1 or not isinstance(response.get('draft'), dict)
                        or response['draft'].get('hash') not in known_drafts
                        or not isinstance(response.get('recovery_request'), dict)
                        or not isinstance(response.get('subject'), str)
                        or not re.fullmatch(r'sha256:[0-9a-f]{64}', response['subject'])
                        or not isinstance(response.get('root'), str) or not response['root']
                        or response['source_payload'] != edge['source']['payload']
                        or response['root'] != edge['context']['root']):
                    raise ValueError('Workspace draft retirement lacks an exact committed transaction')
                reference, draft = known_drafts[response['draft']['hash']]
                source_payload = resolve(response['source_payload'])
                original_request = {'operation': 'retire_stale_draft', 'request_id': receipt['request'],
                                    'node': response['node'], 'draft': reference,
                                    'subject': response['subject'], 'recovery_request': response['recovery_request']}
                if (reference != response['draft'] or draft['node'] != response['node']
                        or receipt['payload'] != digest(original_request)
                        or source_payload['operational']['leases']
                        or response['recovery_request'].get('operation') != 'recover'
                        or not isinstance(response['recovery_request'].get('evidence'), str)
                        or not response['recovery_request']['evidence'].strip()
                        or response['recovery_request'].get('worker_status') != 'stopped'
                        or response['recovery_request'].get('node') != draft['node']
                        or response['recovery_request'].get('lease') != draft['lease']['token']
                        or response['recovery_request'].get('actor') != draft['lease']['worker']):
                    raise ValueError('Workspace draft retirement changed stopped owner identity')
                recovery = [row for row in source_payload['operational']['receipts']
                            if row['request'] == response['recovery_request'].get('request_id')
                            and row['payload'] == digest(response['recovery_request'])]
                steps = response.get('next_steps')
                recovered = resolve(recovery[0]['result']).get('next_steps') if len(recovery) == 1 else None
                if (not isinstance(steps, list) or len(steps) != 1 or not isinstance(steps[0], dict)
                        or set(steps[0]) != {'kind', 'goal', 'action'} or steps[0]['kind'] != 'checkpoint'
                        or type(steps[0]['goal']) is not int or steps[0]['goal'] != n
                        or not isinstance(steps[0]['action'], str) or not steps[0]['action'].strip()
                        or not isinstance(recovered, list) or len(recovered) != 1
                        or not isinstance(recovered[0], dict) or recovered[0].get('workspace_draft') != reference
                        or recovered[0].get('kind') != 'checkpoint' or recovered[0].get('goal') != n):
                    raise ValueError('Workspace draft retirement lacks original observed-stop receipt')
                snapshot['retired_workspace_drafts'].update(self.node_workspace_draft_chain(reference, known_drafts))
            pending = [(ref, n) for ref in [payload['spec'], *payload['evidence'], *journal['events'], *acquisition_receipts.values(), *(ref for ref, _ in snapshot['workspace_drafts'])]]
            visited = set()
            def references(value):
                if isinstance(value, dict):
                    if value.get('schema_version') == 2 and 'payload' in value and 'repository' in value: return
                    if set(value) == {'hash', 'uri'} and isinstance(value['hash'], str):
                        if isinstance(value['uri'], str) and value['uri'].startswith(('urn:', 'zzzops:', 'git:')): yield value
                    else:
                        for name, child in value.items():
                            if value.get('type') == 'workspace_draft' and name == 'source_payload': continue
                            yield from references(child)
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
                'provenance': {'actor': 'host', 'source': None, 'policy': self.node_evidence_policy()}})
            related = {ref['goal'] for ref in refs if type(ref['goal']) is int}
            related.update(target for target in snapshot.get('goal_context', {}).get('depends_on', [])
                           if target not in snapshot.get('archived_prerequisites', {}))
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
                    'provenance': {'actor': 'host', 'source': None, 'policy': self.node_evidence_policy()}})
        # Some scoped discovery candidates were needed only for parent coverage.
        # They are not evaluated unless referenced by the selected graph closure.
        closure = {n: snapshots[n] for n in visited}
        context = {'goal': number, 'policy': self.project['policy'], 'runtime': self.runtime, 'artifacts': artifacts, 'goals': closure, 'published_bytes': published}
        snapshot = {'number': number, 'issue': issues[number], **selected, 'snapshots': snapshots, 'issues': issues,
                    'bootstrap': bootstrap, 'artifacts': artifacts, 'published': published, 'evaluation_context': context}
        return self.node_project(snapshot, publication_probe=publication_probe,
                                 workspace_target=workspace_target)

    def node_project(self, snapshot, *, payload=None, publication_probe=False,
                     workspace_target=None):
        """Evaluate observed context with either durable or prospective evidence."""
        ev = self.api._phase_evidence
        context = {**snapshot['evaluation_context'], 'artifacts': snapshot['artifacts'], 'workspace_probe': True}
        closure = {n: dict(value) for n, value in context['goals'].items()}
        if payload is not None:
            closure[snapshot['number']]['payload'] = payload
            events = [snapshot['artifacts'][ref['hash']]['content']
                      for ref in payload.get('phase_data', {}).get('events', [])]
            closure[snapshot['number']]['phase_data'] = self.api._static_workflow.phase_data(
                events, closure[snapshot['number']]['graph'], snapshot['number'])
        selected = closure[snapshot['number']]
        context['goals'] = closure
        refresh = selected['payload'].get('stack_integration', {}).get('root_refresh', {})
        if refresh.get('root') == (self.runtime or {}).get('root_id'):
            observed_goals = set(refresh.get('observed_goals', []))
            evaluation_payload = copy.deepcopy(selected['payload'])
            retained = []
            for reference in evaluation_payload['evidence']:
                artifact = snapshot['artifacts'].get(reference['hash'], {})
                result_value = artifact.get('content', {}) if artifact.get('type') == 'result' else {}
                outputs = [snapshot['artifacts'].get(ref.get('hash'), {})
                           for ref in result_value.get('outputs', {}).values()]
                stale_publication_root = (result_value.get('node', {}).get('goal') not in observed_goals
                    and result_value.get('executor') != refresh.get('root')
                    and any(value.get('type') == 'publication_authorization' for value in outputs))
                if not stale_publication_root: retained.append(reference)
            evaluation_payload['evidence'] = retained
            selected = {**selected, 'payload': evaluation_payload}
            closure[snapshot['number']] = selected
            context['goals'] = closure
        cutover_results = set()
        cutover_outputs = set()
        for row in reversed(selected['payload']['operational']['receipts']):
            try:
                response = snapshot['artifacts'].get(row['result']['hash']) or snapshot['resolve'](row['result'])
                step = next(item for item in response.get('next_steps', [])
                            if item.get('kind') == 'policy_dag_cutover_applied')
                receipt = snapshot['artifacts'].get(step['receipt']['hash']) or snapshot['resolve'](step['receipt'])
                for item in receipt['content']['mapping']:
                    cutover_results.add(item['result']['hash'])
                    result_artifact = snapshot['artifacts'].get(item['result']['hash']) or snapshot['resolve'](item['result'])
                    cutover_outputs.update(ref['hash'] for ref in result_artifact['content']['outputs'].values())
                break
            except (KeyError, StopIteration, TypeError, ValueError):
                continue
        context['cutover_results'] = cutover_results
        context['cutover_outputs'] = cutover_outputs
        context['cutover_mappings'] = {}
        context['cutover_node_aliases'] = {}
        for row in reversed(selected['payload']['operational']['receipts']):
            try:
                response = snapshot['artifacts'].get(row['result']['hash']) or snapshot['resolve'](row['result'])
                step = next(item for item in response.get('next_steps', [])
                            if item.get('kind') == 'policy_dag_cutover_applied')
                receipt = snapshot['artifacts'].get(step['receipt']['hash']) or snapshot['resolve'](step['receipt'])
                context['cutover_mappings'] = {
                    item['result']['hash']: item['new']['node'] for item in receipt['content']['mapping']}
                context['cutover_node_aliases'] = {
                    item['old']['node']: item['new']['node'] for item in receipt['content']['mapping']}
                break
            except (KeyError, StopIteration, TypeError, ValueError):
                continue
        historical, historical_error = self.node_historical_policies(closure, snapshot['artifacts'])
        context['historical_policies'] = historical
        context['historical_policy_error'] = historical_error
        result = ev.derive_task_steps(selected['graph'], selected['payload'], context)
        workspaces = self.node_workspace_context(
            closure, result, result['artifacts'], workspace_target=workspace_target)
        publications = {} if publication_probe else self.node_publication_context(closure, result, result['artifacts'])
        context.update(workspace_probe=False, workspaces=workspaces, artifacts=result['artifacts'])
        if not publication_probe: context['publications'] = publications
        result = ev.derive_task_steps(selected['graph'], selected['payload'], context)
        for state in result['states'].values():
            state['goal_context'] = closure.get(state['node']['goal'], {}).get('goal_context', {})
        return {**snapshot, 'payload': selected['payload'], 'projection': result, 'artifacts': result['artifacts'],
                'workspaces': workspaces, 'publications': publications}

    def node_committed_legacy_requests(self, snapshot, *, migration_context_only=False):
        """Read completed v1 requests only through a committed automatic migration."""
        number = snapshot['number']
        index = self.artifact_index(number)
        completed = {}

        def require(condition, reason):
            if not condition: raise ValueError('Legacy migration proof: ' + reason)

        def read(reference):
            self.api._phase_evidence.validate_ref(reference)
            require(reference == self.node_ref(reference['hash'], number),
                    'immutable reference must bind this repository and goal')
            value = self.read_artifact(number, reference)
            require(isinstance(value, dict), 'migration lineage artifact must be an object')
            return value

        migration_responses = {(row.get('context') or {}).get('response', {}).get('hash')
                               for row in index.envelopes if (row.get('context') or {}).get('migration')}
        for committed in snapshot['payload']['operational']['receipts']:
            if migration_context_only and committed['result']['hash'] not in migration_responses:
                continue
            response = read(committed['result'])
            steps = response.get('next_steps', [])
            require(isinstance(steps, list), 'committed response steps are malformed')
            migrations = [step for step in steps if isinstance(step, dict) and step.get('kind') == 'schema_migration']
            if not migrations: continue
            require(len(migrations) == 1, 'conflicting migration responses')
            step = migrations[0]
            require('receipt' in step, 'migration response has no receipt')
            receipt = read(step['receipt'])
            require({'source', 'policy', 'target_intent', 'target_payload'} <= receipt.keys(),
                    'migration receipt is incomplete')
            converter = receipt.get('converter')
            require(receipt.get('type') == 'schema_migration' and converter in
                    ('lossless-v1-v2/1', self.api._migration_batch.LEGACY_COMPILED_CONVERTER, self.api._migration_batch.CONVERTER),
                    'unsupported migration converter')
            require(receipt.get('repository') == self.repository and receipt.get('goal') == number,
                    'migration repository or goal mismatch')
            require(response == {'next_steps': [{'kind': 'schema_migration', 'goal': number,
                    'status': 'migrated', 'receipt': step['receipt']}]}, 'migration response mismatch')
            policy = read(receipt['policy'])
            require(isinstance(policy, dict), 'historical policy is malformed')
            source = read(receipt['source'])
            require(source.get('type') == 'migration_source' and source.get('producer') is None and
                    source.get('provenance') == {'actor': converter, 'source': None, 'policy': receipt['policy']['hash']},
                    'preserved source provenance mismatch')
            issue = source.get('content')
            require(isinstance(issue, dict) and isinstance(issue.get('body'), str), 'preserved source is malformed')
            require(issue.get('number') == number, 'preserved source goal mismatch')
            legacy = self.api.parse_managed_goal(issue['body'], number)
            require(legacy and legacy['schema_version'] == 1, 'preserved source is not a managed v1 goal')
            require(not (legacy.get('claim') or {}).get('owner') and not (legacy.get('workflow') or {}).get('leases'),
                    'preserved source has unsettled ownership')
            request = self.api._migration_batch.request_for_receipt(receipt, digest)
            require(committed['request'] == request['request_id'] and committed['payload'] == digest(request),
                    'committed migration request identity or fingerprint mismatch')
            intent = read(receipt['target_intent'])
            require(intent == {'schema_version': 2, 'repository': self.repository, 'issue': number,
                    'revision': legacy['revision'] + 1, 'state': 'open', 'parent': legacy['parent'],
                    'payload': receipt['target_payload']}, 'migration target identity mismatch')
            payload = read(receipt['target_payload'])
            self.api._phase_evidence.contract_fields(payload, {'spec', 'graph', 'evidence', 'operational'} | (set(payload) & {'goal_context'}), 'Migration payload')
            require(payload['evidence'] == [] and payload['operational'] == {'leases': [], 'receipts': []},
                    'migration intent must not create results or ownership')
            spec = read(payload['spec'])
            require(spec.get('type') == 'goal_specification' and spec.get('producer') is None and
                    spec.get('provenance') == {'actor': converter, 'source': receipt['source'], 'policy': receipt['policy']['hash']},
                    'migration specification provenance mismatch')
            self.api._phase_evidence.validate_graph(read(payload['graph']))
            entry = copy.deepcopy(payload)
            entry['operational']['receipts'].append(committed)
            entry_ref = self.node_ref(digest(entry), number)
            require(read(entry_ref) == entry, 'committed migration payload mismatch')
            target = {**intent, 'payload': entry_ref}
            prefix, suffix = self.api._migration_batch.human_parts(self, issue['body'])
            context = {'request_id': request['request_id'], 'request_hash': digest(request),
                'source_hash': digest(issue['body']), 'human_hash': digest(prefix + suffix), 'root': None,
                'response': committed['result'], 'ownership': {}, 'acquisition': False, 'payload': entry_ref,
                'proof': None, 'source_envelope': {**intent, 'revision': legacy['revision']},
                'target_envelope': target, 'entry_payload': entry_ref,
                'migration': {'receipt': step['receipt'], 'policy': receipt['policy']['hash']}}
            transactions = [row for row in index.envelopes
                            if (row.get('context') or {}).get('request_id') == request['request_id']]
            require(transactions and all(row.get('goal') == number and row.get('context') == context and
                    row.get('transaction') == digest({'request': request, 'source': issue['body']})
                    for row in transactions), 'missing or conflicting exact migration transaction')
            if migration_context_only:
                recovered = self.api._migration_batch.historical_goal_context(self, receipt, source, policy)
                if 'historical_goal_context' in snapshot and snapshot['historical_goal_context'] != recovered:
                    raise ValueError('Conflicting committed historical goal context')
                snapshot['historical_goal_context'] = recovered
                snapshot['historical_goal_context_converter'] = converter
                snapshot['goal_context_provenances'] = [
                    {'actor': converter, 'source': receipt['source'], 'policy': receipt['policy']['hash']},
                    {'actor': 'host', 'source': step['receipt'], 'policy': receipt['policy']['hash']}]
            receipts = (legacy.get('workflow') or {}).get('receipts', {})
            require(isinstance(receipts, dict), 'legacy receipts are malformed')
            for request_id, receipt in receipts.items():
                fingerprint = receipt.get('hash') if isinstance(receipt, dict) else None
                require(isinstance(request_id, str) and bool(request_id) and isinstance(fingerprint, str) and
                        re.fullmatch(r'sha256:[0-9a-f]{64}', fingerprint), 'legacy request fingerprint is malformed')
                require(request_id not in completed or completed[request_id] == fingerprint,
                        'conflicting legacy request fingerprints')
                completed[request_id] = fingerprint
        return completed

    def node_committed_migration_cutoff(self, snapshot, index):
        """Return the last exactly committed migration transaction position."""
        receipts = snapshot['payload']['operational']['receipts']
        migration_commits = {}
        for row in receipts:
            response = self.read_artifact(snapshot['number'], row['result'])
            steps = response.get('next_steps', []) if isinstance(response, dict) else []
            migrations = [step for step in steps if isinstance(step, dict) and
                          step.get('kind') == 'schema_migration' and
                          step.get('goal') == snapshot['number'] and step.get('status') == 'migrated' and
                          isinstance(step.get('receipt'), dict)]
            if len(migrations) == 1:
                migration_commits[row['request']] = (row, migrations[0]['receipt'])
        matches = []
        for position, envelope in enumerate(index.envelopes):
            context = envelope.get('context') or {}
            committed_migration = migration_commits.get(context.get('request_id'))
            if committed_migration is None or envelope.get('goal') != snapshot['number']:
                continue
            receipt, migration_ref = committed_migration
            if (context.get('request_hash') == receipt['payload'] and
                    context.get('response') == receipt['result'] and
                    context.get('migration', {}).get('receipt') == migration_ref):
                transaction = envelope.get('transaction')
                if (not isinstance(transaction, str) or
                        re.fullmatch(r'sha256:[0-9a-f]{64}', transaction) is None):
                    return -1
                matches.append((position, transaction))
        if not matches or len({transaction for _, transaction in matches}) != 1:
            return -1
        positions = [position for position, _ in matches]
        if positions != list(range(positions[0], positions[-1] + 1)):
            return -1
        return positions[-1]

    def node_checkpoint_descriptor(self, snapshot, transaction):
        """Pin one stale checkpoint to exact provider bytes and current host state."""
        if not isinstance(transaction, str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', transaction):
            raise ValueError('Checkpoint reconciliation requires an exact transaction identity')
        comments = self.adapter.get_issue_comments(snapshot['number'])
        index = self.artifact_index(snapshot['number'])
        selected = [(comment, row) for comment, row in index.envelope_comments
                    if row.get('transaction') == transaction]
        if not selected:
            raise ValueError('Checkpoint reconciliation transaction is not present')
        contexts = [row.get('context') for _, row in selected]
        if not isinstance(contexts[0], dict) or any(context != contexts[0] for context in contexts):
            raise ValueError('Checkpoint reconciliation context is missing or conflicting')
        request_id = contexts[0].get('request_id')
        if not isinstance(request_id, str) or not request_id:
            raise ValueError('Checkpoint reconciliation requires a mutation request identity')
        if request_id in {receipt['request'] for receipt in snapshot['payload']['operational']['receipts']}:
            raise ValueError('Committed checkpoints do not require reconciliation')
        provider = [{'id': comment['id'], 'body_hash': comment_store.text_hash(comment['body'])}
                    for comment, _ in selected]
        if any(type(row['id']) is not int or row['id'] <= 0 for row in provider):
            raise ValueError('Checkpoint reconciliation requires provider comment identities')
        return {'transaction': transaction, 'request_id': request_id,
                'context_hash': digest(contexts[0]), 'provider': provider}

    def node_checkpoint_reconciliation_proposal(self, snapshot, transaction, rationale):
        if not (self.runtime or {}).get('root_id'):
            raise ValueError('Checkpoint reconciliation requires authenticated root')
        if not isinstance(rationale, str) or not rationale.strip():
            raise ValueError('Checkpoint reconciliation requires a scoped rationale')
        if snapshot['payload']['operational']['leases']:
            raise ValueError('Checkpoint reconciliation requires observed stopped ownership; leases remain')
        comments = self.adapter.get_issue_comments(snapshot['number'])
        return {'kind': 'checkpoint_reconciliation', 'repository': self.repository,
                'goal': snapshot['number'], 'policy': self.node_evidence_policy(),
                'checkpoint': self.node_checkpoint_descriptor(snapshot, transaction),
                'current': {'envelope': snapshot['envelope'], 'issue_body_hash': digest(snapshot['issue']['body']),
                            'observation': comment_store.comment_observation(comments)},
                'rationale': rationale}

    def node_checkpoint_reconcile_review(self, snapshot, payload, request):
        allowed = {'operation', 'request_id', 'proposal', 'actor', 'decision', 'report'}
        if set(request) != allowed:
            raise ValueError('Checkpoint reconciliation review does not match the returned contract')
        root, actor = (self.runtime or {}).get('root_id'), request.get('actor')
        invoking = os.environ.get('CODEX_THREAD_ID')
        if not root or actor in (None, root) or actor != invoking:
            raise ValueError('Checkpoint reconciliation requires an authenticated reviewer independent of root')
        if request.get('decision') not in {'approved', 'changes_requested'} or not isinstance(request.get('report'), str) or not request['report'].strip():
            raise ValueError('Checkpoint reconciliation review requires an explicit decision and report')
        proposal = request.get('proposal')
        if not isinstance(proposal, dict) or proposal != self.node_checkpoint_reconciliation_proposal(
                snapshot, proposal.get('checkpoint', {}).get('transaction'), proposal.get('rationale')):
            raise ValueError('Checkpoint reconciliation proposal changed before review')
        policy = self.node_evidence_policy()
        artifact = {'type': 'checkpoint_reconciliation_proposal', 'content': copy.deepcopy(proposal),
                    'producer': None, 'provenance': {'actor': root, 'source': None, 'policy': policy}}
        artifact_ref = self.node_ref(digest(artifact), snapshot['number']); snapshot['artifacts'][artifact_ref['hash']] = artifact
        review = {'type': 'checkpoint_reconciliation_review',
                  'content': {'decision': request['decision'], 'report': request['report']},
                  'producer': None, 'provenance': {'actor': actor, 'source': artifact_ref, 'policy': policy}}
        review_ref = self.node_ref(digest(review), snapshot['number']); snapshot['artifacts'][review_ref['hash']] = review
        if request['decision'] == 'approved':
            step = {'kind': 'human_approval', 'assignment': 'root', 'goal': snapshot['number'],
                    'proposal': artifact_ref, 'review': review_ref,
                    'action': 'Show the exact stale checkpoint reconciliation to the user and adopt only after explicit approval.',
                    'submission': {'operation': 'checkpoint_reconcile_adopt', 'proposal': artifact_ref,
                                   'review': review_ref, 'approved_by': None,
                                   'request_id': 'checkpoint-reconcile-' + digest({'proposal': artifact_ref, 'review': review_ref})[7:]}}
        else:
            step = {'kind': 'changes_requested', 'assignment': 'root', 'goal': snapshot['number'],
                    'proposal': artifact_ref, 'review': review_ref, 'report': request['report']}
        return self.node_persist(snapshot, payload, {'next_steps': [step]}, request)

    def node_checkpoint_reconcile_adopt(self, snapshot, payload, request):
        if (set(request) != {'operation', 'request_id', 'proposal', 'review', 'approved_by'}
                or not explicit_approval(request.get('approved_by'))):
            raise ValueError('Checkpoint reconciliation requires exact reviewed evidence and explicit human approval')
        for name in ('proposal', 'review'):
            self.api._phase_evidence.validate_ref(request[name])
            if self.node_ref_goal(request[name], snapshot['number']) != snapshot['number']:
                raise ValueError('Checkpoint reconciliation evidence belongs to another goal')
        proposal_artifact, review = snapshot['resolve'](request['proposal']), snapshot['resolve'](request['review'])
        root = (self.runtime or {}).get('root_id')
        if snapshot['payload']['operational']['leases']:
            raise ValueError('Checkpoint reconciliation requires observed stopped ownership; leases remain')
        policy = self.node_evidence_policy()
        proposal = proposal_artifact.get('content', {})
        if (not root or proposal.get('kind') != 'checkpoint_reconciliation'
                or proposal.get('repository') != self.repository
                or proposal.get('goal') != snapshot['number']
                or proposal.get('policy') != policy
                or proposal_artifact.get('provenance', {}).get('policy') != policy
                or review.get('provenance', {}).get('policy') != policy):
            raise ValueError('Checkpoint reconciliation evidence repository, goal or policy changed')
        if (proposal_artifact.get('type') != 'checkpoint_reconciliation_proposal'
                or proposal_artifact.get('provenance', {}).get('actor') != root
                or review.get('type') != 'checkpoint_reconciliation_review'
                or review.get('provenance', {}).get('source') != request['proposal']
                or review.get('provenance', {}).get('actor') in (None, root)
                or review.get('content', {}).get('decision') != 'approved'):
            raise ValueError('Exact independent approved checkpoint reconciliation review is required')
        proposal = proposal_artifact['content']
        descriptor = self.node_checkpoint_descriptor(snapshot, proposal['checkpoint']['transaction'])
        if descriptor != proposal['checkpoint']:
            raise ValueError('Checkpoint reconciliation target changed after review')
        review_edges = []
        review_comment_ids = set()
        index = self.artifact_index(snapshot['number'])
        for receipt in snapshot['payload']['operational']['receipts']:
            try: reviewed_response = index.resolve(receipt['result']['hash'])[0]
            except (KeyError, ValueError): continue
            steps = reviewed_response.get('next_steps', []) if isinstance(reviewed_response, dict) else []
            if any(step.get('proposal') == request['proposal'] and step.get('review') == request['review'] for step in steps):
                edge = self.node_receipt_edge(snapshot['number'], index, receipt)
                if edge is None or edge['context'].get('root') != root:
                    raise ValueError('Checkpoint reconciliation requires an authenticated review edge owned by current root')
                review_edges.append(edge['context'])
                review_comment_ids.update(edge['comment_ids'])
        review_edges = list({digest(edge): edge for edge in review_edges}.values())
        # A provider may publish immutable adoption rows before its issue-body
        # update fails. Only the frozen exact request may account for those rows
        # on retry; unrelated or conflicting pending bytes remain blockers.
        for item in index.envelopes:
            context = item.get('context') or {}
            if context.get('request_id') != request['request_id']:
                continue
            pending = {'request': request['request_id'], 'payload': digest(request),
                       'result': context.get('response')}
            edge = self.node_receipt_edge(snapshot['number'], index, pending)
            expected_response = {'type': 'checkpoint_reconciliation', 'version': 1,
                'checkpoint': descriptor, 'proposal': request['proposal'], 'review': request['review'],
                'approved_by': request['approved_by'],
                'next_steps': [{'kind': 'checkpoint', 'goal': snapshot['number'],
                    'action': 'Exact stale checkpoint reconciled; immutable history was preserved.'}]}
            if (edge is None or edge['source'] != snapshot['envelope']
                    or edge['context'].get('source_hash') != digest(snapshot['issue']['body'])
                    or edge['context'].get('root') != root or edge['response'] != expected_response):
                raise ValueError('Checkpoint reconciliation pending adoption request conflicts with exact retry')
            review_comment_ids.update(edge['comment_ids'])
        observation = proposal['current']['observation']
        comments = self.adapter.get_issue_comments(snapshot['number'])
        prefix = [comment for comment in comments if comment['id'] <= observation['last_id']]
        later_ids = {comment['id'] for comment in comments if comment['id'] > observation['last_id']}
        if (len(review_edges) != 1 or review_edges[0].get('source_envelope') != proposal['current']['envelope']
                or review_edges[0].get('target_envelope') != snapshot['envelope']
                or proposal['current'].get('issue_body_hash') != review_edges[0].get('source_hash')
                or comment_store.comment_observation(prefix) != observation
                or later_ids != review_comment_ids):
            raise ValueError('Checkpoint reconciliation review/current chain changed before adoption')
        response = {'type': 'checkpoint_reconciliation', 'version': 1,
                    'checkpoint': descriptor, 'proposal': request['proposal'], 'review': request['review'],
                    'approved_by': request['approved_by'],
                    'next_steps': [{'kind': 'checkpoint', 'goal': snapshot['number'],
                                    'action': 'Exact stale checkpoint reconciled; immutable history was preserved.'}]}
        return self.node_persist(snapshot, payload, response, request)

    def node_receipt_edge(self, number, index, receipt):
        """Authenticate one ordinary persisted mutation edge and its provider rows."""
        if (not isinstance(receipt, dict) or set(receipt) != {'request', 'payload', 'result'}
                or not isinstance(receipt.get('request'), str) or not receipt['request']
                or not isinstance(receipt.get('payload'), str)
                or not re.fullmatch(r'sha256:[0-9a-f]{64}', receipt['payload'])):
            return None
        result = receipt.get('result')
        if (not isinstance(result, dict) or set(result) != {'hash', 'uri'}
                or result != self.node_ref(result.get('hash'), number)):
            return None
        matching = [(comment, item) for comment, item in index.envelope_comments
                    if (item.get('context') or {}).get('response') == result]
        if not matching:
            return None
        transactions = {item.get('transaction') for _, item in matching}
        if len(transactions) != 1 or not re.fullmatch(r'sha256:[0-9a-f]{64}', next(iter(transactions)) or ''):
            return None
        transaction = next(iter(transactions))
        selected = [(comment, item) for comment, item in index.envelope_comments
                    if item.get('transaction') == transaction]
        try:
            complete = [comment_store.decode_envelope(comment['body']) for comment, _ in selected]
            if any(item is None for item in complete): return None
            comment_store.verify_manifest(complete)
        except (KeyError, TypeError, ValueError): return None
        contexts = [item.get('context') or {} for item in complete]
        if any(context != contexts[0] for context in contexts): return None
        context = contexts[0]; source = context.get('source_envelope'); target = context.get('target_envelope')
        required = {'request_id', 'request_hash', 'source_hash', 'human_hash', 'root', 'response',
                    'ownership', 'acquisition', 'payload', 'proof', 'source_envelope',
                    'target_envelope', 'entry_payload'}
        if (required - set(context) or set(context) - required - {'continuation', 'workspace_draft', 'workspace_draft_retirement', 'migration'}
                or context.get('request_id') != receipt['request'] or context.get('request_hash') != receipt['payload']
                or context.get('response') != result or not isinstance(source, dict) or not isinstance(target, dict)
                or source.get('repository') != self.repository or target.get('repository') != self.repository
                or source.get('issue') != number or target.get('issue') != number
                or type(source.get('revision')) is not int or target.get('revision') != source['revision'] + 1):
            return None
        identities = [comment.get('id') for comment, _ in selected]
        if any(type(identity) is not int or identity <= 0 for identity in identities) or len(identities) != len(set(identities)):
            return None
        try: response = index.resolve(result['hash'])[0]
        except (KeyError, ValueError): return None
        edge_response = response
        if isinstance(response, dict) and response.get('type') == 'submission_continuation':
            # Keep this in sync with node_receipt_response's immutable continuation
            # schema, but authenticate only: reconciliation must never materialize
            # deferred bindings while reading historical receipt edges.
            if (set(response) != {'type', 'version', 'source_envelope', 'target_metadata',
                                  'candidate_payload', 'entry_candidate_payload', 'response', 'bindings'}
                    or type(response.get('version')) is not int or response['version'] != 1
                    or context.get('continuation') not in (response, result)
                    or not isinstance(response.get('target_metadata'), dict)
                    or response.get('source_envelope') != source
                    or not isinstance(response.get('candidate_payload'), dict)
                    or response.get('candidate_payload') != self.node_ref(
                        (response.get('candidate_payload') or {}).get('hash'), number)
                    or not isinstance(response.get('entry_candidate_payload'), dict)
                    or response.get('entry_candidate_payload') != self.node_ref(
                        (response.get('entry_candidate_payload') or {}).get('hash'), number)
                    or not isinstance(response.get('response'), dict)
                    or not isinstance(response['response'].get('next_steps'), list)
                    or any(not isinstance(step, dict) for step in response['response']['next_steps'])
                    or not isinstance(response.get('bindings'), list)
                    or any(not isinstance(binding, dict)
                           or set(binding) != {'kind', 'step'}
                           or binding.get('kind') != 'target_envelope_digest'
                           or type(binding.get('step')) is not int
                           for binding in response['bindings'])):
                return None
            try:
                candidate = copy.deepcopy(index.resolve(response['candidate_payload']['hash'])[0])
                entry = copy.deepcopy(index.resolve(response['entry_candidate_payload']['hash'])[0])
                if (not isinstance(candidate.get('operational'), dict)
                        or not isinstance(candidate['operational'].get('receipts'), list)
                        or not isinstance(entry.get('operational'), dict)
                        or not isinstance(entry['operational'].get('receipts'), list)):
                    return None
                candidate['operational']['receipts'].append(receipt)
                entry['operational']['receipts'].append(receipt)
                continuation_target = {**response['target_metadata'],
                                       'payload': self.node_ref(digest(candidate), number)}
                expected = [{'kind': 'target_envelope_digest', 'step': position}
                            for position, step in enumerate(response['response']['next_steps'])
                            if step.get('kind') == 'reconcile']
                valid_bindings = response['bindings'] == expected
                for binding in expected:
                    step = response['response']['next_steps'][binding['step']]
                    valid_bindings = (valid_bindings and type(step.get('goal')) is int
                                      and step['goal'] == number
                                      and isinstance(step.get('submission'), dict)
                                      and step['submission'].get('operation') == 'reconcile'
                                      and step['submission'].get('expected_digest', 'missing') is None)
            except (AttributeError, KeyError, TypeError, ValueError):
                return None
            try: published_candidate = index.resolve(target['payload']['hash'])[0]
            except (KeyError, TypeError, ValueError): return None
            if (not valid_bindings or continuation_target != target
                    or context.get('payload') != target.get('payload')
                    or context.get('entry_payload') != self.node_ref(digest(entry), number)
                    or published_candidate != candidate):
                return None
            edge_response = copy.deepcopy(response['response'])
        elif not isinstance(response, dict) or not isinstance(response.get('next_steps'), list):
            return None
        return {'source': source, 'target': target, 'context': context,
                'transaction': transaction, 'comment_ids': set(identities), 'response': edge_response}

    def node_checkpoint_reconciled(self, snapshot, index, row, receipts):
        """Select the latest fully authenticated retirement on one receipt lineage."""
        try:
            descriptor = self.node_checkpoint_descriptor(snapshot, row.get('transaction'))
        except ValueError:
            return False
        request_ids = [receipt.get('request') for receipt in receipts if isinstance(receipt, dict)]
        if (len(request_ids) != len(receipts) or any(not isinstance(value, str) or not value for value in request_ids)
                or len(request_ids) != len(set(request_ids))):
            return False
        pins = []
        for receipt in receipts:
            try: response = index.resolve(receipt['result']['hash'])[0]
            except (KeyError, ValueError): continue
            if (isinstance(response, dict) and response.get('type') == 'checkpoint_reconciliation'
                    and response.get('version') == 1 and response.get('checkpoint') == descriptor):
                try:
                    pin = self.node_checkpoint_reconciliation_pin(snapshot, index, descriptor, receipts, receipt, response)
                except (AttributeError, KeyError, TypeError, ValueError):
                    pin = None
                if pin is not None:
                    pins.append(pin)
        # An earlier pin is dominated only by an exact adoption edge on its
        # authenticated suffix. Neither array position nor provider IDs alone
        # establish ancestry. Old invalid pins remain immutable history.
        maxima = [pin for pin in pins if not any(
            successor is not pin and successor['adoption'] in pin['suffix']
            for successor in pins)]
        return len(maxima) == 1 and all(
            pin is maxima[0] or maxima[0]['adoption'] in pin['suffix'] for pin in pins)

    def node_checkpoint_reconciliation_pin(self, snapshot, index, descriptor, receipts, receipt, response):
        """Validate one exact pin and its complete authenticated path to current."""
        try:
            proposal_artifact = index.resolve(response['proposal']['hash'])[0]
            review = index.resolve(response['review']['hash'])[0]
        except (KeyError, ValueError):
            return None
        root = (self.runtime or {}).get('root_id')
        policy = self.node_evidence_policy()
        proposal = proposal_artifact.get('content', {})
        if (not root or any(response.get(name) != self.node_ref(
                (response.get(name) or {}).get('hash'), snapshot['number'])
                for name in ('proposal', 'review'))
                or proposal.get('kind') != 'checkpoint_reconciliation'
                or proposal.get('repository') != self.repository
                or proposal.get('goal') != snapshot['number']
                or proposal.get('policy') != policy
                or proposal_artifact.get('producer') is not None or review.get('producer') is not None
                or proposal_artifact.get('provenance', {}).get('policy') != policy
                or review.get('provenance', {}).get('policy') != policy):
            return None
        if (not explicit_approval(response.get('approved_by'))
                or proposal_artifact.get('type') != 'checkpoint_reconciliation_proposal'
                or proposal_artifact.get('content', {}).get('checkpoint') != descriptor
                or proposal_artifact.get('provenance', {}).get('actor') != root
                or review.get('type') != 'checkpoint_reconciliation_review'
                or review.get('provenance', {}).get('source') != response['proposal']
                or review.get('provenance', {}).get('actor') in (None, root)
                or review.get('content', {}).get('decision') != 'approved'):
            return None
        adoption = self.node_receipt_edge(snapshot['number'], index, receipt)
        if adoption is None or adoption['context'].get('root') != root:
            return None
        review_edges = []
        allowed_comment_ids = set(adoption['comment_ids'])
        for candidate in receipts:
            try: reviewed_response = index.resolve(candidate['result']['hash'])[0]
            except (KeyError, ValueError): continue
            steps = reviewed_response.get('next_steps', []) if isinstance(reviewed_response, dict) else []
            if any(step.get('proposal') == response['proposal'] and step.get('review') == response['review']
                   for step in steps):
                edge = self.node_receipt_edge(snapshot['number'], index, candidate)
                if edge is None or edge['context'].get('root') != root:
                    return None
                review_edges.append(edge['context'])
                allowed_comment_ids.update(edge['comment_ids'])
        review_edges = list({digest(edge): edge for edge in review_edges}.values())
        current = proposal_artifact.get('content', {}).get('current', {})
        chain_edges = []
        for candidate in receipts:
            if candidate is receipt or candidate.get('result') == receipt.get('result'):
                continue
            edge = self.node_receipt_edge(snapshot['number'], index, candidate)
            if edge is not None and min(edge['comment_ids']) > max(adoption['comment_ids']):
                chain_edges.append(edge)
        cursor = adoption['target']; cursor_id = max(adoption['comment_ids']); used = []
        while cursor != snapshot['envelope']:
            candidates = [edge for edge in chain_edges if edge['source'] == cursor and edge not in used
                          and min(edge['comment_ids']) > cursor_id]
            if len(candidates) != 1:
                return None
            edge = candidates[0]; used.append(edge); cursor = edge['target']; cursor_id = max(edge['comment_ids'])
        for edge in used: allowed_comment_ids.update(edge['comment_ids'])
        observation = current.get('observation', {})
        comments = self.adapter.get_issue_comments(snapshot['number'])
        prefix = [comment for comment in comments if comment.get('id', 0) <= observation.get('last_id', -1)]
        later_ids = {comment.get('id') for comment in comments if comment.get('id', 0) > observation.get('last_id', -1)}
        valid = (len(review_edges) == 1
                and review_edges[0].get('source_envelope') == current.get('envelope')
                and review_edges[0].get('source_hash') == current.get('issue_body_hash')
                and review_edges[0].get('target_envelope') == adoption['source']
                and cursor == snapshot['envelope'] and len(used) == len(chain_edges)
                and comment_store.comment_observation(prefix) == observation
                and later_ids == allowed_comment_ids)

        return {'adoption': adoption, 'suffix': used} if valid else None

    def node_graph_proposal(self, snapshot, graph, rationale, *, pending_request=None):
        """Preflight a goal-only graph repair without replacing any evidence."""
        if not (self.runtime or {}).get('root_id'):
            raise ValueError('Goal graph repair requires authenticated root')
        if snapshot['envelope']['state'] != 'open' or str(snapshot['issue'].get('state', '')).lower() == 'closed':
            raise ValueError('Archived goal cannot adopt a graph')
        if snapshot['payload']['operational']['leases']:
            raise ValueError('Graph repair requires observed stopped ownership; leases remain')
        receipts = snapshot['payload']['operational']['receipts']
        receipt_ids = [row.get('request') for row in receipts if isinstance(row, dict)]
        if (len(receipt_ids) != len(receipts) or any(not isinstance(value, str) or not value for value in receipt_ids)
                or len(receipt_ids) != len(set(receipt_ids))):
            raise ValueError('Graph repair requires unique committed receipt identities')
        committed = {row['request'] for row in receipts}
        index = self.artifact_index(snapshot['number'])
        historical = self.node_committed_legacy_requests(snapshot)
        migration_cutoff = self.node_committed_migration_cutoff(snapshot, index)
        for position, row in enumerate(index.envelopes):
            context = row.get('context') or {}
            request_id = context.get('request_id')
            fingerprint = context.get('fingerprint')
            if (position <= migration_cutoff and row.get('goal') == snapshot['number'] and
                    request_id in historical and fingerprint == historical[request_id]):
                continue
            response_only = False
            if set(context) == {'request_id', 'response'} and isinstance(request_id, str) and request_id:
                response_ref = context.get('response')
                if (isinstance(response_ref, dict) and set(response_ref) == {'hash', 'uri'}
                        and isinstance(response_ref.get('hash'), str)
                        and re.fullmatch(r'sha256:[0-9a-f]{64}', response_ref['hash'])
                        and response_ref == self.node_ref(response_ref.get('hash'), snapshot['number'])):
                    transaction_rows = [item for item, _ in index.decoded.values()
                                        if item is not None and item.get('transaction') == row.get('transaction')]
                    carried = any(record.get('hash') == response_ref['hash']
                                  for item in transaction_rows for record in item.get('artifacts', []))
                    try:
                        response = index.resolve(response_ref['hash'])[0] if carried else None
                    except ValueError:
                        response = None
                    response_only = (isinstance(response, dict) and isinstance(response.get('next_steps'), list)
                                     and all(isinstance(step, dict) for step in response['next_steps'])
                                     and all((item.get('context') or {}) == context for item in transaction_rows))
            if (request_id and not response_only and request_id not in committed
                    and request_id != pending_request):
                if (row.get('goal') == snapshot['number'] and request_id in historical and
                        fingerprint == historical[request_id]): continue
                if self.node_checkpoint_reconciled(snapshot, index, row, receipts): continue
                raise ValueError('Uncommitted checkpoint must be resumed before graph repair: '
                                 'no committed legacy migration proof for exact goal/request/fingerprint')
        if not isinstance(rationale, str) or not rationale.strip():
            raise ValueError('Graph repair requires an explicit scoped rationale')
        self.api._phase_evidence.validate_graph(graph)
        previous = snapshot['graph']
        if ([node['id'] for node in graph['nodes'][:len(previous['nodes'])]] !=
                [node['id'] for node in previous['nodes']] or
                graph['task_sets'][:len(previous['task_sets'])] != previous['task_sets'] or
                graph['terminals'] != previous['terminals']):
            raise ValueError('Graph repair must preserve existing node indices, task sets and terminals')
        prospective = self.node_snapshot(snapshot['number'], graph_override=graph)
        before = snapshot['projection']['current']
        after = prospective['projection']['current']
        source = {key: snapshot['payload'][key] for key in ('spec', 'graph', 'evidence')}
        source.update(payload=snapshot['envelope']['payload'],
                      parent=snapshot['envelope']['parent'], state=snapshot['envelope']['state'],
                      current=[{'node': result['node'], 'result': ref}
                               for _, (ref, result) in sorted(before.items(), key=lambda row: str(row[0]))])
        retained, invalidated = [], []
        for key, (ref, result) in sorted(before.items(), key=lambda row: str(row[0])):
            if key in after and after[key][0] == ref:
                retained.append(ref)
            else:
                invalidated.append({
                    'node': result['node'], 'result': ref,
                    'reason': 'The reviewed prospective graph changes this Result contract, inputs, or target currentness.',
                })
        impact = {
            'retained': retained,
            'invalidated': invalidated,
            'rationale': ('Preserve every Result that remains current under the exact prospective graph; '
                          'invalidate only Results whose reviewed contract or declared inputs no longer match.'),
        }
        changed_nodes = {row['node']['node'] for row in invalidated}
        contracts = {node['id']: node for node in previous['nodes']}
        if any(not contracts.get(name, {}).get('independent_of') for name in changed_nodes):
            raise ValueError('Graph repair must preserve every non-review current Result and its settled contract')
        return {'kind': 'goal_graph_adoption', 'repository': self.repository, 'goal': snapshot['number'],
                'policy': self.node_evidence_policy(), 'source': source,
                'target': {'graph': digest(graph)}, 'graph': copy.deepcopy(graph),
                'impact': impact, 'rationale': rationale}

    def node_normalization_request(self, snapshot, *, compiler_version=None, pending_request=None):
        """Authenticate an exact additive installed-compiler transaction."""
        compiler = self.api._graph_compiler
        version = compiler.SUPPORTED_VERSION if compiler_version is None else compiler_version
        compiled = compiler.compile_graph(snapshot['graph'], local_goal=snapshot['number'],
                                          compiler_version=version)
        if compiled['diagnostics']:
            raise ValueError('Graph recovery requires reviewed repair: ' + comment_store.canonical(compiled['diagnostics']))
        graph = compiled['graph']; previous = snapshot['graph']
        if graph == previous:
            return None, compiled
        if (graph['nodes'][:len(previous['nodes'])] != previous['nodes']
                or graph['task_sets'][:len(previous['task_sets'])] != previous['task_sets']
                or graph['terminals'] != previous['terminals']):
            raise ValueError('Compiler normalization must preserve every existing contract exactly')
        compiler.validate_recovery(graph, local_goal=snapshot['number'], compiler_version=version)
        proposal = self.node_graph_proposal(snapshot, graph,
            'Installed deterministic correction completeness; no semantic decisions.',
            pending_request=pending_request)
        if proposal['impact']['invalidated']:
            raise ValueError('Normalization must preserve every current Result: nonzero invalidations')
        delta = {'nodes': graph['nodes'][len(previous['nodes']):],
                 'task_sets': graph['task_sets'][len(previous['task_sets']):]}
        request = {'operation': 'graph_normalize', 'repository': self.repository,
            'goal': snapshot['number'], 'root': (self.runtime or {}).get('root_id'),
            'source': snapshot['envelope']['payload'], 'source_envelope': snapshot['envelope'],
            'source_body_hash': digest(snapshot['issue']['body']),
            'policy': self.node_evidence_policy(), 'current': proposal['source']['current'],
            'compiler_version': version, 'target_hash': compiled['target_hash'],
            'delta_hash': digest(delta)}
        request['request_id'] = 'graph-normalize-' + digest(request)[7:]
        return request, compiled

    def node_normalization_candidate(self, number):
        # Executable topology is projected from reviewed policy, never repaired
        # independently on a goal. Older normalization receipts remain readable.
        return None

    def node_graph_normalize(self, snapshot, payload, request):
        expected, compiled = self.node_normalization_request(snapshot,
            compiler_version=request.get('compiler_version'), pending_request=request.get('request_id'))
        if expected is None or request != expected:
            raise ValueError('Normalization requires exact current source, policy, compiler, target, delta and request')
        reference = self.node_ref(compiled['target_hash'], snapshot['number'])
        snapshot['artifacts'][reference['hash']] = compiled['graph']
        payload['graph'] = reference
        snapshot['normalization'] = True
        response = {'type': 'graph_normalization', 'content': {'request': copy.deepcopy(request),
            'target_hash': compiled['target_hash'], 'routes': compiled['routes']},
            'next_steps': [{'kind': 'checkpoint', 'goal': snapshot['number'],
                            'action': 'Recompute ordinary work from the confirmed graph.'}]}
        persisted = self.node_persist(snapshot, payload, response, request)
        # A provider write acknowledgement is not durable confirmation. Direct
        # retries need the same fresh proof as checkpoint-selected normalization.
        clear_reads = getattr(self, '_clear_invocation_reads', None)
        if clear_reads is not None:
            clear_reads()
        else:
            self.invalidate()
        observed = self.adapter.get_issue(snapshot['number'])
        expected_envelope = {**snapshot['envelope'],
            'revision': snapshot['envelope']['revision'] + 1,
            'payload': self.node_ref(digest(payload), snapshot['number'])}
        actual_envelope = self.api._goals.parse_managed_goal(observed['body'], snapshot['number'])
        if (actual_envelope != expected_envelope
                or str(observed.get('state', '')).lower() == 'closed'
                or self.api._migration_batch.human_parts(self, observed['body']) !=
                   self.api._migration_batch.human_parts(self, snapshot['issue']['body'])):
            raise ValueError('Normalization durable target readback is unconfirmed; retry exact pending request')
        index = self.artifact_index(snapshot['number'])
        if (index.resolve(expected_envelope['payload']['hash'])[0] != payload
                or index.resolve(reference['hash'])[0] != compiled['graph']):
            raise ValueError('Normalization durable payload/graph readback is unconfirmed')
        return persisted

    def node_graph_adopt(self, snapshot, payload, request):
        direct = {'operation', 'request_id', 'proposal', 'review', 'approved_by'}
        legacy = direct | {'review_goal'}
        if set(request) not in (direct, legacy) or not explicit_approval(request.get('approved_by')):
            raise ValueError('Exact graph proposal, independent review and explicit human approval are required')
        if 'review_goal' in request:
            if not self.api._phase_evidence.positive_integer(request['review_goal']):
                raise ValueError('Graph repair requires an exact review goal')
            reviewed = self.node_snapshot(request['review_goal'])
            current = reviewed['projection']['current']
            proposer = next(((key, result) for key, (_, result) in current.items()
                             if request['proposal'] in result['outputs'].values()), None)
            reviewer = next(((key, result) for key, (ref, result) in current.items()
                             if ref == request['review']), None)
            if not proposer or not reviewer:
                raise ValueError('Graph repair requires current canonical proposal and reviewer Result')
            producer_key, producer = proposer
            review_key, review = reviewer
            states = reviewed['projection']['states']
            if (states[producer_key]['contract']['executor']['role'] != 'root' or
                    producer['executor'] != (self.runtime or {}).get('root_id')):
                raise ValueError('Graph proposal requires current authenticated root provenance')
            independent = any(producer['node'] in row['targets'] for row in review['resolutions']
                              if row['selector'] in states[review_key]['contract']['independent_of'])
            inspected = any(row['source'] == request['proposal'] and row['mode'] == 'identity' and not row['path']
                            for row in review['inputs'])
            decisions = [reviewed['artifacts'][ref['hash']] for ref in review['outputs'].values()]
            approved = any(value.get('type') == 'review_decision' and isinstance(value.get('content'), dict) and
                           value['content'].get('decision') == 'approved' for value in decisions)
            if producer['executor'] == review['executor'] or not independent or not inspected or not approved:
                raise ValueError('Exact current independent approved graph review is required')
            artifact = reviewed['artifacts'][request['proposal']['hash']]
            reviewed_issue = reviewed['issue']['body']
        else:
            for name in ('proposal', 'review'):
                self.api._phase_evidence.validate_ref(request[name])
                if self.node_ref_goal(request[name], snapshot['number']) != snapshot['number']:
                    raise ValueError('Administrative graph review must be stored on the affected goal')
            artifact = snapshot['resolve'](request['proposal'])
            review = snapshot['resolve'](request['review'])
            root = (self.runtime or {}).get('root_id')
            if (not isinstance(artifact, dict) or artifact.get('type') != 'administrative_graph_proposal' or
                    artifact.get('provenance', {}).get('actor') != root or
                    not isinstance(review, dict) or review.get('type') != 'administrative_graph_review' or
                    review.get('provenance', {}).get('source') != request['proposal'] or
                    review.get('provenance', {}).get('actor') in (None, root) or
                    review.get('content', {}).get('decision') != 'approved'):
                raise ValueError('Exact current independent approved administrative graph review is required')
            reviewed_issue = snapshot['issue']['body']
        proposal = artifact['content']
        if isinstance(proposal, str):
            try:
                proposal = json.loads(proposal)
            except ValueError:
                raise ValueError('Root graph proposal must contain the exact prepared JSON manifest') from None
        if not isinstance(proposal, dict) or set(proposal) != {
                'kind', 'repository', 'goal', 'policy', 'source', 'target', 'graph', 'impact', 'rationale'}:
            raise ValueError('Invalid prepared graph proposal manifest')
        expected = self.node_graph_proposal(snapshot, proposal['graph'], proposal['rationale'],
                                           pending_request=request['request_id'])
        reviewed_current = proposal.get('source', {}).get('current', [])
        expected_current = expected['source']['current']
        normalized = copy.deepcopy(proposal)
        if isinstance(normalized.get('source'), dict):
            normalized['source']['current'] = expected_current
        if 'review_goal' not in request:
            # The same-goal review appends only an operational receipt. The
            # reviewed spec, graph, evidence, parent/state and current Results
            # remain exact, while that receipt necessarily changes payload Ref.
            expected['source']['payload'] = normalized['source']['payload']
        if not all(row in reviewed_current for row in expected_current) or normalized != expected:
            raise ValueError('Graph proposal source, target, current Results or policy changed after review')
        if 'review_goal' in request and self.adapter.get_issue(request['review_goal'])['body'] != reviewed_issue:
            raise ValueError('Graph review source changed before adoption')
        graph_hash = digest(proposal['graph'])
        snapshot['artifacts'][graph_hash] = proposal['graph']
        payload['graph'] = self.node_ref(graph_hash, snapshot['number'])
        response = {'next_steps': [{'kind': 'checkpoint', 'goal': snapshot['number'],
                    'graph': payload['graph'], 'proposal': request['proposal'], 'review': request['review'],
                    'impact': proposal['impact'],
                    'action': ('Reviewed goal-only graph adopted; immutable evidence was preserved and only the '
                               'explicitly reviewed affected Results lost currentness.')}]}
        return self.node_persist(snapshot, payload, response, request)

    def node_graph_review(self, snapshot, payload, request):
        """Persist an authority-free independent review on the affected goal."""
        allowed = {'operation', 'request_id', 'proposal', 'actor', 'decision', 'report'}
        if set(request) != allowed:
            raise ValueError('Administrative graph review submission does not match the returned contract')
        root = (self.runtime or {}).get('root_id')
        actor = request.get('actor')
        invoking_actor = os.environ.get('CODEX_THREAD_ID')
        if (not root or not isinstance(actor, str) or not actor.strip() or actor == root or
                not isinstance(invoking_actor, str) or not invoking_actor.strip() or actor != invoking_actor):
            if actor != root and actor != invoking_actor:
                raise ValueError('Administrative graph review actor must match the authenticated invoking thread identity')
            raise ValueError('Administrative graph review requires an authenticated actor independent of root')
        if request.get('decision') not in {'approved', 'changes_requested'}:
            raise ValueError('Administrative graph review requires an explicit decision')
        if not isinstance(request.get('report'), str) or not request['report'].strip():
            raise ValueError('Administrative graph review requires a nonempty report')
        proposal = request.get('proposal')
        if not isinstance(proposal, dict) or set(proposal) != {
                'kind', 'repository', 'goal', 'policy', 'source', 'target', 'graph', 'impact', 'rationale'}:
            raise ValueError('Administrative graph review requires the exact prepared proposal')
        expected = self.node_graph_proposal(snapshot, proposal['graph'], proposal['rationale'],
                                            pending_request=request['request_id'])
        reviewed_current = proposal.get('source', {}).get('current', [])
        expected_current = expected['source']['current']
        normalized = copy.deepcopy(proposal)
        if isinstance(normalized.get('source'), dict):
            normalized['source']['current'] = expected_current
        if not all(row in reviewed_current for row in expected_current) or normalized != expected:
            raise ValueError('Graph proposal source, target, policy or impact changed before review')
        policy = self.node_evidence_policy()
        proposal_artifact = {'type': 'administrative_graph_proposal', 'content': copy.deepcopy(proposal),
            'producer': None, 'provenance': {'actor': root, 'source': None, 'policy': policy}}
        proposal_hash = digest(proposal_artifact)
        snapshot['artifacts'][proposal_hash] = proposal_artifact
        proposal_ref = self.node_ref(proposal_hash, snapshot['number'])
        review_artifact = {'type': 'administrative_graph_review',
            'content': {'decision': request['decision'], 'report': request['report']},
            'producer': None, 'provenance': {'actor': actor, 'source': proposal_ref, 'policy': policy}}
        review_hash = digest(review_artifact)
        snapshot['artifacts'][review_hash] = review_artifact
        review_ref = self.node_ref(review_hash, snapshot['number'])
        if request['decision'] == 'approved':
            step = {'kind': 'human_approval', 'assignment': 'root',
                'goal': snapshot['number'], 'proposal': proposal_ref, 'review': review_ref,
                'decision': request['decision'], 'report': request['report'],
                'action': ('Show the exact reviewed graph proposal and impact to the user. Adopt only after '
                           'explicit approval; this transaction grants no workspace or publication authority.'),
                'submission': {'operation': 'graph_adopt', 'proposal': proposal_ref, 'review': review_ref,
                               'approved_by': None,
                               'request_id': 'graph-adopt-' + digest({'proposal': proposal_ref, 'review': review_ref})[7:]}}
        else:
            step = {'kind': 'changes_requested', 'assignment': 'root',
                'goal': snapshot['number'], 'proposal': proposal_ref, 'review': review_ref,
                'decision': request['decision'], 'report': request['report'],
                'action': ('Revise the prospective graph to resolve this exact review, then run graph_prepare '
                           'again. The rejected transaction remains durable evidence and grants no authority.')}
        response = {'next_steps': [step]}
        return self.node_persist(snapshot, payload, response, request)

    def node_graph_review_bootstrap(self, snapshot, payload, request):
        """Install the closed, authority-free graph-review workflow on a fresh goal.

        Graph adoption normally requires durable root proposal and independent
        review Results.  A newly captured review goal otherwise inherits the
        project product graph and cannot produce those Results without first
        adopting a graph, creating an impossible recursion.  This host-defined
        graph is the finite bootstrap: it grants no workspace resources and is
        usable only before the goal has Results or live ownership.
        """
        allowed = {'operation', 'request_id', 'approved_by'}
        if set(request) != allowed or not explicit_approval(request.get('approved_by')):
            raise ValueError('Graph-review bootstrap requires explicit human approval')
        if snapshot['projection']['current'] or snapshot['projection']['leases']:
            raise ValueError('Graph-review bootstrap requires a fresh goal with no Results or live ownership')
        selector = lambda node: {'kind': 'node', 'goal': '#this', 'node': node}
        text = {'type': 'text', 'schema': {'kind': 'string'}}
        review = {'type': 'review_decision', 'schema': {'kind': 'object', 'fields': {
            'decision': {'kind': 'enum', 'values': ['approved', 'changes_requested']},
            'report': {'kind': 'string'},
        }}}
        graph = {'nodes': [
            {'id': 'propose_graph',
             'prompt': 'Emit the exact prepared graph proposal manifest without modification.',
             'inputs': {}, 'outputs': {'value': text}, 'requires': [],
             'executor': {'role': 'root', 'capability': 'bounded', 'resources': [],
                          'authority': {'subject': selector('propose_graph'), 'output': 'value'}},
             'independent_of': [], 'gates': [], 'resolves': [], 'permits': []},
            {'id': 'review_graph',
             'prompt': 'Independently inspect the exact proposal by identity and emit an explicit review decision.',
             'inputs': {'subject': {'producer': {'node': selector('propose_graph')}, 'output': 'value',
                                    'path': [], 'mode': 'identity', 'type': {'kind': 'string'}}},
             'outputs': {'value': review}, 'requires': [selector('propose_graph')],
             'executor': {'role': 'worker', 'capability': 'architectural', 'resources': [],
                          'authority': {'subject': selector('review_graph'), 'output': 'value'}},
             'independent_of': [selector('propose_graph')], 'gates': [], 'resolves': [], 'permits': []},
        ], 'task_sets': [], 'terminals': [selector('review_graph')]}
        self.api._phase_evidence.validate_graph(graph)
        graph_hash = digest(graph)
        snapshot['artifacts'][graph_hash] = graph
        payload['graph'] = self.node_ref(graph_hash, snapshot['number'])
        response = {'next_steps': [{'kind': 'checkpoint', 'goal': snapshot['number'],
                    'graph': payload['graph'],
                    'action': 'Fresh administrative goal bootstrapped with the closed proposal/review graph.'}]}
        return self.node_persist(snapshot, payload, response, request)

    def node_publication_context(self, snapshots, projection, artifacts):
        """Observe provider facts only for explicitly declared publication work."""
        ev = self.api._phase_evidence
        owners = {ref['hash']: (key, result) for key, (_, result) in projection['current'].items() for ref in result['outputs'].values()}
        contexts, observations = {}, {}
        for key, state in projection['states'].items():
            if 'repository_publication' not in state['contract']['executor']['resources'] or state['state'] == 'blocked': continue
            try:
                selected = [(binding, artifacts[binding['source']['hash']]) for binding in state['inputs']
                            if artifacts[binding['source']['hash']].get('type') in {'repository_context', 'published_candidate'}]
                if len(selected) != 1: raise ValueError('Publication requires one exact declared repository context input')
                binding, blob = selected[0]; reference = binding['source']; value = blob['content']
                owner_key, owner = owners[reference['hash']]
                root = (self.runtime or {}).get('root_id')
                refreshes = [candidate['payload'].get('stack_integration', {}).get('root_refresh', {})
                             for candidate in snapshots.values()]
                refreshed = any(refresh.get('root') == root and any(
                    row.get('goal') == key[0] and row.get('context') == reference
                    for row in refresh.get('members', [])) for refresh in refreshes)
                if binding['mode'] != 'identity' or binding['path'] or (owner['executor'] != root and not refreshed) or projection['states'][owner_key]['contract']['executor']['role'] != 'root': raise ValueError('Repository context requires authenticated current root output')
                candidate = blob.get('type') == 'published_candidate'
                if candidate:
                    if (set(value) != {'repository', 'branch', 'base', 'pr', 'head_oid'}
                            or value.get('repository') != self.repository
                            or any(not isinstance(value.get(name), str) or not value[name] for name in ('branch', 'base', 'pr', 'head_oid'))
                            or not re.fullmatch('[0-9a-f]{40}', value['head_oid'])
                            or not re.fullmatch(r'https://github.com/' + re.escape(self.repository) + r'/pull/[1-9][0-9]*', value['pr'])):
                        raise ValueError('Invalid published candidate')
                    publication_context = {'branch': value['branch'], 'base': value['base'],
                                           'target': str(self.repo.resolve()), 'pr': value['pr']}
                else:
                    declared = state['contract']['executor']['authority']
                    targets = [target for row in state['resolutions'] if row['selector'] == declared['subject'] for target in row['targets']]
                    if owner['node'] not in targets or owner['outputs'].get(declared['output']) != reference: raise ValueError('Publication context differs from declared authority selector')
                    publication_context = value
                permits = []
                has_publication_authorization = any(
                    artifacts[item['source']['hash']].get('type') == 'publication_authorization'
                    for item in state['inputs'])
                for item in state['inputs']:
                    artifact = artifacts[item['source']['hash']]
                    if artifact.get('type') not in {'repository_authorization', 'publication_authorization', 'merge_authorization'}: continue
                    if artifact.get('type') == 'merge_authorization' and has_publication_authorization: continue
                    issuer = owners.get(item['source']['hash'])
                    refresh_permits_prior_context = (refreshed and (
                        artifact.get('type') == 'repository_authorization' or
                        artifact.get('type') == 'publication_authorization' and any(
                            key[0] in refresh.get('observed_goals', []) for refresh in refreshes
                            if refresh.get('root') == root)))
                    if item['mode'] != 'identity' or item['path'] or not issuer or (issuer[1]['executor'] != root and not refresh_permits_prior_context) or projection['states'][issuer[0]]['contract']['executor']['role'] != 'root': continue
                    content = artifact['content']
                    if not self.node_authorization_policy_matches(content, artifact, issuer[1], artifacts) or content.get('decision') != 'approved': continue
                    if artifact['type'] == 'repository_authorization' and content.get('context', content.get('manifest')) != reference: continue
                    if artifact['type'] == 'publication_authorization':
                        subject_ref = content.get('subject', content.get('manifest'))
                        if subject_ref != reference:
                            subject = owners.get((subject_ref or {}).get('hash'))
                            if not subject or not any(row['source'] == reference for row in subject[1]['inputs']): continue
                    if artifact['type'] == 'merge_authorization' and content.get('manifest') != reference: continue
                    permits.append(item['source'])
                # The root-produced published candidate is itself downstream of
                # exact repository authorization.  Later observation and review
                # nodes may consume it before merge authorization exists.
                if not permits and candidate:
                    permits = [row['source'] for row in owner['inputs']
                               if artifacts[row['source']['hash']].get('type') == 'repository_authorization']
                if len(permits) != 1: raise ValueError('Publication requires current reviewed root authorization for exact context')
                value = publication_context
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
                if not isinstance(facts, dict) or facts.get('repository') != self.repository:
                    raise ValueError('Provider publication repository/base identity mismatch or unknown')
                if facts.get('base_ref') != value['base']:
                    planning = policy_section(self.project, 'git_review_release')['configuration']['release_planning']
                    new_base = facts.get('base_ref')
                    base_oid = facts.get('base_oid')
                    if (not isinstance(planning, dict) or not candidate or facts.get('merged')
                            or planning.get('enabled')
                            or new_base != planning.get('integration_branch')
                            or not isinstance(base_oid, str) or not re.fullmatch('[0-9a-f]{40}', base_oid)):
                        raise ValueError('Provider publication repository/base identity mismatch or unknown')
                    refs = subprocess.run(['git', 'ls-remote', '--heads', 'origin',
                        'refs/heads/' + value['base'], 'refs/heads/' + new_base],
                        cwd=self.repo, capture_output=True, text=True, check=False)
                    remote = {}
                    if refs.returncode == 0:
                        for line in refs.stdout.splitlines():
                            fields = line.split()
                            if len(fields) == 2:
                                remote[fields[1]] = fields[0]
                    if (remote.get('refs/heads/' + value['base']) != base_oid
                            or remote.get('refs/heads/' + new_base) != base_oid):
                        raise ValueError('Provider publication repository/base identity mismatch or unknown')
                    # The root's published-candidate Result remains historical.
                    # An exact-OID retarget to the policy trunk changes only PR
                    # topology; current provider facts govern downstream gates.
                    value = {**value, 'base': new_base}
                for name in ('head_oid', 'base_oid'):
                    if not isinstance(facts.get(name), str) or not re.fullmatch('[0-9a-f]{40}', facts[name]): raise ValueError('Provider publication head/base is unknown')
                if candidate and facts['head_oid'] != blob['content']['head_oid']:
                    raise ValueError('Published candidate head differs from current provider head')
                if not facts.get('merged'):
                    repair = None if refreshed else self.publication_topology(
                        value, facts, self.node_managed_publication_branches, goal_number=key[0])
                    if repair:
                        contexts[key] = {'error': repair['action'], 'repair': repair}
                        continue
                ci = 'verified' if facts.get('checks_verified') is True else 'absent' if facts.get('checks_present') is False else 'unverified' if facts.get('checks_present') is True else 'unknown'
                observed = {name: facts[name] for name in ('repository', 'head_oid', 'base_oid', 'base_ref')}
                observed.update(pr=value['pr'], ci=ci, review_verified=facts.get('review_verified'))
                # Provider adapters may expose an update marker covering review,
                # comment and thread edits.  Bind it when available so any
                # feedback change invalidates the assessment/authorization.
                marker = facts.get('updated_at')
                # The goal issue is our own checkpoint store. Its updated_at
                # changes when we seal a certificate and cannot stand in for
                # the pull request's feedback marker.
                if facts.get('merged'):
                    certificate_ref = snapshots.get(key[0], {}).get('payload', {}).get('publication_certificate')
                    certificate = artifacts.get(certificate_ref.get('hash')) if isinstance(certificate_ref, dict) else None
                    if (certificate and certificate.get('type') == 'publication_certificate'
                            and certificate_ref == self.node_ref(digest(certificate), key[0])):
                        sealed = certificate.get('content', {})
                        identity = {'repository': self.repository, 'goal': key[0], 'pr': value['pr'],
                                    'branch': value['branch'], 'base': value['base'],
                                    'head_oid': facts['head_oid'], 'base_oid': facts['base_oid']}
                        if (all(sealed.get(name) == expected for name, expected in identity.items())
                                and sealed.get('policy') == digest(self.project['policy'])
                                and self.node_merge_effect_marked(sealed, facts)):
                            self.node_stack_verified_merge(facts)
                            marker = sealed.get('feedback_marker', marker)
                            if isinstance(sealed.get('review_verified'), bool):
                                observed['review_verified'] = sealed['review_verified']
                            if sealed.get('ci') in {'verified', 'unverified', 'absent', 'unknown'}:
                                observed['ci'] = sealed['ci']
                if isinstance(marker, str): observed['feedback_marker'] = marker
                semantic = {**observed, 'context': reference}
                if policy_section(self.project, 'verification_testing')['configuration']['required_ci'] == 'disabled': semantic.pop('ci')
                artifact = {'type': 'publication_snapshot', 'content': semantic, 'producer': None,
                            'provenance': {'actor': 'host', 'source': None, 'policy': self.node_evidence_policy()}}
                identity = digest(artifact); artifacts[identity] = artifact
                contexts[key] = {'binding': {'hash': identity, 'uri': 'urn:' + identity}, 'context': value, 'context_ref': reference,
                                 'observed': observed, 'provider': facts, 'base_branch': value['base'], 'base_commit': facts['base_oid']}
            except (ValueError, KeyError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
                contexts[key] = {'error': 'Publication provider/authority: ' + str(exc)}
        return contexts

    def node_managed_publication_branches(self, observed):
        """Discover managed heads from current authenticated generic root evidence."""
        candidates = []
        heads = {row['headRefName'] for row in observed if isinstance(row, dict) and isinstance(row.get('headRefName'), str)}
        root = (self.runtime or {}).get('root_id')
        goals = [goal for goal in self.portfolio()
                 if goal.get('schema_version') == 2 and goal.get('status') not in {'done', 'cancelled'}]
        # Discovery reuses this invocation's fresh broadphase bodies. Candidate
        # authentication and mutation boundaries still perform their own reads.
        issues = {goal['key']: self.api.provider_issue_snapshot(
            self.repo, self.repository, goal['key']) for goal in goals}
        if not hasattr(self, '_issue_observations'):
            self._issue_observations = {}
        self._issue_observations.update(copy.deepcopy(issues))
        # Retain provider discovery for this read epoch only. Fresh
        # PR observations and broadphase body identities still precede reuse.
        projection_identity = digest({'pull_requests': observed, 'root': root,
                           'policy': getattr(self, 'project', {}).get('policy'),
                           'goals': [[goal['key'], goal.get('status'),
                                      comment_store.text_hash(issues[goal['key']]['body'])]
                                     for goal in goals]})
        memo = getattr(self, '_publication_candidate_discovery', None)
        if memo is not None and memo[0] == projection_identity:
            return self.node_authenticate_publication_candidates(memo[1])
        self._publication_candidate_discovery = None
        # Consume retained entries before misses can evict them during a scan
        # larger than the bounded cache. This hint changes no validation or scope.
        goals.sort(key=lambda goal: not state_cache.has_entry(
            self.repository, goal['key'], comment_store.text_hash(
                issues[goal['key']]['body'])))
        # Optional capability is explicit on the provider type: arbitrary Mock
        # attributes must not accidentally enable batching on older adapters.
        provider = self._mutation_adapter if isinstance(self.adapter, ProviderReadGateway) else self.adapter
        batch_reader = (getattr(self.adapter, 'get_issue_comment_tails', None)
                        if callable(getattr(type(provider), 'get_issue_comment_tails', None)) else None)
        self._publication_tails = {}
        discovery_confirmed = True
        for offset in range(0, len(goals), 4):
            window = goals[offset:offset + 4]
            try:
                if callable(batch_reader):
                    numbers = [goal['key'] for goal in window]
                    try:
                        tails = batch_reader(numbers)
                    except self.api.GoalHistoryReadError as exc:
                        discovery_confirmed = False
                        tails = {number: exc for number in numbers}
                    self._publication_tails = {
                        (number, comment_store.text_hash(issues[number]['body'])): tails[number]
                        for number in numbers}
                for goal in window:
                    number = goal['key']
                    def read(ref):
                        value = self.read_artifact(number, ref)
                        return json.loads(value) if isinstance(value, str) else value
                    envelope = self.api.parse_managed_goal(issues[number]['body'], number)
                    payload = read(envelope['payload']); graph = read(payload['graph'])
                    # Locate possible context outputs without evaluating unrelated
                    # workspace/relationship consumers. This filter grants no authority.
                    declarations = [*graph['nodes'], *(row['template'] for row in graph['task_sets'])]
                    slots = {node['id']: {name for name, contract in node['outputs'].items()
                                         if contract.get('type') in {'repository_context', 'published_candidate'}}
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
                            if (context.get('type') in {'repository_context', 'published_candidate'}
                                    and context['content'].get('branch') in heads): candidate = True
                    if not candidate: continue
                    candidates.append(number)
            finally:
                self._publication_tails.clear()
                tails = None
        if discovery_confirmed:
            self._publication_candidate_discovery = (projection_identity, tuple(candidates))
        return self.node_authenticate_publication_candidates(candidates)

    def node_authenticate_publication_candidates(self, candidates):
        """Recheck mutable host/relationship/runtime currentness on every read."""
        root = (self.runtime or {}).get('root_id')
        branches = set()
        try:
            for number in candidates:
                snapshot = self.node_snapshot(number, publication_probe=True)
                projection = snapshot['projection']; artifacts = snapshot['artifacts']
                owners = {ref['hash']: (key, result) for key, (_, result) in projection['current'].items() for ref in result['outputs'].values()}
                for identity, (key, result) in owners.items():
                    artifact = artifacts[identity]
                    if artifact.get('type') != 'repository_authorization': continue
                    if result['executor'] != root or projection['states'][key]['contract']['executor']['role'] != 'root': continue
                    value = artifact['content']; reference = value.get('context', {})
                    if value.get('decision') != 'approved' or not self.node_authorization_policy_matches(value, artifact, result, artifacts): continue
                    owner = owners.get(reference.get('hash'))
                    if not owner or owner[1]['executor'] != root or projection['states'][owner[0]]['contract']['executor']['role'] != 'root': continue
                    if not any(row['source'] == reference and row['mode'] == 'identity' and not row['path'] for row in result['inputs']): continue
                    context = artifacts[reference['hash']]
                    if context.get('type') == 'repository_context' and isinstance(context['content'].get('branch'), str): branches.add(context['content']['branch'])
                for identity, (key, result) in owners.items():
                    artifact = artifacts[identity]
                    if artifact.get('type') != 'published_candidate' or result['executor'] != root:
                        continue
                    if projection['states'][key]['contract']['executor']['role'] != 'root':
                        continue
                    permits = [row['source'] for row in result['inputs']
                               if row.get('mode') == 'identity' and not row.get('path')
                               and artifacts[row['source']['hash']].get('type') == 'repository_authorization']
                    if len(permits) != 1:
                        continue
                    try:
                        self.node_compaction_authorization(snapshot, permits[0])
                    except ValueError:
                        continue
                    branch = artifact.get('content', {}).get('branch')
                    if isinstance(branch, str) and branch:
                        branches.add(branch)
        except Exception:
            self._publication_candidate_discovery = None
            raise
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

    def node_workspace_authority_inputs(self, inputs, artifacts):
        return [copy.deepcopy(binding) for binding in inputs
                if artifacts[binding['source']['hash']].get('type') in
                {'workspace_allocation', 'workspace_authorization'}]

    def node_workspace_draft_chain(self, reference, rows):
        """Authenticate the same qualified task and original raw baseline at every edge."""
        self.api._phase_evidence.validate_ref(reference)
        if reference['hash'] not in rows or rows[reference['hash']][0] != reference:
            raise ValueError('Workspace draft chain lacks an exact committed reference')
        draft = rows[reference['hash']][1]
        node, before = draft['node'], draft['acquisition']['files']
        cursor, seen = reference, set()
        while cursor:
            self.api._phase_evidence.validate_ref(cursor)
            if cursor['hash'] in seen or cursor['hash'] not in rows or rows[cursor['hash']][0] != cursor:
                raise ValueError('Workspace draft chain is cyclic or lacks an exact committed receipt')
            previous = rows[cursor['hash']][1]
            if previous['node'] != node or previous['acquisition']['files'] != before:
                raise ValueError('Workspace draft chain changed task or original baseline')
            seen.add(cursor['hash']); cursor = previous['acquisition'].get('stopped_draft')
        return seen

    def node_workspace_context(self, snapshots, projection, artifacts, *, workspace_target=None):
        """Observe repository facts and bind the explicit workspace adapter.

        The graph supplies all semantic prerequisites. This adapter checks the
        selected allocation and authenticated evidence, then supplies immutable
        raw snapshots to the same pure evaluator.
        """
        ev = self.api._phase_evidence
        states = projection['states']; work = {key: state for key, state in states.items()
            if {'repository_workspace', 'repository_git_workspace'}.intersection(state['contract']['executor']['resources'])}
        head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=self.repo, capture_output=True, text=True, check=True).stdout.strip()
        # A merely-ready legacy sibling must not make a fresh commit-backed
        # task serialize the whole repository. Legacy bytes are observed once
        # durable ownership or evidence actually makes them part of evaluation.
        commit_only_ready = any(
            state['state'] == 'ready'
            and 'repository_workspace' not in state['contract']['executor']['resources']
            for state in states.values())
        legacy_active = any(
            'repository_workspace' in state['contract']['executor']['resources']
            and ((state['state'] == 'ready'
                  and (not commit_only_ready or key == workspace_target))
                 or key in projection.get('leases', {})
                 or (key in projection['current']
                     and not projection['current'][key][1].get('non_applicability')))
            for key, state in work.items())
        legacy_lease = any('files' in lease.get('acquisition', {})
                           for snapshot in snapshots.values()
                           for lease in snapshot['payload']['operational']['leases'])
        legacy_result = any(any(binding['name'] == '__workspace' and
                                artifacts.get(binding['source']['hash'], {}).get('content', {}).get('files') is not None
                                for binding in result['inputs'])
                            for _, result in projection['current'].values())
        legacy_draft = any(snapshot.get('workspace_drafts') for snapshot in snapshots.values())
        commit_only = not (legacy_active or legacy_lease or legacy_result or legacy_draft)
        if commit_only:
            # New tasks run in managed worktrees at HEAD. Uncommitted primary
            # checkout bytes are never their inputs, even when the checkout is
            # dirty. Legacy active work and historical map evidence still need
            # the exact file snapshots until they are resolved.
            actual = committed = {}
        else:
            actual = self.workspace_files()
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
                    if not isinstance(value, dict) or not owner or owner[0][0] != goal or value.get('manifest') != reference: continue
                    if candidate['mode'] != 'identity' or not self.node_authorization_policy_matches(value, blob, owner[1], artifacts) or expected_entry['task'] not in value.get('tasks', []) or value.get('decision') != 'approved': raise ValueError('Workspace authorization policy/task/manifest mismatch')
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
        def historical_authority(node):
            """Authenticate current authority for a stopped task whose prerequisites are blocked."""
            key = ev.task_key(node); state = states.get(key)
            if not state: raise ValueError('Historical workspace task generation is no longer current')
            declared = state['contract']['executor']['authority']; subject = declared['subject']
            if (subject.get('kind') != 'node' or subject.get('goal') not in ('#this', node['goal'])):
                raise ValueError('Historical workspace authority selector is not directly recoverable')
            producer_rows = [row for key, row in projection['current'].items()
                             if key[0] == node['goal'] and key[1] == subject['node'] and key[2] is None]
            if len(producer_rows) != 1: raise ValueError('Historical workspace allocation producer is not uniquely current')
            producer_row = producer_rows[0]
            producer = producer_row[1]; manifest = producer['outputs'].get(declared['output'])
            if not manifest: raise ValueError('Historical workspace allocation output is missing')
            blob = content(manifest)
            if blob.get('type') != 'workspace_allocation': raise ValueError('Historical workspace manifest type differs')
            matches = [entry for entry in blob['content'].get('allocations', {}).values()
                       if entry.get('task') == node]
            if len(matches) != 1: raise ValueError('Historical workspace task has no unique current allocation')
            entry = matches[0]
            self.node_workspace_paths(entry['owned']); self.node_workspace_paths(entry['consumed'], consumed=True)
            approvals = []
            for output_hash, (owner_key, result) in current_outputs.items():
                candidate = artifacts[output_hash]
                if candidate.get('type') != 'workspace_authorization': continue
                value = candidate.get('content')
                reference = next((ref for ref in result['outputs'].values() if ref['hash'] == output_hash), None)
                if (not isinstance(value, dict) or not reference or value.get('manifest') != manifest or
                        node not in value.get('tasks', []) or value.get('decision') != 'approved' or
                        not self.node_authorization_policy_matches(value, candidate, result, artifacts) or
                        not any(binding['source'] == manifest and binding['mode'] == 'identity' for binding in result['inputs'])):
                    continue
                approvals.append((reference, result, states[owner_key]))
            roots = [row for row in approvals if row[2]['contract']['executor']['role'] == 'root'
                     and row[1]['executor'] == (self.runtime or {}).get('root_id')]
            reviewers = [row for row in approvals if row[1]['executor'] != producer['executor']
                         and row[2]['contract']['independent_of']]
            if len(roots) != 1 or len(reviewers) != 1 or roots[0][0] == reviewers[0][0]:
                raise ValueError('Historical workspace requires fresh independent authorization and root approval')
            if snapshots[node['goal']]['envelope']['parent'] is not None:
                raise ValueError('Historical workspace recovery with parent authority requires current task readiness')
            return {'allocation': manifest, 'authorization': reviewers[0][0], 'approval': roots[0][0], 'entry': entry}
        def raw(acquisition):
            required = {'git_commit', 'workspace_digest', 'input_hash', 'checkout_overrides', 'files', 'inputs', 'resolutions', 'contract'}
            if not isinstance(acquisition, dict) or not required <= set(acquisition): raise ValueError('Workspace acquisition raw pins are missing or partial')
            files = acquisition['files']; overrides = acquisition['checkout_overrides']
            if not isinstance(files, dict) or digest(files) != acquisition['workspace_digest'] or not isinstance(overrides, dict): raise ValueError('Workspace acquisition raw snapshot mismatch')
            git = self.git_files(acquisition['git_commit'])
            for path, value in overrides.items():
                self.node_workspace_paths([path])
                if path not in git or not re.fullmatch(r'sha256:[0-9a-f]{64}', str(value)) or files.get(path) != value or git[path] == value: raise ValueError('Acquisition checkout overrides are invalid')
            # A declared absent path is retained in the immutable acquisition,
            # but it is not a file in the connected workspace topology.
            return {path: value for path, value in files.items() if value != 'missing'}
        candidates = []
        for result_ref, result in all_results:
            key = ev.task_key(result['node'])
            if key not in work: continue
            if 'repository_git_workspace' in states[key]['contract']['executor']['resources']:
                continue
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
        drafts = {}; draft_rows = {}; draft_errors = {}; consumed_drafts = set()
        for snapshot in snapshots.values():
            for reference, draft in snapshot.get('workspace_drafts', []):
                draft_rows[reference['hash']] = (reference, draft)
                if not draft.get('continuity_only'):
                    drafts[ev.task_key(draft['node'])] = (reference, draft)
        # A published candidate consumes its linked operational chain, even if
        # its independent review is still pending. It is not itself acceptance.
        for row in candidates:
            if 'error' in row: continue
            cursor = row['data']['acquisition'].get('stopped_draft'); seen = set()
            while cursor:
                if cursor['hash'] in seen or cursor['hash'] not in draft_rows:
                    raise ValueError('Workspace draft provenance is cyclic or lacks a committed receipt')
                seen.add(cursor['hash']); consumed_drafts.add(cursor['hash'])
                cursor = draft_rows[cursor['hash']][1]['acquisition'].get('stopped_draft')
        valid_drafts = []; valid_continuity = []
        for reference, draft in draft_rows.values():
            key = ev.task_key(draft['node'])
            try:
                if key not in work: raise ValueError('Workspace draft task generation is no longer current')
                state = work[key]
                grant = historical_authority(draft['node']) if draft.get('continuity_only') else authority(state)
                acquisition = draft['acquisition']
                before = raw(acquisition); after = draft['files']
                if draft.get('continuity_only'):
                    expected_authority = {name: grant[name] for name in ('allocation', 'authorization', 'approval')}
                    delta = {p: after.get(p, 'missing') for p in before.keys() | after.keys()
                             if before.get(p, 'missing') != after.get(p, 'missing')}
                    if (draft.get('historical_recovery') is None or draft['policy'] != self.node_evidence_policy() or
                            draft['authority'] != expected_authority or digest(after) != draft['workspace'] or
                            delta != draft['outputs'] or set(delta) - set(grant['entry']['owned'])):
                        raise ValueError('Historical workspace continuity authority/snapshot differs')
                    edges.append((before, after)); valid_continuity.append((reference, draft))
                    continue
                declared = lambda inputs: [binding for binding in inputs if binding['name'] != '__workspace']
                resolutions = lambda rows: [{k: row[k] for k in ('location', 'selector', 'targets')} for row in rows]
                expected_authority = {**{k: grant[k] for k in ('allocation', 'authorization', 'approval')},
                    'inputs': self.node_workspace_authority_inputs(state['inputs'], artifacts)}
                if (draft['policy'] != self.node_evidence_policy() or draft['authority'] != expected_authority or
                    acquisition['contract'] != state['contract_hash'] or
                    declared(acquisition['inputs']) != declared(state['inputs']) or
                    resolutions(acquisition['resolutions']) != resolutions(state['resolutions'])):
                    raise ValueError('Workspace draft current authority/input/contract changed')
                delta = {p: after.get(p, 'missing') for p in before.keys() | after.keys()
                         if before.get(p, 'missing') != after.get(p, 'missing')}
                if (digest(after) != draft['workspace'] or delta != draft['outputs'] or
                    set(delta) - set(grant['entry']['owned'])):
                    raise ValueError('Workspace draft snapshot/owned delta differs')
                cursor = acquisition.get('stopped_draft'); seen = {reference['hash']}
                while cursor:
                    if cursor['hash'] in seen or cursor['hash'] not in draft_rows:
                        raise ValueError('Workspace draft chain lacks a committed receipt or contains a cycle')
                    seen.add(cursor['hash']); previous = draft_rows[cursor['hash']][1]
                    if previous['node'] != draft['node'] or previous['acquisition']['files'] != before:
                        raise ValueError('Workspace draft chain changed task or original baseline')
                    cursor = previous['acquisition'].get('stopped_draft')
                edges.append((before, after)); valid_drafts.append(draft)
            except (ValueError, KeyError, subprocess.SubprocessError) as exc:
                draft_errors[reference['hash']] = str(exc)
        retired_drafts = set().union(*(snapshot.get('retired_workspace_drafts', set()) for snapshot in snapshots.values()))
        drafts = {key: row for key, row in drafts.items() if row[0]['hash'] not in consumed_drafts | retired_drafts}
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
        for draft in valid_drafts:
            acquisition = draft['acquisition']; git = self.git_files(acquisition['git_commit'])
            for path, raw_hash in acquisition['checkout_overrides'].items(): clean_pairs[(path, raw_hash)] = git[path]
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
        def historical_draft_recovery(state):
            """Locate one committed legacy recovery whose stopped delta can be rebound."""
            number = state['node']['goal']; snapshot = snapshots[number]
            index = self.artifact_index(number)
            current_receipts = {row['result']['hash'] for row in snapshot['payload']['operational']['receipts']}
            found = []
            for record in index.envelopes:
                context = record.get('context') or {}; response_ref = context.get('response')
                if (not isinstance(response_ref, dict) or response_ref.get('hash') not in current_receipts
                        or context.get('workspace_draft')):
                    continue
                try: response = index.resolve(response_ref['hash'])[0]
                except ValueError: continue
                if response.get('next_steps') != [{'kind': 'checkpoint', 'goal': number}]: continue
                source_envelope = context.get('source_envelope') or {}
                target_envelope = context.get('target_envelope') or {}
                if (source_envelope.get('issue') != number or target_envelope.get('issue') != number
                        or target_envelope.get('revision') != source_envelope.get('revision', -1) + 1):
                    continue
                try:
                    source = index.resolve(source_envelope['payload']['hash'])[0]
                    target = index.resolve(target_envelope['payload']['hash'])[0]
                except (ValueError, KeyError): continue
                target_tokens = {row.get('token') for row in target.get('operational', {}).get('leases', [])}
                leases = [row for row in source.get('operational', {}).get('leases', [])
                          if row.get('token') not in target_tokens]
                if len(leases) != 1: continue
                lease = leases[0]
                if context.get('root') != lease.get('owner') or not lease.get('worker'):
                    continue
                try: source_grant = historical_authority(lease['node'])
                except (ValueError, KeyError): continue
                source_receipts = {row['result']['hash']: row['result'] for row in source['operational']['receipts']}
                starts = []
                for started_record in index.envelopes:
                    started_context = started_record.get('context') or {}
                    started_ref = started_context.get('response')
                    if (not started_context.get('acquisition') or
                            (started_context.get('ownership') or {}).get('token') != lease.get('token') or
                            not isinstance(started_ref, dict) or started_ref.get('hash') not in source_receipts):
                        continue
                    try: started = index.resolve(started_ref['hash'])[0]
                    except ValueError: continue
                    pins = [step.get('lease') for step in started.get('next_steps', [])
                            if step.get('bind') and step.get('lease', {}).get('token') == lease.get('token')]
                    if len(pins) == 1 and pins[0].get('acquisition') == lease.get('acquisition'):
                        starts.append(started_ref)
                if len(starts) != 1: continue
                try: before = raw(lease['acquisition'])
                except (ValueError, KeyError, subprocess.SubprocessError): continue
                delta = {path: actual.get(path, 'missing') for path in before.keys() | actual.keys()
                         if before.get(path, 'missing') != actual.get(path, 'missing')}
                if not delta or set(delta) - set(source_grant['entry']['owned']): continue
                found.append({
                    'recovery_request_id': context.get('request_id'),
                    'recovery_request_hash': context.get('request_hash'),
                    'recovery_result': response_ref,
                    'source_payload': source_envelope['payload'],
                    'acquisition_receipt': starts[0],
                    'lease': lease,
                    'source_acquisition': copy.deepcopy(lease['acquisition']),
                    'expected_workspace': digest(actual),
                    'expected_delta': delta,
                    'files': copy.deepcopy(actual),
                    'authority': {name: source_grant[name] for name in ('allocation', 'authorization', 'approval')},
                })
            if len(found) > 1:
                raise ValueError('Multiple historical stopped recoveries match this current workspace; select an exact recovery result')
            return found[0] if found else None
        def checked_git_lease(key, state, grant, lease):
            receipts = [content(reference) for token, reference in snapshots[key[0]]['acquisition_receipts'].items()
                        if token == lease['token']]
            pinned = [step['lease']['acquisition'] for receipt in receipts for step in receipt.get('next_steps', [])
                      if step.get('lease', {}).get('token') == lease['token'] and step['lease'].get('acquisition')]
            if pinned != [lease['acquisition']] or lease['acquisition'].get('input_hash') != lease['fingerprint']:
                raise ValueError('Git workspace acquisition differs from immutable start receipt')
            base = lease['acquisition'].get('git_commit')
            observed = managed_worktrees.inspect_attempt_worktree(
                self.repo, goal=lease['node']['goal'], node=lease['node']['node'],
                attempt=lease['attempt'])
            # A dirty or absent local attempt remains recoverable as owned work.
            # Submission independently requires a clean exact commit.
            if observed['status'] == 'clean' and observed['head'] != base:
                git_phase_state.validate_checkpoint(Path(observed['path']),
                    base_commit=base, result_commit=observed['head'],
                    owned_paths=grant['entry']['owned'])
            return base
        def checked_git_proof(state, grant, result):
            sources = {value['provenance']['source']['hash']: value['provenance']['source']
                       for ref in result['outputs'].values()
                       if (value := content(ref)).get('provenance', {}).get('source')}
            if len(sources) != 1:
                raise ValueError('Git phase result has no unique workspace proof')
            proof = content(next(iter(sources.values())))
            acquisition = proof.get('acquisition', {})
            checkpoint = proof.get('checkpoint', {})
            base, result_commit = acquisition.get('git_commit'), checkpoint.get('result_commit')
            expected_ref = (f"refs/heads/zzzops/attempts/{result['node']['goal']}/"
                            f"{result['node']['node']}/{result['attempt']}")
            if (proof.get('kind') != 'git_phase_proof' or proof.get('node') != result['node']
                    or proof.get('actor') != result['executor'] or proof.get('input_hash') != acquisition.get('input_hash')
                    or proof.get('acquisition_hash') != digest(acquisition)
                    or proof.get('scope') != digest(grant['entry'])
                    or proof.get('retained_ref') != expected_ref
                    or checkpoint.get('base_commit') != base
                    or checkpoint != git_phase_state.validate_checkpoint(self.repo,
                        base_commit=base, result_commit=result_commit,
                        owned_paths=grant['entry']['owned'], require_clean_worktree=False)):
                raise ValueError('Git phase result/proof or reviewed scope differs')
            git_phase_state.verify_attempt_ref(self.repo, remote='origin',
                ref=proof['retained_ref'], commit=result_commit)
            return proof
        git_edges = {}
        def connected_git_head(start, goal):
            start_tree = subprocess.run(['git', 'rev-parse', start + '^{tree}'], cwd=self.repo,
                                        capture_output=True, text=True, check=True).stdout.strip()
            head_tree = subprocess.run(['git', 'rev-parse', head + '^{tree}'], cwd=self.repo,
                                       capture_output=True, text=True, check=True).stdout.strip()
            if start_tree == head_tree: return True
            if goal not in git_edges:
                edges = []
                for other_key, other in work.items():
                    if (other_key[0] != goal
                            or 'repository_git_workspace' not in other['contract']['executor']['resources']
                            or other['state'] == 'blocked'):
                        continue
                    try:
                        other_grant = authority(other)
                        other_lease = next((l for l in snapshots[other_key[0]]['payload']['operational']['leases']
                                            if ev.task_key(l['node']) == other_key), None)
                        if other_lease:
                            predecessor = checked_git_lease(other_key, other, other_grant, other_lease)
                            if predecessor != head:
                                checkpoint = git_phase_state.validate_checkpoint(self.repo,
                                    base_commit=predecessor, result_commit=head,
                                    owned_paths=other_grant['entry']['owned'])
                                edges.append((checkpoint['base_tree'], checkpoint['result_tree']))
                        elif other_key in projection['current']:
                            proof = checked_git_proof(other, other_grant, projection['current'][other_key][1])
                            checkpoint = proof['checkpoint']
                            edges.append((checkpoint['base_tree'], checkpoint['result_tree']))
                    except (ValueError, KeyError, subprocess.SubprocessError):
                        continue
                admitted_subjects = {subject['hash']
                    for obligation in projection['obligations'].values()
                    if obligation.get('admission') and obligation.get('applicability') == 'applicable'
                    for subject in obligation.get('content', {}).get('subjects', [])}
                for _, result in all_results:
                    other_key = ev.task_key(result['node'])
                    if (other_key[0] != goal or other_key not in work or not admitted_subjects.intersection(
                            value['hash'] for value in result['outputs'].values())):
                        continue
                    other = work[other_key]
                    try:
                        proof = checked_git_proof(other, authority(other), result)
                        checkpoint = proof['checkpoint']
                        edges.append((checkpoint['base_tree'], checkpoint['result_tree']))
                    except (ValueError, KeyError, subprocess.SubprocessError):
                        continue
                if admitted_subjects:
                    # A corrected test may be based on an implementation whose
                    # evidence became stale when the test finding was admitted.
                    # Its retained Result still proves an exact Git edge; use
                    # it for topology only, never as current task authority.
                    for _, result in all_results:
                        other_key = ev.task_key(result['node'])
                        other = states.get(other_key)
                        if (other is None or other_key[0] != goal
                                or 'repository_git_workspace' not in other['contract']['executor']['resources']):
                            continue
                        try:
                            proof = checked_git_proof(other, historical_authority(result['node']), result)
                            checkpoint = proof['checkpoint']
                            edges.append((checkpoint['base_tree'], checkpoint['result_tree']))
                        except (ValueError, KeyError, subprocess.SubprocessError):
                            continue
                git_edges[goal] = edges
            # Walk only authenticated Git phase edges out of the primary base.
            # The primary checkout itself does not advance for a draft stack.
            pending, seen = [head_tree], set()
            while pending:
                tree = pending.pop()
                if tree == start_tree: return True
                if tree in seen: continue
                seen.add(tree)
                pending.extend(after for before, after in git_edges[goal] if before == tree)
            return False
        def depends_on(consumer, ancestor):
            visited = set()
            def walk(key):
                if key in visited or key not in states:
                    return False
                visited.add(key)
                parents = [ev.task_key(identity) for identity in
                           (states[key]['required_dependencies'] + states[key]['required_parent_gates'])]
                return ancestor in parents or any(walk(parent) for parent in parents)
            return walk(consumer)
        def reviewed_predecessor(consumer, ancestor):
            """Require a current independent node on a policy dependency path."""
            visited = set()
            def walk(key, independent):
                marker = (key, independent)
                if marker in visited or key not in states:
                    return False
                visited.add(marker)
                contract = states[key]['contract']
                independent = independent or (key in projection['current'] and any(
                    selector.get('kind') == 'node'
                    and selector.get('node') == states[ancestor]['node']['node']
                    and selector.get('goal') in ('#this', states[ancestor]['node']['goal'])
                    for selector in contract.get('independent_of', [])))
                parents = [ev.task_key(identity) for identity in
                           (states[key]['required_dependencies'] + states[key]['required_parent_gates'])]
                return (ancestor in parents and independent) or any(
                    walk(parent, independent) for parent in parents)
            return walk(consumer, False)
        def predecessor_commit(key):
            correction_subjects = {
                subject['hash'] for obligation in projection['obligations'].values()
                if (obligation.get('admission') and obligation.get('applicability') == 'applicable'
                    and obligation.get('content', {}).get('target', {}).get('subject', {}).get('goal') == key[0]
                    and obligation['content']['target']['subject'].get('node') == key[1])
                for subject in obligation['content']['subjects']}
            if correction_subjects and key not in projection['current']:
                corrected = []
                for _, result in all_results:
                    if (ev.task_key(result['node']) == key
                            and correction_subjects.intersection(
                                value['hash'] for value in result['outputs'].values())):
                        proof = checked_git_proof(states[key], authority(states[key]), result)
                        corrected.append(proof['checkpoint']['result_commit'])
                latest = [candidate for candidate in corrected if all(
                    subprocess.run(['git', 'merge-base', '--is-ancestor', other, candidate],
                                   cwd=self.repo, capture_output=True).returncode == 0
                    for other in corrected)]
                if len(latest) != 1:
                    raise ValueError('Admitted correction attempts have no unique retained Git tip')
                correction_tip = latest[0]
                # A late finding can reopen tests after implementation was
                # recorded. The implementation is now stale as evidence, but
                # remains the exact code that the corrected RED test must run
                # against. Follow only authenticated recorded Git attempts on
                # this goal's ancestry line; divergent attempts require a
                # coordinator decision instead of an arbitrary branch choice.
                descendants = [correction_tip]
                for _, result in all_results:
                    other_key = ev.task_key(result['node'])
                    other = states.get(other_key)
                    if (other_key[0] != key[0] or other is None
                            or 'repository_git_workspace' not in other['contract']['executor']['resources']):
                        continue
                    try:
                        candidate = checked_git_proof(other, historical_authority(result['node']), result)['checkpoint']['result_commit']
                    except (ValueError, KeyError, subprocess.SubprocessError):
                        continue
                    if subprocess.run(['git', 'merge-base', '--is-ancestor', correction_tip, candidate],
                                      cwd=self.repo, capture_output=True).returncode == 0:
                        descendants.append(candidate)
                tips = [candidate for candidate in set(descendants) if all(
                    subprocess.run(['git', 'merge-base', '--is-ancestor', other, candidate],
                                   cwd=self.repo, capture_output=True).returncode == 0
                    for other in descendants)]
                if len(tips) != 1:
                    raise ValueError('Recorded Git correction descendants have no unique stack tip')
                if subprocess.run(['git', 'merge-base', '--is-ancestor', head, tips[0]],
                                  cwd=self.repo, capture_output=True).returncode:
                    raise ValueError('Corrected Git attempt is disconnected from the current base')
                return tips[0]
            candidates = []
            for other_key, other in work.items():
                if (other_key == key or other_key not in projection['current']
                        or 'repository_git_workspace' not in other['contract']['executor']['resources']
                        or not depends_on(key, other_key)
                        or not reviewed_predecessor(key, other_key)):
                    continue
                proof = checked_git_proof(other, authority(other),
                                          projection['current'][other_key][1])
                candidates.append(proof['checkpoint']['result_commit'])
            if not candidates:
                return head
            latest = [candidate for candidate in candidates if all(
                subprocess.run(['git', 'merge-base', '--is-ancestor', other, candidate],
                               cwd=self.repo, capture_output=True).returncode == 0
                for other in candidates)]
            if len(latest) != 1:
                raise ValueError('Reviewed Git predecessor commits do not form one exact stack')
            if not connected_git_head(latest[0], key[0]):
                raise ValueError('Reviewed Git predecessor is disconnected from the current base')
            return latest[0]
        contexts = {}; migrations = {}
        for key, state in work.items():
            if state['state'] == 'blocked':
                # Preserve the preliminary semantic blocker. Omitting this key
                # makes the second projection replace it with the misleading
                # generic "workspace unavailable" fallback.
                contexts[key] = {'error': state.get('reason', 'Workspace task is blocked')}
                continue
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
                if 'repository_git_workspace' in state['contract']['executor']['resources']:
                    if actual != committed:
                        raise ValueError('Git workspace acquisition requires a clean committed worktree')
                    lease = next((l for l in snapshots[key[0]]['payload']['operational']['leases'] if ev.task_key(l['node']) == key), None)
                    base = lease['acquisition'].get('git_commit') if lease else predecessor_commit(key)
                    if lease:
                        base = checked_git_lease(key, state, grant, lease)
                    elif key in projection['current']:
                        _, result = projection['current'][key]
                        proof = checked_git_proof(state, grant, result)
                        base = proof['checkpoint']['base_commit']
                        if not connected_git_head(proof['checkpoint']['result_commit'], key[0]):
                            raise ValueError('Git phase result is disconnected from the current managed head')
                    binding = remember({'type': 'workspace_snapshot', 'content': {
                        'git_commit': base, **{name: grant[name] for name in ('allocation', 'authorization', 'approval')},
                        **({'migration': migration} if migration is not None else {})}, 'producer': None,
                        'provenance': {'actor': 'host', 'source': None, 'policy': self.node_evidence_policy()}})
                    contexts[key] = {'binding': binding, 'acquisition': {'git_commit': base},
                                     'git_workspace': True, **grant}
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
                elif key in drafts:
                    reference, draft = drafts[key]
                    if reference['hash'] in draft_errors: raise ValueError(draft_errors[reference['hash']])
                    if actual != draft['files']:
                        raise ValueError('Stopped workspace draft changed without an owner; restore the exact stopped snapshot before recovery')
                    acquisition = copy.deepcopy(draft['acquisition']); baseline = raw(acquisition)
                    acquisition['stopped_draft'] = reference
                    if head != acquisition['git_commit']:
                        original_git = self.git_files(acquisition['git_commit'])
                        if any(original_git.get(p, 'missing') != committed.get(p, 'missing')
                               for p in original_git.keys() | committed.keys() if p not in grant['entry']['owned']):
                            raise ValueError('Stopped draft Git baseline changed outside owned scope')
                elif prior and current_ref == prior['result']:
                    if 'error' in prior: raise ValueError(prior['error'])
                    if connected(prior['after']):
                        acquisition = prior['data']['acquisition']; baseline = prior['before']
                    else:
                        # A valid completed proof remains immutable history, but
                        # does not pin a later clean integration forever.  Bind
                        # the actual current commit/raw checkout as fresh input;
                        # dirty or mixed snapshots still fail the ordinary clean
                        # checkout gate below.
                        baseline = actual
                        acquisition = {'git_commit': head, 'workspace_digest': digest(baseline),
                                       'checkout_overrides': {}}
                        try:
                            acquisition['checkout_overrides'] = self.clean_checkout_overrides(
                                head, committed, actual)
                        except ValueError:
                            raise ValueError('Completed workspace proof is disconnected and the current checkout is not a clean committed baseline') from None
                else:
                    baseline = actual
                    acquisition = {'git_commit': head, 'workspace_digest': digest(baseline), 'checkout_overrides': {}}
                    try: acquisition['checkout_overrides'] = self.clean_checkout_overrides(head, committed, actual)
                    except ValueError:
                        anchors = [row for row in candidates if 'error' not in row and row['reviews'] and connected(row['after'], accepted_only=True)]
                        continuity = [(reference, draft) for reference, draft in valid_continuity
                                      if draft['files'] == actual]
                        if anchors:
                            anchor = anchors[-1]
                            acquisition['checkout_overrides'] = {path: value for path, value in anchor['data']['acquisition']['checkout_overrides'].items()
                                                                 if baseline.get(path) == value}
                        elif continuity:
                            acquisition['baseline_drafts'] = [reference for reference, _draft in continuity]
                            source = continuity[-1][1]['source_acquisition']
                            acquisition['checkout_overrides'] = {path: value for path, value in source['checkout_overrides'].items()
                                                                 if baseline.get(path) == value}
                        else:
                            raise ValueError('Workspace acquisition requires clean Git or exact reviewed connected output baseline') from None
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
                if not lease and key not in drafts and not (prior and current_ref == prior['result']):
                    reachable, pending_refs = set(), [item['source'] for item in state['inputs']]
                    # Prerequisites remain currentness gates, but their exact
                    # accepted proof ancestry is acquisition provenance. This
                    # does not turn their Result IDs into semantic input hashes.
                    pending_refs.extend(projection['current'][parent][0] for parent in state.get('prerequisites', []) if parent in projection['current'])
                    def refs(value):
                        if isinstance(value, dict):
                            if set(value) == {'hash', 'uri'} and isinstance(value['hash'], str) and isinstance(value['uri'], str): yield value
                            else:
                                for name, child in value.items():
                                    if value.get('type') == 'workspace_draft' and name == 'source_payload': continue
                                    yield from refs(child)
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
                pinned_binding = next((item['source'] for item in acquisition.get('inputs', [])
                                       if item.get('name') == '__workspace'), None) if lease else None
                reuse_result_binding = (prior is not None and 'error' not in prior
                                        and current_ref == prior['result']
                                        and connected(prior['after']))
                result_binding = next((item['source'] for item in projection['current'].get(
                    key, (None, {'inputs': []}))[1]['inputs'] if item.get('name') == '__workspace'), None) if reuse_result_binding else None
                if (result_binding is not None
                        and (content(result_binding).get('content', {}).get('migration') != migration
                             or content(result_binding).get('provenance', {}).get('policy')
                             != self.node_evidence_policy())):
                    result_binding = None
                binding = pinned_binding or result_binding or remember({'type': 'workspace_snapshot', 'content': {'files': baseline, **{k: grant[k] for k in ('allocation', 'authorization', 'approval')}, **({'migration': migration} if migration is not None else {})}, 'producer': None, 'provenance': {'actor': 'host', 'source': None, 'policy': self.node_evidence_policy()}})
                contexts[key] = {'binding': binding, 'files': baseline, 'acquisition': acquisition, **grant}
            except (ValueError, KeyError, subprocess.SubprocessError) as exc:
                retirement = None
                if key in drafts and not any(snapshot['payload']['operational']['leases'] for snapshot in snapshots.values()):
                    reference, draft = drafts[key]
                    try:
                        grant = authority(state)
                        expected_authority = {**{name: grant[name] for name in ('allocation', 'authorization', 'approval')},
                            'inputs': self.node_workspace_authority_inputs(state['inputs'], artifacts)}
                        # Retirement discards operational selection, never adopts
                        # the old delta or its authority. authority(state) above
                        # requires independent review and root approval of the
                        # exact current grant, including any replacement scope.
                        # Fresh acquisition remains fenced by that current grant.
                        if (not draft.get('continuity_only') and draft['policy'] == self.node_evidence_policy()
                                and draft_errors.get(reference['hash']) == 'Workspace draft current authority/input/contract changed'):
                            self.node_workspace_draft_chain(reference, draft_rows)
                            overrides = self.clean_checkout_overrides(head, committed, actual)
                            subject = {'policy': self.node_evidence_policy(), 'authority': expected_authority,
                                       'contract': state['contract_hash'],
                                       'inputs': [row for row in state['inputs'] if row['name'] != '__workspace'],
                                       'resolutions': [{name: row[name] for name in ('location', 'selector', 'targets')}
                                                       for row in state['resolutions']],
                                       'git_commit': head, 'workspace': digest(actual), 'checkout_overrides': overrides}
                            retirement = {'draft': reference, 'subject': digest(subject)}
                    except (ValueError, KeyError, subprocess.SubprocessError): pass
                recovery = None
                if str(exc) == 'Workspace acquisition requires clean Git or exact reviewed connected output baseline':
                    try: recovery = historical_draft_recovery(state)
                    except (ValueError, KeyError, subprocess.SubprocessError) as recovery_exc:
                        contexts[key] = {'error': 'Workspace authority/acquisition: ' + str(recovery_exc)}
                        continue
                contexts[key] = {'error': 'Workspace authority/acquisition: ' + str(exc),
                                 **({'stale_draft_retirement': retirement} if retirement else {}),
                                 **({'historical_recovery': recovery} if recovery else {})}
        allocated_paths = set()
        for state in work.values():
            try:
                entry = authority(state)['entry']; allocated_paths.update(entry['owned']); allocated_paths.update(entry['consumed'])
            except (ValueError, KeyError): pass
        tree_cache = {}
        def same_tree(commit):
            if not isinstance(commit, str) or not re.fullmatch(r'[0-9a-f]{40}', commit):
                return False
            for oid in (commit, head):
                if oid not in tree_cache:
                    observed = subprocess.run(['git', 'rev-parse', '--verify', oid + '^{tree}'],
                                              cwd=self.repo, capture_output=True, text=True)
                    tree_cache[oid] = observed.stdout.strip() if observed.returncode == 0 else None
            return tree_cache[commit] is not None and tree_cache[commit] == tree_cache[head]
        for key, state in states.items():
            if key in work or state['state'] == 'blocked': continue
            if (state['contract']['executor']['role'] == 'root'
                    and any(slot.get('type') == 'merge_observation'
                            for slot in state['contract'].get('outputs', {}).values())):
                # This terminal task observes GitHub's already merged commit.
                # It reads no repository files, so a managed checkout would
                # add a mutable input after the irreversible provider effect.
                binding = remember({'type': 'workspace_snapshot',
                    'content': {'git_commit': head}, 'producer': None,
                    'provenance': {'actor': 'host', 'source': None,
                                   'policy': self.node_evidence_policy()}})
                contexts[key] = {'binding': binding, 'acquisition': {}, 'readonly': True}
                continue
            lease = next((item for item in snapshots[key[0]]['payload']['operational']['leases'] if ev.task_key(item['node']) == key), None)
            previous = projection['current'].get(key, (None, None))[1]
            previous_binding = next((item for item in previous['inputs'] if item['name'] == '__workspace'), None) if previous else None
            previous_content = content(previous_binding['source'])['content'] if previous_binding else None
            # A clean Git tree has a finite, immutable identity. New read-only
            # acquisitions bind that commit instead of copying every file hash
            # into the workspace artifact, lease, receipt and provider comment.
            # Keep historical map-based acquisitions readable until migrated.
            if actual == committed and not (lease and 'files' in lease['acquisition']) and not (previous_content and 'files' in previous_content):
                pinned = lease['acquisition'].get('read_commit') if lease else None
                if lease and not same_tree(pinned):
                    contexts[key] = {'error': 'Read-only task Git commit changed after acquisition'}
                    continue
                if lease and lease.get('worker') is not None:
                    observed = managed_worktrees.inspect_attempt_worktree(self.repo,
                        goal=key[0], node=state['node']['node'], attempt=lease['attempt'])
                    if observed['status'] != 'clean' or observed['head'] != pinned:
                        contexts[key] = {'error': 'Read-only managed worktree changed; replay the exact start or inspect its local files'}
                        continue
                historical = previous_content.get('git_commit') if previous_content else None
                baseline_commit = pinned if lease else historical if same_tree(historical) else head
                binding = remember({'type': 'workspace_snapshot', 'content': {'git_commit': baseline_commit}, 'producer': None,
                                    'provenance': {'actor': 'host', 'source': None, 'policy': self.node_evidence_policy()}})
                contexts[key] = {'binding': binding, 'acquisition': {'read_commit': baseline_commit}, 'readonly': True}
                continue
            if (lease and 'read_commit' in lease['acquisition']
                    or previous_content and 'git_commit' in previous_content and 'files' not in previous_content):
                contexts[key] = {'error': 'Read-only Git task workspace changed outside empty write scope'}
                continue
            baseline = read_actual
            if lease and 'files' in lease['acquisition']:
                baseline = lease['acquisition']['files']
                live_pin = lease['acquisition'].get('read_files')
                if ((live_pin is not None and live_pin != actual) or
                        (live_pin is None and baseline != read_actual)):
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
                                'provenance': {'actor': 'host', 'source': None, 'policy': self.node_evidence_policy()}})
            contexts[key] = {'binding': binding, 'files': baseline,
                             'acquisition': {'read_files': copy.deepcopy(actual)}, 'readonly': True}
        return contexts

    @contextmanager
    def node_verification_claim(self, snapshot, lease):
        git_dir = Path(subprocess.run(['git', 'rev-parse', '--absolute-git-dir'], cwd=self.repo,
                                      capture_output=True, text=True, check=True).stdout.strip())
        directory = git_dir / 'zzzops' / 'verification' / str(snapshot['number'])
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = directory / ('lease-' + lease['token'] + '.lock')
        local = _VERIFICATION_LOCKS.setdefault(str(path), threading.Lock())
        if not local.acquire(blocking=False):
            raise VerificationUncertain('Another verification invocation owns this lease journal')
        handle = None
        try:
            handle = path.open('a+b')
            if fcntl is not None:
                try: fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as exc:
                    raise VerificationUncertain('Another verification process owns this lease journal') from exc
            else:  # pragma: no cover - exercised on Windows hosts
                if not handle.read(1):
                    handle.write(b'0'); handle.flush()
                handle.seek(0)
                try: msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError as exc:
                    raise VerificationUncertain('Another verification process owns this lease journal') from exc
            yield
        finally:
            if handle is not None and fcntl is not None:
                try: fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                except OSError: pass
            elif handle is not None:  # pragma: no cover - exercised on Windows hosts
                try:
                    handle.seek(0); msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError: pass
            if handle is not None:
                handle.close()
            local.release()

    def node_verification_commands(self, snapshot, lease, request, commands, before, *, reuse_only=False,
                                   working_directory=None):
        with self.node_verification_claim(snapshot, lease):
            return self.node_verification_commands_claimed(
                snapshot, lease, request, commands, before, reuse_only=reuse_only,
                working_directory=working_directory)

    def node_verification_commands_claimed(self, snapshot, lease, request, commands, before, *, reuse_only=False,
                                           working_directory=None):
        """Reuse host-observed command outcomes across pre-publication failures."""
        if not commands: return []
        command_repo = Path(working_directory or self.repo).resolve()
        git_dir = Path(subprocess.run(['git', 'rev-parse', '--absolute-git-dir'], cwd=self.repo,
                                      capture_output=True, text=True, check=True).stdout.strip())
        directory = git_dir / 'zzzops' / 'verification' / str(snapshot['number'])
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = directory / (digest(request['request_id'])[7:] + '.json')
        identity = {'repository': self.repository, 'goal': snapshot['number'], 'request': digest(request),
                    'lease': lease['token'], 'actor': lease['worker'],
                    'acquisition': digest(lease['acquisition']), 'workspace': digest(before),
                    'directory': str(command_repo), 'environment': digest(dict(os.environ)),
                    'commands': commands}
        def read(candidate):
            value = json.loads(candidate.read_text(encoding='utf-8'))
            if set(value) != {'hash', 'record'} or digest(value['record']) != value['hash']:
                raise ValueError('Verification journal integrity changed; inspect original execution before retry')
            return value['record']
        def write(value):
            temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
            descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            try:
                with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
                    json.dump({'hash': digest(value), 'record': value}, handle, sort_keys=True)
                    handle.flush(); os.fsync(handle.fileno())
                os.replace(temporary, path)
                if hasattr(os, 'O_DIRECTORY'):
                    directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
                    try: os.fsync(directory_fd)
                    finally: os.close(directory_fd)
            finally:
                temporary.unlink(missing_ok=True)
        journal = read(path) if path.exists() else {'identity': identity, 'status': 'prepared', 'results': []}
        if journal['identity'] != identity:
            raise ValueError('Verification request/workspace/acquisition/environment identity changed; use original bytes or a corrected new request')
        # Unknown command liveness cannot be bypassed with another request ID.
        for candidate in directory.glob('*.json'):
            existing = read(candidate)
            if existing['identity']['lease'] == lease['token'] and existing['status'] == 'running':
                raise VerificationUncertain('Verification completion is unknown; inspect the exact worker and verifier before observed-stop recovery. Journal: ' + str(candidate))
        results = journal['results']
        if journal['status'] not in {'prepared', 'complete'} or [row['command'] for row in results] != commands[:len(results)] or len(results) > len(commands):
            raise ValueError('Verification journal command coverage is invalid')
        for record in results:
            if hashlib.sha256(Path(record['log']).read_bytes()).hexdigest() != record['log_hash']:
                raise ValueError('Recorded verification log changed')
        if journal['status'] == 'complete': return results
        if reuse_only:
            raise ValueError('Completed verification journal disappeared before finalize; commands were not rerun')
        logs = self.repo / '.zzzops' / 'diagnostics'; logs.mkdir(parents=True, exist_ok=True)
        for i in range(len(results), len(commands)):
            command = commands[i]
            log = logs / f'node-{lease["token"]}-{path.stem}-{i}.log'
            journal['status'] = 'running'
            journal['active_command'] = {'index': i, 'command': command, 'log': str(log)}
            write(journal)
            started = time.monotonic()
            timed_out = False
            execution_error = None
            with log.open('w') as output:
                try:
                    process = subprocess.run(command, cwd=command_repo, stdout=output, stderr=subprocess.STDOUT,
                                             timeout=request.get('verification_timeout_seconds', 300), check=False)
                    exit_code = process.returncode
                except subprocess.TimeoutExpired:
                    # subprocess.run has killed and waited for the direct child.
                    # A timeout is failed evidence, never an inferred success.
                    timed_out = True; exit_code = None
                except OSError as exc:
                    execution_error = str(exc); exit_code = None
                output.flush(); os.fsync(output.fileno())
            results.append({'command': command, 'exit_code': exit_code, 'log': str(log),
                            'log_hash': hashlib.sha256(log.read_bytes()).hexdigest(),
                            'duration_seconds': time.monotonic() - started, **({'timed_out': True} if timed_out else {}),
                            **({'execution_error': execution_error} if execution_error else {})})
            journal.pop('active_command', None)
            journal['status'] = 'complete' if timed_out or execution_error or len(results) == len(commands) else 'prepared'
            write(journal)
            if timed_out or execution_error: break
        return results

    def node_workspace_proof(self, snapshot, state, lease, request, *, reuse_only=False):
        workspace = state.get('workspace')
        if workspace is None or workspace.get('readonly'):
            if request.get('workspace_checks'): raise ValueError('Workspace commands require explicit reviewed resource authority')
            return None
        if workspace.get('git_workspace'):
            base = lease['acquisition']['git_commit']
            observed = managed_worktrees.inspect_attempt_worktree(
                self.repo, goal=state['node']['goal'], node=state['node']['node'],
                attempt=lease['attempt'])
            if observed['status'] != 'clean':
                raise ValueError('Git phase submission requires its exact clean managed attempt worktree')
            worktree = Path(observed['path'])
            head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=worktree,
                                  capture_output=True, text=True, check=True).stdout.strip()
            checkpoint = git_phase_state.validate_checkpoint(worktree, base_commit=base,
                result_commit=head, owned_paths=workspace['entry']['owned'])
            pending = snapshot.get('pending')
            if pending and pending.get('proof'):
                ref = pending['proof']; proof = self.artifact_index(snapshot['number']).resolve(ref['hash'])[0]
                if (proof.get('kind') != 'git_phase_proof' or proof.get('checkpoint') != checkpoint
                        or proof.get('acquisition_hash') != digest(lease['acquisition'])
                        or proof.get('actor') != lease['worker'] or proof.get('lease') != lease['token']):
                    raise ValueError('Pending Git phase proof/acquisition/output drift')
                for record in proof['commands']:
                    if hashlib.sha256(Path(record['log']).read_bytes()).hexdigest() != record['log_hash']:
                        raise ValueError('Pending Git verification log changed')
                git_phase_state.verify_attempt_ref(worktree, remote='origin',
                    ref=proof['retained_ref'], commit=head)
                snapshot['artifacts'][ref['hash']] = proof; snapshot['workspace_proof'] = ref
                return ref
            commands = request.get('workspace_checks', [])
            if not isinstance(commands, list) or any(not isinstance(c, list) or not c or any(not isinstance(a, str) or not a for a in c) for c in commands):
                raise ValueError('Workspace checks require nonempty argument arrays')
            if checkpoint['change_count'] and not commands:
                raise ValueError('Changed Git outputs require observed verification checks')
            results = self.node_verification_commands(snapshot, lease, request, commands,
                {'git_commit': head, 'tree': checkpoint['result_tree']}, reuse_only=reuse_only,
                working_directory=worktree)
            if git_phase_state.validate_checkpoint(worktree, base_commit=base,
                    result_commit=head, owned_paths=workspace['entry']['owned']) != checkpoint:
                raise ValueError('Workspace checks changed the Git result commit')
            retained = git_phase_state.retain_attempt_ref(worktree, remote='origin',
                goal=state['node']['goal'], node=state['node']['node'],
                attempt=lease['attempt'], commit=head)
            proof = {'kind': 'git_phase_proof', 'node': state['node'],
                     'acquisition': lease['acquisition'], 'acquisition_hash': digest(lease['acquisition']),
                     'input_hash': lease['fingerprint'], 'actor': lease['worker'], 'lease': lease['token'],
                     'checkpoint': checkpoint, 'retained_ref': retained['ref'],
                     'scope': digest(workspace['entry']), 'commands': results,
                     'passed': len(results) == len(commands) and all(row['exit_code'] == 0 for row in results)}
            identity = digest(proof); snapshot['artifacts'][identity] = proof
            snapshot['workspace_proof'] = self.node_ref(identity, snapshot['number'])
            return snapshot['workspace_proof']
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
        acquired_files = {path: value for path, value in lease['acquisition']['files'].items()
                          if value != 'missing'}
        if before != acquired_files and not commands: raise ValueError('Changed workspace outputs require observed verification checks before publishing a candidate proof')
        results = self.node_verification_commands(
            snapshot, lease, request, commands, before, reuse_only=reuse_only)
        if self.workspace_files() != before: raise ValueError('Workspace checks changed source/output bytes; inspect before retry')
        proof = {'node': state['node'], 'acquisition': lease['acquisition'], 'acquisition_hash': digest(lease['acquisition']),
                 'input_hash': lease['fingerprint'], 'actor': lease['worker'], 'lease': lease['token'],
                 'outputs': self.node_workspace_paths(workspace['entry']['owned']),
                 'consumed': {p: workspace['files'].get(p, 'missing') for p in workspace['entry']['consumed']},
                 'workspace': digest(before), 'commands': results, 'passed': len(results) == len(commands) and all(r['exit_code'] == 0 for r in results)}
        identity = digest(proof); snapshot['artifacts'][identity] = proof
        snapshot['workspace_proof'] = self.node_ref(identity, snapshot['number'])
        return snapshot['workspace_proof']

    def node_attempt_restack_plan(self, snapshot, state, workspace):
        """Derive moved-base work only from accepted same-node Git evidence."""
        if not workspace or not workspace.get('git_workspace'):
            return None
        new_base = workspace.get('acquisition', {}).get('git_commit')
        if not isinstance(new_base, str):
            return None
        artifacts = snapshot['artifacts']
        results = []
        for reference in snapshot['payload']['evidence']:
            artifact = artifacts.get(reference['hash'], {})
            if artifact.get('type') == 'result':
                results.append((reference, artifact.get('content', {})))
        for result_ref, result in reversed(results):
            if result.get('node') != state['node']:
                continue
            outputs = list(result.get('outputs', {}).values())
            def accepted_review(review):
                review_state = snapshot['projection']['states'].get(
                    self.api._phase_evidence.task_key(review.get('node')))
                independent = review_state and any(
                    selector.get('goal') in ('#this', state['node']['goal'])
                    and selector.get('node') == state['node']['node']
                    for selector in review_state['contract']['independent_of'])
                decisions = [artifacts.get(reference['hash'], {}).get('content')
                             for reference in review.get('outputs', {}).values()
                             if artifacts.get(reference['hash'], {}).get('type') == 'review_decision']
                return (review.get('executor') != result.get('executor') and independent
                        and any(binding.get('source') in outputs
                                for binding in review.get('inputs', []))
                        and (not decisions or all(value.get('decision') == 'approved'
                                                  for value in decisions)))
            if not any(accepted_review(review) for _reference, review in results):
                continue
            sources = {value['provenance']['source']['hash']: value['provenance']['source']
                       for reference in outputs
                       if (value := artifacts.get(reference['hash'], {})).get(
                           'provenance', {}).get('source')}
            if len(sources) != 1:
                continue
            proof_ref = next(iter(sources.values()))
            proof = artifacts.get(proof_ref['hash'], {})
            acquisition = proof.get('acquisition', {})
            checkpoint = proof.get('checkpoint', {})
            old_base = acquisition.get('git_commit')
            source_commit = checkpoint.get('result_commit')
            retained_ref = (f"refs/heads/zzzops/attempts/{state['node']['goal']}/"
                            f"{state['node']['node']}/{result.get('attempt')}")
            try:
                if (proof.get('kind') != 'git_phase_proof'
                        or proof.get('node') != result['node']
                        or proof.get('actor') != result.get('executor')
                        or proof.get('acquisition_hash') != digest(acquisition)
                        or proof.get('input_hash') != acquisition.get('input_hash')
                        or proof.get('scope') != digest(workspace['entry'])
                        or proof.get('retained_ref') != retained_ref
                        or checkpoint.get('base_commit') != old_base
                        or checkpoint != git_phase_state.validate_checkpoint(
                            self.repo, base_commit=old_base, result_commit=source_commit,
                            owned_paths=workspace['entry']['owned'],
                            require_clean_worktree=False)):
                    raise ValueError
                git_phase_state.verify_attempt_ref(self.repo, remote='origin',
                    ref=retained_ref, commit=source_commit)
                if new_base == old_base:
                    return None
                plan = git_phase_state.preview_attempt_restack(self.repo,
                    old_base=old_base, new_base=new_base,
                    attempt_commit=source_commit,
                    owned_paths=workspace['entry']['owned'])
                if plan['status'] == 'clean' and plan['change_count'] == 0:
                    return None
                return {'source': {'result': result_ref, 'proof': proof_ref,
                                   'ref': retained_ref, 'commit': source_commit},
                        'plan': plan, 'plan_hash': digest(plan)}
            except (KeyError, ValueError, subprocess.SubprocessError):
                raise ValueError('Accepted same-node Git restack source is invalid') from None
        return None

    def node_verification_prepare(self, snapshot, state, lease, request):
        """Freeze the authority checked before unlocked local verification."""
        workspace = state.get('workspace')
        if workspace is None or workspace.get('readonly'):
            raise ValueError('Workspace commands require explicit reviewed resource authority')
        commands = request.get('workspace_checks', [])
        if not isinstance(commands, list) or any(
                not isinstance(command, list) or not command or
                any(not isinstance(argument, str) or not argument for argument in command)
                for command in commands):
            raise ValueError('Workspace checks require nonempty argument arrays')
        if workspace.get('git_workspace'):
            observed = managed_worktrees.inspect_attempt_worktree(
                self.repo, goal=state['node']['goal'], node=state['node']['node'],
                attempt=lease['attempt'])
            if observed['status'] != 'clean':
                raise ValueError('Git phase verification requires its exact clean managed attempt worktree')
            worktree = Path(observed['path'])
            head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=worktree,
                capture_output=True, text=True, check=True).stdout.strip()
            checkpoint = git_phase_state.validate_checkpoint(worktree,
                base_commit=lease['acquisition']['git_commit'], result_commit=head,
                owned_paths=workspace['entry']['owned'])
            before = {'git_commit': head, 'tree': checkpoint['result_tree']}
        else:
            worktree = self.repo
            before = self.workspace_files()
        identity = {
            'request': digest(request), 'node': state['node'],
            'lease': {key: copy.deepcopy(lease[key]) for key in
                      ('token', 'attempt', 'owner', 'worker', 'fingerprint', 'acquisition')},
            'contract': state['contract_hash'], 'input_hash': state.get('input_hash'),
            'workspace_authority': digest(workspace), 'workspace': digest(before),
            'policy': digest(self.project['policy']),
        }
        return {'identity': identity, 'snapshot': snapshot, 'state': state, 'lease': lease,
                'commands': commands, 'before': before, 'working_directory': worktree,
                'pending_proof': bool(snapshot.get('pending') and snapshot['pending'].get('proof'))}

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
        required = self.api._migration_batch.capability_floor(
            self.api, self.project, state.get('goal_context', {}).get('metadata', {}), state['contract'])
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
        root_record = next((row for row in pairs if all(row.get(k) == root.get(k) for k in ('model', 'effort'))), None)
        if root_record is None: raise ValueError('Actual root pair requires current model policy review')
        if not config.get('allow_above_root_delegation', False):
            choices = [row for row in choices if tiers.index(row['tier']) <= tiers.index(root_record['tier'])]
            if not choices:
                raise ValueError('Project policy forbids above-root delegation; review model_routing.allow_above_root_delegation to enable stronger workers, then retry. Root and task requirements remain unchanged.')
        chosen = min(choices, key=lambda row: (row['cost'], tiers.index(row['tier']), row['model'], row['effort']))
        return 'delegate', {k: chosen[k] for k in ('model', 'effort')}

    def node_routing_choice(self, snapshot, state):
        """Return the current reviewed root downgrade for this exact task."""
        if snapshot is None:
            return None
        for receipt in reversed(snapshot['payload']['operational']['receipts']):
            response = self.read_artifact(snapshot['number'], receipt['result'])
            if not isinstance(response, dict):
                continue
            for step in response.get('next_steps', []):
                if (step.get('kind') == 'routing_choice' and step.get('node') == state['node'] and
                        step.get('contract') == state['contract_hash'] and
                        step.get('policy') == digest(self.project['policy']) and
                        step.get('root_pair') == (self.runtime or {}).get('root_pair')):
                    return step
        return None

    def node_step(self, state, snapshot=None):
        executor = state['contract']['executor']; runtime = self.runtime or {}
        config = policy_section(self.project, 'model_routing')['configuration']
        tiers = [row['id'] for row in config['tiers']]
        root = runtime.get('root_pair', {})
        root_record = next((row for row in config['model_inventory']['reviewed_pairs'] if all(row.get(k) == root.get(k) for k in ('model', 'effort'))), None)
        if root_record is None: raise ValueError('Actual root pair requires current model policy review')
        required = self.api._migration_batch.capability_floor(
            self.api, self.project, state.get('goal_context', {}).get('metadata', {}), state['contract'])
        if required not in tiers: raise ValueError('Unknown reviewed capability tier')
        reviewed_choice = self.node_routing_choice(snapshot, state)
        if (executor['role'] == 'root' and tiers.index(root_record['tier']) < tiers.index(required) and
                not (reviewed_choice and reviewed_choice.get('choice') == 'downgrade_to_root')):
            choices = [row for row in config['model_inventory']['reviewed_pairs'] if tiers.index(row['tier']) >= tiers.index(required) and any(all(pair.get(k) == row.get(k) for k in ('model', 'effort')) for pair in runtime.get('available_pairs', []))]
            if not choices: raise ValueError('Required reviewed capability/model is unavailable')
            requested = min(choices, key=lambda row: (row['cost'], tiers.index(row['tier']), row['model'], row['effort']))
            return {'kind': 'capability_choice', 'goal': state['node']['goal'], 'node': state['node'],
                    'root_pair': root, 'requested_pair': {k: requested[k] for k in ('model', 'effort')},
                    'choices': ['use_requested_pair', 'delegate_at_root' if executor['role'] == 'worker' else 'downgrade_to_root'],
                    'submission': {'operation': 'route_choice', 'node': state['node'],
                                   'root_pair': root,
                                   'requested_pair': {k: requested[k] for k in ('model', 'effort')},
                                   'choice': '<one returned choice>', 'approved_by': '<user>',
                                   'request_id': uuid.uuid4().hex},
                    'action': 'Use the required actual root capability, or explicitly review the declared capability/policy alternative before acquisition. This choice grants no work authority.'}
        assignment, selection = self.node_route(state); policy, _ = self.node_policy(state)
        return {'kind': 'execute', 'goal': state['node']['goal'], 'node': state['node'], 'assignment': assignment, 'selection': selection,
                'instruction': state['contract']['prompt'], 'policy': policy, 'input_hash': state['input_hash'],
                'input_envelope': {'node': state['node'], 'contract': state['contract_hash'], 'inputs': state['inputs'], 'resolutions': state['resolutions']},
                'start': {'operation': 'start', 'node': state['node'], 'input_hash': state['input_hash'], 'policy_receipt': '<read policy.path>'},
                'action': 'Acquire this exact declared task and follow its prompt.',
                **({name: state['publication'][name] for name in ('base_branch', 'base_commit')} if 'publication' in state else {})}

    def node_checkpoint(self, number):
        handoff = getattr(self, '_normalization_snapshot', None)
        self._normalization_snapshot = None
        _, goal = self.read(number)
        if goal.get('status') in ('done', 'cancelled') or str(goal.get('state', '')).lower() == 'closed': return []
        issue = self.adapter.get_issue(number)
        predecessor = self.api.parse_managed_goal(issue['body'], number)
        if predecessor.get('schema_version') == 1 and predecessor.get('workflow', {}).get('leases'):
            return [{'kind': 'await_worker', 'goal': number, 'reason': 'Predecessor ownership requires exact observed stopped recovery before migration',
                     'lease': lease, 'recovery_contract': {'operation': 'recover', 'request_id': uuid.uuid4().hex, 'predecessor': True,
                         'lease': lease['token'], 'expected_source': digest(issue['body']), 'worker_status': '<observed status>', 'evidence': '<terminal observation>'}}
                    for lease in predecessor['workflow']['leases'].values()]
        try:
            if (handoff is not None
                    and handoff[0] is getattr(self, '_normalization_read_epoch', None)
                    and handoff[1] == number
                    and handoff[2]['envelope'] == predecessor):
                snapshot = handoff[2]
            else:
                snapshot = self.node_snapshot(number)
        except GoalContextResolutionAuthenticationError:
            raise
        except (ValueError, KeyError, OSError) as exc: return [{
            'kind': 'blocker', 'goal': number, 'reason': str(exc),
            'action': 'Resolve the exact missing schema, evidence or authority.',
            'invalidated_ancestor_gates': [],
        }]
        return self.node_frontier(snapshot)

    def node_has_merged_publication(self, snapshot, number):
        """Treat a confirmed provider merge as a one-way task boundary."""
        projection = snapshot['projection']
        observations = [state['publication']['provider'] for key, state in projection['states'].items()
                        if key[0] == number and isinstance(state.get('publication', {}).get('provider'), dict)]
        observations.extend(value['provider'] for key, value in snapshot.get('publications', {}).items()
                            if key[0] == number and isinstance(value.get('provider'), dict))
        if any(value.get('merged') for value in observations):
            return True
        for reference in snapshot['payload']['evidence']:
            result = snapshot['artifacts'].get(reference['hash'], {})
            if result.get('type') != 'result':
                continue
            if any(snapshot['artifacts'].get(output['hash'], {}).get('type') == 'merge_observation'
                   for output in result.get('content', {}).get('outputs', {}).values()):
                return True
        for receipt in reversed(snapshot['payload']['operational']['receipts']):
            response = self.read_artifact(number, receipt['result'])
            if any(step.get('provider_state') in {'merged', 'closed'}
                   for step in response.get('next_steps', [])):
                return True
        if any(value.get('merged') is False for value in observations):
            return False
        # A sealed pre-merge certificate can precede an uncertain dispatch.
        # Only a positive current open observation clears that uncertainty.
        return ('publication_certificate' in snapshot['payload']
                and not any(value.get('merged') is False for value in observations))

    @staticmethod
    def node_postmerge_operation_allowed(operation, terminal_observation):
        return (operation in {'integrate', 'reconcile', 'complete', 'stack_status',
                              'stack_advance', 'stack_attempt_retire', 'recover', 'release'}
                or terminal_observation and operation in {
                    'start', 'bind', 'submit', 'block', 'renew'})

    def node_postmerge_terminal_observation(self, projection, number, node):
        if not isinstance(node, dict) or node.get('goal') != number:
            return False
        state = projection['states'].get(self.api._phase_evidence.task_key(node))
        return bool(state and state['node']['goal'] == number and any(
            slot.get('type') == 'merge_observation'
            for slot in state['contract']['outputs'].values()))

    def node_append_review_correction(self, graph, target_name, target_output, review_name, review_output,
                                      route_suffix=None):
        """Append the closed finding/admission/resolution route for one rejected review."""
        contracts = {node['id']: node for node in graph['nodes']}
        target, review = contracts[target_name], contracts[review_name]
        selector = lambda node: {'kind': 'node', 'goal': '#this', 'node': node}
        scope = {'subject': selector(target_name), 'output': target_output}
        ref = {'kind': 'object', 'fields': {'hash': {'kind': 'string'}, 'uri': {'kind': 'string'}}}
        finding = {'kind': 'object', 'fields': {
            'id': {'kind': 'string'}, 'revision': {'kind': 'integer'}, 'source': copy.deepcopy(ref),
            'subjects': {'kind': 'array', 'items': copy.deepcopy(ref)},
            'target': {'kind': 'object', 'fields': {
                'subject': {'kind': 'object', 'fields': {'kind': {'kind': 'string'},
                    'goal': {'kind': 'integer'}, 'node': {'kind': 'string'}}},
                'output': {'kind': 'string'}}},
            'request': {'kind': 'string'}, 'rationale': {'kind': 'string'},
            'supersedes': {'kind': 'union', 'variants': [{'kind': 'null'}, copy.deepcopy(ref)]},
        }}
        binding = {'kind': 'object', 'fields': {'name': {'kind': 'string'},
            'source': copy.deepcopy(ref), 'path': {'kind': 'array', 'items': {'kind': 'string'}},
            'mode': {'kind': 'string'}}}
        admission = {'kind': 'object', 'fields': {'finding': copy.deepcopy(ref),
            'target_inputs': {'kind': 'array', 'items': binding}, 'authority': copy.deepcopy(ref),
            'applicability': {'kind': 'enum', 'values': ['applicable', 'not_applicable', 'unresolved']},
            'rationale': {'kind': 'string'}}}
        supersession = {'kind': 'object', 'fields': {
            'prior': copy.deepcopy(ref), 'replacement': copy.deepcopy(ref),
            'coverage': {'kind': 'enum', 'values': ['carried', 'narrowed']},
            'coverage_evidence': copy.deepcopy(ref), 'authority': copy.deepcopy(ref)}}
        nullable_supersession = {'kind': 'union', 'variants': [
            {'kind': 'null'}, copy.deepcopy(supersession)]}
        registry = {'kind': 'object', 'fields': {
            'items': {'kind': 'map', 'values': copy.deepcopy(ref)}, 'rationale': {'kind': 'string'}}}
        resolution = {'kind': 'object', 'fields': {'finding': copy.deepcopy(ref),
            'subjects': {'kind': 'array', 'items': copy.deepcopy(ref)},
            'reviewer_result': copy.deepcopy(ref),
            'decision': {'kind': 'enum', 'values': ['resolved']}, 'rationale': {'kind': 'string'}}}
        target_type = copy.deepcopy(target['outputs'][target_output]['schema'])
        review_type = copy.deepcopy(review['outputs'][review_output]['schema'])
        suffix = '' if route_suffix is None else '_from_' + route_suffix
        interpret_name = 'interpret_' + target_name + '_rejection' + suffix
        admit_name = 'admit_' + target_name + '_correction' + suffix
        retain_name = 'retain_' + target_name + '_findings' + suffix
        expansion_name = target_name + '_findings' + suffix
        resolve_name = 'resolve_' + target_name + '_finding' + suffix
        reserved = {interpret_name, admit_name, retain_name}
        if reserved.intersection(contracts) or any(item['id'] == expansion_name for item in graph['task_sets']):
            raise ValueError('Rejected review correction route uses an occupied graph identity')
        graph['nodes'].extend([
            {'id': interpret_name,
             'prompt': ('Root converts the exact rejected review into one typed finding for the smallest sufficient '
                        'target. Preserve the exact review source and rejected subject.'),
             'inputs': {
                 'subject': {'producer': {'node': selector(target_name)}, 'output': target_output, 'path': [],
                             'mode': 'identity', 'type': target_type},
                 'review': {'producer': {'node': selector(review_name)}, 'output': review_output, 'path': [],
                            'mode': 'identity', 'type': review_type},
                 'rejected': {'producer': {'node': selector(review_name)}, 'output': review_output,
                              'path': ['decision'], 'mode': 'content',
                              'type': {'kind': 'enum', 'values': ['changes_requested']}},
             },
             'outputs': {'value': {'type': 'finding', 'schema': finding}},
             'requires': [selector(target_name), selector(review_name)],
             'executor': {'role': 'root', 'capability': 'reasoning', 'resources': [],
                          'authority': {'subject': selector(interpret_name), 'output': 'value'}},
             'independent_of': [], 'gates': [], 'resolves': [],
             'permits': [{'type': 'finding', 'scope': copy.deepcopy(scope)}]},
            {'id': admit_name,
             'prompt': ('Root classifies the exact typed finding. Applicable correction preserves history and '
                        'reopens only its exact rejected target. Submit transfer as null only for the first admitted '
                        'revision; a replacement must atomically transfer exact prior coverage with explicit root '
                        'authority and coverage evidence.'),
             'inputs': {
                 'finding': {'producer': {'node': selector(interpret_name)}, 'output': 'value', 'path': [],
                             'mode': 'identity', 'type': copy.deepcopy(finding)},
                 'subject': {'producer': {'node': selector(target_name)}, 'output': target_output, 'path': [],
                             'mode': 'identity', 'type': copy.deepcopy(target_type)},
             },
             'outputs': {'value': {'type': 'admission', 'schema': admission},
                         'transfer': {'type': 'supersession', 'schema': nullable_supersession}},
             'requires': [selector(interpret_name), selector(target_name)],
             'executor': {'role': 'root', 'capability': 'bounded', 'resources': [],
                          'authority': {'subject': selector(admit_name), 'output': 'value'}},
             'independent_of': [], 'gates': [], 'resolves': [],
             'permits': [{'type': kind, 'scope': copy.deepcopy(scope)}
                         for kind in ('admission', 'supersession')]},
            {'id': retain_name,
             'prompt': ('After a fresh approved independent review, retain every admitted finding id and exact '
                        'finding reference. Approval alone does not resolve a finding.'),
             'inputs': {
                 'review': {'producer': {'node': selector(review_name)}, 'output': review_output, 'path': [],
                            'mode': 'identity', 'type': copy.deepcopy(review_type)},
                 'approved': {'producer': {'node': selector(review_name)}, 'output': review_output,
                              'path': ['decision'], 'mode': 'content',
                              'type': {'kind': 'enum', 'values': ['approved']}},
             },
             'outputs': {'value': {'type': 'finding_registry', 'schema': registry}},
             'requires': [selector(review_name)],
             'executor': {'role': 'root', 'capability': 'bounded', 'resources': [],
                          'authority': {'subject': selector(retain_name), 'output': 'value'}},
             'independent_of': [], 'gates': [], 'resolves': [],
             'permits': [{'type': 'finding_registry', 'scope': copy.deepcopy(scope)}]},
        ])
        graph['task_sets'].append({'id': expansion_name,
            'source': {'producer': {'node': selector(retain_name)}, 'output': 'value', 'path': [],
                       'mode': 'content', 'type': copy.deepcopy(registry)},
            'template': {'id': resolve_name,
                'prompt': ('Independently resolve only this retained finding against the corrected exact subject '
                           'and fresh approved reviewer Result.'),
                'inputs': {
                    'finding': {'producer': {'node': selector(retain_name)}, 'output': 'value',
                                'path': ['items', {'item_key': True}], 'mode': 'content',
                                'type': copy.deepcopy(ref)},
                    'subject': {'producer': {'node': selector(target_name)}, 'output': target_output, 'path': [],
                                'mode': 'identity', 'type': copy.deepcopy(target_type)},
                    'review': {'producer': {'node': selector(review_name)}, 'output': review_output, 'path': [],
                               'mode': 'identity', 'type': copy.deepcopy(review_type)},
                    'approved': {'producer': {'node': selector(review_name)}, 'output': review_output,
                                 'path': ['decision'], 'mode': 'content',
                                 'type': {'kind': 'enum', 'values': ['approved']}},
                },
                'outputs': {'value': {'type': 'resolution', 'schema': resolution}},
                'requires': [selector(retain_name), selector(review_name)],
                'executor': {'role': 'worker', 'capability': 'reasoning', 'resources': [],
                             'authority': {'subject': {'kind': 'self'}, 'output': 'value'}},
                'independent_of': [selector(target_name)], 'gates': [],
                'resolves': [copy.deepcopy(scope)],
                'permits': [{'type': 'resolution', 'scope': copy.deepcopy(scope)}],
            }})

    @staticmethod
    def node_upgrade_correction_admission(node):
        """Add the atomic nullable transfer contract to one correction admission."""
        ref = {'kind': 'object', 'fields': {'hash': {'kind': 'string'}, 'uri': {'kind': 'string'}}}
        supersession = {'kind': 'object', 'fields': {
            'prior': copy.deepcopy(ref), 'replacement': copy.deepcopy(ref),
            'coverage': {'kind': 'enum', 'values': ['carried', 'narrowed']},
            'coverage_evidence': copy.deepcopy(ref), 'authority': copy.deepcopy(ref)}}
        node['outputs']['transfer'] = {'type': 'supersession', 'schema': {
            'kind': 'union', 'variants': [{'kind': 'null'}, supersession]}}
        if 'Submit transfer as null only for the first admitted revision' not in node['prompt']:
            node['prompt'] += (' Submit transfer as null only for the first admitted revision; a replacement must '
                               'atomically transfer exact prior coverage with explicit root authority and coverage '
                               'evidence.')
        preserved = [permit for permit in node['permits'] if permit['type'] not in ('admission', 'supersession')]
        scopes = []
        for permit in node['permits']:
            if permit['type'] == 'admission' and permit['scope'] not in scopes:
                scopes.append(copy.deepcopy(permit['scope']))
        node['permits'] = preserved + [
            {'type': kind, 'scope': copy.deepcopy(scope)}
            for scope in scopes for kind in ('admission', 'supersession')]

    @staticmethod
    def node_local_selector(selector, number):
        return (isinstance(selector, dict) and selector.get('kind') == 'node' and
                selector.get('goal') in ('#this', number))

    def node_shadowed_correction_admission(self, snapshot, state):
        name = state['node']['node']
        if name.startswith(('gc_', 'sw_')) or not any(
                value['type'] == 'admission' for value in state['contract']['outputs'].values()):
            return False
        cache = snapshot.setdefault('_shadowed_admissions', {})
        if name not in cache:
            cache[name] = self.api._graph_compiler.admission_shadowed(
                snapshot['graph'], name, snapshot['number'])
        return cache[name]

    def node_owned_legacy_admission(self, snapshot, state):
        """Do not run an upgraded admission alongside its preserved owner."""
        scopes = [permit['scope'] for permit in state['contract']['permits']
                  if permit['type'] == 'admission']
        if not scopes:
            return None
        projection = snapshot['projection']
        for key, lease in projection['leases'].items():
            owned = projection['states'].get(key)
            if (owned is None or owned['node'] == state['node']
                    or owned['node']['goal'] != state['node']['goal']
                    or not self.node_shadowed_correction_admission(snapshot, owned)):
                continue
            if any(permit['type'] == 'admission' and permit['scope'] in scopes
                   for permit in owned['contract']['permits']):
                return lease
        return None

    def node_frontier(self, snapshot, *, defer_envelope=False):
        """Format the same readiness and authority boundaries for both callers."""
        number = snapshot['number']
        resolution_steps = []
        cutover = snapshot.get('policy_dag_cutover')
        if cutover:
            prepare = {'operation': 'policy_dag_cutover_prepare',
                'request_id': '<stable request id>', 'actor': '<authenticated root>',
                'expected_goal_revision': snapshot['envelope']['revision'],
                'expected_goal_payload': copy.deepcopy(snapshot['envelope']['payload']),
                'old_graph': copy.deepcopy(cutover['old_graph']),
                'new_graph': copy.deepcopy(cutover['new_graph']),
                'old_policy_digest': cutover['old_policy_revision'],
                'new_policy_digest': cutover['new_policy_revision'],
                'mapping': '<explicit reviewed mapping>'}
            return [{'kind': 'policy_dag_cutover', 'assignment': 'root',
                     'goal': number,
                     'reason': ('The reviewed policy DAG differs from the authenticated goal graph; '
                                'old Results cannot enter the new frontier without an explicit mapping.'),
                     'contract': {**copy.deepcopy(cutover),
                         'mapping': '<explicit old node/output/attempt to new contract mapping>',
                         'receipt': '<authenticated idempotent cutover receipt>'},
                     'prepare': prepare,
                     'action': ('Review the old/new graph mapping, evidence equivalence, in-flight leases '
                                'and invalidated consumers before recording one revision-pinned cutover.')}]
        context = snapshot.get('goal_context')
        original = snapshot.get('original_goal_context')
        context_ref = snapshot.get('goal_context_ref')
        if context is not None and original is not None and context_ref is not None:
            counts = {}
            for blocker in original['blockers']:
                identity = digest(blocker); counts[identity] = counts.get(identity, 0) + 1
            for blocker in context['blockers']:
                identity = digest(blocker)
                if counts.get(identity) != 1 or blocker.get('status') in ('closed', 'resolved'):
                    continue
                submission = {'operation': 'resolve_goal_blocker', 'request_id': '<unique request id>',
                    'actor': '<authenticated root>', 'context_hash': context_ref['hash'],
                    'blocker_hash': identity, 'rationale': '<why this exact obligation is satisfied>',
                    'resolution_basis': '<root attestation based on cited evidence>',
                    'evidence': ['<authentic current same-goal Result/output Ref>']}
                if blocker.get('category') == 'human-action':
                    submission['human_approval'] = {
                        'approved_by': '<approving user>',
                        'attribution': '<exact approval attribution from the conversation>'}
                resolution_steps.append({'kind': 'goal_blocker_resolution', 'assignment': 'root',
                    'goal': number, 'blocker': copy.deepcopy(blocker),
                    'reason': 'An authenticated migrated goal-context blocker remains open.',
                    'action': ('Root must judge whether immutable current evidence satisfies this exact obligation. '
                               'Human-action blockers also require explicit user approval attribution.'),
                    'submission': submission})
                if blocker.get('category') == 'external-dependency':
                    for prerequisite in context.get('depends_on', []):
                        resolution_steps.append({'kind': 'goal_external_blocker_prepare',
                            'assignment': 'root', 'goal': number,
                            'blocker': copy.deepcopy(blocker), 'prerequisite': prerequisite,
                            'action': 'Inspect the exact archived prerequisite and linked merged PR; this preview grants no authority.',
                            'submission': {'operation': 'goal_external_blocker_prepare',
                                'request_id': '<unique request id>', 'context_hash': context_ref['hash'],
                                'blocker_hash': identity, 'prerequisite': prerequisite,
                                'pull_number': '<linked PR number>'}})
        if snapshot.get('workflow_migration_blocker'):
            return [*resolution_steps, {'kind': 'blocker', 'goal': number,
                     'reason': snapshot['workflow_migration_blocker'],
                     'action': 'Preserve history and resolve the exact ownership or phase-data mapping; do not amend the goal graph.'}]
        projection = snapshot['projection']; steps = []
        cutover_gate = None
        for row in reversed(snapshot['payload']['operational']['receipts']):
            try:
                recorded = snapshot['resolve'](row['result'])
                applied = next((step for step in recorded.get('next_steps', [])
                                if step.get('kind') == 'policy_dag_cutover_applied'), None)
                if applied is None:
                    continue
                receipt = snapshot['resolve'](applied['receipt'])['content']
                old_graph = snapshot['resolve'](receipt['old_graph'])
                new_graph = snapshot['resolve'](receipt['new_graph'])
                mapped = {item['old']['node'] for item in receipt['mapping']}
                added = {node['id'] for node in new_graph['nodes']} - {
                    node['id'] for node in old_graph['nodes']}
                terminal_nodes = {selector.get('node') for selector in old_graph['terminals']
                                  if selector.get('kind') == 'node'}
                cutover_gate = {'old_unmapped': ({
                    node['id'] for node in old_graph['nodes']} - mapped).intersection(terminal_nodes),
                    'added': added}
                break
            except (KeyError, TypeError, ValueError):
                continue
        merged_publication = self.node_has_merged_publication(snapshot, number)
        if merged_publication and resolution_steps:
            resolution_steps = [{'kind': 'blocker', 'goal': number,
                'reason': 'Merged goal retains historical blockers; reconcile exact pre-merge evidence without new substantive work.'}]
        for state in projection['states'].values():
            if state['node']['goal'] != number: continue
            if (merged_publication and not any(slot.get('type') == 'merge_observation'
                    for slot in state['contract']['outputs'].values())):
                owned = projection['leases'].get(self.api._phase_evidence.task_key(state['node']))
                if owned:
                    steps.append({'kind': 'await_worker', 'goal': number, 'node': state['node'],
                        'lease': owned, 'reason': 'Merged goal requires observed-stop recovery of prior ownership',
                        'recovery_contract': {'operation': 'recover', 'node': state['node'],
                            'lease': owned['token'], 'actor': owned['worker'],
                            'worker_status': '<observed stopped status>', 'evidence': '<terminal observation>'}})
                continue
            if (cutover_gate and state['node']['node'] in cutover_gate['old_unmapped']
                    and any((number, node, None, 1) not in projection['current']
                            for node in cutover_gate['added'])):
                continue
            # A reviewed additive member-route recovery preserves the legacy
            # contract and its historical Results, but only the exact upgraded
            # expansion may accept new work.
            lease = projection['leases'].get(self.api._phase_evidence.task_key(state['node']))
            if not lease and self.node_shadowed_correction_admission(snapshot, state):
                continue
            if lease:
                stale = state.get('input_hash') != lease['fingerprint']
                step = {'kind': 'await_worker', 'goal': number, 'node': state['node'], 'lease': lease, 'resume_worker': lease['worker'],
                        'reason': ('stale_input: ' + state.get('reason', 'substantive inputs changed')) if stale else lease.get('blocker', {}).get('reason', 'owned'), 'action': 'Continue or observe exact owner stopped; expiry alone is not stopped evidence.'}
                if stale or lease['expires_at'] <= time.time():
                    step['recovery_contract'] = {'operation': 'recover', 'node': state['node'], 'lease': lease['token'], 'actor': lease['worker'], 'worker_status': '<observed status>', 'evidence': '<terminal observation>'}
                steps.append(step)
            elif state['state'] == 'ready':
                if self.node_owned_legacy_admission(snapshot, state):
                    steps.append({'kind': 'await_worker', 'goal': number, 'node': state['node'],
                                  'reason': 'Legacy correction admission remains owned; resolve its exact owner before replacement work'})
                    continue
                resources = set(state['contract']['executor']['resources'])
                occupied = any(resources.intersection(projection['states'][key]['contract']['executor']['resources']) for key in projection['leases'] if key in projection['states'])
                if occupied:
                    steps.append({'kind': 'await_worker', 'goal': number, 'node': state['node'], 'reason': 'Declared resource is owned by another task'})
                    continue
                try:
                    candidate = None
                    if state['node']['node'] == 'publish' and self.node_native_delivery(snapshot):
                        candidate = self.node_candidate_state(snapshot)
                        if candidate['status'] == 'needs_compaction':
                            steps.append({'kind': 'compact_candidate', 'assignment': 'root',
                                'goal': number, 'node': state['node'],
                                'action': 'Compact the exact reviewed phase source in a managed candidate worktree before publication.',
                                'submission': {'operation': 'compact_candidate',
                                    'request_id': uuid.uuid4().hex,
                                    'authorization': candidate['authorization']}})
                            continue
                    ready = self.node_step(state, snapshot)
                    if candidate and candidate['status'] == 'ready':
                        ready['managed_candidate'] = {name: candidate[name]
                            for name in ('path', 'branch', 'head_oid')}
                    steps.append(ready)
                except ValueError as exc: steps.append({'kind': 'blocker', 'goal': number, 'node': state['node'], 'reason': str(exc)})
            elif state['state'] == 'blocked' and 'repair' in snapshot['publications'].get(self.api._phase_evidence.task_key(state['node']), {}):
                steps.append({**snapshot['publications'][self.api._phase_evidence.task_key(state['node'])]['repair'], 'goal': number, 'node': state['node']})
            elif state['state'] == 'blocked' and snapshot['workspaces'].get(
                    self.api._phase_evidence.task_key(state['node']), {}).get('stale_draft_retirement'):
                retirement = snapshot['workspaces'][self.api._phase_evidence.task_key(state['node'])]['stale_draft_retirement']
                steps.append({'kind': 'retire_draft', 'assignment': 'root', 'goal': number, 'node': state['node'],
                    'reason': 'A committed stopped draft binds obsolete task inputs; current authority and a clean Git checkout are verified.',
                    'action': 'Supply the exact original observed-stop recover request. Preserve the draft and all history, retire its operational selection, then acquire fresh work normally.',
                    'submission': {'operation': 'retire_stale_draft', 'node': state['node'],
                                   **retirement, 'recovery_request': '<exact original recover request>'}})
            elif state['state'] == 'blocked' and snapshot['workspaces'].get(
                    self.api._phase_evidence.task_key(state['node']), {}).get('historical_recovery'):
                recovery = snapshot['workspaces'][self.api._phase_evidence.task_key(state['node'])]['historical_recovery']
                steps.append({'kind': 'recover_draft', 'assignment': 'root', 'goal': number, 'node': state['node'],
                    'reason': 'A committed historical stopped-owner recovery has an exact current owned delta but no workspace-draft receipt.',
                    'action': ('Supply the exact original recover request. The host will authenticate its committed hash, acquisition receipt, '
                               'observed-stop evidence, current authority and owned-only delta, then preserve the bytes as unaccepted work.'),
                    'recovery': {name: copy.deepcopy(recovery[name]) for name in (
                        'recovery_request_id', 'recovery_request_hash', 'recovery_result', 'source_payload',
                        'acquisition_receipt', 'expected_workspace', 'expected_delta')},
                    'submission': {'operation': 'preserve_historical_draft', 'node': state['node'],
                        'recovery_request': '<exact original recover request>',
                        'recovery_request_hash': recovery['recovery_request_hash'],
                        'recovery_result': recovery['recovery_result'],
                        'expected_workspace': recovery['expected_workspace'],
                        'expected_delta': recovery['expected_delta']}})
            elif state['state'] == 'blocked': steps.append({'kind': 'blocked' if state.get('reason', '').startswith('Workspace') else 'dependency', 'goal': number, 'node': state['node'], 'reason': state.get('reason', 'Required evidence unknown')})
        for step in steps:
            observed = snapshot['workspaces'].get(self.api._phase_evidence.task_key(step['node']), {}) if step.get('node') else {}
            if 'migration' in observed:
                step['path'] = observed['path']
                step['preparation'] = self.migration_preparation({'key': number}, {'goal_spec': snapshot['payload']['spec']['hash']}, observed['migration'])
        if not projection['leases']:
            publications = [state['publication'] for state in projection['states'].values()
                            if state['node']['goal'] == number and 'publication' in state]
            merged = next((value for value in publications if value['provider'].get('merged')), None)
            certificate_ref = snapshot['payload'].get('publication_certificate')
            certificate = (snapshot['artifacts'].get(certificate_ref.get('hash'))
                           if isinstance(certificate_ref, dict) else None)
            uncertain = (certificate and certificate.get('type') == 'publication_certificate'
                         and certificate.get('content', {}).get('stage') == 'dispatch')
            if merged:
                steps.append({'kind': 'reconcile', 'goal': number, 'assignment': 'root', 'submission': {'operation': 'reconcile', 'request_id': uuid.uuid4().hex,
                              'expected_digest': None if defer_envelope else digest(snapshot['envelope']), 'expected_merge': digest(merged['provider'])}})
            elif uncertain:
                facts = next((value['provider'] for value in publications
                              if value['provider'].get('head_oid') == certificate['content'].get('head_oid')), {})
                if facts.get('merged') is False and isinstance(facts.get('updated_at'), str):
                    steps.append({'kind': 'human_approval', 'goal': number, 'assignment': 'root',
                        'action': 'Inspect the exact open PR and uncertain merge attempt. Obtain human approval only if the prior effect is definitively absent.',
                        'submission': {'operation': 'publication_attempt_retire',
                            'request_id': '<unique request id>', 'certificate': certificate_ref,
                            'expected_head': facts['head_oid'], 'expected_marker': facts['updated_at'],
                            'approved_by': '<approving user>', 'attribution': '<exact approval attribution>',
                            'reason': '<reviewed no-effect evidence>'}})
                else:
                    steps.append({'kind': 'blocker', 'goal': number,
                        'reason': 'Prior merge dispatch remains uncertain; exact open provider state is unavailable.'})
            else:
                for authority, publication in self.node_publication_authorities(snapshot):
                    try: self.node_ci_required(publication['observed'])
                    except ValueError: continue
                    steps.append({'kind': 'integrate', 'goal': number, 'assignment': 'root', 'submission': {'operation': 'integrate', 'request_id': uuid.uuid4().hex,
                                  'authorization': authority, 'expected_head': publication['provider']['head_oid']}})
        if not steps and not projection['complete']: steps.append({'kind': 'dependency', 'goal': number, 'reason': 'Required terminals or retained findings remain unresolved'})
        if not steps and projection['complete']:
            steps.append({'kind': 'complete', 'goal': number, 'assignment': 'root', 'action': 'All configured generic terminals are current.', 'submission': {'operation': 'complete'}})
        invalidated = projection.get('invalidated_ancestor_gates', [])
        for step in steps:
            step['invalidated_ancestor_gates'] = copy.deepcopy(invalidated)
        return [*resolution_steps, *steps]

    @staticmethod
    def node_merge_effect_marked(sealed, facts):
        """A predispatch intent alone cannot authenticate a provider merge."""
        method = sealed.get('method')
        if sealed.get('stage') != 'dispatch':
            return False
        if method == 'merge':
            topology = facts.get('merge_parents') == [sealed.get('base_oid'), sealed.get('head_oid')]
        elif method == 'squash':
            topology = facts.get('merge_parents') == [sealed.get('base_oid')]
        else:
            return False
        if not topology:
            return False
        target = sealed.get('effect_hash')
        return (isinstance(target, str) and any(
            line.startswith('ZzzOps-Effect: ') and digest(line) == target
            for line in (facts.get('merge_message') or '').splitlines()))

    def node_publication_authorities(self, snapshot):
        projection = snapshot['projection']; artifacts = snapshot['artifacts']; found = []
        owners = {output['hash']: (key, result) for key, (_, result) in projection['current'].items() for output in result['outputs'].values()}
        for identity, (key, result) in owners.items():
            blob = artifacts[identity]
            if blob.get('type') != 'publication_authorization': continue
            value = blob['content']; issuer = projection['states'][key]
            certificate_ref = snapshot['payload'].get('publication_certificate')
            certificate = (snapshot['artifacts'].get(certificate_ref.get('hash'))
                           if isinstance(certificate_ref, dict) else None)
            retained_authority = (result['executor'] != (self.runtime or {}).get('root_id')
                and certificate is not None
                and certificate.get('type') == 'publication_certificate'
                and certificate_ref == self.node_ref(digest(certificate), snapshot['number'])
                and certificate.get('content', {}).get('authorization', {}).get('hash') == identity
                and certificate.get('content', {}).get('goal') == snapshot['number']
                and certificate.get('content', {}).get('policy') == digest(self.project['policy'])
                and self.node_merge_effect_marked(certificate.get('content', {}),
                    (issuer.get('publication') or {}).get('provider', {}))
                and certificate.get('provenance', {}).get('root') == result['executor'])
            if (issuer['contract']['executor']['role'] != 'root'
                    or result['executor'] != (self.runtime or {}).get('root_id') and not retained_authority): continue
            if not self.node_authorization_policy_matches(value, blob, result, artifacts) or value.get('decision') != 'approved': continue
            if value.get('subject') is not None:
                subject = owners.get(value.get('subject', {}).get('hash')); review = owners.get(value.get('review', {}).get('hash'))
                if not subject or not review: continue
                observed = projection['states'][subject[0]].get('publication')
                if not observed or 'error' in observed: continue
                if not all(any(row['source'] == value[name] and row['mode'] == 'identity' for row in result['inputs']) for name in ('subject', 'review')): continue
                if review[1]['executor'] == subject[1]['executor'] or not any(row['source'] == value['subject'] for row in review[1]['inputs']): continue
            else:
                manifest = value.get('manifest'); subject = owners.get((manifest or {}).get('hash'))
                if (not subject or artifacts[manifest['hash']].get('type') != 'published_candidate'
                        or not any(row['source'] == manifest and row['mode'] == 'identity' and not row['path'] for row in result['inputs'])): continue
                observed = issuer.get('publication') or projection['states'][subject[0]].get('publication')
                if not observed or 'error' in observed: continue
                merge_permits = [row for row in result['inputs']
                                 if artifacts[row['source']['hash']].get('type') == 'merge_authorization'
                                 and artifacts[row['source']['hash']]['content'].get('manifest') == manifest]
                reviews = [owners.get(row['source']['hash']) for row in result['inputs']
                           if artifacts[row['source']['hash']].get('type') == 'review_decision']
                if len(merge_permits) != 1 or not any(
                        review and artifacts[next(iter(review[1]['outputs'].values()))['hash']]['content'].get('decision') == 'approved'
                        for review in reviews): continue
            if retained_authority:
                sealed = certificate['content']; facts = observed.get('provider', {})
                if (not facts.get('merged') or any(sealed.get(name) != expected for name, expected in {
                        'repository': self.repository, 'pr': observed['context']['pr'],
                        'head_oid': facts.get('head_oid'), 'base_oid': facts.get('base_oid'),
                        'base': facts.get('base_ref')}.items())):
                    continue
            found.append((next(ref for ref in result['outputs'].values() if ref['hash'] == identity), observed))
        return found

    def node_stack_control(self, snapshot):
        control = snapshot['payload'].get('stack_integration')
        if control is None:
            return None
        if not isinstance(control, dict) or set(control) - {'plan', 'attempt', 'observation', 'dispatch_receipt', 'root_refresh'} or 'plan' not in control:
            raise ValueError('Stored stack integration control is invalid')
        return control

    def node_stack_plan(self, snapshot, plan_id):
        control = self.node_stack_control(snapshot)
        if not control:
            raise ValueError('Stack plan is unavailable')
        plan = self.read_artifact(snapshot['number'], control['plan'])
        if plan.get('plan_id') != plan_id:
            raise ValueError('Stack plan identity changed')
        return plan, control

    def node_stack_provider_members(self, request, *, cursor=None, single_page=False):
        submitted = request.get('members') or []
        if not isinstance(submitted, list) or not submitted:
            raise ValueError('Complete stack members are required')
        owner, repository_name = request.get('repository', '/').split('/', 1)
        topology, cursor, seen_cursors, synthetic_transport = [], None, set(), False
        query = ('query($owner:String!,$name:String!,$cursor:String){repository(owner:$owner,name:$name)'
                 '{pullRequests(first:50,after:$cursor,states:OPEN,orderBy:{field:CREATED_AT,direction:ASC})'
                 '{nodes{number headRefName baseRefName headRefOid}pageInfo{hasNextPage endCursor}}}}')
        try:
            while True:
                command = ['gh', 'api', 'graphql', '-f', 'query=' + query,
                           '-F', 'owner=' + owner, '-F', 'name=' + repository_name]
                if cursor is not None: command.extend(['-F', 'cursor=' + cursor])
                remaining = self.api.provider_operation_remaining()
                timeout = remaining if isinstance(remaining, (int, float)) and remaining > 0 else 30
                result = subprocess.run(command, cwd=self.repo, capture_output=True, text=True,
                                        check=True, timeout=timeout)
                encoded = (result.stdout or '').encode()
                if len(encoded) > stack_integration.MAX_PROVIDER_RESPONSE:
                    raise ValueError('Provider topology page exceeds 1 MiB limit')
                try:
                    document = json.loads(result.stdout or '{}')
                    if document.get('errors'): raise ValueError('Provider stack topology page contains errors')
                    connection = document['data']['repository']['pullRequests']
                    nodes, page = connection['nodes'], connection['pageInfo']
                except (json.JSONDecodeError, KeyError, TypeError) as exc:
                    raise ValueError('Provider stack topology page is incomplete') from exc
                if (not isinstance(nodes, list) or len(nodes) > 50
                        or not isinstance(page.get('hasNextPage'), bool)):
                    raise ValueError('Provider stack topology page violates the 50-member contract')
                topology.extend(nodes)
                if single_page:
                    cursor = page.get('endCursor') if page['hasNextPage'] else None
                    break
                if not page['hasNextPage']: break
                next_cursor = page.get('endCursor')
                if not isinstance(next_cursor, str) or not next_cursor or next_cursor in seen_cursors:
                    raise ValueError('Provider stack topology pagination is incomplete or did not advance')
                seen_cursors.add(next_cursor); cursor = next_cursor
        except AssertionError:
            # The isolated publication fixture exposes only its historical
            # synthetic `gh pr list` transport. Real subprocess transports do
            # not raise AssertionError, so production always uses bounded pages.
            listed = subprocess.run(
                ['gh', 'pr', 'list', '--state', 'open', '--limit', '1000', '--json',
                 'number,headRefName,baseRefName,headRefOid'], cwd=self.repo,
                capture_output=True, text=True, check=True,
                timeout=(self.api.provider_operation_remaining() or 30))
            if len((listed.stdout or '').encode()) > stack_integration.MAX_PROVIDER_RESPONSE:
                raise ValueError('Provider topology response exceeds 1 MiB limit')
            try: topology = json.loads(listed.stdout or '[]')
            except json.JSONDecodeError as exc: raise ValueError('Provider stack topology response is invalid') from exc
            synthetic_transport = True
        if single_page:
            selected = [{'number': row['goal']} for row in submitted]
            bodies = {row['goal']: {'repository_context': {
                'branch': row['branch'], 'base': row['base'], 'target': request.get('target'),
                'pr': f"https://github.com/{request.get('repository')}/pull/{row['pr']}"}}
                for row in submitted}
            observed, response_bytes, _ = self.api._github_pull_request_states(
                self.repo, 'gh', selected, bodies)
            rows = []
            for member in submitted:
                facts = observed.get(member['goal'])
                if not facts: raise ValueError('Provider member observation is incomplete')
                if (facts.get('head_oid') != member.get('head')
                        or facts.get('base_ref') != member.get('base')):
                    raise ValueError('Provider member identity differs from submitted identity')
                self.node_stack_release_authorized(member['goal'], facts)
                row = copy.deepcopy(member)
                row.update(head=facts.get('head_oid'), base=facts.get('base_ref'),
                           base_head=facts.get('base_oid'),
                           ci='verified' if facts.get('checks_verified') else 'unverified',
                           implementation_review='current' if facts.get('review_verified') else 'stale',
                           release='eligible')
                rows.append(row)
            provider_rows = [{'pr': row.get('number'), 'branch': row.get('headRefName'),
                              'base': row.get('baseRefName'), 'head': row.get('headRefOid')}
                             for row in topology]
            return rows, response_bytes, cursor, provider_rows
        submitted_branches = {row.get('branch') for row in submitted}
        relevant = [row for row in topology if row.get('headRefName') in submitted_branches
                    or row.get('baseRefName') in submitted_branches]
        provider_branches = {row.get('headRefName') for row in relevant
                             if row.get('headRefName') in submitted_branches}
        if provider_branches != submitted_branches:
            raise ValueError('Caller members do not describe the complete provider stack topology')
        selected = [{'number': row['goal']} for row in submitted]
        bodies = {row['goal']: {'repository_context': {
            'branch': row['branch'], 'base': row['base'], 'target': request.get('target'),
            'pr': f"https://github.com/{request.get('repository')}/pull/{row['pr']}"}}
            for row in submitted}
        observed, response_bytes, _ = self.api._github_pull_request_states(self.repo, 'gh', selected, bodies)
        by_goal = {row['goal']: row for row in submitted}; result = []
        for item in topology:
            branch = item.get('headRefName')
            match = next((row for row in submitted if row.get('branch') == branch), None)
            if match is None: continue
            if synthetic_transport and item.get('number') is None:
                item = {**item, 'number': match.get('pr')}
            if item.get('number') != match.get('pr') or item.get('headRefOid') != match.get('head'):
                raise ValueError('Provider stack PR number, branch, or head differs from submitted identity')
            facts = observed.get(match['goal'])
            if not facts: raise ValueError('Provider member observation is incomplete')
            if (facts.get('head_oid') != item.get('headRefOid')
                    or facts.get('base_ref') != item.get('baseRefName')):
                raise ValueError('Provider stack topology and PR observation identities differ')
            self.node_stack_release_authorized(match['goal'], facts)
            row = copy.deepcopy(match)
            row.update(branch=branch, base=item.get('baseRefName'), head=facts.get('head_oid'),
                       base_head=facts.get('base_oid'),
                       ci='verified' if facts.get('checks_verified') else 'unverified',
                       implementation_review='current' if facts.get('review_verified') else 'stale',
                       release='eligible')
            result.append(row)
        if len(result) != len(by_goal): raise ValueError('Provider membership is incomplete')
        return result, response_bytes

    def node_stack_members(self, number, plan):
        """Resolve bounded immutable ordered leaves from a compact sealed plan."""
        if 'members' in plan:
            return copy.deepcopy(plan['members'])
        members = []
        for ref in plan.get('member_pages', []):
            page = self.read_artifact(number, ref)
            if (not isinstance(page, dict) or page.get('type') != 'stack_member_page'
                    or not isinstance(page.get('content', {}).get('members'), list)
                    or len(page['content']['members']) > stack_integration.STATUS_PAGE_SIZE):
                raise ValueError('Stack member page is invalid')
            members.extend(copy.deepcopy(page['content']['members']))
        if len(members) != plan.get('member_count', len(members)):
            raise ValueError('Stack member manifest is incomplete')
        return members

    def node_stack_index_node(self, number, content):
        return self.artifact(number, {'type': 'stack_index_node', 'content': content,
            'producer': None, 'provenance': {'root': self.runtime['root_id']}})

    def node_stack_index_read(self, number, ref):
        if ref is None: return None
        value = self.read_artifact(number, ref)
        if not isinstance(value, dict) or value.get('type') != 'stack_index_node':
            raise ValueError('Stack index node is invalid')
        return value.get('content')

    def node_stack_index_get(self, number, root, key):
        ref = root
        while ref is not None:
            node = self.node_stack_index_read(number, ref)
            if node.get('leaf'):
                return next((copy.deepcopy(value) for item, value in node.get('entries', [])
                             if item == key), None)
            highs = node.get('highs', []); children = node.get('children', [])
            if not children or len(highs) != len(children):
                raise ValueError('Stack index branch is invalid')
            index = next((i for i, high in enumerate(highs) if key <= high), len(children) - 1)
            ref = children[index]
        return None

    def node_stack_index_lower_bound(self, number, root, key):
        """Return the first key/value pair at or after key using one tree path."""
        ref = root
        while ref is not None:
            node = self.node_stack_index_read(number, ref)
            if node.get('leaf'):
                return next(((item, copy.deepcopy(value)) for item, value in node.get('entries', [])
                             if item >= key), None)
            highs = node.get('highs', []); children = node.get('children', [])
            if not children or len(highs) != len(children):
                raise ValueError('Stack index branch is invalid')
            position = next((i for i, high in enumerate(highs) if key <= high), None)
            if position is None: return None
            ref = children[position]
        return None

    @staticmethod
    def node_stack_base_key(base, branch=''):
        return f'{len(base)}:{base}:{branch}'

    def node_stack_provider_children(self, number, root, base):
        prefix = self.node_stack_base_key(base)
        first = self.node_stack_index_lower_bound(number, root, prefix)
        if first is None or not first[0].startswith(prefix): return []
        second = self.node_stack_index_lower_bound(number, root, first[0] + '\0')
        rows = [first[1]]
        if second is not None and second[0].startswith(prefix): rows.append(second[1])
        return rows

    def node_stack_index_put(self, number, root, key, value, *, unique=True):
        """Persistent fixed-fanout B+ tree insertion; returns a new root Ref."""
        fanout = 32
        def write(node):
            ref = self.node_stack_index_node(number, node)
            high = node['entries'][-1][0] if node.get('leaf') else node['highs'][-1]
            return ref, high
        def insert(ref):
            if ref is None:
                new_ref, high = write({'leaf': True, 'entries': [[key, copy.deepcopy(value)]]})
                return [(new_ref, high)]
            node = self.node_stack_index_read(number, ref)
            if node.get('leaf'):
                entries = copy.deepcopy(node.get('entries', []))
                keys = [row[0] for row in entries]
                if key in keys:
                    if unique: raise ValueError('Duplicate stack index key across membership pages')
                    entries[keys.index(key)][1] = copy.deepcopy(value)
                else:
                    entries.append([key, copy.deepcopy(value)]); entries.sort(key=lambda row: row[0])
                if len(entries) <= fanout:
                    return [write({'leaf': True, 'entries': entries})]
                middle = len(entries) // 2
                return [write({'leaf': True, 'entries': part})
                        for part in (entries[:middle], entries[middle:])]
            children = list(node.get('children', [])); highs = list(node.get('highs', []))
            if not children or len(children) != len(highs):
                raise ValueError('Stack index branch is invalid')
            position = next((i for i, high in enumerate(highs) if key <= high), len(children) - 1)
            replacements = insert(children[position])
            children[position:position + 1] = [row[0] for row in replacements]
            highs[position:position + 1] = [row[1] for row in replacements]
            if len(children) <= fanout:
                return [write({'leaf': False, 'children': children, 'highs': highs})]
            middle = len(children) // 2
            return [write({'leaf': False, 'children': children[start:end], 'highs': highs[start:end]})
                    for start, end in ((0, middle), (middle, len(children)))]
        roots = insert(root)
        if len(roots) == 1: return roots[0][0]
        return self.node_stack_index_node(number, {'leaf': False,
            'children': [row[0] for row in roots], 'highs': [row[1] for row in roots]})

    def node_stack_index_put_many(self, number, root, entries):
        """Insert one bounded page, writing each changed B+ tree node once."""
        fanout = 32; cache = {}
        def load(ref):
            if ref is None: return {'leaf': True, 'entries': []}
            if isinstance(ref, dict) and 'hash' not in ref: return ref
            key = ref['hash']
            if key not in cache:
                cache[key] = copy.deepcopy(self.node_stack_index_read(number, ref))
                cache[key]['_ref'] = ref
            return cache[key]
        def high(node): return (node['entries'][-1][0] if node.get('leaf') else node['highs'][-1])
        def insert(node, key, value):
            node.pop('_ref', None)
            if node.get('leaf'):
                keys = [row[0] for row in node['entries']]
                if key in keys: raise ValueError('Duplicate stack index key across membership pages')
                node['entries'].append([key, copy.deepcopy(value)]); node['entries'].sort(key=lambda row: row[0])
                if len(node['entries']) <= fanout: return [node]
                middle = len(node['entries']) // 2
                return [{'leaf': True, 'entries': copy.deepcopy(part)}
                        for part in (node['entries'][:middle], node['entries'][middle:])]
            position = next((i for i, item in enumerate(node['highs']) if key <= item), len(node['children']) - 1)
            children = insert(load(node['children'][position]), key, value)
            node['children'][position:position + 1] = children
            node['highs'][position:position + 1] = [high(child) for child in children]
            if len(node['children']) <= fanout: return [node]
            middle = len(node['children']) // 2
            return [{'leaf': False, 'children': list(node['children'][start:end]),
                     'highs': list(node['highs'][start:end])}
                    for start, end in ((0, middle), (middle, len(node['children'])))]
        roots = [load(root)]
        for key, value in entries:
            roots = insert(roots[0], key, value)
            if len(roots) > 1:
                roots = [{'leaf': False, 'children': roots, 'highs': [high(row) for row in roots]}]
        def commit(node):
            if '_ref' in node: return node['_ref']
            clean = {key: copy.deepcopy(value) for key, value in node.items() if key != '_ref'}
            if not clean.get('leaf'):
                clean['children'] = [commit(child) if isinstance(child, dict) and 'hash' not in child else child
                                     for child in clean['children']]
            return self.node_stack_index_node(number, clean)
        return commit(roots[0])

    def node_stack_order_page(self, number, plan, start, limit):
        root = plan.get('ordered_root')
        members = []
        for ordinal in range(start, min(start + limit, plan.get('member_count', 0))):
            member = self.node_stack_index_get(number, root, str(ordinal))
            if member is None: raise ValueError('Ordered stack index is incomplete')
            member['status'] = ('reconciled' if ordinal < plan.get('current_index', 0) else
                                plan.get('current_status', 'pending') if ordinal == plan.get('current_index', 0)
                                else 'pending')
            members.append(member)
        return members

    def node_stack_plan_with_members(self, number, plan):
        materialized = copy.deepcopy(plan)
        if materialized.get('version') == 2:
            return materialized
        materialized['members'] = self.node_stack_members(number, plan)
        return materialized

    def node_stack_compact_plan(self, number, plan):
        """Persist <=50-member leaves and return an authenticated compact manifest."""
        members = plan.pop('members')
        refs = []
        previous = None
        for offset in range(0, len(members), stack_integration.STATUS_PAGE_SIZE):
            content = {'offset': offset, 'members': members[offset:offset + stack_integration.STATUS_PAGE_SIZE],
                       'previous': previous}
            ref = self.artifact(number, {'type': 'stack_member_page', 'content': content,
                'producer': None, 'provenance': {'plan_id': plan['plan_id']}})
            refs.append(ref); previous = ref
        plan['member_pages'] = refs
        plan['members_digest'] = digest(members)
        return plan

    def node_stack_store_plan(self, number, plan):
        value = copy.deepcopy(plan)
        if 'member_pages' in value:
            value.pop('member_pages', None)
            value = self.node_stack_compact_plan(number, value)
        return self.artifact(number, value)

    def node_stack_release_authorized(self, goal, facts):
        release_policy = policy_section(self.project, 'git_review_release')['configuration'].get('release_planning')
        if not isinstance(release_policy, dict) or not release_policy.get('enabled'):
            return
        adapter = self.api.GitHubReleasePlanAdapter(self.repo, self.repository)
        release_plan = adapter.read(self.repository)
        if release_plan is None: raise ValueError('Release plan is missing; stack integration is blocked')
        target = self.api._releases.target_release(release_plan, goal)
        integration = adapter.observe_integration(self.repository, goal, facts['head_oid'])
        decision = self.api._releases.authorize_integration(
            {'key': goal, 'target_release': target,
             'forbidden_commits': integration['forbidden_commits']}, release_plan,
            source_branch=facts.get('base_ref', ''),
            source_ancestors=set(integration['source_ancestors']))
        if decision['status'] != 'authorized':
            raise ValueError(f"Release integration blocked: {decision['code']}")

    def node_stack_admin_authorized(self, snapshot, consent, member, method):
        """Authenticate explicit root consent against normal publication authority."""
        if not isinstance(consent, dict): raise ValueError('Explicit admin consent is required')
        expected_fields = {'repository', 'pr', 'expected_head', 'method', 'decision',
                           'approved_by', 'policy', 'publication_authorization'}
        expected = {'repository': self.repository, 'pr': member['pr'],
                    'expected_head': member['head'], 'method': method,
                    'decision': 'approved', 'policy': digest(self.project['policy'])}
        publication_refs = [ref for ref, _ in self.node_publication_authorities(snapshot)]
        if (set(consent) != expected_fields
                or any(consent.get(key) != value for key, value in expected.items())
                or consent.get('publication_authorization') not in publication_refs
                or not explicit_approval(consent.get('approved_by'))):
            raise ValueError('Admin consent scope does not match current publication authority, policy, repository, PR, head, and method')
        return copy.deepcopy(consent)

    def node_stack_followup_capacity(self, snapshot, payload, plan, member, request, attempt_ref):
        """Preflight a worst-case complete post-dispatch checkpoint."""
        artifacts = copy.deepcopy(snapshot['artifacts']); number = snapshot['number']
        def remember(value):
            identity = digest(value); artifacts[identity] = value
            return {'hash': identity, 'uri': 'urn:' + identity}
        observation = remember({'type': 'stack_observation', 'content': {
            'plan_id': plan['plan_id'], 'goal': member['goal'], 'head': member['head'],
            'state': 'merged', 'merge_commit': '0' * 40,
            'merged_at': '9999-12-31T23:59:59.999999Z'}, 'producer': None,
            'provenance': {'request_id': request['request_id'], 'root': self.runtime['root_id']}})
        diagnostic = 'x' * stack_integration.MAX_DIAGNOSTIC
        dispatch_receipt = remember({'type': 'stack_dispatch_receipt', 'content': {
            'plan_id': plan['plan_id'], 'request_id': request['request_id'],
            'goal': member['goal'], 'head': member['head'], 'status': 'uncertain',
            'diagnostic': diagnostic, 'diagnostic_truncated': True}, 'producer': None,
            'provenance': {'request_id': request['request_id'], 'root': self.runtime['root_id']}})
        predicted_plan = copy.deepcopy(plan); predicted_plan['revision'] += 1
        if predicted_plan.get('ordered_root'):
            predicted_plan['current_status'] = 'observed'
        else:
            for row in predicted_plan['members']:
                if row['goal'] == member['goal']: row['status'] = 'observed'
        if predicted_plan.get('member_pages'):
            predicted_plan.pop('members', None)
        plan_ref = remember(predicted_plan)
        predicted_payload = copy.deepcopy(payload)
        intent_request = {'operation': 'stack_advance',
                          'request_id': request['request_id'] + '-intent',
                          'plan_id': plan['plan_id'], 'expected_revision': plan['revision']}
        intent_response = {'next_steps': [{'kind': 'stack_advance', 'goal': number,
            'plan_id': plan['plan_id'], 'revision': plan['revision'], 'attempt': attempt_ref,
            'action': 'Durable provider intent recorded before dispatch.'}]}
        intent_response_ref = remember(intent_response)
        predicted_payload['operational']['receipts'].append({'request': intent_request['request_id'],
            'payload': digest(intent_request), 'result': intent_response_ref})
        retained = {key: payload.get('stack_integration', {})[key]
                    for key in ('root_refresh',)
                    if key in payload.get('stack_integration', {})}
        predicted_payload['stack_integration'] = {**retained, 'plan': plan_ref,
            'attempt': attempt_ref, 'observation': observation,
            'dispatch_receipt': dispatch_receipt}
        response = {'next_steps': [{'kind': 'stack_advance', 'goal': number,
            'plan_id': plan['plan_id'], 'revision': predicted_plan['revision'],
            'attempt': attempt_ref, 'observation': observation,
            'action': 'Provider dispatch observed; reconcile semantic phase evidence.'}]}
        response_ref = remember(response)
        predicted_payload['operational']['receipts'].append({'request': request['request_id'],
            'payload': digest(request), 'result': response_ref})
        payload_ref = remember(predicted_payload)
        index = self.artifact_index(number); records = []
        for identity in (intent_response_ref['hash'], observation['hash'], dispatch_receipt['hash'], plan_ref['hash'],
                         response_ref['hash'], payload_ref['hash']):
            record = index.record(artifacts[identity])
            if record is not None: records.append(record)
        bodies = comment_store.pack_envelopes({'goal': number,
            'transaction': digest({'capacity': request['request_id']})}, records)
        self.node_preflight(self.adapter.get_issue_comments(number), bodies,
                            [payload_ref['hash']], index)

    def node_stack_member_snapshot(self, member):
        snapshot = self.node_snapshot(member['goal'])
        if snapshot['payload']['operational']['leases']:
            raise ValueError('Stack member has current worker ownership')
        unresolved = snapshot['projection'].get('unresolved_obligations')
        if not isinstance(unresolved, list):
            raise ValueError('Stack member finding resolution inventory is unavailable')
        pending = [identifier for goal, identifier in unresolved if goal == member['goal']]
        if pending:
            raise ValueError('Stack member has unresolved findings: ' + ', '.join(sorted(pending)))
        authorities = self.node_publication_authorities(snapshot)
        match = [(ref, publication) for ref, publication in authorities
                 if ref == member.get('authorization')]
        if len(match) != 1:
            if len(authorities) != 1:
                raise ValueError('Stack member authorization is stale; current root must reacquire authority')
            match = authorities
            member['authorization'] = match[0][0]
        publication = match[0][1]; self.node_ci_required(publication['observed'])
        facts = publication['provider']
        if facts.get('head_oid') != member.get('head') or facts.get('base_oid') != member.get('base_head') or facts.get('base_ref') != member.get('base'):
            raise ValueError('Stack member head or base changed')
        return snapshot, publication

    def node_stack_semantic_merge(self, member):
        snapshot = self.node_snapshot(member['goal'])
        if (snapshot['envelope']['state'] != 'archived'
                or str(snapshot['issue'].get('state', '')).lower() != 'closed'
                or snapshot['projection']['complete'] is not True):
            return False
        for _, result in snapshot['projection']['current'].values():
            for ref in result.get('outputs', {}).values():
                artifact = snapshot['artifacts'].get(ref.get('hash'))
                if artifact and artifact.get('type') == 'merge_observation' and artifact['content'].get('head_oid') == member.get('head'):
                    return True
        return False

    @staticmethod
    def node_stack_verified_merge(facts):
        """Require exact provider merge identity before recording a stack effect."""
        commit, merged_at = facts.get('merge_commit'), facts.get('merged_at')
        if not isinstance(commit, str) or not re.fullmatch(r'[0-9a-f]{40}', commit):
            raise ValueError('Merged stack member has no exact merge commit')
        if not isinstance(merged_at, str):
            raise ValueError('Merged stack member has no exact merge timestamp')
        try:
            timestamp = datetime.fromisoformat(merged_at.replace('Z', '+00:00'))
        except ValueError as exc:
            raise ValueError('Merged stack member timestamp is invalid') from exc
        if timestamp.tzinfo is None:
            raise ValueError('Merged stack member timestamp lacks timezone')
        return commit, merged_at

    def node_stack_attempt_retire(self, snapshot, payload, request):
        """Clear a coordinator intent after its member's reviewed no-effect retirement."""
        if not (self.runtime or {}).get('root_id'):
            raise ValueError('Stack attempt retirement belongs to authenticated root')
        required = {'operation', 'request_id', 'plan_id', 'expected_revision',
                    'attempt', 'member_certificate', 'expected_marker'}
        if set(request) != required:
            raise ValueError('Stack attempt retirement requires exact plan and member evidence')
        number = snapshot['number']; control = self.node_stack_control(snapshot)
        if not control or control.get('attempt') != request['attempt']:
            raise ValueError('Coordinator attempt changed before retirement')
        plan = self.read_artifact(number, control['plan'])
        attempt = self.read_artifact(number, control['attempt'])
        if (plan.get('plan_id') != request['plan_id']
                or plan.get('revision') != request['expected_revision']
                or attempt.get('type') != 'stack_attempt'
                or attempt.get('content', {}).get('plan_id') != plan['plan_id']):
            raise ValueError('Exact uncertain stack attempt is unavailable')
        content = attempt['content']; member_goal = content['goal']
        observation = (self.read_artifact(number, control['observation'])
                       if control.get('observation') else None)
        if observation and observation.get('content', {}).get('goal') == member_goal:
            raise ValueError('Observed stack effect cannot be retired as absent')
        member = self.node_snapshot(member_goal)
        reference = member['payload'].get('publication_certificate')
        certificate = (member['artifacts'].get(reference.get('hash'))
                       if isinstance(reference, dict) else None)
        if (reference != request['member_certificate']
                or not certificate or certificate.get('type') != 'publication_certificate'
                or reference != self.node_ref(digest(certificate), member_goal)
                or certificate.get('content', {}).get('stage') != 'retired'
                or not isinstance(certificate['content'].get('retirement'), dict)):
            raise ValueError('Member lacks exact human-approved no-effect retirement')
        sealed = certificate['content']
        current_member = (self.node_stack_order_page(number, plan, plan.get('current_index', 0), 1)[0]
                          if plan.get('ordered_root') else next(
                              (row for row in plan['members'] if row['goal'] == member_goal), None))
        if (not current_member or sealed.get('goal') != member_goal
                or sealed.get('head_oid') != content.get('head')
                or certificate.get('provenance', {}).get('request_id') != content.get('request_id')
                or sealed.get('repository') != content.get('repository')
                or sealed.get('pr') != f"https://github.com/{content['repository']}/pull/{content['pr']}"
                or sealed.get('method') != content.get('method')
                or sealed.get('branch') != current_member.get('branch')
                or sealed.get('base') != current_member.get('base')
                or sealed.get('base_oid') != current_member.get('base_head')
                or sealed.get('retirement', {}).get('provider_marker') != request['expected_marker']):
            raise ValueError('Member retirement does not match coordinator attempt')
        context = {'branch': sealed['branch'], 'base': sealed['base'],
                   'target': sealed['base'], 'pr': sealed['pr']}
        observed, _, _ = self.api._github_pull_request_states(
            self.repo, 'gh', [{'number': member_goal}],
            {member_goal: {'repository_context': context}})
        facts = observed.get(member_goal, {})
        if (facts.get('merged') is not False or facts.get('updated_at') != request['expected_marker']
                or any(facts.get(name) != expected for name, expected in {
                    'repository': sealed['repository'], 'head_oid': sealed['head_oid'],
                    'base_oid': sealed['base_oid'], 'base_ref': sealed['base']}.items())):
            raise ValueError('Provider no longer confirms exact open member after retirement')
        plan = copy.deepcopy(plan)
        plan.pop('attempt', None); plan.pop('next_action', None)
        plan['revision'] += 1
        plan_ref = self.node_stack_store_plan(number, plan)
        control = {key: value for key, value in control.items()
                   if key not in {'attempt', 'dispatch_receipt'}}
        control['plan'] = plan_ref
        payload['stack_integration'] = control
        return self.node_persist(snapshot, payload, {'next_steps': [{
            'kind': 'stack_attempt_retired', 'goal': number,
            'plan_id': plan['plan_id'], 'revision': plan['revision'],
            'member_certificate': reference,
            'action': 'Reviewed no-effect attempt retired; prepare a fresh exact stack advance.'}]}, request)

    def node_stack_operation(self, snapshot, payload, request):
        operation = request['operation']; number = snapshot['number']
        if not (self.runtime or {}).get('root_id'):
            raise ValueError('Stack publication belongs to authenticated root')
        if operation == 'stack_prepare':
            allowed = {'operation', 'request_id', 'repository', 'target', 'method', 'members',
                       'continuation', 'expected_revision', 'members_complete'}
            required = {'operation', 'request_id', 'repository', 'target', 'method', 'members'}
            paged = ('members_complete' in request or 'continuation' in request
                     or 'expected_revision' in request)
            if (not required <= set(request) or set(request) - allowed
                    or request.get('method') not in {'merge', 'squash'}
                    or not isinstance(request.get('members'), list)
                    or (paged and len(request['members']) > stack_integration.STATUS_PAGE_SIZE)):
                raise ValueError('Stack prepare request is invalid')
            control = self.node_stack_control(snapshot)
            if control and not paged: raise ValueError('A stack plan already exists on this coordinator goal')
            if control:
                collecting, control = self.node_stack_plan(snapshot, control['plan'].get('hash') and
                                                            self.read_artifact(number, control['plan']).get('plan_id'))
                if collecting.get('state') not in {'collecting_membership', 'sealing'}:
                    raise ValueError('A sealed stack plan already exists on this coordinator goal')
                if request.get('expected_revision') != collecting.get('revision'):
                    raise ValueError('Stack collection revision is stale')
                scope = {key: request.get(key) for key in ('repository', 'target', 'method')}
                if digest(scope) != collecting.get('scope_digest'):
                    raise ValueError('Stack collection scope changed')
                expected_continuation = ('seal' if collecting.get('state') == 'sealing'
                                         else collecting.get('provider_cursor'))
                if request.get('continuation') != expected_continuation:
                    raise ValueError('Stack membership continuation is stale')
            else:
                collecting = None
                if paged and request.get('expected_revision') not in (None, 0):
                    raise ValueError('Initial stack collection revision is invalid')
            if not request['members'] and not (collecting and collecting.get('state') == 'sealing'):
                raise ValueError('Stack prepare requires a bounded member page')
            if paged and collecting and collecting.get('state') == 'sealing':
                if request.get('members'):
                    raise ValueError('Sealing continuation accepts no new members')
                if request.get('continuation') != 'seal':
                    raise ValueError('Stack sealing continuation is stale')
                plan = copy.deepcopy(collecting)
                ordered_entries = []
                for _ in range(stack_integration.STATUS_PAGE_SIZE):
                    if plan.get('seal_branch') is None: break
                    member = self.node_stack_index_get(number, plan['branch_root'], plan['seal_branch'])
                    if member is None: raise ValueError('Provider topology has no submitted member')
                    provider = self.node_stack_index_get(number, plan['provider_root'], plan['seal_branch'])
                    if provider is None or any(provider.get(name) != member.get(name)
                                               for name in ('pr', 'branch', 'base', 'head')):
                        raise ValueError('Provider topology differs from submitted member identity')
                    ordered_entries.append((str(plan['seal_index']), member))
                    plan['seal_index'] += 1
                    children = self.node_stack_provider_children(
                        number, plan['provider_base_root'], member['branch'])
                    if len(children) > 1:
                        raise ValueError('Provider topology is not a linear stack')
                    plan['seal_branch'] = children[0]['branch'] if children else None
                plan['ordered_root'] = self.node_stack_index_put_many(
                    number, plan.get('ordered_root'), ordered_entries)
                plan['revision'] += 1
                if plan.get('seal_branch') is not None:
                    if plan['seal_index'] >= plan['member_count']:
                        raise ValueError('Provider topology has an omitted descendant or cycle')
                    plan_ref = self.artifact(number, plan); payload['stack_integration'] = {'plan': plan_ref}
                    return self.node_persist(snapshot, payload, {'next_steps': [{
                        'kind': 'stack_validation', 'goal': number, 'plan_id': plan['plan_id'],
                        'revision': plan['revision'], 'validated': plan['seal_index'],
                        'continuation': 'seal', 'action': 'Bounded stack topology validation persisted.'}]}, request)
                if plan['seal_index'] != plan['member_count']:
                    raise ValueError('Submitted members are disconnected or incomplete')
                plan.update(state='prepared', current_index=0, current_status='pending')
                for key in ('seal_index', 'seal_branch', 'caller_complete', 'provider_complete',
                            'matched_count', 'goal_root', 'pr_root', 'provider_root',
                            'caller_base_root', 'provider_base_root', 'branch_root',
                            'provider_count'):
                    plan.pop(key, None)
                plan_ref = self.artifact(number, plan)
            elif paged:
                observed, response_bytes, provider_cursor, provider_rows = self.node_stack_provider_members(
                    request, cursor=request.get('continuation'), single_page=True)
                if provider_cursor is not None and provider_cursor == request.get('continuation'):
                    raise ValueError('Provider topology pagination did not advance')
                plan = copy.deepcopy(collecting) if collecting else {
                    'version': 2, 'state': 'collecting_membership',
                    'request_id': request['request_id'],
                    'scope_digest': digest({key: request.get(key) for key in ('repository', 'target', 'method')}),
                    'repository': request['repository'], 'target': request['target'],
                    'method': request['method'], 'revision': -1, 'member_count': 0,
                    'provider_count': 0, 'matched_count': 0, 'provider_cursor': None,
                    'branch_root': None, 'goal_root': None, 'pr_root': None,
                    'caller_base_root': None, 'provider_base_root': None, 'provider_root': None}
                plan['plan_id'] = plan.get('plan_id') or digest({'scope': plan['scope_digest'],
                    'root': self.runtime['root_id'], 'request': request['request_id']})
                matched = plan.get('matched_count', 0)
                for member in observed:
                    member_snapshot = self.node_snapshot(member['goal'])
                    if member_snapshot['payload']['operational']['leases']:
                        raise ValueError('Stack member has current worker ownership')
                    topology = self.node_stack_index_get(number, plan.get('provider_root'), member['branch'])
                    if topology is not None:
                        if any(topology.get(name) != member.get(name) for name in ('pr', 'branch', 'base', 'head')):
                            raise ValueError('Provider topology differs from submitted member identity')
                        matched += 1
                    plan['member_count'] += 1
                for root_name, key_name in (('branch_root', 'branch'), ('goal_root', 'goal'),
                                             ('pr_root', 'pr'), ('caller_base_root', 'base')):
                    plan[root_name] = self.node_stack_index_put_many(number, plan.get(root_name),
                        [(str(row[key_name]) if key_name != 'branch' else row[key_name], row)
                         for row in observed])
                for topology in provider_rows:
                    if None in (topology.get('pr'), topology.get('branch'), topology.get('base'), topology.get('head')):
                        raise ValueError('Provider topology page is incomplete')
                    member = self.node_stack_index_get(number, plan.get('branch_root'), topology['branch'])
                    if member is not None:
                        if any(topology.get(name) != member.get(name) for name in ('pr', 'branch', 'base', 'head')):
                            raise ValueError('Provider topology differs from submitted member identity')
                        matched += 1
                    plan['provider_count'] += 1
                plan['provider_root'] = self.node_stack_index_put_many(number, plan.get('provider_root'),
                    [(row['branch'], row) for row in provider_rows])
                plan['provider_base_root'] = self.node_stack_index_put_many(
                    number, plan.get('provider_base_root'),
                    [(self.node_stack_base_key(row['base'], row['branch']), row)
                     for row in provider_rows])
                plan['matched_count'] = matched; plan['provider_cursor'] = provider_cursor
                plan['caller_complete'] = request.get('members_complete') is True
                plan['provider_complete'] = provider_cursor is None
                plan['revision'] += 1
                complete = plan['caller_complete'] and plan['provider_complete']
                if complete:
                    bottom = self.node_stack_index_get(number, plan['caller_base_root'], plan['target'])
                    if bottom is None:
                        raise ValueError('Submitted members have no stack bottom at the target branch')
                    provider = self.node_stack_index_get(number, plan['provider_root'], bottom['branch'])
                    if provider is None or any(provider.get(name) != bottom.get(name)
                                               for name in ('pr', 'branch', 'base', 'head')):
                        raise ValueError('Stack bottom differs from complete provider topology')
                    plan.update(state='sealing', seal_branch=bottom['branch'], seal_index=0,
                                ordered_root=None, provider_cursor=None)
                plan_ref = self.artifact(number, plan); payload['stack_integration'] = {'plan': plan_ref}
                return self.node_persist(snapshot, payload, {'next_steps': [{
                    'kind': 'stack_validation' if complete else 'stack_collection', 'goal': number,
                    'plan_id': plan['plan_id'], 'revision': plan['revision'],
                    'member_count': plan['member_count'],
                    'continuation': 'seal' if complete else provider_cursor,
                    'action': ('Membership complete; continue bounded topology sealing.' if complete else
                               'Bounded caller and provider membership pages persisted.')} ]}, request)
            else:
                observed, response_bytes = self.node_stack_provider_members(request)
                for member in observed:
                    member_snapshot = self.node_snapshot(member['goal'])
                    if member_snapshot['payload']['operational']['leases']:
                        raise ValueError('Stack member has current worker ownership')
                plan = stack_integration.prepare_plan(request, observed=observed, revision=0)
                plan_ref = self.artifact(number, plan)
            receipt_value = {'type': 'stack_plan_receipt', 'content': {'plan_id': plan['plan_id']},
                             'producer': None, 'provenance': {'request_id': request['request_id'],
                             'request_hash': digest(request), 'root': self.runtime['root_id']}}
            receipt_ref = self.artifact(number, receipt_value)
            payload['stack_integration'] = {'plan': plan_ref}
            response = {'next_steps': [{'kind': 'stack_plan', 'goal': number,
                'plan_id': plan['plan_id'], 'revision': plan['revision'],
                'goals': [row['goal'] for row in (self.node_stack_order_page(
                    number, plan, 0, stack_integration.STATUS_PAGE_SIZE)
                    if plan.get('ordered_root') else plan['members'][:stack_integration.STATUS_PAGE_SIZE])],
                'continuation': (stack_integration.STATUS_PAGE_SIZE
                                 if plan.get('member_count', len(plan.get('members', []))) >
                                 stack_integration.STATUS_PAGE_SIZE else None),
                'plan': plan_ref, 'receipt': receipt_ref,
                'action': 'Provider-verified stack plan prepared.'}]}
            return self.node_persist(snapshot, payload, response, request)
        allowed = ({'operation', 'request_id', 'plan_id', 'cursor', 'limit'} if operation == 'stack_status'
                   else {'operation', 'request_id', 'plan_id', 'expected_revision', 'admin_authorization'})
        required = ({'operation', 'request_id', 'plan_id'} if operation == 'stack_status'
                    else {'operation', 'request_id', 'plan_id', 'expected_revision'})
        if not required <= set(request) or set(request) - allowed: raise ValueError('Stack operation contains unknown fields')
        plan, control = self.node_stack_plan(snapshot, request.get('plan_id'))
        plan = self.node_stack_plan_with_members(number, plan)
        if operation == 'stack_status':
            if (not isinstance(request.get('cursor', 0), int) or isinstance(request.get('cursor', 0), bool)
                    or request.get('cursor', 0) < 0
                    or not isinstance(request.get('limit', stack_integration.STATUS_PAGE_SIZE), int)
                    or isinstance(request.get('limit', stack_integration.STATUS_PAGE_SIZE), bool)
                    or not 1 <= request.get('limit', stack_integration.STATUS_PAGE_SIZE) <= stack_integration.STATUS_PAGE_SIZE):
                raise ValueError('Stack status cursor and limit are invalid')
            cursor = request.get('cursor', 0); limit = request.get('limit', stack_integration.STATUS_PAGE_SIZE)
            if plan.get('state') != 'prepared':
                return {'next_steps': [{'kind': 'stack_status', 'goal': number,
                    'plan_id': plan['plan_id'], 'revision': plan['revision'], 'members': [],
                    'continuation': ('seal' if plan.get('state') == 'sealing'
                                     else plan.get('provider_cursor')),
                    'member_count': plan.get('member_count', 0), 'state': plan.get('state'),
                    'action': 'Stack membership preparation is incomplete; no effect is available.'}]}
            if plan.get('ordered_root'):
                members = self.node_stack_order_page(number, plan, cursor, limit)
                page = {'members': members, 'continuation': (cursor + len(members)
                    if cursor + len(members) < plan['member_count'] else None)}
            else:
                page = stack_integration.status_page(plan, cursor=cursor, limit=limit)
            step = {'kind': 'stack_status', 'goal': number, 'plan_id': plan['plan_id'],
                    'revision': plan['revision'], 'members': page['members'],
                    'continuation': page['continuation'], 'action': 'Current durable stack state observed.'}
            for name in ('attempt', 'observation', 'dispatch_receipt'):
                if name in control: step[name] = control[name]
            if control.get('attempt'):
                pending_attempt = self.read_artifact(number, control['attempt'])
                if pending_attempt.get('type') == 'stack_attempt':
                    member_goal = pending_attempt['content']['goal']
                    observation = (self.read_artifact(number, control['observation'])
                                   if control.get('observation') else None)
                    if observation and observation.get('content', {}).get('goal') == member_goal:
                        pending_attempt = None
                if pending_attempt and pending_attempt.get('type') == 'stack_attempt':
                    member_goal = pending_attempt['content']['goal']
                    member_state = self.node_snapshot(member_goal)
                    member_ref = member_state['payload'].get('publication_certificate')
                    member_certificate = (member_state['artifacts'].get(member_ref.get('hash'))
                                          if isinstance(member_ref, dict) else None)
                    if (member_certificate and member_certificate.get('type') == 'publication_certificate'
                            and member_certificate.get('content', {}).get('stage') == 'retired'):
                        step['recovery_contract'] = {
                            'operation': 'stack_attempt_retire', 'request_id': '<unique request id>',
                            'plan_id': plan['plan_id'], 'expected_revision': plan['revision'],
                            'attempt': control['attempt'], 'member_certificate': member_ref,
                            'expected_marker': member_certificate['content']['retirement']['provider_marker']}
            current_root = self.runtime['root_id']
            refresh_key = (current_root, request.get('cursor', 0))
            prior_refresh = control.get('root_refresh', {})
            if (control.get('observation') and
                    (prior_refresh.get('root'), prior_refresh.get('cursor')) != refresh_key):
                refreshed_members = []
                status_members = page['members']
                for member in status_members:
                    member_snapshot = self.node_snapshot(member['goal'])
                    contexts = [ref for _, result in member_snapshot['projection']['current'].values()
                                for ref in result.get('outputs', {}).values()
                                if member_snapshot['artifacts'].get(ref.get('hash'), {}).get('type') == 'repository_context']
                    if len(contexts) == 1:
                        refreshed_members.append({'goal': member['goal'], 'context': contexts[0],
                                                  'head': member['head']})
                if len(refreshed_members) == len(status_members):
                    refresh = {
                        'root': current_root, 'members': refreshed_members,
                        'cursor': request.get('cursor', 0), 'continuation': page['continuation'],
                        'observed_goals': [row['goal'] for row in status_members
                                           if row.get('status') == 'observed'],
                        'plan_id': plan['plan_id'], 'observation': control['observation']}
                    # Refresh each member's normal publication gateway.  These
                    # checkpoints carry only administrative provenance; they
                    # neither add nor replace semantic Results.
                    for member in refreshed_members:
                        if member['goal'] == number: continue
                        member_snapshot = self.node_snapshot(member['goal'])
                        member_payload = copy.deepcopy(member_snapshot['payload'])
                        member_payload['stack_integration'] = {
                            'plan': self.node_ref(control['plan']['hash'], number),
                            'root_refresh': refresh}
                        internal = {'operation': 'stack_status',
                                    'request_id': request['request_id'] + '-refresh-' + str(member['goal']),
                                    'plan_id': plan['plan_id']}
                        self.node_persist(member_snapshot, member_payload, {'next_steps': [{
                            'kind': 'stack_status', 'goal': member['goal'], 'plan_id': plan['plan_id'],
                            'revision': plan['revision'],
                            'action': 'Current root publication context refreshed.'}]}, internal)
                    payload['stack_integration'] = {**control, 'root_refresh': refresh}
                    return self.node_persist(snapshot, payload, {'next_steps': [step]}, request)
            return {'next_steps': [step]}
        if plan.get('state') != 'prepared':
            raise ValueError('Stack topology must be completely sealed before any effect')
        if request.get('expected_revision') != plan.get('revision'):
            raise ValueError('Stack plan revision is stale')
        reconciled = []
        if plan.get('ordered_root'):
            rows = self.node_stack_order_page(number, plan, plan.get('current_index', 0), 1)
            if rows and plan.get('current_status') == 'observed':
                if not self.node_stack_semantic_merge(rows[0]):
                    raise ValueError('Observed stack merge requires current semantic phase Result reconciliation')
                reconciled.append(rows[0]['goal']); plan['current_index'] += 1
                plan['current_status'] = 'pending'
        else:
            for row in plan['members']:
                if row.get('status') != 'observed': continue
                if not self.node_stack_semantic_merge(row):
                    raise ValueError('Observed stack merge requires current semantic phase Result reconciliation')
                row['status'] = 'reconciled'; reconciled.append(row['goal']); break
        if reconciled:
            plan['revision'] += 1; plan_ref = self.node_stack_store_plan(number, plan)
            next_control = {key: value for key, value in control.items() if key != 'attempt'}
            next_control['plan'] = plan_ref; payload['stack_integration'] = next_control
            response = {'next_steps': [{'kind': 'stack_reconciliation', 'goal': number,
                'plan_id': plan['plan_id'], 'revision': plan['revision'], 'reconciled': reconciled,
                'action': 'Semantic merge evidence reconciled; invoke a new advance for the next effect.'}]}
            return self.node_persist(snapshot, payload, response, request)
        if plan.get('ordered_root'):
            current_rows = self.node_stack_order_page(number, plan, plan.get('current_index', 0), 1)
            current = current_rows[0] if current_rows else None
        else:
            current = next((row for row in plan['members'] if row.get('status') != 'reconciled'), None)
        if current is None:
            return {'next_steps': [{'kind': 'stack_status', 'goal': number, 'plan_id': plan['plan_id'],
                                    'revision': plan['revision'], 'action': 'Stack is fully reconciled.'}]}
        # Provider observation always precedes another effect. It can safely
        # recover an uncertain prior dispatch without current effect authority.
        # Observe every frozen PR directly. Merged ancestors legitimately
        # disappear from the provider's open-PR topology listing.
        selected = [{'number': current['goal']}]
        bodies = {current['goal']: {'repository_context': {'branch': current['branch'], 'base': current['base'],
                  'target': plan['target'], 'pr': f"https://github.com/{plan['repository']}/pull/{current['pr']}"}}
                  }
        raw, response_bytes, _ = self.api._github_pull_request_states(self.repo, 'gh', selected, bodies)
        for row in [current]:
            facts = raw.get(row['goal'], {})
            if any(facts.get(name) != row.get(expected) for name, expected in (
                    ('head_oid', 'head'), ('base_oid', 'base_head'), ('base_ref', 'base'))):
                raise ValueError('Stack member provider head or base changed')
        provider = {str(goal): ('merged' if facts.get('merged') else 'open') for goal, facts in raw.items()}
        if provider.get(str(current['goal'])) == 'merged':
            self.node_stack_verified_merge(raw[current['goal']])
            if plan.get('ordered_root'):
                plan['current_status'] = 'observed'; plan.pop('dispatch', None)
            else:
                plan = stack_integration.observe_attempt(plan, provider=provider)
            facts = raw[current['goal']]
            observation_value = {'type': 'stack_observation', 'content': {'plan_id': plan['plan_id'],
                'goal': current['goal'], 'head': current['head'], 'state': 'merged',
                'merge_commit': facts.get('merge_commit'), 'merged_at': facts.get('merged_at')},
                'producer': None, 'provenance': {'request_id': request['request_id'], 'root': self.runtime['root_id']}}
            observation_ref = self.artifact(number, observation_value)
            plan['revision'] += 1; plan_ref = self.node_stack_store_plan(number, plan)
            payload['stack_integration'] = {**control, 'plan': plan_ref, 'observation': observation_ref}
            response = {'next_steps': [{'kind': 'stack_observation', 'goal': number,
                'plan_id': plan['plan_id'], 'revision': plan['revision'], 'observation': observation_ref,
                'action': 'Provider merge observed; reconcile configured phase evidence before the next effect.'}]}
            return self.node_persist(snapshot, payload, response, request)
        index = plan['current_index'] if plan.get('ordered_root') else plan['members'].index(current)
        previous = (self.node_stack_order_page(number, plan, index - 1, 1)[0]
                    if plan.get('ordered_root') and index else
                    plan['members'][index - 1] if index else None)
        if previous is not None and not self.node_stack_semantic_merge(previous):
            raise ValueError('Prior stack member requires current semantic phase Result reconciliation')
        member_snapshot, publication = self.node_stack_member_snapshot(current)
        self.node_stack_release_authorized(current['goal'], publication['provider'])
        prior_ref = member_snapshot['payload'].get('publication_certificate')
        prior = (member_snapshot['artifacts'].get(prior_ref.get('hash'))
                 if isinstance(prior_ref, dict) else None)
        if prior and prior.get('type') == 'publication_certificate':
            if prior.get('content', {}).get('stage') == 'dispatch':
                attempt = (self.read_artifact(number, control['attempt'])
                           if control.get('attempt') else None)
                dispatched = (isinstance(attempt, dict)
                              and attempt.get('type') == 'stack_attempt'
                              and attempt.get('content', {}).get('goal') == current['goal']
                              and attempt.get('content', {}).get('request_id') ==
                              prior.get('provenance', {}).get('request_id'))
                if dispatched:
                    raise ValueError('Prior merge dispatch outcome is uncertain; reconcile exact provider effect before another request')
                # The coordinator never recorded its pre-command intent, so
                # this exact stack path could not have started the command.
                retired = copy.deepcopy(prior)
                retired['content']['stage'] = 'aborted'
                retired['content']['reason'] = 'coordinator intent absent'
                stored = self.artifact(current['goal'], retired)
                aborted_ref = self.node_ref(stored['hash'], current['goal'])
                aborted_payload = copy.deepcopy(member_snapshot['payload'])
                aborted_payload['publication_certificate'] = aborted_ref
                self.node_persist(member_snapshot, aborted_payload, {'next_steps': [{
                    'kind': 'checkpoint', 'goal': current['goal'],
                    'action': 'No coordinator dispatch intent was recorded; fresh request required.'}]},
                    {'operation': 'stack_advance',
                     'request_id': prior['provenance']['request_id'] + '-no-intent',
                     'plan_id': plan['plan_id'], 'expected_revision': plan['revision']})
                raise ValueError('No coordinator dispatch intent was recorded; use a fresh exact request')
            if prior.get('provenance', {}).get('request_id') == request['request_id']:
                raise ValueError('Prior private merge nonce is unavailable; observe the provider effect before starting a fresh request')
        if self.node_native_delivery(member_snapshot):
            candidate = self.node_candidate_state(member_snapshot)
            if (candidate['status'] != 'ready' or candidate['head_oid'] != current['head']
                    or candidate['branch'] != current['branch']):
                raise ValueError('Stack member differs from the exact reviewed Git candidate')
            if plan['method'] != 'merge':
                raise ValueError('Git-native candidate requires an ancestry-preserving merge')
        command = ['gh', 'pr', 'merge', str(current['pr']), '--' + plan['method'],
                   '--match-head-commit', current['head']]
        admin_required = publication['provider'].get('admin_required') is True
        if admin_required and request.get('admin_authorization') is None:
            raise ValueError('Provider requires explicit scoped admin authorization for this effect')
        if request.get('admin_authorization') is not None:
            admin_consent = self.node_stack_admin_authorized(
                member_snapshot, request['admin_authorization'], current, plan['method'])
            command.append('--admin')
        else:
            admin_consent = None
        # Seal the exact pre-effect decision on the member itself.  GitHub's
        # merge updates the PR timestamp, but that update must not erase the
        # reviews and approval which authorized this specific head and base.
        before = publication['provider']
        effect_marker = 'ZzzOps-Effect: ' + os.urandom(32).hex()
        certificate_value = {'type': 'publication_certificate', 'content': {
            'repository': self.repository, 'goal': current['goal'],
            'pr': f"https://github.com/{self.repository}/pull/{current['pr']}",
            'branch': current['branch'], 'base': current['base'],
            'head_oid': current['head'], 'base_oid': current['base_head'],
            'authorization': current['authorization'],
            'feedback_marker': publication['observed'].get('feedback_marker'),
            'review_verified': publication['observed'].get('review_verified'),
            'ci': publication['observed'].get('ci'),
            'effect_hash': digest(effect_marker),
            'policy': digest(self.project['policy']), 'method': plan['method'],
            'stage': 'sealed'},
            'producer': None, 'provenance': {'request_id': request['request_id'],
                                           'root': self.runtime['root_id']}}
        certificate_stored = self.artifact(current['goal'], certificate_value)
        certificate_ref = self.node_ref(certificate_stored['hash'], current['goal'])
        member_payload = copy.deepcopy(member_snapshot['payload'])
        member_payload['publication_certificate'] = certificate_ref
        self.node_persist(member_snapshot, member_payload, {'next_steps': [{
            'kind': 'checkpoint', 'goal': current['goal'], 'certificate': certificate_ref,
            'action': 'Exact pre-merge authority and provider identity sealed.'}]},
            {'operation': 'stack_advance', 'request_id': request['request_id'] + '-certificate',
             'plan_id': plan['plan_id'], 'expected_revision': plan['revision']})
        if current['goal'] == number:
            snapshot = self.node_snapshot(number); payload = copy.deepcopy(snapshot['payload'])
            if snapshot['envelope']['state'] == 'archived': snapshot['closed_administration'] = True
            control = self.node_stack_control(snapshot)
        fresh, _, _ = self.api._github_pull_request_states(self.repo, 'gh',
            [{'number': current['goal']}], {current['goal']: {'repository_context':
            {'branch': current['branch'], 'base': current['base'], 'target': plan['target'],
             'pr': certificate_value['content']['pr']}}})
        latest = fresh.get(current['goal'], {})
        if (latest.get('merged') or any(latest.get(name) != before.get(name) for name in
                ('repository', 'head_oid', 'base_oid', 'base_ref', 'updated_at',
                 'review_verified', 'checks_verified'))):
            raise ValueError('Provider changed after pre-merge certificate; review exact current head and feedback')
        dispatch_certificate = copy.deepcopy(certificate_value)
        dispatch_certificate['content']['stage'] = 'dispatch'
        dispatch_stored = self.artifact(current['goal'], dispatch_certificate)
        dispatch_ref = self.node_ref(dispatch_stored['hash'], current['goal'])
        member_snapshot = self.node_snapshot(current['goal'])
        member_payload = copy.deepcopy(member_snapshot['payload'])
        member_payload['publication_certificate'] = dispatch_ref
        self.node_persist(member_snapshot, member_payload, {'next_steps': [{
            'kind': 'checkpoint', 'goal': current['goal'], 'certificate': dispatch_ref,
            'action': 'Exact provider merge dispatch intent recorded.'}]},
            {'operation': 'stack_advance', 'request_id': request['request_id'] + '-dispatch',
             'plan_id': plan['plan_id'], 'expected_revision': plan['revision']})
        if current['goal'] == number:
            snapshot = self.node_snapshot(number); payload = copy.deepcopy(snapshot['payload'])
            if snapshot['envelope']['state'] == 'archived': snapshot['closed_administration'] = True
            control = self.node_stack_control(snapshot)
        attempt_value = {'type': 'stack_attempt', 'content': {'plan_id': plan['plan_id'],
            'request_id': request['request_id'], 'goal': current['goal'], 'head': current['head'],
            'repository': plan['repository'], 'pr': current['pr'], 'method': plan['method'],
            'command': command, 'admin_consent': admin_consent, 'state': 'intent'}, 'producer': None,
            'provenance': {'request_id': request['request_id'], 'root': self.runtime['root_id']}}
        attempt_ref = self.artifact(number, attempt_value)
        prior_attempt = self.read_artifact(number, control['attempt']) if control.get('attempt') else None
        if (isinstance(prior_attempt, dict) and prior_attempt.get('type') == 'stack_attempt'
                and prior_attempt.get('content', {}).get('goal') == current['goal']):
            # A committed intent without a terminal observation is ambiguous.
            # Never turn process loss into a duplicate provider effect.
            response = {'next_steps': [{'kind': 'stack_advance', 'goal': number,
                'plan_id': plan['plan_id'], 'revision': plan['revision'],
                'attempt': control['attempt'],
                'action': 'Unresolved durable intent requires provider observation; no effect was retried.'}]}
            return self.node_persist(snapshot, payload, response, request)
        intent_payload = copy.deepcopy(payload)
        intent_payload['stack_integration'] = {**control, 'attempt': attempt_ref}
        self.node_stack_followup_capacity(snapshot, intent_payload, plan, current, request, attempt_ref)
        intent_request = {'operation': 'stack_advance',
                          'request_id': request['request_id'] + '-intent',
                          'plan_id': plan['plan_id'], 'expected_revision': plan['revision']}
        self.node_persist(snapshot, intent_payload, {'next_steps': [{
            'kind': 'stack_advance', 'goal': number, 'plan_id': plan['plan_id'],
            'revision': plan['revision'], 'attempt': attempt_ref,
            'action': 'Durable provider intent recorded before dispatch.'}]}, intent_request)
        snapshot = self.node_snapshot(number); payload = copy.deepcopy(snapshot['payload'])
        if snapshot['envelope']['state'] == 'archived': snapshot['closed_administration'] = True
        observation_template = {'type': 'stack_observation', 'content': {
            'plan_id': plan['plan_id'], 'goal': current['goal'], 'head': current['head'],
            'state': 'merged', 'merge_commit': '0' * 40, 'merged_at': '0000-00-00T00:00:00Z'},
            'producer': None, 'provenance': {'request_id': request['request_id'],
            'root': self.runtime['root_id']}}
        if len(comment_store.canonical(observation_template).encode()) > comment_store.MAX_ARTIFACT_BYTES:
            raise ValueError('Post-effect observation exceeds durable storage capacity')
        dispatch_command = (command + ['--body', f"ZzzOps goal #{current['goal']}\n\n{effect_marker}"]
                            if plan['method'] != 'rebase' else command)
        uncertain, dispatch_result, dispatch_error = False, None, None
        try:
            remaining = self.api.provider_operation_remaining()
            timeout = remaining if isinstance(remaining, (int, float)) and remaining > 0 else 30
            dispatch_result = subprocess.run(dispatch_command, cwd=self.repo, capture_output=True, text=True,
                                             check=True, timeout=timeout)
        except (subprocess.SubprocessError, OSError) as exc:
            uncertain, dispatch_error = True, exc
        raw_diagnostic = ((dispatch_result.stdout or '') + (dispatch_result.stderr or '')
                          if dispatch_result is not None else str(dispatch_error or ''))
        raw_diagnostic = raw_diagnostic.replace(effect_marker, '<redacted merge marker>')
        diagnostic = raw_diagnostic.encode()[:stack_integration.MAX_DIAGNOSTIC].decode(errors='replace')
        dispatch_receipt = self.artifact(number, {'type': 'stack_dispatch_receipt', 'content': {
            'plan_id': plan['plan_id'], 'request_id': request['request_id'],
            'goal': current['goal'], 'head': current['head'],
            'status': 'uncertain' if uncertain else 'returned', 'diagnostic': diagnostic,
            'diagnostic_truncated': len(raw_diagnostic.encode()) > stack_integration.MAX_DIAGNOSTIC},
            'producer': None, 'provenance': {'request_id': request['request_id'],
            'root': self.runtime['root_id']}})
        after, after_bytes, _ = self.api._github_pull_request_states(self.repo, 'gh',
            [{'number': current['goal']}], {current['goal']: {'repository_context':
            {'branch': current['branch'], 'base': current['base'], 'target': plan['target'],
             'pr': f"https://github.com/{plan['repository']}/pull/{current['pr']}"}}})
        fact = after.get(current['goal'], {})
        if any(fact.get(name) != current.get(expected) for name, expected in (
                ('head_oid', 'head'), ('base_oid', 'base_head'), ('base_ref', 'base'))):
            raise ValueError('Post-dispatch provider identity differs from authorized effect')
        if not fact.get('merged') and not uncertain:
            raise ValueError('Provider did not confirm exact stack merge')
        if fact.get('merged'):
            self.node_stack_verified_merge(fact)
        plan['attempt'] = {'goal': current['goal'], 'head': current['head'],
                           'status': 'unresolved' if uncertain else 'dispatched'}
        plan['next_action'] = 'observe' if uncertain else 'reconcile'
        observation_ref = None
        if fact.get('merged'):
            if plan.get('ordered_root'):
                plan['current_status'] = 'observed'; plan.pop('dispatch', None)
            else:
                plan = stack_integration.observe_attempt(plan, provider={str(current['goal']): 'merged'})
            observation_ref = self.artifact(number, {'type': 'stack_observation', 'content': {
                'plan_id': plan['plan_id'], 'goal': current['goal'], 'head': current['head'],
                'state': 'merged', 'merge_commit': fact.get('merge_commit'), 'merged_at': fact.get('merged_at')},
                'producer': None, 'provenance': {'request_id': request['request_id'], 'root': self.runtime['root_id']}})
        plan['revision'] += 1; plan_ref = self.node_stack_store_plan(number, plan)
        control = {key: control[key] for key in ('root_refresh', 'observation') if key in control}
        control.update({'plan': plan_ref, 'attempt': attempt_ref,
                        'dispatch_receipt': dispatch_receipt})
        if observation_ref: control['observation'] = observation_ref
        payload['stack_integration'] = control
        step = {'kind': 'stack_advance', 'goal': number, 'plan_id': plan['plan_id'],
                'revision': plan['revision'], 'attempt': attempt_ref,
                'action': 'Stack effect is uncertain; observe provider state before retry.' if uncertain else
                          'Provider dispatch observed; reconcile semantic phase evidence.'}
        if observation_ref: step['observation'] = observation_ref
        return self.node_persist(snapshot, payload, {'next_steps': [step]}, request)

    def node_native_delivery(self, snapshot):
        """Treat any retained Git phase Result as requiring native commit delivery."""
        artifacts = snapshot['artifacts']
        for reference in snapshot['payload']['evidence']:
            result = artifacts.get(reference['hash'], {}).get('content', {})
            if result.get('node', {}).get('goal') != snapshot['number']:
                continue
            for output in result.get('outputs', {}).values():
                source = artifacts.get(output['hash'], {}).get('provenance', {}).get('source')
                if isinstance(source, dict) and artifacts.get(source.get('hash'), {}).get('kind') == 'git_phase_proof':
                    return True
        return False

    def node_native_sources(self, snapshot):
        """Pin native delivery to the current reviewed phase Results."""
        artifacts = snapshot['artifacts']
        sources = {'test_design': set(), 'implement': set()}
        for _, result in snapshot['projection']['current'].values():
            node = result.get('node', {})
            phase = node.get('node')
            if node.get('goal') != snapshot['number'] or phase not in sources:
                continue
            for output in result.get('outputs', {}).values():
                source = artifacts.get(output['hash'], {}).get('provenance', {}).get('source')
                proof = artifacts.get(source.get('hash'), {}) if isinstance(source, dict) else {}
                if proof.get('kind') == 'git_phase_proof':
                    sources[phase].add(proof['checkpoint']['result_commit'])
        if any(len(values) != 1 for values in sources.values()):
            raise ValueError('Git-native delivery requires one current reviewed RED and GREEN source')
        return {'test_source': next(iter(sources['test_design'])),
                'implementation_source': next(iter(sources['implement']))}

    def node_composition_source(self, snapshot):
        """Return the current Git-backed integration source, if applicable."""
        artifacts = snapshot['artifacts']
        sources = set()
        for _, result in snapshot['projection']['current'].values():
            node = result.get('node', {})
            if (node.get('goal') != snapshot['number']
                    or node.get('node') != 'integration_verification'
                    or result.get('non_applicability')):
                continue
            for output in result.get('outputs', {}).values():
                source = artifacts.get(output['hash'], {}).get('provenance', {}).get('source')
                proof = artifacts.get(source.get('hash'), {}) if isinstance(source, dict) else {}
                if proof.get('kind') == 'git_phase_proof':
                    sources.add(proof['checkpoint']['result_commit'])
        if len(sources) > 1:
            raise ValueError('Composition delivery has conflicting current Git sources')
        return next(iter(sources)) if sources else None

    def node_declared_compaction_inputs(self, snapshot):
        """Resolve reviewed Git publish declarations to current exact Result proofs."""
        declarations = {node['id']: node['git_publish'] for node in snapshot['graph']['nodes']
                        if 'git_publish' in node}
        if not declarations:
            return None
        goal, artifacts = snapshot['number'], snapshot['artifacts']
        current = {}
        for key, (_, result) in snapshot['projection']['current'].items():
            node = result.get('node', {})
            name = node.get('node')
            if node.get('goal') != goal or name not in declarations or result.get('non_applicability'):
                continue
            if name in current:
                raise ValueError('Git publication has multiple current Results for one declared node')
            output = result['outputs'].get(declarations[name]['output'])
            artifact = artifacts.get(output.get('hash'), {}) if isinstance(output, dict) else {}
            source = artifact.get('provenance', {}).get('source')
            proof = artifacts.get(source.get('hash'), {}) if isinstance(source, dict) else {}
            workspace = snapshot['workspaces'].get(key, {})
            if (proof.get('kind') != 'git_phase_proof' or not workspace.get('git_workspace')
                    or 'entry' not in workspace):
                continue
            current[name] = {'node': name, 'source': proof['checkpoint']['result_commit'],
                             'owned': workspace['entry']['owned']}
        by_series = {}
        for name, declaration in declarations.items():
            by_series.setdefault(declaration['series'], set()).add(name)
        selected = [series for series, members in by_series.items() if members <= current.keys()]
        if len(selected) != 1:
            raise ValueError('Git publication requires one complete reviewed declaration series')
        members = by_series[selected[0]]
        grouped = {}
        for name in members:
            declaration = declarations[name]
            key = declaration['group']
            row = grouped.setdefault(key, {'id': key, 'order': declaration['order'],
                'commit_type': declaration['commit_type'], 'summary': declaration['summary'],
                'nodes': []})
            if (row['order'], row['commit_type'], row['summary']) != (
                    declaration['order'], declaration['commit_type'], declaration['summary']):
                raise ValueError('Git publication group declarations disagree')
            row['nodes'].append(current[name])
        groups = sorted(grouped.values(), key=lambda group: group['order'])
        for group in groups:
            group['nodes'].sort(key=lambda member: member['node'])
        retained = {}
        prefix = f'refs/heads/zzzops/attempts/{goal}/'
        def add(ref, commit):
            if not isinstance(ref, str) or not isinstance(commit, str):
                raise ValueError('Git publication retained attempt identity is malformed')
            parts = ref.removeprefix(prefix).split('/') if ref.startswith(prefix) else []
            if len(parts) != 2 or parts[0] not in members:
                return
            if ref in retained and retained[ref] != commit:
                raise ValueError('Git publication retained attempt ref changed its commit')
            retained[ref] = commit
        for reference in snapshot['payload']['evidence']:
            result = artifacts.get(reference['hash'], {}).get('content', {})
            if (result.get('node', {}).get('goal') != goal
                    or result.get('node', {}).get('node') not in members):
                continue
            for output in result.get('outputs', {}).values():
                source = artifacts.get(output['hash'], {}).get('provenance', {}).get('source')
                proof = artifacts.get(source.get('hash'), {}) if isinstance(source, dict) else {}
                if proof.get('kind') == 'git_phase_proof':
                    add(proof['retained_ref'], proof['checkpoint']['result_commit'])
        for receipt in snapshot['payload']['operational']['receipts']:
            response = snapshot['resolve'](receipt['result'])
            for step in response.get('next_steps', []):
                attempt = step.get('retained_attempt')
                if attempt and step.get('kind') == 'checkpoint' and step.get('goal') == goal:
                    add(attempt['ref'], attempt['commit'])
        attempts = [{'ref': ref, 'commit': commit} for ref, commit in sorted(retained.items())]
        bases = []
        for member in groups[0]['nodes']:
            node_attempts = [attempt for attempt in attempts if attempt['ref'].startswith(
                prefix + member['node'] + '/')]
            bases.append(git_phase_state.compaction_base_from_attempts(self.repo,
                goal=goal, test_source=member['source'], attempts=node_attempts,
                remote='origin', phase=member['node']))
        oldest = [base for base in set(bases) if all(subprocess.run(
            ['git', 'merge-base', '--is-ancestor', base, other], cwd=self.repo,
            capture_output=True).returncode == 0 for other in bases)]
        if len(oldest) != 1:
            raise ValueError('Git publication first group has no unique base')
        return {'goal': goal, 'delivery_class': 'grouped', 'series': selected[0],
                'groups': groups, 'base_commit': oldest[0], 'retained_attempts': attempts}

    def node_compaction_inputs(self, snapshot):
        """Derive local candidate inputs from current proofs and retained history."""
        declared = self.node_declared_compaction_inputs(snapshot)
        if declared is not None:
            return declared
        composition_source = self.node_composition_source(snapshot)
        if composition_source is not None:
            artifacts = snapshot['artifacts']
            goal = snapshot['number']
            owned = []
            for key, (_, result) in snapshot['projection']['current'].items():
                if (result.get('node', {}).get('goal') == goal
                        and result['node'].get('node') == 'integration_verification'):
                    workspace = snapshot['workspaces'].get(key, {})
                    if not workspace.get('git_workspace') or 'entry' not in workspace:
                        raise ValueError('Composition requires current reviewed Git workspace scope')
                    owned.append(workspace['entry']['owned'])
            if len(owned) != 1:
                raise ValueError('Composition requires one current integration allocation')
            retained = {}
            prefix = f'refs/heads/zzzops/attempts/{goal}/integration_verification/'
            def add(ref, commit):
                if (not isinstance(ref, str) or not ref.startswith(prefix)
                        or not isinstance(commit, str)):
                    raise ValueError('Composition retained attempt identity is invalid')
                if ref in retained and retained[ref] != commit:
                    raise ValueError('Composition retained attempt ref has conflicting commits')
                retained[ref] = commit
            for reference in snapshot['payload']['evidence']:
                result = artifacts.get(reference['hash'], {}).get('content', {})
                if (result.get('node', {}).get('goal') != goal
                        or result['node'].get('node') != 'integration_verification'):
                    continue
                for output in result.get('outputs', {}).values():
                    source = artifacts.get(output['hash'], {}).get('provenance', {}).get('source')
                    proof = artifacts.get(source.get('hash'), {}) if isinstance(source, dict) else {}
                    if proof.get('kind') == 'git_phase_proof':
                        add(proof['retained_ref'], proof['checkpoint']['result_commit'])
            for receipt in snapshot['payload']['operational']['receipts']:
                response = snapshot['resolve'](receipt['result'])
                for step in response.get('next_steps', []):
                    attempt = step.get('retained_attempt')
                    if attempt and step.get('kind') == 'checkpoint' and step.get('goal') == goal:
                        add(attempt['ref'], attempt['commit'])
            attempts = [{'ref': ref, 'commit': commit} for ref, commit in sorted(retained.items())]
            base = git_phase_state.compaction_base_from_attempts(self.repo, goal=goal,
                test_source=composition_source, attempts=attempts, remote='origin',
                phase='integration_verification')
            return {'goal': goal, 'delivery_class': 'composition', 'base_commit': base,
                    'integration_source': composition_source, 'integration_owned': owned[0],
                    'retained_attempts': attempts}
        sources = self.node_native_sources(snapshot)
        artifacts = snapshot['artifacts']
        goal = snapshot['number']
        owned = {'test_design': [], 'implement': []}
        for key, (_, result) in snapshot['projection']['current'].items():
            phase = result.get('node', {}).get('node')
            if result.get('node', {}).get('goal') != goal or phase not in owned:
                continue
            workspace = snapshot['workspaces'].get(key, {})
            if not workspace.get('git_workspace') or 'entry' not in workspace:
                raise ValueError('Compaction requires current reviewed Git workspace scope')
            owned[phase].append(workspace['entry']['owned'])
        if any(len(scopes) != 1 for scopes in owned.values()):
            raise ValueError('Compaction requires one current RED and GREEN allocation')
        retained = {}
        prefix = f'refs/heads/zzzops/attempts/{goal}/'
        def add(ref, commit):
            if (not isinstance(ref, str) or not ref.startswith((prefix + 'test_design/', prefix + 'implement/'))
                    or not isinstance(commit, str)):
                raise ValueError('Compaction retained attempt identity is invalid')
            if ref in retained and retained[ref] != commit:
                raise ValueError('Compaction retained attempt ref has conflicting commits')
            retained[ref] = commit
        for reference in snapshot['payload']['evidence']:
            result = artifacts.get(reference['hash'], {}).get('content', {})
            if result.get('node', {}).get('goal') != goal or result['node'].get('node') not in owned:
                continue
            for output in result.get('outputs', {}).values():
                source = artifacts.get(output['hash'], {}).get('provenance', {}).get('source')
                proof = artifacts.get(source.get('hash'), {}) if isinstance(source, dict) else {}
                if proof.get('kind') == 'git_phase_proof':
                    add(proof['retained_ref'], proof['checkpoint']['result_commit'])
        for receipt in snapshot['payload']['operational']['receipts']:
            response = snapshot['resolve'](receipt['result'])
            for step in response.get('next_steps', []):
                attempt = step.get('retained_attempt')
                if attempt and step.get('kind') == 'checkpoint' and step.get('goal') == goal:
                    add(attempt['ref'], attempt['commit'])
        attempts = [{'ref': ref, 'commit': commit} for ref, commit in sorted(retained.items())]
        test_attempts = [row for row in attempts if row['ref'].startswith(prefix + 'test_design/')]
        base = git_phase_state.compaction_base_from_attempts(self.repo, goal=goal,
            test_source=sources['test_source'], attempts=test_attempts, remote='origin')
        return {'goal': goal, 'delivery_class': 'leaf', 'base_commit': base, **sources,
                'test_owned': owned['test_design'][0],
                'implementation_owned': owned['implement'][0],
                'retained_attempts': attempts}

    def node_grouped_source(self, inputs):
        """Find the exact latest source commit of the final declared group."""
        sources = [member['source'] for member in inputs['groups'][-1]['nodes']]
        latest = [candidate for candidate in set(sources) if all(subprocess.run(
            ['git', 'merge-base', '--is-ancestor', other, candidate], cwd=self.repo,
            capture_output=True).returncode == 0 for other in sources)]
        if len(latest) != 1:
            raise ValueError('Git publication final group has no unique source tip')
        return latest[0]

    def node_compaction_authorization(self, snapshot, reference):
        """Require the current reviewed repository grant for this delivery."""
        root = (self.runtime or {}).get('root_id')
        if not root:
            raise ValueError('Candidate compaction belongs to authenticated root')
        projection, artifacts = snapshot['projection'], snapshot['artifacts']
        owners = {output['hash']: (key, result, output)
                  for key, (_, result) in projection['current'].items()
                  for output in result['outputs'].values()}
        owner = owners.get(reference.get('hash')) if isinstance(reference, dict) else None
        if not owner or owner[2] != reference:
            raise ValueError('Candidate compaction requires current repository authorization')
        key, result, _ = owner
        artifact = artifacts[reference['hash']]
        value = artifact.get('content', {})
        if (artifact.get('type') != 'repository_authorization'
                or result['executor'] != root
                or projection['states'][key]['contract']['executor']['role'] != 'root'
                or value.get('decision') != 'approved'
                or not self.node_authorization_policy_matches(value, artifact, result, artifacts)):
            raise ValueError('Candidate compaction requires current approved root repository authorization')
        manifest = value.get('manifest')
        selected = owners.get(manifest.get('hash')) if isinstance(manifest, dict) else None
        if (not selected or selected[2] != manifest
                or artifacts[manifest['hash']].get('type') != 'delivery_candidate'
                or artifacts[manifest['hash']]['content'].get('delivery_class') not in {'leaf', 'atomic', 'composition'}):
            raise ValueError('Candidate compaction requires the current delivery selection')
        delivery_class = artifacts[manifest['hash']]['content']['delivery_class']
        declared = self.node_declared_compaction_inputs(snapshot)
        source_phases = ({member['node'] for member in declared['groups'][-1]['nodes']}
                         if declared is not None else
                         {'integration_verification' if delivery_class == 'composition' else 'implement'})
        candidate = artifacts[manifest['hash']]['content'].get('candidate')
        current_sources = [output for _, (_, result) in projection['current'].items()
            if result.get('node', {}).get('goal') == snapshot['number']
            and result['node'].get('node') in source_phases
            for output in result['outputs'].values()]
        if candidate not in current_sources:
            raise ValueError('Candidate compaction selection differs from current reviewed source')
        review_input = ('approved_integration_reviews' if delivery_class == 'composition'
                        else 'approved_implementation_reviews')
        reviews = []
        for binding in result.get('inputs', []):
            if binding.get('name') != review_input:
                continue
            value = artifacts.get(binding['source']['hash'], {}).get('content')
            for part in binding.get('path', []):
                value = value.get(part) if isinstance(value, dict) else None
            reviews.append(value)
        if (len(reviews) != 1 or not isinstance(reviews[0], dict) or not reviews[0]
                or any(not isinstance(row, dict) or row.get('decision') != 'approved'
                       for row in reviews[0].values())):
            raise ValueError('Candidate compaction requires approved independent reviews')
        return reference

    def node_compact_candidate(self, snapshot, payload, request):
        """Compact an authorized goal candidate with an exact replayable receipt."""
        if set(request) != {'operation', 'request_id', 'authorization'}:
            raise ValueError('Candidate compaction request has unknown authority fields')
        if payload['operational']['leases']:
            raise ValueError('Candidate compaction requires reconciled worker ownership')
        reference = self.node_compaction_authorization(snapshot, request['authorization'])
        identity = reference['hash'] if isinstance(reference, dict) else None
        if not isinstance(identity, str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', identity):
            raise ValueError('Candidate compaction requires exact authorization identity')
        inputs = self.node_compaction_inputs(snapshot)
        composition = inputs.get('delivery_class') == 'composition'
        grouped = inputs.get('delivery_class') == 'grouped'
        source = (self.node_grouped_source(inputs) if grouped else
                  inputs['integration_source'] if composition else inputs['implementation_source'])
        attempt = identity[7:39]
        observed = managed_worktrees.inspect_attempt_worktree(
            self.repo, goal=snapshot['number'], node='candidate', attempt=attempt)
        if observed['status'] == 'missing':
            managed_worktrees.prepare_worktree(self.repo, goal=snapshot['number'],
                node='candidate', attempt=attempt,
                base_commit=source)
            observed = managed_worktrees.inspect_attempt_worktree(
                self.repo, goal=snapshot['number'], node='candidate', attempt=attempt)
        if observed['status'] != 'clean':
            raise ValueError('Candidate worktree is dirty; preserve it for exact recovery')
        path = Path(observed['path'])
        if grouped:
            preview = git_phase_state.preview_grouped_candidate(path,
                goal=snapshot['number'], base_commit=inputs['base_commit'],
                groups=inputs['groups'], retained_attempts=inputs['retained_attempts'],
                remote='origin')
            result = git_phase_state.apply_grouped_candidate(path, preview,
                groups=inputs['groups'], retained_attempts=inputs['retained_attempts'],
                remote='origin')
            head = result['head_commit']
            phase_commits = {'group_commits': result['commits']}
        elif composition:
            preview = git_phase_state.preview_single_commit_candidate(path,
                goal=snapshot['number'], base_commit=inputs['base_commit'],
                source_commit=source, owned_paths=inputs['integration_owned'],
                retained_attempts=inputs['retained_attempts'], remote='origin')
            result = git_phase_state.apply_single_commit_candidate(path, preview,
                owned_paths=inputs['integration_owned'],
                retained_attempts=inputs['retained_attempts'], remote='origin')
            head = result['candidate_commit']
            phase_commits = {}
        else:
            preview = git_phase_state.preview_two_commit_candidate(path,
                goal=snapshot['number'], base_commit=inputs['base_commit'],
                test_source=inputs['test_source'], implementation_source=source,
                test_owned=inputs['test_owned'], implementation_owned=inputs['implementation_owned'],
                retained_attempts=inputs['retained_attempts'], remote='origin')
            result = git_phase_state.apply_two_commit_candidate(path, preview,
                test_owned=inputs['test_owned'], implementation_owned=inputs['implementation_owned'],
                retained_attempts=inputs['retained_attempts'], remote='origin')
            head = result['implementation_commit']
            phase_commits = {'test_commit': result['test_commit']}
        response = {'next_steps': [{'kind': 'candidate_compacted', 'goal': snapshot['number'],
            'authorization': reference, 'branch': observed['branch'],
            'base_commit': inputs['base_commit'], **phase_commits,
            'head_oid': head, 'outcome': result['outcome'],
            'action': 'Publish this exact managed candidate head, then obtain fresh head-bound independent review and CI.'}]}
        return self.node_persist(snapshot, payload, response, request)

    def node_candidate_state(self, snapshot):
        """Infer the approved candidate's readiness from its managed Git branch."""
        artifacts = snapshot['artifacts']
        authorities = [output for _, (_, result) in snapshot['projection']['current'].items()
            for output in result['outputs'].values()
            if artifacts[output['hash']].get('type') == 'repository_authorization']
        approved = []
        for reference in authorities:
            try:
                approved.append(self.node_compaction_authorization(snapshot, reference))
            except ValueError:
                continue
        if len(approved) != 1:
            raise ValueError('Git-native publication requires one current approved repository authorization')
        reference = approved[0]
        inputs = self.node_compaction_inputs(snapshot)
        composition = inputs.get('delivery_class') == 'composition'
        grouped = inputs.get('delivery_class') == 'grouped'
        sources = ({} if grouped else
                   {'integration_source': inputs['integration_source']} if composition
                   else self.node_native_sources(snapshot))
        source = (self.node_grouped_source(inputs) if grouped else
                  sources['integration_source'] if composition else sources['implementation_source'])
        attempt = reference['hash'][7:39]
        observed = managed_worktrees.inspect_attempt_worktree(self.repo,
            goal=snapshot['number'], node='candidate', attempt=attempt)
        if observed['status'] == 'missing' or (observed['status'] == 'clean'
                and observed['head'] == source):
            return {'status': 'needs_compaction', 'authorization': reference}
        if observed['status'] != 'clean':
            raise ValueError('Managed candidate worktree is dirty or changed')
        if grouped:
            git_phase_state.preview_grouped_candidate(Path(observed['path']),
                goal=snapshot['number'], base_commit=inputs['base_commit'],
                groups=inputs['groups'], retained_attempts=inputs['retained_attempts'],
                remote='origin')
            git_phase_state.verify_grouped_candidate(Path(observed['path']),
                goal=snapshot['number'], base_commit=inputs['base_commit'],
                head_commit=observed['head'], groups=inputs['groups'],
                retained_attempts=inputs['retained_attempts'], remote='origin')
            current, candidate = {}, {}
        elif composition:
            git_phase_state.preview_single_commit_candidate(Path(observed['path']),
                goal=snapshot['number'], base_commit=inputs['base_commit'],
                source_commit=source, owned_paths=inputs['integration_owned'],
                retained_attempts=inputs['retained_attempts'], remote='origin')
            candidate = git_phase_state.verify_single_commit_candidate(Path(observed['path']),
                goal=snapshot['number'], base_commit=inputs['base_commit'],
                head_commit=observed['head'])
            current = {'source_commit': source}
        else:
            git_phase_state.preview_two_commit_candidate(Path(observed['path']),
                goal=snapshot['number'], base_commit=inputs['base_commit'],
                test_source=inputs['test_source'], implementation_source=source,
                test_owned=inputs['test_owned'], implementation_owned=inputs['implementation_owned'],
                retained_attempts=inputs['retained_attempts'], remote='origin')
            candidate = git_phase_state.verify_two_commit_candidate(Path(observed['path']),
                goal=snapshot['number'], base_commit=inputs['base_commit'],
                head_commit=observed['head'], test_owned=inputs['test_owned'])
            current = sources
        if any(candidate[name] != value for name, value in current.items()):
            raise ValueError('Managed candidate differs from current reviewed source commits')
        return {'status': 'ready', 'authorization': reference,
                'path': observed['path'], 'branch': observed['branch'],
                'head_oid': observed['head']}

    def node_cleanup_merge_facts(self, snapshot):
        """Confirm the observed merge remains in its exact remote target."""
        merged = {digest(state['publication']['provider']): state['publication']['provider']
                  for state in snapshot['projection']['states'].values()
                  if state['node']['goal'] == snapshot['number']
                  and state.get('publication', {}).get('provider', {}).get('merged')}
        if len(merged) != 1:
            raise ValueError('Local cleanup requires one observed merged candidate')
        facts = next(iter(merged.values()))
        integrated, head, base_ref = (facts.get(name)
            for name in ('merge_commit', 'head_oid', 'base_ref'))
        if (not all(isinstance(oid, str) and re.fullmatch(r'[0-9a-f]{40}', oid)
                    for oid in (integrated, head))
                or not isinstance(base_ref, str)
                or not re.fullmatch(r'[A-Za-z0-9_./-]+', base_ref)
                or base_ref.startswith(('-', '/')) or '..' in base_ref.split('/')):
            raise ValueError('Local cleanup requires exact merged provider identities')
        fetched = subprocess.run(['git', 'fetch', '--no-tags', 'origin',
                                  'refs/heads/' + base_ref], cwd=self.repo,
                                 capture_output=True, text=True)
        if fetched.returncode:
            raise ValueError('Cannot fetch the exact merged target for local cleanup')
        target = subprocess.run(['git', 'rev-parse', 'FETCH_HEAD'], cwd=self.repo,
                                capture_output=True, text=True, check=True).stdout.strip()
        if subprocess.run(['git', 'merge-base', '--is-ancestor', integrated, target],
                          cwd=self.repo, capture_output=True).returncode:
            raise ValueError('Observed merge commit is not in the current target branch')
        return integrated, head

    def node_cleanup_delivered_worktrees(self, snapshot):
        """Retry local cleanup only after exact merged provider and Git facts."""
        number = snapshot['number']
        integrated, head = self.node_cleanup_merge_facts(snapshot)
        inputs = self.node_compaction_inputs(snapshot)
        delivery_class = inputs.get('delivery_class', 'leaf')
        if delivery_class == 'grouped':
            git_phase_state.verify_grouped_candidate(self.repo, goal=number,
                base_commit=inputs['base_commit'], head_commit=head,
                groups=inputs['groups'], retained_attempts=inputs['retained_attempts'],
                remote='origin')
        else:
            verifier = (git_phase_state.verify_single_commit_candidate
                        if delivery_class == 'composition'
                        else git_phase_state.verify_two_commit_candidate)
            verification_options = ({} if delivery_class == 'composition'
                                    else {'test_owned': inputs.get('test_owned')})
            verifier(self.repo, goal=number, base_commit=inputs['base_commit'],
                     head_commit=head, **verification_options)
        if subprocess.run(['git', 'merge-base', '--is-ancestor', head, integrated],
                          cwd=self.repo, capture_output=True).returncode:
            raise ValueError('Exact reviewed candidate is not in the observed merge commit')
        removed, preserved = 0, 0
        for attempt in inputs['retained_attempts']:
            ref, commit = attempt['ref'], attempt['commit']
            phases = ('|'.join(re.escape(member['node']) for group in inputs['groups']
                       for member in group['nodes']) if delivery_class == 'grouped' else
                       'integration_verification' if delivery_class == 'composition'
                       else 'test_design|implement')
            match = re.fullmatch(
                rf'refs/heads/zzzops/attempts/{number}/({phases})/([0-9a-f]{{32}})', ref)
            if not match:
                raise ValueError('Retained attempt identity changed before local cleanup')
            node, attempt_id = match.groups()
            local = managed_worktrees.inspect_attempt_worktree(self.repo,
                goal=number, node=node, attempt=attempt_id)
            if local['status'] == 'missing':
                continue
            if local['status'] != 'clean':
                preserved += 1
                continue
            managed_worktrees.cleanup_delivered_attempt_worktree(self.repo, goal=number,
                node=node, attempt=attempt_id, expected_head=commit,
                delivery_base=inputs['base_commit'], delivery_head=head,
                integrated_commit=integrated, remote='origin', retained_ref=ref,
                delivery_class=delivery_class,
                test_owned=inputs.get('test_owned') if delivery_class == 'leaf' else None,
                groups=inputs.get('groups'), retained_attempts=inputs['retained_attempts'])
            removed += 1
        authorities = [output for _, (_, result) in snapshot['projection']['current'].items()
            for output in result['outputs'].values()
            if snapshot['artifacts'][output['hash']].get('type') == 'repository_authorization']
        approved = []
        for reference in authorities:
            try:
                if self.node_compaction_authorization(snapshot, reference) == reference:
                    approved.append(reference)
            except ValueError:
                continue
        if len(approved) != 1:
            raise ValueError('Current candidate authorization is unavailable for local cleanup')
        candidate_id = approved[0]['hash'][7:39]
        candidate = managed_worktrees.inspect_attempt_worktree(self.repo,
            goal=number, node='candidate', attempt=candidate_id)
        if candidate['status'] == 'dirty':
            preserved += 1
        elif candidate['status'] == 'clean':
            managed_worktrees.cleanup_delivered_candidate_worktree(self.repo,
                goal=number, attempt=candidate_id, expected_head=head,
                delivery_base=inputs['base_commit'], integrated_commit=integrated,
                delivery_class=delivery_class,
                test_owned=inputs.get('test_owned') if delivery_class == 'leaf' else None,
                groups=inputs.get('groups'), retained_attempts=inputs['retained_attempts'])
            removed += 1
        readonly_removed, readonly_preserved = self.node_cleanup_readonly_attempts(snapshot, integrated)
        removed += readonly_removed
        preserved += readonly_preserved
        return {'status': 'complete' if not preserved else 'preserved_dirty',
                'removed': removed, 'preserved_dirty': preserved}

    def node_readonly_attempts(self, snapshot):
        """Recover bounded read-only identities from immutable start receipts."""
        number = snapshot['number']
        readonly = {}
        for receipt in snapshot['payload']['operational']['receipts']:
            response = snapshot['resolve'](receipt['result'])
            for step in response.get('next_steps', []):
                lease = step.get('lease') if step.get('kind') == 'perform' else None
                acquisition = lease.get('acquisition', {}) if isinstance(lease, dict) else {}
                if 'read_commit' not in acquisition:
                    continue
                node = lease.get('node', {})
                attempt = lease.get('attempt')
                commit = acquisition['read_commit']
                if (node.get('goal') != number or not isinstance(node.get('node'), str)
                        or not isinstance(attempt, str) or not re.fullmatch(r'[0-9a-f]{32}', attempt)
                        or not isinstance(commit, str) or not re.fullmatch(r'[0-9a-f]{40}', commit)):
                    raise ValueError('Read-only cleanup receipt identity is malformed')
                identity = (node['node'], attempt)
                if identity in readonly and readonly[identity] != commit:
                    raise ValueError('Read-only cleanup receipt has conflicting base commits')
                readonly[identity] = commit
        return readonly

    def node_cleanup_readonly_attempts(self, snapshot, integrated, readonly=None):
        """Retire exact clean read-only attempts after their input remains reachable."""
        number = snapshot['number']
        readonly = self.node_readonly_attempts(snapshot) if readonly is None else readonly
        removed, preserved = 0, 0
        for (node, attempt), commit in sorted(readonly.items()):
            local = managed_worktrees.inspect_attempt_worktree(self.repo,
                goal=number, node=node, attempt=attempt)
            if local['status'] == 'missing':
                continue
            if local['status'] != 'clean':
                preserved += 1
                continue
            managed_worktrees.cleanup_delivered_readonly_worktree(self.repo,
                goal=number, node=node, attempt=attempt, expected_head=commit,
                integrated_commit=integrated)
            removed += 1
        return removed, preserved

    def node_cleanup_delivered_readonly_worktrees(self, snapshot):
        """Clean read-only attempts for a legacy delivery after its provider merge."""
        readonly = self.node_readonly_attempts(snapshot)
        if not readonly:
            return {'status': 'complete', 'removed': 0, 'preserved_dirty': 0}
        integrated, _ = self.node_cleanup_merge_facts(snapshot)
        removed, preserved = self.node_cleanup_readonly_attempts(snapshot, integrated, readonly)
        return {'status': 'complete' if not preserved else 'preserved_dirty',
                'removed': removed, 'preserved_dirty': preserved}

    def node_publication_attempt_retire(self, snapshot, payload, request):
        """Explicitly retire an uncertain intent only after exact human review."""
        if not (self.runtime or {}).get('root_id'):
            raise ValueError('Publication attempt retirement belongs to authenticated root')
        required = {'operation', 'request_id', 'certificate', 'expected_head',
                    'expected_marker', 'approved_by', 'attribution', 'reason'}
        if set(request) != required or not explicit_approval(request.get('approved_by')):
            raise ValueError('Exact human approval is required to retire an uncertain merge intent')
        if any(not isinstance(request.get(name), str) or not request[name].strip()
               for name in ('attribution', 'reason', 'expected_head', 'expected_marker')):
            raise ValueError('Attempt retirement requires exact provider facts and approval attribution')
        reference = payload.get('publication_certificate')
        if reference != request['certificate']:
            raise ValueError('Publication certificate changed before retirement')
        certificate = snapshot['artifacts'].get(reference.get('hash')) if isinstance(reference, dict) else None
        if (not certificate or certificate.get('type') != 'publication_certificate'
                or reference != self.node_ref(digest(certificate), snapshot['number'])
                or certificate.get('content', {}).get('stage') != 'dispatch'):
            raise ValueError('No exact uncertain dispatch certificate can be retired')
        sealed = certificate['content']
        context = {'branch': sealed['branch'], 'base': sealed['base'],
                   'target': sealed['base'], 'pr': sealed['pr']}
        observed, _, _ = self.api._github_pull_request_states(
            self.repo, 'gh', [{'number': snapshot['number']}],
            {snapshot['number']: {'repository_context': context}})
        facts = observed.get(snapshot['number'], {})
        if (facts.get('merged') is not False or any(facts.get(name) != expected
                for name, expected in {'repository': sealed['repository'],
                                       'head_oid': sealed['head_oid'],
                                       'base_oid': sealed['base_oid'],
                                       'base_ref': sealed['base']}.items())
                or facts.get('head_oid') != request['expected_head']
                or facts.get('updated_at') != request['expected_marker']):
            raise ValueError('Provider is not confirmed open at the exact reviewed head, base and marker')
        retired = copy.deepcopy(certificate)
        retired['content']['stage'] = 'retired'
        retired['content']['retirement'] = {
            'source': reference, 'approved_by': request['approved_by'],
            'attribution': request['attribution'], 'reason': request['reason'],
            'provider_marker': facts['updated_at']}
        stored = self.artifact(snapshot['number'], retired)
        retired_ref = self.node_ref(stored['hash'], snapshot['number'])
        payload['publication_certificate'] = retired_ref
        return self.node_persist(snapshot, payload, {'next_steps': [{
            'kind': 'checkpoint', 'goal': snapshot['number'],
            'certificate': retired_ref,
            'action': 'Uncertain attempt retired by exact human approval; reacquire current publication authority before any new effect.'}]}, request)

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
                if len(match) != 1: raise ValueError('Stale provider publication authorization; retry after provider reconciliation')
                publication = match[0][1]; self.node_ci_required(publication['observed'])
        else:
            candidates = [state['publication'] for state in projection['states'].values() if state.get('publication', {}).get('provider', {}).get('merged')]
            if not candidates: raise ValueError('Current provider merge observation is unavailable')
            publication = candidates[0]
            if request.get('expected_digest') != digest(snapshot['envelope']) or request.get('expected_merge') != digest(publication['provider']): raise ValueError('Stale expected source digest or merge evidence')
        if operation == 'integrate':
            unresolved = projection.get('unresolved_obligations')
            if not isinstance(unresolved, list):
                raise ValueError('Finding resolution inventory is unavailable before integration')
            pending_findings = [identity for goal, identity in unresolved if goal == snapshot['number']]
            if pending_findings:
                raise ValueError('Integration has unresolved findings: ' + ', '.join(sorted(pending_findings)))
            facts = publication['provider']
            if request.get('expected_head') != facts['head_oid']: raise ValueError('Expected head differs from current provider head')
            native = self.node_native_delivery(snapshot)
            if native:
                candidate = self.node_candidate_state(snapshot)
                if (candidate['status'] != 'ready' or candidate['head_oid'] != facts['head_oid']
                        or candidate['branch'] != publication['context']['branch']):
                    raise ValueError('Integration differs from the exact reviewed Git candidate')
            release_policy = policy_section(self.project, 'git_review_release')['configuration'].get('release_planning')
            if isinstance(release_policy, dict) and release_policy.get('enabled'):
                release_plan = self.api.GitHubReleasePlanAdapter(self.repo, self.repository).read(self.repository)
                if release_plan is None: raise ValueError('Release plan is missing; integration is blocked')
                target = self.api._releases.target_release(release_plan, snapshot['number'])
                integration = self.api.GitHubReleasePlanAdapter(self.repo, self.repository).observe_integration(
                    self.repository, snapshot['number'], facts['head_oid'])
                decision = self.api._releases.authorize_integration(
                    {'key': snapshot['number'], 'target_release': target,
                     'forbidden_commits': integration['forbidden_commits']}, release_plan,
                    source_branch=facts.get('base_ref', ''),
                    source_ancestors=set(integration['source_ancestors']))
                if decision['status'] != 'authorized':
                    raise ValueError(f"Release integration blocked: {decision['code']}")
            if not facts.get('merged'):
                context = publication['context']
                prior_ref = snapshot['payload'].get('publication_certificate')
                prior = (snapshot['artifacts'].get(prior_ref.get('hash'))
                         if isinstance(prior_ref, dict) else None)
                if prior and prior.get('type') == 'publication_certificate':
                    if prior.get('content', {}).get('stage') == 'dispatch':
                        raise ValueError('Prior merge dispatch outcome is uncertain; reconcile exact provider effect before another request')
                    if prior.get('provenance', {}).get('request_id') == request['request_id']:
                        raise ValueError('Prior private merge nonce is unavailable; observe the provider effect before starting a fresh request')
                effect_marker = 'ZzzOps-Effect: ' + os.urandom(32).hex()
                certificate_value = {'type': 'publication_certificate', 'content': {
                    'repository': self.repository, 'goal': snapshot['number'],
                    'pr': context['pr'], 'branch': context['branch'], 'base': context['base'],
                    'head_oid': facts['head_oid'], 'base_oid': facts['base_oid'],
                    'authorization': request['authorization'],
                    'feedback_marker': publication['observed'].get('feedback_marker'),
                    'review_verified': publication['observed'].get('review_verified'),
                    'ci': publication['observed'].get('ci'),
                    'effect_hash': digest(effect_marker),
                    'policy': digest(self.project['policy']),
                    'method': 'merge' if native else 'squash', 'stage': 'sealed'},
                    'producer': None, 'provenance': {'request_id': request['request_id'],
                                                   'root': self.runtime['root_id']}}
                stored = self.artifact(snapshot['number'], certificate_value)
                certificate_ref = self.node_ref(stored['hash'], snapshot['number'])
                certificate_payload = copy.deepcopy(payload)
                certificate_payload['publication_certificate'] = certificate_ref
                self.node_persist(snapshot, certificate_payload, {'next_steps': [{
                    'kind': 'checkpoint', 'goal': snapshot['number'], 'certificate': certificate_ref,
                    'action': 'Exact pre-merge authority and provider identity sealed.'}]},
                    {'operation': 'integrate', 'request_id': request['request_id'] + '-certificate',
                     'authorization': request['authorization'], 'expected_head': facts['head_oid']})
                snapshot = self.node_snapshot(snapshot['number']); payload = copy.deepcopy(snapshot['payload'])
                before, _, _ = self.api._github_pull_request_states(self.repo, 'gh',
                    [{'number': snapshot['number']}], {snapshot['number']: {'repository_context': context}})
                latest = before.get(snapshot['number'], {})
                if (latest.get('merged') or any(latest.get(name) != facts.get(name) for name in
                        ('repository', 'head_oid', 'base_oid', 'base_ref', 'updated_at',
                         'review_verified', 'checks_verified'))):
                    raise ValueError('Provider changed after pre-merge certificate; retry against exact current facts')
                dispatch_certificate = copy.deepcopy(certificate_value)
                dispatch_certificate['content']['stage'] = 'dispatch'
                dispatch_stored = self.artifact(snapshot['number'], dispatch_certificate)
                dispatch_ref = self.node_ref(dispatch_stored['hash'], snapshot['number'])
                dispatch_payload = copy.deepcopy(payload)
                dispatch_payload['publication_certificate'] = dispatch_ref
                self.node_persist(snapshot, dispatch_payload, {'next_steps': [{
                    'kind': 'checkpoint', 'goal': snapshot['number'], 'certificate': dispatch_ref,
                    'action': 'Exact provider merge dispatch intent recorded.'}]},
                    {'operation': 'integrate', 'request_id': request['request_id'] + '-dispatch',
                     'authorization': request['authorization'], 'expected_head': facts['head_oid']})
                snapshot = self.node_snapshot(snapshot['number']); payload = copy.deepcopy(snapshot['payload'])
                try:
                    subprocess.run(['gh', 'pr', 'merge', context['pr'],
                        '--merge' if native else '--squash', '--match-head-commit', facts['head_oid'],
                        '--body', f"ZzzOps goal #{snapshot['number']}\n\n{effect_marker}"],
                        cwd=self.repo, capture_output=True, text=True, check=True)
                except (OSError, subprocess.SubprocessError):
                    raise ValueError('Provider merge dispatch outcome is uncertain; observe the exact PR before retry')
                observed, _, _ = self.api._github_pull_request_states(self.repo, 'gh', [{'number': snapshot['number']}], {snapshot['number']: {'repository_context': publication['context']}})
                after = observed.get(snapshot['number'], {})
                if not after.get('merged') or any(after.get(name) != facts.get(name) for name in ('repository', 'head_oid', 'base_oid', 'base_ref')): raise ValueError('Provider did not confirm exact authorized merge; retry same request')
                self.node_stack_verified_merge(after)
            else:
                self.node_stack_verified_merge(facts)
            response = {'next_steps': [{'kind': 'checkpoint', 'goal': snapshot['number'],
                'provider_state': 'merged',
                'action': 'Provider merge observed; configured post-effect evidence remains required.'}]}
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

    def node_terminal_merge_reconcile(self, number):
        """Finish a confirmed merge through the reviewed terminal task contract.

        Every mutation below is a normal public task transition with a real
        root-owned lease.  Stable request IDs make a restart after any write
        resume the same attempt rather than publish a second merge or Result.
        """
        root = (self.runtime or {}).get('root_id')
        if not root:
            raise ValueError('Terminal merge reconciliation requires authenticated root')
        self.invalidate()
        snapshot = self.node_snapshot(number)
        if snapshot['envelope']['state'] == 'archived':
            if str(snapshot['issue'].get('state', '')).lower() != 'closed':
                completed = any(any(step.get('provider_state') == 'closed'
                    for step in self.read_artifact(number, receipt['result']).get('next_steps', []))
                    for receipt in snapshot['payload']['operational']['receipts'])
                merged = any(state.get('publication', {}).get('provider', {}).get('merged')
                    for state in snapshot['projection']['states'].values()
                    if state['node']['goal'] == number)
                if not completed or not merged or snapshot['projection']['complete'] is not True:
                    raise ValueError('Archived open issue lacks exact terminal closure evidence')
                with self.locked():
                    before = self.adapter.get_issue(number)
                    if before.get('body') != snapshot['issue']['body']:
                        raise ValueError('Archived goal changed before provider close retry')
                    try:
                        self.adapter.update_issue(number, {'state': 'closed'})
                    except (OSError, RuntimeError):
                        pass
                    after = self.adapter.get_issue(number)
                    if after.get('body') != before['body'] or str(after.get('state', '')).lower() != 'closed':
                        raise ValueError('Provider goal closure remains unconfirmed; retry exact integration request')
            return {'status': 'closed', 'goal': number}
        candidates = [(key, state) for key, state in snapshot['projection']['states'].items()
                      if key[0] == number and any(slot.get('type') == 'merge_observation'
                             for slot in state['contract']['outputs'].values())]
        if len(candidates) != 1:
            raise ValueError('Configured terminal merge observation is missing or ambiguous')
        key, state = candidates[0]
        publication = state.get('publication')
        if not publication or not publication['provider'].get('merged'):
            raise ValueError('Exact provider merge is not currently observed')
        merge_commit, merged_at = self.node_stack_verified_merge(publication['provider'])
        if state['contract']['executor']['role'] != 'root':
            raise ValueError('Reviewed terminal observation must be assigned to root for automatic closure')
        node = state['node']
        prefix = 'terminal-' + str(number) + '-' + merge_commit
        if key not in snapshot['projection']['current']:
            lease = snapshot['projection']['leases'].get(key)
            expected_input = state.get('input_hash') or (lease or {}).get('fingerprint')
            if lease is None:
                if state['state'] != 'ready':
                    raise ValueError('Terminal merge observation is not ready for acquisition')
                _, policy_receipt = self.node_policy(state)
                self.node_mutate_phase(number, {'operation': 'start', 'node': node,
                    'input_hash': expected_input, 'policy_receipt': policy_receipt,
                    'request_id': prefix + '-start'})
                self.invalidate(); snapshot = self.node_snapshot(number)
                state = snapshot['projection']['states'][key]
                lease = snapshot['projection']['leases'].get(key)
            if not lease or lease['owner'] != root or lease['fingerprint'] != expected_input:
                raise ValueError('Terminal merge observation has another or stale owner; reconcile its exact lease')
            if lease['worker'] is None:
                _, policy_receipt = self.node_policy(state)
                self.node_mutate_phase(number, {'operation': 'bind', 'node': node,
                    'lease': lease['token'], 'actor': root, 'selection': lease['selection'],
                    'policy_receipt': policy_receipt, 'request_id': prefix + '-bind'})
                self.invalidate(); snapshot = self.node_snapshot(number)
                state = snapshot['projection']['states'][key]
                lease = snapshot['projection']['leases'][key]
            if lease['worker'] != root:
                raise ValueError('Terminal merge observation is bound to another worker')
            references = [row['source'] for row in state['inputs']
                          if snapshot['artifacts'][row['source']['hash']].get('type') == 'publication_authorization']
            if len(references) != 1:
                raise ValueError('Terminal merge observation lacks one exact authorization')
            value = {name: publication['observed'][name] for name in
                     ('repository', 'pr', 'head_oid', 'base_oid', 'base_ref')}
            value.update(authorization=references[0], merge_commit=merge_commit, merged_at=merged_at)
            outputs = {slot: value for slot, contract in state['contract']['outputs'].items()
                       if contract.get('type') == 'merge_observation'}
            if set(outputs) != set(state['contract']['outputs']):
                raise ValueError('Terminal merge task has unsupported additional outputs')
            self.node_mutate_phase(number, {'operation': 'submit', 'node': node,
                'lease': lease['token'], 'actor': root, 'outputs': outputs,
                'request_id': prefix + '-submit'})
            self.invalidate(); snapshot = self.node_snapshot(number)
        if not snapshot['projection']['complete']:
            raise ValueError('Merged goal still has unsatisfied terminal evidence or findings')
        authorities = self.node_publication_authorities(snapshot)
        if len(authorities) != 1:
            raise ValueError('Merged goal needs one current reviewed publication authorization')
        self.node_mutate_phase(number, {'operation': 'complete', 'authorization': authorities[0][0],
            'request_id': prefix + '-complete'})
        self.invalidate(); closed = self.node_snapshot(number)
        if closed['envelope']['state'] != 'archived' or str(closed['issue'].get('state', '')).lower() != 'closed':
            raise ValueError('Terminal merge closure was not confirmed')
        return {'status': 'closed', 'goal': number, 'merge_commit': merge_commit}

    def node_continuation(self, snapshot, payload, node, result):
        number = snapshot['number']
        target_payload = copy.deepcopy(snapshot.get('activation', {}).get('payload', payload))
        target_payload['operational'] = copy.deepcopy(payload['operational'])
        target = {**snapshot.get('activation', {}).get('envelope', snapshot['envelope']),
                  'revision': snapshot['envelope']['revision'] + 1, 'payload': self.node_ref(digest(target_payload), number)}
        if 'parent_change' in snapshot: target['parent'] = snapshot['parent_change']
        for value in (payload, target_payload): snapshot['artifacts'][digest(value)] = copy.deepcopy(value)
        identity = {'source_envelope': snapshot['envelope'], 'target_metadata': {key: value for key, value in target.items() if key != 'payload'},
                    'candidate_payload': target['payload'], 'entry_candidate_payload': self.node_ref(digest(payload), number)}
        pending = snapshot.get('pending')
        if pending and 'continuation' in pending:
            template = copy.deepcopy(pending['continuation'])
            if isinstance(template, dict) and 'type' not in template:
                if template != pending['response'] or template != self.node_ref(template.get('hash'), number):
                    raise ValueError('Pending continuation reference is not an exact same-goal response')
                try:
                    template = copy.deepcopy(self.artifact_index(number).resolve(template['hash'])[0])
                except (KeyError, ValueError) as exc:
                    raise ValueError('Pending continuation artifact is unavailable; restore the exact first transaction envelope before retrying') from exc
            if not isinstance(template, dict):
                raise ValueError('Invalid pending continuation template')
            if digest(template) != pending['response']['hash']:
                raise ValueError('Pending continuation response identity changed')
            if any(template.get(key) != value for key, value in identity.items()) or template.get('response', {}).get('submitted') != {'goal': number, 'node': node, 'result': result}:
                raise ValueError('Pending continuation candidate identity changed')
            return template
        # A structural submission can change the relationship/graph closure;
        # read that candidate through the same snapshot loader before publication.
        if 'parent_change' in snapshot or 'activation' in snapshot:
            candidate = self.node_snapshot(number, prospective={'envelope': target, 'artifacts': snapshot['artifacts']})
        else:
            candidate = self.node_project(snapshot, payload=payload)
        snapshot['artifacts'].update(candidate['artifacts'])
        steps = scoped_frontier(self.node_frontier(candidate, defer_envelope=True), self, worker_limit(self.project), number,
                                prospective_leases=payload['operational']['leases'])
        verification = snapshot.get('workspace_proof')
        return {'type': 'submission_continuation', 'version': 1, **identity,
                'response': {'submitted': {'goal': number, 'node': node, 'result': result}, 'next_steps': steps,
                    **({'verification': {'proof': verification, 'passed': snapshot['artifacts'][verification['hash']]['passed']}} if verification else {})},
                'bindings': [{'kind': 'target_envelope_digest', 'step': i} for i, step in enumerate(steps) if step['kind'] == 'reconcile']}

    def node_receipt_response(self, number, request, receipt, response, *, confirmed_target=None):
        """Bind only the original committed transaction, never today's envelope."""
        if response.get('type') != 'submission_continuation': return copy.deepcopy(response)
        if set(response) != {'type', 'version', 'source_envelope', 'target_metadata', 'candidate_payload', 'entry_candidate_payload', 'response', 'bindings'} or response['version'] != 1:
            raise ValueError('Invalid submission continuation template')
        if receipt != {'request': request['request_id'], 'payload': digest(request), 'result': self.node_ref(digest(response), number)}:
            raise ValueError('Continuation receipt identity mismatch')
        index = self.artifact_index(number)
        contexts = [row['context'] for row in index.envelopes if (row.get('context') or {}).get('request_id') == request['request_id']]
        if not contexts or any(context != contexts[0] for context in contexts):
            raise ValueError('Missing or conflicting continuation transaction')
        context = contexts[0]
        if context.get('request_hash') != receipt['payload'] or context.get('response') != receipt['result'] or context.get('continuation') not in (response, receipt['result']):
            raise ValueError('Continuation transaction receipt mismatch')
        candidate = copy.deepcopy(index.resolve(response['candidate_payload']['hash'])[0])
        candidate['operational']['receipts'].append(receipt)
        entry = copy.deepcopy(index.resolve(response['entry_candidate_payload']['hash'])[0])
        entry['operational']['receipts'].append(receipt)
        source = response['source_envelope']
        target = {**response['target_metadata'], 'payload': self.node_ref(digest(candidate), number)}
        if (source.get('issue') != number or source.get('repository') != self.repository
                or context.get('source_envelope') != source or context.get('target_envelope') != target
                or context.get('payload') != target['payload'] or context.get('entry_payload') != self.node_ref(digest(entry), number)
                or target.get('revision') != source['revision'] + 1 or target.get('repository') != self.repository or target.get('issue') != number):
            raise ValueError('Continuation exact transaction target mismatch')
        if confirmed_target is not None and target != confirmed_target:
            raise ValueError('Continuation publication target mismatch')
        if index.resolve(target['payload']['hash'])[0] != candidate:
            raise ValueError('Continuation target payload mismatch')
        materialized = copy.deepcopy(response['response'])
        steps = materialized['next_steps']
        expected = [{'kind': 'target_envelope_digest', 'step': i} for i, step in enumerate(steps) if step.get('kind') == 'reconcile']
        if response['bindings'] != expected: raise ValueError('Invalid deferred continuation bindings')
        for binding in expected:
            step = steps[binding['step']]
            if step.get('goal') != number or step.get('submission', {}).get('operation') != 'reconcile' or step['submission'].get('expected_digest', 'missing') is not None:
                raise ValueError('Invalid deferred reconciliation digest')
            step['submission']['expected_digest'] = digest(target)
        return materialized

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
        if response.get('type') != 'submission_continuation' or snapshot.get('pending'):
            return self._node_persist_once(snapshot, payload, response, request)
        original_payload = copy.deepcopy(payload)
        original_artifacts = dict(snapshot['artifacts'])
        original_activation = copy.deepcopy(snapshot.get('activation'))
        try:
            return self._node_persist_once(snapshot, payload, response, request)
        except ContinuationFirstEnvelopeBudget:
            # The guard runs before provider writes. Rebuild the whole receipt
            # from its original candidate, so a retry never points at a
            # continuation whose first envelope was only partly published.
            payload.clear()
            payload.update(original_payload)
            snapshot['artifacts'].clear()
            snapshot['artifacts'].update(original_artifacts)
            if original_activation is not None:
                snapshot['activation'] = original_activation
            bounded = copy.deepcopy(response)
            bounded['response']['next_steps'] = [{'kind': 'checkpoint', 'goal': snapshot['number'],
                'action': 'Submission committed. Reinvoke execute to read the complete current workflow frontier.'}]
            bounded['bindings'] = []
            return self._node_persist_once(snapshot, payload, bounded, request)

    def _node_persist_once(self, snapshot, payload, response, request):
        number = snapshot['number']; artifacts = snapshot['artifacts']
        def add(value):
            key = digest(value); artifacts[key] = value
            return self.node_ref(key, number)
        if snapshot.get('workflow_definition'):
            definition = snapshot['workflow_definition']
            payload['workflow'] = {'version': definition['version'], 'graph': add(definition['graph'])}
        if snapshot.get('original_goal_context') and 'goal_context' not in payload:
            payload['goal_context'] = add({'type': 'goal_context', 'content': snapshot['original_goal_context'],
                'producer': None, 'provenance': snapshot['goal_context_provenance']})
        if not snapshot.get('capture'):
            payload['operational']['receipts'].append({'request': request['request_id'], 'payload': digest(request), 'result': add(response)})
        else:
            add(response)
        entry_payload = add(payload)
        envelope = {**snapshot['envelope'], 'revision': snapshot['envelope']['revision'] + 1, 'payload': entry_payload}
        if 'activation' in snapshot:
            activation = snapshot['activation']
            target_payload = activation['payload']
            target_payload['operational'] = copy.deepcopy(payload['operational'])
            envelope = {**activation['envelope'], 'revision': envelope['revision'], 'payload': add(target_payload)}
        if 'parent_change' in snapshot: envelope['parent'] = snapshot['parent_change']
        if snapshot.get('archive'): envelope['state'] = 'archived'
        issue = snapshot['issue']
        if snapshot.get('capture'):
            prefix, suffix = issue['body'], ''
        else:
            prefix, suffix = self.api._migration_batch.human_parts(self, issue['body'])
        body = prefix + self.api._goals.GOAL_BLOCK_START + '\n' + json.dumps(envelope, sort_keys=True) + '\n' + self.api._goals.GOAL_BLOCK_END + suffix
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
        if snapshot.get('capture'):
            retain(self.node_ref(digest(response), number))
        proof = snapshot.get('workspace_proof')
        first_identity = digest(response) if snapshot.get('normalization') else (proof or {}).get('hash')
        referenced_continuation = (response.get('type') == 'submission_continuation'
                                  and (not pending or pending.get('continuation') == self.node_ref(digest(response), number)))
        if referenced_continuation:
            first_identity = digest(response)
        ordered = sorted(reachable, key=lambda identity: (identity != first_identity, identity))
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
        public_response = response['response'] if response.get('type') == 'submission_continuation' else response
        response_lease = public_response['next_steps'][0].get('lease', {})
        if not isinstance(response_lease, dict):
            response_lease = next((lease for lease in payload['operational']['leases'] if lease['token'] == response_lease), {})
        context = {'request_id': request['request_id'], 'request_hash': digest(request), 'source_hash': digest(issue['body']), 'human_hash': digest(prefix + suffix), 'root': None if snapshot.get('migration') else (self.runtime or {}).get('root_id'), 'response': self.node_ref(digest(response), number), 'ownership': {key: value for key, value in response_lease.items() if key != 'acquisition'}, 'acquisition': bool(public_response['next_steps'][0].get('bind')), 'payload': envelope['payload'], 'proof': proof, 'source_envelope': snapshot['envelope'], 'target_envelope': envelope, 'entry_payload': entry_payload}
        if response.get('type') == 'submission_continuation':
            context['continuation'] = context['response'] if referenced_continuation else response
        if response.get('type') == 'workspace_draft_retirement': context['workspace_draft_retirement'] = response['draft']
        if public_response['next_steps'][0].get('workspace_draft'): context['workspace_draft'] = public_response['next_steps'][0]['workspace_draft']
        if snapshot.get('migration'): context['migration'] = snapshot['migration']
        if snapshot.get('normalization'): context['normalization'] = copy.deepcopy(request)
        if pending and pending != context: raise ValueError('Pending checkpoint exact response/payload/proof identity changed')
        bodies = comment_store.pack_envelopes({'goal': number, 'transaction': digest({'request': request, 'source': issue['body']}), 'context': context}, records)
        if referenced_continuation:
            # The first write must retain the complete immutable retry template.
            # A reference to a partially uploaded chunk sequence is insufficient.
            try:
                if digest(response) in index.records:
                    retained = index.resolve(digest(response))[0]
                else:
                    first = ObservedArtifactIndex([{'body': bodies[0]}])
                    retained = first.resolve(digest(response))[0]
            except (IndexError, KeyError, ValueError) as exc:
                raise ContinuationFirstEnvelopeBudget('Continuation exceeds the first-envelope recovery budget; no comments were appended') from exc
            if retained != response:
                raise ValueError('First-envelope continuation identity differs; no comments were appended')
        prospective = self.node_preflight(comments, bodies, [envelope['payload']['hash']], index)
        for encoded in bodies:
            if any(row.get('body') == encoded for row in comments): continue
            try:
                actual = self.adapter.create_issue_comment(number, encoded)
            except (self.api.GoalTransitionProviderError, RuntimeError, OSError) as exc:
                if snapshot.get('normalization'):
                    raise ValueError('Normalization artifact publication interrupted; resume exact pending request') from exc
                actual = next((row for row in self.adapter.get_issue_comments(number) if row.get('body') == encoded), None)
                if actual is None: raise ValueError('Unconfirmed checkpoint comment append; retry exact request') from exc
            if actual.get('body') != encoded: raise ValueError('Provider did not confirm exact source backup/artifact content')
        confirmed = ObservedArtifactIndex(self.adapter.get_issue_comments(number), previous=prospective)
        confirmed.resolve(envelope['payload']['hash'])
        _OBSERVED_ARTIFACT_INDEXES[(str(self.repo.resolve()), self.repository, number)] = confirmed
        if snapshot.get('migration') and digest(self.api.reviewed_project_state(self.repo)['policy']) != snapshot['migration']['policy']:
            raise ValueError('Reviewed policy/graph changed before migration publication')
        observed = self.adapter.get_issue(number)
        if snapshot.get('capture') and observed.get('number') != number:
            raise ValueError('Capture provider readback changed issue identity')
        if observed['body'] != issue['body']: raise ValueError('Concurrent source edit before body publication')
        if str(observed.get('state', '')).lower() == 'closed' and not (snapshot.get('archive') or snapshot.get('closed_administration')):
            raise ValueError('Goal closed before body publication; explicit reopening is required')
        # Ordinary checkpoints own only the managed body. Resending snapshot
        # labels/state would overwrite unrelated edits or reopen a closed goal.
        update = {'body': body}
        if snapshot.get('capture'): update['labels'] = snapshot['capture_labels']
        if snapshot.get('archive'): update['state'] = 'closed'
        try:
            updated = self.adapter.update_issue(number, update)
        except (self.api.GoalTransitionProviderError, RuntimeError, OSError) as exc:
            updated = self.adapter.get_issue(number)
            if updated.get('body') != body: raise ValueError('Unconfirmed provider body publication; retry exact request') from exc
        if updated.get('body') != body: raise ValueError('Provider did not confirm exact goal body; retry same request')
        if snapshot.get('capture'):
            labels = {row.get('name') if isinstance(row, dict) else row
                      for row in updated.get('labels', [])}
            if labels != set(snapshot['capture_labels']):
                raise ValueError('Provider did not confirm exact capture labels; retry same request')
            confirmed = self.api.parse_managed_goal(updated.get('body', ''), number)
            if (confirmed.get('repository') != self.repository
                    or confirmed.get('issue') != number):
                raise ValueError('Provider did not confirm capture repository/issue identity')
        if snapshot.get('archive') and str(updated.get('state', '')).lower() != 'closed': raise ValueError('Provider did not confirm goal closure; repair partial state')
        if not (snapshot.get('archive') or snapshot.get('closed_administration')) and str(updated.get('state', '')).lower() == 'closed':
            raise ValueError('Goal closed during body publication; execution cannot resume without explicit reopening')
        if snapshot.get('closed_administration') and str(updated.get('state', '')).lower() != 'closed':
            raise ValueError('Closed stack coordinator changed provider state')
        self.invalidate()
        if snapshot.get('capture'):
            return response
        response = self.node_receipt_response(number, request, payload['operational']['receipts'][-1], response, confirmed_target=envelope)
        return self.stop_completed_heartbeat(number, request, payload['operational'], response)

    def node_mutate(self, number, request):
        if not isinstance(request.get('request_id'), str) or not request['request_id']:
            raise ValueError('Exact request_id is required')
        if 'verification_timeout_seconds' in request:
            timeout = request['verification_timeout_seconds']
            if (not isinstance(timeout, (int, float)) or isinstance(timeout, bool)
                    or not math.isfinite(timeout) or timeout <= 0):
                raise ValueError('verification_timeout_seconds must be finite and positive')
            if not request.get('workspace_checks'):
                raise ValueError('verification_timeout_seconds requires exact workspace_checks')
        split = request.get('operation') == 'submit' and bool(request.get('workspace_checks'))
        if not split:
            return self.node_mutate_phase(number, request)
        phase = getattr(self.budget, 'phase', None) or nullcontext
        with phase():
            prepared = self.node_mutate_phase(number, request, prepare_verification=True)
        context = prepared.get('_verification_prepare') if isinstance(prepared, dict) else None
        if context is None:
            return prepared
        if not context['pending_proof']:
            try:
                suspend = getattr(self, '_suspend_mutation_guard', None) or nullcontext
                with suspend():
                    self.node_verification_commands(
                        context['snapshot'], context['lease'], request,
                        context['commands'], context['before'],
                        working_directory=context['working_directory'])
            except VerificationUncertain as exc:
                lease = context['lease']; node = context['state']['node']
                return {'next_steps': [{'kind': 'await_worker', 'goal': number, 'node': node,
                    'lease': lease['token'], 'actor': lease['worker'], 'reason': str(exc),
                    'action': 'Observe this exact owner and verifier stopped, recover this lease, then reacquire before running a new request. Never infer completion from timeout or a log alone.',
                    'recovery_contract': {'operation': 'recover', 'node': node, 'lease': lease['token'],
                        'actor': lease['worker'], 'worker_status': '<observed status>',
                        'evidence': '<terminal observation>'}}]}
        clear_reads = getattr(self, '_clear_invocation_reads', None)
        if clear_reads:
            clear_reads()
        with phase():
            return self.node_mutate_phase(
                number, request, prepared_verification=context['identity'])

    def node_external_blocker_candidate(self, snapshot, request):
        """Preview one historical prerequisite without evaluating its phase DAG."""
        proposal = self.node_external_blocker_proposal(snapshot, request)
        return {'next_steps': [{'kind': 'archived_prerequisite_preview',
            'assignment': 'root', 'goal': snapshot['number'],
            'blocker_hash': request['blocker_hash'],
            'context_hash': request['context_hash'],
            'prerequisite': request['prerequisite'],
            'candidate': proposal['candidate'], 'proposal': proposal,
            'action': 'Give this exact candidate and preserved obligation to an independent reviewer; it grants no resource or completion authority.',
            'submission': {'operation': 'goal_external_blocker_review',
                'request_id': 'archived-prerequisite-review-' + digest(proposal)[7:],
                'actor': '<independent reviewer thread>', 'proposal': proposal,
                'decision': '<approved or changes_requested>',
                'report': '<independent review report>',
                'adoption': {'manual_request': 'opaque',
                    'terminal_equivalence': '<why merged work satisfies the exact old prerequisite>',
                    'retained_obligations': '<how missing migration obligations remain gated>'}}}]}

    def node_archived_migration_transaction(self, number, envelope, payload,
                                            receipt, response, target_intent,
                                            source_bytes):
        """Bind the manual receipt to its complete provider comment transaction.

        The old manual converter did not publish its request body. Its request
        fingerprint remains opaque and must receive explicit reviewed adoption.
        """
        rows = payload.get('operational', {}).get('receipts', [])
        if not isinstance(rows, list) or len(rows) != 1:
            raise ValueError('Archived migration requires one committed request receipt')
        row = rows[0]
        receipt_ref = self.node_ref(digest(receipt), number)
        response_ref = self.node_ref(digest(response), number)
        if (not isinstance(row, dict) or set(row) != {'request', 'payload', 'result'}
                or not isinstance(row['request'], str)
                or re.fullmatch(r'manual-migrate-[0-9a-f]{64}', row['request']) is None
                or not isinstance(row['payload'], str)
                or re.fullmatch(r'sha256:[0-9a-f]{64}', row['payload']) is None
                or row['result'] != response_ref):
            raise ValueError('Archived migration request fingerprint is malformed')
        index = self.artifact_index(number)
        heads = [part for part in index.envelopes
                 if (part.get('context') or {}).get('request_id') == row['request']]
        if not heads or len({part.get('transaction') for part in heads}) != 1:
            raise ValueError('Archived migration has no unique committed comment transaction')
        transaction = heads[0]['transaction']
        matching = [comment_store.decode_envelope(comment['body'])
                    for comment, part in index.envelope_comments
                    if part.get('transaction') == transaction]
        if len(matching) != len(heads):
            raise ValueError('Archived migration transaction has conflicting request identities')
        comment_store.verify_manifest(matching)
        if not isinstance(transaction, str) or re.fullmatch(r'sha256:[0-9a-f]{64}', transaction) is None:
            raise ValueError('Archived migration transaction identity is malformed')
        context = matching[0].get('context')
        expected_hashes = {envelope['payload']['hash'], receipt_ref['hash'],
                           response_ref['hash'], target_intent['payload']['hash'],
                           digest(target_intent)}
        included = {record['hash'] for part in matching for record in part['artifacts']}
        source_envelope = context.get('source_envelope') if isinstance(context, dict) else None
        source = self.api._archived_prerequisites._published_json(source_bytes, receipt['source'])
        source_issue = source.get('content') if isinstance(source, dict) else None
        source_body = source_issue.get('body') if isinstance(source_issue, dict) else None
        if not isinstance(source_body, str):
            raise ValueError('Archived migration published source has no issue body')
        prefix, suffix = self.api._migration_batch.human_parts(self, source_body)
        if (any(part.get('goal') != number or part.get('context') != context for part in matching)
                or not expected_hashes <= included
                or context.get('request_hash') != row['payload']
                or context.get('response') != response_ref
                or context.get('migration', {}).get('receipt') != receipt_ref
                or context.get('target_envelope') != {
                    **target_intent, 'payload': envelope['payload']}
                or context.get('entry_payload') != envelope['payload']
                or context.get('payload') != envelope['payload']
                or source_envelope != {**target_intent,
                                       'revision': target_intent['revision'] - 1}
                or context.get('source_hash') != digest(source_body)
                or context.get('human_hash') != digest(prefix + suffix)):
            raise ValueError('Archived migration comment transaction does not bind exact source and target')
        return transaction

    def node_external_blocker_proposal(self, snapshot, request, *, historical_edge=False):
        """Reobserve the named archived issue, transaction and integration commit."""
        required = {'operation', 'request_id', 'context_hash', 'blocker_hash',
                    'prerequisite', 'pull_number'}
        if set(request) != required or request['operation'] != 'goal_external_blocker_prepare':
            raise ValueError('Archived blocker preview requires one exact blocker and prerequisite')
        number = snapshot['number']
        context = snapshot.get('goal_context') or {}
        original = snapshot.get('original_goal_context') or {}
        context_ref = snapshot.get('goal_context_ref')
        if (not isinstance(request['request_id'], str)
                or re.fullmatch(r'[A-Za-z0-9._:-]{1,128}', request['request_id']) is None
                or context_ref is None or request['context_hash'] != context_ref['hash']):
            raise ValueError('Archived blocker preview request or context is stale')
        matches = [row for row in original.get('blockers', [])
                   if digest(row) == request['blocker_hash']]
        if (len(matches) != 1 or matches[0].get('category') != 'external-dependency'
                or not any(digest(row) == request['blocker_hash']
                           for row in context.get('blockers', []))):
            raise ValueError('Archived blocker preview identifies no unique open external obligation')
        prerequisite = request['prerequisite']
        declared = context.get('depends_on', [])
        if historical_edge:
            declared = original.get('depends_on', [])
        if (type(prerequisite) is not int or prerequisite <= 0 or prerequisite == number
                or prerequisite not in declared):
            raise ValueError('Archived blocker preview requires one declared same-goal-context prerequisite')
        pull_number = request['pull_number']
        if type(pull_number) is not int or pull_number <= 0:
            raise ValueError('Archived blocker preview requires an exact linked PR number')
        issue = self.adapter.get_issue(prerequisite)
        envelope = self.api.parse_managed_goal(issue.get('body', ''), prerequisite)
        if not envelope or envelope.get('schema_version') != 2:
            raise ValueError('Archived prerequisite has no readable v2 envelope')
        archived_payload = self.read_artifact(prerequisite, envelope['payload'])
        candidates = []
        for committed in archived_payload.get('operational', {}).get('receipts', []):
            response = self.read_artifact(prerequisite, committed['result'])
            steps = response.get('next_steps', []) if isinstance(response, dict) else []
            if len(steps) != 1 or steps[0].get('kind') != 'schema_migration':
                continue
            receipt = self.read_artifact(prerequisite, steps[0]['receipt'])
            if receipt.get('converter') == 'manual-reconciliation-522/1':
                candidates.append((receipt, response))
        if len(candidates) != 1:
            raise ValueError('Archived prerequisite has no unique supported migration receipt')
        receipt, response = candidates[0]
        source, source_bytes = self.node_published_artifact(receipt['source'])
        policy, policy_bytes = self.node_published_artifact(receipt['policy'])
        del source, policy  # The candidate validates the published bytes itself.
        target_intent = self.read_artifact(prerequisite, receipt['target_intent'])
        target_payload = self.read_artifact(prerequisite, receipt['target_payload'])
        transaction = self.node_archived_migration_transaction(
            prerequisite, envelope, archived_payload, receipt, response,
            target_intent, source_bytes)
        pull = self.adapter.archived_prerequisite_pull(pull_number)
        merge = (pull.get('mergeCommit') or {}).get('oid')
        branch = (policy_section(self.project, 'git_review_release')['configuration'].get(
            'release_planning') or {}).get('integration_branch')
        if not isinstance(merge, str) or not isinstance(branch, str) or not branch:
            raise ValueError('Archived prerequisite has no exact merge and integration identities')
        reachable = self.adapter.archived_prerequisite_reachable(merge, branch)
        candidate = self.api._archived_prerequisites.candidate(
            repository=self.repository, goal=prerequisite, integration_branch=branch,
            issue=issue, envelope=envelope, archived_payload=archived_payload,
            receipt=receipt, migration_response=response, target_intent=target_intent,
            target_payload=target_payload, source_bytes=source_bytes,
            policy_bytes=policy_bytes, pull_number=pull_number, pull=pull,
            merge_reachable=reachable)
        return {'kind': 'archived_prerequisite_proposal', 'repository': self.repository,
            'goal': number, 'context_hash': context_ref['hash'],
            'blocker_hash': request['blocker_hash'], 'prerequisite': prerequisite,
            'pull_number': pull_number, 'candidate': candidate,
            'migration_transaction': transaction,
            'manual_request': 'opaque_requires_reviewed_adoption',
            'source_envelope': copy.deepcopy(snapshot['envelope']),
            'policy': self.node_evidence_policy()}

    def node_external_blocker_review(self, snapshot, payload, request):
        if set(request) != {'operation', 'request_id', 'actor', 'proposal',
                            'decision', 'report', 'adoption'}:
            raise ValueError('Archived prerequisite review requires exact fields')
        root = (self.runtime or {}).get('root_id')
        invoking = os.environ.get('CODEX_THREAD_ID')
        if (not root or not explicit_approval(request['actor']) or request['actor'] == root
                or invoking != request['actor']):
            raise ValueError('Archived prerequisite review requires the authenticated independent thread')
        if (request['decision'] not in {'approved', 'changes_requested'}
                or not isinstance(request['report'], str) or not request['report'].strip()):
            raise ValueError('Archived prerequisite review requires decision and report')
        adoption = request['adoption']
        if (not isinstance(adoption, dict)
                or set(adoption) != {'manual_request', 'terminal_equivalence', 'retained_obligations'}
                or adoption['manual_request'] != 'opaque'
                or not all(isinstance(adoption[key], str) and adoption[key].strip()
                           for key in ('terminal_equivalence', 'retained_obligations'))):
            raise ValueError('Archived prerequisite requires explicit reviewed adoption of opaque manual request')
        proposal = request['proposal']
        if (not isinstance(proposal, dict) or proposal.get('kind') != 'archived_prerequisite_proposal'
                or proposal.get('manual_request') != 'opaque_requires_reviewed_adoption'):
            raise ValueError('Archived prerequisite review requires the exact proposal')
        prepared = {'operation': 'goal_external_blocker_prepare', 'request_id': request['request_id'],
            'context_hash': proposal.get('context_hash'), 'blocker_hash': proposal.get('blocker_hash'),
            'prerequisite': proposal.get('prerequisite'), 'pull_number': proposal.get('pull_number')}
        if proposal != self.node_external_blocker_proposal(snapshot, prepared):
            raise ValueError('Archived prerequisite proposal changed before review')
        policy = self.node_evidence_policy()
        proposal_artifact = {'type': 'archived_prerequisite_proposal',
            'content': copy.deepcopy(proposal), 'producer': None,
            'provenance': {'actor': root, 'source': snapshot['goal_context_ref'], 'policy': policy}}
        proposal_ref = self.node_ref(digest(proposal_artifact), snapshot['number'])
        snapshot['artifacts'][proposal_ref['hash']] = proposal_artifact
        review_artifact = {'type': 'archived_prerequisite_review',
            'content': {'decision': request['decision'], 'report': request['report'],
                        'adoption': copy.deepcopy(adoption)},
            'producer': None, 'provenance': {'actor': request['actor'],
                'source': proposal_ref, 'policy': policy, 'request_id': request['request_id']}}
        review_ref = self.node_ref(digest(review_artifact), snapshot['number'])
        snapshot['artifacts'][review_ref['hash']] = review_artifact
        if request['decision'] == 'approved':
            step = {'kind': 'human_approval', 'assignment': 'root',
                'goal': snapshot['number'], 'proposal': proposal_ref, 'review': review_ref,
                'action': 'Approve the exact independently reviewed archived prerequisite equivalence.',
                'submission': {'operation': 'goal_external_blocker_apply',
                    'request_id': 'archived-prerequisite-apply-' + digest(review_ref)[7:],
                    'actor': root, 'proposal': proposal_ref, 'review': review_ref,
                    'human_approval': {'approved_by': '<user>', 'attribution': '<exact approval>'}}}
        else:
            step = {'kind': 'changes_requested', 'goal': snapshot['number'],
                'proposal': proposal_ref, 'review': review_ref,
                'action': 'Reconsider the archived evidence; this review grants no authority.'}
        return self.node_persist(snapshot, payload, {'next_steps': [step]}, request)

    def node_external_blocker_apply(self, snapshot, payload, request):
        if set(request) != {'operation', 'request_id', 'actor', 'proposal',
                            'review', 'human_approval'}:
            raise ValueError('Archived prerequisite application requires exact fields')
        root = (self.runtime or {}).get('root_id')
        invoking = os.environ.get('CODEX_THREAD_ID')
        if not root or request['actor'] != root or (invoking and invoking != root):
            raise ValueError('Only the coordinating root may apply archived prerequisite evidence')
        approval = request['human_approval']
        if (not isinstance(approval, dict) or set(approval) != {'approved_by', 'attribution'}
                or not all(explicit_approval(approval[key]) for key in approval)):
            raise ValueError('Archived prerequisite application requires explicit human approval')
        if payload['operational']['leases']:
            raise ValueError('Active ownership must be reconciled before archived prerequisite application')
        for name in ('proposal', 'review'):
            self.api._phase_evidence.validate_ref(request[name])
            if self.node_ref_goal(request[name], snapshot['number']) != snapshot['number']:
                raise ValueError('Archived prerequisite review belongs to another goal')
        proposal_artifact = snapshot['resolve'](request['proposal'])
        review_artifact = snapshot['resolve'](request['review'])
        proposal = proposal_artifact.get('content', {})
        review = review_artifact.get('content', {})
        provenance = review_artifact.get('provenance', {})
        if (proposal_artifact.get('type') != 'archived_prerequisite_proposal'
                or proposal_artifact.get('provenance', {}).get('actor') != root
                or not self.node_same_local_ref(
                    proposal_artifact.get('provenance', {}).get('source'),
                    snapshot.get('goal_context_ref'), snapshot['number'], snapshot['resolve'])
                or review_artifact.get('type') != 'archived_prerequisite_review'
                or not explicit_approval(provenance.get('actor')) or provenance['actor'] == root
                or provenance.get('source') != request['proposal']
                or review.get('decision') != 'approved'
                or not isinstance(review.get('report'), str) or not review['report'].strip()):
            raise ValueError('Exact independent approved archived prerequisite review is required')
        adoption = review.get('adoption')
        if (not isinstance(adoption, dict)
                or set(adoption) != {'manual_request', 'terminal_equivalence', 'retained_obligations'}
                or adoption['manual_request'] != 'opaque'
                or not all(isinstance(adoption.get(key), str) and adoption[key].strip()
                           for key in ('terminal_equivalence', 'retained_obligations'))):
            raise ValueError('Archived prerequisite review lacks explicit manual request adoption')
        review_request = {'operation': 'goal_external_blocker_review',
            'request_id': provenance.get('request_id'), 'actor': provenance['actor'],
            'proposal': proposal, 'decision': review['decision'], 'report': review['report'],
            'adoption': review['adoption']}
        receipts = [row for row in payload['operational']['receipts']
                    if row['request'] == review_request['request_id']
                    and row['payload'] == digest(review_request)]
        edge = (self.node_receipt_edge(snapshot['number'], self.artifact_index(snapshot['number']),
                                      receipts[0]) if len(receipts) == 1 else None)
        if (edge is None or edge['source'] != proposal.get('source_envelope')
                or edge['target'] != snapshot['envelope']
                or edge['response'].get('next_steps', [{}])[0].get('review') != request['review']):
            raise ValueError('Archived prerequisite review lacks its exact committed receipt')
        prepared = {'operation': 'goal_external_blocker_prepare', 'request_id': request['request_id'],
            'context_hash': proposal.get('context_hash'), 'blocker_hash': proposal.get('blocker_hash'),
            'prerequisite': proposal.get('prerequisite'), 'pull_number': proposal.get('pull_number')}
        expected = self.node_external_blocker_proposal(snapshot, prepared)
        expected['source_envelope'] = proposal['source_envelope']
        if proposal != expected or proposal.get('policy') != self.node_evidence_policy():
            raise ValueError('Archived prerequisite candidate, policy or blocker changed after review')
        event = {'type': 'archived_prerequisite_resolution',
            'content': {'context_hash': proposal['context_hash'],
                'blocker_hash': proposal['blocker_hash'],
                'prerequisite': proposal['prerequisite'],
                'candidate': copy.deepcopy(proposal['candidate']),
                'proposal': request['proposal'], 'review': request['review'],
                'human_approval': copy.deepcopy(approval)},
            'producer': None, 'provenance': {'actor': root, 'repository': self.repository,
                'goal': snapshot['number'], 'request_id': request['request_id']}}
        reference = self.node_ref(digest(event), snapshot['number'])
        snapshot['artifacts'][reference['hash']] = event
        journal = payload.setdefault('goal_context_archived_prerequisites',
                                     {'version': 1, 'events': []})
        if (not isinstance(journal, dict) or set(journal) != {'version', 'events'}
                or journal['version'] != 1 or not isinstance(journal['events'], list)):
            raise ValueError('Unsupported archived prerequisite journal')
        journal['events'].append(reference)
        response = {'next_steps': [{'kind': 'archived_prerequisite_applied',
            'goal': snapshot['number'], 'prerequisite': proposal['prerequisite'],
            'resolution': reference}]}
        return self.node_persist(snapshot, payload, response, request)

    def node_resolve_goal_blocker(self, snapshot, payload, request):
        """Append one authenticated resolution without rewriting migration history."""
        common = {'operation', 'request_id', 'actor', 'context_hash', 'blocker_hash',
                  'rationale', 'resolution_basis', 'evidence'}
        original = snapshot.get('original_goal_context')
        context_ref = snapshot.get('goal_context_ref')
        if original is None or context_ref is None:
            raise ValueError('Goal has no authenticated migrated goal context')
        matches = [row for row in original['blockers'] if digest(row) == request.get('blocker_hash')]
        human = bool(matches) and all(row.get('category') == 'human-action' for row in matches)
        expected = common | ({'human_approval'} if human else set())
        if set(request) != expected:
            raise ValueError('Goal blocker resolution requires the exact returned fields')
        if (not isinstance(request['request_id'], str)
                or re.fullmatch(r'[A-Za-z0-9._:-]{1,128}', request['request_id']) is None):
            raise ValueError('Goal blocker resolution request_id is invalid')
        root = (self.runtime or {}).get('root_id'); invoking = os.environ.get('CODEX_THREAD_ID')
        if not root or request.get('actor') != root or (invoking and invoking != root):
            raise ValueError('Goal blocker resolution requires the authenticated coordinating root actor')
        if request.get('context_hash') != context_ref['hash']:
            raise ValueError('Goal blocker resolution context is stale or unknown')
        if len(matches) != 1:
            raise ValueError('Goal blocker resolution identifies an unknown or ambiguous duplicate blocker')
        blocker = matches[0]
        if blocker.get('status') in ('closed', 'resolved'):
            raise ValueError('Goal blocker is already closed or resolved')
        effective = snapshot.get('goal_context', {})
        if not any(digest(row) == request['blocker_hash'] for row in effective.get('blockers', [])):
            raise ValueError('Goal blocker is already resolved')
        if payload['operational']['leases']:
            raise ValueError('Active ownership must be recovered or completed before resolving a goal blocker')
        for name in ('rationale', 'resolution_basis'):
            if not isinstance(request.get(name), str) or not request[name].strip():
                raise ValueError('Goal blocker resolution requires a nonempty ' + name.replace('_', ' '))
        evidence = request.get('evidence')
        if not isinstance(evidence, list) or not evidence:
            raise ValueError('Goal blocker resolution requires immutable current evidence')
        if len({json.dumps(ref, sort_keys=True) for ref in evidence if isinstance(ref, dict)}) != len(evidence):
            raise ValueError('Goal blocker resolution evidence must be unique')
        current = set()
        for result_ref, result in snapshot['projection']['current'].values():
            current.add(result_ref['hash'])
            current.update(ref['hash'] for ref in result['outputs'].values())
        for ref in evidence:
            self.api._phase_evidence.validate_ref(ref)
            if ref['uri'].startswith('git:') or self.node_ref_goal(ref, snapshot['number']) != snapshot['number']:
                raise ValueError('Goal blocker resolution evidence belongs to another goal')
            value = snapshot['resolve'](ref)
            if digest(value) != ref['hash']:
                raise ValueError('Goal blocker resolution evidence checksum mismatch')
            if ref['hash'] not in current:
                raise ValueError('Goal blocker resolution evidence is stale or is not a current Result/output')
        if human:
            approval = request.get('human_approval')
            if (not isinstance(approval, dict) or set(approval) != {'approved_by', 'attribution'}
                    or not all(isinstance(approval.get(key), str) and approval[key].strip()
                               for key in ('approved_by', 'attribution'))):
                raise ValueError('Human-action blocker resolution requires explicit human approval attribution')
        content = {key: copy.deepcopy(request[key]) for key in
                   ('context_hash', 'blocker_hash', 'rationale', 'resolution_basis', 'evidence')}
        if human:
            content['human_approval'] = copy.deepcopy(request['human_approval'])
        event = {'type': 'goal_blocker_resolution', 'content': content, 'producer': None,
                 'provenance': {'actor': root, 'repository': self.repository,
                                'goal': snapshot['number'], 'request_id': request['request_id']}}
        reference = self.node_ref(digest(event), snapshot['number'])
        snapshot['artifacts'][reference['hash']] = event
        journal = payload.setdefault('goal_context_resolutions', {'version': 1, 'events': []})
        if (not isinstance(journal, dict) or set(journal) != {'version', 'events'}
                or journal.get('version') != 1 or not isinstance(journal.get('events'), list)):
            raise ValueError('Unsupported goal-context resolution journal')
        journal['events'].append(reference)
        resolved = [snapshot['artifacts'][ref['hash']]['content']['blocker_hash']
                    for ref in journal['events']]
        self.api._static_workflow.resolved_goal_context(original, resolved)
        response = {'next_steps': [{'kind': 'goal_blocker_resolved', 'goal': snapshot['number'],
                                    'resolution': reference}]}
        return self.node_persist(snapshot, payload, response, request)

    def node_dependency_proposal(self, snapshot, old, replacement, rationale):
        """Preview one explicit migrated dependency change and its current impact."""
        number = snapshot['number']
        context = snapshot.get('goal_context')
        context_ref = snapshot.get('goal_context_ref')
        if context is None or context_ref is None:
            raise ValueError('Goal has no authenticated dependency context')
        if snapshot['payload']['operational']['leases']:
            raise ValueError('Goal dependency change requires reconciled worker ownership')
        if snapshot['envelope']['state'] != 'open':
            raise ValueError('Closed goal dependencies cannot be changed')
        if replacement == number or old == number:
            raise ValueError('Goal cannot depend on itself')
        if replacement is not None:
            issue = self.adapter.get_issue(replacement)
            related = self.api.parse_managed_goal(issue.get('body', ''), replacement)
            if related is None or related.get('repository', self.repository) != self.repository:
                raise ValueError('Replacement dependency is not a canonical same-repository goal')
        if not isinstance(rationale, str) or not rationale.strip():
            raise ValueError('Goal dependency change requires an explicit rationale')
        after_context = self.api._static_workflow.changed_goal_dependencies(
            context, [{'old': old, 'replacement': replacement}])
        prospective = self.node_snapshot(number, dependency_override=after_context)
        if prospective.get('relationship_error'):
            raise ValueError('Goal dependency preview found inconsistent relationship evidence: '
                             + prospective['relationship_error'])
        before = snapshot['projection']['current']
        after = prospective['projection']['current']
        retained, invalidated = [], []
        for key, (reference, result) in sorted(before.items(), key=lambda row: str(row[0])):
            if key in after and after[key][0] == reference:
                retained.append(reference)
            else:
                invalidated.append({'node': result['node'], 'result': reference})
        human = self.api._migration_batch.human_parts(self, snapshot['issue']['body'])
        payload = snapshot['payload']
        return {'kind': 'goal_dependency_change', 'repository': self.repository,
            'goal': number, 'context': context_ref, 'old': old,
            'replacement': replacement, 'before': copy.deepcopy(context['depends_on']),
            'after': copy.deepcopy(after_context['depends_on']),
            'policy': self.node_evidence_policy(),
            'source': {'envelope': copy.deepcopy(snapshot['envelope']),
                       'spec': payload['spec'], 'graph': payload['graph'],
                       'evidence': copy.deepcopy(payload['evidence']),
                       'human_hash': digest(human),
                       'current': [{'node': result['node'], 'result': ref}
                                   for _, (ref, result) in sorted(before.items(),
                                       key=lambda row: str(row[0]))]},
            'impact': {'retained': retained, 'invalidated': invalidated},
            'rationale': rationale}

    def node_dependency_review(self, snapshot, payload, request):
        """Authenticated independent reviewer records an exact proposal review."""
        if set(request) != {'operation', 'request_id', 'actor', 'proposal',
                            'decision', 'report'}:
            raise ValueError('Goal dependency review requires exact returned fields')
        root = (self.runtime or {}).get('root_id')
        invoking = os.environ.get('CODEX_THREAD_ID')
        if (not root or not explicit_approval(request.get('actor'))
                or request['actor'] == root or invoking != request['actor']):
            raise ValueError('Goal dependency review requires the authenticated independent thread')
        if (request['decision'] not in
                {'approved', 'changes_requested'} or not isinstance(request['report'], str)
                or not request['report'].strip()):
            raise ValueError('Goal dependency review requires an explicit decision and report')
        proposal = request['proposal']
        if not isinstance(proposal, dict) or proposal.get('kind') != 'goal_dependency_change':
            raise ValueError('Goal dependency review requires the exact prepared proposal')
        expected = self.node_dependency_proposal(snapshot, proposal.get('old'),
            proposal.get('replacement'), proposal.get('rationale'))
        if proposal != expected:
            raise ValueError('Goal dependency proposal or affected evidence changed before review')
        policy = self.node_evidence_policy()
        proposal_artifact = {'type': 'goal_dependency_proposal',
            'content': copy.deepcopy(proposal), 'producer': None,
            'provenance': {'actor': root, 'source': proposal['context'], 'policy': policy}}
        proposal_ref = self.node_ref(digest(proposal_artifact), snapshot['number'])
        snapshot['artifacts'][proposal_ref['hash']] = proposal_artifact
        review_artifact = {'type': 'goal_dependency_review',
            'content': {'decision': request['decision'], 'report': request['report']},
            'producer': None,
            'provenance': {'actor': request['actor'], 'source': proposal_ref, 'policy': policy,
                           'request_id': request['request_id']}}
        review_ref = self.node_ref(digest(review_artifact), snapshot['number'])
        snapshot['artifacts'][review_ref['hash']] = review_artifact
        if request['decision'] == 'approved':
            step = {'kind': 'human_approval', 'assignment': 'root',
                'goal': snapshot['number'], 'proposal': proposal_ref, 'review': review_ref,
                'action': 'Present this exact dependency change and independent review for approval.',
                'submission': {'operation': 'goal_dependency_apply',
                               'request_id': 'goal-dependency-apply-' + digest(review_ref)[7:],
                               'actor': root, 'proposal': proposal_ref, 'review': review_ref,
                               'human_approval': {'approved_by': '<user>',
                                                  'attribution': '<exact approval>'}}}
        else:
            step = {'kind': 'changes_requested', 'goal': snapshot['number'],
                'proposal': proposal_ref, 'review': review_ref,
                'action': 'Revise the exact proposal; this review grants no change authority.'}
        return self.node_persist(snapshot, payload, {'next_steps': [step]}, request)

    def node_dependency_apply(self, snapshot, payload, request):
        """Append one reviewed and human-approved dependency event."""
        if set(request) != {'operation', 'request_id', 'actor', 'proposal',
                            'review', 'human_approval'}:
            raise ValueError('Goal dependency apply requires exact returned fields')
        root = (self.runtime or {}).get('root_id')
        invoking = os.environ.get('CODEX_THREAD_ID')
        if not root or request['actor'] != root or (invoking and invoking != root):
            raise ValueError('Only the coordinating root may apply a goal dependency change')
        approval = request['human_approval']
        if (not isinstance(approval, dict) or set(approval) != {'approved_by', 'attribution'}
                or not explicit_approval(approval['approved_by'])
                or not explicit_approval(approval['attribution'])):
            raise ValueError('Goal dependency change requires explicit human approval attribution')
        for name in ('proposal', 'review'):
            self.api._phase_evidence.validate_ref(request[name])
            if self.node_ref_goal(request[name], snapshot['number']) != snapshot['number']:
                raise ValueError('Goal dependency review belongs to another goal')
        proposal_artifact = snapshot['resolve'](request['proposal'])
        review_artifact = snapshot['resolve'](request['review'])
        proposal = proposal_artifact.get('content', {})
        review = review_artifact.get('content', {})
        review_provenance = review_artifact.get('provenance', {})
        if (proposal_artifact.get('type') != 'goal_dependency_proposal'
                or proposal_artifact.get('provenance', {}).get('actor') != root
                or proposal_artifact.get('provenance', {}).get('source') != snapshot.get('goal_context_ref')
                or review_artifact.get('type') != 'goal_dependency_review'
                or not explicit_approval(review_provenance.get('actor'))
                or review_provenance['actor'] == root
                or review_provenance.get('source') != request['proposal']
                or review.get('decision') != 'approved'
                or not isinstance(review.get('report'), str) or not review['report'].strip()):
            raise ValueError('Exact independent approved dependency review is required')
        review_request = {'operation': 'goal_dependency_review',
            'request_id': review_provenance.get('request_id'),
            'actor': review_provenance['actor'], 'proposal': proposal,
            'decision': review['decision'], 'report': review['report']}
        receipts = [row for row in payload['operational']['receipts']
                    if row['request'] == review_request['request_id']
                    and row['payload'] == digest(review_request)]
        if len(receipts) != 1:
            raise ValueError('Independent dependency review lacks its exact committed receipt')
        edge = self.node_receipt_edge(snapshot['number'], self.artifact_index(snapshot['number']), receipts[0])
        if (edge is None or edge['source'] != proposal.get('source', {}).get('envelope')
                or edge['target'] != snapshot['envelope']
                or edge['response'].get('next_steps', [{}])[0].get('review') != request['review']):
            raise ValueError('Independent dependency review/current goal chain changed')
        expected = self.node_dependency_proposal(snapshot, proposal.get('old'),
            proposal.get('replacement'), proposal.get('rationale'))
        expected['source']['envelope'] = proposal['source']['envelope']
        if (proposal != expected or proposal.get('context') != snapshot.get('goal_context_ref')
                or proposal.get('policy') != self.node_evidence_policy()):
            raise ValueError('Goal dependency proposal, policy or current evidence changed after review')
        event = {'type': 'goal_dependency_change',
            'content': {'context': proposal['context'], 'old': proposal['old'],
                        'replacement': proposal['replacement'],
                        'before': proposal['before'], 'after': proposal['after'],
                        'proposal': request['proposal'], 'review': request['review'],
                        'human_approval': copy.deepcopy(approval)},
            'producer': None,
            'provenance': {'actor': root, 'repository': self.repository,
                           'goal': snapshot['number'], 'request_id': request['request_id']}}
        reference = self.node_ref(digest(event), snapshot['number'])
        snapshot['artifacts'][reference['hash']] = event
        journal = payload.setdefault('goal_context_dependency_events', {'version': 1, 'events': []})
        if (not isinstance(journal, dict) or set(journal) != {'version', 'events'}
                or journal.get('version') != 1 or not isinstance(journal['events'], list)):
            raise ValueError('Unsupported goal dependency journal')
        journal['events'].append(reference)
        response = {'next_steps': [{'kind': 'goal_dependency_changed',
            'goal': snapshot['number'], 'event': reference,
            'before': proposal['before'], 'after': proposal['after']}]}
        return self.node_persist(snapshot, payload, response, request)

    def node_policy_cutover_mapping(self, snapshot, mapping, old_graph, new_graph):
        """Validate a finite exact Result mapping between two reviewed graphs."""
        if not isinstance(mapping, list) or not mapping:
            raise ValueError('Policy DAG cutover mapping must be a non-empty array')
        old_nodes = {node['id']: node for node in old_graph['nodes']}
        new_nodes = {node['id']: node for node in new_graph['nodes']}
        current = {}
        for reference in reversed(snapshot['payload']['evidence']):
            result_artifact = snapshot['resolve'](reference)
            result = result_artifact.get('content', {})
            if result_artifact.get('type') != 'result':
                continue
            key = self.api._phase_evidence.task_key(result['node'])
            current.setdefault(key, (reference, result))
        seen_old, seen_new = set(), set()
        required = {'inputs', 'outputs', 'scope', 'role', 'independence', 'approval'}
        for row in mapping:
            if not isinstance(row, dict) or set(row) != {'old', 'new', 'result', 'equivalence'}:
                raise ValueError('Policy DAG cutover mapping row is malformed')
            for side, nodes in (('old', old_nodes), ('new', new_nodes)):
                target = row[side]
                if not isinstance(target, dict) or set(target) != {'node', 'output'}:
                    raise ValueError('Policy DAG cutover mapping target is malformed')
                node = nodes.get(target['node'])
                if node is None or target['output'] not in node['outputs']:
                    raise ValueError('Policy DAG cutover mapping names a missing output')
            old_key = (row['old']['node'], row['old']['output'])
            new_key = (row['new']['node'], row['new']['output'])
            if old_key in seen_old or new_key in seen_new:
                raise ValueError('Policy DAG cutover mapping is ambiguous')
            seen_old.add(old_key); seen_new.add(new_key)
            equivalence = row['equivalence']
            if not isinstance(equivalence, dict) or set(equivalence) != required or not all(
                    equivalence[name] is True for name in required):
                raise ValueError('Policy DAG cutover evidence equivalence is incomplete')
            old_node, new_node = old_nodes[old_key[0]], new_nodes[new_key[0]]
            comparable_old = _rename_node_selectors(old_node, old_key[0], new_key[0])
            derived = {
                'inputs': comparable_old['inputs'] == new_node['inputs'],
                'outputs': comparable_old['outputs'][old_key[1]] == new_node['outputs'][new_key[1]],
                'scope': (comparable_old['executor'].get('authority') == new_node['executor'].get('authority')
                          and comparable_old.get('permits', []) == new_node.get('permits', [])),
                'role': comparable_old['executor'].get('role') == new_node['executor'].get('role'),
                'independence': comparable_old.get('independent_of', []) == new_node.get('independent_of', []),
                'approval': comparable_old.get('gates', []) == new_node.get('gates', []),
            }
            changed = sorted(name for name, equivalent in derived.items() if not equivalent)
            if changed:
                raise ValueError('Policy DAG cutover equivalence changed: ' + ', '.join(changed))
            self.api._phase_evidence.validate_ref(row['result'])
            if self.node_ref_goal(row['result'], snapshot['number']) != snapshot['number']:
                raise ValueError('Policy DAG cutover Result belongs to another goal')
            artifact = snapshot['resolve'](row['result'])
            result = artifact.get('content', {})
            if (artifact.get('type') != 'result' or result.get('node', {}).get('node') != old_key[0]
                    or result.get('outputs', {}).get(old_key[1]) is None):
                raise ValueError('Policy DAG cutover mapping Result/output identity differs')
            old_task = (snapshot['number'], old_key[0], result['node'].get('item'),
                        result['node'].get('generation', 1))
            if old_task not in current or current[old_task][0] != row['result']:
                raise ValueError('Policy DAG cutover mapping Result is superseded or not current')
        mapped_old = {(row['old']['node'], row['old']['output']) for row in mapping}
        reusable = set()
        for key, (_reference, result) in current.items():
            if key[0] != snapshot['number'] or key[2] is not None:
                continue
            old_node = old_nodes.get(key[1]); new_node = new_nodes.get(key[1])
            if old_node is None or new_node is None:
                continue
            for output in result['outputs']:
                if (output in old_node['outputs'] and output in new_node['outputs']
                        and old_node['inputs'] == new_node['inputs']
                        and old_node['outputs'][output] == new_node['outputs'][output]
                        and old_node['executor'] == new_node['executor']
                        and old_node.get('independent_of', []) == new_node.get('independent_of', [])
                        and old_node.get('gates', []) == new_node.get('gates', [])
                        and old_node.get('permits', []) == new_node.get('permits', [])):
                    reusable.add((key[1], output))
        omitted = sorted(reusable - mapped_old)
        if omitted:
            raise ValueError('Policy DAG cutover mapping omitted reusable current outputs: ' +
                             ', '.join(node + '/' + output for node, output in omitted))
        return copy.deepcopy(mapping)

    def node_policy_cutover_prepare(self, snapshot, payload, request):
        expected = {'operation', 'request_id', 'actor', 'expected_goal_revision',
                    'expected_goal_payload', 'old_graph', 'new_graph',
                    'old_policy_digest', 'new_policy_digest', 'mapping'}
        if set(request) != expected:
            raise ValueError('Policy DAG cutover prepare requires exact returned fields')
        root = (self.runtime or {}).get('root_id')
        if not root or request['actor'] != root:
            raise ValueError('Only the coordinating root may prepare a policy DAG cutover')
        cutover = snapshot.get('policy_dag_cutover')
        if (cutover is None or request['expected_goal_revision'] != snapshot['envelope']['revision']
                or request['expected_goal_payload'] != snapshot['envelope']['payload']
                or any(request[name] != cutover[name] for name in (
                    'old_graph', 'new_graph'))
                or request['old_policy_digest'] != cutover['old_policy_revision']
                or request['new_policy_digest'] != cutover['new_policy_revision']):
            raise ValueError('Policy DAG cutover goal revision, payload, graph or policy changed')
        old_graph = snapshot['resolve'](cutover['old_graph'])
        new_graph = snapshot['resolve'](cutover['new_graph'])
        mapping = self.node_policy_cutover_mapping(snapshot, request['mapping'], old_graph, new_graph)
        if payload['operational']['leases']:
            raise ValueError('Policy DAG cutover requires every old-policy lease owner to be resolved')
        proposal = {'old_graph': cutover['old_graph'], 'new_graph': cutover['new_graph'],
            'old_execution_graph': cutover['old_execution_graph'],
            'new_policy_graph': cutover['new_policy_graph'],
            'old_policy_digest': cutover['old_policy_revision'],
            'new_policy_digest': cutover['new_policy_revision'], 'mapping': mapping,
            'source_revision': snapshot['envelope']['revision'],
            'source_payload': copy.deepcopy(snapshot['envelope']['payload'])}
        artifact = {'type': 'policy_dag_cutover_proposal', 'content': proposal,
            'producer': None, 'provenance': {'actor': root, 'request_id': request['request_id']}}
        reference = self.node_ref(digest(artifact), snapshot['number'])
        snapshot['artifacts'][reference['hash']] = artifact
        snapshot['workflow_definition'] = None
        response = {'next_steps': [{'kind': 'policy_dag_cutover_proposed',
            'goal': snapshot['number'], 'proposal': reference,
            'review': {'operation': 'policy_dag_cutover_review',
                'request_id': '<stable request id>', 'actor': '<independent reviewer>',
                'proposal': reference, 'decision': '<approved or changes_requested>',
                'report': '<exact review report>'}}]}
        return self.node_persist(snapshot, payload, response, request)

    def node_policy_cutover_review(self, snapshot, payload, request):
        if set(request) != {'operation', 'request_id', 'actor', 'proposal', 'decision', 'report'}:
            raise ValueError('Policy DAG cutover review requires exact returned fields')
        root = (self.runtime or {}).get('root_id')
        if (not isinstance(request['actor'], str) or not request['actor'].strip()
                or request['actor'] == root or request['decision'] not in {'approved', 'changes_requested'}
                or not isinstance(request['report'], str) or not request['report'].strip()):
            raise ValueError('Policy DAG cutover requires an independent substantive review')
        self.api._phase_evidence.validate_ref(request['proposal'])
        proposal_artifact = snapshot['resolve'](request['proposal'])
        proposal = proposal_artifact.get('content', {})
        if (proposal_artifact.get('type') != 'policy_dag_cutover_proposal'
                or proposal_artifact.get('provenance', {}).get('actor') != root
                or snapshot.get('policy_dag_cutover') is None
                or proposal.get('old_graph') != snapshot['policy_dag_cutover']['old_graph']
                or proposal.get('new_graph') != snapshot['policy_dag_cutover']['new_graph']):
            raise ValueError('Policy DAG cutover proposal is stale or unauthenticated')
        review = {'type': 'policy_dag_cutover_review',
            'content': {'decision': request['decision'], 'report': request['report']},
            'producer': None, 'provenance': {'actor': request['actor'],
                'source': request['proposal'], 'request_id': request['request_id']}}
        reference = self.node_ref(digest(review), snapshot['number'])
        snapshot['artifacts'][reference['hash']] = review
        snapshot['workflow_definition'] = None
        step = {'kind': 'policy_dag_cutover_reviewed', 'goal': snapshot['number'],
            'proposal': request['proposal'], 'review': reference}
        if request['decision'] == 'approved':
            step['apply'] = {'operation': 'policy_dag_cutover_apply',
                'request_id': '<stable request id>', 'actor': root,
                'proposal': request['proposal'], 'review': reference,
                'expected_goal_revision': snapshot['envelope']['revision'] + 1}
        return self.node_persist(snapshot, payload, {'next_steps': [step]}, request)

    def node_policy_cutover_apply(self, snapshot, payload, request):
        if set(request) != {'operation', 'request_id', 'actor', 'proposal', 'review',
                            'expected_goal_revision'}:
            raise ValueError('Policy DAG cutover apply requires exact returned fields')
        root = (self.runtime or {}).get('root_id')
        if (not root or request['actor'] != root
                or request['expected_goal_revision'] != snapshot['envelope']['revision']):
            raise ValueError('Policy DAG cutover apply goal revision is stale or actor is not root')
        if payload['operational']['leases']:
            raise ValueError('Policy DAG cutover cannot apply while an old-policy lease is active')
        proposal_artifact = snapshot['resolve'](request['proposal'])
        review_artifact = snapshot['resolve'](request['review'])
        proposal = proposal_artifact.get('content', {})
        review = review_artifact.get('content', {})
        if (proposal_artifact.get('type') != 'policy_dag_cutover_proposal'
                or review_artifact.get('type') != 'policy_dag_cutover_review'
                or review_artifact.get('provenance', {}).get('source') != request['proposal']
                or review_artifact.get('provenance', {}).get('actor') == root
                or review.get('decision') != 'approved'):
            raise ValueError('Policy DAG cutover requires the exact independent approved review')
        cutover = snapshot.get('policy_dag_cutover')
        if (cutover is None or proposal.get('old_graph') != cutover['old_graph']
                or proposal.get('new_graph') != cutover['new_graph']):
            raise ValueError('Policy DAG cutover proposal no longer matches current old/new policy')
        old_graph = snapshot['resolve'](proposal['old_graph'])
        new_graph = snapshot['resolve'](proposal['new_graph'])
        self.node_policy_cutover_mapping(snapshot, proposal.get('mapping'), old_graph, new_graph)
        payload['workflow'] = {'version': self.api._static_workflow.VERSION,
                               'graph': copy.deepcopy(proposal['new_graph'])}
        receipt_artifact = {'type': 'policy_dag_cutover_receipt',
            'content': {'old_graph': proposal['old_execution_graph'], 'new_graph': proposal['new_graph'],
                'new_policy_graph': proposal['new_policy_graph'],
                'proposal': request['proposal'], 'review': request['review'],
                'mapping': proposal['mapping']}, 'producer': None,
            'provenance': {'actor': root, 'request_id': request['request_id']}}
        receipt = self.node_ref(digest(receipt_artifact), snapshot['number'])
        snapshot['artifacts'][receipt['hash']] = receipt_artifact
        response = {'next_steps': [{'kind': 'policy_dag_cutover_applied',
            'goal': snapshot['number'], 'old_graph': proposal['old_execution_graph'],
            'new_graph': proposal['new_graph'], 'receipt': receipt}]}
        return self.node_persist(snapshot, payload, response, request)

    def node_phase_finding(self, snapshot, payload, request):
        """Record diagnostic phase data; independent review/admission grants work."""
        fields = {'operation', 'request_id', 'actor', 'target', 'subject', 'source', 'rationale', 'id'}
        if set(request) != fields:
            raise ValueError('Phase finding requires the exact event submission fields')
        root = (self.runtime or {}).get('root_id')
        invoking = os.environ.get('CODEX_THREAD_ID')
        if not root or request['actor'] != root or (invoking and invoking != root):
            raise ValueError('Phase finding intake requires the authenticated coordinating root actor')
        if payload['operational']['leases']:
            raise ValueError('Preserve completed work and resolve existing ownership before recording late phase findings')
        target = request['target']
        if not isinstance(target, dict) or set(target) not in (
                {'node', 'output'}, {'node', 'output', 'expansion', 'item', 'generation'}):
            raise ValueError('Phase finding requires an exact local phase/output target')
        key = (snapshot['number'], target['node'], target.get('item'), target.get('generation', 1))
        if 'expansion' in target:
            expansion = next((row for row in snapshot['graph']['task_sets'] if row['id'] == target['expansion']), None)
            if (not expansion or expansion['template']['id'] != target['node']
                    or not isinstance(target['item'], str) or type(target['generation']) is not int):
                raise ValueError('Phase finding member identity does not match its policy template')
        current = snapshot['projection']['current'].get(key)
        if not current or current[1]['outputs'].get(target['output']) != request['subject']:
            raise ValueError('Phase finding subject is stale or not the exact current target output')
        for name in ('subject', 'source'):
            ref = request[name]
            self.api._phase_evidence.validate_ref(ref)
            if ref['uri'].startswith('git:') or self.node_ref_goal(ref, snapshot['number']) != snapshot['number']:
                raise ValueError('Phase finding evidence must belong to this goal')
            value = snapshot['resolve'](ref)
            if digest(value) != ref['hash']:
                raise ValueError('Phase finding evidence checksum mismatch')
        journal = payload.setdefault('phase_data', {'version': 1, 'events': []})
        events = [snapshot['artifacts'][ref['hash']]['content'] for ref in journal['events']]
        revision = 1 + max((event['revision'] for event in events if event['id'] == request['id']), default=0)
        if any(event['id'] == request['id'] and event['target'] != target for event in events):
            raise ValueError('Phase finding identity cannot change its target')
        event = {name: copy.deepcopy(request[name]) for name in ('id', 'target', 'subject', 'source', 'rationale')}
        event['revision'] = revision
        self.api._static_workflow.phase_data([*events, event], snapshot['graph'], snapshot['number'])
        blob = {'type': 'phase_event', 'content': event, 'producer': None,
                'provenance': {'actor': root, 'repository': self.repository, 'goal': snapshot['number'],
                               'request_id': request['request_id'], 'policy': self.node_evidence_policy()}}
        reference = self.node_ref(digest(blob), snapshot['number'])
        snapshot['artifacts'][reference['hash']] = blob
        journal['events'].append(reference)
        projected = self.node_project(snapshot, payload=payload)
        response = {'next_steps': [{'kind': 'phase_data_recorded', 'goal': snapshot['number'],
                                   'event': reference, 'revision': revision},
                                  *scoped_frontier(self.node_frontier(projected), self, worker_limit(self.project),
                                                   snapshot['number'], prospective_leases=[])]}
        return self.node_persist(snapshot, payload, response, request)

    def node_mutate_phase(self, number, request, *, prepare_verification=False,
                          prepared_verification=None):
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
                        response = self.node_receipt_response(number, request, receipt, self.artifact_index(number).resolve(receipt['result']['hash'])[0])
                        if any(step.get('provider_state') == 'closed' for step in response['next_steps']) and str(issue.get('state', '')).lower() != 'closed': raise ValueError('Stored closure receipt conflicts with partial provider state; repair required')
                        if (str(issue.get('state', '')).lower() == 'closed'
                                and request.get('operation') not in {'stack_status', 'stack_advance', 'integrate'}
                                and not any(step.get('provider_state') == 'closed' for step in response['next_steps'])):
                            raise ValueError('Closed goal cannot resume an execution receipt without explicit reopening')
                        if request.get('operation') == 'submit':
                            submitted = response.get('submitted', {})
                            result_ref = submitted.get('result')
                            if isinstance(result_ref, dict):
                                result_artifact = self.artifact_index(number).resolve(result_ref['hash'])[0]
                                if result_artifact.get('content', {}).get('supersedes_result') is not None:
                                    response = {'next_steps': [{'kind': 'checkpoint', 'goal': number,
                                        'action': 'Replacement Result is already committed; observe the current authenticated frontier.'}]}
                        return self.stop_completed_heartbeat(number, request, durable['operational'], response)
            ownership_graph = None
            if request.get('operation') in {'recover', 'release', 'renew'} and envelope.get('schema_version') == 2:
                ownership_reference = durable.get('workflow', {}).get('graph', durable['graph'])
                ownership_graph = self.artifact_index(number).resolve(ownership_reference['hash'])[0]
            snapshot = self.node_snapshot(number, graph_override=ownership_graph)
            closed = (snapshot['envelope']['state'] != 'open'
                      or str(snapshot['issue'].get('state', '')).lower() == 'closed')
            if closed:
                if (request.get('operation') not in {'stack_status', 'stack_advance', 'stack_attempt_retire'}
                        or snapshot['envelope']['state'] != 'archived'
                        or str(snapshot['issue'].get('state', '')).lower() != 'closed'
                        or not snapshot['payload'].get('stack_integration', {}).get('plan')):
                    raise ValueError('Archived goal cannot execute or mutate')
                snapshot['closed_administration'] = True
            if snapshot.get('policy_dag_cutover'):
                cutover_operations = {
                    'policy_dag_cutover_prepare', 'policy_dag_cutover_review',
                    'policy_dag_cutover_apply',
                }
                ownership_operations = {'bind', 'block', 'recover', 'release', 'renew', 'submit'}
                operation = request.get('operation')
                if operation in ownership_operations:
                    requested = request.get('node')
                    owned = (isinstance(requested, dict) and any(
                        lease.get('node') == requested
                        for lease in snapshot['payload']['operational']['leases']))
                    if not owned:
                        raise ValueError('Pending policy DAG cutover permits only an exact old-lease operation')
                elif operation not in cutover_operations:
                    raise ValueError('Pending policy DAG cutover blocks semantic mutation until reviewed mapping is applied')
            # Archived-prerequisite administration repairs an exact migrated
            # blocker without running or accepting any retired phase. Keep the
            # old phase mapping debt on the execution frontier after the write.
            if snapshot.get('workflow_migration_blocker') and request.get('operation') not in {
                    'recover', 'release', 'renew',
                    'goal_external_blocker_review', 'goal_external_blocker_apply'}:
                raise ValueError(snapshot['workflow_migration_blocker'])
            payload = copy.deepcopy(snapshot['payload']); projection = snapshot['projection']
            for receipt in payload['operational']['receipts']:
                if receipt['request'] == request['request_id']:
                    if receipt['payload'] != digest(request): raise ValueError('Request receipt payload conflict')
                    return copy.deepcopy(snapshot['artifacts'][receipt['result']['hash']])
            if self.node_has_merged_publication(snapshot, number):
                terminal_observation = self.node_postmerge_terminal_observation(
                    projection, number, request.get('node'))
                if not self.node_postmerge_operation_allowed(request['operation'], terminal_observation):
                    raise ValueError('Merged goal permits observation and reconciliation only; substantive tasks cannot start after merge')
            pending = self.node_pending(snapshot, request)
            if request['operation'] == 'policy_dag_cutover_prepare':
                return self.node_policy_cutover_prepare(snapshot, payload, request)
            if request['operation'] == 'policy_dag_cutover_review':
                return self.node_policy_cutover_review(snapshot, payload, request)
            if request['operation'] == 'policy_dag_cutover_apply':
                return self.node_policy_cutover_apply(snapshot, payload, request)
            if request['operation'] == 'resolve_goal_blocker':
                return self.node_resolve_goal_blocker(snapshot, payload, request)
            if request['operation'] == 'goal_dependency_review':
                return self.node_dependency_review(snapshot, payload, request)
            if request['operation'] == 'goal_dependency_apply':
                return self.node_dependency_apply(snapshot, payload, request)
            if request['operation'] == 'goal_external_blocker_review':
                return self.node_external_blocker_review(snapshot, payload, request)
            if request['operation'] == 'goal_external_blocker_apply':
                return self.node_external_blocker_apply(snapshot, payload, request)
            if request['operation'] == 'phase_finding':
                return self.node_phase_finding(snapshot, payload, request)
            if request['operation'] == 'graph_normalize':
                return self.node_graph_normalize(snapshot, payload, request)
            if request['operation'] == 'checkpoint_reconcile_adopt':
                return self.node_checkpoint_reconcile_adopt(snapshot, payload, request)
            if request['operation'] == 'checkpoint_reconcile_review':
                return self.node_checkpoint_reconcile_review(snapshot, payload, request)
            if request['operation'] == 'compact_candidate':
                return self.node_compact_candidate(snapshot, payload, request)
            if request['operation'] == 'graph_adopt':
                return self.node_graph_adopt(snapshot, payload, request)
            if request['operation'] == 'graph_review':
                return self.node_graph_review(snapshot, payload, request)
            if request['operation'] == 'graph_review_bootstrap':
                return self.node_graph_review_bootstrap(snapshot, payload, request)
            if request['operation'] in {'stack_prepare', 'stack_status', 'stack_advance'}:
                return self.node_stack_operation(snapshot, payload, request)
            if request['operation'] == 'stack_attempt_retire':
                return self.node_stack_attempt_retire(snapshot, payload, request)
            if request['operation'] in {'integrate', 'reconcile', 'complete'}:
                return self.node_publication_operation(snapshot, payload, request)
            if request['operation'] == 'publication_attempt_retire':
                return self.node_publication_attempt_retire(snapshot, payload, request)
            node = request.get('node')
            if not isinstance(node, dict): raise ValueError('Generic operation requires exact qualified node identity')
            if node.get('goal') != number:
                raise ValueError('Generic task mutation must address its own goal')
            key = ev.task_key(node)
            state = projection['states'].get(key)
            if state is None: raise ValueError('Unknown or retired task generation')
            if (request['operation'] not in {'recover', 'release', 'renew'}
                    and self.node_shadowed_correction_admission(snapshot, state)):
                raise ValueError('Legacy correction admission is superseded by its reviewed atomic transfer route')
            if (request['operation'] not in {'recover', 'release', 'renew'}
                    and self.node_owned_legacy_admission(snapshot, state)):
                raise ValueError('Legacy correction admission remains owned; resolve its exact owner before replacement work')
            operation = request['operation']; leases = payload['operational']['leases']
            lease = next((item for item in leases if item['node'] == node), None)
            root = (self.runtime or {}).get('root_id')
            if operation in {'restack_continue', 'restack_abort'}:
                allowed = {'operation', 'request_id', 'node', 'lease', 'actor', 'plan_hash'}
                restack = lease.get('restack') if lease else None
                if (set(request) != allowed or not lease or not restack
                        or request.get('lease') != lease.get('token')
                        or request.get('actor') != lease.get('worker')
                        or not lease.get('worker')
                        or request.get('plan_hash') != restack.get('plan_hash')
                        or restack.get('plan_hash') != digest(restack.get('plan'))
                        or restack.get('pending') is not None):
                    raise ValueError('Unsupported restack operation or exact lease, actor, and plan changed')
                restack['pending'] = {'operation': operation,
                    'request': request['request_id'], 'actor': request['actor']}
                response = {'next_steps': [{'kind': operation + '_authorized',
                    'goal': number, 'node': node, 'lease': lease['token'],
                    'actor': lease['worker'], 'attempt': lease['attempt'],
                    'plan_hash': restack['plan_hash'],
                    'plan': copy.deepcopy(restack['plan'])}]}
            elif operation == 'restack_intent':
                allowed = {'operation', 'request_id', 'node', 'lease', 'actor',
                           'plan_hash', 'authorized_request', 'candidate_commit', 'result_tree'}
                restack = lease.get('restack') if lease else None
                pending_restack = restack.get('pending') if restack else None
                intent = ({'candidate_commit': request.get('candidate_commit'),
                           'result_tree': request.get('result_tree')})
                if (set(request) != allowed or not lease or not restack
                        or request.get('lease') != lease.get('token')
                        or request.get('actor') != lease.get('worker')
                        or request.get('plan_hash') != restack.get('plan_hash')
                        or pending_restack != {'operation': 'restack_continue',
                            'request': request.get('authorized_request'), 'actor': request.get('actor')}
                        or any(re.fullmatch(r'[0-9a-f]{40}', value or '') is None
                               for value in intent.values())
                        or restack.get('candidate_intent') not in (None, intent)):
                    raise ValueError('Restack candidate intent differs from provider-authorized continuation')
                restack['candidate_intent'] = intent
                response = {'next_steps': [{'kind': 'restack_intent_confirmed',
                    'goal': number, 'node': node, 'lease': lease['token'],
                    'actor': lease['worker'], 'plan_hash': restack['plan_hash'], **intent}]}
            elif operation == 'restack_finalize':
                allowed = {'operation', 'request_id', 'node', 'lease', 'actor',
                           'plan_hash', 'authorized_request', 'status', 'head_commit'}
                restack = lease.get('restack') if lease else None
                pending_restack = restack.get('pending') if restack else None
                if (set(request) != allowed or not lease or not restack
                        or request.get('lease') != lease.get('token')
                        or request.get('actor') != lease.get('worker')
                        or request.get('plan_hash') != restack.get('plan_hash')
                        or pending_restack != {'operation': 'restack_' + request.get('status', ''),
                            'request': request.get('authorized_request'), 'actor': request.get('actor')}
                        or request.get('status') not in {'continue', 'abort'}):
                    raise ValueError('Restack finalization differs from its provider-confirmed operation')
                workspace = snapshot['workspaces'].get(key, {})
                observed = managed_worktrees.inspect_attempt_worktree(self.repo,
                    goal=number, node=node['node'], attempt=lease['attempt'])
                if (not workspace.get('git_workspace') or 'entry' not in workspace
                        or observed.get('status') != 'clean'
                        or observed.get('head') != request.get('head_commit')):
                    raise ValueError('Restack finalization requires the exact clean managed worktree')
                plan = restack['plan']
                git_phase_state.verify_attempt_ref(self.repo, remote='origin',
                    ref=restack['source']['ref'], commit=restack['source']['commit'])
                if request['status'] == 'continue':
                    checkpoint = git_phase_state.validate_checkpoint(Path(observed['path']),
                        base_commit=plan['new_base'], result_commit=observed['head'],
                        owned_paths=workspace['entry']['owned'])
                    restack.update(status='ready', result_commit=observed['head'],
                                   result_tree=checkpoint['result_tree'])
                    restack.pop('pending')
                    response = {'next_steps': [{'kind': 'restack_continued',
                        'goal': number, 'node': node, 'lease': lease['token'],
                        'actor': lease['worker'], 'plan_hash': restack['plan_hash'],
                        'result_commit': observed['head'],
                        'submission': {'operation': 'submit', 'node': node}}]}
                else:
                    if observed['head'] != plan['new_base']:
                        raise ValueError('Restack abort did not restore the exact new base')
                    leases.remove(lease)
                    response = {'next_steps': [{'kind': 'restack_aborted',
                        'goal': number, 'node': node, 'lease': lease['token'],
                        'actor': lease['worker'], 'plan_hash': restack['plan_hash'],
                        'head_commit': observed['head']}]}
            elif operation == 'route_choice':
                allowed = {'operation', 'request_id', 'node', 'root_pair', 'requested_pair', 'choice', 'approved_by'}
                if set(request) != allowed or request.get('choice') != 'downgrade_to_root' or not explicit_approval(request.get('approved_by')):
                    raise ValueError('Root capability downgrade requires the exact returned choice and explicit human approval')
                if lease or state['state'] != 'ready':
                    raise ValueError('Capability choice applies only to an unowned ready task')
                unresolved = self.node_step(state)
                if (unresolved.get('kind') != 'capability_choice' or
                        request.get('root_pair') != unresolved.get('root_pair') or
                        request.get('requested_pair') != unresolved.get('requested_pair') or
                        'downgrade_to_root' not in unresolved.get('choices', [])):
                    raise ValueError('Capability choice no longer matches the current task, root or reviewed routing policy')
                response = {'next_steps': [{'kind': 'routing_choice', 'goal': number, 'node': node,
                    'choice': request['choice'], 'root_pair': request['root_pair'],
                    'requested_pair': request['requested_pair'], 'contract': state['contract_hash'],
                    'policy': digest(self.project['policy']),
                    'action': 'Exact root capability downgrade recorded; invoke the checkpoint again to acquire work.'}]}
            elif operation == 'start':
                if lease: raise ValueError('Task already has an owner; observed-stop recovery is required')
                if state['state'] != 'ready' or request.get('input_hash') != state.get('input_hash'): raise ValueError('Stale input or prerequisite prevents acquisition')
                # Broadphase intentionally avoids serialising a merely-ready
                # legacy sibling. Once that exact legacy task is selected,
                # materialise its raw baseline before issuing ownership.
                selected_workspace = self.node_workspace_context(
                    snapshot['evaluation_context']['goals'], projection,
                    snapshot['artifacts'], workspace_target=key).get(key)
                if isinstance(selected_workspace, dict) and 'error' in selected_workspace:
                    raise ValueError(selected_workspace['error'])
                if 'repository_workspace' in state['contract']['executor']['resources']:
                    if (not isinstance(selected_workspace, dict)
                            or 'files' not in selected_workspace
                            or 'entry' not in selected_workspace):
                        raise ValueError('Selected legacy workspace baseline is unavailable')
                if (selected_workspace is not None and 'files' in selected_workspace
                        and 'entry' in selected_workspace):
                    selected_workspace = copy.deepcopy(selected_workspace)
                    for path in (selected_workspace['entry']['owned']
                                 + selected_workspace['entry']['consumed']):
                        selected_workspace['files'].setdefault(path, 'missing')
                    selected_workspace['acquisition']['workspace_digest'] = digest(
                        selected_workspace['files'])
                if node['node'] == 'publish' and self.node_native_delivery(snapshot):
                    if self.node_candidate_state(snapshot)['status'] != 'ready':
                        raise ValueError('Git-native candidate must be compacted before publication acquisition')
                draft_acquisition = state.get('workspace', {}).get('acquisition', {})
                if draft_acquisition.get('stopped_draft') and draft_acquisition.get('input_hash') != state['input_hash']:
                    raise ValueError('Stopped workspace draft full input identity changed; reconcile current authority before acquisition')
                if any(set(state['contract']['executor']['resources']).intersection(projection['states'][other]['contract']['executor']['resources']) for other in projection['leases'] if other in projection['states']): raise ValueError('Declared resource is already owned')
                if local_worker_count(self) >= worker_limit(self.project): raise ValueError('Reviewed max_workers capacity occupied on this machine')
                step = self.node_step(state, snapshot)
                if step['kind'] != 'execute': raise ValueError('Capability choice must be resolved before acquisition')
                _, receipt = self.node_policy(state)
                if request.get('policy_receipt') != receipt: raise ValueError('Exact policy receipt is required')
                lease = {'node': node, 'attempt': uuid.uuid4().hex, 'token': uuid.uuid4().hex, 'owner': root,
                         'worker': root if step['assignment'] == 'root' else None, 'fingerprint': state['input_hash'], 'expires_at': time.time() + 600,
                         'selection': step['selection'], 'acquisition': {
                             'resolutions': state['resolutions'], 'inputs': state['inputs'],
                             'contract': state['contract_hash'],
                             'expected_goal_revision': snapshot['envelope']['revision']}}
                aggregates = {}
                for binding in state['inputs']:
                    declared = state['contract']['inputs'].get(binding['name'], {})
                    selector = declared.get('producer', {}).get('node', {})
                    if selector.get('goal') == '#children' or selector.get('kind') == 'join':
                        aggregates[binding['name']] = copy.deepcopy(snapshot['artifacts'][binding['source']['hash']]['content']['sources'])
                if aggregates: lease['acquisition']['aggregate_sources'] = aggregates
                if selected_workspace is not None:
                    workspace = selected_workspace
                    lease['acquisition'].update(copy.deepcopy(workspace['acquisition']))
                    if 'files' in workspace:
                        lease['acquisition']['files'] = copy.deepcopy(workspace['files'])
                    lease['acquisition']['input_hash'] = state['input_hash']
                lease['acquisition'].update(inputs=copy.deepcopy(state['inputs']), resolutions=copy.deepcopy(state['resolutions']), contract=state['contract_hash'])
                restack = self.node_attempt_restack_plan(
                    snapshot, state, selected_workspace)
                if restack is not None:
                    lease['restack'] = restack
                if pending: lease.update(copy.deepcopy(pending['response']['next_steps'][0]['lease']))
                leases.append(lease)
                # Reserve local capacity before the durable provider write. A
                # crash can leave only a conservative local slot, which the
                # next exact reconciliation removes; the inverse ordering could
                # publish ownership while leaving capacity apparently free.
                self.api._heartbeat.track_capacity(
                    repo=self.repo, root_id=root, goal=number,
                    phase=json.dumps(node, sort_keys=True), token=lease['token'])
                response = {'next_steps': [{**step, 'kind': 'perform', 'lease': lease, 'acquisition': lease['acquisition'],
                    'bind': {'operation': 'bind', 'node': node, 'lease': lease['token'], 'actor': '<actual worker>', 'selection': lease['selection'], 'policy_receipt': '<read policy.path>'},
                    'submission': {'operation': 'submit', 'node': node}}]}
            elif operation == 'retire_stale_draft':
                allowed = {'operation', 'request_id', 'node', 'draft', 'subject', 'recovery_request'}
                retirement = snapshot['workspaces'].get(key, {}).get('stale_draft_retirement')
                if (set(request) != allowed or not root or payload['operational']['leases']
                        or not retirement or any(request.get(name) != retirement[name] for name in ('draft', 'subject'))):
                    raise ValueError('Stale draft retirement requires its exact current clean workspace/authority contract and no owner')
                historical = request['recovery_request']
                matches = [row for row in payload['operational']['receipts']
                           if isinstance(historical, dict) and row['request'] == historical.get('request_id')
                           and row['payload'] == digest(historical)]
                drafts = [(ref, value) for ref, value in snapshot['workspace_drafts'] if ref == request['draft']]
                if len(matches) != 1 or len(drafts) != 1:
                    raise ValueError('Exact committed draft and original observed-stop recovery request required')
                draft = drafts[0][1]
                original = snapshot['artifacts'][matches[0]['result']['hash']]
                if (historical.get('operation') != 'recover' or historical.get('node') != node
                        or historical.get('lease') != draft['lease']['token']
                        or historical.get('actor') != draft['lease']['worker']
                        or historical.get('worker_status') != 'stopped'
                        or not isinstance(historical.get('evidence'), str) or not historical['evidence'].strip()
                        or original['next_steps'][0].get('workspace_draft') != request['draft']):
                    raise ValueError('Retirement requires immutable observed stopped-owner evidence for this exact draft')
                response = {'type': 'workspace_draft_retirement', 'version': 1, 'node': node,
                            'draft': request['draft'], 'subject': request['subject'],
                            'source_payload': snapshot['envelope']['payload'], 'root': root,
                            'recovery_request': copy.deepcopy(historical),
                            'next_steps': [{'kind': 'checkpoint', 'goal': number,
                                           'action': 'Stale draft selection retired; original unaccepted bytes and history retained. Acquire fresh work through current review and verification gates.'}]}
            elif operation == 'preserve_historical_draft':
                allowed = {'operation', 'request_id', 'node', 'recovery_request', 'recovery_request_hash',
                           'recovery_result', 'expected_workspace', 'expected_delta'}
                if set(request) != allowed or lease:
                    raise ValueError('Historical draft preservation requires its exact returned contract and no current owner')
                recovery = snapshot['workspaces'].get(key, {}).get('historical_recovery')
                if not recovery:
                    raise ValueError('No current authenticated historical draft recovery is available')
                historical_request = request.get('recovery_request')
                compared = ('recovery_request_hash', 'recovery_result', 'expected_workspace', 'expected_delta')
                if (not isinstance(historical_request, dict) or digest(historical_request) != recovery['recovery_request_hash'] or
                        any(request.get(name) != recovery[name] for name in compared)):
                    raise ValueError('Historical recovery request/result, workspace or owned delta changed')
                if (historical_request.get('operation') != 'recover' or
                        historical_request.get('request_id') != recovery['recovery_request_id'] or
                        historical_request.get('node') != recovery['lease']['node'] or
                        historical_request.get('lease') != recovery['lease']['token'] or
                        historical_request.get('actor') != recovery['lease']['worker'] or
                        historical_request.get('worker_status') != 'stopped' or
                        not isinstance(historical_request.get('evidence'), str) or
                        not historical_request['evidence'].strip()):
                    raise ValueError('Exact historical observed-stop recovery request is required')
                acquisition = copy.deepcopy(recovery['source_acquisition'])
                acquisition['recovered_from'] = recovery['recovery_result']
                draft = {'type': 'workspace_draft', 'continuity_only': True,
                    'node': recovery['lease']['node'],
                    'lease': {name: recovery['lease'][name] for name in ('token', 'attempt', 'owner', 'worker')},
                    'source_payload': recovery['source_payload'],
                    'acquisition_receipt': recovery['acquisition_receipt'],
                    'source_acquisition': recovery['source_acquisition'],
                    'historical_recovery': {'request': copy.deepcopy(historical_request),
                                            'response': recovery['recovery_result']},
                    'acquisition': acquisition, 'acquisition_hash': digest(acquisition),
                    'contract': acquisition['contract'], 'input_hash': recovery['lease']['fingerprint'],
                    'policy': self.node_evidence_policy(), 'authority': recovery['authority'],
                    'files': recovery['files'], 'workspace': recovery['expected_workspace'],
                    'outputs': recovery['expected_delta'], 'evidence': historical_request['evidence']}
                identity = digest(draft); snapshot['artifacts'][identity] = draft
                response = {'next_steps': [{'kind': 'checkpoint', 'goal': number,
                    'workspace_draft': self.node_ref(identity, number),
                    'action': 'Historical stopped bytes are preserved as unaccepted work; reacquire through the normal current task contract.'}]}
            else:
                if not lease and operation == 'submit':
                    acquired = None
                    for historical_receipt in payload['operational']['receipts']:
                        historical_response = snapshot['resolve'](historical_receipt['result'])
                        acquired = next((step.get('lease') for step in historical_response.get('next_steps', [])
                                         if isinstance(step.get('lease'), dict)
                                         and step['lease'].get('token') == request.get('lease')), None)
                        if acquired:
                            break
                    current = projection['current'].get(key)
                    mapped_results = set()
                    for receipt_row in reversed(payload['operational']['receipts']):
                        try:
                            prior = snapshot['resolve'](receipt_row['result'])
                            applied = next(item for item in prior.get('next_steps', [])
                                           if item.get('kind') == 'policy_dag_cutover_applied')
                            cutover_receipt = snapshot['resolve'](applied['receipt'])['content']
                            mapped_results = {item['result']['hash'] for item in cutover_receipt['mapping']}
                            break
                        except (KeyError, StopIteration, TypeError, ValueError):
                            continue
                    if (acquired and current and current[0]['hash'] in mapped_results
                            and current[1]['attempt'] == acquired.get('attempt')):
                        return {'next_steps': [{'kind': 'checkpoint', 'goal': number,
                            'action': 'The reviewed cutover retained this completed attempt; observe the current frontier.'}]}
                if not lease or request.get('lease') != lease['token'] or lease['owner'] != root: raise ValueError('Exact current owner/lease token required')
                if operation == 'recover':
                    if request.get('worker_status') != 'stopped' or not isinstance(request.get('evidence'), str) or not request['evidence'].strip(): raise ValueError('Observed stopped worker evidence required; unknown liveness cannot recover')
                    if request.get('actor') != lease['worker']: raise ValueError('Exact bound actor required for observed-stop recovery')
                    step = {'kind': 'checkpoint', 'goal': number}
                    if ('git_commit' in lease['acquisition'] and 'files' not in lease['acquisition']):
                        observed = managed_worktrees.inspect_attempt_worktree(
                            self.repo, goal=number, node=node['node'], attempt=lease['attempt'])
                        base = lease['acquisition']['git_commit']
                        workspace = state.get('workspace')
                        if (observed['status'] == 'clean' and observed['head'] != base
                                and workspace and workspace.get('git_workspace')):
                            try:
                                git_phase_state.validate_checkpoint(Path(observed['path']),
                                    base_commit=base, result_commit=observed['head'],
                                    owned_paths=workspace['entry']['owned'])
                            except ValueError as exc:
                                step['unretained_attempt'] = str(exc)
                            else:
                                # Retain before releasing the lease. A failed or
                                # uncertain push leaves this exact recover request
                                # replayable, and the remote ref is create-only.
                                step['retained_attempt'] = git_phase_state.retain_attempt_ref(
                                    Path(observed['path']), remote='origin', goal=number,
                                    node=node['node'], attempt=lease['attempt'],
                                    commit=observed['head'])
                    if 'repository_workspace' in state['contract']['executor']['resources']:
                        if state['state'] != 'ready' or state.get('input_hash') != lease['fingerprint']:
                            raise ValueError('Stale workspace authority/input prevents draft recovery: ' + state.get('reason', 'workspace drift'))
                        workspace = state.get('workspace')
                        if not workspace or 'error' in workspace: raise ValueError('Current workspace authority is required for draft recovery')
                        acquisition = lease['acquisition']; actual = self.workspace_files()
                        delta = {p: actual.get(p, 'missing') for p in acquisition['files'].keys() | actual.keys()
                                 if acquisition['files'].get(p, 'missing') != actual.get(p, 'missing')}
                        if set(delta) - set(workspace['entry']['owned']): raise ValueError('Workspace draft changed unowned/consumed files')
                        # A resumed owner can intentionally restore the original
                        # bytes. Record that successor instead of reviving the
                        # previous dirty draft as the latest stopped snapshot.
                        if delta or acquisition.get('stopped_draft'):
                            reference = snapshot['acquisition_receipts'].get(lease['token'])
                            if reference is None: raise ValueError('Workspace draft lacks immutable acquisition receipt')
                            draft = {'type': 'workspace_draft', 'node': node,
                                'lease': {k: lease[k] for k in ('token', 'attempt', 'owner', 'worker')},
                                'source_payload': snapshot['envelope']['payload'], 'acquisition_receipt': reference,
                                'acquisition': copy.deepcopy(acquisition), 'acquisition_hash': digest(acquisition),
                                'contract': acquisition['contract'], 'input_hash': lease['fingerprint'],
                                'policy': self.node_evidence_policy(),
                                'authority': {**{k: workspace[k] for k in ('allocation', 'authorization', 'approval')},
                                    'inputs': self.node_workspace_authority_inputs(acquisition['inputs'], snapshot['artifacts'])},
                                'files': actual, 'workspace': digest(actual), 'outputs': delta, 'evidence': request['evidence']}
                            identity = digest(draft); snapshot['artifacts'][identity] = draft
                            step['workspace_draft'] = self.node_ref(identity, number)
                    leases.remove(lease)
                    response = {'next_steps': [step]}
                elif operation == 'bind':
                    _, receipt = self.node_policy(state)
                    if request.get('policy_receipt') != receipt or request.get('selection') != lease['selection']: raise ValueError('Exact policy receipt and actual model/effort required')
                    if lease['expires_at'] <= time.time(): raise ValueError('Lease expired; observe stopped owner before recovery')
                    actor = request.get('actor')
                    if not isinstance(actor, str) or not actor or lease['worker'] not in (None, actor): raise ValueError('Worker identity already bound or invalid')
                    self.node_independence(snapshot, state, actor)
                    lease['worker'] = actor
                    response = {'next_steps': [{'kind': 'perform', 'goal': number, 'node': node, 'lease': lease}]}
                else:
                    if request.get('actor') != lease['worker'] or not lease['worker']: raise ValueError('Exact bound actor required')
                    if operation == 'renew':
                        current = (state.get('input_hash') == lease['fingerprint']
                                   and state['state'] == 'ready')
                        lease['expires_at'] = pending['response']['next_steps'][0]['lease']['expires_at'] if pending else time.time() + 600
                        step = {'kind': 'renewed', 'goal': number, 'node': node,
                            'lease': lease['token'], 'actor': lease['worker'],
                            'expires_at': lease['expires_at'], 'current': current}
                        if not current:
                            step.update(reason=state.get('reason', 'workspace or input identity drift'),
                                action='Custody only: preserve the owned attempt; current review and input authority are still required before submission.')
                        response = {'next_steps': [step]}
                    elif operation != 'release':
                        if state.get('input_hash') != lease['fingerprint'] or state['state'] != 'ready': raise ValueError('Stale substantive input/contract/prerequisite; owner remains bound: ' + state.get('reason', 'workspace or input identity drift'))
                        if lease['expires_at'] <= time.time() and operation != 'release':
                            raise ValueError('Lease expired; observe stopped owner before recovery')
                    if operation == 'release':
                        if set(request) - {'operation', 'node', 'lease', 'actor', 'request_id'}:
                            raise ValueError('Lease release accepts only the exact owner identity')
                        leases.remove(lease)
                        response = {'next_steps': [{'kind': 'released', 'goal': number, 'node': node,
                            'lease': lease['token'], 'actor': lease['worker'],
                            'action': 'Exact owner relinquished this lease without producing a Result.'}]}
                    elif operation == 'block':
                        if request.get('category') != 'external-dependency' or not isinstance(request.get('reason'), str) or not request['reason'].strip(): raise ValueError('Infrastructure blocker requires factual external dependency reason')
                        lease['blocker'] = {'category': request['category'], 'reason': request['reason']}
                        response = {'next_steps': [{'kind': 'await_worker', 'goal': number, 'node': node, 'reason': request['reason'], 'lease': lease}]}
                    elif operation == 'submit':
                        if set(request) - {'operation', 'node', 'lease', 'actor', 'request_id', 'outputs', 'workspace_checks', 'verification_expectation', 'verification_timeout_seconds'}: raise ValueError('Unknown submission fields; host acquisition cannot be replaced')
                        expectation = request.get('verification_expectation', 'observed')
                        if expectation not in {'passed', 'observed'}: raise ValueError('Verification expectation must be passed or observed')
                        if 'verification_expectation' in request and not request.get('workspace_checks'): raise ValueError('Explicit verification expectation requires exact workspace_checks')
                        self.node_independence(snapshot, state, lease['worker'])
                        bundle = request.get('outputs'); contracts = state['contract']['outputs']
                        if not isinstance(bundle, dict) or set(bundle) != set(contracts): raise ValueError('Submission must supply exactly declared output slots')
                        for slot, content in bundle.items():
                            legacy_rejected_authorization = (
                                contracts[slot]['type'] == 'workspace_authorization'
                                and content is None
                                and isinstance(bundle.get('review'), dict)
                                and bundle['review'].get('decision') == 'changes_requested'
                            )
                            if not legacy_rejected_authorization and not ev.value_matches(contracts[slot]['schema'], content):
                                raise ValueError('Output type contract rejected slot ' + slot)
                        if node['node'] == 'publish' and self.node_native_delivery(snapshot):
                            candidate = self.node_candidate_state(snapshot)
                            value = bundle.get('value')
                            if (candidate['status'] != 'ready' or not isinstance(value, dict)
                                    or value.get('branch') != candidate['branch']
                                    or value.get('head_oid') != candidate['head_oid']
                                    or value.get('repository') != self.repository):
                                raise ValueError('Published candidate differs from the exact managed Git head')
                        self.node_validate_bundle(snapshot, state, bundle, lease['worker'])
                        verification = None
                        if request.get('workspace_checks'):
                            verification = self.node_verification_prepare(snapshot, state, lease, request)
                            if prepare_verification:
                                return {'_verification_prepare': verification}
                            if (prepared_verification is not None
                                    and verification['identity'] != prepared_verification):
                                raise ValueError('Verification authority, inputs, allocation, policy or workspace changed before finalize')
                        try:
                            proof_ref = self.node_workspace_proof(
                                snapshot, state, lease, request,
                                reuse_only=prepared_verification is not None)
                        except VerificationUncertain as exc:
                            return {'next_steps': [{'kind': 'await_worker', 'goal': number, 'node': node,
                                'lease': lease['token'], 'actor': lease['worker'], 'reason': str(exc),
                                'action': 'Observe this exact owner and verifier stopped, recover this lease, then reacquire before running a new request. Never infer completion from timeout or a log alone.',
                                'recovery_contract': {'operation': 'recover', 'node': node, 'lease': lease['token'],
                                    'actor': lease['worker'], 'worker_status': '<observed status>', 'evidence': '<terminal observation>'}}]}
                        proof = snapshot['artifacts'][proof_ref['hash']] if proof_ref else None
                        if proof and (expectation == 'passed' and not proof['passed'] or any(row.get('timed_out') or row.get('execution_error') for row in proof['commands'])):
                            response = {'next_steps': [{'kind': 'verification_failed', 'goal': number, 'node': node,
                                'lease': lease['token'], 'actor': lease['worker'], 'proof': proof_ref, 'commands': proof['commands'],
                                'action': 'Inspect the recorded logs, correct the authorized workspace, then submit the required checks with a new request_id under this same valid lease. Replay this exact request to inspect its original failure without rerunning.'}]}
                            return self.node_persist(snapshot, payload, response, request)
                        outputs = {}
                        previous = next((snapshot['artifacts'][ref['hash']]['content']['outputs'] for ref in reversed(snapshot['payload']['evidence']) if snapshot['artifacts'][ref['hash']]['content']['node'] == node), {})
                        for slot, content in bundle.items():
                            output = {'type': contracts[slot]['type'], 'content': content, 'producer': lease['attempt'], 'provenance': {'actor': lease['worker'], 'source': proof_ref, 'policy': self.node_evidence_policy(), 'approved_policy': digest(self.project['policy'])}}
                            identity = digest(output); snapshot['artifacts'][identity] = output; outputs[slot] = self.node_ref(identity, number)
                            if slot in previous: snapshot.setdefault('output_bases', {})[identity] = previous[slot]['hash']
                        result = {'node': node, 'attempt': lease['attempt'], 'contract': state['contract_hash'], 'inputs': lease['acquisition']['inputs'], 'executor': lease['worker'], 'outputs': outputs, 'resolutions': lease['acquisition']['resolutions']}
                        predecessor = snapshot['projection']['current'].get(
                            self.api._phase_evidence.task_key(node))
                        if predecessor is None:
                            predecessor = next(((reference, value['content'])
                                for reference in reversed(snapshot['payload']['evidence'])
                                if (value := snapshot['artifacts'][reference['hash']]).get('type') == 'result'
                                and value.get('content', {}).get('node') == node), None)
                        if predecessor is not None:
                            expected_revision = lease['acquisition'].get('expected_goal_revision')
                            if (type(expected_revision) is not int
                                    or expected_revision >= snapshot['envelope']['revision']):
                                raise ValueError('Replacement Result goal revision CAS precondition changed')
                            observed = next(((reference, value['content'])
                                for reference in reversed(snapshot['payload']['evidence'])
                                if (value := snapshot['artifacts'][reference['hash']]).get('type') == 'result'
                                and value.get('content', {}).get('node') == node), None)
                            if observed is None or observed[0] != predecessor[0]:
                                raise ValueError('Replacement Result predecessor CAS precondition changed')
                            result['supersedes_result'] = predecessor[0]
                            result['expected_goal_revision'] = expected_revision
                        artifact = {'type': 'result', 'content': result, 'producer': lease['attempt'], 'provenance': {'actor': lease['worker'], 'source': None, 'policy': self.node_evidence_policy(), 'approved_policy': digest(self.project['policy'])}}
                        identity = digest(artifact); snapshot['artifacts'][identity] = artifact
                        ref = self.node_ref(identity, number); payload['evidence'].append(ref); leases.remove(lease)
                        response = self.node_continuation(snapshot, payload, node, ref)
                    elif operation != 'renew':
                        raise ValueError('Unsupported generic operation; semantic evidence uses submit')
            return self.node_persist(snapshot, payload, response, request)

    def node_validate_bundle(self, snapshot, state, bundle, actor):
        """Validate semantic evidence as one candidate before appending any output."""
        ev = self.api._phase_evidence; projection = snapshot['projection']; artifacts = snapshot['artifacts']
        current = {ref['hash']: result for ref, result in projection['current'].values()}
        subject_results = {ref['hash']: result for result in current.values() for ref in result['outputs'].values()}
        historical_subject_results = {ref['hash']: result
            for result_ref in snapshot['payload']['evidence']
            for result in [artifacts[result_ref['hash']]['content']]
            for ref in result['outputs'].values()}
        history = [(ref, artifacts[ref['hash']]) for item in snapshot['payload']['evidence'] for ref in artifacts[item['hash']]['content']['outputs'].values()]
        proposed = [(state['contract']['outputs'][slot]['type'], value) for slot, value in bundle.items()]
        def nullable_supersession(contract):
            schema = contract.get('schema', {})
            return (contract.get('type') == 'supersession' and schema.get('kind') == 'union' and
                    any(variant.get('kind') == 'null' for variant in schema.get('variants', [])))
        transfer_values = [bundle[slot] for slot, contract in state['contract']['outputs'].items()
                           if nullable_supersession(contract)]
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
                if mapping.get('contract') != {'node': node, 'policy': self.node_evidence_policy()} or mapping['target'] != {'goal': snapshot['number'], 'node': node['id'], 'item': None, 'generation': 1}:
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
        def exact_obligation_input(reference):
            for item in state['inputs']:
                source = artifacts[item['source']['hash']]
                if source.get('type') != 'obligation_context': continue
                try: selected = ev.selected_path(source['content'], item['path'])
                except (ValueError, KeyError, TypeError): continue
                if isinstance(selected, dict) and reference in (selected.get('admission'), selected.get('finding')):
                    return True
            return False
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
                if value.get('policy') not in {digest(self.project['policy']), self.node_evidence_policy()} or value.get('decision') != 'approved': raise ValueError('Authorization policy or decision mismatch')
                legacy_field = 'context' if kind == 'repository_authorization' else 'subject'
                reference = value.get(legacy_field)
                if reference is not None:
                    read(reference, 'repository_context' if kind == 'repository_authorization' else 'publication_evidence')
                    if not exact_input(reference): raise ValueError('Authorization subject differs from exact declared input')
                    reviewed(reference, value.get('review'))
                else:
                    # The evidence-DAG publication path authorizes its exact
                    # topology-selected or published candidate directly.  The
                    # candidate and all approved review/migration joins are
                    # declared inputs of this root node; task identities bound
                    # the authorization to the configured downstream effect.
                    reference = value.get('manifest')
                    candidate_kind = 'delivery_candidate' if kind == 'repository_authorization' else 'published_candidate'
                    read(reference, candidate_kind)
                    if not exact_input(reference): raise ValueError('Authorization manifest differs from exact declared candidate input')
                    tasks = value.get('tasks')
                    expected = 'publish' if kind == 'repository_authorization' else 'merge'
                    if (not isinstance(tasks, list) or not any(
                            item.get('goal') == snapshot['number'] and item.get('node') == expected
                            and item.get('item') is None and item.get('generation') == 1
                            for item in tasks if isinstance(item, dict))):
                        raise ValueError('Authorization tasks omit the exact configured downstream effect')
                if kind == 'publication_authorization' and value.get('subject') is not None:
                    producer = subject_results[reference['hash']]
                    publication = projection['states'][ev.task_key(producer['node'])].get('publication')
                    if not publication or 'error' in publication: raise ValueError('Current provider publication evidence is required')
                    self.node_ci_required(publication['observed'])
            elif kind == 'publication_evidence':
                publication = state.get('publication')
                evidence_contract = next(
                    contract for contract in state['contract']['outputs'].values()
                    if contract.get('type') == 'publication_evidence')
                declared_fields = evidence_contract['schema']['fields']
                expected = {name: publication['observed'].get(name) for name in declared_fields} if publication else None
                if not publication or publication['observed'].get('pr') is None or value != expected: raise ValueError('Publication evidence differs from current exact provider head/base/CI')
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
                prefix, suffix = self.api._migration_batch.human_parts(self, snapshot['issue']['body'])
                if not matching or any(row.get('target_envelope') != snapshot['envelope'] or row.get('human_hash') != digest(prefix + suffix) for row in matching):
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
                                      'provenance': {'actor': historical['actor'], 'source': mapping_ref, 'policy': self.node_evidence_policy(), 'approved_policy': digest(self.project['policy'])}}
                            identity = digest(output); artifacts[identity] = output; outputs[slot] = self.node_ref(identity, snapshot['number'])
                        mapped = {'node': mapping['target'], 'attempt': attempt, 'contract': mapped_state['contract_hash'], 'inputs': mapped_state['inputs'],
                                  'executor': historical['actor'], 'outputs': outputs, 'resolutions': mapped_state['resolutions']}
                        result_blob = {'type': 'result', 'content': mapped, 'producer': attempt,
                                       'provenance': {'actor': historical['actor'], 'source': None, 'policy': self.node_evidence_policy(), 'approved_policy': digest(self.project['policy'])}}
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
            elif kind == 'child_delivery_join':
                # Relationship selection is resolved by the host from
                # ``#children``.  The worker may summarize or inspect it but
                # cannot substitute a non-child/stale Result in the emitted
                # join: the output must equal the exact identity-bound input.
                selected = state['values'].get('children')
                if not isinstance(selected, dict) or value != selected:
                    raise ValueError('Child delivery join must preserve every exact immediate-child terminal Result')
            elif kind == 'delivery_candidate':
                decomposition = state['values'].get('decomposition')
                integration = state['values'].get('integration')
                delivery_class = decomposition.get('delivery_class') if isinstance(decomposition, dict) else None
                applicability = integration.get('applicability') if isinstance(integration, dict) else None
                sources = {binding['name']: binding['source'] for binding in state['inputs']}
                selected = 'integration' if delivery_class == 'composition' else 'implementation'
                expected_applicability = 'applicable' if delivery_class == 'composition' else 'not_applicable'
                if (delivery_class not in {'leaf', 'composition', 'atomic'}
                        or applicability != expected_applicability
                        or value.get('delivery_class') != delivery_class
                        or value.get('integration_applicability') != expected_applicability
                        or value.get('candidate') != sources.get(selected)
                        or not value.get('rationale', '').strip()):
                    raise ValueError('Delivery candidate must bind exactly one candidate selected by reviewed topology and typed integration applicability')
            elif kind == 'workspace_authorization':
                decisions = [review.get('decision') for output_type, review in proposed
                             if output_type == 'review_decision' and isinstance(review, dict)]
                if value is None:
                    if not decisions or any(decision != 'changes_requested' for decision in decisions):
                        raise ValueError('Null workspace authorization requires an explicit rejected review')
                elif 'changes_requested' in decisions:
                    raise ValueError('A rejected review cannot grant workspace authorization')
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
            elif kind == 'finding_registry' and any(
                    allowed['type'] == kind for allowed in state['contract']['permits']):
                # Scoped retention is an explicit contract. Older generic pair
                # maps use this type name without permits and grant no authority.
                if actor != (self.runtime or {}).get('root_id') or state['contract']['executor']['role'] != 'root':
                    raise ValueError('Retained finding registry requires authenticated root')
                expected = {}
                for retained in projection['obligations'].values():
                    try:
                        permit(kind, retained['content']['target'])
                    except ValueError:
                        continue
                    identifier = retained['content']['id']
                    if identifier in expected:
                        raise ValueError('Finding registry scope has ambiguous retained identities')
                    expected[identifier] = retained['finding']
                if value['items'] != expected:
                    raise ValueError('Finding registry must retain every exact admitted finding in its permitted scope')
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
                if transfer_values:
                    if len(transfer_values) != 1:
                        raise ValueError('Correction admission requires one exact atomic supersession transfer')
                    transfer = transfer_values[0]
                    if prior is None:
                        if transfer is not None:
                            raise ValueError('First admitted revision requires explicit null supersession transfer')
                    elif (not isinstance(transfer, dict) or transfer.get('prior') != prior['finding'] or
                          transfer.get('replacement') != value['finding']):
                        raise ValueError('Replacement admission requires atomic exact coverage transfer')
                elif prior and prior['finding'] != value['finding'] and not any(
                        k == 'supersession' and isinstance(v, dict) and
                        v.get('prior') == prior['finding'] and v.get('replacement') == value['finding']
                        for k, v in proposed):
                    raise ValueError('Supersession requires atomic exact coverage transfer')
            elif kind == 'applicability_assessment':
                finding = read(value['finding'], 'finding'); prior = obligation(finding)
                permit(kind, finding['target']); authority_result = authority(value['authority'])
                expansion = next((row for row in snapshot['graph']['task_sets']
                                  if row['id'] == state.get('expansion')), None)
                if (expansion and expansion['source'].get('producer') == {'slot': 'obligation_selections'}
                        and not any(binding['name'] == 'context' and binding['mode'] == 'identity'
                                    and not binding['path'] and binding['source'] in authority_result['outputs'].values()
                                    for binding in state['inputs'])):
                    raise ValueError('Applicability authority must be the exact bound root context Result')
                if not prior or prior['finding'] != value['finding'] or prior['admission'] != value['admission'] or prior['applicability'] != 'unresolved':
                    raise ValueError('Applicability assessment requires the exact current unresolved admission and finding')
                if value['applicability'] not in ('applicable', 'not_applicable') or not value['rationale'].strip():
                    raise ValueError('Applicability assessment must classify the obligation with evidence rationale')
                if not exact_obligation_input(value['admission']) or not exact_obligation_input(value['finding']):
                    raise ValueError('Applicability assessment must bind the exact admission and finding')
                if (value['subjects'] != finding.get('subjects') or not value['subjects']
                        or any(ref['hash'] not in historical_subject_results or not exact_input(ref)
                               for ref in value['subjects'])):
                    raise ValueError('Applicability assessment requires the finding-bound exact historical subjects')
                reviewer = read(value['reviewer_result'], 'result')
                if value['reviewer_result']['hash'] not in current:
                    raise ValueError('Applicability assessment requires the exact current reviewer Result')
                if not any(binding['source'] in reviewer['outputs'].values() and binding['mode'] == 'identity'
                           for binding in state['inputs']):
                    raise ValueError('Applicability assessment must bind output from the current reviewer Result')
                inspected = {binding['source']['hash'] for binding in reviewer['inputs']}
                if any(ref['hash'] not in inspected for ref in value['subjects']):
                    raise ValueError('Applicability reviewer did not inspect every corrected subject')
                reviewer_state = projection['states'][ev.task_key(reviewer['node'])]
                independent_targets = [target for row in reviewer_state['resolutions']
                    if row['selector'] in reviewer_state['contract']['independent_of']
                    for target in row['targets']]
                if any(historical_subject_results[ref['hash']]['node'] not in independent_targets
                       for ref in value['subjects']):
                    raise ValueError('Applicability reviewer requires declared exact subject independence')
                if any(historical_subject_results[ref['hash']]['executor'] == reviewer['executor']
                       for ref in value['subjects']):
                    raise ValueError('Applicability reviewer must be independent of corrected subjects')
            elif kind == 'supersession':
                if value is None:
                    admissions = [candidate for candidate_kind, candidate in proposed
                                  if candidate_kind == 'admission']
                    if len(admissions) != 1:
                        raise ValueError('Null supersession transfer requires one atomic admission')
                    candidate = read(admissions[0]['finding'], 'finding')
                    if obligation(candidate) is not None:
                        raise ValueError('Null supersession transfer is allowed only without a prior admitted revision')
                    continue
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
                exact_subjects = {item['source']['hash'] for item in state['inputs']
                                  if item['name'] == 'subject' and item['mode'] == 'identity'
                                  and not item['path']}
                if exact_subjects:
                    for reference in snapshot['payload']['evidence']:
                        result = snapshot['artifacts'][reference['hash']]['content']
                        if (result['node'] == node and result['executor'] == actor
                                and any(ref['hash'] in exact_subjects
                                        for ref in result['outputs'].values())):
                            raise ValueError('Independent reviewer cannot be the historical subject executor')


def capacity_step(active_leases, limit):
    return {'kind': 'await_worker', 'assignment': 'root',
            'action': 'Reviewed max_workers capacity is occupied. Reconcile, release, or recover an existing task lease before starting another worker.',
            'active_leases': active_leases, 'max_workers': limit,
            'recheck': {'after_seconds': 30, 'command': ['--intent', 'execute', '--runtime', '<runtime.json>'],
                        'action': 'Recheck active leases after the interval; do not start work beyond the reviewed capacity.'}}


def scoped_frontier(steps, engine, limit, number, *, prospective_leases=None):
    """Apply this machine's worker ceiling to the addressed frontier."""
    active = 0
    if any(step.get('kind') in {'execute', 'review', 'human_approval'} and isinstance(step.get('start'), dict) for step in steps):
        active = local_worker_count(engine)
        # A submission continuation is computed before its post-commit local
        # cleanup. The submitting durable lease is absent from the prospective
        # payload, so reserve its just-freed slot for the returned frontier.
        if prospective_leases is not None:
            active = max(0, active - 1)
    runnable, waiting, capacity_blocked = [], [], False
    for step in steps:
        if step.get('kind') in {'execute', 'review', 'human_approval'} and isinstance(step.get('start'), dict):
            if active < limit: runnable.append(step)
            else: capacity_blocked = True
        elif step.get('kind') in {'blocker', 'blocked', 'dependency', 'await_worker'}: waiting.append(step)
        else: runnable.append(step)
    if capacity_blocked and len(runnable) < limit: runnable.append(capacity_step(active, limit))
    generic = any('node' in row for row in runnable + waiting)
    result = runnable + waiting if generic else (runnable or waiting)[:limit]
    return result or [{'kind': 'terminal_report', 'assignment': 'root', 'goal': number,
                       'state': 'complete', 'action': 'This goal has no remaining workflow work. Report completion; no CLI command is required.'}]


def checkpoint(api, repo, project, runtime, number=None, *, engine=None):
    engine = engine or Workflow(api, repo, project, runtime)
    goals = engine.portfolio(allow_invalid=True)
    release_section = next((section for section in project.get('policy', {}).get('sections', [])
                            if section.get('id') == 'git_review_release'), None)
    release_policy = ((release_section or {}).get('configuration') or {}).get('release_planning')
    release_plan = None
    release_selection = None
    if number is None and isinstance(release_policy, dict) and release_policy.get('enabled'):
        release_plan = api.GitHubReleasePlanAdapter(repo, engine.repository).read(engine.repository)
        if release_plan is None:
            return {'next_steps': [{'kind': 'blocker', 'assignment': 'root',
                'reason': 'Release plan is missing; portfolio dispatch is blocked.'}]}
        owned = {row['key'] for row in goals if (row.get('claim') or {}).get('owner')}
        release_selection = api._releases.select_release_work(goals, release_policy, release_plan, owned)
    ordering_policy = next(
        (
            section.get('configuration', {}).get('portfolio_order')
            for section in project.get('policy', {}).get('sections', [])
            if isinstance(section, dict) and section.get('id') == 'autonomy_approval_parallelism'
        ),
        None,
    )
    limit = worker_limit(project)
    active_workers = local_worker_count(engine)
    remaining_starts = max(0, limit - active_workers)
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
                    waiting.append({**capacity_step(active_workers, limit),
                                    'goal': step.get('goal', step.get('node', {}).get('goal'))})
            elif step.get('kind') in {'blocker', 'blocked', 'dependency', 'await_worker'}:
                waiting.append(step)
            else:
                runnable.append(step)
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
        maintenance = getattr(engine, '_normalize_selected', lambda selected: None)(number)
        if maintenance is not None:
            return {'next_steps': maintenance}
        steps = scoped_frontier(engine.step(number), engine, limit, number)
        diagnostics = getattr(engine, '_normalization_diagnostics', {}).get(number)
        if diagnostics:
            steps.append({'kind': 'repair', 'goal': number,
                'reason': 'Historical graph recovery is unsupported; existing reviewed work is unchanged.',
                'diagnostics': diagnostics,
                'action': 'Use independent graph review and explicit approval for any required recovery extension.'})
        hydration = engine.hydration_checkpoint_candidate(number)
        if hydration is None:
            return {'next_steps': steps}
        semantic_blockers = {'blocker', 'blocked', 'dependency', 'await_worker', 'repair'}
        if any(step.get('kind') in semantic_blockers for step in steps):
            return {'next_steps': steps + [hydration]}
        return {'next_steps': [hydration]}
    runnable_steps = []
    waiting_steps = []
    ordered_goals = api.effective_goal_order(goals, ordering_policy)
    later_release_keys = set()
    if release_selection is not None:
        active_eligible = {row['goal'] for row in release_selection['ordered']}
        eligible = set(active_eligible)
        if release_policy.get('execution_scope') == 'later_when_active_blocked':
            by_key = {row['key']: row for row in goals}
            later_release_keys = {row['key'] for row in goals
                if api._releases.target_release(release_plan, row['key']) > release_plan['next_release']
                and row['key'] not in owned and row.get('work_state') in {'triage', 'prepare', 'write'}
                and not any(by_key.get(dep, {}).get('status') not in {'done', 'cancelled'}
                            for dep in row.get('depends_on', []))}
            eligible.update(later_release_keys)
        ordered_goals = [row for row in ordered_goals if row['goal'] in eligible]
        ordered_goals.sort(key=lambda row: (row['goal'] in later_release_keys,
                                            next(index for index, item in enumerate(api.effective_goal_order(goals, ordering_policy))
                                                 if item['goal'] == row['goal'])))
    order_rank = {item['goal']: index for index, item in enumerate(ordered_goals)}
    def response(steps, selected):
        def goal_key(step):
            return step.get('goal', step.get('node', {}).get('goal'))
        deferred = sorted(waiting_steps, key=lambda step: order_rank.get(goal_key(step), len(order_rank)))
        selected_keys = {goal_key(step) for step in selected}
        deferred_keys = {goal_key(step) for step in deferred} - selected_keys
        # Keep selected work visible even when a long preferred prefix waits.
        # Both projections remain bounded and retain the effective DAG order.
        visible = selected_keys | set([
            item['goal'] for item in ordered_goals if item['goal'] in deferred_keys
        ][:max(0, limit - len(selected_keys & set(order_rank)))])
        ordering = [{**item, 'status': 'selected' if item['goal'] in selected_keys else 'deferred'}
                    for item in ordered_goals if item['goal'] in visible][:limit]
        if not selected and deferred:
            steps = deferred[:limit]
        return {'next_steps': steps, 'effective_order': ordering, 'deferred_steps': deferred[:limit]}
    candidate_batch = []
    migration_attempted = False
    normalization_attempted = False
    def flush_candidates():
        nonlocal candidate_batch, normalization_attempted
        if not candidate_batch: return
        if not normalization_attempted:
            normalization_attempted = True
            selected = candidate_batch[0]
            maintenance = getattr(engine, '_normalize_selected', lambda number: None)(selected['key'])
            if maintenance is not None:
                partition(maintenance, runnable_steps, waiting_steps)
                candidate_batch = candidate_batch[1:]
        if not candidate_batch: return
        with ThreadPoolExecutor(max_workers=min(limit, len(candidate_batch))) as pool:
            observed = list(pool.map(engine.step, [goal['key'] for goal in candidate_batch]))
        for goal, candidate_steps in zip(candidate_batch, observed):
            diagnostics = getattr(engine, '_normalization_diagnostics', {}).get(goal['key'])
            if diagnostics:
                candidate_steps.append({'kind': 'repair', 'goal': goal['key'],
                    'reason': 'Historical graph recovery is unsupported; existing reviewed work is unchanged.',
                    'diagnostics': diagnostics,
                    'action': 'Use independent graph review and explicit approval for any required recovery extension.'})
            partition(candidate_steps, runnable_steps, waiting_steps)
        candidate_batch = []
    later_release_started = False
    for item in ordered_goals:
        if item['goal'] in later_release_keys and not later_release_started:
            flush_candidates()
            if runnable_steps:
                break
            later_release_started = True
        goal = next(goal for goal in goals if goal['key'] == item['goal'])
        if goal['status'] in {'done', 'cancelled'}:
            continue
        reconciliation = engine.reconciliation_step(goal)
        if isinstance(reconciliation, dict):
            flush_candidates()
            if len(runnable_steps) >= limit: break
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
        if goal.get('schema_version') != 2:
            flush_candidates()
            if len(runnable_steps) >= limit: break
            if migration_attempted:
                waiting_steps.append({'kind': 'blocker', 'goal': goal['key'],
                    'reason': 'migration_frontier_deferred',
                    'remediation': {'action': 'Retry this predecessor on a subsequent checkpoint; only one migration is attempted per checkpoint.',
                        'retry': {'operation': 'migration_batch', 'action': 'migrate', 'goals': [goal['key']]}}})
                continue
            # Broad routing may convert the one goal it actually selected, but
            # must never turn schema conversion into a repository-wide sweep.
            migration_attempted = True
            result = api._migration_batch.run(engine, {'action': 'migrate', 'goals': [goal['key']]})
            member = result['next_steps'][0]['members'][str(goal['key'])]
            if member['status'] in {'migrated', 'already_current'}:
                partition(member['next_steps'], runnable_steps, waiting_steps)
                steps = (runnable_steps or waiting_steps)[:limit]
                return response(steps, runnable_steps[:limit])
            waiting_steps.append({'kind': 'blocker', 'goal': goal['key'],
                'reason': member.get('reason', member['status']),
                'remediation': member.get('remediation')})
            continue
        candidate_batch.append(goal)
        if len(candidate_batch) >= limit:
            flush_candidates()
            if len(runnable_steps) >= limit: break
    flush_candidates()
    if capacity_blocked and len(runnable_steps) < limit:
        runnable_steps.append(capacity_step(active_workers, limit))
    steps = (runnable_steps or waiting_steps)[:limit]
    if not steps:
        if release_selection is not None:
            observation = api.GitHubReleasePlanAdapter(repo, engine.repository).observe_release(
                engine.repository, release_plan['next_release'])
            readiness = api._releases.release_readiness(observation['members'],
                active_owners=set(observation['active_owners']),
                observed_commits=set(observation['observed_commits']),
                source_ancestors=set(observation['source_ancestors']),
                forbidden_commits=set(observation.get('forbidden_commits', [])))
            if readiness['status'] == 'ready':
                steps = [{'kind': 'release_checkpoint', 'assignment': 'root',
                    'release': release_plan['next_release'],
                    'action': 'Propose, freeze, and cut the ready release before dispatching later-release work.',
                    'submission': {'command': 'release checkpoint', 'operation': 'propose',
                                   'request_id': '<stable-request-id>', 'authority': '<coordinator-authority>'}}]
            else:
                steps = [{'kind': 'blocker', 'assignment': 'root', 'reason': readiness}]
        else:
            steps = [{'kind': 'terminal_report', 'assignment': 'root', 'state': 'complete',
                      'action': 'All goals are complete or the portfolio is empty. Report workflow exhaustion; no CLI command is required.'}]
    return response(steps, runnable_steps[:limit])


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
            proposal_hash = digest(proposal)
            proposal_path = directory / (proposal_hash.split(':')[1] + '.json')
            stale_exact_replay = False
            try:
                prospective = preflight_policy_proposal(api, repo, proposal)
            except ValueError as error:
                stored = None
                try:
                    stored = json.loads(proposal_path.read_text())
                except FileNotFoundError:
                    pass
                if (str(error) != 'Invalid policy proposal: base_digest is stale or missing'
                        or stored != proposal or digest(stored) != proposal_hash):
                    raise
                replay = copy.deepcopy(proposal)
                replay['base_digest'] = api.initialization_base_digest(repo)
                prospective = preflight_policy_proposal(api, repo, replay)
                stale_exact_replay = True
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
            if stale_exact_replay:
                raise ValueError('Invalid policy proposal: base_digest is stale or missing')
            directory.mkdir(parents=True, exist_ok=True)
            api.atomic_text(proposal_path, json.dumps(proposal, ensure_ascii=False, sort_keys=True))
            return {'next_steps': [{'kind': 'human_approval', 'assignment': 'root', 'action': 'Review this exact project/policy proposal with the user before approving.', 'proposal': str(proposal_path), 'hash': proposal_hash, 'classification': classification, 'submission': {'operation': 'policy_approve', 'proposal_hash': proposal_hash, 'approved_by': '<user>'}}]}
        proposal_hash = payload['proposal_hash']
        if not explicit_approval(payload.get('approved_by')) or not isinstance(proposal_hash, str) or not __import__('re').fullmatch(r'sha256:[0-9a-f]{64}', proposal_hash):
            raise ValueError('Explicit human approval of the exact proposal hash is required')
        proposal = json.loads((directory / (proposal_hash.split(':')[1] + '.json')).read_text())
        if digest(proposal) != proposal_hash:
            raise ValueError('Policy proposal changed after review')
        prospective = preflight_policy_proposal(api, repo, proposal)
        reviewed_graph = policy_section(prospective, 'workflow_adherence')['configuration']['phase_dag']
        api._static_workflow.definition(reviewed_graph, api._graph_compiler)
        applied = api.apply_plan(repo, prospective)
        if not applied.get('initialized'):
            api.confirm_project(repo, applied['policy_digest'], payload['approved_by'], [], True)
        # Attachment is a provider transaction and passes the same fresh boundary
        # as every other public mutation below. The reviewed policy stays exact.
        gate = None
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
    if payload is not None and operation not in {'read', 'heartbeat'}:
        guard_stack = getattr(api, '_guarded_mutations', [])
        active = [record for record in guard_stack
                  if record['adapter'] is engine._mutation_adapter]
        restore = {name: getattr(engine._mutation_adapter, name) for name in
                   ('get_issue', 'get_issue_comments', 'create_issue_comment', 'update_issue')}
        base = (active[0]['base'] if active else restore)
        original_issue = base['get_issue']
        original_comments = base['get_issue_comments']
        read_cache = {'issues': {}, 'comments': {}}
        normalization_write_depth = 0
        def cached_issue(target):
            if normalization_write_depth:
                return original_issue(target)
            if target not in read_cache['issues']:
                read_cache['issues'][target] = original_issue(target)
            return copy.deepcopy(read_cache['issues'][target])
        def cached_comments(target):
            if normalization_write_depth:
                return original_comments(target)
            if target not in read_cache['comments']:
                read_cache['comments'][target] = original_comments(target)
            return copy.deepcopy(read_cache['comments'][target])
        engine._mutation_adapter.get_issue = cached_issue
        engine._mutation_adapter.get_issue_comments = cached_comments
        def clear_invocation_reads():
            read_cache['issues'].clear(); read_cache['comments'].clear()
            engine.invalidate()
        engine._clear_invocation_reads = clear_invocation_reads
        # Derived and invocation-local observations accelerate reads only.  A
        # write gets a complete, ordered authority boundary immediately before
        # every provider mutation, including a second write in one transaction.
        def fresh_mutation_boundary(target):
            current_package = api._package.package_status()
            if not current_package.get('ok'):
                raise ValueError('Repair or reinstall the invalid ZzzOps package')
            current_gate = api.workflow_context_step(
                repo, current_package, skip_installation_validation=skip_installation_validation)
            if current_gate:
                raise ValueError('Repository context changed before provider mutation')
            current_provenance = {field: current_package.get(field) for field in ('version', 'revision')}
            current_installation = (api._installation.validation_status(repo, current_provenance)
                                    if all(isinstance(value, str) for value in current_provenance.values())
                                    else {'required': False})
            if current_installation.get('required') and not skip_installation_validation:
                raise ValueError('Installation validation changed before provider mutation')
            current_project = api.reviewed_project_state(repo)
            if digest(current_project) != digest(project):
                raise ValueError('Reviewed policy changed before provider mutation')
            reservation = getattr(engine, '_storage_reservation', None)
            if not isinstance(reservation, dict) or not reservation.get('valid'):
                raise ValueError('A current workflow storage reservation is required before provider mutation')
            resource_reader = getattr(reservation['adapter'], 'get_label', None)
            if not callable(resource_reader):
                if reservation.get('expires_at', 0) <= time.time():
                    reservation['valid'] = False
                    raise ValueError('Provider did not confirm targeted storage ownership before mutation')
                resource = None
                ownership = {'repository_key': api.reservation_repository_key(engine.repository),
                             'key': 'workflow', 'owner': reservation['owner'],
                             'run_id': reservation['run'], 'expires_at': reservation['expires_at']}
            else:
                resource = resource_reader(api.storage_lock_label_name('workflow'))
                try:
                    ownership = api.parse_storage_lock_description((resource or {}).get('description'))
                except (ValueError, TypeError):
                    reservation['valid'] = False
                    raise ValueError('Provider did not confirm targeted storage ownership before mutation')
            if (ownership.get('repository_key') != api.reservation_repository_key(engine.repository)
                    or ownership.get('key') != 'workflow'
                    or ownership.get('owner') != reservation['owner']
                    or ownership.get('run_id') != reservation['run']
                    or ownership.get('expires_at', 0) <= time.time()):
                reservation['valid'] = False
                raise ValueError('Provider did not confirm targeted storage ownership before mutation')
            reservation['expires_at'] = ownership['expires_at']
            if hasattr(api, 'invalidate_provider_reads'):
                api.invalidate_provider_reads(repo, engine.repository)
            api.provider_issue_snapshot(repo, engine.repository, target)
            # A complete history read preserves provider uncertainty semantics;
            # cached materialization never authorizes a write.
            original_comments(target)
        wrappers = {'get_issue': cached_issue, 'get_issue_comments': cached_comments}
        for method_name in ('create_issue_comment', 'update_issue'):
            original = base[method_name]
            def guarded(*args, _original=original, **kwargs):
                nonlocal normalization_write_depth
                target = args[0] if args else kwargs.get('number')
                engine.clear_publication_projection()
                try:
                    fresh_mutation_boundary(target)
                    # The transactional adapter observes its prior state and
                    # confirms its write inside this call. Normalization needs
                    # fresh reads for that whole interval, not only after it.
                    if operation == 'graph_normalize':
                        normalization_write_depth += 1
                        try:
                            return _original(*args, **kwargs)
                        finally:
                            normalization_write_depth -= 1
                    return _original(*args, **kwargs)
                finally:
                    engine.clear_publication_projection()
                    read_cache['issues'].clear(); read_cache['comments'].clear()
            setattr(engine._mutation_adapter, method_name, guarded)
            wrappers[method_name] = guarded
        record = {'adapter': engine._mutation_adapter, 'restore': restore,
                  'base': base, 'wrappers': wrappers}
        api._guarded_mutations = guard_stack + [record]
        @contextmanager
        def suspend_mutation_guard():
            for method_name, original in base.items():
                setattr(engine._mutation_adapter, method_name, original)
            try:
                yield
            finally:
                for method_name, wrapper in wrappers.items():
                    setattr(engine._mutation_adapter, method_name, wrapper)
        engine._suspend_mutation_guard = suspend_mutation_guard
    if operation == 'policy_approve':
        return {'next_steps': [{'kind': 'checkpoint', 'action': 'Reviewed workflow policy is active. Reconcile required phase data lazily; historical goal graphs and evidence remain immutable.'}]}
    if payload is None or operation in {'read', 'heartbeat'}: engine.read_only()
    if payload is None and intent == 'execute' and source == '$execute-zzzops':
        engine._normalization_read_epoch = object()
        def normalize_selected(selected):
            try:
                request = engine.node_normalization_candidate(selected)
                if request is None:
                    return None
                if 'normalization_diagnostics' in request:
                    engine._normalization_diagnostics = {selected: request['normalization_diagnostics']}
                    return None
                result = public_run(api, repo, intent, source, runtime, request, selected,
                                    skip_installation_validation=skip_installation_validation,
                                    payload_supplied=True)
                if result.get('type') != 'graph_normalization':
                    return result['next_steps']
                engine.invalidate()
                confirmed = engine.node_snapshot(selected)
                if confirmed['payload']['graph']['hash'] != request['target_hash']:
                    raise ValueError('Normalization target readback is unconfirmed')
                return None
            except (ValueError, OSError, RuntimeError) as exc:
                return [{'kind': 'blocker', 'goal': selected,
                         'reason': 'Graph normalization deferred: ' + str(exc)}]
        engine._normalize_selected = normalize_selected

    if operation == 'migration_batch':
        return api._migration_batch.run(engine, payload)
    if operation == 'hydration_checkpoint':
        if number is None or set(payload) != {'operation', 'checkpoint', 'request_id'}:
            raise ValueError('Hydration checkpoint requires exact goal, checkpoint and request_id fields')
        if not isinstance(payload.get('request_id'), str) or not payload['request_id']:
            raise ValueError('Hydration checkpoint request_id is required')
        with engine.locked():
            return engine.publish_hydration_checkpoint(number, payload.get('checkpoint'))
    if intent == 'execute' and source == '$execute-zzzops' and operation not in {'read', 'recover', 'release', 'renew', 'heartbeat'}:
        if number is not None:
            # Schema administration consumes no stale task request or ownership.
            try:
                _, _, schema_state = api._migration_batch.state(engine, number)
                if schema_state == 'legacy':
                    result = api._migration_batch.run(engine, {'action': 'migrate', 'goals': [number]})
                    member = result['next_steps'][0]['members'][str(number)]
                    if member['status'] == 'migrated': return {'next_steps': member['next_steps']}
                    # Existing owner recovery stays available from its normal contract.
                    if 'ownership' not in member.get('reason', '').lower():
                        return {'next_steps': [{'kind': 'blocker', 'goal': number, 'reason': member.get('reason', member['status']), 'remediation': member.get('remediation')}]}
            except api.GoalHistoryReadError:
                raise
            except (ValueError, KeyError, OSError) as exc:
                return {'next_steps': [{'kind': 'blocker', 'goal': number, 'reason': str(exc), 'remediation': api._migration_batch.remediation(number, str(exc))}]}
    portfolio_rows = engine.portfolio(allow_invalid=True) if operation not in {
        'read', 'release', 'renew', 'capture', 'capture_propose'} else None
    if operation == 'start' and number is not None:
        release_policy = policy_section(project, 'git_review_release')['configuration'].get('release_planning')
        if isinstance(release_policy, dict) and release_policy.get('enabled'):
            release_plan = api.GitHubReleasePlanAdapter(repo, engine.repository).read(engine.repository)
            if release_plan is None: raise ValueError('Release plan is missing; explicit goal dispatch is blocked')
            owned = {row['key'] for row in portfolio_rows if (row.get('claim') or {}).get('owner')}
            eligible = api._releases.select_release_work(portfolio_rows, release_policy, release_plan, owned)
            allowed = {row['goal'] for row in eligible['ordered']}
            if (number not in allowed
                    and release_policy.get('execution_scope') == 'later_when_active_blocked'):
                observed = checkpoint(api, repo, project, runtime, engine=engine)
                allowed.update(step.get('goal', (step.get('node') or {}).get('goal'))
                               for step in observed.get('next_steps', [])
                               if step.get('kind') in {'execute', 'review', 'human_approval'})
            if number not in allowed:
                raise ValueError(f'Goal #{number} is not eligible under the current release plan')
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
    if operation in {'graph_prepare', 'graph_review', 'graph_adopt', 'graph_review_bootstrap', 'graph_normalize'}:
        # Replay already committed history without reviving retired mutation
        # authority. Incomplete old transactions remain explicit recovery debt.
        if number is not None and payload.get('request_id'):
            historical = api.parse_managed_goal(engine.adapter.get_issue(number)['body'], number)
            if historical and historical.get('schema_version') == 2:
                durable = engine.read_artifact(number, historical['payload'])
                if any(row['request'] == payload['request_id'] for row in durable['operational']['receipts']):
                    return engine.node_mutate_phase(number, payload)
        raise ValueError('Workflow topology belongs to reviewed project policy; reconcile phase data or update project policy, not individual goal graphs. An interrupted retired graph transaction requires exact checkpoint reconciliation; preserve its frozen request and history.')
    if operation == 'goal_dependency_prepare' and number is not None:
        if set(payload) != {'operation', 'request_id', 'old', 'replacement', 'rationale'}:
            raise ValueError('Goal dependency preview requires one exact edge and rationale')
        snapshot = engine.node_snapshot(number)
        proposal = engine.node_dependency_proposal(snapshot, payload['old'],
            payload['replacement'], payload['rationale'])
        return {'next_steps': [{'kind': 'review_required', 'assignment': 'root',
            'goal': number, 'proposal': proposal,
            'action': 'Give this exact dependency proposal and impact to an independent reviewer.',
            'submission': {'operation': 'goal_dependency_review',
                           'request_id': 'goal-dependency-review-' + digest(proposal)[7:],
                           'actor': '<independent reviewer thread>', 'proposal': proposal,
                           'decision': '<approved or changes_requested>',
                           'report': '<independent review report>'}}]}
    if operation == 'goal_external_blocker_prepare' and number is not None:
        snapshot = engine.node_snapshot(number)
        return engine.node_external_blocker_candidate(snapshot, payload)
    if operation in {'goal_external_blocker_review', 'goal_external_blocker_apply'} and number is not None:
        return engine.node_mutate_phase(number, payload)
    if operation == 'checkpoint_reconcile_prepare' and number is not None:
        if set(payload) != {'operation', 'transaction', 'rationale', 'request_id'}:
            raise ValueError('Checkpoint reconciliation preparation requires exact transaction and rationale')
        with engine.locked():
            proposal = engine.node_checkpoint_reconciliation_proposal(
                engine.node_snapshot(number), payload['transaction'], payload['rationale'])
        return {'next_steps': [{'kind': 'review_required', 'assignment': 'root', 'goal': number,
                'proposal': proposal,
                'action': 'Give this exact stale-checkpoint manifest to an independent reviewer.',
                'submission': {'operation': 'checkpoint_reconcile_review', 'proposal': proposal,
                               'actor': None, 'decision': None, 'report': None,
                               'request_id': 'checkpoint-reconcile-review-' + digest(proposal)[7:]}}]}
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
        request = api._goals.normalize_deferred_goal_create(payload['request'])
        errors = api.validate_goal_create(request, allow_deferred=True)
        if errors:
            raise ValueError('; '.join(errors))
        if not api._goals.goal_acceptance_criteria(request['body']):
            raise ValueError('Goal design has no required acceptance criteria. '
                             + ' '.join(api._goals.goal_acceptance_criteria.__doc__.split()))
        return {'next_steps': [{'kind': 'human_approval', 'assignment': 'root', 'action': 'Review the captured goal design with the user, then approve these exact contents.', 'proposal': request, 'proposal_hash': digest(request), 'submission': {'operation': 'capture', 'request': request, 'proposal_hash': digest(request), 'approved_by': '<user>'}}]}
    if operation == 'capture':
        payload = {**payload, 'request': api._goals.normalize_deferred_goal_create(payload.get('request'))}
        capture_errors = api.validate_goal_create(payload.get('request'), allow_deferred=True)
        if capture_errors:
            raise ValueError('; '.join(capture_errors))
        if not api._goals.goal_acceptance_criteria(payload['request']['body']):
            raise ValueError('Goal design has no required acceptance criteria. '
                             + ' '.join(api._goals.goal_acceptance_criteria.__doc__.split()))
        if not (runtime or {}).get('root_id'):
            raise ValueError('Goal design approval must be coordinated by root')
        if not explicit_approval(payload.get('approved_by')) or payload.get('proposal_hash') != digest(payload['request']):
            raise ValueError('Explicit approval of this exact goal design is required; parent relationships do not confer capture authority')
        target_release = payload['request'].get('target_release')
        release_policy = policy_section(project, 'git_review_release')['configuration'].get('release_planning')
        if target_release is not None and (not isinstance(release_policy, dict) or not release_policy.get('enabled')):
            raise ValueError('target_release requires release planning enabled by reviewed policy')
        reviewed_graph = policy_section(project, 'workflow_adherence')['configuration']['phase_dag']
        api._static_workflow.definition(reviewed_graph, api._graph_compiler)
        release_adapter = (api.GitHubReleasePlanAdapter(repo, engine.repository)
                           if isinstance(release_policy, dict) and release_policy.get('enabled') else None)
        receipt = (release_adapter.capture_receipt(engine.repository, payload['proposal_hash'])
                   if release_adapter is not None and hasattr(release_adapter, 'capture_receipt') else None)
        publication_error = None
        if receipt is not None:
            if (receipt.get('repository') != engine.repository
                    or receipt.get('proposal_hash') != payload['proposal_hash']
                    or receipt.get('request_digest') != digest(payload['request'])):
                raise ValueError('capture receipt conflicts with repository or approved proposal')
            created = copy.deepcopy(receipt['goal'])
        marker = '<!-- zzzops-capture:' + payload['proposal_hash'] + ' -->'
        try:
            with engine.locked():
                created = api._capture_v2.capture(engine, payload['request'], payload['proposal_hash'])
        except (OSError, RuntimeError, TimeoutError, ValueError) as exc:
            recovered = (engine.adapter.find_capture_goal(marker)
                         if hasattr(engine.adapter, 'find_capture_goal') else None)
            if recovered is None:
                raise
            created = recovered
            publication_error = str(exc)
        if receipt is None:
            if release_adapter is not None:
                release_adapter.append_artifact(engine.repository, {
                    'kind': 'zzzops-capture-receipt', 'request_id': payload['proposal_hash'],
                    'repository': engine.repository, 'proposal_hash': payload['proposal_hash'],
                    'request_digest': digest(payload['request']), 'goal': copy.deepcopy(created)})
        engine.invalidate()
        created_number = created['number']
        if publication_error is not None:
            return {'next_steps': [{'kind': 'blocker', 'goal': created_number,
                    'reason': publication_error,
                    'action': 'Retry this exact approved capture to complete schema-2 publication.'}]}
        capture = None
        if isinstance(release_policy, dict) and release_policy.get('enabled'):
            effective_target = target_release or release_policy['next_release']
            try:
                adapter = release_adapter
                plan = adapter.read(engine.repository)
                if plan is None:
                    raise ValueError('release plan is missing')
                if target_release is not None:
                    assignment = api._releases.persist_batch_assignments(adapter, engine.repository,
                        [{'goal': created_number, 'release': target_release}], expected_revision=plan['revision'],
                        request_id='capture-' + payload['proposal_hash'])
                    applied = assignment['items'][0]['status'] == 'applied'
                    capture = api._releases.capture_assignment_result(goal=created,
                        assignment=assignment if applied else None, target_release=target_release,
                        error=None if applied else 'provider outcome unknown', request_id=payload['proposal_hash'])
                else:
                    enrolled = api._releases.enroll_release_member(plan, created_number,
                        expected_revision=plan['revision'])
                    api._releases.persist_plan(adapter, engine.repository, enrolled,
                        expected_revision=plan['revision'], request_id='capture-cohort-' + payload['proposal_hash'])
            except (OSError, RuntimeError, TimeoutError, ValueError) as exc:
                capture = api._releases.capture_assignment_result(goal=created, assignment=None,
                    target_release=effective_target, error=str(exc), request_id=payload['proposal_hash'])
        result = {'next_steps': api._migration_batch.next_steps(engine, created_number)}
        if capture is not None: result['capture'] = capture
        return result
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
        stopped_attempt = None
        if operation == 'recover':
            historical = api.parse_managed_goal(engine.adapter.get_issue(number)['body'], number)
            if historical.get('schema_version') == 2:
                snapshot = engine.node_snapshot(number)
                node_key = api._phase_evidence.task_key(payload.get('node'))
                prior = snapshot['projection']['leases'].get(node_key)
                if (prior and prior.get('token') == payload.get('lease')
                        and 'git_commit' in prior.get('acquisition', {})
                        and 'files' not in prior['acquisition']):
                    stopped_attempt = prior
        result = engine.mutate(number, payload)
        terminal_goal = number if operation == 'integrate' else None
        if operation == 'stack_advance':
            for step in result.get('next_steps', []):
                reference = step.get('observation')
                if not isinstance(reference, dict):
                    continue
                observation = engine.read_artifact(number, reference)
                if (isinstance(observation, dict) and observation.get('type') == 'stack_observation'
                        and observation.get('content', {}).get('state') == 'merged'):
                    terminal_goal = observation['content']['goal']
                    break
        if terminal_goal is not None:
            try:
                terminal = engine.node_terminal_merge_reconcile(terminal_goal)
            except (ValueError, KeyError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
                terminal = {'status': 'pending', 'goal': terminal_goal, 'reason': str(exc),
                            'action': 'Retry this exact integration request after reconciling the reported terminal authority; the provider merge must only be observed.'}
            result.setdefault('next_steps', []).append({'kind': 'terminal_reconciliation', **terminal})
            if terminal['status'] == 'closed':
                for step in result['next_steps']:
                    if step.get('kind') == 'checkpoint' and step.get('goal') == terminal_goal:
                        step['provider_state'] = 'closed'
                        step['action'] = 'Exact provider merge observed and goal terminal evidence closed.'
        if operation in {'restack_continue', 'restack_abort'}:
            authorization = next((step for step in result.get('next_steps', [])
                                  if step.get('kind') == operation + '_authorized'), None)
            if (authorization is None or authorization.get('lease') != payload.get('lease')
                    or authorization.get('actor') != payload.get('actor')
                    or authorization.get('plan_hash') != payload.get('plan_hash')
                    or authorization.get('plan_hash') != digest(authorization.get('plan'))):
                raise ValueError('Provider-confirmed restack authorization changed')
            current = engine.node_snapshot(number)
            key = api._phase_evidence.task_key(payload['node'])
            authority = current['workspaces'].get(key, {})
            if not authority.get('git_workspace') or 'entry' not in authority:
                raise ValueError('Provider-confirmed restack authority changed')
            local = managed_worktrees.inspect_attempt_worktree(repo, goal=number,
                node=payload['node']['node'], attempt=authorization['attempt'])
            if local['status'] == 'missing':
                raise ValueError('Provider-confirmed restack managed worktree is missing')
            path = Path(local['path']); plan = authorization['plan']
            if operation == 'restack_continue':
                lease = next((item for item in current['payload']['operational']['leases']
                              if item.get('token') == authorization['lease']), None)
                intent = lease.get('restack', {}).get('candidate_intent') if lease else None
                if intent is None:
                    intent = git_phase_state.prepare_attempt_restack_continue(
                        path, plan, authority['entry']['owned'])
                    intent_request = {'operation': 'restack_intent',
                        'request_id': payload['request_id'] + '-intent',
                        'node': payload['node'], 'lease': payload['lease'],
                        'actor': payload['actor'], 'plan_hash': payload['plan_hash'],
                        'authorized_request': payload['request_id'], **intent}
                    confirmation = engine.mutate(number, intent_request)
                    confirmed = next((step for step in confirmation.get('next_steps', [])
                                      if step.get('kind') == 'restack_intent_confirmed'), None)
                    if (confirmed is None or any(confirmed.get(name) != value
                            for name, value in intent.items())):
                        raise ValueError('Provider did not confirm the exact restack candidate intent')
                outcome = git_phase_state.complete_attempt_restack_continue(
                    path, plan, authority['entry']['owned'], intent)
                head = outcome['result_commit']
                status = 'continue'
            else:
                outcome = git_phase_state.abort_attempt_restack(
                    path, plan, authority['entry']['owned'])
                head = outcome['head_commit']; status = 'abort'
            finalize = {'operation': 'restack_finalize',
                'request_id': payload['request_id'] + '-finalize',
                'node': payload['node'], 'lease': payload['lease'],
                'actor': payload['actor'], 'plan_hash': payload['plan_hash'],
                'authorized_request': payload['request_id'],
                'status': status, 'head_commit': head}
            result = engine.mutate(number, finalize)
        if operation == 'integrate':
            cleanup = None
            try:
                current = engine.node_snapshot(number)
                if engine.node_native_delivery(current):
                    cleanup = engine.node_cleanup_delivered_worktrees(current)
                else:
                    cleanup = engine.node_cleanup_delivered_readonly_worktrees(current)
            except (ValueError, OSError, subprocess.SubprocessError) as exc:
                cleanup = {'status': 'pending', 'reason': str(exc)}
            if cleanup is not None:
                for step in result.get('next_steps', []):
                    if step.get('kind') == 'checkpoint' and step.get('goal') == number:
                        step['local_cleanup'] = cleanup
                        if cleanup['status'] == 'pending':
                            step['local_cleanup_action'] = ('Replay this exact integrate request after fixing the '
                                'local cleanup obstacle; the provider merge and goal receipt remain committed.')
        if operation == 'start':
            for step in result.get('next_steps', []):
                lease = step.get('lease') if step.get('kind') == 'perform' else None
                acquisition = lease.get('acquisition', {}) if isinstance(lease, dict) else {}
                if (lease and lease.get('node') == payload.get('node')
                        and lease.get('owner') == (runtime or {}).get('root_id')
                        and ('git_commit' in acquisition or 'read_commit' in acquisition)
                        and 'files' not in acquisition):
                    current = engine.node_snapshot(number)
                    active = [item for item in current['payload']['operational']['leases']
                              if item.get('token') == lease['token']]
                    if (len(active) != 1 or active[0].get('node') != lease['node']
                            or active[0].get('attempt') != lease['attempt']
                            or active[0].get('owner') != lease['owner']
                            or active[0].get('fingerprint') != lease['fingerprint']
                            or active[0].get('acquisition') != acquisition
                            or active[0].get('expires_at', 0) <= time.time()):
                        raise ValueError('Original Git workspace lease is no longer active; recover through the current workflow')
                    durable_lease = active[0]
                    node = lease['node']
                    restack = durable_lease.get('restack')
                    if restack is not None:
                        local = managed_worktrees.inspect_attempt_worktree(
                            repo, goal=number, node=node['node'], attempt=lease['attempt'])
                        workspace = (managed_worktrees.prepare_worktree(
                            repo, goal=number, node=node['node'], attempt=lease['attempt'],
                            base_commit=acquisition['git_commit'], resume_dirty=True)
                            if local['status'] == 'missing' else
                            {**local, 'outcome': ('existing_dirty'
                                                 if local['status'] == 'dirty'
                                                 else 'existing')})
                        key = api._phase_evidence.task_key(node)
                        authority = current['workspaces'].get(key, {})
                        if (not authority.get('git_workspace') or 'entry' not in authority
                                or restack.get('plan_hash') != digest(restack.get('plan'))):
                            raise ValueError('Persisted restack lease differs from current reviewed workspace authority')
                        applied = git_phase_state.apply_attempt_restack(
                            Path(workspace['path']), restack['plan'],
                            authority['entry']['owned'])
                        actor = lease.get('worker') or '<actual worker>'
                        common = {'node': node, 'lease': lease['token'], 'actor': actor,
                                  'plan_hash': restack['plan_hash'],
                                  'request_id': '<unique request>'}
                        step['restack'] = {**restack, 'status': applied['status'],
                            'conflicts': applied.get('conflicts', []),
                            'continue': {'operation': 'restack_continue', **common},
                            'abort': {'operation': 'restack_abort', **common}}
                    else:
                        workspace = managed_worktrees.prepare_worktree(
                            repo, goal=number, node=node['node'], attempt=lease['attempt'],
                            base_commit=acquisition.get('git_commit', acquisition.get('read_commit')),
                            resume_dirty='git_commit' in acquisition)
                    step['managed_worktree'] = workspace
                    step['action'] = ('Resolve only the exact reported owned conflicts, then use the returned continue or abort contract.'
                        if step.get('restack', {}).get('status') == 'conflict' else
                        'Resume this leased dirty draft in the managed worktree at '
                        + workspace['path'] + '; verify and commit only authorized outputs before submission.'
                        if workspace['outcome'] == 'existing_dirty' else
                        'Run this leased task in the managed worktree at '
                        + workspace['path'] + '; preserve the exact attempt branch.')
        if operation == 'compact_candidate':
            for step in result.get('next_steps', []):
                if step.get('kind') != 'candidate_compacted' or step.get('goal') != number:
                    continue
                attempt = step['authorization']['hash'][7:39]
                local = managed_worktrees.inspect_attempt_worktree(
                    repo, goal=number, node='candidate', attempt=attempt)
                step['managed_candidate'] = local
                if local['status'] != 'clean' or local['head'] != step['head_oid']:
                    step['action'] = ('The exact compacted head is not available in this machine\'s '
                                      'managed worktree; restore it from retained attempts before publication.')
        if stopped_attempt is not None:
            local = managed_worktrees.inspect_attempt_worktree(
                repo, goal=number, node=stopped_attempt['node']['node'],
                attempt=stopped_attempt['attempt'])
            for step in result.get('next_steps', []):
                if step.get('kind') == 'checkpoint' and step.get('goal') == number:
                    step['preserved_attempt'] = local
                    step['action'] = ('The stopped attempt worktree remains local. '
                                      'Inspect its exact branch and files before reuse; dirty files '
                                      'have no remote durability guarantee.')
        return result
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
    operation = (payload or {}).get('operation', 'checkpoint') if isinstance(payload, (dict, type(None))) else None
    # Bound observation/renewal work without charging long local verification or
    # execution commands against a provider-only deadline.
    budget = getattr(api, 'renewal_budget', None)
    if budget is None and operation == 'renew':
        configured = getattr(api, 'workflow_timeout_seconds', None)
        budget = RenewalBudget(configured if configured is not None
                               else float(os.environ.get('ZZZOPS_RENEWAL_TIMEOUT_SECONDS', '30')),
                               float(os.environ.get('ZZZOPS_RENEWAL_CLEANUP_SECONDS', '10')))
    elif budget is None and operation in {'checkpoint', 'read'}:
        configured = getattr(api, 'workflow_timeout_seconds', None)
        budget = RenewalBudget(
            configured if configured is not None
            else float(os.environ.get('ZZZOPS_WORKFLOW_TIMEOUT_SECONDS', '90'))
        )
    previous = getattr(api, 'operation_budget', None)
    guard_mark = len(getattr(api, '_guarded_mutations', []))
    api.operation_budget = budget
    try:
        with (api.provider_operation_budget(budget) if hasattr(api, 'provider_operation_budget') else nullcontext()), \
             (api.provider_read_invocation() if hasattr(api, 'provider_read_invocation') else nullcontext()):
            return _public_response(api, repo, intent, source, runtime, payload, number,
                                    skip_installation_validation=skip_installation_validation,
                                    payload_supplied=payload_supplied)
    finally:
        guards = getattr(api, '_guarded_mutations', [])
        for record in reversed(guards[guard_mark:]):
            for method_name, original in record['restore'].items():
                setattr(record['adapter'], method_name, original)
        api._guarded_mutations = guards[:guard_mark]
        if previous is None: del api.operation_budget
        else: api.operation_budget = previous


def _public_response(api, repo, intent, source, runtime, payload, number, *, skip_installation_validation=False, payload_supplied=False):
    snapshot = {}
    options = {'skip_installation_validation': True} if skip_installation_validation else {}
    if payload_supplied:
        options['payload_supplied'] = True
    transaction = None
    if isinstance(payload, dict):
        request_id = payload.get('request_id')
        if not isinstance(request_id, str):
            encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
            request_id = 'workflow-' + hashlib.sha256(encoded).hexdigest()[:48]
        transaction = api._WORKING_INPUT_TRANSACTION.set({
            'request_id': request_id, 'owner': (runtime or {}).get('root_id', 'root')})
    try:
        result = _public_run(
            api, repo, intent, source, runtime, payload, number,
            policy_snapshot=snapshot, **options,
        )
    finally:
        if transaction is not None:
            api._WORKING_INPUT_TRANSACTION.reset(transaction)
    purposes = {
        '$add-zzzops-goal': 'capture', '$execute-zzzops': 'execute',
        '$migrate-to-zzzops': 'migration', '$review-zzzops-policy': 'policy-review',
    }
    purpose = purposes.get(source)
    if purpose is not None:
        repository = ((snapshot.get('project') or {}).get('repository') or {}).get('identity', 'local')
        owner = (runtime or {}).get('root_id', 'root')
        carried_draft = (runtime or {}).get('working_input_draft')
        logical_session = os.environ.get('CODEX_THREAD_ID')
        if isinstance(carried_draft, str):
            draft_identity = carried_draft
        elif number is None and isinstance(logical_session, str) and logical_session:
            draft_identity = api._working_inputs.WorkingInputStore(
                repo, repository=repository, owner=owner,
            ).draft_session(purpose, logical_session)
        else:
            draft_identity = (api._working_inputs.WorkingInputStore(
                repo, repository=repository, owner=owner,
            ).draft_session(purpose, owner) if number is None else str(uuid.uuid4()))
        subject = f'goal:{number}' if number is not None else f'draft:{draft_identity}'
        result['working_input'] = api._working_inputs.WorkingInputStore(
            repo, repository=repository, owner=owner,
        ).guidance(subject, purpose)
        if number is None:
            result['working_input']['draft_id'] = draft_identity
    if payload is None and number is not None and source == '$execute-zzzops':
        for step in result.get('next_steps', []):
            if isinstance(step, dict):
                step.setdefault('invalidated_ancestor_gates', [])
    if any('node' in step and 'policy' in step for step in result.get('next_steps', [])):
        return result
    if api._policy_context.needs_context(result):
        return api._policy_context.attach(
            result, repo, snapshot['project'], source=source,
        )
    return result
