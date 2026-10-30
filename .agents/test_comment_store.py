"""#539 text-only storage contract.

The comment_store codec is the implemented bounded text-patch interface.
Public/provider tests exercise its behavioral boundaries alongside these
focused storage contract tests.
"""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

import test_zzzops as fixtures

z = fixtures.zzzops


class ProviderCommentBudgetTests(unittest.TestCase):
    def post(self, body):
        with mock.patch.object(z.shutil, 'which', return_value='gh'), mock.patch.object(
            z.subprocess, 'run', return_value=SimpleNamespace(
                returncode=0, stdout=json.dumps({'body': body, 'id': 1, 'html_url': 'https://example.test/1'}), stderr='')) as run:
            adapter = z.GitHubGoalTransitionAdapter(Path.cwd(), 'owner/repo')
            try:
                result = adapter.create_issue_comment(42, body)
            except (ValueError, z.GoalTransitionProviderError) as exc:
                return exc, run.call_count
            return result, run.call_count

    def test_complete_unicode_body_at_character_allowance_is_accepted(self):
        for char in ('a', '😀', 'é'):
            with self.subTest(char=char):
                body = '<!-- wrapper -->\n' + char * (65536 - len('<!-- wrapper -->\n'))
                result, calls = self.post(body)
                self.assertIsInstance(result, dict)
                self.assertEqual(body, result['body'])
                self.assertGreater(calls, 0)

    def test_one_character_over_reports_sizes_and_reference_before_provider_write(self):
        for char in ('a', '😀'):
            with self.subTest(char=char):
                result, calls = self.post(char * 65537)
                self.assertTrue(isinstance(result, Exception), 'Shared provider boundary must reject oversized complete bodies')
                self.assertEqual(0, calls)
                for diagnostic in ('65537', '65536', str(len((char * 65537).encode())), 'reference'):
                    self.assertIn(diagnostic, str(result).lower())

    def test_invalid_surrogate_fails_before_provider(self):
        result, calls = self.post('invalid\ud800')
        self.assertIsInstance(result, Exception)
        self.assertEqual(0, calls)


