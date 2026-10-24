"""Classify the worktree allowed to coordinate shared ZzzOps mutations."""

from __future__ import annotations

import subprocess
from pathlib import Path


class WorkspaceRouteError(ValueError):
    """A frozen request must be retried from the canonical coordinator."""

    def __init__(self, step: dict):
        super().__init__(step.get('reason', 'Coordinator worktree required'))
        self.step = step


def _git(repo: Path, *arguments: str) -> str:
    result = subprocess.run(['git', '-C', str(repo), *arguments], capture_output=True,
                            text=True, check=False)
    if result.returncode or not result.stdout.strip():
        raise ValueError('Git worktree identity could not be verified')
    return result.stdout.strip()


def _registered(repo: Path) -> list[dict[str, str]]:
    entries = []
    current = None
    for line in _git(repo, 'worktree', 'list', '--porcelain').splitlines():
        if line.startswith('worktree '):
            if current is not None:
                entries.append(current)
            current = {'path': line[9:]}
        elif current is not None and line.startswith('branch '):
            current['branch'] = line[7:]
        elif current is not None and line == 'detached':
            current['branch'] = '<detached>'
    if current is not None:
        entries.append(current)
    if not entries or any(not row.get('path') or not Path(row['path']).is_absolute()
                          for row in entries):
        raise ValueError('Registered Git worktrees are unavailable or malformed')
    return entries


def classify(repo: Path, integration_branch: str | None, *, provisional: bool = False) -> dict:
    """Use the effective --repo root, never the shell's current directory."""
    repo = Path(repo).resolve()
    root = Path(_git(repo, 'rev-parse', '--show-toplevel')).resolve()
    common = Path(_git(root, 'rev-parse', '--git-common-dir'))
    common = (root / common).resolve() if not common.is_absolute() else common.resolve()
    worktrees = _registered(root)
    registered = [row for row in worktrees if Path(row['path']).resolve() == root]
    if len(registered) != 1:
        raise ValueError('Effective repository worktree is not uniquely registered')
    if provisional:
        selected = worktrees[:1]
    else:
        if not isinstance(integration_branch, str) or not integration_branch.strip():
            raise ValueError('Reviewed integration branch is required for shared administration')
        selected = [row for row in worktrees
                    if row.get('branch') == 'refs/heads/' + integration_branch]
    if len(selected) != 1:
        raise ValueError('Canonical integration worktree is missing or ambiguous')
    coordinator = Path(selected[0]['path']).resolve()
    if not coordinator.is_dir():
        raise ValueError('Canonical integration worktree is unavailable')
    if Path(_git(coordinator, 'rev-parse', '--show-toplevel')).resolve() != coordinator:
        raise ValueError('Canonical integration worktree registration changed')
    coordinator_common = Path(_git(coordinator, 'rev-parse', '--git-common-dir'))
    coordinator_common = ((coordinator / coordinator_common).resolve()
                          if not coordinator_common.is_absolute() else coordinator_common.resolve())
    if coordinator_common != common:
        raise ValueError('Canonical integration worktree belongs to another repository')
    if not provisional and _git(coordinator, 'symbolic-ref', 'HEAD') != 'refs/heads/' + integration_branch:
        raise ValueError('Canonical integration worktree branch changed')
    return {'repository_root': str(root), 'git_common_dir': str(common),
            'coordinator': str(coordinator), 'integration_branch': integration_branch,
            'role': 'coordinator' if root == coordinator else 'feature'}


def route_step(context: dict, command: list[str], *, operation: str | None = None) -> dict:
    return {'kind': 'workspace_route', 'assignment': 'root',
            'reason': 'Shared ZzzOps administration requires the canonical coordinator worktree',
            'action': 'Retry the exact frozen request from the coordinator worktree.',
            'cwd': context['coordinator'], 'git_common_dir': context['git_common_dir'],
            'repository_root': context['repository_root'],
            'integration_branch': context['integration_branch'],
            'operation': operation, 'command': command}
