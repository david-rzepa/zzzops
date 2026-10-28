"""Finite resolution acceptance proofs, separate from current task eligibility.

A committed submit closes an exact admitted finding revision. This module never
executes a historical DAG or promotes an old Result to current authority.
"""
from __future__ import annotations

import copy


def require(condition, message):
    if not condition:
        raise ValueError('Resolution acceptance: ' + message)


def materialize(graph, result, ev):
    """Recover one exact captured contract, without evaluating dependencies."""
    node = result['node']
    if node.get('item') is None:
        matches = [row for row in graph['nodes'] if row['id'] == node['node']]
        require(len(matches) == 1, 'historical node contract is absent or ambiguous')
        return matches[0]
    expansions = [row for row in graph['task_sets'] if row['template']['id'] == node['node']]
    require(len(expansions) == 1, 'historical member contract is absent or ambiguous')
    expansion = expansions[0]
    self_selector = {'kind': 'member', 'goal': node['goal'], 'expansion': expansion['id'],
                     'item': node['item'], 'generation': node['generation']}
    # Event subject selectors are bound in the Result's exact host resolutions.
    event_targets = [row['targets'][0] for row in result['resolutions']
                     if row['selector'].get('kind') == 'member'
                     and row['selector'].get('expansion') != expansion['id']
                     and len(row['targets']) == 1]
    def replace(value):
        if value == {'kind': 'self'}: return copy.deepcopy(self_selector)
        if value == {'item_key': True}: return node['item']
        if value == {'event_subject_item': True}:
            values = {row['item'] for row in event_targets}
            require(len(values) == 1, 'ambiguous captured event subject item')
            return next(iter(values))
        if value == {'event_subject_generation': True}:
            values = {row['generation'] for row in event_targets}
            require(len(values) == 1, 'ambiguous captured event subject generation')
            return next(iter(values))
        if isinstance(value, dict): return {key: replace(child) for key, child in value.items()}
        if isinstance(value, list): return [replace(child) for child in value]
        return value
    return replace(expansion['template'])


def validate_entry(value, *, expected, scope, goal, results, contracts, read, ev,
                   required_reviews, subject):
    """The same semantic entry checks serve live submit and accepted history."""
    require(isinstance(value, dict) and set(value) == {
        'finding', 'subjects', 'reviewer_result', 'decision', 'rationale'}, 'malformed entry')
    require(value['decision'] in ('resolved', 'unresolved') and
            isinstance(value['rationale'], str) and value['rationale'].strip(),
            'entry needs an explicit decision and rationale')
    require(value['finding'] == expected['finding'], 'entry differs from exact admitted finding revision')
    finding = read(value['finding'], 'finding')
    require(finding['target']['subject']['goal'] == goal and finding['id'] == expected['id']
            and finding['revision'] == expected['revision'], 'foreign or stale finding identity')
    permitted = copy.deepcopy(scope)
    if permitted['subject']['goal'] == '#this': permitted['subject']['goal'] = goal
    require(finding['target'] == permitted, 'finding is outside exact permitted scope')
    subjects = subject if isinstance(subject, list) else [subject]
    require(subjects and value['subjects'] == subjects and len({ref['hash'] for ref in subjects}) == len(subjects),
            'entry differs from exact corrected subjects')
    require(value['reviewer_result'] in required_reviews, 'entry substitutes a required independent reviewer')
    producers = []
    for reference in subjects:
        owners = [result for _, result in results.values() if reference in result['outputs'].values()]
        require(len(owners) == 1, 'corrected subject has no unique accepted producer')
        producers.append(owners[0])
    target = finding['target']['subject']
    targeted = [producer for producer in producers if producer['node']['goal'] == goal
                and (target['kind'] == 'node' and producer['node']['node'] == target['node']
                     and producer['node'].get('item') is None
                     or target['kind'] == 'member' and producer['node'].get('item') == target['item']
                     and producer['node'].get('generation') == target['generation'])]
    require(len(targeted) == 1, 'subjects omit the exact finding target producer')
    for reference in required_reviews:
        require(reference['hash'] in results, 'required reviewer Result is unavailable')
        reviewer = results[reference['hash']][1]
        contract = contracts.get(reference['hash'])
        require(contract is not None, 'required reviewer contract is unavailable')
        for inspected, producer in zip(subjects, producers):
            require(reviewer['executor'] != producer['executor'], 'reviewer is the subject executor')
            require(any(binding['source'] == inspected and binding['mode'] == 'identity'
                        and not binding['path'] for binding in reviewer['inputs']),
                    'reviewer did not inspect the exact full corrected subject')
        independent = []
        for row in reviewer['resolutions']:
            selector = copy.deepcopy(row['selector'])
            if selector.get('goal') == '#this': selector['goal'] = goal
            if row['selector'] in contract['independent_of'] and selector == target:
                independent.extend(row['targets'])
        require(targeted[0]['node'] in independent, 'reviewer lacks declared exact subject independence')
    return value