class ExactTextPatchContractTests(unittest.TestCase):
    def setUp(self):
        path = fixtures.PLUGIN_ROOT / 'zzzops/comment_store.py'
        self.assertTrue(path.is_file(), 'The approved bounded text-patch codec is not implemented')
        spec = importlib.util.spec_from_file_location('goal539_comment_store', path)
        self.codec = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.codec)

    @staticmethod
    def exact_patch(before, after, edits):
        # Independent wire fixture: do not ask the generator to compute either
        # coordinates or endpoint metadata for reader/resource assertions.
        return {'schema_version': 1, 'base_hash': 'sha256:' + hashlib.sha256(before.encode('utf-8')).hexdigest(),
                'result_hash': 'sha256:' + hashlib.sha256(after.encode('utf-8')).hexdigest(),
                'base_length': len(before), 'result_length': len(after), 'edits': edits}

    def test_aggregate_envelope_decode_work_is_bounded_across_distinct_records(self):
        codec = self.codec
        values = [str(i) + ':' + 'x' * 999000 for i in range(17)]
        records = [{'kind': 'full', 'type': 'text', 'text': value,
                    'hash': codec.digest(value)} for value in values]
        bodies = codec.pack_envelopes({'goal': 42, 'transaction': 'aggregate-budget'}, records)
        self.assertGreater(len(bodies), 1)
        comments = [{'body': body} for body in bodies]
        # Distinct, individually valid records, not duplicates or a deep chain.
        control = codec.pack_envelopes({'goal': 42, 'transaction': 'control'}, records[:1])
        self.assertEqual(values[0], codec.ArtifactIndex([{'body': b} for b in control]).resolve(records[0]['hash'])[0])
        decoded = 0
        unpack = codec.unpack
        def metered(*args, **kwargs):
            nonlocal decoded
            result = unpack(*args, **kwargs)
            decoded += len(result)
            return result
        with mock.patch.object(codec, 'unpack', side_effect=metered):
            try:
                result = codec.ArtifactIndex(comments).resolve(records[0]['hash'])[0]
            except ValueError as exc:
                self.assertRegex(str(exc), r'(?i)(work|decoded|reconstruct).*(limit|budget|exceed|bound)')
            else:
                self.assertEqual(values[0], result)
        self.assertLessEqual(decoded, codec.MAX_RECONSTRUCTION_WORK_BYTES,
                             'Lookup materialized unrelated envelopes beyond its total budget before returning or rejecting')

    def test_single_review_artifact_over_comment_limit_is_split_and_resolves_exactly(self):
        codec = self.codec
        value = ''.join(hashlib.sha256(str(index).encode()).hexdigest() for index in range(2000))
        record = {'kind': 'full', 'type': 'text', 'text': value, 'hash': codec.digest(value)}
        common = {'goal': 21, 'transaction': 'review-test-design',
                  'context': {'provenance': 'p' * 8000}}
        with self.assertRaisesRegex(ValueError, r'65536'):
            codec.encode_envelope({'schema_version': 2, **common, 'part': 0,
                'manifest': [codec.digest({'kind': 'artifact', 'value': record})],
                'members': [0], 'artifacts': [record], 'history': None})
        bodies = codec.pack_envelopes(common, [record])
        self.assertGreater(len(bodies), 1)
        self.assertTrue(all(len(body) <= codec.MAX_COMMENT_CHARACTERS for body in bodies))
        resolved = codec.ArtifactIndex([{'body': body} for body in bodies]).resolve(record['hash'])[0]
        self.assertEqual(value, resolved)

    def test_chunked_artifact_requires_one_complete_immutable_set(self):
        codec = self.codec
        value = ''.join(hashlib.sha256(('chunk-' + str(index)).encode()).hexdigest() for index in range(2000))
        record = {'kind': 'full', 'type': 'text', 'text': value, 'hash': codec.digest(value)}
        bodies = codec.pack_envelopes({'goal': 21, 'transaction': 'chunk-integrity',
                                       'context': {'provenance': 'p' * 8000}}, [record])
        comments = [{'body': body} for body in bodies]
        with self.assertRaisesRegex(ValueError, r'(?i)incomplete|missing'):
            codec.ArtifactIndex(comments[:-1]).resolve(record['hash'])
        envelope = codec.decode_envelope(comments[0]['body'])
        envelope['artifacts'][0]['text'] += 'tampered'
        comments[0]['body'] = codec.encode_envelope(envelope)
        with self.assertRaisesRegex(ValueError, r'(?i)conflict|identity'):
            codec.ArtifactIndex(comments).resolve(record['hash'])

    def test_three_plus_chunk_pack_round_trips_exact_text_in_any_comment_order(self):
        codec = self.codec
        value = ''.join(hashlib.sha256(('lossless-' + str(index)).encode()).hexdigest()
                        for index in range(5000))
        record = {'kind': 'full', 'type': 'text', 'text': value, 'hash': codec.digest(value)}
        bodies = codec.pack_envelopes({
            'goal': 21, 'transaction': 'lossless-three-plus-chunks',
            'context': {'provenance': 'reviewed-cutover-' + 'p' * 8000}}, [record])

        self.assertGreaterEqual(len(bodies), 3,
            'fixture must cross at least three provider comments to exercise manifest packing')
        self.assertTrue(all(len(body) <= codec.MAX_COMMENT_CHARACTERS for body in bodies))
        comments = [{'body': body} for body in reversed(bodies)]
        index = codec.ArtifactIndex(comments)
        chunks = index.records[record['hash']]
        self.assertEqual(len(bodies), len(chunks))
        self.assertTrue(all(chunk['kind'] == 'chunk' for chunk in chunks))
        self.assertTrue(all(chunk['hash'] == record['hash'] for chunk in chunks))
        self.assertEqual({len(chunks)}, {chunk['total'] for chunk in chunks})
        resolved, depth, spent = index.resolve(record['hash'])
        self.assertEqual(value, resolved)
        self.assertEqual(0, depth)
        self.assertGreater(spent, len(value.encode('utf-8')))
        self.assertLessEqual(spent, codec.MAX_RECONSTRUCTION_WORK_BYTES)

    def test_chunk_sizing_includes_complete_transaction_manifest(self):
        codec = self.codec
        value = ''.join(hashlib.sha256(str(i).encode()).hexdigest() for i in range(70))
        values = [value] + [str(i) for i in range(6)]
        records = [{'kind': 'full', 'type': 'text', 'text': text, 'hash': codec.digest(text)}
                   for text in values]
        with mock.patch.object(codec, 'MAX_COMMENT_CHARACTERS', 4096):
            bodies = codec.pack_envelopes({'goal': 21, 'transaction': 'manifest-boundary',
                                          'context': {}}, records)
            self.assertTrue(all(len(body) <= 4096 for body in bodies))
        index = codec.ArtifactIndex([{'body': body} for body in reversed(bodies)])
        codec.verify_manifest(index.envelopes)
        for value in values:
            self.assertEqual(value, index.resolve(codec.digest(value))[0])

    def test_unicode_original_base_offsets_and_exact_newlines(self):
        before = 'A😀e\u0301BC🌍D'
        after = 'AXY😀e\u0301bC🌍!'
        # Original code-point indices: A=0, emoji=1, e=2, accent=3, B=4,
        # C=5, globe=6, D=7. The first insertion changes subsequent live offsets.
        edits = [[1, 0, 'XY'], [4, 1, 'b'], [7, 1, '!']]
        manual = self.exact_patch(before, after, edits)
        self.assertEqual(after, self.codec.apply_text_patch(before, manual))
        generated = self.codec.make_text_patch(before, after)
        self.assertEqual(edits, generated['edits'], 'Generator must emit original-base Unicode code-point coordinates')
        for before, after in [('A😀é\r\nlast', 'A😀É\r\nlast!'), ('abcXYZdef', '!abcXdef?'), ('', '😀'), ('text\n', '')]:
            with self.subTest(before=before):
                patch = self.codec.make_text_patch(before, after)
                self.assertEqual(after, self.codec.apply_text_patch(before, patch))
                self.assertTrue(all(isinstance(edit, list) and len(edit) == 3 for edit in patch['edits']))
                self.assertNotIn('operations', patch)

    def test_long_single_line_and_json_value_use_character_edits(self):
        for before in ('paragraph ' * 3000, json.dumps({'text': 'paragraph ' * 3000}, sort_keys=True, separators=(',', ':'))):
            after = before[:9000] + 'X' + before[9001:]
            patch = self.codec.make_text_patch(before, after)
            self.assertEqual(after, self.codec.apply_text_patch(before, patch))
            self.assertLess(len(json.dumps(patch)), 1500, 'Single character change must not replace the whole paragraph/JSON field')

    def test_malformed_edits_and_wrong_endpoints_are_rejected_without_fuzzy_matching(self):
        original = self.codec.make_text_patch('a😀bc', 'a😀Bc')
        for edits in ([[True, 1, 'x']], [[-1, 0, 'x']], [[0, 99, 'x']], [[2, 1, 'x'], [1, 1, 'y']], [[1, 2, 'x'], [2, 1, 'y']], [[0, 0, '\ud800']]):
            with self.subTest(edits=repr(edits)):
                patch = copy.deepcopy(original)
                patch['edits'] = edits
                with self.assertRaises(ValueError):
                    self.codec.apply_text_patch('a😀bc', patch)
        with self.assertRaises(ValueError):
            self.codec.apply_text_patch('different', original)
        patch = copy.deepcopy(original)
        patch['edits'][0][2] = 'wrong'
        with self.assertRaises(ValueError):
            self.codec.apply_text_patch('a😀bc', patch)

    def test_generation_budget_avoids_quadratic_matcher(self):
        # Prefix/suffix trimming leaves a repetitive middle above the approved budget.
        with mock.patch('difflib.SequenceMatcher', side_effect=AssertionError('unbounded matcher entered')):
            before, after = 'ab' * 6000, 'ba' * 6000
            patch = self.codec.make_text_patch(before, after)
            self.assertEqual(after, self.codec.apply_text_patch(before, patch))

    def test_insertion_and_edit_count_bounded_before_output_allocation(self):
        with self.subTest(resource='insertion/output bytes'):
            before = 'a'
            within = 'z' * 999_999 + 'a'
            self.assertEqual(within, self.codec.apply_text_patch(
                before, self.exact_patch(before, within, [[0, 0, 'z' * 999_999]])))
            over = 'z' * 1_000_001 + 'a'
            patch = self.exact_patch(before, over, [[0, 0, 'z' * 1_000_001]])
            with self.assertRaisesRegex(ValueError, r'(?i)(insert|output|reconstruct|materializ).*(limit|budget|exceed|bound)'):
                self.codec.apply_text_patch(before, patch)
        with self.subTest(resource='edit count'):
            before = 'a' * 20_003
            within = 'ba' * 10_000 + 'aaa'
            edits = [[2 * index, 1, 'b'] for index in range(10_000)]
            self.assertEqual(within, self.codec.apply_text_patch(before, self.exact_patch(before, within, edits)))
            over = 'ba' * 10_001 + 'a'
            edits = [[2 * index, 1, 'b'] for index in range(10_001)]
            patch = self.exact_patch(before, over, edits)
            with self.assertRaisesRegex(ValueError, r'(?i)(edit.*(limit|budget|exceed|bound)|too many.*edit)'):
                self.codec.apply_text_patch(before, patch)


