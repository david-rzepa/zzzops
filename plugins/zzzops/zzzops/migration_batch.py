"""Deterministic schema administration; never issues product Results or approvals.

Both execute-on-encounter and bounded batches use the same per-goal transaction.
The immutable source and target are stored before replacing the managed block.
"""
from __future__ import annotations

import copy

MAX_MEMBERS = 20
CONVERTER = 'lossless-v1-v2/1'


def configuration(engine):
    return engine.api._workflow_section(engine.project, 'workflow_adherence')['configuration']


def custom_entry(engine):
    return any(row.get('from') == 1 and row.get('to') == 2
               for row in configuration(engine).get('migration_entries', []))


def human_parts(engine, body):
    start, end = engine.api._goals.GOAL_BLOCK_START, engine.api._goals.GOAL_BLOCK_END
    prefix, managed = body.split(start, 1)
    return prefix, managed.split(end, 1)[1]


def ids(value):
    if (not isinstance(value, list) or not 1 <= len(value) <= MAX_MEMBERS
            or any(type(n) is not int or n <= 0 for n in value)
            or len(set(value)) != len(value)):
        raise ValueError(f'Select one to {MAX_MEMBERS} distinct positive goal numbers')
    return value


def page(engine, request):
    limit, after = request.get('limit', MAX_MEMBERS), request.get('after', 0)
    if type(limit) is not int or not 1 <= limit <= MAX_MEMBERS or type(after) is not int or after < 0:
        raise ValueError('Migration page requires a bounded positive limit and nonnegative cursor')
    capability, rows, findings, *_ = engine.api.github_repository_goal_index(engine.repo, engine.project)
    if not capability.get('usable') or findings:
        raise ValueError('Minimal open-goal discovery is incomplete or unavailable')
    if any(type(row.get('number')) is not int or row['number'] <= 0 for row in rows):
        raise ValueError('Invalid goal index identity')
    numbers = sorted({row['number'] for row in rows if str(row.get('state', '')).lower() == 'open' and row['number'] > after})
    selected = numbers[:limit]
    return selected, {'remaining': max(0, len(numbers) - len(selected)), 'cursor': selected[-1] if selected else after}


def load(engine, number, reference):
    engine.api._phase_evidence.validate_ref(reference)
    if reference['uri'].startswith('git:'):
        return engine.node_published_artifact(reference)[0]
    if engine.node_ref_goal(reference, number) != number:
        raise ValueError('Migration receipt references a different goal')
    return engine.artifact_index(number).observe(reference['hash'])[0]


def state(engine, number):
    issue = engine.adapter.get_issue(number)
    if str(issue.get('state', '')).lower() == 'closed':
        return issue, None, 'closed'
    envelope = engine.api.parse_managed_goal(issue.get('body', ''), number)
    if not envelope:
        raise ValueError('Missing canonical goal envelope')
    if envelope['schema_version'] == 2:
        if envelope['repository'] != engine.repository:
            raise ValueError('Canonical goal repository identity mismatch')
        payload = load(engine, number, envelope['payload'])
        if not isinstance(payload, dict): raise ValueError('Current payload must be a JSON object')
        source = load(engine, number, payload['spec'])
        if not isinstance(source, dict): raise ValueError('Current specification artifact must be a JSON object')
        return issue, envelope, 'custom_migration' if source.get('type') == 'migration_source' else 'already_current'
    if custom_entry(engine):
        return issue, envelope, 'custom_migration'
    return issue, envelope, 'legacy'


def selector(node, goal='#this'):
    return {'kind': 'node', 'goal': goal, 'node': node}


