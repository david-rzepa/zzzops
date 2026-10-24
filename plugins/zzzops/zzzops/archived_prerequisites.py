"""Bounded observations for an explicitly named archived prerequisite.

This module produces a candidate for independent review. It never turns a
closed issue or a merged pull request into an execution grant by itself.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any


class ArchivedPrerequisiteError(ValueError):
    """The exact historical evidence cannot support a terminal candidate."""


def digest(value: Any) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':')).encode('utf-8')
    return 'sha256:' + hashlib.sha256(data).hexdigest()


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise ArchivedPrerequisiteError(reason)


def _label_names(issue: dict) -> set[str]:
    return {row['name'] if isinstance(row, dict) else row
            for row in issue.get('labels', [])
            if isinstance(row, str) or isinstance(row, dict) and isinstance(row.get('name'), str)}


def _ref(value: Any, repository: str, goal: int, *, git: bool = False) -> bool:
    if not isinstance(value, dict) or set(value) != {'hash', 'uri'}:
        return False
    h, uri = value['hash'], value['uri']
    if not isinstance(h, str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', h):
        return False
    if not isinstance(uri, str):
        return False
    if git:
        match = re.fullmatch(r'git:([0-9a-f]{40}):(.+)', uri)
        return bool(match and not match[2].startswith('/') and '..' not in match[2].split('/'))
    return uri == f'zzzops:{repository}:goal:{goal}:{h}'


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ArchivedPrerequisiteError('Historical JSON has duplicate keys')
        value[key] = item
    return value


def _published_json(raw: bytes, reference: dict) -> dict:
    _require(isinstance(raw, bytes) and len(raw) <= 1048576
             and 'sha256:' + hashlib.sha256(raw).hexdigest() == reference['hash'],
             'Historical published Git bytes changed or exceed the size bound')
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique_object)
    except (UnicodeError, ValueError) as exc:
        raise ArchivedPrerequisiteError('Historical published JSON is invalid') from exc
    _require(isinstance(value, dict), 'Historical published artifact must be an object')
    return value


def candidate(*, repository: str, goal: int, integration_branch: str,
              issue: dict, envelope: dict, archived_payload: dict,
              receipt: dict, migration_response: dict, target_intent: dict,
              target_payload: dict, source_bytes: bytes,
              policy_bytes: bytes, pull_number: int, pull: dict,
              merge_reachable: bool) -> dict:
    """Validate exact observations without hydrating the archived phase DAG.

    The caller must supply content fetched from the receipt's published Git
    refs and a provider pull request fetched by ``pull_number``. A separate
    reviewed apply operation must authenticate and adopt this candidate.
    """
    _require(type(goal) is int and goal > 0 and isinstance(repository, str)
             and bool(repository) and isinstance(integration_branch, str)
             and bool(integration_branch), 'Archived prerequisite identity is invalid')
    _require(isinstance(issue, dict) and isinstance(envelope, dict),
             'Archived prerequisite issue or envelope is malformed')
    markers = list(re.finditer(r'<!-- zzzops-goal\s*\n(.*?)\nzzzops-goal -->',
                               issue.get('body') or '', re.DOTALL))
    _require(len(markers) == 1, 'Archived issue must contain one managed goal block')
    try:
        body_envelope = json.loads(markers[0].group(1), object_pairs_hook=_unique_object)
    except ValueError as exc:
        raise ArchivedPrerequisiteError('Archived issue envelope is malformed') from exc
    _require(body_envelope == envelope,
             'Archived envelope differs from the current provider issue body')
    _require(issue.get('number') == goal and str(issue.get('state', '')).lower() == 'closed'
             and isinstance(issue.get('closed_at'), str) and bool(issue['closed_at']),
             'Archived prerequisite is not closed by the provider')
    statuses = {name for name in _label_names(issue) if name.startswith('zzzops:status:')}
    _require(statuses == {'zzzops:status:done'},
             'Archived prerequisite provider status is missing or ambiguous')
    _require(envelope.get('schema_version') == 2 and envelope.get('repository') == repository
             and envelope.get('issue') == goal and envelope.get('state') == 'archived'
             and type(envelope.get('revision')) is int and envelope['revision'] > 0
             and _ref(envelope.get('payload'), repository, goal),
             'Archived prerequisite envelope is not an exact same-repository archive')
    _require(isinstance(archived_payload, dict)
             and digest(archived_payload) == envelope['payload']['hash'],
             'Archived prerequisite payload is not bound to its envelope')
    _require(isinstance(receipt, dict) and receipt.get('type') == 'schema_migration'
             and receipt.get('converter') == 'manual-reconciliation-522/1'
             and receipt.get('repository') == repository and receipt.get('goal') == goal,
             'Historical migration converter or identity is unsupported')
    _require(_ref(receipt.get('source'), repository, goal, git=True)
             and _ref(receipt.get('policy'), repository, goal, git=True)
             and _ref(receipt.get('target_intent'), repository, goal)
             and _ref(receipt.get('target_payload'), repository, goal)
             and isinstance(receipt.get('reason'), str) and bool(receipt['reason'])
             and isinstance(receipt.get('missing_obligations'), list)
             and bool(receipt['missing_obligations'])
             and all(isinstance(text, str) and bool(text) for text in receipt['missing_obligations']),
             'Historical migration receipt lacks exact source, target or retained obligations')
    source = _published_json(source_bytes, receipt['source'])
    _published_json(policy_bytes, receipt['policy'])
    _require(isinstance(source, dict) and source.get('type') == 'migration_source'
             and source.get('producer') is None
             and isinstance(source.get('content'), dict)
             and source['content'].get('number') == goal
             and isinstance(source['content'].get('body'), str)
             and isinstance(source.get('provenance'), dict)
             and source['provenance'].get('actor') == 'manual-schema-reconciliation-522',
             'Historical migration source identity is unsupported')
    _require(isinstance(source['provenance'].get('policy'), str)
             and re.fullmatch(r'sha256:[0-9a-f]{64}', source['provenance']['policy']) is not None,
             'Historical source policy provenance is malformed')
    # The manual source names the policy that governed the old issue. The
    # receipt publishes the newer migration policy, so these hashes can differ.
    # Neither policy hash grants terminal authority without independent review.
    receipt_ref = {'hash': digest(receipt),
                   'uri': f'zzzops:{repository}:goal:{goal}:{digest(receipt)}'}
    response_ref = {'hash': digest(migration_response),
                    'uri': f'zzzops:{repository}:goal:{goal}:{digest(migration_response)}'}
    _require(migration_response == {'next_steps': [{'kind': 'schema_migration',
        'goal': goal, 'status': 'migrated', 'receipt': receipt_ref}]},
        'Historical migration response does not bind the exact receipt')
    _require(isinstance(target_intent, dict) and digest(target_intent) == receipt['target_intent']['hash']
             and target_intent == {'schema_version': 2, 'repository': repository,
                'issue': goal, 'revision': envelope['revision'] - 1,
                'state': 'open', 'parent': envelope.get('parent'),
                'payload': receipt['target_payload']},
             'Historical migration target intent is not the archived predecessor')
    _require(isinstance(target_payload, dict)
             and digest(target_payload) == receipt['target_payload']['hash']
             and target_payload.get('operational') == {'leases': [], 'receipts': []},
             'Historical migration target payload is malformed')
    final_expected = json.loads(json.dumps(target_payload))
    operational = archived_payload.get('operational') if isinstance(archived_payload, dict) else None
    committed = operational.get('receipts') if isinstance(operational, dict) else None
    _require(isinstance(committed, list) and len(committed) == 1
             and isinstance(committed[0], dict)
             and isinstance(committed[0].get('request'), str) and bool(committed[0]['request'])
             and isinstance(committed[0].get('payload'), str)
             and re.fullmatch(r'sha256:[0-9a-f]{64}', committed[0]['payload']) is not None
             and committed[0].get('result') == response_ref,
             'Archived payload lacks the exact committed migration response')
    final_expected['operational']['receipts'] = committed
    _require(archived_payload == final_expected,
             'Archived payload differs from the committed migration target')
    _require(type(pull_number) is int and pull_number > 0 and isinstance(pull, dict)
             and pull.get('number') == pull_number
             and pull.get('baseRepository') == repository
             and pull.get('state') == 'MERGED'
             and pull.get('baseRefName') == integration_branch
             and isinstance(pull.get('mergedAt'), str) and bool(pull['mergedAt'])
             and isinstance(pull.get('headRefOid'), str)
             and re.fullmatch(r'[0-9a-f]{40}', pull['headRefOid']) is not None
             and isinstance(pull.get('mergeCommit'), dict)
             and isinstance(pull['mergeCommit'].get('oid'), str)
             and re.fullmatch(r'[0-9a-f]{40}', pull['mergeCommit']['oid']) is not None,
             'Historical pull request is not merged into the reviewed integration branch')
    _require(merge_reachable is True, 'Historical merge commit is not reachable from integration')
    issue_text = issue.get('body') or ''
    pull_text = pull.get('body') or ''
    plain_link = re.search(rf'(?i)\b(?:PR|pull request)\s+#?{pull_number}\b', issue_text)
    markdown_link = re.search(rf'(?i)\b(?:PR|pull request)\s+\[#{pull_number}\]'
        rf'\(https://github\.com/{re.escape(repository)}/pull/{pull_number}\)', issue_text)
    _require((plain_link is not None or markdown_link is not None)
             and re.search(rf'(?i)\b(?:refs|closes|fixes)\s+#?{goal}\b', pull_text) is not None,
             'Historical pull request is not explicitly linked to the archived goal')
    observation = {
        'repository': repository, 'goal': goal,
        'envelope': digest(envelope), 'payload': envelope['payload'],
        'closed_at': issue['closed_at'], 'provider_state': 'closed',
        'migration_receipt': digest(receipt), 'source': receipt['source'],
        'policy': receipt['policy'], 'pull': pull_number,
        'pull_head': pull.get('headRefOid'),
        'merge_commit': pull['mergeCommit']['oid'], 'merged_at': pull['mergedAt'],
        'integration_branch': integration_branch,
    }
    return {'kind': 'archived_prerequisite_candidate', 'identity': digest(observation),
            'observation': observation, 'requires_independent_review': True}