def committed_results(engine, snapshot):
    """Authenticate accepted submit edges on the current immutable receipt chain.

    Prepared comments, disconnected branches and self-asserted Result provenance
    cannot enter this map. The trusted provider journal is the authority boundary.
    """
    ev = engine.api._phase_evidence
    number = snapshot['envelope']['issue']
    resolve = snapshot['resolve']
    index = engine.artifact_index(number)
    receipts = snapshot['payload']['operational']['receipts']
    edges = {}
    for receipt in receipts:
        edge = engine.node_receipt_edge(number, index, receipt)
        if edge is None:
            continue
        key = engine.api._workflow.digest(edge['target'])
        require(key not in edges, 'conflicting committed receipt target')
        edges[key] = (edge, receipt)
    current = snapshot['envelope']
    accepted = {}
    while engine.api._workflow.digest(current) in edges:
        edge, receipt = edges[engine.api._workflow.digest(current)]
        source, target = resolve(edge['source']['payload']), resolve(edge['target']['payload'])
        require(target['operational']['receipts'] == source['operational']['receipts'] + [receipt],
                'receipt is not the exact source/target prefix extension')
        submitted = edge['response'].get('submitted')
        if submitted is not None:
            reference = submitted.get('result')
            require(submitted.get('goal') == number and isinstance(reference, dict),
                    'submitted Result has a foreign identity')
            require(target['evidence'] == source['evidence'] + [reference],
                    'submit did not append exactly one Result to its captured evidence prefix')
            blob = resolve(reference)
            require(blob.get('type') == 'result', 'submitted artifact is not a host Result')
            result = blob['content']
            require(submitted.get('node') == result['node'] and result['node']['goal'] == number,
                    'submitted Result node identity differs')
            leases = [lease for lease in source['operational']['leases']
                      if lease['node'] == result['node'] and lease['attempt'] == result['attempt']]
            require(len(leases) == 1, 'submit lacks its exact consumed source lease')
            lease = leases[0]
            require(lease['worker'] == result['executor'] and all(
                lease['acquisition'][name] == result[name] for name in ('inputs', 'resolutions', 'contract')),
                'Result differs from bound worker/acquisition')
            if 'expected_goal_revision' in result:
                require(result['expected_goal_revision'] == lease['acquisition'].get('expected_goal_revision'),
                        'Result successor CAS differs from its captured acquisition revision')
            require(target['operational']['leases'] == [row for row in source['operational']['leases'] if row != lease],
                    'submit did not remove exactly its own lease')
            graph_ref = source.get('workflow', {}).get('graph', source['graph'])
            contract = materialize(resolve(graph_ref), result, ev)
            accepted[reference['hash']] = {'reference': reference, 'result': result,
                'blob': blob, 'contract': contract, 'source': source, 'target': target,
                'source_envelope': edge['source'], 'receipt': receipt}
        current = edge['source']
    return accepted