def metadata(engine, legacy):
    resources = engine.api.normalize_resources(legacy.get('resources') or [])
    rigor = legacy.get('engineering_rigor') or {}
    if rigor.get('override') is not None:
        raise ValueError('Legacy engineering_rigor.override requires explicit reconciliation with current policy')
    result = {}
    if resources:
        policy = engine.api.project_resource_policy(engine.project)
        exclusive = engine.api.exclusive_resources(resources, policy)
        if exclusive:
            raise ValueError('Legacy exclusive resources require a compatible shared reservation protocol before migration: ' + ', '.join(exclusive))
        result['resources'] = resources
        result['exclusive_resources'] = exclusive
    if rigor.get('risk_categories'):
        assessment = engine.api.derive_engineering_rigor(rigor, engine.api._workflow_section(engine.project, 'engineering_rigor'))
        if not assessment['valid']:
            raise ValueError('Legacy engineering_rigor cannot be mapped under current policy: ' + ', '.join(assessment['errors']))
        result['engineering_rigor'] = assessment
    return result


def map_metadata(engine, graph, legacy, preserved):
    nodes = graph['nodes'] + [entry['template'] for entry in graph['task_sets']]
    if 'engineering_rigor' in preserved:
        rigor = preserved['engineering_rigor']
        settings = engine.api._workflow_section(engine.project, 'model_routing')['configuration']
        ranks = {row['id']: row['rank'] for row in settings['tiers']}
        # Unknown/custom tasks take the maximum across supported phase mappings,
        # rather than silently escaping a phase-specific reviewed risk floor.
        phases = engine.api._policy.WORKFLOW_PHASE_TYPES
        for node in nodes:
            phase = node['id'].removeprefix('review_').removeprefix('approve_')
            dimensions = {'engineering_rigor': rigor['effective'],
                'consequence': 'architectural' if 'architecture' in rigor['risk_categories'] else 'bounded',
                'boundedness': 'atomic' if legacy.get('difficulty') in {'XS', 'S'} else 'bounded'}
            floors = [engine.api._policy.capability_tier(settings, {**dimensions, 'phase_type': p})['tier']
                      for p in ([phase] if phase in phases else sorted(phases))]
            executor = node['executor']
            executor['capability'] = max([executor['capability'], *floors], key=ranks.__getitem__)
            node['prompt'] += '\nPreserved engineering requirement: effective rigor ' + rigor['effective'] + '; risks ' + ', '.join(rigor['risk_categories']) + '. Apply the reviewed engineering-rigor policy to this work.'


def remediation(number, reason):
    """Useful even when parsing failed; never proposes blind field deletion."""
    lower = reason.lower()
    fields, steps = ['managed_goal'], ['Save the exact issue body and comments before making a targeted repair.']
    if 'rigor' in lower:
        fields = ['engineering_rigor']
        steps += ['Inspect the named risk categories or per-goal override against the reviewed engineering_rigor policy. Preserve the requirement in goal text and reconcile its current meaning before changing metadata; do not silently delete it.']
    elif 'ownership' in lower or ('reservation' in lower and 'exclusive resources' not in lower):
        fields = ['claim', 'workflow.leases', 'resources']
        steps += ['Identify the recorded owner and obtain observed stopped evidence. Use the supported recovery/release contract; expiry alone is not permission to discard ownership.']
    elif 'dependency' in lower or 'blocker' in lower:
        fields = ['depends_on', 'blockers']
        steps += ['Inspect only the named dependency or blocker, including targeted historical evidence if closed. Preserve the relationship and establish equivalent current evidence or a reviewed graph mapping.']
    elif 'resource' in lower:
        fields = ['resources']
        steps += ['Inspect the named exclusive resources and current reservation policy. If a resource is obsolete, preserve its history and confirm retirement before a targeted metadata change. Otherwise use a reviewed mapping with a shared reservation protocol for legacy and current workers. A DAG resource name alone cannot replace provider exclusion; resource paths do not grant edit authority.']
    elif 'custom' in lower:
        fields = ['payload.spec', 'payload.graph']
        steps += ['Resume the existing custom conversion contract. If its policy entry was retired, reconcile that exact graph through policy review; do not replace its evidence or ownership with an automatic reset.']
    elif 'revision' in lower:
        fields = ['revision']
        steps += ['Recover the positive integer revision from the most recent valid issue history or transaction. Do not invent a revision or rewrite unrelated fields.']
    elif 'priority' in lower:
        fields = ['priority', 'labels']
        steps += ['Choose the intended priority and reconcile the canonical field with exactly one matching native priority label.']
    elif 'pending' in lower or 'prepared' in lower:
        fields = ['migration_receipt', 'policy']
        steps += ['Inspect the immutable prepared transaction and its source/target/policy references. Restore missing exact artifacts or reconcile policy drift; retain the pending receipt and do not manufacture a replacement target.']
    else:
        steps += ['Use the reported error to repair only the invalid canonical field or missing exact artifact. Recover original values from issue history; preserve parent, dependencies, blockers, ownership, and all human text.']
    steps += ['Rerun migration for this goal; successful members need no rollback or repeated approval.']
    return {'fields': fields, 'steps': steps,
        'retry': {'operation': 'migration_batch', 'action': 'migrate', 'goals': [number]}}


