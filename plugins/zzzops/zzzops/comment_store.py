"""Bounded exact text patches and immutable issue-comment envelopes.

Hashes identify complete JSON values; storage representation is deliberately
separate. This module performs no provider writes and grants no workflow authority.
"""
from __future__ import annotations

import base64
import copy
import difflib
import hashlib
import json
import math
import re
import zlib

MAX_COMMENT_CHARACTERS = 65536
MAX_ARTIFACT_BYTES = 1_000_000
MAX_RECONSTRUCTION_WORK_BYTES = 16_000_000
MAX_HISTORY_BYTES = 2_000_000
MAX_PATCH_EDITS = 10_000
MAX_DELTA_DEPTH = 8
MAX_ARTIFACT_RECORDS = 32
START = '<!-- zzzops-envelope\n'
END = '\nzzzops-envelope -->'


def valid_text(text):
    if not isinstance(text, str):
        raise ValueError('Expected Unicode text')
    try:
        return text.encode('utf-8')
    except UnicodeEncodeError as exc:
        raise ValueError('Invalid Unicode surrogate text') from exc


def guard_comment(body):
    raw = valid_text(body)
    if len(body) > MAX_COMMENT_CHARACTERS:
        raise ValueError(f'Comment has {len(body)} characters / {len(raw)} UTF-8 bytes; '
                         f'limit {MAX_COMMENT_CHARACTERS} characters. Use a published Git content reference.')
    return body


