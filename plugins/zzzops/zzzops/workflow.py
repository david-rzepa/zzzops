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
import base64
import zlib
import re
from contextlib import contextmanager, nullcontext
from pathlib import Path


# Public submissions are intentionally enumerated here, before any context or
# provider work.  A misspelled operation must be repaired as such rather than
# being routed through an unrelated installation, policy, lease, or portfolio
# gate.
PUBLIC_OPERATIONS = frozenset({
    'adopt', 'approve', 'artifact', 'assess', 'batch', 'bind', 'block',
    'capture', 'capture_propose', 'complete', 'feedback_prepare',
    'feedback_submit', 'heartbeat', 'installation_record', 'integrate',
    'policy_approve', 'policy_propose', 'read', 'record_result',
    'record_review', 'recover', 'recover_legacy', 'release', 'renew',
    'reopen', 'revise', 'route_choice', 'specify', 'start', 'verify',
    'withdraw',
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
        for _lease in state(goal)['leases'].values()
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

    def read(self, number):
        if number not in self._read_cache:
            self.portfolio(allow_invalid=True)
            records = {item.get('key'): item for item in self._portfolio_cache.get('goals', []) if isinstance(item, dict)}
            goal = records.get(number)
            if not isinstance(goal, dict):
                raise ValueError(f'Goal #{number} is absent from the current portfolio gateway')
            goal = {
                **goal,
                "human_spec": goal.get("human_spec") or f"Archived goal #{number}; body unavailable.",
                "acceptance_criteria": goal.get("acceptance_criteria", []),
                "phase_evidence": goal.get("phase_evidence") or self.api.empty_phase_evidence(),
            }
            # Workflow context is allowed to consume only the portfolio gateway.
            # Mutations still use their provider adapter at the write boundary.
            self._read_cache[number] = ({'number': number}, copy.deepcopy(goal))
        return copy.deepcopy(self._read_cache[number])

    def artifact(self, number, content):
        identity = digest(content)
        marker = '<!-- zzzops-artifact ' + identity + ' -->'
        raw = json.dumps({'hash': identity, 'content': content}, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        if len(raw.encode('utf-8')) > 1_000_000:
            raise ValueError('Phase artifacts must be bounded to one megabyte')
        encoded = base64.b64encode(zlib.compress(raw.encode('utf-8'))).decode('ascii')
        body = marker + '\n<details><summary>Immutable phase artifact</summary>\n\n```text\n' + encoded + '\n```\n</details>'
        if len(body) > 65000:
            raise ValueError('Artifact is too large for one provider comment; use a published Git content reference')
        existing = [c for c in self.adapter.get_issue_comments(number) if c.get('body', '').startswith(marker)]
        if existing and any(c['body'] != body for c in existing):
            raise ValueError('Stored artifact identity conflicts with its contents')
        if not existing:
            stored = self.adapter.create_issue_comment(number, body)
            if stored.get('body') != body:
                raise ValueError('Provider did not confirm the exact artifact')
        return {'reference': 'urn:' + identity, 'hash': identity}

    def read_artifact(self, number, artifact):
        # Content-addressed successful reads may be reused within this invocation.
        # Live records/review bindings are still checked independently each time.
        key = (number, digest(artifact))
        cache = getattr(self, '_immutable_artifacts', {})
        if key not in cache:
            cache[key] = self._read_artifact(number, artifact)
            self._immutable_artifacts = cache
        return copy.deepcopy(cache[key])

    def _read_artifact(self, number, artifact):
        artifact = self.api._phase_evidence._artifact(artifact, 'artifact', required=True)
        reference, expected = artifact['reference'], artifact['hash']
        if reference.startswith('git:'):
            content = subprocess.run(['git', 'show', reference[4:]], cwd=self.repo, capture_output=True, check=True).stdout
            if 'sha256:' + hashlib.sha256(content).hexdigest() != expected:
                raise ValueError('Git artifact content does not match its declared hash')
            return content.decode('utf-8')
        if reference != 'urn:' + expected:
            raise ValueError('Artifact reference must identify its exact stored content hash')
        marker = '<!-- zzzops-artifact ' + expected + ' -->'
        for comment in self.adapter.get_issue_comments(number):
            body = comment.get('body', '')
            if body.startswith(marker):
                match = re.search(r'```text\n([A-Za-z0-9+/=]+)\n```', body)
                if not match:
                    raise ValueError('Malformed stored artifact')
                decoder = zlib.decompressobj()
                try:
                    raw = decoder.decompress(base64.b64decode(match[1], validate=True), 1_000_001)
                except (ValueError, zlib.error) as exc:
                    raise ValueError('Malformed stored artifact encoding') from exc
                if not decoder.eof or decoder.unused_data or len(raw) > 1_000_000:
                    raise ValueError('Stored artifact exceeds its bounded size')
                value = json.loads(raw)
                if value.get('hash') != expected or digest(value.get('content')) != expected:
                    raise ValueError('Stored artifact content changed')
                return value['content']
        raise ValueError('Persist the phase artifact through operation=artifact before submitting its reference')

    def portfolio(self, *, allow_invalid=False):
        if self._portfolio_cache is None:
            self._portfolio_cache = self.api.portfolio_snapshot(self.repo)
        portfolio = self._portfolio_cache
        if not portfolio.get('complete'):
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
        result = self.api.apply_goal_transition(self.adapter, self.repository, goal['key'], {
            'schema_version': self.api.GOAL_TRANSITION_SCHEMA_VERSION,
            'expected_revision': goal['revision'], 'expected_digest': goal['digest'], 'goal': desired,
            **({'human_spec': human_spec} if human_spec is not None else {}),
        })
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
            if assessment:
                envelope['capabilities']['snapshot'] = {'assessment': assessment}
            if phase == 'publish' and not goal.get('parent'):
                children = [self.read(g['key'])[1] for g in self.portfolio() if g.get('parent') == goal['key']]
                envelope['dependencies'] += [
                    {'goal': child['key'], 'artifact': {'reference': 'urn:sha256:' + digest({'status': child['status'], 'results': completion_identity(child), 'spec': self.api.goal_spec_digest(child, title=child['title'], human_spec=child['human_spec'])})[7:],
                     'hash': digest({'status': child['status'], 'results': completion_identity(child), 'spec': self.api.goal_spec_digest(child, title=child['title'], human_spec=child['human_spec'])})}}
                    for child in sorted(children, key=lambda g: g['key'])]
            if phase == 'publish' and (goal.get('implementation') or {}).get('branch'):
                envelope['provider']['snapshot']['publication'] = self.publication_identity(goal)
            proof = state(goal)['artifacts'].get(phase)
            withdrawn = any(item['phase'] == phase for item in evidence['withdrawals'])
            if not withdrawn and proof and proof.get('workspace') and proof['workspace'] != self.workspace_digest() and not (versions and self.historical_proof(goal, phase, proof)):
                envelope['repository']['snapshot']['output_drift'] = self.workspace_digest()
        return live

    def historical_proof(self, goal, phase, proof):
        if phase not in {'test_design', 'implement'}:
            return False
        lease = state(goal)['leases'].get(phase + ':execute')
        if lease and self.acquisition(goal, phase, lease):
            return True
        return proof.get('workspace') in getattr(self, '_connected_workspaces', set())

    def reviewed_scope(self, goal):
        """Only substantive reviewed plans grant the small, finite output scope."""
        if not goal.get('parent'):
            return None
        scopes = []
        for current in (self.read(goal['parent'])[1], goal):
            evidence = current.get('phase_evidence') or self.api.empty_phase_evidence()
            record, review = evidence['records'].get('plan'), evidence['reviews'].get('plan')
            if not record or not review or review['decision'] != 'approved' or review['reviewer'] == record['actor']:
                return None
            if any(item['phase'] == 'plan' for item in evidence['withdrawals']):
                return None
            if review['record_hash'] != digest(record) or review['input_hash'] != record['input_hash']:
                return None
            graph, _ = self.api._workflow_phase_configuration(self.project, current)
            live = self.api.workflow_live_inputs(self.repo, self.project, current, 'execute', graph)['plan']
            if any(record['input_envelope'][field] != live[field] for field in ('goal_spec', 'policy', 'phase_dag')):
                return None
            content = self.read_artifact(current['key'], record['output'])
            scope = content.get('output_scope') if isinstance(content, dict) else None
            if current['key'] == goal['parent'] and isinstance(content, dict) and 'output_scopes' in content:
                entries = content['output_scopes']
                if scope is not None or not isinstance(entries, list) or any(not isinstance(x, dict) for x in entries):
                    return None
                identifiers = [x.get('child') for x in entries]
                if any(not isinstance(x, int) or isinstance(x, bool) for x in identifiers) or len(identifiers) != len(set(identifiers)):
                    return None
                scope = next((x for x in entries if x.get('child') == goal['key']), None)
            if not isinstance(scope, dict) or set(scope) != {'parent', 'child', 'test_design', 'implement'}:
                return None
            if scope['parent'] != goal['parent'] or scope['child'] != goal['key']:
                return None
            paths = scope['test_design'] + scope['implement'] if all(isinstance(scope[p], list) for p in ('test_design', 'implement')) else []
            if not all(isinstance(scope[p], list) for p in ('test_design', 'implement')) or any(not isinstance(p, str) for p in paths) or len(paths) != len(set(paths)):
                raise ValueError('Reviewed output scope must contain distinct finite paths')
            for path in paths:
                if not isinstance(path, str) or Path(path).is_absolute() or Path(path).as_posix() != path or '..' in Path(path).parts or path.startswith('.zzzops/') or path == 'AGENTS.md':
                    raise ValueError('Output scope paths must be canonical repository files')
            self.file_hashes(paths)  # Resolves symlinks and rejects worktree escapes.
            scopes.append(scope)
        if scopes[0] != scopes[1]:
            return None
        return scopes[0]

    def git_files(self, commit):
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
        files = self.file_hashes(path for path in paths if path and not path.startswith('.zzzops/'))
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
        reference = self.artifact(goal['key'], previous)
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
            raise ValueError('Policy or plan input changed; current reviewed output scope is unavailable')
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

    def context(self, goal):
        self._input_requester = goal['key']
        graph, nodes = self.api._workflow_phase_configuration(self.project, goal)
        related = {}
        if goal.get('parent'):
            _, parent = self.read(goal['parent'])
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
        # Phase contracts must be derived from the same exact body that the
        # locked mutation path validates.
        projected = self.read(number)[1]
        adapter = getattr(self, 'adapter', None)
        exact_reader = getattr(self.api, 'github_goal_record', None)
        if adapter is not None and callable(exact_reader):
            goal = exact_reader(adapter.get_issue(number))
        else:
            # Isolated contract tests may deliberately supply only the
            # portfolio gateway. Production Workflow instances always have an
            # exact provider adapter, so this never broadens provider reads.
            goal = copy.deepcopy(projected)
        if isinstance(projected.get('pull_request'), dict):
            goal['pull_request'] = projected['pull_request']
        if goal['status'] in {'done', 'cancelled'}:
            return []
        if goal.get('needs_human'):
            return [{'kind': 'blocker', 'assignment': 'root', 'goal': number,
                     'action': 'Resolve human blockers on root. Remove only resolved entries from changes.blockers, retain unresolved entries, and describe the resolution in changes.next_action.',
                     'categories': goal.get('blocker_categories', []),
                     'submission': {'operation': 'revise', 'expected_digest': goal['digest'], 'request_id': 'new-unique-id',
                                    'changes': {'blockers': goal.get('blockers', []), 'next_action': '<observed blocker resolution>'}}}]
        if goal.get('claim'):
            return [{'kind': 'recover_legacy', 'assignment': 'root', 'goal': number, 'action': 'Confirm the legacy worker stopped before replacing its claim with phase leases.', 'submission': {'operation': 'recover_legacy', 'claim_hash': digest(goal['claim']), 'worker_status': 'stopped', 'evidence': '<observed terminal state>', 'request_id': 'new-unique-id'}}]
        graph, nodes, live, related = self.context(goal)
        result = self.api.workflow_step_plan(goal, graph, live, nodes,
                    self.api._workflow_section(self.project, 'model_routing')['configuration'], self.runtime,
                    related_goals=related)
        steps = result['next_steps']
        for step in steps:
            phase = step.get('phase')
            step['goal'] = number
            if not phase:
                step.update(action='Discover the complete harness tool catalog, including deferred tools, and available model/effort pairs. Resubmit --runtime with root_pair, available_pairs, root_id and delegation evidence.',
                            runtime_contract={'root_pair': {'model': 'identifier', 'effort': 'identifier'}, 'available_pairs': [], 'root_id': 'thread-id', 'delegation': {'available': True, 'tool': 'actual harness tool name', 'discovery_complete': True}})
                continue
            kind = step['kind']
            migration = live.get(phase, {}).get('provider', {}).get('snapshot', {}).get('migration', {})
            if migration.get('decision', {}).get('action') == 'block':
                step.clear()
                step.update(input_hash=digest(live[phase]), input_envelope=live[phase], kind='blocker', assignment='root', goal=number, phase=phase,
                            action='Investigate affected contract evidence first. Prepare or correct the local goal/spec-bound assessment from available facts, then request a fresh checkpoint. Only if the evidence remains unresolved, submit the provided blocker contract and continue independent goals. Local evidence preparation is not a backend submission or reset authority.',
                            evidence=migration, path=f'.zzzops/migration/{number}.json',
                            preparation=self.migration_preparation(goal, live[phase], migration),
                            command=['--intent', 'execute', '--goal', str(number), '--runtime', '<runtime.json>', '--input', '<submission.json>'],
                            submission={'operation': 'block', 'phase': phase, 'category': 'technical-unknown',
                                        'reason': f'Unresolved migration contract evidence for goal {number}, phase {phase}, .zzzops/migration/{number}.json: {migration["decision"]["reason"]}. Investigate and reassess before affected work.',
                                        'request_id': 'new-unique-id'})
                continue
            if phase in {'test_design', 'implement'} and kind in {'assess', 'execute'} and self.reviewed_scope(goal) is None:
                repairs = []
                for owner in ([self.read(goal['parent'])[1]] if goal.get('parent') else []) + [goal]:
                    record = (owner.get('phase_evidence') or {}).get('records', {}).get('plan')
                    repair = {'goal': owner['key'], 'phase': 'plan',
                              'field': 'output_scope' if owner.get('parent') else 'output_scopes',
                              'command': ['--intent', 'execute', '--goal', str(owner['key'])]}
                    review = (owner.get('phase_evidence') or {}).get('reviews', {}).get('plan')
                    if record and (not review or review.get('record_hash') != digest(record)):
                        repair['action'] = 'Request this goal checkpoint and acquire its exact current independent plan review before editing.'
                        repair['required_kind'] = 'review'
                    elif record:
                        repair['submission'] = {'operation': 'withdraw', 'phase': 'plan',
                                                'record_hash': digest(record), 'request_id': 'new-unique-id',
                                                'reason': 'Correct finite output scope and independently review before file execution.'}
                    repairs.append(repair)
                step.update(kind='repair', action='Correct and independently review the parent plan output_scopes entry and matching child plan output_scope before acquiring this phase. If content already matches, complete its current independent review instead of replacing content.',
                            scope_repair={'goal': number, 'parent': goal.get('parent'), 'phase': phase,
                                          'field': 'output_scope', 'required_phase': 'plan', 'repairs': repairs})
                continue
            if kind not in {'execute', 'review', 'human_approval'}:
                if kind == 'capability_choice':
                    human_only = 'downgrade_to_root' in step.get('choices', [])
                    step.update(
                        action=('Ask the user whether to use the requested stronger root pair or approve this human-interaction phase at the observed root pair.' if human_only else 'Ask the user whether to use the requested stronger pair or delegate this phase at the observed root pair.'),
                        instruction=self.api.workflow_instruction('routing-evidence'),
                        submission={'operation': 'route_choice', 'phase': phase, 'choice': '<one returned choice>', 'approved_by': '<user>', 'request_id': 'new-unique-id'},
                    )
                    continue
                step.update(action='Resolve this routing prerequisite on root. If it needs user authority, persist a blocker and continue other goals; do not silently substitute root work.',
                            instruction=self.api.workflow_instruction('routing-evidence'),
                            submission={'operation': 'block', 'category': 'access-approval', 'reason': step.get('reason', 'Routing prerequisite unavailable'), 'request_id': 'new-unique-id'})
                continue
            if phase == 'test_design' and not goal['acceptance_criteria']:
                step.clear()
                step.update(kind='specify', assignment='root', goal=number, action='Capture explicit acceptance bullets for every required behavior before designing tests.', submission={'operation': 'specify', 'expected_digest': goal['digest'], 'human_spec': '<complete updated human goal specification with acceptance bullets>', 'request_id': 'new-unique-id'})
                continue
            if phase == 'publish':
                gate = self.publication_gate(goal)
                if gate:
                    step.clear(); step.update(gate, goal=number, phase=phase)
                    continue
            if step.get('assignment') == 'delegate':
                capability = (self.runtime or {}).get('delegation', {})
                if not capability.get('available') or not capability.get('discovery_complete') or not capability.get('tool'):
                    step.update(kind='capability_discovery', assignment='root', action='Discover deferred delegation tools and record the actual launch tool in runtime.delegation. If unavailable, record a blocker; do not silently run this phase on root.')
                    continue
            phase_input = live[phase]
            assessment = state(goal)['assessments'].get(phase)
            if not assessment or assessment.get('goal_spec') != phase_input['goal_spec'] or assessment.get('policy') != phase_input['policy']:
                step.clear()
                step.update(kind='assess', assignment='root', goal=number, phase=phase,
                            action='Assess consequence, boundedness and engineering rigor; declare every repository file consumed by this phase. For affected persistent-state or API compatibility work, add migration_evidence.path to submission.files even if missing, then use the linked preparation resource returned by the next checkpoint. Determine applicability from the actual goal scope; do not infer it from project release status. Use an empty list only when no repository files are inputs.',
                            migration_evidence={'path': f'.zzzops/migration/{number}.json',
                                                'when': 'This phase changes or decides compatibility/replacement of persistent state or an API contract; root determines applicability from evidenced scope.'},
                            title=goal['title'], input_envelope=phase_input, input_hash=digest(phase_input),
                            goal_specification={'reference': goal['url'], 'hash': phase_input['goal_spec'], 'read': {'operation': 'read', 'phase': phase}},
                            command=['--intent', 'execute', '--goal', str(number), '--runtime', '<runtime.json>', '--input', '<submission.json>'],
                            submission={'operation': 'assess', 'phase': phase, 'input_hash': digest(phase_input), 'request_id': 'new-unique-id', 'files': [], 'dimensions': {'consequence': 'bounded', 'boundedness': 'atomic', 'engineering_rigor': 'structured'}})
                continue
            key = phase + ':' + kind
            lease = state(goal)['leases'].get(key)
            step['instruction'] = self.api.workflow_instruction(f'phase:{phase}:{"review" if kind == "human_approval" else kind}')
            step['input_envelope'] = phase_input
            step['input_hash'] = digest(phase_input)
            step['goal_specification'] = {'reference': goal['url'], 'hash': phase_input['goal_spec'], 'read': {'operation': 'read', 'phase': phase}}
            step['artifact_submission'] = {'operation': 'artifact', 'lease': '<current-token>', 'actor': '<bound-worker>', 'content': '<phase output or review content>'}
            records = (goal.get('phase_evidence') or {}).get('records', {})
            prior_review = (goal.get('phase_evidence') or {}).get('reviews', {}).get(phase)
            step['upstream_evidence'] = {entry['phase']: records[entry['phase']].get('output') for entry in phase_input['upstream_outputs'] if entry['phase'] in records}
            if kind == 'execute' and isinstance(prior_review, dict) and prior_review.get('decision') == 'changes_requested':
                step['correction'] = {
                    'prior_reviewer': prior_review.get('reviewer'),
                    'prior_findings': prior_review.get('outcomes'),
                    'prior_record_hash': prior_review.get('record_hash'),
                    'scope': 'Correct only the recorded findings and revised artifact unless the phase inputs materially change.',
                    'routing': 'Reuse the current assessment and routing choice while goal specification and policy digests remain unchanged.',
                    'reviewer': 'Prefer the original independent reviewer; use a replacement only for unavailability or explicit escalation.',
                }
            if kind != 'execute':
                step['review_target'] = {'record_hash': digest(records.get(phase)), 'output': records.get(phase, {}).get('output'), 'verification': records.get(phase, {}).get('verification') or (records.get(phase, {}).get('test_design') or {}).get('baseline_failure')}
                proof = state(goal)['artifacts'].get(phase, {})
                if proof.get('acquisition', {}).get('predecessor'):
                    step['review_target']['predecessor'] = proof['acquisition']['predecessor']
                    step['review_target']['correction_review'] = 'Inspect the composed change and rejected predecessor facts; approval applies only to this latest result.'
                if step['review_target']['output']:
                    step['review_target']['read'] = {'operation': 'read', 'artifact': step['review_target']['output']}
            step['submission'] = {'operation': 'record_result' if kind == 'execute' else 'record_review' if kind == 'review' else 'approve', 'phase': phase, 'request_id': 'new-unique-id', 'lease': 'token from start', 'actor': 'bound worker identity'}
            if kind == 'execute':
                step['submission']['files'] = list(phase_input['repository']['snapshot']['files'])
            step['result_contract'] = {
                'record': {'status': 'completed', 'input_envelope': phase_input, 'input_hash': digest(phase_input), 'output': {'reference': '<immutable content reference>', 'hash': '<sha256 digest>'}, 'verification': None, 'routing': {'reference': 'urn:sha256:' + digest(assessment)[7:], 'hash': digest(assessment)}, 'selection': step['selection'], 'actor': '<bound-worker>', 'not_required': None, 'test_design': None},
                'review': {'artifact': {'reference': '<immutable review reference>', 'hash': '<sha256 digest>'}, 'outcomes': {'acceptance': 'approved or changes_requested', 'entropy': {'outcome': 'no_findings, fixed or follow_up', 'evidence': '<concrete finding or inspected scope>', 'goals': []}}},
                'approval': {'actor': '<root-id>', 'approval_token': '<explicit user approval reference>'},
            }
            if phase == 'plan':
                step['output_contract'] = {
                    'output_scope': {'parent': goal.get('parent') or goal['key'],
                                     'child': goal['key'] if goal.get('parent') else '<implementation-child-id>',
                                     'test_design': ['<exact test output path>'], 'implement': ['<exact source output path>']},
                    'action': 'Parent plans declare finite output_scopes entries selected uniquely by child; each child declares its matching output_scope. Both test_design and implement arrays are required; [] permits no file changes. Independently review both plans before acquisition. Keep changing provenance out of substantive content.',
                }
            step['recovery_contract'] = {'operation': 'recover', 'phase': phase, 'lease': '<exact-token>', 'worker_status': 'stopped', 'evidence': '<observed terminal state>', 'request_id': 'new-unique-id'}
            if nodes[phase].get('not_required', 'never') != 'never':
                step['result_contract']['not_required'] = {'status': 'not_required', 'output': None, 'not_required': {'reason': '<evidence supporting this exception>', 'policy_rule': nodes[phase]['not_required']}}
            step['command'] = ['--intent', 'execute', '--goal', str(number), '--runtime', '<runtime.json>', '--input', '<submission.json>']
            if phase in {'test_design', 'implement', 'publish'}:
                step['verification'] = {'operation': 'verify', 'phase': phase, 'lease': '<current-token>', 'actor': '<bound-worker>', 'commands': [['<project-test-runner>', '<arguments>']], 'request_id': 'new-unique-id'}
                if lease and kind == 'execute' and not lease.get('acquisition') and self.reviewed_scope(goal):
                    step['verification']['input_envelope'] = '<exact original envelope from the acquired start; its digest must match the lease>'
                try:
                    implementation = goal.get('implementation') or {}
                    if implementation.get('pr'):
                        identity = self.publication_identity(goal)
                        step['base_commit'] = identity['base_oid']
                        step['work_head'] = identity['head_oid']
                        step['base_branch'] = identity['base_ref']
                    else:
                        step['base_branch'] = implementation.get('base') or implementation.get('target') or 'dev'
                        step['base_commit'] = subprocess.run(['git', 'rev-parse', '--verify', step['base_branch'] + '^{commit}'], cwd=self.repo, capture_output=True, text=True, check=True).stdout.strip()
                except subprocess.CalledProcessError:
                    step.clear()
                    step.update(kind='publication_setup', assignment='root', goal=number, phase=phase,
                                action='Fetch or record the declared implementation base before starting this phase; its exact commit is unavailable.')
                    continue
            step['start'] = {'operation': 'start', 'phase': phase, 'kind': kind, 'input_hash': step['input_hash'], 'policy_receipt': '<copy policy_receipt from policy.path>', 'request_id': 'new-unique-id'}
            step['assignment_group'] = nodes[phase].get('review', {}).get('assignment_group', 'review') if kind == 'review' else nodes[phase]['assignment_group']
            reusable = [w for w in state(goal)['workers'].values() if w.get('group') == step['assignment_group'] and w.get('selection') == step['selection'] and (kind != 'review' or w['id'] != (goal.get('phase_evidence') or {}).get('records', {}).get(phase, {}).get('actor'))]
            if reusable:
                step['resume_worker'] = reusable[-1]['id']
            if lease:
                step['lease'] = lease
                step['kind'] = 'recover' if lease['expires_at'] <= time.time() else 'await_worker'
                step['action'] = 'Check the bound worker. Reconcile completion or explicitly recover only after confirming it stopped; expiry is not permission to duplicate work.'
                if step['kind'] == 'await_worker':
                    step['recheck'] = {
                        'after_seconds': 30,
                        'command': ['--intent', 'execute', '--goal', str(number), '--runtime', '<runtime.json>'],
                        'action': 'Recheck this exact leased phase after the interval; do not start a replacement worker.',
                    }
                    receipts = state(goal).get('receipts', {})
                    step['monitor'] = {
                        'worker': lease.get('worker'),
                        'lease': lease.get('token'),
                        'expires_at': lease.get('expires_at'),
                        'last_durable_operation': next(reversed(receipts), None),
                        'instruction': 'skills/execute-zzzops/references/MONITOR.md',
                        'heartbeat': 'Use the bound worker liveness probe as the primary monitor: active means wait; stopped means inspect results before recovery; unknown means diagnose the real worker and backend lease.',
                        'recovery': step['recovery_contract'],
                    }
                    try:
                        step['monitor']['health'] = self.api._heartbeat.heartbeat_health(
                            repo=self.repo, root_id=lease['owner'], goal=number, phase=phase,
                            token=lease['token'],
                        )
                    except (OSError, ValueError):
                        step['monitor']['health'] = {
                            'classification': 'unknown',
                            'explanation': ['Local heartbeat health could not be read.'],
                            'next_action': 'Inspect the real process, harness worker status, latest result file, and backend lease before recovery.',
                        }
            else:
                step['action'] = 'Acquire this phase with the start request before doing work; bind the actual executor before submitting evidence.'
        if not steps and result['frontier']['blocked']:
            return [{'kind': 'dependency', 'assignment': 'root', 'goal': number, 'action': 'Complete the required ancestor phases.', 'blocked': result['frontier']['blocked']}]
        if not steps:
            if (goal.get('implementation') or {}).get('pr'):
                current = self.pull_request(goal)
                classification = self.classify_merge(goal, current)
                if classification['status'] != 'merged_verified':
                    if not current.get('merged'):
                        return [{'kind': 'integration', 'assignment': 'root', 'goal': number, 'action': 'Confirm human merge approval and satisfy the reviewed CI policy for this exact PR head, then integrate through the CLI.', 'head': current['head_oid'], 'submission': {'operation': 'integrate', 'expected_head': current['head_oid'], 'approved_by': '<user>', 'request_id': 'new-unique-id'}}]
                    return [{'kind': 'repair', 'assignment': 'root', 'goal': number, 'action': 'Reconcile incomplete or stale merge evidence before completing this goal.', 'reasons': classification['reasons']}]
            return [{'kind': 'complete', 'goal': number, 'assignment': 'root', 'action': 'All required phase evidence is current. Record completion, then continue with the next goal.', 'submission': {'operation': 'complete', 'request_id': 'new-unique-id'}}]
        return steps

    def publication_gate(self, goal):
        if not goal.get('parent'):
            children = [self.read(g['key'])[1] for g in self.portfolio() if g.get('parent') == goal['key']]
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
        # Read provider topology here, never accept a caller-supplied topology as
        # proof that another coordinator has not published in the meantime.
        result = subprocess.run(['gh', 'pr', 'list', '--state', 'open', '--limit', '1000', '--json', 'headRefName,baseRefName,headRefOid'], cwd=self.repo, capture_output=True, text=True, check=True)
        pulls = json.loads(result.stdout)
        managed_branches = {(g.get('implementation') or {}).get('branch') for g in self.portfolio()}
        managed_branches.add(implementation['branch'])
        pulls = [pull for pull in pulls if pull['headRefName'] in managed_branches]
        trunk = implementation.get('target') or 'dev'
        ordered, base = [], trunk
        remaining = list(pulls)
        while remaining:
            matches = [p for p in remaining if p['baseRefName'] == base]
            if len(matches) != 1:
                return {'kind': 'repair_stack', 'assignment': 'root', 'action': 'Rebase open PRs into one linear stack before publication.'}
            p = matches[0]; remaining.remove(p)
            ordered.append({'branch': p['headRefName'], 'base': p['baseRefName'], 'head': p['headRefOid']})
            base = p['headRefName']
        def rev(ref):
            return subprocess.run(['git', 'rev-parse', ref], cwd=self.repo, capture_output=True, text=True, check=True).stdout.strip()
        published = next((i for i, p in enumerate(ordered) if p['branch'] == implementation['branch']), None)
        if published is not None:
            ordered = ordered[:published]
        identity = self.publication_identity(goal)
        candidate = {'branch': implementation['branch'], 'base': identity['base_ref'], 'base_head': identity['base_oid'], 'head': identity['head_oid']}
        if implementation.get('pr') and (rev(implementation['branch']) != identity['head_oid'] or rev(implementation['base']) != identity['base_oid']):
            return {'kind': 'repair_stack', 'assignment': 'root', 'action': 'Synchronize the local candidate and base with the exact provider commits before verifying publication.', 'head': identity['head_oid'], 'base': identity['base_oid']}
        directive = self.api.linear_publication_next_step(ordered, candidate, trunk=trunk)
        if directive['action'] != 'publish_linear':
            return {'kind': 'repair_stack', 'assignment': 'root', **directive}
        return None

    def verify(self, number, payload):
        # Verification may be slow. Never hold the short backend storage lock
        # while tests run; revalidate ownership and inputs before recording it.
        _, goal = self.read(number)
        receipt = state(goal)['receipts'].get(payload['request_id'])
        if receipt:
            if receipt['hash'] != digest(payload):
                raise ValueError('request_id was already used with different inputs')
            proof = state(goal)['artifacts'].get(payload.get('phase'))
            if isinstance(proof, dict):
                reference = {'reference': 'urn:sha256:' + digest(proof)[7:], 'hash': digest(proof)}
                expected = not proof.get('passed') if payload.get('phase') == 'test_design' else proof.get('passed')
                return {'next_steps': [{'kind': 'record_result' if expected else 'correct', 'goal': number,
                    'phase': payload.get('phase'), 'verification': reference,
                    'action': 'Verification was already recorded; submit this exact proof.' if expected else
                              'Verification was already recorded and failed; correct the checks or implementation before a new verification request.'}]}
            return {'next_steps': [{'kind': 'checkpoint', 'goal': number, 'action': 'Verification was already recorded; re-read its evidence.'}]}
        lease = next((v for v in state(goal)['leases'].values() if v['token'] == payload.get('lease')), None)
        if not lease or payload.get('actor') != lease['worker']:
            raise ValueError('Verification requires the bound phase executor')
        if lease['kind'] != 'execute' or lease['owner'] != (self.runtime or {}).get('root_id') or lease['expires_at'] <= time.time():
            raise ValueError('Verification requires a current owned execution lease')
        acquired, scope = self.execution_preflight(goal, payload['phase'], lease, payload)
        commands = payload.get('commands')
        if not isinstance(commands, list) or not commands or any(not isinstance(command, list) or not command or any(not isinstance(arg, str) or not arg for arg in command) for command in commands):
            raise ValueError('Verification commands must be nonempty argument arrays')
        before = self.workspace_digest()
        logs = self.repo / '.zzzops' / 'diagnostics'
        logs.mkdir(parents=True, exist_ok=True)
        results = []
        for index, command in enumerate(commands):
            log = logs / f'verify-{lease["token"]}-{index}.log'
            with log.open('w') as output:
                process = subprocess.run(command, cwd=self.repo, stdout=output, stderr=subprocess.STDOUT, timeout=300, check=False)
            results.append({'command': command, 'exit_code': process.returncode, 'log_hash': hashlib.sha256(log.read_bytes()).hexdigest(), 'log': str(log)})
        after = self.workspace_digest()
        if before != after:
            raise ValueError('Verification changed repository inputs; inspect generated changes and rerun')
        proof = {'commands': results, 'workspace': after, 'passed': all(r['exit_code'] == 0 for r in results)}
        if acquired:
            proof.update(acquisition={**{k: acquired[k] for k in ('git_commit', 'workspace_digest', 'predecessor', 'checkout_overrides') if k in acquired}, 'input_hash': lease['input_hash']},
                         phase=payload['phase'], lease=lease['token'], actor=lease['worker'], outputs=self.file_hashes(scope[payload['phase']]))
        return self.mutate(number, payload, _proof=proof)

    def mutate(self, number, payload, *, _proof=None):
        if not isinstance(payload, dict) or not isinstance(payload.get('request_id'), str) or not payload['request_id']:
            raise ValueError('Every mutation requires a stable request_id for safe retries')
        if payload.get('operation') == 'verify' and _proof is None:
            return self.verify(number, payload)
        with self.locked():
            # Public preflight already validated the portfolio. Renewal only touches
            # this exact lease; rehydrating every goal under the lock caused timeouts.
            portfolio = [] if payload.get('operation') == 'renew' else self.portfolio(allow_invalid=payload.get('operation') in {'revise', 'recover_legacy'})
            # A mutation must re-read its exact provider body under the storage
            # lock; read-only workflow context remains portfolio-gateway-only.
            adapter = getattr(self, 'adapter', None)
            exact_reader = getattr(self.api, 'github_goal_record', None)
            if adapter is not None and callable(exact_reader):
                issue = adapter.get_issue(number)
                goal = exact_reader(issue)
            else:
                issue, goal = self.read(number)
            projected = next((record for record in portfolio if record['key'] == number), None) if portfolio else None
            if isinstance(projected, dict) and isinstance(projected.get('pull_request'), dict):
                # The exact issue body is authoritative for a write, while the
                # portfolio gateway owns the current cached PR observation.
                goal['pull_request'] = copy.deepcopy(projected['pull_request'])
            if portfolio and payload.get('operation') not in {'revise', 'recover_legacy'}:
                if projected is not None:
                    findings = self.validation_blockers(projected)
                    if isinstance(findings, list) and findings:
                        details = '; '.join(
                            f"goal {finding.get('goal', '?')}: {finding.get('code', 'validation_error')} — {finding.get('detail', 'inspect the goal record')}"
                            for finding in findings
                        )
                        raise ValueError(f'Repair validation findings relevant to goal {number} before submitting work: {details}')
            desired = self.api.parse_managed_goal(issue['body'], number)
            durable = state(goal)
            fingerprint = digest(payload)
            receipt = durable['receipts'].get(payload['request_id'])
            if receipt:
                if receipt['hash'] != fingerprint:
                    raise ValueError('request_id was already used with different inputs')
                response = {'next_steps': [{'kind': 'checkpoint', 'goal': number, 'action': 'This request was already applied. Re-read current goal evidence.'}]}
                return self.stop_completed_heartbeat(number, payload, durable, response)
            operation = payload.get('operation')
            human_spec = None
            phase = payload.get('phase')
            runtime = self.runtime or {}
            root = runtime.get('root_id')
            if not root:
                raise ValueError('Current runtime.root_id is required')
            if operation == 'start':
                kind = payload.get('kind')
                step = next((s for s in self.step(number) if s.get('phase') == phase and s.get('kind') == kind), None)
                if not step or kind not in {'execute', 'review', 'human_approval'}:
                    raise ValueError('This phase is not eligible to start')
                if step['input_hash'] != payload.get('input_hash'):
                    raise ValueError('Start inputs changed; request a fresh checkpoint')
                if unresolved_lease_count(portfolio) >= worker_limit(self.project):
                    raise ValueError('Reviewed max_workers limit is already occupied by active phase leases')
                if phase == 'publish':
                    for row in self.portfolio():
                        other = self.read(row['key'])[1] if row['status'] not in {'done', 'cancelled'} else row
                        if other['key'] != number and any(k.startswith('publish:') for k in state(other)['leases']):
                            raise ValueError('Another goal owns publication; wait or recover its lease')
                self.api._policy_context.require_receipt(self.project, step, payload)
                key = phase + ':' + kind
                evidence = goal.get('phase_evidence') or self.api.empty_phase_evidence()
                lease = {'token': uuid.uuid4().hex, 'owner': root, 'worker': root if step['assignment'] == 'root' else None,
                         'selection': step['selection'], 'kind': kind, 'input_hash': step['input_hash'], 'expires_at': time.time() + 900, 'group': step['assignment_group'],
                         'record_hash': digest(evidence['records'].get(phase)) if kind != 'execute' else None,
                         'review_hash': digest(evidence['reviews'].get(phase)) if kind == 'human_approval' else None}
                if kind == 'execute' and phase in {'test_design', 'implement'} and self.reviewed_scope(goal):
                    commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=self.repo, capture_output=True, text=True, check=True).stdout.strip()
                    baseline, actual = self.git_files(commit), self.workspace_files()
                    overrides = self.clean_checkout_overrides(commit, baseline, actual)
                    lease['acquisition'] = {'input_envelope': copy.deepcopy(step['input_envelope']), 'git_commit': commit, 'workspace_digest': digest(actual)}
                    if overrides:
                        lease['acquisition']['checkout_overrides'] = overrides
                    predecessor = self.correction_predecessor(goal, phase, self.reviewed_scope(goal), digest(actual))
                    if predecessor:
                        lease['acquisition']['predecessor'] = predecessor
                durable['leases'][key] = lease
                response = {'next_steps': [{**step, 'kind': 'perform', 'lease': lease, 'action': 'Perform the root step.' if lease['worker'] else 'Launch or resume the assigned worker, then bind its identity using operation=bind. Release the lease if dispatch fails.', 'bind': {'operation': 'bind', 'phase': phase, 'lease': lease['token'], 'actor': '<worker-id>', 'selection': lease['selection'], 'policy_receipt': '<worker copies policy_receipt from policy.path>', 'request_id': 'new-unique-id'}}]}
            elif operation == 'assess':
                graph, nodes, live, _ = self.context(goal)
                if phase not in nodes or payload.get('input_hash') != digest(live[phase]):
                    raise ValueError('Assessment must bind the current phase inputs')
                dimensions = payload.get('dimensions')
                if not isinstance(dimensions, dict):
                    raise ValueError('Root capability assessment dimensions are required')
                self.api.capability_tier(self.api._workflow_section(self.project, 'model_routing')['configuration'], {**dimensions, 'phase_type': phase})
                files = payload.get('files')
                if not isinstance(files, list) or any(not isinstance(path, str) or not path for path in files):
                    raise ValueError('Declared phase inputs must be repository-relative file paths')
                self.file_hashes(files)
                durable['assessments'][phase] = {'dimensions': dimensions, 'goal_spec': live[phase]['goal_spec'], 'policy': live[phase]['policy'], 'files': files}
                response = {'next_steps': [{'kind': 'checkpoint', 'action': 'Re-evaluate the goal with the recorded capability assessment.', 'goal': number}]}
            elif operation == 'route_choice':
                step = next((item for item in self.step(number) if item.get('phase') == phase and item.get('kind') == 'capability_choice'), None)
                choice = payload.get('choice')
                existing = durable['routing_choices'].get(phase)
                if not step and existing and payload.get('selection') is not None:
                    step = {'root_pair': existing['root_pair'], 'requested_pair': existing.get('requested_pair'), 'choices': [existing['choice']]}
                    if choice is None:
                        choice = existing['choice']
                if not step or choice not in step.get('choices', []) or not explicit_approval(payload.get('approved_by')):
                    raise ValueError('Routing choice requires an explicit user-approved current capability checkpoint')
                override = payload.get('selection')
                if override is not None and (not isinstance(override, dict) or set(override) != {'model', 'effort'} or any(not isinstance(value, str) or not value.strip() for value in override.values())):
                    raise ValueError('An explicit model override must contain nonempty model and effort strings')
                durable['routing_choices'][phase] = {
                    'choice': choice, 'root_pair': step['root_pair'], 'requested_pair': step['requested_pair'],
                    'approved_by': payload['approved_by'],
                }
                if override is not None:
                    durable['routing_choices'][phase]['selection'] = override
                response = {'next_steps': [{'kind': 'checkpoint', 'goal': number, 'action': 'The user-selected route is durable. Re-evaluate the phase.'}]}
            elif operation == 'withdraw':
                evidence = goal.get('phase_evidence') or self.api.empty_phase_evidence()
                record = evidence['records'].get(phase)
                if payload.get('record_hash') != digest(record):
                    raise ValueError('Withdrawal requires the exact current record hash')
                if any(k.startswith(str(phase) + ':') for k in durable['leases']):
                    raise ValueError('Stop and reconcile the phase worker before withdrawing its evidence')
                desired['phase_evidence'] = self.api.withdraw_phase_evidence(evidence, phase, reason=payload['reason'], actor=root)
                response = {'next_steps': [{'kind': 'checkpoint', 'goal': number, 'action': 'Reassess withdrawn phase evidence.'}]}
            elif operation == 'revise':
                if payload.get('expected_digest') != goal['digest']:
                    raise ValueError('Goal changed before revision; re-read it')
                changes = payload.get('changes')
                allowed = {'priority', 'value', 'difficulty', 'confidence', 'depends_on', 'parent', 'resources', 'engineering_rigor', 'implementation', 'next_action', 'blockers'}
                if not isinstance(changes, dict) or set(changes) - allowed:
                    raise ValueError('Only goal metadata may be revised; phase evidence and completion use their guarded operations')
                if 'implementation' in changes:
                    incoming = (changes['implementation'] or {}).get('review')
                    existing = (goal.get('implementation') or {}).get('review')
                    if incoming != existing and incoming != {'status': 'not_started', 'checkpoint': None}:
                        raise ValueError('Review approval/checkpoints must come from guarded publication, not metadata revision')
                desired.update(changes)
                projected = [{**row, **changes} if row['key'] == number else row for row in portfolio]
                relation_codes = {'missing_relation', 'self_relation', 'parent_cycle', 'depends_on_cycle', 'duplicate_dependency', 'done_with_unfinished_dependency', 'cancelled_dependency'}
                def issues(rows):
                    return {(f['code'], f['goal'], f['detail']) for f in self.api.audit_portfolio(copy.deepcopy(rows), 'github_issues') if f['code'] in relation_codes}
                if issues(projected) - issues(portfolio):
                    raise ValueError('The proposed metadata would break goal-DAG invariants')
                response = {'next_steps': [{'kind': 'checkpoint', 'goal': number, 'action': 'Re-evaluate changed goal metadata and affected phase evidence.'}]}
            elif operation == 'recover_legacy':
                if payload.get('claim_hash') != digest(goal.get('claim')) or payload.get('worker_status') != 'stopped' or not explicit_approval(payload.get('evidence')):
                    raise ValueError('Legacy claim recovery requires exact claim identity and evidence the worker stopped')
                desired['claim'] = None
                response = {'next_steps': [{'kind': 'checkpoint', 'goal': number, 'action': 'Reassess missing phase evidence; old claims do not imply completed work.'}]}
            elif operation == 'reopen':
                if payload.get('expected_digest') != goal['digest'] or not explicit_approval(payload.get('reason')):
                    raise ValueError('Reopening requires current goal digest and an explicit reason')
                desired['status'] = 'ready'
                desired['next_action'] = payload['reason']
                response = {'next_steps': [{'kind': 'checkpoint', 'goal': number, 'action': 'Re-evaluate all evidence under current policy; retained historical phases may be stale.'}]}
            elif operation == 'specify':
                if payload.get('expected_digest') != goal['digest'] or not isinstance(payload.get('human_spec'), str) or not payload['human_spec'].strip():
                    raise ValueError('Specification changes require exact current goal digest and nonempty human_spec')
                if durable['leases']:
                    raise ValueError('Reconcile workers before changing the specification they consume')
                human_spec = payload['human_spec']
                if not self.api._goals.goal_acceptance_criteria(human_spec):
                    raise ValueError('Specify explicit acceptance bullets so every behavior can be covered by tests')
                response = {'next_steps': [{'kind': 'checkpoint', 'goal': number, 'action': 'Reassess the changed specification and obtain its required design approval.'}]}
            elif operation == 'block':
                if payload.get('category') not in self.api.BLOCKER_CATEGORIES or not explicit_approval(payload.get('reason')):
                    raise ValueError('A concrete categorized blocker is required')
                blocker = {'id': digest({'category': payload['category'], 'reason': payload['reason']})[7:23], 'status': 'open', 'category': payload['category'], 'reason': payload['reason']}
                desired['blockers'] = [b for b in desired['blockers'] if b.get('id') != blocker['id']] + [blocker]
                desired['status'] = 'blocked'
                desired['next_action'] = payload['reason']
                response = {'next_steps': [{'kind': 'checkpoint', 'action': 'The blocker is durable. Continue independent goals.'}]}
            elif operation == 'complete':
                graph, nodes, live, related = self.context(goal)
                frontier = self.api.derive_phase_steps(goal, graph, live, related, review_policy=nodes)
                if frontier['execute'] or frontier['review'] or frontier['blocked'] or frontier.get('approve'):
                    raise ValueError('Goal completion requires every phase and review to be current')
                merged = (goal.get('implementation') or {}).get('pr') and self.pull_request(goal).get('merged')
                if not merged and self.publication_gate(goal):
                    raise ValueError('Aggregate/publication proof is incomplete')
                if durable['leases']:
                    raise ValueError('Reconcile active workers before completing the goal')
                if (goal.get('implementation') or {}).get('pr'):
                    classification = self.classify_merge(goal, self.pull_request(goal))
                    if classification['status'] != 'merged_verified':
                        raise ValueError('Completion requires exact-head merged PR evidence: ' + str(classification))
                desired['status'] = 'done'
                desired['next_action'] = 'Completed from current phase evidence.'
                response = {'next_steps': [{'kind': 'checkpoint', 'action': 'Continue execution across the remaining portfolio.'}]}
            elif operation == 'integrate':
                graph, nodes, live, related = self.context(goal)
                frontier = self.api.derive_phase_steps(goal, graph, live, related, review_policy=nodes)
                if frontier['execute'] or frontier['review'] or frontier['blocked'] or durable['leases']:
                    raise ValueError('Integration requires all phase reviews and reconciled workers')
                current = self.pull_request(goal)
                checks_ready = not self.ci_checks_required(current) or current.get('checks_verified') is True
                if not explicit_approval(payload.get('approved_by')) or payload.get('expected_head') != current['head_oid'] or not checks_ready:
                    raise ValueError('Integration requires exact-head human approval and any CI checks required by reviewed policy')
                if self.publication_gate(goal):
                    raise ValueError('Repair publication topology before integration')
                if not current.get('merged'):
                    subprocess.run(['gh', 'pr', 'merge', goal['implementation']['pr'], '--squash', '--match-head-commit', current['head_oid']], cwd=self.repo, capture_output=True, text=True, check=True)
                desired['implementation']['review'] = {'status': 'approved', 'checkpoint': current['head_oid']}
                response = {'next_steps': [{'kind': 'checkpoint', 'goal': number, 'action': 'Re-read provider evidence before recording completion.'}]}
            else:
                matches = [(k, v) for k, v in durable['leases'].items() if v['token'] == payload.get('lease')]
                if len(matches) != 1:
                    raise ValueError('An exact current phase lease is required')
                key, lease = matches[0]
                if not key.startswith(str(phase) + ':') or lease['owner'] != root:
                    raise ValueError('Lease belongs to another coordinator or phase')
                if operation == 'bind':
                    actor = payload.get('actor')
                    if not isinstance(actor, str) or not actor or payload.get('selection') != lease['selection']:
                        raise ValueError('Bind the actual executor and exact selected model/effort')
                    if lease['worker'] and lease['worker'] != actor:
                        raise ValueError('A bound executor cannot be replaced without recovery')
                    if lease['kind'] != 'human_approval' and phase != 'understand' and actor == root:
                        raise ValueError('Autonomous phase work must be delegated')
                    if lease['kind'] == 'review' and actor == (goal.get('phase_evidence') or {}).get('records', {}).get(phase, {}).get('actor'):
                        raise ValueError('Reviewer must be independent')
                    self.api._policy_context.require_receipt(self.project, {'phase': phase, 'kind': lease['kind']}, payload)
                    lease['worker'] = actor
                    durable['workers'][actor] = {'id': actor, 'group': lease['group'], 'selection': lease['selection']}
                    response = {'next_steps': [{'kind': 'heartbeat', 'assignment': 'root', 'goal': number, 'phase': phase, 'lease': lease, 'action': 'Configure a local liveness probe for the bound worker so the CLI can renew ownership. Exit 0 means active, 1 stopped, other/timeout unknown.', 'submission': {'operation': 'heartbeat', 'phase': phase, 'lease': lease['token'], 'probe': ['<local-worker-status-command>', '<worker-id>']}}]}
                elif operation == 'verify':
                    if payload.get('actor') != lease['worker'] or lease['kind'] != 'execute':
                        raise ValueError('Only the bound executor can verify phase work')
                    proof = _proof
                    self.execution_preflight(goal, phase, lease, payload)
                    if proof['workspace'] != self.workspace_digest():
                        raise ValueError('Verification inputs changed before persistence')
                    results = proof['commands']
                    durable['artifacts'][phase] = proof
                    self.artifact(number, proof)
                    proof_hash = digest(proof)
                    expected = not proof['passed'] if phase == 'test_design' else proof['passed']
                    response = {'next_steps': [{'kind': 'record_result' if expected else 'correct', 'goal': number, 'phase': phase, 'action': 'Submit this evidence after confirming failures exercise the intended missing behavior.' if expected and phase == 'test_design' else 'Submit the verified result.' if expected else 'Correct the checks or implementation and rerun verification.', 'verification': {'reference': 'urn:sha256:' + proof_hash[7:], 'hash': proof_hash}, **({} if proof['passed'] else {'logs': [r['log'] for r in results if r['exit_code'] != 0]})}]}
                elif operation in {'renew', 'release', 'recover'}:
                    if operation == 'recover' and (payload.get('worker_status') != 'stopped' or not payload.get('evidence')):
                        raise ValueError('Recovery requires evidence that the old worker stopped; expiry/unknown liveness is insufficient')
                    if operation == 'release' and lease['worker'] and payload.get('worker_status') not in {'completed', 'stopped'}:
                        raise ValueError('Confirm worker completion or stop before releasing ownership')
                    if operation == 'release' and lease['worker'] and not payload.get('evidence'):
                        raise ValueError('Bound-worker release requires terminal-state evidence')
                    if operation == 'renew':
                        if payload.get('actor') != lease['worker'] or payload.get('worker_status') != 'active':
                            raise ValueError('Renewal requires observed activity of the bound worker')
                        lease['expires_at'] = time.time() + 900
                    else:
                        del durable['leases'][key]
                        if operation == 'recover':
                            durable['workers'].pop(lease['worker'], None)
                    response = {'next_steps': [{'kind': 'checkpoint', 'goal': number, 'action': 'Re-evaluate current goal evidence.'}]}
                else:
                    response = self.submit_evidence(goal, desired, durable, key, lease, payload)
            desired['workflow'] = durable
            if operation != 'renew':
                durable['receipts'][payload['request_id']] = {'hash': fingerprint}
            self.save(issue, goal, desired, human_spec=human_spec)
            if operation == 'renew':
                response = {'next_steps': [{'kind': 'renewed', 'goal': number, 'phase': phase,
                    'actor': lease['worker'], 'lease': lease['token'], 'expires_at': lease['expires_at'],
                    'action': 'Ownership renewal was saved. Continue monitoring the bound worker.'}]}
            else:
                response = self.stop_completed_heartbeat(number, payload, durable, response)
            if operation == 'verify' and response['next_steps'][0]['kind'] == 'record_result':
                artifact = response['next_steps'][0]['verification']
                next_step = next(s for s in self.step(number) if s.get('phase') == phase)
                next_step.update(kind='record_result', action=response['next_steps'][0]['action'])
                record = next_step['result_contract']['record']
                record['actor'] = lease['worker']
                if phase == 'test_design':
                    record['test_design'] = {'baseline_failure': artifact, 'coverage': [{'criterion': criterion, 'test': None, 'exclusion': None} for criterion in record['input_envelope']['acceptance_criteria']]}
                else:
                    record['verification'] = artifact
                next_step['submission'].update(lease=lease['token'], actor=lease['worker'], record=record)
                next_step['verification'] = artifact
                return {'next_steps': [next_step]}
            return response

    def stop_completed_heartbeat(self, number, payload, durable, response):
        token = payload.get('lease')
        if not token or any(v['token'] == token for v in durable['leases'].values()):
            return response
        try:
            self.api._heartbeat.stop_heartbeat(repo=self.repo, root_id=(self.runtime or {}).get('root_id'),
                goal=number, phase=payload.get('phase'), token=token)
        except (OSError, ValueError) as exc:
            # The durable operation already succeeded. Its exact replay retries
            # this local, idempotent cleanup without reapplying goal evidence.
            response['next_steps'].append({'kind': 'repair', 'assignment': 'root',
                'goal': number, 'phase': payload.get('phase'), 'actor': payload.get('actor'),
                'action': 'The durable submission succeeded. Resolve the local heartbeat error, then replay this exact request to stop monitoring the completed lease.',
                'reason': str(exc), 'submission': copy.deepcopy(payload),
                'command': ['--intent', 'execute', '--goal', str(number), '--runtime', '<runtime.json>', '--input', '<submission.json>']})
        return response

    def submit_evidence(self, goal, desired, durable, key, lease, payload):
        api = self.api
        phase, operation = payload['phase'], payload['operation']
        if not lease['worker'] or payload.get('actor') != lease['worker']:
            raise ValueError('Only the bound executor may submit evidence')
        acquired, scope = None, None
        if lease['kind'] == 'execute' and operation == 'record_result':
            acquired, scope = self.execution_preflight(goal, phase, lease, {
                **payload, 'input_envelope': payload.get('record', {}).get('input_envelope'),
            })
        graph, nodes, live, related = self.context(goal)
        if live[phase].get('provider', {}).get('snapshot', {}).get('migration', {}).get('decision', {}).get('action') == 'block':
            raise ValueError('Affected contract evidence requires investigation before submission')
        frontier = api.derive_phase_steps(goal, graph, live, related, review_policy=nodes)
        expected_frontier = frontier['execute'] if lease['kind'] == 'execute' else frontier['review']
        if phase not in {item['phase'] for item in expected_frontier}:
            raise ValueError('Ancestor or review evidence changed; this assignment is no longer eligible')
        if lease['input_hash'] != digest(live[phase]):
            raise ValueError('Phase inputs changed while work was in flight; reassess before submitting')
        evidence = goal.get('phase_evidence') or api.empty_phase_evidence()
        if lease['kind'] != 'execute' and lease['record_hash'] != digest(evidence['records'].get(phase)):
            raise ValueError('The reviewed artifact changed while review was in flight')
        if lease['kind'] == 'human_approval' and lease['review_hash'] != digest(evidence['reviews'].get(phase)):
            raise ValueError('The independent review changed before human approval')
        if operation == 'record_result' and lease['kind'] == 'execute':
            record = copy.deepcopy(payload['record'])
            if record.get('status') == 'not_required' and (nodes[phase].get('not_required', 'never') == 'never' or (record.get('not_required') or {}).get('policy_rule') != nodes[phase]['not_required']):
                raise ValueError('The reviewed policy does not permit this phase exemption')
            if record['actor'] != lease['worker'] or record['selection'] != lease['selection']:
                raise ValueError('Result actor/model/effort does not match the assigned executor')
            routing_hash = digest(durable['assessments'].get(phase))
            if record.get('routing') != {'reference': 'urn:' + routing_hash, 'hash': routing_hash}:
                raise ValueError('Result routing must bind the current capability assessment')
            # Declared file dependencies are re-read at submission, not trusted hashes.
            files = payload.get('files', [])
            actual = self.file_hashes(files)
            expected = record['input_envelope']['repository']['snapshot'].get('files', {})
            writable = set(scope[phase]) if acquired else set()
            if set(actual) != set(expected) or any(actual[path] != expected[path] for path in actual if path not in writable):
                raise ValueError('Declared file evidence changed or was omitted')
            live[phase]['repository']['snapshot']['files'] = expected if acquired else actual
            if acquired:
                proof = durable['artifacts'].get(phase) or {}
                if (proof.get('acquisition') != {**{k: acquired[k] for k in ('git_commit', 'workspace_digest', 'predecessor', 'checkout_overrides') if k in acquired}, 'input_hash': lease['input_hash']}
                    or proof.get('actor') != lease['worker'] or proof.get('lease') != lease['token']
                    or proof.get('phase') != phase or proof.get('outputs') != self.file_hashes(scope[phase])):
                    requirement = 'failing-baseline' if phase == 'test_design' else 'passing verification'
                    raise ValueError(f'Current {requirement} proof does not bind this acquisition, actor, lease and output')
            if phase in {'implement', 'publish'} and record.get('status') != 'not_required':
                proof = durable['artifacts'].get(phase)
                if not proof or not proof.get('passed') or proof.get('workspace') != self.workspace_digest() or (record.get('verification') or {}).get('hash') != digest(proof):
                    raise ValueError('Implementation/publication requires current passing verification from operation=verify')
            if phase == 'test_design' and record.get('status') != 'not_required':
                proof = durable['artifacts'].get(phase)
                if not proof or proof.get('passed') or proof.get('workspace') != self.workspace_digest() or ((record.get('test_design') or {}).get('baseline_failure') or {}).get('hash') != digest(proof):
                    raise ValueError('Test design requires current failing-baseline evidence from operation=verify')
            if phase == 'publish' and (goal.get('implementation') or {}).get('branch'):
                current = self.pull_request(goal)
                if self.publication_gate(goal):
                    raise ValueError('Publication topology changed; reconcile before recording the result')
                desired['implementation']['review'] = {'status': 'not_started', 'checkpoint': current['head_oid']}
            if record.get('output'):
                self.read_artifact(goal['key'], record['output'])
            desired['phase_evidence'] = api.record_phase_result(
                evidence, phase, record, live[phase], phase_policy=nodes,
            )
        elif operation == 'record_review' and lease['kind'] == 'review':
            if phase == 'publish' and (goal.get('implementation') or {}).get('pr'):
                current = self.pull_request(goal)
                if self.ci_checks_required(current) and current.get('checks_verified') is not True:
                    raise ValueError('Publication review requires any CI checks required by reviewed policy')
            outcomes = payload.get('outcomes')
            if not isinstance(outcomes, dict) or set(outcomes) != {'acceptance', 'entropy'}:
                raise ValueError('Review requires separate acceptance and entropy outcomes')
            entropy = outcomes['entropy']
            if not isinstance(entropy, dict) or entropy.get('outcome') not in {'no_findings', 'fixed', 'follow_up'} or not entropy.get('evidence'):
                raise ValueError('Entropy review requires an explicit evidenced disposition')
            if entropy['outcome'] == 'follow_up':
                ids = entropy.get('goals', [])
                if not ids:
                    raise ValueError('Out-of-scope entropy requires durable follow-up goals immediately')
                for number in ids:
                    _, followup = self.read(number)
                    if followup['status'] in {'done', 'cancelled'} or (followup.get('parent') != goal['key'] and goal['key'] not in followup.get('depends_on', [])):
                        raise ValueError('Entropy follow-up must be an open goal linked to this reviewed goal')
            if outcomes['acceptance'] not in {'approved', 'changes_requested'}:
                raise ValueError('Acceptance review decision is invalid')
            self.read_artifact(goal['key'], payload['artifact'])
            desired['phase_evidence'] = api.record_phase_review(evidence, phase, payload['artifact'], lease['worker'], decision=outcomes['acceptance'], require_independent=nodes[phase]['review'].get('independent', True), outcomes=outcomes)
        elif operation == 'approve' and lease['kind'] == 'human_approval':
            if payload.get('actor') != (self.runtime or {}).get('root_id'):
                raise ValueError('Human approval must be recorded by root')
            if payload.get('approval', {}).get('actor') != payload['actor']:
                raise ValueError('Approval provenance must match the root executor')
            if not explicit_approval(payload['approval'].get('approval_token')):
                raise ValueError('Replace the approval placeholder with an explicit user approval reference')
            # Exact reviewed evidence, never approval implied by phase completion.
            desired['phase_evidence'] = api.record_phase_approval(evidence, phase, actor='root', approval_token=payload['approval']['approval_token'])
        elif operation == 'withdraw':
            desired['phase_evidence'] = api.withdraw_phase_evidence(evidence, phase, reason=payload['reason'], actor=lease['worker'])
        else:
            raise ValueError('Operation does not match the leased phase assignment')
        del durable['leases'][key]
        return {'next_steps': [{'kind': 'checkpoint', 'goal': goal['key'], 'action': 'Re-read the goal to obtain its next required phase or review.'}]}


def checkpoint(api, repo, project, runtime, number=None, *, engine=None):
    engine = engine or Workflow(api, repo, project, runtime)
    goals = engine.portfolio()
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
                    remaining_starts -= 1
                else:
                    capacity_blocked = True
            elif step.get('kind') in {'blocker', 'dependency', 'await_worker'}:
                waiting.append(step)
            else:
                runnable.append(step)
    def capacity_step():
        return {
            'kind': 'await_worker', 'assignment': 'root',
            'action': 'Reviewed max_workers capacity is occupied. Reconcile, release, or recover an existing phase lease before starting another worker.',
            'active_leases': unresolved_lease_count(goals), 'max_workers': limit,
            'recheck': {
                'after_seconds': 30,
                'command': ['--intent', 'execute', '--runtime', '<runtime.json>'],
                'action': 'Recheck active leases after the interval; do not start work beyond the reviewed capacity.',
            },
        }
    # Understanding is the portfolio intake gate. It exposes unresolved human
    # scope and authority questions before new downstream work is dispatched;
    # existing leases are counted above but never revoked here.
    pending_understanding = []
    for goal in goals:
        if goal.get('status') in {'done', 'cancelled'}:
            continue
        # Legacy/minimal projections cannot establish a broad portfolio gate.
        # The gate applies only when the canonical phase-evidence shape is
        # present; normal per-goal dispatch still reports their next action.
        if not isinstance(goal.get('phase_evidence'), dict):
            continue
        evidence = goal['phase_evidence']
        record = (evidence.get('records') or {}).get('understand')
        review = (evidence.get('reviews') or {}).get('understand')
        if not isinstance(record, dict) or not isinstance(review, dict) or review.get('record_hash') != digest(record):
            pending_understanding.append(goal)
    if pending_understanding and number is None:
        steps = []
        for goal in pending_understanding:
            steps.extend(step for step in engine.step(goal['key']) if step.get('phase') == 'understand')
            if len(steps) >= limit:
                break
        if steps:
            return {'next_steps': steps[:limit]}
    if number is not None:
        if number not in {g['key'] for g in goals}:
            raise ValueError('Requested goal is not in the validated portfolio')
        goal = next(goal for goal in goals if goal['key'] == number)
        findings = engine.validation_blockers(goal)
        if isinstance(findings, list) and findings:
            return {'next_steps': [{'kind': 'blocker', 'assignment': 'root', 'goal': number,
                'action': 'Repair this goal or one of its prerequisites before continuing.',
                'findings': findings}]}
        runnable_steps, waiting_steps = [], []
        partition(engine.step(number), runnable_steps, waiting_steps)
        if capacity_blocked and len(runnable_steps) < limit:
            runnable_steps.append(capacity_step())
        steps = (runnable_steps or waiting_steps)[:limit]
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
    if payload is not None and payload.get('operation') not in PUBLIC_OPERATIONS:
        raise ValueError('Submission operation is missing or unsupported')
    if intent not in api.WORKFLOW_SKILL_INTENTS.get(source, set()):
        raise ValueError('The source skill cannot initiate this intent')
    package = api._package.package_status()
    if not package.get('ok'):
        raise ValueError('Repair or reinstall the invalid ZzzOps package')
    operation = payload.get('operation') if isinstance(payload, dict) else None
    readonly = intent == 'preview'
    if readonly and payload is not None:
        raise ValueError('Preview never accepts mutations')
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
            preflight_policy_proposal(api, repo, proposal)
            proposal_hash = digest(proposal)
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / (proposal_hash.split(':')[1] + '.json')
            api.atomic_text(path, json.dumps(proposal, ensure_ascii=False, sort_keys=True))
            return {'next_steps': [{'kind': 'human_approval', 'assignment': 'root', 'action': 'Review this exact project/policy proposal with the user before approving.', 'proposal': str(path), 'hash': proposal_hash, 'submission': {'operation': 'policy_approve', 'proposal_hash': proposal_hash, 'approved_by': '<user>'}}]}
        proposal_hash = payload['proposal_hash']
        if not explicit_approval(payload.get('approved_by')) or not isinstance(proposal_hash, str) or not __import__('re').fullmatch(r'sha256:[0-9a-f]{64}', proposal_hash):
            raise ValueError('Explicit human approval of the exact proposal hash is required')
        proposal = json.loads((directory / (proposal_hash.split(':')[1] + '.json')).read_text())
        if digest(proposal) != proposal_hash:
            raise ValueError('Policy proposal changed after review')
        prospective = preflight_policy_proposal(api, repo, proposal)
        applied = api.apply_plan(repo, prospective)
        api.confirm_project(repo, applied['policy_digest'], payload['approved_by'], [], True)
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
    engine.portfolio(allow_invalid=operation in {'revise', 'adopt', 'recover_legacy'})
    if operation == 'read' and number is not None:
        _, goal = engine.read(number)
        evidence = goal.get('phase_evidence') or api.empty_phase_evidence()
        content = engine.read_artifact(number, payload['artifact']) if payload.get('artifact') else {'specification': goal['human_spec'], 'acceptance_criteria': goal['acceptance_criteria'], 'phase_record': evidence['records'].get(payload.get('phase')), 'phase_review': evidence['reviews'].get(payload.get('phase'))}
        return {'next_steps': [{'kind': 'inspect_evidence', 'goal': number, 'action': 'Use this current evidence for the assigned phase.', 'content': content}]}
    if operation == 'artifact' and number is not None:
        with engine.locked():
            _, goal = engine.read(number)
            lease = next((v for v in state(goal)['leases'].values() if v['token'] == payload.get('lease')), None)
            if not lease or lease['expires_at'] <= time.time() or lease['owner'] != (runtime or {}).get('root_id') or lease['worker'] != payload.get('actor'):
                raise ValueError('Artifact persistence requires the bound phase executor')
            artifact = engine.artifact(number, payload['content'])
        kind = 'record_review' if lease['kind'] == 'review' else 'record_result'
        return {'next_steps': [{'kind': kind, 'goal': number, 'action': 'Use this immutable artifact reference in the assigned submission.', 'artifact': artifact}]}
    administrative = api._workflow_admin.handle(api, repo, project, source, runtime, payload) if operation not in {'capture_propose', 'capture'} else None
    if administrative is not None:
        return administrative
    if operation == 'heartbeat':
        _, goal = engine.read(number)
        lease = next((v for v in state(goal)['leases'].values() if v['token'] == payload.get('lease')), None)
        if not lease or not lease['worker'] or lease['owner'] != (runtime or {}).get('root_id'):
            raise ValueError('Heartbeat requires a lease owned by the current coordinator and a bound executor')
        api._heartbeat.start_heartbeat(repo=repo, root_id=lease['owner'], runtime_path=api.runtime_path, cli_path=Path(api.__file__), goal=number, phase=payload['phase'], token=lease['token'], actor=lease['worker'], probe_argv=payload['probe'])
        return {'next_steps': [{'kind': 'perform', 'goal': number, 'phase': payload['phase'], 'action': 'The local coordinator is monitoring this worker. Continue its assigned work.'}]}
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
        parent = payload.get('request', {}).get('goal', {}).get('parent')
        if parent is None:
            if not explicit_approval(payload.get('approved_by')) or payload.get('proposal_hash') != digest(payload['request']):
                raise ValueError('Explicit approval of this exact goal design is required')
        else:
            _, parent_goal = engine.read(parent)
            graph, nodes, live, related = engine.context(parent_goal)
            frontier = api.derive_phase_steps(parent_goal, graph, live, related, review_policy=nodes)
            if any(item['phase'] == 'understand' for key in ('execute', 'review', 'blocked') for item in frontier[key]):
                raise ValueError('Child capture requires current parent design approval')
        with engine.locked():
            created = api.apply_goal_create(engine.adapter, engine.repository, payload['request'], allow_deferred=True)
        engine.invalidate()
        # Capture occurs while the human who approved the goal is present.
        # Surface its required understanding work now instead of losing that
        # review opportunity behind a generic later checkpoint.
        return checkpoint(api, repo, project, runtime, engine=engine)
    if operation == 'adopt':
        with engine.locked():
            api.migrate_open_repository_goals(repo, project, limit=payload.get('limit', 25))
        return {'next_steps': [{'kind': 'checkpoint', 'action': 'Re-evaluate open goals; closed goals remain untouched.'}]}
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
        return {'next_steps': [{'kind': 'adopt', 'assignment': 'root', 'instruction': api.workflow_instruction(source), 'submission': {'operation': 'adopt', 'limit': 25}, 'action': 'Adopt open goals only; preserve historical records and current implementation links.'}]}
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
    if api._policy_context.needs_context(result):
        return api._policy_context.attach(
            result, repo, snapshot['project'], source=source,
        )
    return result
