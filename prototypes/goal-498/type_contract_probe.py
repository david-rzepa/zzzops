"""Bounded grammar experiment, not production validation or host authentication.

Exercises the approved output/map amendment independently of the scheduling model.
Fixture permissions demonstrate structural/semantic separation, not full admission
freshness or provider authority (covered by the existing scheduling probes).
"""
import copy
import json
import re
import unittest

from probe import digest


def identifier(value):
    return isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_-]+', value) is not None


def bounded(value, depth=0):
    if depth > 16:
        raise ValueError('nesting limit')
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            raise ValueError('JSON string keys required')
        for item in value.values():
            bounded(item, depth + 1)
    elif type(value) is list:
        for item in value:
            bounded(item, depth + 1)
    elif type(value) not in (str, int, bool, type(None)):
        raise ValueError('probe supports only finite scalar subset')
    if depth == 0 and len(json.dumps(value, ensure_ascii=False).encode()) > 1024 * 1024:
        raise ValueError('size limit')


def decode(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate key')
            result[key] = value
        return result
    if len(text.encode()) > 1024 * 1024:
        raise ValueError('size limit')
    value = json.loads(text, object_pairs_hook=pairs)
    bounded(value)
    return value


def accepts(schema, value):
    kind = schema['kind']
    scalars = {'string': str, 'integer': int, 'boolean': bool, 'null': type(None)}
    if kind in scalars:
        return type(value) is scalars[kind]
    if kind == 'map':
        return type(value) is dict and all(type(k) is str and accepts(schema['values'], v) for k, v in value.items())
    if kind == 'object':
        return type(value) is dict and set(value) == set(schema['fields']) and all(accepts(t, value[k]) for k, t in schema['fields'].items())
    if kind == 'array':
        return type(value) is list and all(accepts(schema['items'], v) for v in value)
    if kind == 'union':
        return sum(accepts(t, value) for t in schema['variants']) == 1
    raise ValueError('unsupported probe type')


def overlaps(a, b):
    # Exact for the deliberately restricted, non-enum probe grammar.
    if a['kind'] == 'union':
        return any(overlaps(t, b) for t in a['variants'])
    if b['kind'] == 'union':
        return overlaps(b, a)
    ak, bk = a['kind'], b['kind']
    if {ak, bk} == {'map', 'object'}:
        m, o = (a, b) if ak == 'map' else (b, a)
        return all(overlaps(m['values'], t) for t in o['fields'].values())
    if ak != bk:
        return False
    if ak == 'object':
        return set(a['fields']) == set(b['fields']) and all(overlaps(t, b['fields'][k]) for k, t in a['fields'].items())
    return True  # arrays and maps share their empty value; equal scalars overlap


def validate_schema(schema):
    bounded(schema)
    if type(schema) is not dict:
        raise ValueError('schema object required')
    kind = schema.get('kind')
    fields = {'string': {'kind'}, 'integer': {'kind'}, 'boolean': {'kind'}, 'null': {'kind'},
              'map': {'kind', 'values'}, 'object': {'kind', 'fields'},
              'array': {'kind', 'items'}, 'union': {'kind', 'variants'}}
    if kind not in fields or set(schema) != fields[kind]:
        raise ValueError('unknown schema fields/type')
    if kind in ('map', 'array'):
        validate_schema(schema['values' if kind == 'map' else 'items'])
    if kind == 'object':
        if type(schema['fields']) is not dict or any(not identifier(k) for k in schema['fields']):
            raise ValueError('invalid field identity')
        for t in schema['fields'].values():
            validate_schema(t)
    if kind == 'union':
        variants = schema['variants']
        if type(variants) is not list or not variants:
            raise ValueError('nonempty variants required')
        for i, t in enumerate(variants):
            validate_schema(t)
            if any(overlaps(t, other) for other in variants[:i]):
                raise ValueError('overlapping union')


def pack_outputs(contracts, contents, *, actor, attempt, policy, permits=()):
    """Host context is fixture-supplied, never taken from submitted contents."""
    bounded(contracts)
    bounded(contents)
    if type(contracts) is not dict or type(contents) is not dict or set(contents) != set(contracts):
        raise ValueError('exact output slots required')
    candidate = {}
    for slot, declaration in contracts.items():
        if not identifier(slot) or type(declaration) is not dict or set(declaration) != {'type', 'schema'}:
            raise ValueError('invalid output declaration')
        kind = declaration['type']
        if not identifier(kind) or kind == 'result':
            raise ValueError('reserved or invalid artifact type')
        validate_schema(declaration['schema'])
        content = contents[slot]
        if not accepts(declaration['schema'], content):
            raise ValueError('output schema mismatch')
        if kind == 'selection':
            if type(content) is not dict or set(content) != {'items', 'rationale'} or type(content['items']) is not dict or any(not identifier(k) for k in content['items']) or not isinstance(content['rationale'], str) or not content['rationale'].strip():
                raise ValueError('invalid selection')
        if kind == 'admission':
            # Deliberately small fixture admission, not the normative Admission shape.
            if type(content) is not dict or set(content) != {'target', 'request'} or (kind, content['target']) not in permits or actor != 'root':
                raise ValueError('semantic authority/scope denied')
        candidate[slot] = {'type': kind, 'content': copy.deepcopy(content), 'producer': attempt,
                           'provenance': {'actor': actor, 'source': None, 'policy': policy}}
    return candidate  # caller publishes nothing before every slot is checked


STRING = {'kind': 'string'}
MAP = {'kind': 'map', 'values': STRING}


class AmendmentProbe(unittest.TestCase):
    def pack(self, contracts, contents, **kw):
        return pack_outputs(contracts, contents, actor=kw.pop('actor', 'root'), attempt='attempt_1', policy='reviewed_policy', **kw)

    def test_two_slots_share_semantic_type_and_keep_host_provenance(self):
        declaration = {'type': 'admission', 'schema': {'kind': 'object', 'fields': {'target': STRING, 'request': STRING}}}
        contracts = dict(admission_a=declaration, admission_b=declaration)
        contents = {k: {'target': 'code', 'request': k} for k in contracts}
        packed = self.pack(contracts, contents, permits=(('admission', 'code'),))
        self.assertEqual([v['type'] for v in packed.values()], ['admission', 'admission'])
        self.assertTrue(all(v['producer'] == 'attempt_1' and v['provenance']['actor'] == 'root' for v in packed.values()))

    def test_missing_extra_slots_and_provenance_injection_rejected(self):
        contracts = {'value': {'type': 'text', 'schema': STRING}}
        for value in ({}, {'value': 'ok', 'extra': 'bad'}, {'value': {'type': 'result', 'producer': 'fake', 'provenance': {'actor': 'root'}}}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.pack(contracts, value)

    def test_host_result_declaration_rejected(self):
        with self.assertRaisesRegex(ValueError, 'reserved'):
            self.pack({'value': {'type': 'result', 'schema': STRING}}, {'value': 'fake'})

    def test_artifact_like_ordinary_content_cannot_override_host_fields(self):
        content = {'type': 'result', 'producer': 'fake_attempt', 'actor': 'attacker', 'policy': 'fake_policy'}
        packed = self.pack({'data': {'type': 'report', 'schema': MAP}}, {'data': content})['data']
        self.assertEqual(packed['content'], content)
        self.assertEqual(packed['type'], 'report')
        self.assertEqual(packed['producer'], 'attempt_1')
        self.assertEqual(packed['provenance'], {'actor': 'root', 'source': None, 'policy': 'reviewed_policy'})

    def test_permissive_structure_cannot_bypass_semantic_authority(self):
        contracts = {'a': {'type': 'admission', 'schema': MAP}}
        value = {'a': {'target': 'code', 'request': 'fix'}}
        for kwargs in ({}, {'actor': 'worker', 'permits': (('admission', 'code'),)}, {'permits': (('admission', 'other'),)}):
            with self.subTest(kwargs=kwargs), self.assertRaisesRegex(ValueError, 'authority'):
                self.pack(contracts, value, **kwargs)

    def test_type_and_schema_changes_change_contract_identity(self):
        contracts = {'value': {'type': 'text', 'schema': STRING}}
        for field, replacement in (('type', 'report'), ('schema', MAP)):
            changed = copy.deepcopy(contracts)
            changed['value'][field] = replacement
            self.assertNotEqual(digest(contracts), digest(changed))

    def test_empty_and_newly_discovered_items_without_graph_change(self):
        contracts = {'chosen': {'type': 'selection', 'schema': {'kind': 'object', 'fields': {'items': MAP, 'rationale': STRING}}}}
        before = digest(contracts)
        for items in ({}, {'requirements': 'inspect'}, {'requirements': 'inspect', 'migration': 'new bucket'}):
            self.assertEqual(self.pack(contracts, {'chosen': {'items': items, 'rationale': 'evidence'}})['chosen']['content']['items'], items)
        self.assertEqual(before, digest(contracts))

    def test_general_map_keys_are_not_selection_ids(self):
        self.assertTrue(accepts(MAP, {'arbitrary key /': 'data'}))
        with self.assertRaisesRegex(ValueError, 'selection'):
            self.pack({'x': {'type': 'selection', 'schema': {'kind': 'object', 'fields': {'items': MAP, 'rationale': STRING}}}}, {'x': {'items': {'bad/key': 'data'}, 'rationale': 'reason'}})

    def test_wrong_map_value_and_closed_object(self):
        self.assertFalse(accepts(MAP, {'key': 1}))
        self.assertFalse(accepts({'kind': 'object', 'fields': {'a': STRING}}, {'a': 'ok', 'b': 'new'}))

    def test_overlapping_map_union_rejected_even_for_disjoint_value_types(self):
        with self.assertRaisesRegex(ValueError, 'overlapping'):
            validate_schema({'kind': 'union', 'variants': [MAP, {'kind': 'map', 'values': {'kind': 'integer'}}]})
        validate_schema({'kind': 'union', 'variants': [MAP, STRING]})

    def test_duplicate_keys_and_noncanonical_types_rejected(self):
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            decode('{"items":{"a":"first","a":"second"}}')
        self.assertEqual(digest(decode('{"b":"2","a":"1"}')), digest(decode('{"a":"1","b":"2"}')))
        self.assertFalse(accepts({'kind': 'integer'}, True))

    def test_depth_size_and_unknown_schema_fields(self):
        nested = 'leaf'
        for _ in range(17):
            nested = {'key': nested}
        for value in (nested, 'x' * (1024 * 1024 + 1)):
            with self.assertRaisesRegex(ValueError, 'limit'):
                bounded(value)
        with self.assertRaisesRegex(ValueError, 'unknown'):
            validate_schema({'kind': 'map', 'values': STRING, 'script': 'execute'})


if __name__ == '__main__':
    unittest.main()
