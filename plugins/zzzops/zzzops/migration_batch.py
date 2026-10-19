"""Deterministic schema administration; never issues product Results or approvals.

Both execute-on-encounter and bounded batches use the same per-goal transaction.
The immutable source and target are stored before replacing the managed block.
"""
from __future__ import annotations

import copy

MAX_MEMBERS = 20
LEGACY_COMPILED_CONVERTER = 'lossless-v1-v2/2'
CONVERTER = 'lossless-v1-v2/3'


def request_for_receipt(receipt, digest):
    """Reconstruct the exact request identity for each supported converter."""
    converter = receipt.get('converter')
    if converter == 'lossless-v1-v2/1':
        manifest = {key: receipt[key] for key in ('source', 'policy', 'converter')}
    elif converter == LEGACY_COMPILED_CONVERTER:
        required = {'repository', 'goal', 'converter', 'compiler_version', 'source',
                    'policy', 'target_intent', 'target_payload'}
        if not required <= receipt.keys():
            raise ValueError('Compiled migration receipt has an incomplete request manifest')
        manifest = {key: receipt[key] for key in sorted(required)}
    elif converter == CONVERTER:
        required = {'repository', 'goal', 'converter', 'static_workflow_version',
                    'static_workflow_hash', 'source', 'policy', 'target_intent', 'target_payload'}
        if not required <= receipt.keys():
            raise ValueError('Static workflow migration receipt has an incomplete request manifest')
        manifest = {key: receipt[key] for key in sorted(required)}
    else:
        raise ValueError('Unsupported migration converter version; exact request is deferred')
    return {'operation': 'migration_batch', 'action': 'migrate', 'goal': receipt['goal'],
        'request_id': 'migrate-' + digest(manifest)[7:]}


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


def metadata(engine, legacy, *, project=None):
    project = engine.project if project is None else project
    resources = engine.api.normalize_resources(legacy.get('resources') or [])
    rigor = legacy.get('engineering_rigor') or {}
    if rigor.get('override') is not None:
        raise ValueError('Legacy engineering_rigor.override requires explicit reconciliation with current policy')
    result = {}
    difficulty = legacy.get('difficulty')
    if difficulty is not None:
        if not isinstance(difficulty, str) or not difficulty:
            raise ValueError('Legacy difficulty has unsupported routing semantics')
        result['difficulty'] = difficulty
    if resources:
        policy = engine.api.project_resource_policy(project)
        exclusive = engine.api.exclusive_resources(resources, policy)
        if exclusive:
            raise ValueError('Legacy exclusive resources require a compatible shared reservation protocol before migration: ' + ', '.join(exclusive))
        result['resources'] = resources
        result['exclusive_resources'] = exclusive
    if rigor.get('risk_categories'):
        assessment = engine.api.derive_engineering_rigor(
            rigor, engine.api._workflow_section(project, 'engineering_rigor'))
        if not assessment['valid']:
            raise ValueError('Legacy engineering_rigor cannot be mapped under current policy: ' + ', '.join(assessment['errors']))
        result['engineering_rigor'] = assessment
    return result


def capability_floor(api, project, metadata, node):
    """Project a migrated goal's routing floor without changing its policy graph."""
    if not isinstance(metadata, dict) or not isinstance(node, dict):
        raise ValueError('Migrated routing context must contain metadata and a node contract')
    executor = node.get('executor')
    if not isinstance(executor, dict) or not isinstance(executor.get('capability'), str):
        raise ValueError('Migrated routing node capability is invalid')
    required = executor['capability']
    rigor = metadata.get('engineering_rigor')
    if rigor is None:
        return required
    if (not isinstance(rigor, dict)
            or not isinstance(rigor.get('effective'), str)
            or not isinstance(rigor.get('risk_categories'), list)):
        raise ValueError('Migrated engineering rigor metadata is invalid')
    settings = api._workflow_section(project, 'model_routing')['configuration']
    ranks = {row['id']: row['rank'] for row in settings['tiers']}
    if required not in ranks:
        raise ValueError('Migrated node capability is not a reviewed tier')
    phase = node.get('id', '').removeprefix('review_').removeprefix('approve_')
    phases = api._policy.WORKFLOW_PHASE_TYPES
    dimensions = {
        'engineering_rigor': rigor['effective'],
        'consequence': ('architectural' if 'architecture' in rigor['risk_categories']
                        else 'bounded'),
        'boundedness': ('atomic' if metadata.get('difficulty') in {'XS', 'S'}
                        else 'bounded'),
    }
    floors = [
        api._policy.capability_tier(
            settings, {**dimensions, 'phase_type': phase_type})['tier']
        for phase_type in ([phase] if phase in phases else sorted(phases))
    ]
    return max([required, *floors], key=ranks.__getitem__)