def normal_graph(engine, legacy, preserved):
    graph = copy.deepcopy(configuration(engine)['phase_dag'])
    engine.api._phase_evidence.validate_graph(graph)
    nodes = {node['id']: node for node in graph['nodes']}
    dependencies = legacy['depends_on']
    blockers = [b for b in legacy['blockers'] if b.get('status') == 'open']
    # Only mappings whose execution meaning is known are automatic. Do not
    # silently remove a custom workflow's resource or dependency semantics.
    if (dependencies or blockers) and not {'test_design', 'implement', 'observe_merge'} <= nodes.keys():
        raise ValueError('Current graph has no supported mapping for legacy dependency/blocker gates')
    if (legacy.get('claim') or {}).get('owner') or (legacy.get('workflow') or {}).get('leases'):
        raise ValueError('Predecessor ownership requires observed stopped recovery before migration')
    if legacy.get('status') in {'done', 'cancelled'}:
        raise ValueError('Open predecessor has terminal status; reconcile its provider state first')
    for dependency in dependencies:
        try:
            related_issue, related, kind = state(engine, dependency)
            if kind == 'closed':
                # Explicitly targeted history can be read; it is never migrated.
                related = engine.api.parse_managed_goal(related_issue['body'], dependency)
                if not related or related['schema_version'] != 2:
                    raise ValueError('Closed predecessor has no current generic dependency evidence')
            if kind == 'custom_migration': raise ValueError('Dependency is in a custom migration')
            target_graph = configuration(engine)['phase_dag'] if related['schema_version'] == 1 else load(engine, dependency, load(engine, dependency, related['payload'])['graph'])
            contracts = {n['id']: n for n in target_graph['nodes']}
            review = contracts['review_implement']['outputs']['value']
            if review['schema']['fields']['decision'].get('values') != ['approved', 'changes_requested']:
                raise ValueError('Dependency review has incompatible decision semantics')
            if 'observe_merge' not in contracts: raise ValueError('Dependency lacks a merge observation gate')
        except (ValueError, KeyError, OSError) as exc:
            raise ValueError(f'Dependency {dependency} cannot be mapped: {exc}') from exc
        for name in ('test_design', 'implement'):
            node = nodes[name]
            node['requires'].append(selector('review_implement', dependency))
            node['inputs'][f'legacy_dependency_{dependency}'] = {
                'producer': {'node': selector('review_implement', dependency)}, 'output': 'value',
                'path': ['decision'], 'mode': 'content', 'type': {'kind': 'enum', 'values': ['approved']}}
        nodes['observe_merge']['requires'].append(selector('observe_merge', dependency))
    if blockers:
        if 'legacy_blockers' in nodes: raise ValueError('Current graph already uses reserved legacy_blockers identity')
        gate = {'id': 'legacy_blockers',
                'prompt': 'Resolve every preserved blocker with actual evidence before workspace work: ' + engine.api._workflow.comment_store.canonical(blockers),
                'inputs': {}, 'outputs': {'value': {'type': 'text', 'schema': {'kind': 'string'}}},
                'requires': [], 'executor': {'role': 'root', 'capability': 'bounded', 'resources': [],
                    'authority': {'subject': selector('legacy_blockers'), 'output': 'value'}},
                'independent_of': [], 'gates': [], 'resolves': [], 'permits': []}
        graph['nodes'].append(gate)
        for node in graph['nodes']:
            if node['executor']['resources']:
                node['requires'].append(selector('legacy_blockers'))
    map_metadata(engine, graph, legacy, preserved)
    engine.api._phase_evidence.validate_graph(graph)
    return graph