def _validate(value, depth=0):
    if depth > 100:
        raise ValueError('JSON nesting limit exceeded')
    if isinstance(value, str):
        valid_text(value)
    elif isinstance(value, dict):
        for key, item in value.items():
            valid_text(key)
            _validate(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _validate(item, depth + 1)
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError('Nonfinite JSON number')


def canonical(value):
    _validate(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return text_hash(canonical(value))


def text_hash(text):
    return 'sha256:' + hashlib.sha256(valid_text(text)).hexdigest()


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate JSON key')
            result[key] = value
        return result
    def invalid(_value):
        raise ValueError('Nonfinite JSON number')
    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)
        _validate(value)
        return value
    except (RecursionError, UnicodeError) as exc:
        raise ValueError('Invalid or excessively nested JSON') from exc


def unpack(encoded, limit):
    if not isinstance(encoded, str) or len(encoded) > MAX_RECONSTRUCTION_WORK_BYTES * 2:
        raise ValueError('Encoded content limit exceeded')
    try:
        data = base64.b64decode(encoded, validate=True)
        decoder = zlib.decompressobj()
        raw = decoder.decompress(data, limit + 1)
        if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail or len(raw) > limit:
            raise ValueError('Decoded content limit exceeded or trailing encoding')
        return raw
    except (zlib.error, UnicodeError) as exc:
        raise ValueError('Malformed compressed encoding') from exc


def make_text_patch(before, after, *, limit=MAX_ARTIFACT_BYTES):
    if max(len(valid_text(before)), len(valid_text(after))) > limit:
        raise ValueError('Reconstructed text exceeds output limit')
    prefix = 0
    bound = min(len(before), len(after))
    while prefix < bound and before[prefix] == after[prefix]:
        prefix += 1
    suffix = 0
    while suffix < bound - prefix and before[len(before) - suffix - 1] == after[len(after) - suffix - 1]:
        suffix += 1
    old = before[prefix:len(before) - suffix if suffix else len(before)]
    new = after[prefix:len(after) - suffix if suffix else len(after)]
    edits = []
    if old != new:
        if max(len(old), len(new)) <= 4096 and len(old) * len(new) <= 4_000_000:
            for tag, a, b, c, d in difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
                if tag != 'equal':
                    edits.append([prefix + a, b - a, new[c:d]])
        else:
            edits = [[prefix, len(old), new]]
    return {'schema_version': 1, 'base_hash': text_hash(before), 'result_hash': text_hash(after),
            'base_length': len(before), 'result_length': len(after), 'edits': edits}


def apply_text_patch(before, patch, *, limit=MAX_ARTIFACT_BYTES):
    fields = {'schema_version', 'base_hash', 'result_hash', 'base_length', 'result_length', 'edits'}
    if not isinstance(patch, dict) or set(patch) != fields or type(patch['schema_version']) is not int or patch['schema_version'] != 1:
        raise ValueError('Unsupported text patch')
    if any(type(patch[k]) is not int or patch[k] < 0 for k in ('base_length', 'result_length')):
        raise ValueError('Invalid text patch lengths')
    if len(valid_text(before)) > limit or patch['result_length'] > limit:
        raise ValueError('Reconstructed output exceeds size limit')
    if patch['base_length'] != len(before) or patch['base_hash'] != text_hash(before):
        raise ValueError('Text patch base endpoint mismatch')
    edits = patch['edits']
    if not isinstance(edits, list) or len(edits) > MAX_PATCH_EDITS:
        raise ValueError('Patch edit count exceeds limit')
    cursor, last, output_bytes, output_length = 0, -1, len(valid_text(before)), len(before)
    for edit in edits:
        if not isinstance(edit, list) or len(edit) != 3:
            raise ValueError('Malformed text edit')
        start, delete, inserted = edit
        if type(start) is not int or type(delete) is not int or start < 0 or delete < 0:
            raise ValueError('Invalid text edit index')
        if start < cursor or start <= last or start + delete > len(before):
            raise ValueError('Overlapping, unordered or out-of-bounds text edit')
        inserted_bytes = len(valid_text(inserted))
        if inserted_bytes > limit:
            raise ValueError('Inserted text exceeds limit')
        output_bytes += inserted_bytes - len(valid_text(before[start:start + delete]))
        output_length += len(inserted) - delete
        cursor, last = start + delete, start
    if output_bytes > limit:
        raise ValueError('Reconstructed output exceeds byte limit')
    if output_length != patch['result_length']:
        raise ValueError('Text patch result length mismatch')
    pieces, cursor = [], 0
    for start, delete, inserted in edits:
        pieces.extend((before[cursor:start], inserted))
        cursor = start + delete
    pieces.append(before[cursor:])
    result = ''.join(pieces)
    if text_hash(result) != patch['result_hash']:
        raise ValueError('Text patch result endpoint mismatch')
    return result


def encode_envelope(envelope):
    raw = canonical(envelope).encode('utf-8')
    if len(raw) > MAX_RECONSTRUCTION_WORK_BYTES:
        raise ValueError('Envelope decoded work limit exceeded')
    wrapper = {'encoding': 'zlib-base64', 'hash': text_hash(raw.decode()),
               'payload': base64.b64encode(zlib.compress(raw)).decode('ascii')}
    return guard_comment(START + json.dumps(wrapper, sort_keys=True, separators=(',', ':')) + END)


def decode_envelope(body, *, budget=None):
    if not isinstance(body, str) or not body.startswith(START):
        return None
    if not body.endswith(END):
        raise ValueError('Malformed envelope wrapper')
    wrapper = strict_json(body[len(START):-len(END)])
    if not isinstance(wrapper, dict) or set(wrapper) != {'encoding', 'hash', 'payload'} or wrapper['encoding'] != 'zlib-base64':
        raise ValueError('Unsupported envelope encoding')
    raw = unpack(wrapper['payload'], MAX_RECONSTRUCTION_WORK_BYTES if budget is None else budget[0])
    if budget is not None:
        budget[0] -= len(raw)
    if text_hash(raw.decode('utf-8')) != wrapper['hash']:
        raise ValueError('Envelope content hash mismatch')
    result = strict_json(raw)
    if not isinstance(result, dict) or result.get('schema_version') != 2:
        raise ValueError('Unsupported envelope version')
    records = result.get('artifacts')
    if not isinstance(records, list) or len(records) > MAX_ARTIFACT_RECORDS:
        raise ValueError('Invalid envelope artifacts')
    identities = [r.get('hash') if isinstance(r, dict) else None for r in records]
    if any(not isinstance(x, str) for x in identities) or len(identities) != len(set(identities)):
        raise ValueError('Duplicate or malformed artifact records')
    return result


def encoded_size(value):
    return len(base64.b64encode(zlib.compress(canonical(value).encode('utf-8'))))


def text_record(before, after, *, limit=MAX_HISTORY_BYTES):
    patch = make_text_patch(before, after, limit=limit)
    delta = {'kind': 'delta', 'patch': patch}
    full = {'kind': 'full', 'base_hash': patch['base_hash'], 'result_hash': patch['result_hash'],
            'base_length': len(before), 'result_length': len(after), 'text': after}
    return delta if encoded_size(delta) < encoded_size(full) else full


def apply_text_record(before, record, *, limit=MAX_HISTORY_BYTES):
    if not isinstance(record, dict):
        raise ValueError('Malformed text record')
    if record.get('kind') == 'delta' and set(record) == {'kind', 'patch'}:
        return apply_text_patch(before, record['patch'], limit=limit)
    if set(record) != {'kind', 'base_hash', 'result_hash', 'base_length', 'result_length', 'text'} or record.get('kind') != 'full':
        raise ValueError('Unsupported text checkpoint')
    if any(type(record[k]) is not int or record[k] < 0 for k in ('base_length', 'result_length')):
        raise ValueError('Invalid text checkpoint lengths')
    if max(len(valid_text(before)), len(valid_text(record['text']))) > limit:
        raise ValueError('Text checkpoint decoded limit exceeded')
    if (record['base_hash'] != text_hash(before) or record['result_hash'] != text_hash(record['text'])
        or record['base_length'] != len(before) or record['result_length'] != len(record['text'])):
        raise ValueError('Text checkpoint endpoint mismatch')
    return record['text']


class ArtifactIndex:
    def __init__(self, comments, previous=None):
        self.comments = copy.deepcopy(comments)
        self.records = {}
        self.envelopes = []
        self.envelope_comments = []
        self.decoded = {}
        self.decode_sizes = {}
        budget = [MAX_RECONSTRUCTION_WORK_BYTES]
        for comment in comments:
            body = comment.get('body', '')
            cached = previous.decoded.get(body) if previous is not None else None
            before = budget[0]
            if cached is not None:
                budget[0] -= previous.decode_sizes[body]
                if budget[0] < 0:
                    raise ValueError('Aggregate decoded work limit exceeded')
            envelope, legacy = cached if cached is not None else (decode_envelope(body, budget=budget), None)
            if envelope is not None:
                self.envelopes.append(envelope)
                self.envelope_comments.append((comment, envelope))
                for record in envelope['artifacts']:
                    self.records.setdefault(record['hash'], []).append(record)
            elif body.startswith('<!-- zzzops-artifact '):
                if legacy is None:
                    marker = re.match(r'<!-- zzzops-artifact (sha256:[0-9a-f]{64}) -->', body)
                    match = re.search(r'```text\n([A-Za-z0-9+/=]+)\n```', body)
                    if not marker or not match:
                        raise ValueError('Malformed stored artifact')
                    raw = unpack(match[1], min(MAX_ARTIFACT_BYTES, budget[0]))
                    budget[0] -= len(raw)
                    value = strict_json(raw)
                    if not isinstance(value, dict) or set(value) != {'hash', 'content'} or value['hash'] != marker[1]:
                        raise ValueError('Malformed legacy artifact identity')
                    legacy = {'kind': 'legacy', **value}
                self.records.setdefault(legacy['hash'], []).append(legacy)
            self.decoded[body] = (envelope, legacy)
            self.decode_sizes[body] = before - budget[0]
        self.decode_work = MAX_RECONSTRUCTION_WORK_BYTES - budget[0]

    def resolve(self, identity):
        spent = self.decode_work
        def visit(key, active):
            nonlocal spent
            if key in active:
                raise ValueError('Cyclic artifact base')
            if len(active) > MAX_DELTA_DEPTH:
                raise ValueError('Artifact delta depth limit exceeded')
            records = self.records.get(key)
            if not records:
                raise ValueError('Missing artifact/base; persist the complete immutable content before referencing it')
            values, depths = [], []
            for record in records:
                spent += len(canonical(record).encode('utf-8'))
                if spent > MAX_RECONSTRUCTION_WORK_BYTES:
                    raise ValueError('Artifact reconstruction work limit exceeded')
                kind = record.get('kind')
                allowed = {'legacy': {'kind', 'hash', 'content'}, 'full': {'kind', 'hash', 'type', 'text'},
                           'delta': {'kind', 'hash', 'type', 'base', 'patch'}}
                if kind not in allowed or set(record) != allowed[kind]:
                    raise ValueError('Malformed artifact record fields')
                if kind == 'legacy':
                    value, depth = record['content'], 0
                elif kind == 'full':
                    value, depth = _from_text(record.get('type'), record.get('text')), 0
                elif kind == 'delta':
                    base, depth = visit(record.get('base'), active | {key})
                    base_type, base_text = _to_text(base)
                    if base_type != record.get('type'):
                        raise ValueError('Artifact delta base type mismatch')
                    value = _from_text(base_type, apply_text_patch(base_text, record.get('patch')))
                    depth += 1
                else:
                    raise ValueError('Unsupported artifact representation')
                raw = canonical(value).encode('utf-8')
                spent += len(raw)
                if len(raw) > MAX_ARTIFACT_BYTES or spent > MAX_RECONSTRUCTION_WORK_BYTES:
                    raise ValueError('Artifact decoded/reconstruction size limit exceeded')
                if digest(value) != key or record.get('hash') != key:
                    raise ValueError('Stored artifact content conflicts with its identity')
                values.append(value)
                depths.append(depth)
            if any(value != values[0] for value in values[1:]):
                raise ValueError('Conflicting stored artifact identity')
            return values[0], max(depths)
        value, depth = visit(identity, set())
        return copy.deepcopy(value), depth, spent

    def record(self, content, base=None):
        identity = digest(content)
        if identity in self.records:
            self.resolve(identity)
            return None
        kind, text = _to_text(content)
        if len(canonical(content).encode('utf-8')) > MAX_ARTIFACT_BYTES:
            raise ValueError('Artifact decoded content exceeds one megabyte; use a published Git content reference')
        full = {'hash': identity, 'kind': 'full', 'type': kind, 'text': text}
        if base and base in self.records:
            previous, depth, work = self.resolve(base)
            old_kind, old_text = _to_text(previous)
            if kind == old_kind and depth < MAX_DELTA_DEPTH:
                patch = make_text_patch(old_text, text)
                delta = {'hash': identity, 'kind': 'delta', 'type': kind, 'base': base, 'patch': patch}
                if work + len(canonical(delta).encode()) + len(canonical(content).encode()) <= MAX_RECONSTRUCTION_WORK_BYTES and encoded_size(delta) < encoded_size(full):
                    return delta
        return full


def _to_text(value):
    canonical(value)
    return ('text', value) if isinstance(value, str) else ('json', canonical(value))


def _from_text(kind, text):
    valid_text(text)
    if kind == 'text':
        return text
    if kind != 'json':
        raise ValueError('Unsupported artifact type')
    value = strict_json(text)
    if canonical(value) != text:
        raise ValueError('Noncanonical structured artifact serialization')
    return value


def pack_envelopes(common, artifacts, history=None):
    if len(artifacts) > MAX_ARTIFACT_RECORDS:
        raise ValueError('Transaction artifact record limit exceeded')
    pieces = [('artifact', record) for record in artifacts]
    if history is not None:
        pieces.append(('history', history))
    manifest = [digest({'kind': kind, 'value': value}) for kind, value in pieces]
    groups, current = [], []
    def envelope(group, part):
        return {'schema_version': 2, **common, 'part': part, 'manifest': manifest,
                'members': [index for index, _, _ in group],
                'artifacts': [value for _, kind, value in group if kind == 'artifact'],
                'history': next((value for _, kind, value in group if kind == 'history'), None)}
    for index, (kind, value) in enumerate(pieces):
        candidate = current + [(index, kind, value)]
        try:
            encode_envelope(envelope(candidate, len(groups)))
        except ValueError:
            if not current:
                raise
            groups.append(current)
            current = [(index, kind, value)]
            encode_envelope(envelope(current, len(groups)))
        else:
            current = candidate
    if current:
        groups.append(current)
    bodies = [encode_envelope(envelope(group, part)) for part, group in enumerate(groups)]
    if sum(len(body) for body in bodies) > MAX_RECONSTRUCTION_WORK_BYTES:
        raise ValueError('Transaction reconstruction work limit exceeded')
    return bodies


def preflight_comments(comments, bodies, references=(), *, previous=None):
    """Validate the exact prospective reader view before any provider write."""
    existing = {comment.get('body', '') for comment in comments}
    prospective = list(comments) + [{'body': body} for body in bodies if body not in existing]
    try:
        stored = ArtifactIndex(comments, previous=previous)
        index = ArtifactIndex(prospective, previous=previous)
        required = set(references)
        # Preserve currently readable immutable records. An already broken old
        # chain must not prevent an independent checkpoint; required references
        # remain mandatory regardless of their prior readability.
        for identity in set(stored.records) - required:
            try:
                stored.resolve(identity)
            except ValueError:
                continue
            required.add(identity)
        for identity in required:
            index.resolve(identity)
    except ValueError as exc:
        raise ValueError(
            f'Prospective comment/artifact validation failed (decoded/reconstruction limit '
            f'{MAX_RECONSTRUCTION_WORK_BYTES} bytes): {exc}. '
            'Use a published Git content reference; no comments were appended.'
        ) from exc
    return index


def verify_manifest(envelopes):
    if not envelopes:
        raise ValueError('Missing transaction envelope')
    manifest = envelopes[0].get('manifest')
    seen, parts = {}, set()
    for env in envelopes:
        if env.get('manifest') != manifest or env.get('part') in parts:
            raise ValueError('Conflicting/duplicate transaction envelope')
        parts.add(env.get('part'))
        values = [('artifact', x) for x in env['artifacts']]
        if env.get('history') is not None:
            values.append(('history', env['history']))
        if len(values) != len(env.get('members', [])):
            raise ValueError('Malformed envelope manifest membership')
        for index, (kind, value) in zip(env['members'], values):
            if type(index) is not int or not isinstance(manifest, list) or not 0 <= index < len(manifest) or index in seen:
                raise ValueError('Duplicate/invalid envelope member')
            if digest({'kind': kind, 'value': value}) != manifest[index]:
                raise ValueError('Envelope record identity mismatch')
            seen[index] = True
    if set(seen) != set(range(len(manifest))) or parts != set(range(len(parts))):
        raise ValueError('Incomplete transaction envelope')