def goal_context(legacy, preserved):
    """Preserve goal-specific v1 obligations without changing policy workflow."""
    dependencies = legacy.get('depends_on') or []
    blockers = legacy.get('blockers') or []
    if (not isinstance(dependencies, list)
            or any(type(number) is not int or number <= 0 for number in dependencies)
            or len(dependencies) != len(set(dependencies))):
        raise ValueError('Legacy dependencies have unsupported identity semantics')
    if not isinstance(blockers, list) or any(not isinstance(blocker, dict) for blocker in blockers):
        raise ValueError('Legacy blockers have unsupported typed data')
    if not isinstance(preserved, dict):
        raise ValueError('Legacy planning metadata has unsupported typed data')
    return {'version': 1, 'depends_on': copy.deepcopy(dependencies),
            'blockers': copy.deepcopy(blockers), 'metadata': copy.deepcopy(preserved)}


def historical_goal_context(engine, receipt, source, policy):
    """Recover obligations from an authenticated pre-static migration source.

    The caller must first resolve ``source`` through the immutable reference in
    the committed receipt.  These checks bind the decoded v1 goal to that
    receipt before projecting its data into the current goal-context contract.
    """
    converter = receipt.get('converter') if isinstance(receipt, dict) else None
    if converter not in {'lossless-v1-v2/1', LEGACY_COMPILED_CONVERTER, CONVERTER}:
        raise ValueError('Historical goal context requires a supported migration receipt')
    if not isinstance(source, dict) or source.get('type') != 'migration_source':
        raise ValueError('Historical migration source artifact is malformed')
    expected = {'actor': converter, 'source': None,
                'policy': (receipt.get('policy') or {}).get('hash')}
    if source.get('producer') is not None or source.get('provenance') != expected:
        raise ValueError('Historical migration source provenance mismatch')
    if (not isinstance(policy, dict)
            or engine.api._workflow.digest(policy) != expected['policy']):
        raise ValueError('Historical migration policy artifact mismatch')
    issue = source.get('content')
    number = receipt.get('goal')
    if (not isinstance(issue, dict) or type(number) is not int
            or issue.get('number') != number or not isinstance(issue.get('body'), str)):
        raise ValueError('Historical migration source goal identity mismatch')
    legacy = engine.api.parse_managed_goal(issue['body'], number)
    if not isinstance(legacy, dict) or legacy.get('schema_version') != 1:
        raise ValueError('Historical migration source is not a managed v1 goal')
    historical_project = copy.deepcopy(engine.project)
    historical_project['policy'] = copy.deepcopy(policy)
    return goal_context(legacy, metadata(engine, legacy, project=historical_project))


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


def normal_graph(engine, number, legacy, preserved):
    graph = copy.deepcopy(configuration(engine)['phase_dag'])
    engine.api._phase_evidence.validate_graph(graph)
    if (legacy.get('claim') or {}).get('owner') or (legacy.get('workflow') or {}).get('leases'):
        raise ValueError('Predecessor ownership requires observed stopped recovery before migration')
    if legacy.get('status') in {'done', 'cancelled'}:
        raise ValueError('Open predecessor has terminal status; reconcile its provider state first')
    compiler = engine.api._graph_compiler
    definition = engine.api._static_workflow.definition(graph, compiler)
    engine.api._phase_evidence.validate_graph(definition['graph'])
    return definition


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
            rows.append((context, row))
    if not rows:
        return issue, None
    context, transaction = rows[-1]
    receipt = load(engine, number, context['migration']['receipt'])
    if (receipt.get('type') != 'schema_migration' or receipt.get('repository') != engine.repository
            or receipt.get('goal') != number
            or receipt.get('converter') not in {LEGACY_COMPILED_CONVERTER, CONVERTER}):
        raise ValueError('Pending migration receipt identity differs')
    compiler = engine.api._graph_compiler
    converter = receipt.get('converter')
    if converter == LEGACY_COMPILED_CONVERTER:
        if receipt.get('compiler_version') != compiler.SUPPORTED_VERSION:
            raise ValueError('Pending migration compiler version is unsupported; exact prepared target is deferred')
    elif converter == CONVERTER:
        if receipt.get('static_workflow_version') != engine.api._static_workflow.VERSION:
            raise ValueError('Pending migration static workflow version is unsupported; exact prepared target is deferred')
    else:
        raise ValueError('Pending migration converter version is unsupported; exact prepared target is deferred')
    policy = load(engine, number, receipt['policy'])
    if policy != engine.project['policy']:
        raise ValueError('Pending migration policy/graph drift; stale prepared target cannot publish')
    source = load(engine, number, receipt['source'])
    target = load(engine, number, receipt['target_intent'])
    if (target.get('schema_version') != 2 or target.get('repository') != engine.repository
            or target.get('issue') != number or receipt.get('target_payload') != target.get('payload')):
        raise ValueError('Pending migration exact target identity differs')
    payload = load(engine, number, target['payload'])
    load(engine, number, payload['spec'])
    graph = load(engine, number, payload['graph'])
    if converter == LEGACY_COMPILED_CONVERTER:
        compiler.validate_recovery(graph, local_goal=number,
                                   compiler_version=receipt['compiler_version'])
    else:
        definition = engine.api._static_workflow.definition(graph, compiler)
        if definition['graph'] != graph or definition['hash'] != receipt.get('static_workflow_hash'):
            raise ValueError('Pending migration static workflow identity differs')
    if source.get('type') != 'migration_source' or source['content']['body'] != issue['body']:
        raise ValueError('Pending migration source identity differs')
    response = load(engine, number, context['response'])
    expected = {'next_steps': [{'kind': 'schema_migration', 'goal': number,
        'status': 'migrated', 'receipt': context['migration']['receipt']}]}
    if response != expected:
        raise ValueError('Pending migration exact response identity differs')
    # Recreate the original pre-persist artifact set in its canonical insertion
    # order. The transaction envelope also contains node_persist's response and
    # entry artifacts; feeding those back would publish a second transaction.
    ordered = (receipt['policy'], receipt['source'], payload['spec'], payload['graph'],
               *((payload['goal_context'],) if 'goal_context' in payload else ()),
               target['payload'], receipt['target_intent'], context['migration']['receipt'])
    artifacts = {reference['hash']: load(engine, number, reference) for reference in ordered}
    return source['content'], {'context': context, 'receipt': receipt,
        'receipt_ref': context['migration']['receipt'], 'target': target,
        'payload': payload, 'response': response, 'artifacts': artifacts}