def fold(engine, snapshot, historical_policies):
    """Return only authenticated immutable per-finding lifecycle decisions."""
    ev, digest = engine.api._phase_evidence, engine.api._workflow.digest
    resolve = snapshot['resolve']
    number = snapshot['envelope']['issue']
    candidates = []
    for reference in snapshot['payload']['evidence']:
        result = resolve(reference)['content']
        for output in result['outputs'].values():
            if resolve(output).get('type') in ('resolution', 'resolution_batch'):
                candidates.append((reference, output))
    if not candidates:
        return []
    accepted = committed_results(engine, snapshot)
    policies = [engine.project['policy'], *historical_policies.values()]
    def policy_contract(row):
        provenance = row['blob'].get('provenance', {})
        approved, recorded = provenance.get('approved_policy'), provenance.get('policy')
        def authenticated_matches():
            matches = []
            for policy in policies:
                forms = {digest(engine.api._policy.phase_policy_projection(policy, form))
                         for form in ('full', 'pre_static', 'current', 'normalized')}
                if recorded in forms and (approved is None or approved == digest(policy)):
                    matches.append(forms)
            return matches
        matching = authenticated_matches()
        error = None
        if not matching:
            recovered, error = engine.node_historical_policies({}, {}, compatible_only=False,
                required_hashes={value for value in (recorded, approved) if isinstance(value, str)})
            policies.extend(recovered.values())
            matching = authenticated_matches()
        require(matching, 'historical approved policy is not authenticated for ' + row['reference']['hash']
                + (': ' + error if error else ''))
        require(any(row['result']['contract'] == digest({'node': row['contract'], 'policy': form})
                    for forms in matching for form in forms),
                'Result contract does not match the exact captured policy/node')
        return row['contract']
    def read(reference, kind=None):
        ev.validate_ref(reference)
        require(engine.node_ref_goal(reference, number) == number, 'foreign immutable evidence Ref')
        value = resolve(reference)
        require(kind is None or value.get('type') == kind, 'immutable evidence type mismatch')
        return value.get('content', value)
    folded = []
    for reference, output_ref in candidates:
        row = accepted.get(reference['hash'])
        require(row is not None, 'resolution Result lacks an exact committed submit lineage: ' + reference['hash'])
        result, output = row['result'], resolve(output_ref)
        contract = policy_contract(row)
        require(output.get('producer') == result['attempt'] and
                output.get('provenance', {}).get('actor') == result['executor'] and
                output.get('provenance', {}).get('policy') == row['blob']['provenance'].get('policy') and
                output.get('provenance', {}).get('approved_policy') == row['blob']['provenance'].get('approved_policy'),
                'resolution output producer/policy provenance mismatch')
        slots = [slot for slot, ref in result['outputs'].items() if ref == output_ref]
        require(len(slots) == 1 and slots[0] in contract['outputs'], 'resolution output slot is not declared')
        output_contract = contract['outputs'][slots[0]]
        require(output_contract['type'] == output['type'] and ev.value_matches(output_contract['schema'], output['content']),
                'resolution output violates captured type contract')
        source_refs = {ref['hash'] for ref in row['source']['evidence']}
        results = {identity: (value['reference'], value['result']) for identity, value in accepted.items()
                   if identity in source_refs}
        contracts = {identity: value['contract'] for identity, value in accepted.items() if identity in source_refs}
        obligations = {}
        for source_ref in row['source']['evidence']:
            source_result = read(source_ref, 'result')
            for source_output in source_result['outputs'].values():
                value = resolve(source_output)
                if value.get('type') == 'admission':
                    finding = read(value['content']['finding'], 'finding')
                    obligations[finding['id']] = {'finding': value['content']['finding'],
                        'admission': source_output, 'id': finding['id'], 'revision': finding['revision']}
        if output['type'] == 'resolution_batch':
            bindings = [binding for binding in result['inputs'] if binding['name'] == 'batch']
            require(len(bindings) == 1, 'batch lacks its exact captured manifest')
            binding = bindings[0]
            blob = resolve(binding['source'])
            require(blob.get('type') == 'resolution_batch_context' and blob.get('producer') is None
                    and blob.get('provenance', {}).get('actor') == 'host', 'batch manifest is not host captured')
            manifest = ev.selected_path(blob['content'], binding['path'])
            require(set(output['content']['entries']) == set(manifest['findings']),
                    'batch omits or adds required finding entries')
            entries = output['content']['entries']
            required_reviews, subject = manifest['reviews'], manifest['subject']
        else:
            value = output['content']
            finding = read(value['finding'], 'finding')
            manifest = {'findings': {'legacy': {'finding': value['finding'], 'id': finding['id'],
                'revision': finding['revision']}}, 'opportunities': {}}
            entries = {'legacy': value}
            required_reviews, subject = [value['reviewer_result']], value['subjects']
        for reviewer_ref in required_reviews:
            require(reviewer_ref['hash'] in accepted and reviewer_ref['hash'] in source_refs,
                    'reviewer was not committed before resolution acceptance')
            policy_contract(accepted[reviewer_ref['hash']])
        for key, value in entries.items():
            expected = manifest['findings'][key]
            prior = obligations.get(expected['id'])
            require(prior is not None and all(prior[field] == expected[field]
                for field in ('id', 'revision', 'finding')), 'resolution did not cover the current admitted revision')
            if 'admission' in expected:
                require(prior['admission'] == expected['admission'], 'batch substituted its exact admission')
            finding = read(expected['finding'], 'finding')
            scopes = [permit['scope'] for permit in contract['permits'] if permit['type'] == output['type']]
            matching = [scope for scope in scopes if {**scope, 'subject': {
                **scope['subject'], 'goal': number if scope['subject']['goal'] == '#this' else scope['subject']['goal']}}
                == finding['target']]
            require(len(matching) == 1, 'resolution lacks one exact captured scope permit')
            validate_entry(value, expected=expected, scope=matching[0], goal=number,
                results=results, contracts=contracts, read=read, ev=ev,
                required_reviews=expected.get('reviews', required_reviews), subject=subject)
            folded.append({'finding': value['finding'], 'decision': value['decision'],
                'opportunity': manifest['opportunities'].get(key), 'result': reference, 'output': output_ref})
    return folded