class VerifiedReconstructionDetailsTests(unittest.TestCase):
    def setUp(self):
        self.codec = z._comment_store

    @staticmethod
    def wire(value):
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(',', ':'), allow_nan=False).encode('utf-8')

    def full(self, value):
        return {'kind': 'full', 'hash': 'sha256:' + hashlib.sha256(self.wire(value)).hexdigest(),
                'type': 'text' if isinstance(value, str) else 'json',
                'text': value if isinstance(value, str) else self.wire(value).decode('utf-8')}

    def test_verified_size_and_charged_work_cover_every_representation(self):
        for value in ('', 'é\n"😀', None, False, 17, 1.25, [], {},
                      {'items': ['é', '😀'], 'enabled': True}):
            full = self.full(value); identity = full['hash']
            base = self.full({'different': ['base', 123]})
            # Delta base and root must have different sizes, including UTF-8.
            if full['type'] == 'text': base = self.full('a different base')
            delta = {'kind': 'delta', 'hash': identity, 'type': full['type'], 'base': base['hash'],
                     'patch': self.codec.make_text_patch(base['text'], full['text'])}
            split = len(full['text']) // 2
            chunks = [{'kind': 'chunk', 'hash': identity, 'type': full['type'],
                       'index': i, 'total': 2, 'text': text}
                      for i, text in enumerate((full['text'][:split], full['text'][split:]))]
            legacy = {'kind': 'legacy', 'hash': identity, 'content': value}
            cases = [('full', [full], 0, 1), ('legacy', [legacy], 0, 1),
                     ('chunk', chunks, 0, 1), ('delta', [delta], 1, 1),
                     ('competing-valid', [full, legacy, delta, *chunks], 1, 4)]
            for name, records, depth, representations in cases:
                with self.subTest(value=value, representation=name):
                    index = self.codec.ArtifactIndex([])
                    index.decode_work = 13
                    index.records = {identity: copy.deepcopy(records), base['hash']: [base]}
                    charged = 13 + sum(len(self.wire(record)) for record in records)
                    charged += representations * len(self.wire(value))
                    if depth:
                        charged += len(self.wire(base)) + len(self.wire(
                            'a different base' if full['type'] == 'text' else {'different': ['base', 123]}))
                    details = index._resolve_details(identity)
                    self.assertEqual((value, depth, charged, len(self.wire(value))), details)
                    self.assertEqual((value, depth, charged), index.resolve(identity))
                    self.assertIs(type(details[3]), int)

    def test_json_string_base_uses_decoded_text_transport(self):
        base = self.full('é😀')
        base.update(type='json', text=self.wire('é😀').decode())
        target = self.full('changed é😀')
        delta = {'kind': 'delta', 'hash': target['hash'], 'type': 'text', 'base': base['hash'],
                 'patch': self.codec.make_text_patch('é😀', target['text'])}
        index = self.codec.ArtifactIndex([])
        index.records = {base['hash']: [base], target['hash']: [delta]}
        self.assertEqual(('é😀', 0), index.resolve(base['hash'])[:2])
        self.assertEqual((target['text'], 1), index.resolve(target['hash'])[:2])
        delta['type'] = 'json'
        with self.assertRaisesRegex(ValueError, 'Artifact delta base type mismatch'):
            index.resolve(target['hash'])

    def test_reused_text_still_passes_original_decoder_and_legacy_validation(self):
        valid = self.full({'a': 1})
        for text in ('{"a": 1}', '{"a":1,"a":1}', 'NaN',
                     '[' * 102 + '0' + ']' * 102, '"\\ud800"'):
            for representation in ('full', 'chunk', 'delta'):
                with self.subTest(text=text[:30], representation=representation):
                    index = self.codec.ArtifactIndex([])
                    record = {**valid, 'text': text}
                    if representation == 'chunk':
                        record.update(kind='chunk', index=0, total=1)
                    elif representation == 'delta':
                        base = self.full({'base': 2})
                        index.records[base['hash']] = [base]
                        record = {'kind': 'delta', 'hash': valid['hash'], 'type': 'json',
                                  'base': base['hash'],
                                  'patch': self.codec.make_text_patch(base['text'], text)}
                    index.records[valid['hash']] = [record]
                    with self.assertRaises(ValueError):
                        index._resolve_details(valid['hash'])
        for value in ({1: 'numeric key'}, {'a': float('nan')}, {'a': {1}}, '\ud800'):
            with self.subTest(legacy=repr(value)):
                index = self.codec.ArtifactIndex([])
                index.records[valid['hash']] = [{'kind': 'legacy', 'hash': valid['hash'],
                                                'content': value}]
                with self.assertRaises((ValueError, TypeError)):
                    index.resolve(valid['hash'])
        index = self.codec.ArtifactIndex([])
        index.records[valid['hash']] = [{**valid, 'type': 'unsupported'}]
        with self.assertRaises(ValueError):
            index.resolve(valid['hash'])

    def test_metadata_does_not_short_circuit_bad_competing_representation(self):
        full = self.full({'items': [1]}); identity = full['hash']
        corrupt = {**full, 'text': '{"items":[9]}'}
        incomplete = {'kind': 'chunk', 'hash': identity, 'type': 'json',
                      'index': 0, 'total': 2, 'text': full['text']}
        foreign = {**full, 'hash': 'sha256:' + '0' * 64}
        for bad in (corrupt, incomplete, foreign):
            with self.subTest(kind=bad['kind'], record_hash=bad['hash']):
                index = self.codec.ArtifactIndex([])
                index.records[identity] = [full, bad]
                for reader in (index.resolve, index._resolve_details):
                    with self.assertRaises(ValueError): reader(identity)

    def test_metadata_preserves_work_size_depth_and_missing_base_limits(self):
        base = self.full('base'); full = self.full('changed é😀')
        delta = {'kind': 'delta', 'hash': full['hash'], 'type': 'text', 'base': base['hash'],
                 'patch': self.codec.make_text_patch(base['text'], full['text'])}
        index = self.codec.ArtifactIndex([])
        index.records = {full['hash']: [delta], base['hash']: [base]}
        identity = full['hash']; details = index._resolve_details(identity)
        for constant, limit in (('MAX_RECONSTRUCTION_WORK_BYTES', details[2] - 1),
                                ('MAX_ARTIFACT_BYTES', details[3] - 1), ('MAX_DELTA_DEPTH', 0)):
            with self.subTest(limit=constant), mock.patch.object(self.codec, constant, limit):
                with self.assertRaises(ValueError): index._resolve_details(identity)
        del index.records[base['hash']]
        with self.assertRaisesRegex(ValueError, 'Missing artifact/base'):
            index._resolve_details(identity)
        delta['base'] = identity
        with self.assertRaisesRegex(ValueError, 'Cyclic artifact base'):
            index._resolve_details(identity)

    def test_detached_results_and_observed_cache_keep_mutation_guards(self):
        value = {'items': ['é', 1]}; full = self.full(value); identity = full['hash']
        legacy = {'kind': 'legacy', 'hash': identity, 'content': copy.deepcopy(value)}
        index = self.codec.ArtifactIndex([]); index.records[identity] = [legacy]
        for reader in (index.resolve, index._resolve_details):
            returned = reader(identity); returned[0]['items'].append('caller mutation')
            self.assertEqual(value, reader(identity)[0])
        observed = z._workflow.ObservedArtifactIndex([])
        observed.records[identity] = [full]
        returned = observed.resolve(identity)
        self.assertEqual(3, len(returned))
        self.assertEqual(len(self.wire(value)), observed._value_costs[identity])
        returned[0]['items'].append('detached cache read')
        self.assertEqual(value, observed.resolve(identity)[0])
        full['text'] = '{"items":["changed"]}'
        with self.assertRaisesRegex(ValueError, 'conflicts with its identity'):
            observed.resolve(identity)
        legacy['content']['items'].append(float('nan'))
        with self.assertRaisesRegex(ValueError, 'Nonfinite JSON number'):
            index._resolve_details(identity)


if __name__ == '__main__':
    unittest.main()