def resume_pending(engine, number, issue, legacy, pending):
    """Resume authenticated immutable intent without rebuilding its target."""
    wf = engine.api._workflow
    receipt, target = pending['receipt'], pending['target']
    request = request_for_receipt(receipt, wf.digest)
    context = pending['context']
    if (context.get('request_id') != request['request_id']
            or context.get('request_hash') != wf.digest(request)):
        raise ValueError('Pending migration exact request identity differs')
    snapshot = {'number': number, 'issue': issue,
        'envelope': {**target, 'revision': legacy['revision']},
        'artifacts': copy.deepcopy(pending['artifacts']),
        'migration': copy.deepcopy(context['migration']), 'pending': context}
    engine.node_persist(snapshot, copy.deepcopy(pending['payload']),
                        copy.deepcopy(pending['response']), request)
    published = engine.api.parse_managed_goal(engine.adapter.get_issue(number)['body'], number)
    return {'status': 'migrated', 'receipt': pending['receipt_ref'],
            'published_target': published}


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
        if pending:
            return resume_pending(engine, number, issue, legacy, pending)
        preserved = metadata(engine, legacy)
        compilation = normal_graph(engine, number, legacy, preserved)
        graph = compilation['graph']
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
        context = goal_context(legacy, preserved)
        context_ref = save({'type': 'goal_context', 'content': context, 'producer': None,
            'provenance': {'actor': CONVERTER, 'source': source_ref, 'policy': policy_ref['hash']}})
        payload = {'spec': spec, 'graph': save(graph), 'goal_context': context_ref,
                   'evidence': [], 'operational': {'leases': [], 'receipts': []}}
        target = {'schema_version': 2, 'repository': engine.repository, 'issue': number,
                  'revision': legacy['revision'] + 1, 'state': 'open', 'parent': legacy['parent'], 'payload': save(payload)}
        receipt_value = {'type': 'schema_migration', 'repository': engine.repository, 'goal': number,
            'converter': CONVERTER, 'static_workflow_version': compilation['version'],
            'static_workflow_hash': compilation['hash'],
            'source': source_ref, 'target_intent': save(target), 'target_payload': target['payload'], 'policy': policy_ref,
            'missing_obligations': ['All current normal workflow evidence, independent reviews and applicable user approvals remain required.']}
        receipt = save(receipt_value)
        request = request_for_receipt(receipt_value, wf.digest)
        response = {'next_steps': [{'kind': 'schema_migration', 'goal': number, 'status': 'migrated', 'receipt': receipt}]}
        snapshot = {'number': number, 'issue': issue, 'envelope': {**target, 'revision': legacy['revision']},
                    'artifacts': artifacts, 'migration': {'receipt': receipt, 'policy': policy_ref['hash']}}
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
