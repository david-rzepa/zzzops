"""Cached, exact policy excerpts for actionable public workflow steps.

These files are disclosure, never authority. Policy freshness and phase evidence
still use the canonical reviewed policy. No excerpts enter the working tree.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile


COMMON = {'security_privacy_compliance', 'documentation_style',
          'autonomy_approval_parallelism', 'automated_design'}
PHASES = {
    'understand': {'engineering_rigor', 'workflow_adherence', 'git_review_release'},
    'decompose': {'engineering_rigor', 'workflow_adherence', 'git_review_release'},
    'plan': {'engineering_rigor', 'code_quality', 'dependencies_tooling',
             'verification_testing', 'git_review_release', 'deployment_resources'},
    'test_design': {'engineering_rigor', 'code_quality', 'dependencies_tooling',
                    'verification_testing', 'git_review_release'},
    'implement': {'engineering_rigor', 'code_quality', 'dependencies_tooling',
                  'verification_testing', 'git_review_release', 'deployment_resources'},
    'publish': {'git_review_release', 'verification_testing', 'dependencies_tooling',
                'deployment_resources'},
}
WORK_KINDS = {'execute', 'review', 'assess', 'perform', 'capture', 'dispatch', 'adopt',
              'specify', 'integration', 'publication_setup', 'repair_stack', 'complete',
              'feedback_prepare', 'suggest', 'heartbeat', 'record_result', 'record_review',
              'correct', 'capability_discovery', 'inspect_evidence', 'recover_legacy',
              'repair', 'blocker', 'session_override'}


def steps(result):
    for step in result.get('next_steps', []):
        yield step
        yield from steps(step)


def actionable(step):
    # A policy-proposal approval is a prerequisite, not work under that policy.
    if step.get('kind') in {'await_worker', 'recover'}:
        # Restore missing policy files for an already assigned worker too.
        return bool(step.get('phase')) and step.get('lease', {}).get('kind') in {'execute', 'review', 'human_approval'}
    return step.get('kind') in WORK_KINDS or (
        step.get('kind') == 'human_approval'
        and step.get('submission', {}).get('operation') != 'policy_approve'
    )


def needs_context(result):
    return any(actionable(step) for step in steps(result))


def temporary_directory(repo, root=None):
    directory = Path(tempfile.mkdtemp(prefix='zzzops-policy-', dir=root)).resolve()
    if directory.is_relative_to(Path(repo).resolve()):
        directory.rmdir()
        raise ValueError('Policy excerpts require a temporary directory outside the repository')
    return directory


def write_inspection(repo, inspection):
    """Keep unreviewed policy inspection out of stdout, including in preview."""
    content = (json.dumps(inspection, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')
    path = temporary_directory(repo) / 'inspection.json'
    with path.open('xb') as handle:
        handle.write(content)
    return {'path': str(path), 'sha256': hashlib.sha256(content).hexdigest()}


def section_ids(step, source, available):
    selected = set(COMMON)
    phase = step.get('phase')
    if phase:
        # Custom DAG phases must not silently lose a relevant project constraint.
        selected.update(PHASES.get(phase, available))
    elif step.get('kind') in {'capture', 'specify'} or source == '$add-zzzops-goal':
        selected.update({'engineering_rigor', 'workflow_adherence', 'git_review_release'})
    elif step.get('kind') in {'integration', 'publication_setup', 'repair_stack', 'complete'}:
        selected.update({'git_review_release', 'verification_testing', 'deployment_resources'})
    elif source == '$send-zzzops-feedback':
        pass
    elif source == '$suggest-zzzops-work':
        selected.update({'code_quality', 'verification_testing', 'engineering_rigor'})
    else:
        selected.update(available)
    if step.get('kind') in {'assess', 'capability_discovery', 'session_override'}:
        selected.update({'model_routing', 'engineering_rigor'})
    if step.get('lease', {}).get('kind', step.get('kind')) in {'review', 'human_approval'}:
        selected.update({'code_quality', 'verification_testing'})
    return selected


def disclosure(project, step, *, source='$execute-zzzops'):
    """Derive a stable receipt from precisely the instructions being disclosed.

    This is a read acknowledgment, not a secret or proof of compliance. The
    public file hash includes the receipt and cannot itself serve as the receipt.
    """
    sections = project.get('policy', {}).get('sections', [])
    available = {section['id'] for section in sections}
    selected = section_ids(step, source, available)
    blocks = [
        {key: section[key] for key in ('id', 'title', 'instructions', 'exceptions') if key in section}
        for section in sections
        if section['id'] in selected and section.get('applicable') is not False
    ]
    canonical = json.dumps({'sections': blocks}, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    receipt = hashlib.sha256(('zzzops-policy-read-v1\n' + canonical).encode('utf-8')).hexdigest()
    return {'sections': blocks, 'policy_receipt': receipt}


def require_receipt(project, step, payload):
    expected = disclosure(project, step)['policy_receipt']
    if payload.get('policy_receipt') != expected:
        raise ValueError('Missing or stale policy_receipt: request the current checkpoint, read policy.path, and copy its policy_receipt into the start or bind request')


def cache_root():
    # Do not trust a redirected/shared Windows TEMP for reusable private files.
    # The standard profile subtree inherits the user's private profile ACL.
    return Path.home() / 'AppData' / 'Local' / 'Temp' if os.name == 'nt' else Path(tempfile.gettempdir())


def cached_file(repo, content, root=None):
    """Reuse immutable content outside the repository, including across runs."""
    user = hashlib.sha256(str(Path.home()).encode('utf-8')).hexdigest()[:16]
    directory = Path(root or cache_root()) / ('zzzops-policy-cache-' + user)
    if directory.resolve().is_relative_to(Path(repo).resolve()):
        raise ValueError('Policy excerpts require a temporary directory outside the repository')
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError('Policy cache must be a private directory')
    if os.name != 'nt' and (directory.stat().st_uid != os.getuid() or directory.stat().st_mode & 0o077):
        raise ValueError('Policy cache must be owned by the current user with private permissions')
    sha256 = hashlib.sha256(content).hexdigest()
    path = directory / (sha256 + '.json')
    if path.is_symlink():
        raise ValueError('Policy cache file must not be a symlink')
    if path.exists():
        if path.read_bytes() != content:
            raise ValueError('Policy cache content changed; remove the damaged cached file and request a fresh checkpoint')
    else:
        # Publish a complete file atomically. Concurrent writers derive identical
        # bytes; readers never observe a partially written policy.
        with tempfile.NamedTemporaryFile(dir=directory, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(content)
        try:
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
    return {'path': str(path.resolve()), 'sha256': sha256}


def attach(result, repo, project, *, source, temporary_root=None):
    """Disclose cached agent instructions and an in-file-only read receipt."""
    for step in steps(result):
        if not actionable(step):
            continue
        document = disclosure(project, step, source=source)
        if not document['sections']:
            continue
        content = (json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')
        step['policy'] = {**cached_file(repo, content, temporary_root),
                          'sections': [section['id'] for section in document['sections']]}
    return result
