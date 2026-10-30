"""Pure policy workflow definition and authenticated phase-event projections.

The caller authenticates event provenance and current subject at ingestion.
These helpers grant no authority and never inspect a provider or workspace.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from collections import OrderedDict
from threading import RLock

_CACHE = OrderedDict()
_CACHE_LOCK = RLock()
_CACHE_BYTES = 16_000_000
_CACHE_ENTRIES = 8

VERSION = 'static-policy-workflow-v1'
REF = {'kind': 'object', 'fields': {'hash': {'kind': 'string'}, 'uri': {'kind': 'string'}}}
EVENT = {'kind': 'object', 'fields': {
    'id': {'kind': 'string'}, 'revision': {'kind': 'integer'},
    'source': REF, 'subject': REF, 'rationale': {'kind': 'string'},
    'target': {'kind': 'union', 'variants': [
        {'kind': 'object', 'fields': {'node': {'kind': 'string'}, 'output': {'kind': 'string'}}},
        {'kind': 'object', 'fields': {'node': {'kind': 'string'}, 'output': {'kind': 'string'},
            'expansion': {'kind': 'string'}, 'item': {'kind': 'string'}, 'generation': {'kind': 'integer'}}}]}}}

SELECTION = {'kind': 'object', 'fields': {
    'items': {'kind': 'map', 'values': EVENT}, 'rationale': {'kind': 'string'}}}
CONTROL_TYPES = {'finding', 'admission', 'resolution', 'resolution_batch', 'supersession', 'withdrawal',
                 'retirement', 'finding_registry', 'applicability_assessment', 'result',
                 'policy_context'}


def digest(value):
    return 'sha256:' + hashlib.sha256(json.dumps(value, ensure_ascii=False,
        sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def targets(graph):
    """Static local policy outputs with ordinary semantic production contracts."""
    return [(node, output) for node in graph['nodes'] + [row['template'] for row in graph['task_sets']]
            if not node['id'].startswith(('gc_', 'sw_'))
            for output, contract in node['outputs'].items()
            if contract['type'] not in CONTROL_TYPES]


def review_name(node, output):
    return 'sw_review_' + digest([node, output])[7:]


def _member_family(graph, target, output, review, source, member, compiler, key):
    """Fixed event-member routes; resolved findings come from admitted history."""
    static = {'kind': 'node', 'goal': '#this', 'node': target['id']}
    ordinary_review = copy.deepcopy(review)
    def replace(value, before, after):
        if value == before: return copy.deepcopy(after)
        if isinstance(value, dict): return {k: replace(v, before, after) for k, v in value.items()}
        if isinstance(value, list): return [replace(v, before, after) for v in value]
        return value
    ordinary_review = replace(ordinary_review, member, static)
    temporary = {'nodes': [copy.deepcopy(target)], 'task_sets': [
        {'id': review['id'] + '_events', 'source': copy.deepcopy(source), 'template': ordinary_review}],
        'terminals': []}
    family = compiler._route_family(temporary, ordinary_review, 'value',
                                    {'subject': static, 'output': output}, key)
    family = replace(family, static, member)
    old_subject = {'kind': 'object', 'fields': {'kind': {'kind': 'string'},
                   'goal': {'kind': 'integer'}, 'node': {'kind': 'string'}}}
    member_subject = {'kind': 'object', 'fields': {'kind': {'kind': 'string'},
        'goal': {'kind': 'integer'}, 'expansion': {'kind': 'string'},
        'item': {'kind': 'string'}, 'generation': {'kind': 'integer'}}}
    if member['kind'] == 'member':
        family = replace(family, old_subject, member_subject)
        for row in family['task_sets']:
            contract = row['template']
            for output_contract in contract['outputs'].values():
                if output_contract['type'] == 'admission':
                    output_contract['schema']['fields']['applicability']['values'] = ['applicable', 'not_applicable']
                    contract['prompt'] += (' If applicability is uncertain, retain the pending event and seek '
                        'missing evidence through the fixed review/data flow. Do not fabricate classification '
                        'or submit an admission until the evidence supports it.')
    # A historical admitted finding must outlive the rejecting review Result.
    # Select it from host-folded immutable admission history, keyed by event.
    resolution = family['task_sets'][-1]
    joined_review = {'kind': 'member', 'goal': '#this', 'expansion': review['id'] + '_events',
                     'item': {'item_key': True}, 'generation': 'current'}
    item_type = {'kind': 'object', 'fields': {'event': copy.deepcopy(EVENT), 'finding': copy.deepcopy(REF)}}
    obligation_source = {'producer': {'slot': 'phase_event_obligations'}, 'output': 'content',
        'path': [target['id'], output], 'mode': 'content',
        'type': {'kind': 'object', 'fields': {'items': {'kind': 'map', 'values': item_type},
                                            'rationale': {'kind': 'string'}}}}
    resolution['source'] = obligation_source
    node = resolution['template']
    node['inputs']['finding'] = {**copy.deepcopy(obligation_source),
        'path': [target['id'], output, 'items', {'item_key': True}, 'finding'], 'type': copy.deepcopy(REF)}
    node['inputs'].pop('approved_reviews', None)
    node['inputs']['review'] = {'producer': {'node': joined_review}, 'output': 'value',
        'path': [], 'mode': 'identity', 'type': copy.deepcopy(review['outputs']['value']['schema'])}
    node['inputs']['approved'] = {'producer': {'node': joined_review}, 'output': 'value',
        'path': ['decision'], 'mode': 'content', 'type': {'kind': 'enum', 'values': ['approved']}}
    node['requires'] = [copy.deepcopy(joined_review)]
    family['nodes'] = []
    return family


def _validate_static_scope(graph, scope, compiler):
    subject = scope.get('subject', {})
    if (subject.get('kind') == 'node' and isinstance(subject.get('goal'), int)
            and not isinstance(subject['goal'], bool) and subject['goal'] > 0):
        target = next((row for row in graph['nodes'] if row['id'] == subject.get('node')), None)
        if target is None or scope.get('output') not in target['outputs']:
            raise ValueError('Unknown absolute policy correction target/output')
    else:
        compiler._validate_scope(graph, scope)


def _exact_target(value, local, exact):
    if value == local: return copy.deepcopy(exact)
    if isinstance(value, dict): return {k: _exact_target(v, local, exact) for k, v in value.items()}
    if isinstance(value, list): return [_exact_target(v, local, exact) for v in value]
    return value


def _canonical(graph, compiler):
    """Predeclare every late-correction family once, independent of goal events.

    Accepts validated policy graphs, including unregistered/custom node contracts.
    Existing nodes and terminals are never rewritten. Generated name collisions
    fail closed rather than silently granting a different contract.
    """
    result = copy.deepcopy(graph)
    batch_rows = [row for row in result['task_sets']
                  if row['source']['producer'] == {'slot': 'resolution_batches'}]
    result['task_sets'] = [row for row in result['task_sets'] if row not in batch_rows]
    eligible = {}

    def restore_retired(row):
        previous = next((old for old in result['task_sets'] if old['id'] == row['id']), None)
        if previous is not None and previous['source']['producer'] == {'slot': 'retired_resolution_members'}:
            expected = copy.deepcopy(row)
            expected['source'] = retired_source(row)
            if previous != expected:
                raise ValueError('Unsupported modified retired resolution contract')
            result['task_sets'][result['task_sets'].index(previous)] = copy.deepcopy(row)

    def append_family(family):
        for row in family['task_sets']: restore_retired(row)
        # Recompiling a canonical batch graph may restore exactly its removed
        # singular resolver before deriving the same batch definition again.
        missing = [row for row in family['task_sets']
                   if not any(old['id'] == row['id'] for old in result['task_sets'])]
        if batch_rows and len(missing) == 1 and all(
                output['type'] == 'resolution'
                for output in missing[0]['template']['outputs'].values()):
            present = {'nodes': family['nodes'],
                       'task_sets': [row for row in family['task_sets'] if row not in missing]}
            if all(any(old == node for old in result['nodes']) for node in present['nodes']) and all(
                    any(old == row for old in result['task_sets']) for row in present['task_sets']):
                result['task_sets'].extend(copy.deepcopy(missing))
        compiler._append_family(result, family)

    def retain_resolver(family):
        for row in family['task_sets']:
            if all(value['type'] == 'resolution' for value in row['template']['outputs'].values()):
                if any(old == row for old in result['task_sets']):
                    eligible[row['id']] = row

    # Routine rejections use the same fixed policy-time compilation. For custom
    # reviewed policy contracts, infer only one exact independent full subject;
    # names/fingerprints from shipped defaults are not execution authority.
    for review in compiler._definitions(graph):
        for slot, contract in review['outputs'].items():
            decisions = contract.get('schema', {}).get('fields', {}).get('decision', {})
            if contract['type'] != 'review_decision' or 'changes_requested' not in decisions.get('values', []):
                continue
            try:
                scopes, declared = compiler._review_targets(result, review, slot)
            except compiler.RecoveryError as exc:
                if json.loads(str(exc)).get('code') not in {'changed_trusted_review_contract', 'unsupported_correction_target'}:
                    raise
                scopes = []
                for binding in review['inputs'].values():
                    producer = binding.get('producer', {}).get('node')
                    if producer in review['independent_of'] and binding['mode'] == 'identity' and not binding['path']:
                        scope = {'subject': producer, 'output': binding['output']}
                        if scope not in scopes: scopes.append(scope)
                if len(scopes) != 1:
                    raise ValueError('Policy review requires one exact correction target: ' + review['id'])
                declared = False
            for scope in scopes:
                complete, legacy = compiler._route_status(result, review, slot, scope)
                if scope['subject']['kind'] == 'node':
                    key = compiler._route_key(result, review, slot, scope, compiler.SUPPORTED_VERSION)
                    expected = compiler._route_family(result, review, slot, scope, key)
                    expected = _exact_target(expected, {**scope['subject'], 'goal': '#this'}, scope['subject'])
                    if expected['nodes'] and all(node in result['nodes'] for node in expected['nodes']):
                        for row in expected['task_sets']: restore_retired(row)
                        if batch_rows:
                            append_family(expected)
                        retain_resolver(expected)
                        if any(row['id'] in eligible for row in expected['task_sets']):
                            complete = True
                if complete: continue
                if declared:
                    # Preserve the reviewed legacy declaration byte-for-byte,
                    # but append its exact trusted nullable-transfer adapter.
                    # Replacing the old admission would invalidate history;
                    # leaving it as the only route makes repeated corrections
                    # impossible to transfer atomically.
                    if len(legacy) > 1:
                        raise ValueError('Policy correction route has no unique trusted legacy admission: '
                                         + review['id'])
                    if legacy:
                        _validate_static_scope(result, scope, compiler)
                        compiler._append_family(
                            result, compiler._admission_adapter(
                                result, legacy[0], compiler.SUPPORTED_VERSION))
                    continue
                _validate_static_scope(result, scope, compiler)
                if scope['subject']['kind'] != 'node':
                    raise ValueError('Policy member-target correction requires an explicit complete route')
                key = compiler._route_key(result, review, slot, scope, compiler.SUPPORTED_VERSION)
                family = compiler._route_family(result, review, slot, scope, key)
                local = {**scope['subject'], 'goal': '#this'}
                family = _exact_target(family, local, scope['subject'])
                append_family(family)
                retain_resolver(family)
    for target, output in targets(graph):
        name = review_name(target['id'], output)
        target_expansion = next((row['id'] for row in graph['task_sets'] if row['template']['id'] == target['id']), None)
        selector = ({'kind': 'member', 'goal': '#this', 'expansion': target_expansion,
                     'item': {'event_subject_item': True}, 'generation': {'event_subject_generation': True}}
                    if target_expansion else {'kind': 'node', 'goal': '#this', 'node': target['id']})
        source = {'producer': {'slot': 'phase_data'}, 'output': 'content',
                  'path': [target['id'], output], 'mode': 'content', 'type': copy.deepcopy(SELECTION)}
        review = {'id': name, 'prompt': (
            'Independently assess the exact authenticated late event against the current subject. '
            'The event subject is historical diagnostic context, not current authority. '
            'Request changes only for substantiated in-scope defects; approve only after verifying '
            'the current corrected subject. Preserve negative controls and existing allocation.'),
            'inputs': {
                'event': {**copy.deepcopy(source), 'path': [target['id'], output, 'items', {'item_key': True}],
                          'type': copy.deepcopy(EVENT)},
                'subject': {'producer': {'node': selector}, 'output': output, 'path': [],
                            'mode': 'identity', 'type': copy.deepcopy(target['outputs'][output]['schema'])}},
            'outputs': {'value': {'type': 'review_decision', 'schema': {'kind': 'object', 'fields': {
                'decision': {'kind': 'enum', 'values': ['approved', 'changes_requested']},
                'report': {'kind': 'string'}}}}},
            'requires': [copy.deepcopy(selector)], 'independent_of': [copy.deepcopy(selector)],
            'gates': [], 'resolves': [], 'permits': [],
            'executor': {'role': 'worker', 'capability': 'reasoning', 'resources': [],
                         'authority': {'subject': {'kind': 'self'}, 'output': 'value'}}}
        expansion = {'id': name + '_events', 'source': source, 'template': review}
        def append_exact(collection, value):
            previous = next((row for row in collection if row['id'] == value['id']), None)
            if previous is not None and previous != value:
                raise ValueError('Static workflow generated identity collision: ' + value['id'])
            if previous is None: collection.append(value)
        append_exact(result['task_sets'], expansion)
        scope = {'subject': selector, 'output': output}
        key = json.dumps([VERSION, name, scope], sort_keys=True, separators=(',', ':'))
        family = _member_family(result, target, output, review, source, selector, compiler, key)
        for node in family['nodes']:
            # A zero-member late-review join requires no human bookkeeping.
            node['applicability'] = {
                'input': {'producer': {'slot': 'phase_event_presence'}, 'output': 'content',
                          'path': [target['id'], output], 'mode': 'content', 'type': {'kind': 'boolean'}},
                'values': [True], 'outputs': {'value': {'items': {}, 'rationale': 'No late events.'}},
                'rationale': 'No authenticated late events require retention.'}
            append_exact(result['nodes'], node)
        for task_set in family['task_sets']:
            restore_retired(task_set)
            append_exact(result['task_sets'], task_set)
        retain_resolver(family)
    # Reviewed custom correction families are policy contracts, not candidates
    # for the legacy per-goal repair compiler's fingerprint eligibility rules.
    # Preserve their bytes, and supply the universal unresolved-admission route
    # without upgrading or duplicating their declared correction semantics.
    scopes = []
    for node in compiler._definitions(result):
        if any(output['type'] == 'admission' and 'unresolved' in
               output.get('schema', {}).get('fields', {}).get('applicability', {}).get('values', [])
               for output in node['outputs'].values()):
            for permit in node['permits']:
                if permit['type'] == 'admission' and permit['scope'] not in scopes:
                    scopes.append(permit['scope'])
    for scope in sorted(scopes, key=lambda value: json.dumps(value, sort_keys=True)):
        if scope['subject']['kind'] != 'node':
            raise ValueError('Unsupported unresolved member admission scope: the fixed policy '
                             'must require explicit applicable/not_applicable classification because '
                             'member applicability assessment is unsupported; no goal graph repair is permitted')
        _validate_static_scope(result, scope, compiler)
        compiler._append_family(result, compiler._applicability_family(result, scope, compiler.SUPPORTED_VERSION))
    # Older shipped policies declare the same single-finding registry contract
    # under non-generated names. Recognize its exact bounded semantics, never a
    # name/fingerprint wildcard or an arbitrary user correction workflow.
    for row in result['task_sets']:
        node = row['template']
        if row['id'] in eligible or not any(value['type'] == 'resolution' for value in node['outputs'].values()):
            continue
        finding = node['inputs'].get('finding', {})
        producer = finding.get('producer', {}).get('node', {})
        registry = next((candidate for candidate in result['nodes'] if candidate['id'] == producer.get('node')), None)
        if registry is None or registry['outputs'].get(finding.get('output'), {}).get('type') != 'finding_registry':
            source_node = row['source']['producer'].get('node', {}).get('node')
            source_registry = next((candidate for candidate in result['nodes'] if candidate['id'] == source_node), None)
            if (source_registry is not None and source_registry['outputs'].get(row['source']['output'], {}).get('type') == 'finding_registry'
                    or row['source']['producer'] == {'slot': 'retired_resolution_members'}):
                raise ValueError('Unsupported resolution registry finding binding: ' + node['id'])
            continue
        scopes = node['resolves']
        subjects = [scope['subject'] for scope in scopes]
        reference = compiler._ref_type()
        resolution_schema = {'kind': 'object', 'fields': {
            'finding': reference, 'subjects': {'kind': 'array', 'items': reference},
            'reviewer_result': reference, 'decision': {'kind': 'enum', 'values': ['resolved']},
            'rationale': {'kind': 'string'}}}
        supported_outputs = [{'value': {'type': 'resolution', 'schema': copy.deepcopy(resolution_schema)}}]
        resolution_schema['fields']['decision']['values'] = ['resolved', 'unresolved']
        supported_outputs.append({'value': {'type': 'resolution', 'schema': resolution_schema}})
        registry_schema = {'kind': 'object', 'fields': {
            'items': {'kind': 'map', 'values': reference}, 'rationale': {'kind': 'string'}}}
        if (set(node) != {'id', 'prompt', 'inputs', 'outputs', 'requires', 'executor',
                         'independent_of', 'gates', 'resolves', 'permits'}
                or node['outputs'] not in supported_outputs or finding.get('type') != reference
                or registry['outputs'][finding['output']]['schema'] != registry_schema
                or not scopes or any(scope['subject']['kind'] != 'node' for scope in scopes)
                or set(node['outputs']) != {'value'} or node['outputs']['value']['type'] != 'resolution'
                or node['gates'] or node['executor']['capability'] not in ('bounded', 'reasoning')
                or {**node['executor'], 'capability': 'reasoning'} != {'role': 'worker', 'capability': 'reasoning',
                    'resources': [], 'authority': {'subject': {'kind': 'self'}, 'output': 'value'}}
                or sorted(node['independent_of'], key=digest) != sorted(subjects, key=digest)
                or sorted(node['permits'], key=digest) != sorted(
                    [{'type': 'resolution', 'scope': scope} for scope in scopes], key=digest)
                or finding.get('path') != ['items', {'item_key': True}] or finding.get('mode') != 'content'):
            raise ValueError('Unsupported custom resolution batching contract: ' + node['id'])
        for scope in scopes:
            matching = [binding for binding in node['inputs'].values()
                        if binding.get('producer') == {'node': scope['subject']}
                        and binding.get('output') == scope['output'] and binding.get('mode') == 'identity'
                        and binding.get('path') == []]
            if len(matching) != 1:
                raise ValueError('Unsupported resolution subject contract: ' + node['id'])
        for name, binding in node['inputs'].items():
            if name in ('finding', 'review', 'approved', 'approved_reviews'): continue
            if (binding.get('producer', {}).get('node', {}).get('kind') != 'node'
                    or binding.get('mode') != 'identity' or binding.get('path') != []):
                raise ValueError('Unsupported additional resolution input: ' + node['id'] + '/' + name)
        expected_source = {'producer': copy.deepcopy(finding['producer']), 'output': finding['output'],
                           'path': [], 'mode': 'content', 'type': copy.deepcopy(registry['outputs'][finding['output']]['schema'])}
        original = {**copy.deepcopy(row), 'source': expected_source}
        if row['source'] not in (expected_source, retired_source(original)):
            raise ValueError('Unsupported custom resolution registry selection: ' + node['id'])
        review_inputs = {key: value for key, value in node['inputs'].items()
                         if key in ('review', 'approved', 'approved_reviews')}
        if not review_inputs or not any(
                value.get('path') == ['decision'] and value.get('type') == {'kind': 'enum', 'values': ['approved']}
                or value.get('type', {}).get('kind') == 'map'
                and value['type']['values'].get('fields', {}).get('decision') == {'kind': 'enum', 'values': ['approved']}
                for value in review_inputs.values()):
            raise ValueError('Unsupported resolution contract without exact approved review gate: ' + node['id'])
        allowed_dependencies = [producer] + [value['producer']['node'] for value in review_inputs.values()]
        if any(selector not in allowed_dependencies for selector in node['requires']):
            raise ValueError('Unsupported additional resolution prerequisite: ' + node['id'])
        eligible[row['id']] = original
    groups = {}
    for row in eligible.values():
        node = row['template']
        for scope in node['resolves']:
            subject_binding = next(binding for binding in node['inputs'].values()
                if binding.get('producer') == {'node': scope['subject']} and binding.get('output') == scope['output']
                and binding.get('mode') == 'identity' and binding.get('path') == [])
            identity = digest(scope)
            group = groups.setdefault(identity, {'scope': scope, 'subject': subject_binding, 'reviews': {}, 'independent': [], 'bounded': False})
            group['bounded'] = group['bounded'] or node['executor']['capability'] == 'bounded'
            for selector in node['independent_of']:
                if selector not in group['independent']: group['independent'].append(copy.deepcopy(selector))
            if group['subject'] != subject_binding:
                raise ValueError('Unsupported batch correction contracts disagree on exact subject binding')
            for label, binding in node['inputs'].items():
                if label == 'finding' or binding == subject_binding: continue
                binding = copy.deepcopy(binding)
                is_review = label in ('review', 'approved', 'approved_reviews')
                selector = binding['producer'].get('node', {})
                if is_review and selector.get('kind') == 'member' and selector.get('item') == {'item_key': True}:
                    if label == 'approved': continue
                    selector.pop('item'); selector.pop('generation'); selector['kind'] = 'join'
                    approved = copy.deepcopy(binding['type'])
                    approved['fields']['decision'] = {'kind': 'enum', 'values': ['approved']}
                    binding['type'] = {'kind': 'map', 'values': approved}
                group['reviews'][('review_' if is_review else 'context_') + digest(binding)[7:]] = binding
        position = next(index for index, old in enumerate(result['task_sets']) if old['id'] == row['id'])
        result['task_sets'][position] = {**copy.deepcopy(row), 'source': retired_source(row)}
    generated = []
    for identity, group in sorted(groups.items()):
        generated.append(compiler.resolution_batch_family(
            group['scope'], group['subject'], dict(sorted(group['reviews'].items())),
            sorted(group['independent'], key=digest)))
    # Existing reasoning families retain their positions; bounded lanes append
    # after them and can never change their required executor capability.
    for identity, group in sorted(groups.items()):
        if group['bounded']:
            generated.append(compiler.resolution_batch_family(
                group['scope'], group['subject'], dict(sorted(group['reviews'].items())),
                sorted(group['independent'], key=digest), capability='bounded'))
    if batch_rows and sorted(batch_rows, key=lambda row: row['id']) != sorted(generated, key=lambda row: row['id']):
        raise ValueError('Unsupported or altered resolution batch contract; exact policy compiler definition required')
    result['task_sets'].extend(generated)
    return result



def retired_source(row):
    return {'producer': {'slot': 'retired_resolution_members'}, 'output': 'content',
            'path': [row['id']], 'mode': 'content', 'type': copy.deepcopy(row['source']['type'])}


def resolution_batch_adoption(old, new, compiler):
    """Only the exact compiler substitution may adopt lazily; other DAG changes wait."""
    if old == new or old['nodes'] != new['nodes'] or old['terminals'] != new['terminals']:
        return False
    if len(new['task_sets']) < len(old['task_sets']):
        return False
    for before, after in zip(old['task_sets'], new['task_sets']):
        if before == after: continue
        if (before['template'] != after['template'] or
                after != {**before, 'source': retired_source(before)} or
                any(output['type'] != 'resolution' for output in before['template']['outputs'].values())):
            return False
    if any(row['source']['producer'] != {'slot': 'resolution_batches'}
           for row in new['task_sets'][len(old['task_sets']):]):
        return False
    return canonical(old, compiler) == new

def canonical(graph, compiler):
    """Bounded memoized policy compilation; every caller gets detached JSON."""
    source = json.dumps(graph, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    key = (VERSION, compiler.SUPPORTED_VERSION, hashlib.sha256(source).hexdigest())
    with _CACHE_LOCK:
        stored = _CACHE.get(key)
        if stored is not None:
            _CACHE.move_to_end(key)
            return json.loads(stored)
    result = _canonical(graph, compiler)
    encoded = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    if len(encoded) <= _CACHE_BYTES:
        with _CACHE_LOCK:
            _CACHE[key] = encoded
            _CACHE.move_to_end(key)
            while len(_CACHE) > _CACHE_ENTRIES or sum(map(len, _CACHE.values())) > _CACHE_BYTES:
                _CACHE.popitem(last=False)
    return result


def definition(graph, compiler):
    value = canonical(graph, compiler)
    return {'version': VERSION, 'hash': digest(value), 'graph': value}


def event_key(event):
    return 'event_' + digest([event['id'], event['revision']])[7:]


def resolved_goal_context(context, resolutions):
    """Return a detached context with only exact authenticated blockers removed.

    The host authenticates the immutable journal and passes the selected content
    hashes here.  Content identity deliberately avoids inventing IDs for legacy
    blockers; duplicate content therefore cannot be selected unambiguously.
    """
    if (not isinstance(context, dict) or set(context) !=
            {'version', 'depends_on', 'blockers', 'metadata'} or context.get('version') != 1
            or not isinstance(context.get('depends_on'), list)
            or not isinstance(context.get('blockers'), list)
            or not isinstance(context.get('metadata'), dict)):
        raise ValueError('Unsupported or malformed goal context')
    if not isinstance(resolutions, list) or any(
            not isinstance(value, str) or re.fullmatch(r'sha256:[0-9a-f]{64}', value) is None
            for value in resolutions):
        raise ValueError('Malformed goal-context resolution identities')
    if len(resolutions) != len(set(resolutions)):
        raise ValueError('Goal-context blocker cannot be resolved more than once')
    counts = {}
    for blocker in context['blockers']:
        identity = digest(blocker)
        counts[identity] = counts.get(identity, 0) + 1
    if any(counts.get(identity) != 1 for identity in resolutions):
        raise ValueError('Goal-context resolution identifies an unknown or ambiguous blocker')
    selected = set(resolutions)
    result = copy.deepcopy(context)
    result['blockers'] = [blocker for blocker in result['blockers'] if digest(blocker) not in selected]
    return result


def changed_goal_dependencies(context, changes):
    """Project reviewed single-edge changes without rewriting migrated context."""
    if (not isinstance(context, dict) or set(context) !=
            {'version', 'depends_on', 'blockers', 'metadata'} or context.get('version') != 1
            or not isinstance(context.get('depends_on'), list)
            or any(type(value) is not int or value <= 0 for value in context['depends_on'])
            or len(context['depends_on']) != len(set(context['depends_on']))
            or not isinstance(changes, list)):
        raise ValueError('Unsupported or malformed goal dependency context')
    result = copy.deepcopy(context)
    for change in changes:
        if (not isinstance(change, dict) or set(change) != {'old', 'replacement'}
                or type(change['old']) is not int or change['old'] <= 0
                or (change['replacement'] is not None
                    and (type(change['replacement']) is not int or change['replacement'] <= 0))
                or change['replacement'] == change['old']):
            raise ValueError('Goal dependency change has invalid identities')
        dependencies = result['depends_on']
        if dependencies.count(change['old']) != 1:
            raise ValueError('Goal dependency change must select one current edge')
        if change['replacement'] in dependencies:
            raise ValueError('Goal dependency replacement duplicates an existing edge')
        position = dependencies.index(change['old'])
        if change['replacement'] is None:
            del dependencies[position]
        else:
            dependencies[position] = change['replacement']
    return result


def phase_data(events, graph, goal):
    """Project authenticated event contents without dropping historical versions.

    This is structural validation, not authentication: the host must verify every
    source Ref, exact subject revision, actor, scope and journal provenance first.
    """
    if type(goal) is not int or goal <= 0 or not isinstance(events, list):
        raise ValueError('Phase data requires a positive goal and event list')
    result = {}
    for node, output in targets(graph):
        result.setdefault(node['id'], {})[output] = {'items': {}, 'rationale':
            'Authenticated late events for this exact local phase output.'}
    identities = {}
    for event in events:
        if not isinstance(event, dict) or set(event) != set(EVENT['fields']):
            raise ValueError('Malformed phase event fields')
        if (not isinstance(event['id'], str) or not re.fullmatch(r'[A-Za-z0-9_.-]+', event['id'])
                or type(event['revision']) is not int or event['revision'] < 1
                or not isinstance(event['rationale'], str) or not event['rationale'].strip()):
            raise ValueError('Invalid phase event identity/revision/rationale')
        for field in ('source', 'subject'):
            ref = event[field]
            if (not isinstance(ref, dict) or set(ref) != {'hash', 'uri'}
                    or not isinstance(ref['hash'], str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', ref['hash'])
                    or not isinstance(ref['uri'], str) or not ref['uri']):
                raise ValueError('Invalid phase event immutable reference')
        target = event['target']
        if (not isinstance(target, dict) or set(target) not in ({'node', 'output'}, {'node', 'output', 'expansion', 'item', 'generation'})
                or not all(isinstance(target.get(k), str) for k in ('node', 'output'))
                or target['node'] not in result or target['output'] not in result[target['node']]):
            raise ValueError('Unknown or unsupported phase event target')
        expansion = next((row for row in graph['task_sets'] if row['template']['id'] == target['node']), None)
        if expansion is not None:
            if (set(target) != {'node', 'output', 'expansion', 'item', 'generation'}
                    or target['expansion'] != expansion['id']
                    or not isinstance(target['item'], str) or not re.fullmatch(r'[A-Za-z0-9_-]+', target['item'])
                    or type(target['generation']) is not int or target['generation'] < 1):
                raise ValueError('Invalid exact phase event member target')
        elif set(target) != {'node', 'output'}:
            raise ValueError('Static phase event cannot claim a member target')
        key = event_key(event)
        if key in identities and identities[key] != event:
            raise ValueError('Conflicting immutable phase event revision')
        identities[key] = event
        result[target['node']][target['output']]['items'][key] = copy.deepcopy(event)
    return result
