"""Versioned, pure additive compilation of local correction contracts.

This module has no provider or execution dependency. It never accepts Results,
actors, approval flags or caller-selected target graphs. Unknown contracts fail
closed; the executor must separately authorize and guard any persisted delta.
"""
from __future__ import annotations

import copy
import hashlib
import json

SUPPORTED_VERSION = 'correction-graphs-v1'


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def digest(value):
    return 'sha256:' + hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def _localize(value, local_goal):
    if isinstance(value, dict):
        return {key: ('#this' if key == 'goal' and local_goal is not None and item == local_goal
                      else _localize(item, local_goal)) for key, item in value.items()}
    if isinstance(value, list):
        return [_localize(item, local_goal) for item in value]
    return value


def _definitions(graph):
    return graph['nodes'] + [row['template'] for row in graph['task_sets']]


def _selector(name):
    return {'kind': 'node', 'goal': '#this', 'node': name}


def _scope(name, output):
    return {'subject': _selector(name), 'output': output}


def _member(expansion):
    return {'kind': 'member', 'goal': '#this', 'expansion': expansion,
            'item': {'item_key': True}, 'generation': 'current'}


def _join(expansion):
    return {'kind': 'join', 'goal': '#this', 'expansion': expansion}


def _output_slots(node, kind):
    return sorted(slot for slot, value in node['outputs'].items() if value['type'] == kind)


def _fingerprint(graph, node):
    definitions = {value['id']: value for value in _definitions(graph)}
    referenced = {v['producer']['node']['node'] for v in node['inputs'].values()
                  if v.get('producer', {}).get('node', {}).get('kind') == 'node'}
    return digest({'review': node,
                   'subjects': {name: definitions[name]['outputs'] for name in sorted(referenced)},
                   'expansion': [{'id': row['id'], 'source': row['source']}
                                 for row in graph['task_sets'] if row['template']['id'] == node['id']]})[7:]


# Frozen signatures from the reviewed repository default and shipped INIT_PLAN.
# Each binds the ENTIRE review, co-reviewed output contracts and expansion source.
# Never populate this table from an encountered graph, policy, template file or name.
TRUSTED_TARGETS = {
    '875655d2d1f2514001252d9368b44e1fd03c5aa71a5bd5c58e64931b5837e5ff': ('review_understanding', 'review', 'understand', 'design'),
    '83c160d8c743d9ae723f5393fe0efccab4fb441a5d998dd50c370abf3eaab071': ('review_decomposition', 'value', 'decompose', 'value'),
    '7c6b3c41d2e7fd712411e346100819fbaf7901757dd10e86457632ecfc87106e': ('review_test_design', 'value', 'test_design', 'value'),
    '9248178a501de110b8901fd0020dcc927ca1946ea5ab42f570368b6406772de7': ('review_implement', 'value', 'implement', 'value'),
    '666d956ffeac3bcb52ca29645de2f8d44a0267fc144d01776276f4cace6a0cb1': ('review_publication_context', 'value', 'publication_context', 'value'),
    'df14c301d1c91dc6eacbd8f02c0918517bdd209f0b63cc1e47a5c6ae3094b3ef': ('review_publication', 'value', 'observe_publication', 'value'),
    '53725c9bfc030c50cb538bf2b9771a74a8b669e9357539a23badda6e753e4e59': ('decomposition_review', 'value', 'decompose', 'value'),
    '5a2867043dd59ab65cbbc1d60df1236a447c35d2418b5689c349588839340c2a': ('test_design_review', 'value', 'test_design', 'value'),
    'bb40fd377fa0afb1c1b28685c6a2a4ef3a17048fcd2fe80052af7955ebfc28f8': ('migration_review', 'value', 'migration_verification', 'value'),
    '319b8ffedf157d8658b21897aa5ebef4eccbed0d710d3bca4e914efd114c4dc9': ('integration_feedback_review', 'value', 'integrate', 'value'),
    'cbf1212fcb0a5a859619ea278ed2a235924a37eb9a9101f50dee38d5124716d7': ('spec_review', 'value', 'spec', 'value'),
    'e1632ccea3daf6bb4d19f65f8dc85a7e008e53db9fda33218e2262108c14de41': ('implementation_review', 'value', 'implement', 'value'),
    '324a7def53d0ba5bc8a22e39212cdf4ee48140a410c0028b5c34a75e09402a3a': ('integration_review', 'value', 'integration_verification', 'value'),
}


class RecoveryError(ValueError):
    """A graph needs reviewed recovery rather than canonical maintenance."""


def _fail(code, **context):
    raise RecoveryError(canonical({'code': code, **context}))


def _permit(node, kind, scope):
    return {'type': kind, 'scope': scope} in node.get('permits', [])


def _binding(node, selector, output, path, mode):
    return [value for value in node.get('inputs', {}).values()
            if value.get('producer') == {'node': selector} and value.get('output') == output
            and value.get('path') == path and value.get('mode') == mode]


