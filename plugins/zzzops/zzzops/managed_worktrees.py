"""Local, ignored Git worktrees for exact goal attempts.

Git registration is the source of local worktree state. These helpers do not
grant a task lease or integration authority; the workflow must authenticate
those receipts before calling them.
"""

from __future__ import annotations

from pathlib import Path
import re
import subprocess


_OID = re.compile(r'[0-9a-f]{40}\Z')
_NODE = re.compile(r'[A-Za-z0-9_-]+\Z')
_ATTEMPT = re.compile(r'[0-9a-f]{32}\Z')


def _run(repo: Path, *arguments: str, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(['git', *arguments], cwd=repo, capture_output=True, text=True)
    if check and result.returncode:
        raise ValueError('Git could not confirm managed worktree state')
    return result


def _identity(goal: int, node: str, attempt: str) -> None:
    if (type(goal) is not int or goal <= 0 or not isinstance(node, str)
            or not _NODE.fullmatch(node) or not isinstance(attempt, str)
            or not _ATTEMPT.fullmatch(attempt)):
        raise ValueError('Invalid managed worktree identity')


def _worktrees(repo: Path) -> list[dict]:
    records = []
    for block in _run(repo, 'worktree', 'list', '--porcelain').stdout.strip().split('\n\n'):
        record = {}
        for line in block.splitlines():
            key, _, value = line.partition(' ')
            record[key] = value
        if record.get('worktree'):
            records.append(record)
    return records


def _primary(repo: Path) -> Path:
    primary = [Path(row['worktree']).resolve() for row in _worktrees(repo)
               if (Path(row['worktree']) / '.git').is_dir()]
    if len(primary) != 1:
        raise ValueError('Managed worktrees require one available primary checkout')
    return primary[0]


def _managed(primary: Path, goal: int, node: str, attempt: str) -> tuple[Path, str]:
    return (primary / '.zzzops' / 'worktrees' / str(goal) / node / attempt,
            f'zzzops/goal-{goal}/{node}/{attempt}')


def _clean(repo: Path) -> bool:
    return not _run(repo, 'status', '--porcelain=v1', '-z', '--untracked-files=all',
                    '--', '.', ':(exclude).zzzops').stdout


def _install_ignore(repo: Path) -> None:
    common = Path(_run(repo, 'rev-parse', '--path-format=absolute', '--git-common-dir').stdout.strip())
    info = common / 'info' / 'exclude'
    info.parent.mkdir(parents=True, exist_ok=True)
    marker = '.zzzops/worktrees/'
    # Re-reading the local exclude keeps retries idempotent. The path is under
    # Git's common directory so every linked checkout shares the ignore rule.
    text = info.read_text(encoding='utf-8') if info.exists() else ''
    if marker not in text.splitlines():
        with info.open('a', encoding='utf-8') as handle:
            if text and not text.endswith('\n'):
                handle.write('\n')
            handle.write(marker + '\n')


def prepare_worktree(repo: Path, *, goal: int, node: str, attempt: str,
                     base_commit: str) -> dict:
    """Create or resume one exact isolated attempt from a committed base."""
    repo = Path(repo).resolve()
    _identity(goal, node, attempt)
    if not isinstance(base_commit, str) or not _OID.fullmatch(base_commit):
        raise ValueError('Managed worktree requires an exact base commit')
    if _run(repo, 'cat-file', '-t', base_commit).stdout.strip() != 'commit':
        raise ValueError('Managed worktree base is not a commit')
    primary = _primary(repo)
    path, branch = _managed(primary, goal, node, attempt)
    branch_ref = 'refs/heads/' + branch
    registered = next((row for row in _worktrees(repo) if Path(row['worktree']).resolve() == path), None)
    if registered:
        if (registered.get('branch') != branch_ref or not path.is_dir()
                or _run(path, 'rev-parse', 'HEAD').stdout.strip() != base_commit
                or not _clean(path)):
            raise ValueError('Managed worktree changed; inspect its branch and files before recovery')
        return {'outcome': 'existing', 'path': str(path), 'branch': branch,
                'base_commit': base_commit}
    if path.exists() or _run(repo, 'show-ref', '--verify', '--quiet', branch_ref, check=False).returncode == 0:
        raise ValueError('Managed worktree path or branch already exists without matching registration')
    _install_ignore(primary)
    path.parent.mkdir(parents=True, exist_ok=True)
    _run(primary, 'worktree', 'add', '-q', '-b', branch, str(path), base_commit)
    if (_run(path, 'rev-parse', 'HEAD').stdout.strip() != base_commit
            or _run(path, 'symbolic-ref', 'HEAD').stdout.strip() != branch_ref
            or not _clean(path)):
        raise ValueError('Managed worktree creation could not be verified')
    return {'outcome': 'created', 'path': str(path), 'branch': branch,
            'base_commit': base_commit}


def inspect_attempt_worktree(repo: Path, *, goal: int, node: str, attempt: str) -> dict:
    """Report one local attempt without changing its files, branch or lease."""
    repo = Path(repo).resolve()
    _identity(goal, node, attempt)
    primary = _primary(repo)
    path, branch = _managed(primary, goal, node, attempt)
    registered = next((row for row in _worktrees(repo) if Path(row['worktree']).resolve() == path), None)
    if not registered and not path.exists():
        return {'status': 'missing', 'path': str(path), 'branch': branch}
    if not registered or registered.get('branch') != 'refs/heads/' + branch or not path.is_dir():
        raise ValueError('Local attempt worktree changed; inspect its registration before recovery')
    return {'status': 'dirty' if not _clean(path) else 'clean',
            'path': str(path), 'branch': branch,
            'head': _run(path, 'rev-parse', 'HEAD').stdout.strip()}


def cleanup_integrated_worktree(repo: Path, *, goal: int, node: str, attempt: str,
                                expected_head: str, integrated_commit: str,
                                remote: str, retained_ref: str) -> dict:
    """Remove only a clean registered attempt already integrated by ancestry."""
    repo = Path(repo).resolve()
    _identity(goal, node, attempt)
    if any(not isinstance(oid, str) or not _OID.fullmatch(oid)
           for oid in (expected_head, integrated_commit)):
        raise ValueError('Cleanup requires exact result and integration commits')
    primary = _primary(repo)
    path, branch = _managed(primary, goal, node, attempt)
    registered = next((row for row in _worktrees(repo) if Path(row['worktree']).resolve() == path), None)
    if not registered or registered.get('branch') != 'refs/heads/' + branch or not path.is_dir():
        raise ValueError('Cleanup requires the exact registered managed worktree')
    if not _clean(path):
        raise ValueError('Managed worktree is dirty; preserve its unverified files locally')
    if _run(path, 'rev-parse', 'HEAD').stdout.strip() != expected_head:
        raise ValueError('Managed worktree head changed before cleanup')
    if _run(repo, 'merge-base', '--is-ancestor', expected_head, integrated_commit,
            check=False).returncode:
        raise ValueError('Managed result is not integrated into the observed target commit')
    # Imported late to keep local worktree preparation independent of remote
    # availability. The workflow must separately authenticate merge evidence.
    from zzzops_git_phase_state import verify_attempt_ref
    verify_attempt_ref(repo, remote=remote, ref=retained_ref, commit=expected_head)
    _run(primary, 'worktree', 'remove', str(path))
    if path.exists() or any(Path(row['worktree']).resolve() == path for row in _worktrees(repo)):
        raise ValueError('Managed worktree removal could not be confirmed')
    return {'outcome': 'removed', 'path': str(path), 'branch': branch,
            'integrated_commit': integrated_commit}


def cleanup_delivered_attempt_worktree(repo: Path, *, goal: int, node: str,
                                       attempt: str, expected_head: str,
                                       delivery_base: str, delivery_head: str,
                                       integrated_commit: str, remote: str,
                                       retained_ref: str,
                                       delivery_class: str = 'leaf') -> dict:
    """Remove a clean archived attempt after its exact delivery is merged.

    Rejected correction commits need not be ancestors of the compacted pair.
    Their exact remote refs survive this local cleanup.
    """
    repo = Path(repo).resolve()
    _identity(goal, node, attempt)
    if (any(not isinstance(oid, str) or not _OID.fullmatch(oid)
            for oid in (expected_head, delivery_base, delivery_head, integrated_commit))
            or retained_ref != f'refs/heads/zzzops/attempts/{goal}/{node}/{attempt}'):
        raise ValueError('Cleanup requires exact attempt and delivery identities')
    if delivery_class not in {'leaf', 'composition'} or (
            delivery_class == 'composition' and node != 'integration_verification') or (
            delivery_class == 'leaf' and node not in {'test_design', 'implement'}):
        raise ValueError('Cleanup delivery class does not match attempt phase')
    from zzzops_git_phase_state import (verify_attempt_ref,
        verify_single_commit_candidate, verify_two_commit_candidate)
    verify_attempt_ref(repo, remote=remote, ref=retained_ref, commit=expected_head)
    verifier = (verify_single_commit_candidate if delivery_class == 'composition'
                else verify_two_commit_candidate)
    verifier(repo, goal=goal, base_commit=delivery_base, head_commit=delivery_head)
    if _run(repo, 'merge-base', '--is-ancestor', delivery_head, integrated_commit,
            check=False).returncode:
        raise ValueError('Reviewed candidate is not integrated into the observed target commit')
    observed = inspect_attempt_worktree(repo, goal=goal, node=node, attempt=attempt)
    path, branch = Path(observed['path']), observed['branch']
    branch_ref = 'refs/heads/' + branch
    if observed['status'] != 'missing':
        if observed['status'] != 'clean':
            raise ValueError('Managed worktree is dirty; preserve its unverified files locally')
        if observed['head'] != expected_head:
            raise ValueError('Managed attempt head changed before cleanup')
        _run(_primary(repo), 'worktree', 'remove', str(path))
        if path.exists() or any(Path(row['worktree']).resolve() == path for row in _worktrees(repo)):
            raise ValueError('Managed worktree removal could not be confirmed')
    existing = _run(repo, 'rev-parse', '--verify', branch_ref, check=False)
    if existing.returncode == 0:
        if existing.stdout.strip() != expected_head:
            raise ValueError('Managed attempt branch changed during cleanup')
        _run(repo, 'update-ref', '-d', branch_ref, expected_head)
    return {'outcome': 'removed' if observed['status'] != 'missing' or existing.returncode == 0
            else 'already_removed', 'path': str(path), 'branch': branch,
            'integrated_commit': integrated_commit}


def cleanup_delivered_candidate_worktree(repo: Path, *, goal: int, attempt: str,
                                         expected_head: str, delivery_base: str,
                                         integrated_commit: str,
                                         delivery_class: str = 'leaf') -> dict:
    """Remove only a clean exact candidate already present in the target."""
    repo = Path(repo).resolve()
    _identity(goal, 'candidate', attempt)
    if any(not isinstance(oid, str) or not _OID.fullmatch(oid)
           for oid in (expected_head, delivery_base, integrated_commit)):
        raise ValueError('Candidate cleanup requires exact commit identities')
    from zzzops_git_phase_state import verify_single_commit_candidate, verify_two_commit_candidate
    if delivery_class not in {'leaf', 'composition'}:
        raise ValueError('Candidate cleanup delivery class is invalid')
    verifier = (verify_single_commit_candidate if delivery_class == 'composition'
                else verify_two_commit_candidate)
    verifier(repo, goal=goal, base_commit=delivery_base, head_commit=expected_head)
    if _run(repo, 'merge-base', '--is-ancestor', expected_head, integrated_commit,
            check=False).returncode:
        raise ValueError('Reviewed candidate is not integrated into the observed target commit')
    observed = inspect_attempt_worktree(repo, goal=goal, node='candidate', attempt=attempt)
    path, branch = Path(observed['path']), observed['branch']
    branch_ref = 'refs/heads/' + branch
    if observed['status'] != 'missing':
        if observed['status'] != 'clean':
            raise ValueError('Managed candidate worktree is dirty; preserve its files locally')
        if observed['head'] != expected_head:
            raise ValueError('Managed candidate head changed before cleanup')
        _run(_primary(repo), 'worktree', 'remove', str(path))
        if path.exists() or any(Path(row['worktree']).resolve() == path for row in _worktrees(repo)):
            raise ValueError('Managed candidate worktree removal could not be confirmed')
    existing = _run(repo, 'rev-parse', '--verify', branch_ref, check=False)
    if existing.returncode == 0:
        if existing.stdout.strip() != expected_head:
            raise ValueError('Managed candidate branch changed during cleanup')
        _run(repo, 'update-ref', '-d', branch_ref, expected_head)
    return {'outcome': 'removed' if observed['status'] != 'missing' or existing.returncode == 0
            else 'already_removed', 'path': str(path), 'branch': branch,
            'integrated_commit': integrated_commit}
