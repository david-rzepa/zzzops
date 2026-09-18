"""Ephemeral, exact policy excerpts for actionable public workflow steps.

These files are disclosure, never authority. Policy freshness and phase evidence
still use the canonical reviewed policy. No excerpts enter the working tree.
"""
from __future__ import annotations

import hashlib
import json
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
    return step.get('kind') in WORK_KINDS or (
        step.get('kind') == 'human_approval'
        and step.get('submission', {}).get('operation') != 'policy_approve'
    )


def needs_context(result):
    return any(actionable(step) for step in steps(result))


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
    if step.get('kind') == 'review':
        selected.update({'code_quality', 'verification_testing'})
    return selected


def attach(result, repo, project, *, source, temporary_root=None):
    """Attach local file references, preserving exact section values and order.

    A private temporary directory belongs to one invocation. Identical excerpts
    share a file within that invocation; a later invocation regenerates them.
    The OS/user may reclaim these files after the assigned work has finished.
    """
    sections = project.get('policy', {}).get('sections', [])
    available = {section['id'] for section in sections}
    directory = None
    references = {}
    for step in steps(result):
        if not actionable(step):
            continue
        selected = section_ids(step, source, available)
        blocks = [section for section in sections if section['id'] in selected]
        if not blocks:
            continue
        content = (json.dumps({'sections': blocks}, ensure_ascii=False, sort_keys=True,
                              indent=2) + '\n').encode('utf-8')
        sha256 = hashlib.sha256(content).hexdigest()
        if sha256 not in references:
            if directory is None:
                directory = Path(tempfile.mkdtemp(prefix='zzzops-policy-', dir=temporary_root)).resolve()
                if directory.is_relative_to(Path(repo).resolve()):
                    directory.rmdir()
                    raise ValueError('Policy excerpts require a temporary directory outside the repository')
            path = directory / (sha256 + '.json')
            # mkdtemp gives private directory permissions; exclusive creation
            # avoids replacing any prior file, including through a symlink.
            with path.open('xb') as handle:
                handle.write(content)
            references[sha256] = {'path': str(path), 'sha256': sha256,
                                  'sections': [section['id'] for section in blocks]}
        step['policy'] = dict(references[sha256])
    return result