def prepared_source(engine, number, issue):
    """Recover exact pre-publication inputs, never infer a receipt from labels."""
    digest = engine.api._workflow.digest
    rows = []
    for row in engine.artifact_index(number).envelopes:
        context = row.get('context')
        if context is None:
            continue
        if not isinstance(context, dict):
            raise ValueError('Pending migration transaction context must be an object or null')
        if context.get('migration') and context.get('source_hash') == digest(issue['body']):
            rows.append(context)
    if not rows:
        return issue, None
    context = rows[-1]
    receipt = load(engine, number, context['migration']['receipt'])
    if (receipt.get('type') != 'schema_migration' or receipt.get('repository') != engine.repository
            or receipt.get('goal') != number or receipt.get('converter') != CONVERTER):
        raise ValueError('Pending migration receipt identity differs')
    policy = load(engine, number, receipt['policy'])
    if policy != engine.project['policy']:
        raise ValueError('Pending migration policy/graph drift; stale prepared target cannot publish')
    source = load(engine, number, receipt['source'])
    target = load(engine, number, receipt['target_intent'])
    payload = load(engine, number, target['payload'])
    load(engine, number, payload['spec']); load(engine, number, payload['graph'])
    if source.get('type') != 'migration_source' or source['content']['body'] != issue['body']:
        raise ValueError('Pending migration source identity differs')
    return source['content'], context


def migrate_one(engine, number):
    with engine.locked():
        engine.invalidate()
        issue, legacy, kind = state(engine, number)
        if kind != 'legacy': return {'status': kind, **({'published_target': legacy} if kind == 'already_current' else {})}
        priorities = [label.get('name') if isinstance(label, dict) else label for label in issue.get('labels', [])]
        priorities = [label for label in priorities if isinstance(label, str) and label.startswith('zzzops:priority:')]
        if priorities != ['zzzops:priority:' + legacy['priority']]:
            raise ValueError('Canonical priority differs from native labels; reconcile priority before lossless migration')
        source_issue, pending = prepared_source(engine, number, issue)
        preserved = metadata(engine, legacy)
        graph = normal_graph(engine, legacy, preserved)
        wf = engine.api._workflow
        artifacts = {}
        def save(value):
            identity = wf.digest(value); artifacts[identity] = value
            return engine.node_ref(identity, number)
        policy_ref = save(engine.project['policy'])
        source_ref = save({'type': 'migration_source', 'content': source_issue, 'producer': None,
            'provenance': {'actor': CONVERTER, 'source': None, 'policy': policy_ref['hash']}})
        prefix, suffix = human_parts(engine, issue['body'])
        specification = prefix + suffix
        if preserved:
            specification += '\n\nPreserved legacy planning metadata (resource declarations are reservations, not edit authority):\n' + wf.comment_store.canonical(preserved)
        spec = save({'type': 'goal_specification', 'content': specification, 'producer': None,
            'provenance': {'actor': CONVERTER, 'source': source_ref, 'policy': policy_ref['hash']}})
        payload = {'spec': spec, 'graph': save(graph), 'evidence': [], 'operational': {'leases': [], 'receipts': []}}
        target = {'schema_version': 2, 'repository': engine.repository, 'issue': number,
                  'revision': legacy['revision'] + 1, 'state': 'open', 'parent': legacy['parent'], 'payload': save(payload)}
        receipt = save({'type': 'schema_migration', 'repository': engine.repository, 'goal': number,
            'converter': CONVERTER, 'source': source_ref, 'target_intent': save(target), 'target_payload': target['payload'], 'policy': policy_ref,
            'missing_obligations': ['All current normal workflow evidence, independent reviews and applicable user approvals remain required.']})
        request = {'operation': 'migration_batch', 'action': 'migrate', 'goal': number,
            'request_id': 'migrate-' + wf.digest({'source': source_ref, 'policy': policy_ref, 'converter': CONVERTER})[7:]}
        response = {'next_steps': [{'kind': 'schema_migration', 'goal': number, 'status': 'migrated', 'receipt': receipt}]}
        snapshot = {'number': number, 'issue': issue, 'envelope': {**target, 'revision': legacy['revision']},
                    'artifacts': artifacts, 'migration': {'receipt': receipt, 'policy': policy_ref['hash']}}
        if pending:
            if pending.get('migration') != snapshot['migration'] or pending.get('request_hash') != wf.digest(request):
                raise ValueError('Prepared migration source/target/request identity changed')
            snapshot['pending'] = pending
        engine.node_persist(snapshot, copy.deepcopy(payload), response, request)
        # The intent excludes the operational receipt to avoid a circular hash.
        # node_persist's exact durable context binds the committed envelope.
        published = engine.api.parse_managed_goal(engine.adapter.get_issue(number)['body'], number)
        return {'status': 'migrated', 'receipt': receipt, 'published_target': published}