def _predicate(node, selector, output, decision):
    for value in _binding(node, selector, output, ['decision'], 'content'):
        schema = value.get('type', {})
        if selector.get('kind') == 'join':
            schema = schema.get('values', {}) if schema.get('kind') == 'map' else {}
        if schema == {'kind': 'enum', 'values': [decision]}:
            return True
    # A joined approved-content-constrained identity binding also enforces the predicate.
    for value in _binding(node, selector, output, [], 'identity'):
        schema = value.get('type', {})
        if selector.get('kind') == 'join':
            schema = schema.get('values', {}) if schema.get('kind') == 'map' else {}
        if schema.get('fields', {}).get('decision') == {'kind': 'enum', 'values': [decision]}:
            return True
    return False


def _atomic(node, scope):
    return (_permit(node, 'supersession', scope) and
            any(value['type'] == 'supersession' and value['schema'] == _transfer_type()
                for value in node['outputs'].values()))


def _ref_type():
    return {'kind': 'object', 'fields': {'hash': {'kind': 'string'}, 'uri': {'kind': 'string'}}}


def _transfer_type():
    return {'kind': 'union', 'variants': [{'kind': 'null'}, {'kind': 'object', 'fields': {
        'prior': _ref_type(), 'replacement': _ref_type(),
        'coverage': {'kind': 'enum', 'values': ['carried', 'narrowed']},
        'coverage_evidence': _ref_type(), 'authority': _ref_type()}}]}
