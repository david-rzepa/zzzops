"""Local Git facts for a commit-backed workspace phase.

This validator grants no workflow authority. The goal's reviewed allocation,
lease, verification, independent review and acceptance receipt must still bind
the exact returned commits before a result can become current.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
import re
import subprocess


_COMMIT = re.compile(r'[0-9a-f]{40}\Z')
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