def next_steps(engine, number):
    """Read scoped normal gates; task acquisition still enforces global capacity."""
    try:
        snapshot = engine.node_snapshot(number)
        steps = []
        for key, state_ in snapshot['projection']['states'].items():
            if state_['node']['goal'] != number: continue
            lease = snapshot['projection']['leases'].get(key)
            if lease:
                steps.append({'kind': 'await_worker', 'goal': number, 'node': state_['node'], 'lease': lease})
            elif state_['state'] == 'ready':
                steps.append(engine.node_step(state_))
            elif state_['state'] == 'blocked':
                steps.append({'kind': 'dependency', 'goal': number, 'node': state_['node'], 'reason': state_.get('reason', 'Required evidence missing')})
        return steps or [{'kind': 'checkpoint', 'goal': number, 'action': 'Reinvoke normal execution for this current goal.'}]
    except (ValueError, KeyError, OSError) as exc:
        return [{'kind': 'blocker', 'goal': number, 'reason': str(exc)}]


def run(engine, request):
    action = request.get('action')
    if action not in {'discover', 'migrate', 'status'}:
        raise ValueError('Migration action must be discover, migrate or status; no conversion approval is required')
    allowed = {'operation', 'action', 'request_id', 'goals', 'limit', 'after'}
    if set(request) - allowed: raise ValueError('Unknown migration request fields')
    if 'goals' in request and ('limit' in request or 'after' in request): raise ValueError('Use explicit members or one discovery page')
    numbers, pagination = (ids(request['goals']), {}) if 'goals' in request else page(engine, request)
    members, candidates = {}, []
    for number in numbers:
        try:
            if action == 'migrate':
                member = migrate_one(engine, number)
            else:
                _, _, kind = state(engine, number)
                member = {'status': kind}
            if member['status'] == 'custom_migration': member['remediation'] = remediation(number, 'custom migration')
            if member['status'] == 'legacy': candidates.append(number)
            members[str(number)] = member
        except (ValueError, KeyError, OSError) as exc:
            members[str(number)] = {'status': 'blocked', 'reason': str(exc), 'remediation': remediation(number, str(exc))}
    # All selected migrations finish before resolving related normal gates.
    # Closed and malformed members do not enter broad portfolio hydration.
    if action != 'discover':
        for number, member in members.items():
            if member['status'] in {'migrated', 'already_current', 'custom_migration'}:
                member['next_steps'] = next_steps(engine, int(number))
    continuation = {}
    if pagination.get('remaining'):
        continuation = {'submission': {'operation': 'migration_batch', 'action': action,
                        'limit': request.get('limit', MAX_MEMBERS), 'after': pagination['cursor']}}
    return {'next_steps': [{'kind': 'migration_batch', 'action': action, 'goals': candidates,
        'members': members, 'complete': all(m['status'] in {'migrated', 'already_current'} for m in members.values()), **pagination, **continuation}]}