def _append_static( graph, target_name, target_output, review_name, review_output,
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

def _upgrade_admission(node):
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

def _expansion_for(graph, name):
    return next((row for row in graph['task_sets'] if row['template']['id'] == name), None)


def _producer(graph, node):
    expansion = _expansion_for(graph, node['id'])
    return _member(expansion['id']) if expansion else _selector(node['id'])


def _same_expansion_source(graph, node, review_expansion):
    expansion = _expansion_for(graph, node['id'])
    if review_expansion is None:
        return expansion is None
    return expansion is not None and expansion['source'] == review_expansion['source']


def _subject_bound(node, scope, graph):
    selector = scope['subject']
    if selector.get('goal') != '#this':
        return False
    if selector.get('kind') == 'node':
        target = next((row for row in graph['nodes'] if row['id'] == selector.get('node')), None)
    elif selector.get('kind') == 'member':
        expansion = next((row for row in graph['task_sets'] if row['id'] == selector.get('expansion')), None)
        target = expansion['template'] if expansion else None
    else:
        return False
    if target is None or scope['output'] not in target['outputs']:
        return False
    schema = target['outputs'][scope['output']]['schema']
    return any(value.get('type') == schema for value in
               _binding(node, scope['subject'], scope['output'], [], 'identity'))


def _safe_root(node):
    return (node['executor']['role'] == 'root' and not node['executor']['resources'] and
            not node['gates'] and not node['resolves'])


def _approved_links(graph, registry, review, review_output, scope):
    candidates = [(review, review_output)]
    # Existing custom routes may resolve an accepted-test defect against a fresh
    # independent test review instead of the implementation review that found it.
    # This recognizes an already-declared chain; it grants no synthesis target.
    for node in _definitions(graph):
        if scope['subject'] in node['independent_of'] and _subject_bound(node, scope, graph):
            candidates.extend((node, slot) for slot in _output_slots(node, 'review_decision'))
    links = []
    for node, slot in candidates:
        expansion = _expansion_for(graph, node['id'])
        selector = _join(expansion['id']) if expansion else _selector(node['id'])
        if _predicate(registry, selector, slot, 'approved') and (selector, slot) not in links:
            links.append((selector, slot))
    return links


def _route_status(graph, review, review_output, scope):
    """Exact route recognition; returns (complete, legacy admission candidates).

    Bind every output and member selector, including expansion source/key/generation.
    A same-named producer, a predicate-less decision, or another output is not evidence.
    """
    definitions = _definitions(graph)
    review_expansion = _expansion_for(graph, review['id'])
    review_selector = _producer(graph, review)
    approved_selector = _join(review_expansion['id']) if review_expansion else review_selector
    legacy = []
    for finding in definitions:
        if not (_output_slots(finding, 'finding') and _permit(finding, 'finding', scope)
                and _safe_root(finding) and _subject_bound(finding, scope, graph)
                and _same_expansion_source(graph, finding, review_expansion)
                and _predicate(finding, review_selector, review_output, 'changes_requested')
                and any(value.get('type') == review['outputs'][review_output]['schema']
                        for value in _binding(finding, review_selector, review_output, [], 'identity'))):
            continue
        finding_selector = _producer(graph, finding)
        admissions = [node for node in definitions
                      if _output_slots(node, 'admission') and _permit(node, 'admission', scope)
                      and _safe_root(node) and _subject_bound(node, scope, graph)
                      and _same_expansion_source(graph, node, review_expansion)
                      and any(value.get('type') == finding['outputs'][slot]['schema']
                              for slot in _output_slots(finding, 'finding')
                              for value in _binding(node, finding_selector, slot, [], 'identity'))]
        for registry in graph['nodes']:
            if not (_output_slots(registry, 'finding_registry') and _safe_root(registry)
                    and _permit(registry, 'finding_registry', scope)
                    and _approved_links(graph, registry, review, review_output, scope)):
                continue
            registry_selector = _selector(registry['id'])
            for slot in _output_slots(registry, 'finding_registry'):
                for expansion in graph['task_sets']:
                    resolver = expansion['template']
                    source = expansion['source']
                    if not (source == {'producer': {'node': registry_selector}, 'output': slot,
                            'path': [], 'mode': 'content', 'type': registry['outputs'][slot]['schema']}
                            and _output_slots(resolver, 'resolution')
                            and resolver['executor']['role'] == 'worker'
                            and not resolver['executor']['resources']
                            and _permit(resolver, 'resolution', scope)
                            and scope in resolver['resolves']
                            and scope['subject'] in resolver['independent_of']
                            and _subject_bound(resolver, scope, graph)
                            and _binding(resolver, registry_selector, slot,
                                         ['items', {'item_key': True}], 'content')
                            and any(_predicate(resolver, sel, slot_name, 'approved')
                                    for sel, slot_name in _approved_links(graph, registry, review, review_output, scope))):
                        continue
                    if any(_atomic(node, scope) for node in admissions):
                        return True, []
                    legacy.extend(admissions)
    return False, legacy


def correction_route_covers(graph, target_name, target_output, review_name, review_output,
                            local_goal=None):
    """Shared pure exact matcher for the runtime frontier; no inference of output slots."""
    graph = _localize(graph, local_goal)
    review = next((node for node in _definitions(graph) if node['id'] == review_name), None)
    return bool(review and _route_status(graph, review, review_output,
                                        _scope(target_name, target_output))[0])


def _rename(value, mapping):
    if isinstance(value, dict):
        return {key: (mapping.get(item, item) if key in ('node', 'id', 'expansion') and isinstance(item, str)
                      else _rename(item, mapping)) for key, item in value.items()}
    if isinstance(value, list):
        return [_rename(item, mapping) for item in value]
    return value


def _route_key(graph, review, review_output, scope, version):
    expansion = _expansion_for(graph, review['id'])
    return [version, _producer(graph, review),
            {'id': expansion['id'], 'source': expansion['source']} if expansion else None,
            review_output, scope['subject'], scope['output']]


def _name(role, key):
    return 'gc_' + role + '_' + digest(key)[7:]


def _route_family(graph, review, review_output, scope, key):
    target = next(node for node in graph['nodes'] if node['id'] == scope['subject']['node'])
    temporary = {'nodes': [copy.deepcopy(target), copy.deepcopy(review)], 'task_sets': [], 'terminals': []}
    _append_static(temporary, target['id'], scope['output'], review['id'], review_output)
    added = {'nodes': temporary['nodes'][2:], 'task_sets': temporary['task_sets']}
    role_names = ['interpret', 'admit', 'retain']
    mapping = {node['id']: _name(role, key) for role, node in zip(role_names, added['nodes'])}
    mapping[added['task_sets'][0]['id']] = _name('findings', key)
    mapping[added['task_sets'][0]['template']['id']] = _name('resolve', key)
    added = _rename(added, mapping)
    metadata = _graph_metadata(graph)
    expansion = _expansion_for(graph, review['id'])
    if expansion is None:
        return _preserve_metadata(added, metadata)
    # Static target, configured member reviewers: member interpretation/admission,
    # static all-approved join retention, then retained-finding resolver expansion.
    interpreter, admission, retention = added['nodes']
    interpretation_set = _name('interpret_members', key)
    admission_set = _name('admit_members', key)
    review_selector = _selector(review['id'])
    interpreter_selector = _selector(interpreter['id'])
    def memberize(value):
        if value == review_selector:
            return _member(expansion['id'])
        if value == interpreter_selector:
            return _member(interpretation_set)
        if isinstance(value, dict):
            return {k: memberize(v) for k, v in value.items()}
        if isinstance(value, list):
            return [memberize(v) for v in value]
        return value
    interpreter, admission = memberize(interpreter), memberize(admission)
    for node in (interpreter, admission):
        node['executor']['authority']['subject'] = {'kind': 'self'}
    approved_type = copy.deepcopy(review['outputs'][review_output]['schema'])
    approved_type['fields']['decision'] = {'kind': 'enum', 'values': ['approved']}
    joined = {'producer': {'node': _join(expansion['id'])}, 'output': review_output,
              'path': [], 'mode': 'identity', 'type': {'kind': 'map', 'values': approved_type}}
    for node in (retention, added['task_sets'][0]['template']):
        node['inputs'].pop('review', None)
        node['inputs'].pop('approved', None)
        node['inputs']['approved_reviews'] = copy.deepcopy(joined)
        node['requires'] = [_join(expansion['id']) if selector == review_selector else selector
                            for selector in node['requires']]
    added['nodes'] = [retention]
    added['task_sets'] = [
        {'id': interpretation_set, 'source': copy.deepcopy(expansion['source']), 'template': interpreter},
        {'id': admission_set, 'source': copy.deepcopy(expansion['source']), 'template': admission},
        *added['task_sets']]
    return _preserve_metadata(added, metadata)


def _applicability_family(graph, scope, version):
    target = next(node for node in graph['nodes'] if node['id'] == scope['subject']['node'])
    output = scope['output']
    # Contract-derived identities stay constant across findings, revisions and Results.
    key = [version, 'applicability', scope, target['outputs'][output]]
    metadata = _graph_metadata(graph)
    if metadata:
        key.append(metadata)
    names = {role: _name(role, key) for role in ('observation', 'context', 'assessment')}
    sets = {role: _name(role + '_members', key) for role in names}
    target_shape = {'kind': 'object', 'fields': {
        'subject': {'kind': 'object', 'fields': {'kind': {'kind': 'string'},
                    'goal': {'kind': 'integer'}, 'node': {'kind': 'string'}}},
        'output': {'kind': 'string'}}}
    obligation = {'kind': 'object', 'fields': {'admission': _ref_type(), 'finding': _ref_type(),
        'target': target_shape, 'applicability': {'kind': 'enum',
        'values': ['applicable', 'not_applicable', 'unresolved']}}}
    selection = {'kind': 'object', 'fields': {'items': {'kind': 'map', 'values': obligation},
                                            'rationale': {'kind': 'string'}}}
    source = {'producer': {'slot': 'obligation_selections'}, 'output': 'content',
              'path': [target['id'], output], 'mode': 'content', 'type': selection}
    obligation_input = {'producer': {'slot': 'obligations'}, 'output': 'content',
                        'path': [{'item_key': True}], 'mode': 'content', 'type': obligation}
    subject_input = {'producer': {'slot': 'obligation_subject'}, 'output': 'content',
                     'path': [{'item_key': True}],
                     'mode': 'identity', 'type': copy.deepcopy(target['outputs'][output]['schema'])}
    assessment = {'kind': 'object', 'fields': {
        'admission': _ref_type(), 'finding': _ref_type(),
        'subjects': {'kind': 'array', 'items': _ref_type()}, 'reviewer_result': _ref_type(),
        'authority': _ref_type(), 'applicability': {'kind': 'enum', 'values': ['applicable', 'not_applicable']},
        'rationale': {'kind': 'string'}}}
    rows = []
    for role in ('observation', 'context', 'assessment'):
        node = {'id': names[role],
            'prompt': {'observation': 'Independently inspect this exact unresolved obligation and its exact admitted historical subject; report applicability evidence without classifying or resolving it.',
                       'context': 'Root supplies current bounded applicability context for this exact obligation and independent observation; do not grant workspace or source authority.',
                       'assessment': 'Root explicitly classifies this exact admission and finding revision using its exact admitted historical subject, independent observation Result and root context Result. Classification never resolves finding debt.'}[role],
            'inputs': {'obligation': copy.deepcopy(obligation_input), 'subject': copy.deepcopy(subject_input)},
            'outputs': {'value': {'type': 'applicability_assessment' if role == 'assessment' else 'text',
                                 'schema': copy.deepcopy(assessment) if role == 'assessment' else {'kind': 'string'}}},
            'requires': [],
            'executor': {'role': 'worker' if role == 'observation' else 'root',
                         'capability': 'reasoning' if role == 'observation' else 'bounded',
                         'resources': [], 'authority': {'subject': {'kind': 'self'}, 'output': 'value'}},
            'independent_of': [copy.deepcopy(scope['subject'])] if role == 'observation' else [],
            'gates': [], 'resolves': [], 'permits': []}
        for dependency in ([] if role == 'observation' else ['observation'] if role == 'context'
                           else ['observation', 'context']):
            selector = _member(sets[dependency])
            node['inputs'][dependency] = {'producer': {'node': selector}, 'output': 'value',
                                         'path': [], 'mode': 'identity', 'type': {'kind': 'string'}}
            node['requires'].append(selector)
        if role == 'assessment':
            node['permits'] = [{'type': 'applicability_assessment', 'scope': copy.deepcopy(scope)}]
        rows.append({'id': sets[role], 'source': copy.deepcopy(source), 'template': node})
    return _preserve_metadata({'nodes': [], 'task_sets': rows}, metadata)


def applicability_family_covers(graph, target_name, target_output, local_goal=None,
                                compiler_version=SUPPORTED_VERSION):
    """Verify the whole canonical family, not merely a permit or a suffix."""
    normalized = _localize(graph, local_goal)
    try:
        family = _applicability_family(normalized, _scope(target_name, target_output), compiler_version)
        return all(row in normalized['task_sets'] for row in family['task_sets'])
    except (KeyError, StopIteration):
        return False


# Versioned admission upgrade adapters. Each hash binds the complete old node and
# its enclosing expansion source, when present. Filled with literal reviewed
# historical contracts below; there is no name/suffix-based admission authority.
LEGACY_ADMISSIONS = frozenset({
    'sha256:008bdb826c84425029e94f19b539776ca9e3744a2a93729ffd8ca64024cccd0e',  # admit_decomposition_correction
    'sha256:01f41b2e75f585c1e57ef7d88aa479b3a384b533fe059b9c71d8db8ec30bc23b',  # admit_migration_correction
    'sha256:07ce1204d6fec372a845216c678040473f6d6a738bbde9a9967c90fcefd8154f',  # admit_spec_review_correction
    'sha256:127521bf55e17c92f050c34dfad7d72ee379871e408db3f8a192b2a422bc8fee',  # admit_integration_feedback_correction
    'sha256:147b1b233b77c26cfa38aac00ee65aec8cef1527ebaecac6baa47a5c76290789',  # admit_integration_review_correction
    'sha256:1812b78e4893da858488721b60993197c5d4b0d67534f0bcc848d3513b13c1e9',  # admit_implement_correction
    'sha256:1acd551936221b90c31da21523889e6011e9be610accc7e65fd6f26b3415f377',  # admit_test_design_correction
    'sha256:4c001569fb61761f8fd194b26966df408694e33ba2027c387a0bb44ce64ee891',  # admit_implementation_review_correction
    'sha256:4c27734c88c3099398b6ed2c8104deb799c5a5e2b1f3cc4445067ba7c3db1e68',  # admit_spec_review_correction
    'sha256:53879900da8eb5813403b302903a674c56b9aec3e0a0f119b83a8dbd1d9f6427',  # admit_test_design_correction
    'sha256:6a15e97c666ab318bb1023943905bfdf3885c7336e472c3bfeac8d7984ebf463',  # admit_publication_context_correction
    'sha256:6bc21e1085f9c249ce7f28bcd4270734f03caa8162b60b24d497bb2b3ea7c0c2',  # admit_integration_review_correction
    'sha256:6c22a9d51c5f57ad6f63b2fdae4d66eaecbdd475ecb83b9db35f6c2eef7cb34f',  # admit_decomposition_correction
    'sha256:70bb3779a1be95950ee20ee83a2c060fa95ac0b836db42c0e62362adb37806f1',  # admit_observe_publication_correction
    'sha256:731544741f81add784cd093eee631dd333767db087e4dc68798b8e0434aadf5b',  # admit_implementation_review_correction
    'sha256:b2f2b27403317f4c02146f7793ff9271731c1ad3f1afa4dae5aea2721a71ee60',  # admit_decompose_correction
    'sha256:b78dd801b53f377d7f642a0707a65bb37a6f0584faf9c9dd59ce1b556e56008e',  # admit_accepted_test_correction
    'sha256:ebf77f74cf8e3f033045c58250f410fee88fcb4fb666846bc17039688c9391e7',  # admit_understand_correction
    'sha256:eda2abb03d942e7e7a7888979a97c339894d0012715c32426556b6ea971f13df',  # admit_integration_feedback_correction
    'sha256:f19d269db2ffbba7f7125b70becbb26c279c200255cd0180371c95a321b07675',  # admit_migration_correction
    'sha256:f7def792185edd72050ac21117bcdd9f3e32f4aa08b300d9f2e83f659896f499',  # admit_test_design_correction
})


def _admission_signature(graph, node):
    expansion = _expansion_for(graph, node['id'])
    return digest({'node': node, 'expansion': {'id': expansion['id'], 'source': expansion['source']}
                   if expansion else None})


# Versioned restrictive metadata grammar emitted by the lossless converter.
# These literals never derive trust from the installed template or user policy.
_METADATA_TIERS = ('bounded', 'reasoning', 'architectural')
_METADATA_RISKS = frozenset(('authentication', 'authorization', 'payments', 'secrets',
    'destructive_data_migrations', 'security_sensitive', 'throwaway_prototypes', 'architecture'))
_METADATA_PREFIX = '\nPreserved engineering requirement: effective rigor '
_METADATA_END = '. Apply the reviewed engineering-rigor policy to this work.'


def _mapped_metadata(node):
    prompt = node.get('prompt', '')
    if prompt.count(_METADATA_PREFIX) != 1 or not prompt.endswith(_METADATA_END):
        return None
    original, suffix = prompt.split(_METADATA_PREFIX)
    fields = suffix[:-len(_METADATA_END)].split('; risks ')
    if len(fields) != 2 or fields[0] not in ('vibe', 'structured', 'agentic'):
        return None
    risks = fields[1].split(', ') if fields[1] else []
    if len(risks) != len(set(risks)) or any(risk not in _METADATA_RISKS for risk in risks):
        return None
    tier = node.get('executor', {}).get('capability')
    if tier not in _METADATA_TIERS:
        return None
    return {'prompt': original, 'suffix': _METADATA_PREFIX + suffix, 'tier': tier}


def _trusted_admission(graph, node):
    if _admission_signature(graph, node) in LEGACY_ADMISSIONS:
        return True
    metadata = _mapped_metadata(node)
    if metadata is None:
        return False
    recovered = copy.deepcopy(node)
    recovered['prompt'] = metadata['prompt']
    for predecessor in _METADATA_TIERS[:_METADATA_TIERS.index(metadata['tier']) + 1]:
        recovered['executor']['capability'] = predecessor
        if _admission_signature(graph, recovered) in LEGACY_ADMISSIONS:
            return True
    return False


def _graph_metadata(graph):
    definitions = _definitions(graph)
    sources = set()
    def subject(selector):
        if selector.get('goal') != '#this':
            return
        if selector.get('kind') == 'node':
            sources.add(selector.get('node'))
        elif selector.get('kind') == 'member':
            expansion = next((row for row in graph['task_sets']
                              if row['id'] == selector.get('expansion')), None)
            if expansion:
                sources.add(expansion['template']['id'])
    for node in definitions:
        rejectable = any(output.get('type') == 'review_decision' and 'changes_requested' in
            output.get('schema', {}).get('fields', {}).get('decision', {}).get('values', [])
            for output in node['outputs'].values())
        if rejectable:
            sources.add(node['id'])
            for binding in node['inputs'].values():
                selector = binding.get('producer', {}).get('node', {})
                if (selector in node['independent_of'] and binding.get('mode') == 'identity'
                        and binding.get('path') == []):
                    subject(selector)
        for permit in node['permits']:
            if permit['type'] == 'admission':
                subject(permit['scope']['subject'])
        if _trusted_admission(graph, node):
            sources.add(node['id'])
    # Source reviews and correction subjects are invariant under compilation:
    # helpers produce no review_decision and introduce no new correction target.
    # Frozen legacy admissions also retain the converter's unknown-phase floor.
    # A generated helper's per-role minimum must never become a source floor.
    rows = [_mapped_metadata(node) for node in definitions if node['id'] in sources]
    rows = [row for row in rows if row is not None]
    if not rows:
        return None
    suffixes = {row['suffix'] for row in rows}
    if len(suffixes) != 1:
        _fail('inconsistent_mapped_engineering_requirements')
    return {'suffix': rows[0]['suffix'],
            'tier': max((row['tier'] for row in rows), key=_METADATA_TIERS.index)}


def _preserve_metadata(family, metadata):
    if metadata:
        for node in _definitions(family):
            node['prompt'] += metadata['suffix']
            node['executor']['capability'] = max(
                (node['executor']['capability'], metadata['tier']), key=_METADATA_TIERS.index)
    return family


def _admission_adapter(graph, node, version):
    if not _trusted_admission(graph, node):
        _fail('unsupported_partial_correction_route', admission=node['id'])
    expansion = _expansion_for(graph, node['id'])
    key = [version, 'nullable_atomic_admission', _admission_signature(graph, node)]
    upgraded = copy.deepcopy(node)
    upgraded['id'] = _name('atomic_admit', key)
    _upgrade_admission(upgraded)
    if upgraded['executor']['authority']['subject'] == _selector(node['id']):
        upgraded['executor']['authority']['subject'] = _selector(upgraded['id'])
    if expansion:
        return {'nodes': [], 'task_sets': [{'id': _name('atomic_members', key),
                  'source': copy.deepcopy(expansion['source']), 'template': upgraded}]}
    return {'nodes': [upgraded], 'task_sets': []}


def admission_shadowed(graph, node_name, local_goal=None, compiler_version=SUPPORTED_VERSION):
    """Runtime may shadow a legacy admission only with its exact v1 counterpart."""
    graph = _localize(graph, local_goal)
    node = next((row for row in _definitions(graph) if row['id'] == node_name), None)
    if node is None or not _trusted_admission(graph, node):
        return False
    family = _admission_adapter(graph, node, compiler_version)
    if all(row in graph[kind] for kind in ('nodes', 'task_sets') for row in family[kind]):
        return True
    # Historical reviewed recovery used this literal member identity. Trust is
    # still the frozen predecessor fingerprint plus the complete exact upgrade,
    # including its source, predicates, authority and nullable transfer contract.
    expansion = _expansion_for(graph, node_name)
    if expansion is None:
        return False
    historical = copy.deepcopy(expansion)
    historical['id'] += '_atomic_transfer'
    historical['template']['id'] += '_atomic_transfer'
    _upgrade_admission(historical['template'])
    return historical in graph['task_sets']


def _append_family(graph, family):
    occupied = {node['id']: node for node in graph['nodes']}
    for row in graph['task_sets']:
        occupied[row['id']] = row
        occupied[row['template']['id']] = row['template']
    expected = [(node['id'], node) for node in family['nodes']]
    for row in family['task_sets']:
        expected.extend([(row['id'], row), (row['template']['id'], row['template'])])
    present = [name in occupied for name, _ in expected]
    for name, value in expected:
        if name in occupied and occupied[name] != value:
            _fail('occupied_correction_identity', identity=name)
    if all(present):
        return False
    if any(present):
        _fail('partial_generated_correction_contract', identities=[name for name, _ in expected])
    graph['nodes'].extend(copy.deepcopy(family['nodes']))
    graph['task_sets'].extend(copy.deepcopy(family['task_sets']))
    return True


def _validate_scope(graph, scope):
    selector = scope.get('subject', {})
    if selector.get('kind') != 'node' or selector.get('goal') != '#this':
        _fail('unsupported_correction_target', target=scope)
    target = next((node for node in graph['nodes'] if node['id'] == selector.get('node')), None)
    if target is None or scope.get('output') not in target['outputs']:
        _fail('unknown_correction_target_output', target=scope)


def _review_targets(graph, review, review_output):
    selector = _producer(graph, review)
    declared = []
    related = []
    for node in _definitions(graph):
        if not _output_slots(node, 'finding'):
            continue
        # A wrong slot/key/generation is not a missing route that may be silently
        # replaced. It is an existing custom contract requiring explicit review.
        for value in node['inputs'].values():
            producer = value.get('producer', {}).get('node', {})
            same_identity = (producer.get('node') == selector.get('node') if selector['kind'] == 'node'
                             else producer.get('expansion') == selector.get('expansion'))
            if (same_identity and value.get('path') == ['decision']
                    and 'changes_requested' in value.get('type', {}).get('values', [])):
                bound_output = value.get('output')
                if bound_output != review_output:
                    other = review['outputs'].get(bound_output, {})
                    decision = other.get('schema', {}).get('fields', {}).get('decision', {})
                    if (producer == selector and other.get('type') == 'review_decision'
                            and decision.get('kind') == 'enum'
                            and {'approved', 'changes_requested'} <= set(decision.get('values', []))):
                        # A different declared rejectable output owns a different
                        # route tuple. It is not this output's partial route.
                        continue
                related.append(node)
                if not _predicate(node, selector, review_output, 'changes_requested'):
                    _fail('mismatched_review_binding', review=review['id'], finding=node['id'])
        if _predicate(node, selector, review_output, 'changes_requested'):
            for permit in node['permits']:
                if permit['type'] == 'finding' and permit['scope'] not in declared:
                    declared.append(permit['scope'])
    if declared:
        # Complete existing member-target routes are checked with their exact
        # selectors before deciding whether synthesis is supported.
        return sorted(declared, key=canonical), True
    if related:
        _fail('partial_custom_correction_route', review=review['id'])
    signature = _fingerprint(graph, review)
    rule = TRUSTED_TARGETS.get(signature)
    if rule:
        if (review['id'], review_output) != rule[:2]:
            _fail('trusted_review_output_mismatch', review=review['id'], output=review_output)
        return [_scope(rule[2], rule[3])], False
    if review['id'] in {row[0] for row in TRUSTED_TARGETS.values()}:
        _fail('changed_trusted_review_contract', review=review['id'])
    targets = []
    for value in review['inputs'].values():
        producer = value.get('producer', {}).get('node')
        if (producer in review['independent_of'] and value.get('mode') == 'identity'
                and value.get('path') == []):
            scope = {'subject': producer, 'output': value['output']}
            _validate_scope(graph, scope)
            if scope not in targets:
                targets.append(scope)
    if len(targets) != 1:
        _fail('ambiguous_review_target', review=review['id'], output=review_output, targets=targets)
    return targets, False


def _compile(graph, local_goal, version):
    working = _localize(copy.deepcopy(graph), local_goal)
    if set(working) != {'nodes', 'task_sets', 'terminals'}:
        _fail('unsupported_graph_contract')
    definitions = _definitions(working)
    identities = [node['id'] for node in definitions] + [row['id'] for row in working['task_sets']]
    if len(identities) != len(set(identities)):
        _fail('occupied_graph_identity')
    pending, changes = [], []
    for review in definitions:
        for slot, output in sorted(review['outputs'].items()):
            decision = output.get('schema', {}).get('fields', {}).get('decision', {})
            if output['type'] != 'review_decision' or 'changes_requested' not in decision.get('values', []):
                continue
            if decision.get('kind') != 'enum' or 'approved' not in decision.get('values', []):
                _fail('unsupported_review_decision_contract', review=review['id'], output=slot)
            scopes, declared = _review_targets(working, review, slot)
            for scope in scopes:
                key = _route_key(working, review, slot, scope, version)
                pending.append((canonical(key), key, review, slot, scope, declared))
    for _, key, review, slot, scope, declared in sorted(pending, key=lambda row: row[0]):
        complete, legacy = _route_status(working, review, slot, scope)
        if complete:
            continue
        if declared:
            _validate_scope(working, scope)
            if len(legacy) != 1:
                _fail('incomplete_custom_correction_route', review=review['id'], output=slot, target=scope)
            family = _admission_adapter(working, legacy[0], version)
        else:
            family = _route_family(working, review, slot, scope, key)
        if _append_family(working, family):
            changes.append({'key': canonical(key), 'kind': 'correction', 'review': review['id'],
                            'review_output': slot, 'target': scope})
        if not _route_status(working, review, slot, scope)[0]:
            _fail('incomplete_generated_correction_route', review=review['id'], target=scope)
    # Every unresolved-capable declared admission needs a per-target assessment
    # family, including existing admissions that did not originate in a review.
    scopes = []
    for node in _definitions(working):
        unresolved = any(output['type'] == 'admission' and 'unresolved' in
                         output['schema'].get('fields', {}).get('applicability', {}).get('values', [])
                         for output in node['outputs'].values())
        if unresolved:
            for permit in node['permits']:
                if permit['type'] == 'admission':
                    scope = permit['scope']
                    _validate_scope(working, scope)
                    if scope not in scopes:
                        scopes.append(scope)
    for scope in sorted(scopes, key=canonical):
        family = _applicability_family(working, scope, version)
        if _append_family(working, family):
            changes.append({'key': canonical([version, 'applicability', scope]), 'kind': 'applicability', 'target': scope})
    # Preserve caller bytes/order/aliases in every old declaration. Only appended
    # contracts use canonical #this selectors.
    result = copy.deepcopy(graph)
    result['nodes'].extend(working['nodes'][len(graph['nodes']):])
    result['task_sets'].extend(working['task_sets'][len(graph['task_sets']):])
    return result, changes


def compile_graph(graph, local_goal=None, compiler_version=None):
    """Return an all-or-nothing deterministic delta and precise eligibility diagnostics.

    None means the installed version at invocation time. Explicit historical
    versions are never silently translated into the currently installed compiler.
    """
    version = SUPPORTED_VERSION if compiler_version is None else compiler_version
    if version != SUPPORTED_VERSION:
        raise RecoveryError('Unsupported correction compiler version: ' + str(version))
    original = copy.deepcopy(graph)
    diagnostics = []
    try:
        target, routes = _compile(original, local_goal, version)
    except RecoveryError as exc:
        try:
            diagnostic = json.loads(str(exc))
        except ValueError:
            diagnostic = {'code': 'unsupported_correction_contract', 'detail': str(exc)}
        diagnostics.append(diagnostic)
        target, routes = original, []
    except (KeyError, TypeError, StopIteration, IndexError) as exc:
        diagnostics.append({'code': 'malformed_correction_contract', 'detail': str(exc)})
        target, routes = original, []
    return {'graph': target, 'source_hash': digest(original), 'target_hash': digest(target),
            'version': version, 'routes': routes, 'diagnostics': sorted(diagnostics, key=canonical)}


def validate_recovery(graph, local_goal=None, compiler_version=None):
    """Explicit execution/publication boundary check, not historical grammar loading."""
    result = compile_graph(graph, local_goal, compiler_version)
    if result['diagnostics']:
        raise RecoveryError('Correction route recovery contract: ' + canonical(result['diagnostics']))
    if result['graph'] != graph:
        raise RecoveryError('Correction route recovery incomplete: canonical additions required')


def resolution_batch_family(scope, subject_binding, reviews, independent, capability="reasoning"):
    """One policy-time resolver family; membership remains authenticated host data.

    ``reviews`` retains every exact approved route input. No reviewer is chosen
    by the worker, by a convenient finding, or by a naming convention.
    """
    identity = ['resolution-batch-v1', scope, subject_binding, reviews, independent]
    if capability != 'reasoning': identity.append(capability)
    key = digest(identity)[7:]
    name, expansion = 'gc_resolve_batch_' + key, 'gc_resolution_batches_' + key
    ref = _ref_type()
    entry = {'kind': 'object', 'fields': {
        'finding': copy.deepcopy(ref), 'admission': copy.deepcopy(ref),
        'id': {'kind': 'string'}, 'revision': {'kind': 'integer'},
        'reviews': {'kind': 'array', 'items': copy.deepcopy(ref)}}}
    target_schema = {'kind': 'union', 'variants': [
        {'kind': 'object', 'fields': {'node': {'kind': 'string'}, 'output': {'kind': 'string'}}},
        {'kind': 'object', 'fields': {'node': {'kind': 'string'}, 'output': {'kind': 'string'},
            'expansion': {'kind': 'string'}, 'item': {'kind': 'string'}, 'generation': {'kind': 'integer'}}}]}
    manifest = {'kind': 'object', 'fields': {
        'target': target_schema,
        'findings': {'kind': 'map', 'values': entry},
        'subject': copy.deepcopy(ref),
        'reviews': {'kind': 'array', 'items': copy.deepcopy(ref)},
        'opportunities': {'kind': 'map', 'values': {'kind': 'string'}}}}
    source = {'producer': {'slot': 'resolution_batches'}, 'output': 'content',
              'path': [expansion], 'mode': 'content',
              'type': {'kind': 'object', 'fields': {
                  'items': {'kind': 'map', 'values': copy.deepcopy(manifest)},
                  'rationale': {'kind': 'string'}}}}
    decision = {'kind': 'object', 'fields': {
        'finding': copy.deepcopy(ref), 'subjects': {'kind': 'array', 'items': copy.deepcopy(ref)},
        'reviewer_result': copy.deepcopy(ref),
        'decision': {'kind': 'enum', 'values': ['resolved', 'unresolved']},
        'rationale': {'kind': 'string'}}}
    inputs = {'batch': {**copy.deepcopy(source),
        'path': [expansion, 'items', {'item_key': True}], 'type': manifest},
        'subject': copy.deepcopy(subject_binding)}
    inputs.update(copy.deepcopy(reviews))
    node = {'id': name,
        'prompt': 'Assess every exact finding in batch.findings against the exact corrected subject and all bound independent approved reviews. Return one decision and rationale per exact finding key; unresolved entries remain obligations. Never infer resolution from approval alone.',
        'inputs': inputs,
        'outputs': {'value': {'type': 'resolution_batch', 'schema': {
            'kind': 'object', 'fields': {'entries': {'kind': 'map', 'values': decision}}}}},
        'requires': [],
        'executor': {'role': 'worker', 'capability': capability, 'resources': [],
                     'authority': {'subject': {'kind': 'self'}, 'output': 'value'}},
        'independent_of': independent, 'gates': [],
        'resolves': [copy.deepcopy(scope)],
        'permits': [{'type': 'resolution_batch', 'scope': copy.deepcopy(scope)}]}
    return {'id': expansion, 'source': source, 'template': node}
