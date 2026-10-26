"""Local Git facts for a commit-backed workspace phase.

This validator grants no workflow authority. The goal's reviewed allocation,
lease, verification, independent review and acceptance receipt must still bind
the exact returned commits before a result can become current.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
import hashlib
import json
import os
import re
import subprocess
import tempfile


_COMMIT = re.compile(r'[0-9a-f]{40}\Z')
_NODE = re.compile(r'[A-Za-z0-9_.-]+\Z')
_ATTEMPT = re.compile(r'[0-9a-f]{32}\Z')
_ORDINARY_MODES = {b'100644', b'100755'}


def _git(repo: Path, *arguments: str) -> bytes:
    result = subprocess.run(['git', *arguments], cwd=repo, capture_output=True)
    if result.returncode:
        raise ValueError('Git checkpoint could not verify the requested repository object')
    return result.stdout


def _commit(repo: Path, oid: str) -> None:
    if not isinstance(oid, str) or not _COMMIT.fullmatch(oid):
        raise ValueError('Git checkpoint requires an exact commit identity')
    if _git(repo, 'cat-file', '-t', oid).strip() != b'commit':
        raise ValueError('Git checkpoint identity is not a commit')


def _owned_path(path: str) -> bool:
    if not isinstance(path, str) or not path or '\x00' in path or '\\' in path:
        return False
    parsed = PurePosixPath(path)
    return (not parsed.is_absolute() and parsed.as_posix() == path
            and all(part not in ('.', '..') for part in path.split('/')))


def validate_checkpoint(repo: Path, *, base_commit: str, result_commit: str,
                        owned_paths: list[str], require_clean_worktree: bool = True) -> dict:
    """Verify one result commit against its exact base and reviewed path scope.

    File names are observed only in the local Git diff and are never returned
    as a checkpoint inventory. External receipts must prove task authority,
    tests, and remote retention separately.
    """
    repo = Path(repo).resolve()
    top = Path(_git(repo, 'rev-parse', '--show-toplevel').decode().strip()).resolve()
    if top != repo:
        raise ValueError('Git checkpoint requires the exact managed worktree root')
    if not isinstance(owned_paths, list) or any(not _owned_path(path) for path in owned_paths) or len(set(owned_paths)) != len(owned_paths):
        raise ValueError('Git checkpoint requires distinct canonical reviewed owned paths')
    _commit(repo, base_commit)
    _commit(repo, result_commit)
    parents = _git(repo, 'rev-list', '--parents', '-n', '1', result_commit).decode().split()
    if parents != [result_commit, base_commit]:
        raise ValueError('Git phase result must have the exact parent base commit')
    if require_clean_worktree:
        if _git(repo, 'rev-parse', 'HEAD').decode().strip() != result_commit:
            raise ValueError('Git phase result must be the managed worktree HEAD')
        dirty = _git(repo, 'status', '--porcelain=v1', '-z', '--untracked-files=all',
                     '--', '.', ':(exclude).zzzops')
        if dirty:
            raise ValueError('Git phase result requires a clean worktree')
    changed = _git(repo, 'diff', '--name-only', '--no-renames', '-z', base_commit, result_commit)
    try:
        paths = [name.decode('utf-8') for name in changed.split(b'\x00') if name]
    except UnicodeDecodeError as exc:
        raise ValueError('Git phase result contains a non-UTF-8 path') from exc
    if any(not _owned_path(path) or path not in owned_paths for path in paths):
        raise ValueError('Git phase result changed files outside reviewed owned paths')
    for path in paths:
        entry = _git(repo, 'ls-tree', '-z', result_commit, '--', path)
        if not entry:
            continue  # A deletion is an ordinary scoped output.
        metadata, name = entry.rstrip(b'\x00').split(b'\t', 1)
        mode, kind, _oid = metadata.split()
        if name.decode('utf-8') != path or kind != b'blob' or mode not in _ORDINARY_MODES:
            raise ValueError('Git phase result requires ordinary files in its output scope')
    return {
        'base_commit': base_commit,
        'base_tree': _git(repo, 'rev-parse', base_commit + '^{tree}').decode().strip(),
        'result_commit': result_commit,
        'result_tree': _git(repo, 'rev-parse', result_commit + '^{tree}').decode().strip(),
        'change_count': len(paths),
    }


def _remote_ref(repo: Path, remote: str, ref: str) -> str | None:
    observation = subprocess.run(['git', 'ls-remote', '--exit-code', '--refs', remote, ref],
                                 cwd=repo, capture_output=True, timeout=30)
    if observation.returncode == 2 and not observation.stdout:
        return None
    if observation.returncode:
        raise ValueError('Cannot confirm the exact remote attempt ref')
    rows = observation.stdout.decode('ascii').splitlines()
    if len(rows) != 1:
        raise ValueError('Remote attempt ref observation is ambiguous')
    values = rows[0].split('\t')
    if len(values) != 2 or values[1] != ref or not _COMMIT.fullmatch(values[0]):
        raise ValueError('Remote attempt ref identity is malformed')
    return values[0]


def retain_attempt_ref(repo: Path, *, remote: str, goal: int, node: str,
                       attempt: str, commit: str) -> dict:
    """Create an immutable remote attempt branch; never infer acceptance from it.

    An uncertain push is resolved by observing the exact ref. A missing ref
    gets one create-only retry; a moved ref stops without overwriting it.
    """
    repo = Path(repo).resolve()
    if (not isinstance(remote, str) or not _NODE.fullmatch(remote)
            or type(goal) is not int or goal <= 0
            or not isinstance(node, str) or not _NODE.fullmatch(node)
            or not isinstance(attempt, str) or not _ATTEMPT.fullmatch(attempt)):
        raise ValueError('Invalid remote attempt identity')
    _commit(repo, commit)
    ref = f'refs/heads/zzzops/attempts/{goal}/{node}/{attempt}'
    previous = _remote_ref(repo, remote, ref)
    if previous == commit:
        return {'ref': ref, 'commit': commit, 'outcome': 'existing'}
    if previous is not None:
        raise ValueError('Remote attempt ref already names a different commit')
    for retry in range(2):
        uncertain = False
        try:
            pushed = subprocess.run(
                ['git', 'push', '--porcelain', f'--force-with-lease={ref}:',
                 remote, f'{commit}:{ref}'], cwd=repo, capture_output=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired):
            uncertain = True
            pushed = None
        observed = _remote_ref(repo, remote, ref)
        if observed == commit:
            return {'ref': ref, 'commit': commit,
                    'outcome': 'observed_after_uncertain_push' if uncertain else 'created'}
        if observed is not None:
            raise ValueError('Remote attempt ref moved to a different commit')
        if not uncertain or retry:
            raise ValueError('Remote attempt ref was not retained')
    raise ValueError('Remote attempt ref was not retained')


def verify_attempt_ref(repo: Path, *, remote: str, ref: str, commit: str) -> None:
    """Read-only check that the retained attempt still names its exact commit."""
    if (not isinstance(remote, str) or not _NODE.fullmatch(remote)
            or not isinstance(ref, str) or not re.fullmatch(
                r'refs/heads/zzzops/attempts/[1-9][0-9]*/[A-Za-z0-9_.-]+/[0-9a-f]{32}', ref)
            or not isinstance(commit, str) or not _COMMIT.fullmatch(commit)):
        raise ValueError('Invalid retained attempt identity')
    if _remote_ref(Path(repo).resolve(), remote, ref) != commit:
        raise ValueError('Retained attempt ref is missing or moved')


def _scope_hash(paths: list[str]) -> str:
    if not isinstance(paths, list) or any(not _owned_path(path) for path in paths) or len(set(paths)) != len(paths):
        raise ValueError('Compaction requires distinct canonical reviewed paths')
    raw = json.dumps(sorted(paths), ensure_ascii=False, separators=(',', ':')).encode()
    return 'sha256:' + hashlib.sha256(raw).hexdigest()


def _scoped_change_count(repo: Path, before: str, after: str, paths: list[str]) -> int:
    changed = _git(repo, 'diff', '--name-only', '--no-renames', '-z', before, after)
    try:
        names = [name.decode('utf-8') for name in changed.split(b'\x00') if name]
    except UnicodeDecodeError as exc:
        raise ValueError('Compaction contains a non-UTF-8 path') from exc
    if any(not _owned_path(name) or name not in paths for name in names):
        raise ValueError('Compaction changes files outside reviewed owned paths')
    for name in names:
        entry = _git(repo, 'ls-tree', '-z', after, '--', name)
        if entry:
            metadata, listed = entry.rstrip(b'\x00').split(b'\t', 1)
            mode, kind, _oid = metadata.split()
            if listed.decode('utf-8') != name or kind != b'blob' or mode not in _ORDINARY_MODES:
                raise ValueError('Compaction requires ordinary scoped files')
    return len(names)


def _project_owned_tree(repo: Path, *, base_commit: str, source_commit: str,
                        owned_paths: list[str]) -> str:
    """Apply only a reviewed phase's final paths to a disposable Git index."""
    if not isinstance(owned_paths, list) or not owned_paths:
        raise ValueError('Projected candidate phase requires reviewed owned paths')
    _scope_hash(owned_paths)
    changed = set(_git(repo, 'diff', '--name-only', '--no-renames', '-z',
                       base_commit, source_commit).split(b'\x00'))
    selected = [path for path in owned_paths if path.encode('utf-8') in changed]
    with tempfile.TemporaryDirectory(prefix='zzzops-candidate-index-') as directory:
        environment = {**os.environ, 'GIT_INDEX_FILE': str(Path(directory) / 'index')}
        pathspec = Path(directory) / 'owned-paths'
        if selected:
            pathspec.write_bytes(b'\x00'.join(path.encode('utf-8') for path in selected) + b'\x00')
        def isolated(*arguments, input_bytes=None):
            result = subprocess.run(['git', *arguments], cwd=repo, env=environment,
                                    input=input_bytes, capture_output=True)
            if result.returncode:
                raise ValueError('Git could not project the reviewed phase into a candidate tree')
            return result.stdout
        isolated('read-tree', base_commit)
        if selected:
            isolated('restore', '--source=' + source_commit, '--staged',
                     '--pathspec-from-file=' + str(pathspec), '--pathspec-file-nul')
        return isolated('write-tree').decode().strip()


