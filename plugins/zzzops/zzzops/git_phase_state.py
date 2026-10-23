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


def compaction_base_from_attempts(repo: Path, *, goal: int, test_source: str,
                                  attempts: list[dict], remote: str) -> str:
    """Find the base before the earliest retained RED attempt on the final line."""
    repo = Path(repo).resolve()
    if type(goal) is not int or goal <= 0 or not isinstance(attempts, list) or not attempts:
        raise ValueError('Compaction requires retained RED attempts')
    _commit(repo, test_source)
    earliest = test_source
    found_source = False
    for attempt in attempts:
        if (not isinstance(attempt, dict) or set(attempt) != {'ref', 'commit'}
                or not attempt['ref'].startswith(f'refs/heads/zzzops/attempts/{goal}/test_design/')):
            raise ValueError('Compaction RED attempt identity is malformed')
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
        raise ValueError('Final RED source lacks its exact retained attempt ref')
    parents = _git(repo, 'rev-list', '--parents', '-n', '1', earliest).decode().split()
    if len(parents) != 2:
        raise ValueError('Earliest RED attempt must have exactly one base parent')
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
    if not _scoped_change_count(repo, base_commit, test_source, test_owned):
        raise ValueError('Compaction has no reviewed RED test changes')
    if not _scoped_change_count(repo, test_source, implementation_source, implementation_owned):
        raise ValueError('Compaction has no reviewed GREEN implementation changes')
    seen = set()
    for attempt in retained_attempts:
        if (not isinstance(attempt, dict) or set(attempt) != {'ref', 'commit'}
                or attempt['ref'] in seen
                or not attempt['ref'].startswith(f'refs/heads/zzzops/attempts/{goal}/')):
            raise ValueError('Compaction retained attempt list is malformed')
        seen.add(attempt['ref'])
        verify_attempt_ref(repo, remote=remote, **attempt)
    if not {test_source, implementation_source} <= {row['commit'] for row in retained_attempts}:
        raise ValueError('Compaction must retain both final source attempts')
    raw_attempts = json.dumps(retained_attempts, sort_keys=True, separators=(',', ':')).encode()
    return {'goal': goal, 'base_commit': base_commit, 'test_source': test_source,
            'implementation_source': implementation_source,
            'test_tree': _git(repo, 'rev-parse', test_source + '^{tree}').decode().strip(),
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
    if _git(repo, 'rev-parse', 'HEAD').decode().strip() != implementation_source:
        raise ValueError('Compaction source differs from the candidate branch head')
    return {**_compaction_facts(repo, goal=goal, base_commit=base_commit,
        test_source=test_source, implementation_source=implementation_source,
        test_owned=test_owned, implementation_owned=implementation_owned,
        retained_attempts=retained_attempts, remote=remote), 'branch_ref': branch}


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
                                head_commit: str) -> dict:
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
        if _git(repo, 'rev-parse', sources[0] + '^{tree}') != _git(repo, 'rev-parse', commit + '^{tree}'):
            raise ValueError('Candidate tree differs from its retained source')
        source_commits[phase] = sources[0]
    return {'test_commit': test_commit, 'implementation_commit': head_commit,
            'test_source': source_commits['test_design'],
            'implementation_source': source_commits['implement']}
