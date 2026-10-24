"""Direct, retryable creation of a current-schema managed goal."""
from __future__ import annotations

import copy


def capture(engine, request, proposal_hash):
    api = engine.api
    marker = '<!-- zzzops-capture:' + proposal_hash + ' -->'
    pending_body = request['body'] + marker + '\n'
    created = (engine.adapter.find_capture_goal(marker)
               if hasattr(engine.adapter, 'find_capture_goal') else None)
    if created is None:
        issue = engine.adapter.create_issue({
            'title': request['title'], 'body': pending_body,
            'labels': list(request['labels']),
        })
        number = issue.get('number') if isinstance(issue, dict) else None
        if (type(number) is not int or number <= 0 or issue.get('title') != request['title']
                or issue.get('body') != pending_body
                or str(issue.get('state', '')).lower() != 'open'):
            recovered = (engine.adapter.find_capture_goal(marker)
                         if hasattr(engine.adapter, 'find_capture_goal') else None)
            if recovered is None:
                raise api.GoalTransitionProviderError(
                    'GitHub did not confirm the pending capture issue; retry the exact approved request.')
            created = recovered
        else:
            created = {'number': number, 'revision': 1, 'state': 'open', 'status': 'new',
                       'url': issue.get('html_url')}
    number = created['number']
    issue = engine.adapter.get_issue(number)
    existing = api.parse_managed_goal(issue.get('body', ''), number)
    if existing is not None:
        expected_labels = ['zzzops', *request['labels'], 'zzzops:schema:v2',
                           'zzzops:status:new',
                           'zzzops:priority:' + request['goal']['priority']]
        observed_labels = [row.get('name') if isinstance(row, dict) else row
                           for row in issue.get('labels', [])]
        if (existing.get('schema_version') != 2
                or existing.get('repository') != engine.repository
                or existing.get('issue') != number
                or marker not in issue.get('body', '')
                or issue.get('title') != request['title']
                or str(issue.get('state', '')).lower() != 'open'
                or len(observed_labels) != len(expected_labels)
                or set(observed_labels) != set(expected_labels)):
            raise ValueError('Completed capture provider state differs from the exact approved goal')
        snapshot = engine.node_snapshot(number)
        specification = engine.read_artifact(number, snapshot['payload']['spec'])
        if (not isinstance(specification, dict)
                or specification.get('type') != 'goal_specification'
                or specification.get('content') != request['body']):
            raise ValueError('Completed capture specification differs from the approved request')
        return {'number': number, 'revision': existing['revision'], 'state': 'open',
                'status': 'new', 'url': created.get('url')}
    if issue.get('body') != pending_body or issue.get('title') != request['title']:
        raise ValueError('Marked capture issue differs from the exact approved request')

    legacy = copy.deepcopy(request['goal'])
    # Capture is not a historical migration: retain the approved planning
    # inputs verbatim instead of attempting to reinterpret them as legacy
    # routing policy.
    preserved = {key: copy.deepcopy(value) for key, value in legacy.items()
                 if key not in {'schema_version', 'status', 'revision', 'parent',
                                'depends_on', 'blockers', 'claim', 'implementation'}}
    compilation = api._migration_batch.normal_graph(engine, number, legacy, preserved)
    artifacts = {}

    def save(value):
        identity = api._workflow.digest(value)
        artifacts[identity] = value
        return engine.node_ref(identity, number)

    policy_ref = save(engine.project['policy'])
    provenance = {'actor': 'direct-v2-capture/1', 'source': None,
                  'policy': policy_ref}
    spec_ref = save({'type': 'goal_specification', 'content': request['body'],
                     'producer': None, 'provenance': provenance})
    context = api._migration_batch.goal_context(legacy, preserved)
    context_ref = save({'type': 'goal_context', 'content': context,
                        'producer': None, 'provenance': provenance})
    payload = {'spec': spec_ref, 'graph': save(compilation['graph']),
               'goal_context': context_ref, 'evidence': [],
               'operational': {'leases': [], 'receipts': []}}
    initial_payload = save(payload)
    envelope = {'schema_version': 2, 'repository': engine.repository, 'issue': number,
                'revision': 0, 'state': 'open', 'parent': legacy['parent'],
                'payload': initial_payload}
    transaction = {'operation': 'capture', 'request_id': 'capture-' + proposal_hash[7:],
                   'proposal_hash': proposal_hash}
    response = {'next_steps': [{'kind': 'checkpoint', 'goal': number,
                                'action': 'Direct schema-2 capture committed.'}]}
    snapshot = {'number': number, 'issue': issue, 'envelope': envelope,
                'artifacts': artifacts, 'capture': True,
                'capture_labels': ['zzzops', *request['labels'], 'zzzops:schema:v2',
                                   'zzzops:status:new',
                                   'zzzops:priority:' + legacy['priority']]}
    engine.node_persist(snapshot, copy.deepcopy(payload), response, transaction)
    return {'number': number, 'revision': 1, 'state': 'open', 'status': 'new',
            'url': created.get('url')}