def compaction_base_from_attempts(repo: Path, *, goal: int, test_source: str,
                                  attempts: list[dict], remote: str,
                                  phase: str = 'test_design') -> str:
    """Find the base before the earliest retained attempt on the final line."""
    repo = Path(repo).resolve()
    if (type(goal) is not int or goal <= 0 or not isinstance(attempts, list)
            or not attempts or not isinstance(phase, str) or not _NODE.fullmatch(phase)):
        raise ValueError('Compaction requires retained phase attempts')
    _commit(repo, test_source)
    earliest = test_source
    found_source = False
    for attempt in attempts:
        if (not isinstance(attempt, dict) or set(attempt) != {'ref', 'commit'}
                or not attempt['ref'].startswith(f'refs/heads/zzzops/attempts/{goal}/{phase}/')):
            raise ValueError('Compaction phase attempt identity is malformed')
        verify_attempt_ref(repo, remote=remote, **attempt)
        commit = attempt['commit']
        if commit == test_source:
            found_source = True
        if subprocess.run(['git', 'merge-base', '--is-ancestor', commit, test_source],
                          cwd=repo, capture_output=True).returncode:
            continue  # An abandoned branch stays retained but is not in the final candidate.
        if subprocess.run(['git', 'merge-base', '--is-ancestor', commit, earliest],
                          cwd=repo, capture_output=True).returncode == 0:
            earliest = commit
    if not found_source:
        raise ValueError('Final phase source lacks its exact retained attempt ref')
    parents = _git(repo, 'rev-list', '--parents', '-n', '1', earliest).decode().split()
    if len(parents) != 2:
        raise ValueError('Earliest phase attempt must have exactly one base parent')
    return parents[1]


