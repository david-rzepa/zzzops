"""#539 text-only storage contract.

The comment_store codec API below is a proposed internal interface, not an
existing implementation. Public/provider failures live alongside these focused
contract tests so missing-module assertions are not the behavioral baseline.
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


if __name__ == '__main__':
    unittest.main()