def _compaction_facts(repo: Path, *, goal: int, base_commit: str, test_source: str,
                      implementation_source: str, test_owned: list[str],
                      implementation_owned: list[str], retained_attempts: list[dict],
                      remote: str) -> dict:
    if type(goal) is not int or goal <= 0 or not isinstance(retained_attempts, list) or not retained_attempts:
        raise ValueError('Compaction requires a positive goal and retained attempts')
    for commit in (base_commit, test_source, implementation_source):
        _commit(repo, commit)
    for earlier, later in ((base_commit, test_source), (test_source, implementation_source)):
        if subprocess.run(['git', 'merge-base', '--is-ancestor', earlier, later],
                          cwd=repo, capture_output=True).returncode:
            raise ValueError('Compaction sources must follow the exact goal stack ancestry')
    if set(test_owned).intersection(implementation_owned):
        raise ValueError('Compaction RED and GREEN owned scopes overlap')
    _scope_hash(test_owned)
    _scope_hash(implementation_owned)
    _scoped_change_count(repo, base_commit, implementation_source,
                         test_owned + implementation_owned)
    test_tree = _project_owned_tree(repo, base_commit=base_commit,
        source_commit=test_source, owned_paths=test_owned)
    if not _scoped_change_count(repo, base_commit, test_tree, test_owned):
        raise ValueError('Compaction has no reviewed RED test changes')
    if not _scoped_change_count(repo, test_source, implementation_source, implementation_owned):
        raise ValueError('Compaction has no reviewed GREEN implementation changes')
    seen = set()
    final_refs = {'test_design': False, 'implement': False}
    for attempt in retained_attempts:
        if (not isinstance(attempt, dict) or set(attempt) != {'ref', 'commit'}
                or attempt['ref'] in seen
                or not attempt['ref'].startswith(f'refs/heads/zzzops/attempts/{goal}/')):
            raise ValueError('Compaction retained attempt list is malformed')
        seen.add(attempt['ref'])
        match = re.fullmatch(
            rf'refs/heads/zzzops/attempts/{goal}/(test_design|implement)/[0-9a-f]{{32}}',
            attempt['ref'])
        if not match:
            raise ValueError('Compaction retained attempt phase is not a reviewed group')
        verify_attempt_ref(repo, remote=remote, **attempt)
        phase = match.group(1)
        parent = _git(repo, 'rev-list', '--parents', '-n', '1', attempt['commit']).decode().split()
        if len(parent) != 2:
            raise ValueError('Compaction retained attempt must have one exact parent')
        _scoped_change_count(repo, parent[1], attempt['commit'],
                             test_owned if phase == 'test_design' else implementation_owned)
        if attempt['commit'] == (test_source if phase == 'test_design' else implementation_source):
            final_refs[phase] = True
    if not all(final_refs.values()):
        raise ValueError('Compaction must retain both final source attempts by phase')
    raw_attempts = json.dumps(retained_attempts, sort_keys=True, separators=(',', ':')).encode()
    return {'goal': goal, 'base_commit': base_commit, 'test_source': test_source,
            'implementation_source': implementation_source,
            'test_tree': test_tree,
            'implementation_tree': _git(repo, 'rev-parse', implementation_source + '^{tree}').decode().strip(),
            'test_scope': _scope_hash(test_owned),
            'implementation_scope': _scope_hash(implementation_owned),
            'retained_attempt_count': len(retained_attempts),
            'retained_attempts_hash': 'sha256:' + hashlib.sha256(raw_attempts).hexdigest()}


def _candidate_branch(repo: Path) -> str:
    branch = _git(repo, 'symbolic-ref', 'HEAD').decode().strip()
    if not branch.startswith('refs/heads/') or branch in {'refs/heads/dev', 'refs/heads/main'}:
        raise ValueError('Compaction requires a checked-out candidate branch')
    return branch


def _clean_candidate(repo: Path) -> None:
    if _git(repo, 'status', '--porcelain=v1', '-z', '--untracked-files=all',
            '--', '.', ':(exclude).zzzops'):
        raise ValueError('Compaction requires a clean candidate worktree')


def preview_two_commit_candidate(repo: Path, *, goal: int, base_commit: str,
                                 test_source: str, implementation_source: str,
                                 test_owned: list[str], implementation_owned: list[str],
                                 retained_attempts: list[dict], remote: str) -> dict:
    """Read-only preview of one final RED and one final GREEN commit."""
    repo = Path(repo).resolve()
    branch = _candidate_branch(repo)
    _clean_candidate(repo)
    facts = _compaction_facts(repo, goal=goal, base_commit=base_commit,
        test_source=test_source, implementation_source=implementation_source,
        test_owned=test_owned, implementation_owned=implementation_owned,
        retained_attempts=retained_attempts, remote=remote)
    head = _git(repo, 'rev-parse', 'HEAD').decode().strip()
    if head != implementation_source:
        candidate = verify_two_commit_candidate(repo, goal=goal,
            base_commit=base_commit, head_commit=head, test_owned=test_owned)
        if (candidate['test_source'] != test_source
                or candidate['implementation_source'] != implementation_source
                or _git(repo, 'rev-parse', candidate['test_commit'] + '^{tree}').decode().strip() != facts['test_tree']
                or _git(repo, 'rev-parse', head + '^{tree}').decode().strip() != facts['implementation_tree']):
            raise ValueError('Compaction source differs from the candidate branch head')
    return {**facts, 'branch_ref': branch}


def _commit_tree(repo: Path, *, tree: str, parent: str, source: str,
                 message: str) -> str:
    metadata = _git(repo, 'show', '-s', '--format=%an%x00%ae%x00%aI%x00%cn%x00%ce%x00%cI',
                    source).rstrip(b'\n').decode().split('\x00')
    if len(metadata) != 6:
        raise ValueError('Cannot preserve source commit authorship during compaction')
    environment = {**os.environ, **dict(zip(
        ('GIT_AUTHOR_NAME', 'GIT_AUTHOR_EMAIL', 'GIT_AUTHOR_DATE',
         'GIT_COMMITTER_NAME', 'GIT_COMMITTER_EMAIL', 'GIT_COMMITTER_DATE'), metadata))}
    result = subprocess.run(['git', 'commit-tree', tree, '-p', parent], cwd=repo,
                            input=message.encode(), capture_output=True, env=environment)
    if result.returncode:
        raise ValueError('Git could not prepare a deterministic compacted commit')
    return result.stdout.decode().strip()


def _grouped_candidate_facts(repo: Path, *, goal: int, base_commit: str,
                             groups: list[dict], retained_attempts: list[dict],
                             remote: str) -> dict:
    """Validate declarative publish groups against exact retained attempt commits."""
    if type(goal) is not int or goal <= 0 or not isinstance(groups, list) or not groups:
        raise ValueError('Git publication requires reviewed ordered groups')
    _commit(repo, base_commit)
    if not isinstance(retained_attempts, list) or not retained_attempts:
        raise ValueError('Git publication requires retained attempts')
    seen_groups, seen_nodes, all_paths, previous_tree = set(), set(), set(), base_commit
    previous_source = base_commit
    normalized = []
    node_scopes, source_refs = {}, set()
    for order, group in enumerate(groups):
        if (not isinstance(group, dict)
                or set(group) != {'id', 'order', 'nodes', 'commit_type', 'summary'}
                or not isinstance(group['id'], str) or not _NODE.fullmatch(group['id'])
                or group['id'] in seen_groups or type(group['order']) is not int
                or group['order'] != order
                or not isinstance(group['commit_type'], str)
                or not re.fullmatch(r'[a-z][a-z0-9]*', group['commit_type'])
                or not isinstance(group['summary'], str) or not group['summary'].strip()
                or group['summary'] != group['summary'].strip()
                or len(group['summary']) > 120
                or any(ord(character) < 32 or ord(character) == 127
                       for character in group['summary'])
                or not isinstance(group['nodes'], list) or not group['nodes']):
            raise ValueError('Git publication group declaration is malformed')
        seen_groups.add(group['id'])
        owned, sources = set(), []
        for member in group['nodes']:
            if (not isinstance(member, dict) or set(member) != {'node', 'source', 'owned'}
                    or not isinstance(member['node'], str) or not _NODE.fullmatch(member['node'])
                    or member['node'] in seen_nodes):
                raise ValueError('Git publication group has an invalid or duplicate node')
            _commit(repo, member['source'])
            _scope_hash(member['owned'])
            if not member['owned']:
                raise ValueError('Git publication node has no reviewed owned paths')
            seen_nodes.add(member['node'])
            node_scopes[member['node']] = member['owned']
            owned.update(member['owned'])
            sources.append(member['source'])
            source_refs.add((member['node'], member['source']))
        if all_paths.intersection(owned):
            raise ValueError('Git publication groups overlap in reviewed paths')
        all_paths.update(owned)
        tips = [source for source in set(sources) if all(
            subprocess.run(['git', 'merge-base', '--is-ancestor', other, source],
                           cwd=repo, capture_output=True).returncode == 0
            for other in sources)]
        if len(tips) != 1:
            raise ValueError('Git publication group sources have no unique ancestry tip')
        source = tips[0]
        if subprocess.run(['git', 'merge-base', '--is-ancestor', previous_source, source],
                          cwd=repo, capture_output=True).returncode:
            raise ValueError('Git publication groups do not follow declared order')
        tree = _project_owned_tree(repo, base_commit=previous_tree,
                                   source_commit=source, owned_paths=sorted(owned))
        if not _scoped_change_count(repo, previous_tree, tree, sorted(owned)):
            raise ValueError('Git publication group has no reviewed changes')
        normalized.append({'id': group['id'], 'order': order, 'source': source,
                           'tree': tree, 'scope': _scope_hash(sorted(owned)),
                           'commit_type': group['commit_type'], 'summary': group['summary']})
        previous_tree, previous_source = tree, source
    _scoped_change_count(repo, base_commit, previous_source, sorted(all_paths))
    if _git(repo, 'rev-parse', previous_source + '^{tree}').decode().strip() != previous_tree:
        raise ValueError('Git publication final tree differs from retained source')
    observed_sources, seen_refs = set(), set()
    for attempt in retained_attempts:
        if (not isinstance(attempt, dict) or set(attempt) != {'ref', 'commit'}
                or attempt['ref'] in seen_refs):
            raise ValueError('Git publication retained attempt is malformed')
        seen_refs.add(attempt['ref'])
        match = re.fullmatch(
            rf'refs/heads/zzzops/attempts/{goal}/([A-Za-z0-9_.-]+)/[0-9a-f]{{32}}',
            attempt['ref'])
        if not match or match.group(1) not in node_scopes:
            raise ValueError('Git publication retained attempt has an undeclared node')
        verify_attempt_ref(repo, remote=remote, **attempt)
        parents = _git(repo, 'rev-list', '--parents', '-n', '1', attempt['commit']).decode().split()
        if len(parents) != 2:
            raise ValueError('Git publication retained attempt must have one parent')
        _scoped_change_count(repo, parents[1], attempt['commit'], node_scopes[match.group(1)])
        observed_sources.add((match.group(1), attempt['commit']))
    if not source_refs <= observed_sources:
        raise ValueError('Git publication source is missing its exact retained attempt')
    plan_hash = 'sha256:' + hashlib.sha256(json.dumps(groups, sort_keys=True,
        separators=(',', ':')).encode()).hexdigest()
    attempts_hash = 'sha256:' + hashlib.sha256(json.dumps(retained_attempts,
        sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return {'goal': goal, 'base_commit': base_commit, 'groups': normalized,
            'plan_hash': plan_hash, 'retained_attempts_hash': attempts_hash}


def _grouped_commit_message(facts: dict, group: dict) -> str:
    return (f"{group['commit_type']}(goal-{facts['goal']}): {group['summary']}\n\n"
            f"ZzzOps-Goal: {facts['goal']}\nZzzOps-Group: {group['id']}\n"
            f"ZzzOps-Source: {group['source']}\nZzzOps-Plan: {facts['plan_hash']}\n")


def _grouped_commits(repo: Path, facts: dict) -> list[str]:
    parent, commits = facts['base_commit'], []
    for group in facts['groups']:
        parent = _commit_tree(repo, tree=group['tree'], parent=parent,
                              source=group['source'],
                              message=_grouped_commit_message(facts, group))
        commits.append(parent)
    return commits


def preview_grouped_candidate(repo: Path, *, goal: int, base_commit: str,
                              groups: list[dict], retained_attempts: list[dict],
                              remote: str) -> dict:
    """Preview a policy-declared candidate without moving its branch."""
    repo = Path(repo).resolve()
    branch = _candidate_branch(repo)
    _clean_candidate(repo)
    facts = _grouped_candidate_facts(repo, goal=goal, base_commit=base_commit,
        groups=groups, retained_attempts=retained_attempts, remote=remote)
    head = _git(repo, 'rev-parse', 'HEAD').decode().strip()
    source = facts['groups'][-1]['source']
    if head != source and head != _grouped_commits(repo, facts)[-1]:
        raise ValueError('Git publication candidate head differs from reviewed source or compacted plan')
    return {**facts, 'branch_ref': branch, 'expected_head': head}


def apply_grouped_candidate(repo: Path, preview: dict, *, groups: list[dict],
                            retained_attempts: list[dict], remote: str) -> dict:
    """Revalidate the reviewed plan, then CAS the clean candidate branch."""
    repo = Path(repo).resolve()
    if not isinstance(preview, dict) or _candidate_branch(repo) != preview.get('branch_ref'):
        raise ValueError('Git publication candidate branch changed')
    facts = _grouped_candidate_facts(repo, goal=preview['goal'],
        base_commit=preview['base_commit'], groups=groups,
        retained_attempts=retained_attempts, remote=remote)
    if preview != {**facts, 'branch_ref': preview['branch_ref'],
                   'expected_head': preview['expected_head']}:
        raise ValueError('Git publication reviewed plan or retained attempts changed')
    commits = _grouped_commits(repo, facts)
    current = _git(repo, 'rev-parse', 'HEAD').decode().strip()
    _clean_candidate(repo)
    if current == commits[-1]:
        return {'outcome': 'existing', 'head_commit': current, 'commits': commits}
    if current != preview['expected_head'] or current != facts['groups'][-1]['source']:
        raise ValueError('Git publication candidate head moved after preview')
    _git(repo, 'update-ref', '-m', f"zzzops compact goal {facts['goal']}",
         preview['branch_ref'], commits[-1], current)
    _clean_candidate(repo)
    return {'outcome': 'created', 'head_commit': commits[-1], 'commits': commits}


def verify_grouped_candidate(repo: Path, *, goal: int, base_commit: str,
                             head_commit: str, groups: list[dict],
                             retained_attempts: list[dict], remote: str) -> dict:
    """Bind a published head to the same exact reviewed group plan and refs."""
    repo = Path(repo).resolve()
    _commit(repo, head_commit)
    facts = _grouped_candidate_facts(repo, goal=goal, base_commit=base_commit,
        groups=groups, retained_attempts=retained_attempts, remote=remote)
    commits = _grouped_commits(repo, facts)
    if head_commit != commits[-1]:
        raise ValueError('Git publication head differs from the reviewed compacted plan')
    return {'head_commit': head_commit, 'commits': commits,
            'plan_hash': facts['plan_hash']}


def apply_two_commit_candidate(repo: Path, preview: dict, *, test_owned: list[str],
                               implementation_owned: list[str], retained_attempts: list[dict],
                               remote: str) -> dict:
    """CAS the candidate branch after rechecking the exact preview and refs."""
    repo = Path(repo).resolve()
    if not isinstance(preview, dict) or _candidate_branch(repo) != preview.get('branch_ref'):
        raise ValueError('Compaction candidate branch changed')
    facts = _compaction_facts(repo, goal=preview['goal'], base_commit=preview['base_commit'],
        test_source=preview['test_source'], implementation_source=preview['implementation_source'],
        test_owned=test_owned, implementation_owned=implementation_owned,
        retained_attempts=retained_attempts, remote=remote)
    if preview != {**facts, 'branch_ref': preview['branch_ref']}:
        raise ValueError('Compaction reviewed preview or retained attempts changed')
    test_commit = _commit_tree(repo, tree=facts['test_tree'], parent=facts['base_commit'],
        source=facts['test_source'], message=(f"test(goal-{facts['goal']}): consolidate reviewed RED tests\n\n"
            f"ZzzOps-Goal: {facts['goal']}\nZzzOps-Phase: test_design\nZzzOps-Source: {facts['test_source']}\n"))
    implementation_commit = _commit_tree(repo, tree=facts['implementation_tree'], parent=test_commit,
        source=facts['implementation_source'], message=(f"feat(goal-{facts['goal']}): consolidate GREEN implementation\n\n"
            f"ZzzOps-Goal: {facts['goal']}\nZzzOps-Phase: implement\nZzzOps-Source: {facts['implementation_source']}\n"))
    current = _git(repo, 'rev-parse', 'HEAD').decode().strip()
    if current == implementation_commit:
        _clean_candidate(repo)
        return {'outcome': 'existing', 'test_commit': test_commit,
                'implementation_commit': implementation_commit}
    if current != facts['implementation_source']:
        raise ValueError('Compaction candidate branch moved after preview')
    _clean_candidate(repo)
    _git(repo, 'update-ref', '-m', f"zzzops compact goal {facts['goal']}",
         preview['branch_ref'], implementation_commit, current)
    _clean_candidate(repo)
    return {'outcome': 'created', 'test_commit': test_commit,
            'implementation_commit': implementation_commit}


def verify_two_commit_candidate(repo: Path, *, goal: int, base_commit: str,
                                head_commit: str,
                                test_owned: list[str] | None = None) -> dict:
    """Require the reviewed RED/GREEN pair before an ancestry-preserving merge."""
    repo = Path(repo).resolve()
    if type(goal) is not int or goal <= 0:
        raise ValueError('Candidate goal identity is invalid')
    _commit(repo, base_commit)
    _commit(repo, head_commit)
    implementation = _git(repo, 'rev-list', '--parents', '-n', '1', head_commit).decode().split()
    if len(implementation) != 2:
        raise ValueError('Candidate GREEN commit must have exactly one parent')
    test_commit = implementation[1]
    test = _git(repo, 'rev-list', '--parents', '-n', '1', test_commit).decode().split()
    if len(test) != 2:
        raise ValueError('Candidate RED commit must have exactly one parent')
    if _git(repo, 'rev-parse', test[1] + '^{tree}') != _git(repo, 'rev-parse', base_commit + '^{tree}'):
        raise ValueError('Candidate base tree changed after review')
    source_commits = {}
    for commit, phase, title in ((test_commit, 'test_design', f'test(goal-{goal}): consolidate reviewed RED tests'),
                                 (head_commit, 'implement', f'feat(goal-{goal}): consolidate GREEN implementation')):
        message = _git(repo, 'show', '-s', '--format=%B', commit).decode().splitlines()
        if (not message or message[0] != title or f'ZzzOps-Goal: {goal}' not in message
                or f'ZzzOps-Phase: {phase}' not in message):
            raise ValueError('Candidate commit does not name the reviewed goal and phase')
        sources = [line.removeprefix('ZzzOps-Source: ') for line in message
                   if line.startswith('ZzzOps-Source: ')]
        if len(sources) != 1:
            raise ValueError('Candidate commit has no unique retained source')
        _commit(repo, sources[0])
        expected_tree = (_project_owned_tree(repo, base_commit=base_commit,
            source_commit=sources[0], owned_paths=test_owned)
            if phase == 'test_design' and test_owned is not None
            else _git(repo, 'rev-parse', sources[0] + '^{tree}').decode().strip())
        if expected_tree != _git(repo, 'rev-parse', commit + '^{tree}').decode().strip():
            raise ValueError('Candidate tree differs from its retained source')
        source_commits[phase] = sources[0]
    return {'test_commit': test_commit, 'implementation_commit': head_commit,
            'test_source': source_commits['test_design'],
            'implementation_source': source_commits['implement']}


def _single_compaction_facts(repo: Path, *, goal: int, base_commit: str,
                             source_commit: str, owned_paths: list[str],
                             retained_attempts: list[dict], remote: str) -> dict:
    if type(goal) is not int or goal <= 0 or not isinstance(retained_attempts, list):
        raise ValueError('Composition compaction requires a positive goal and retained attempts')
    for commit in (base_commit, source_commit):
        _commit(repo, commit)
    prefix = f'refs/heads/zzzops/attempts/{goal}/integration_verification/'
    seen = set()
    for attempt in retained_attempts:
        if (not isinstance(attempt, dict) or set(attempt) != {'ref', 'commit'}
                or not isinstance(attempt['ref'], str)
                or not attempt['ref'].startswith(prefix) or attempt['ref'] in seen):
            raise ValueError('Composition retained attempt identity is malformed')
        seen.add(attempt['ref'])
        verify_attempt_ref(repo, remote=remote, **attempt)
        parents = _git(repo, 'rev-list', '--parents', '-n', '1', attempt['commit']).decode().split()
        if len(parents) != 2:
            raise ValueError('Composition attempt must have one parent')
        _scoped_change_count(repo, parents[1], attempt['commit'], owned_paths)
    if compaction_base_from_attempts(repo, goal=goal, test_source=source_commit,
            attempts=retained_attempts, remote=remote,
            phase='integration_verification') != base_commit:
        raise ValueError('Composition base differs from retained attempt ancestry')
    _scoped_change_count(repo, base_commit, source_commit, owned_paths)
    raw_attempts = json.dumps(retained_attempts, sort_keys=True, separators=(',', ':')).encode()
    return {'goal': goal, 'phase': 'integration_verification',
            'base_commit': base_commit, 'source_commit': source_commit,
            'source_tree': _git(repo, 'rev-parse', source_commit + '^{tree}').decode().strip(),
            'scope': _scope_hash(owned_paths),
            'retained_attempt_count': len(retained_attempts),
            'retained_attempts_hash': 'sha256:' + hashlib.sha256(raw_attempts).hexdigest()}


def verify_single_commit_candidate(repo: Path, *, goal: int, base_commit: str,
                                   head_commit: str) -> dict:
    """Verify the exact one-commit composition delivery and retained source."""
    repo = Path(repo).resolve()
    if type(goal) is not int or goal <= 0:
        raise ValueError('Composition candidate goal identity is invalid')
    _commit(repo, base_commit)
    _commit(repo, head_commit)
    parents = _git(repo, 'rev-list', '--parents', '-n', '1', head_commit).decode().split()
    if len(parents) != 2:
        raise ValueError('Composition candidate must have exactly one parent')
    if _git(repo, 'rev-parse', parents[1] + '^{tree}') != _git(repo, 'rev-parse', base_commit + '^{tree}'):
        raise ValueError('Composition candidate base tree changed after review')
    lines = _git(repo, 'show', '-s', '--format=%B', head_commit).decode().splitlines()
    if (not lines or lines[0] != f'feat(goal-{goal}): consolidate reviewed integration'
            or f'ZzzOps-Goal: {goal}' not in lines
            or 'ZzzOps-Phase: integration_verification' not in lines):
        raise ValueError('Composition candidate does not name the reviewed goal and phase')
    sources = [line.removeprefix('ZzzOps-Source: ') for line in lines
               if line.startswith('ZzzOps-Source: ')]
    if len(sources) != 1:
        raise ValueError('Composition candidate lacks one retained source')
    _commit(repo, sources[0])
    if _git(repo, 'rev-parse', sources[0] + '^{tree}') != _git(repo, 'rev-parse', head_commit + '^{tree}'):
        raise ValueError('Composition candidate tree differs from its retained source')
    return {'candidate_commit': head_commit, 'source_commit': sources[0]}


def preview_single_commit_candidate(repo: Path, *, goal: int, base_commit: str,
                                    source_commit: str, owned_paths: list[str],
                                    retained_attempts: list[dict], remote: str) -> dict:
    """Preview one reviewed composition commit without changing branch refs."""
    repo = Path(repo).resolve()
    facts = _single_compaction_facts(repo, goal=goal, base_commit=base_commit,
        source_commit=source_commit, owned_paths=owned_paths,
        retained_attempts=retained_attempts, remote=remote)
    branch = _candidate_branch(repo)
    head = _git(repo, 'rev-parse', 'HEAD').decode().strip()
    if head != source_commit:
        candidate = verify_single_commit_candidate(repo, goal=goal,
            base_commit=base_commit, head_commit=head)
        if candidate['source_commit'] != source_commit:
            raise ValueError('Composition source differs from candidate branch head')
    _clean_candidate(repo)
    return {**facts, 'branch_ref': branch}


def apply_single_commit_candidate(repo: Path, preview: dict, *, owned_paths: list[str],
                                  retained_attempts: list[dict], remote: str) -> dict:
    """CAS a one-commit composition candidate after rechecking its exact preview."""
    repo = Path(repo).resolve()
    if not isinstance(preview, dict) or _candidate_branch(repo) != preview.get('branch_ref'):
        raise ValueError('Composition candidate branch changed')
    facts = _single_compaction_facts(repo, goal=preview['goal'],
        base_commit=preview['base_commit'], source_commit=preview['source_commit'],
        owned_paths=owned_paths, retained_attempts=retained_attempts, remote=remote)
    if preview != {**facts, 'branch_ref': preview['branch_ref']}:
        raise ValueError('Composition reviewed preview or retained attempts changed')
    source = facts['source_commit']
    candidate_commit = _commit_tree(repo, tree=facts['source_tree'],
        parent=facts['base_commit'], source=source,
        message=(f"feat(goal-{facts['goal']}): consolidate reviewed integration\n\n"
            f"ZzzOps-Goal: {facts['goal']}\nZzzOps-Phase: integration_verification\n"
            f"ZzzOps-Source: {source}\n"))
    current = _git(repo, 'rev-parse', 'HEAD').decode().strip()
    if current == candidate_commit:
        _clean_candidate(repo)
        return {'outcome': 'existing', 'candidate_commit': candidate_commit}
    if current != source:
        raise ValueError('Composition candidate branch moved after preview')
    _clean_candidate(repo)
    _git(repo, 'update-ref', '-m', f"zzzops compact composition goal {facts['goal']}",
         preview['branch_ref'], candidate_commit, current)
    _clean_candidate(repo)
    return {'outcome': 'created', 'candidate_commit': candidate_commit}


def classify_base_move(repo: Path, *, old_base: str, new_base: str) -> dict:
    """Classify what a changed base invalidates without rewriting a branch."""
    repo = Path(repo).resolve()
    _commit(repo, old_base)
    _commit(repo, new_base)
    old_tree = _git(repo, 'rev-parse', old_base + '^{tree}').decode().strip()
    new_tree = _git(repo, 'rev-parse', new_base + '^{tree}').decode().strip()
    preserves_ancestry = subprocess.run(
        ['git', 'merge-base', '--is-ancestor', old_base, new_base],
        cwd=repo, capture_output=True).returncode == 0
    if old_base == new_base:
        action = 'current'
    elif old_tree == new_tree:
        action = 'retarget_only' if preserves_ancestry else 'topology_rewrite'
    else:
        action = 'rebase_and_reverify'
    return {'action': action, 'old_base': old_base, 'new_base': new_base,
            'old_tree': old_tree, 'new_tree': new_tree,
            'preserves_ancestry': preserves_ancestry}


def preview_attempt_restack(repo: Path, *, old_base: str, new_base: str,
                            attempt_commit: str, owned_paths: list[str]) -> dict:
    """Inspect one verified attempt on a moved base without changing any ref."""
    repo = Path(repo).resolve()
    original = validate_checkpoint(repo, base_commit=old_base,
        result_commit=attempt_commit, owned_paths=owned_paths,
        require_clean_worktree=False)
    movement = classify_base_move(repo, old_base=old_base, new_base=new_base)
    try:
        result = subprocess.run(['git', 'merge-tree', '--write-tree', '--name-only', '-z',
            '--merge-base=' + old_base, new_base, attempt_commit],
            cwd=repo, capture_output=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError('Git restack preview could not complete') from exc
    if result.returncode not in (0, 1):
        raise ValueError('Git restack preview could not determine conflicts')
    parts = result.stdout.split(b'\x00')
    if not parts or re.fullmatch(rb'[0-9a-f]{40}', parts[0]) is None:
        raise ValueError('Git restack preview returned no exact tree')
    tree = parts[0].decode('ascii')
    if result.returncode:
        if b'' not in parts[1:]:
            raise ValueError('Git restack preview omitted conflict path boundary')
        boundary = parts.index(b'', 1)
        try:
            conflicts = [path.decode('utf-8') for path in parts[1:boundary]]
        except UnicodeDecodeError as exc:
            raise ValueError('Git restack preview contains a non-UTF-8 conflict path') from exc
        if not conflicts or any(not _owned_path(path) or path not in owned_paths
                                for path in conflicts):
            raise ValueError('Git restack conflict is missing or outside reviewed owned paths')
        status = 'conflict'
        changed = None
    else:
        if parts[1:] != [b'']:
            raise ValueError('Git restack preview returned unexpected clean output')
        conflicts = []
        changed = _scoped_change_count(repo, new_base, tree, owned_paths)
        status = 'clean'
    return {'status': status, 'old_base': old_base, 'new_base': new_base,
            'attempt_commit': attempt_commit, 'original_tree': original['result_tree'],
            'proposed_tree': tree, 'conflicts': conflicts, 'change_count': changed,
            'owned_scope': _scope_hash(owned_paths),
            'content_stale': movement['old_tree'] != movement['new_tree'],
            'topology_changed': old_base != new_base}


def _restack_preview(repo: Path, preview: dict, owned_paths: list[str]) -> dict:
    """Recompute a restack plan so caller-supplied facts never authorize Git writes."""
    if not isinstance(preview, dict):
        raise ValueError('Git restack requires an exact preview')
    required = {'status', 'old_base', 'new_base', 'attempt_commit', 'original_tree',
                'proposed_tree', 'conflicts', 'change_count', 'content_stale',
                'topology_changed', 'owned_scope'}
    if set(preview) != required:
        raise ValueError('Git restack preview fields changed')
    if preview['owned_scope'] != _scope_hash(owned_paths):
        raise ValueError('Git restack reviewed owned scope changed')
    current = preview_attempt_restack(repo, old_base=preview['old_base'],
        new_base=preview['new_base'], attempt_commit=preview['attempt_commit'],
        owned_paths=owned_paths)
    if current != preview:
        raise ValueError('Git restack preview changed')
    return current


def _restack_sequencer(repo: Path) -> str | None:
    result = subprocess.run(['git', 'rev-parse', '--verify', 'CHERRY_PICK_HEAD'],
        cwd=repo, capture_output=True, text=True)
    if result.returncode:
        return None
    value = result.stdout.strip()
    if re.fullmatch(r'[0-9a-f]{40}', value) is None:
        raise ValueError('Git restack cherry-pick identity is invalid')
    return value


def _restack_dirty_paths(repo: Path, owned_paths: list[str]) -> list[str]:
    dirty = _git(repo, 'status', '--porcelain=v1', '-z', '--untracked-files=all',
                 '--no-renames', '--', '.', ':(exclude).zzzops')
    paths = []
    for entry in dirty.split(b'\x00'):
        if not entry:
            continue
        if len(entry) < 4 or entry[2:3] != b' ':
            raise ValueError('Git restack worktree status is invalid')
        try:
            path = entry[3:].decode('utf-8')
        except UnicodeDecodeError as exc:
            raise ValueError('Git restack contains a non-UTF-8 path') from exc
        if not _owned_path(path) or path not in owned_paths:
            raise ValueError('Git restack contains unowned dirt outside reviewed owned paths')
        paths.append(path)
    return paths


def _restack_clean_result(repo: Path, plan: dict, owned_paths: list[str]) -> dict:
    head = _git(repo, 'rev-parse', 'HEAD').decode().strip()
    checkpoint = validate_checkpoint(repo, base_commit=plan['new_base'],
        result_commit=head, owned_paths=owned_paths)
    if (plan['status'] == 'clean'
            and checkpoint['result_tree'] != plan['proposed_tree']):
        raise ValueError('Git restack result tree differs from exact preview')
    return {**plan, 'status': 'clean', 'result_commit': head,
            'result_tree': checkpoint['result_tree'], 'conflicts': []}


def apply_attempt_restack(repo: Path, preview: dict, owned_paths: list[str]) -> dict:
    """Cherry-pick one exact verified attempt onto its previewed moved base."""
    repo = Path(repo).resolve()
    plan = _restack_preview(repo, preview, owned_paths)
    head = _git(repo, 'rev-parse', 'HEAD').decode().strip()
    sequencer = _restack_sequencer(repo)
    if sequencer is not None:
        if (sequencer != plan['attempt_commit'] or head != plan['new_base']
                or plan['status'] != 'conflict'):
            raise ValueError('Git restack sequencer or HEAD changed')
        paths = _restack_dirty_paths(repo, owned_paths)
        if sorted(paths) != sorted(plan['conflicts']):
            raise ValueError('Git restack conflict paths changed')
        return {**plan, 'status': 'conflict', 'conflicts': sorted(paths)}
    if head != plan['new_base']:
        if plan['status'] != 'clean':
            raise ValueError('Git restack conflict result lacks an exact replay sequencer')
        return _restack_clean_result(repo, plan, owned_paths)
    if _restack_dirty_paths(repo, owned_paths):
        raise ValueError('Git restack requires a clean new-base worktree')
    result = subprocess.run(['git', 'cherry-pick', plan['attempt_commit']], cwd=repo,
                            capture_output=True, text=True)
    if result.returncode == 0:
        return _restack_clean_result(repo, plan, owned_paths)
    sequencer = _restack_sequencer(repo)
    if sequencer != plan['attempt_commit'] or plan['status'] != 'conflict':
        raise ValueError('Git restack cherry-pick failed without the expected conflict')
    paths = _restack_dirty_paths(repo, owned_paths)
    if sorted(paths) != sorted(plan['conflicts']):
        raise ValueError('Git restack conflict paths changed')
    return {**plan, 'status': 'conflict', 'conflicts': sorted(paths)}


def continue_attempt_restack(repo: Path, preview: dict, owned_paths: list[str]) -> dict:
    """Continue only the exact previewed cherry-pick after an owned resolution."""
    repo = Path(repo).resolve()
    plan = _restack_preview(repo, preview, owned_paths)
    head = _git(repo, 'rev-parse', 'HEAD').decode().strip()
    sequencer = _restack_sequencer(repo)
    if sequencer is None:
        if head == plan['new_base']:
            raise ValueError('Git restack has no conflict resolution to continue')
        if plan['status'] != 'clean':
            raise ValueError('Git restack conflict result lacks an exact replay sequencer')
        return _restack_clean_result(repo, plan, owned_paths)
    if sequencer != plan['attempt_commit'] or head != plan['new_base']:
        raise ValueError('Git restack sequencer or HEAD changed')
    paths = _restack_dirty_paths(repo, owned_paths)
    if not paths:
        raise ValueError('Git restack conflict resolution is missing')
    for path in paths:
        target = repo / path
        if target.is_symlink() or target.exists() and not target.is_file():
            raise ValueError('Git restack resolution requires ordinary files, never symlinks')
    _git(repo, 'add', '-A', '--', *sorted(set(paths)))
    if _git(repo, 'ls-files', '-u', '-z'):
        raise ValueError('Git restack conflict remains unresolved')
    environment = dict(os.environ, GIT_EDITOR='true')
    result = subprocess.run(['git', 'cherry-pick', '--continue'], cwd=repo,
                            capture_output=True, text=True, env=environment)
    if result.returncode:
        raise ValueError('Git restack could not continue the exact cherry-pick')
    return _restack_clean_result(repo, plan, owned_paths)


def abort_attempt_restack(repo: Path, preview: dict, owned_paths: list[str]) -> dict:
    """Abort an exact conflict and restore the clean moved-base attempt."""
    repo = Path(repo).resolve()
    plan = _restack_preview(repo, preview, owned_paths)
    head = _git(repo, 'rev-parse', 'HEAD').decode().strip()
    sequencer = _restack_sequencer(repo)
    if sequencer is None:
        if head != plan['new_base'] or _restack_dirty_paths(repo, owned_paths):
            raise ValueError('Git restack abort state changed')
    else:
        if sequencer != plan['attempt_commit'] or head != plan['new_base']:
            raise ValueError('Git restack sequencer or HEAD changed')
        _restack_dirty_paths(repo, owned_paths)
        result = subprocess.run(['git', 'cherry-pick', '--abort'], cwd=repo,
                                capture_output=True, text=True)
        if result.returncode:
            raise ValueError('Git restack could not abort the exact cherry-pick')
    if (_git(repo, 'rev-parse', 'HEAD').decode().strip() != plan['new_base']
            or _restack_sequencer(repo) is not None
            or _restack_dirty_paths(repo, owned_paths)):
        raise ValueError('Git restack abort did not restore the clean moved base')
    return {**plan, 'status': 'aborted', 'head_commit': plan['new_base'],
            'conflicts': []}
