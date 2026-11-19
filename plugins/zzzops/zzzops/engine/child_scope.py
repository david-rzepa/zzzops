"""Verify accepted submodule tests without freezing the entire gitlink.

Only local, explicitly declared submodules are inspected. Missing objects and
ambiguous or rewritten history fail closed; this code never fetches child data.
"""
from __future__ import annotations

import os
import subprocess

from engine.errors import Refused
from engine import worktree


def _git(cwd, *args, missing_ok=False):
    p = subprocess.run(['git', '-C', cwd, *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode:
        if missing_ok:
            return None
        raise Refused('validation', 'submodule provenance or child Git objects are unavailable',
                      details={'path': cwd, 'operation': args[0] if args else 'git'})
    return p.stdout


def _links(git, commit):
    raw = git.run('ls-tree', '-r', '-z', commit, text=False).stdout
    out = {}
    for entry in raw.split(b'\0'):
        if not entry:
            continue
        info, name = entry.split(b'\t', 1)
        mode, typ, oid = info.decode().split()
        if mode == '160000':
            out[name.decode('utf-8', 'surrogateescape')] = oid
    return out


def _mapping(git, commit):
    result = git.run('rev-parse', f'{commit}:.gitmodules', check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def _declared(git, commit, path):
    p = git.run('config', '--blob', f'{commit}:.gitmodules', '--get-regexp',
                r'^submodule\..*\.path$', check=False)
    if p.returncode:
        return None
    keys = []
    for line in p.stdout.splitlines():
        key, sep, value = line.partition(' ')
        if sep and value == path:
            keys.append(key[:-len('path')] + 'url')
    if len(keys) != 1:
        return None
    value = git.run('config', '--blob', f'{commit}:.gitmodules', '--get', keys[0], check=False)
    return value.stdout.strip() if value.returncode == 0 else None


def _identity(git, commit, path, repo):
    declared = _declared(git, commit, path)
    origin = _git(repo, 'config', '--get', 'remote.origin.url', missing_ok=True)
    if not declared or not origin or origin.decode('utf-8', 'surrogateescape').strip() != declared:
        raise Refused('validation', 'submodule repository identity or mapping cannot be verified', details={'path': path})


def _child(s, goal, path):
    root = os.path.realpath(worktree.worktree_path(s.git, goal))
    child = os.path.realpath(os.path.join(root, path))
    if child == root or not child.startswith(root + os.sep) or not os.path.isdir(child):
        raise Refused('validation', 'submodule path or child repository is unavailable', details={'path': path})
    _git(child, 'rev-parse', '--git-dir')
    if _git(child, 'ls-files', '--stage', '-z') and _git(child, 'ls-files', '--stage', '-z').find(b'160000 ') >= 0:
        raise Refused('validation', 'nested submodules are unsupported', details={'path': path})
    return child


def _entry(repo, commit, path):
    data = _git(repo, 'ls-tree', '-z', commit, '--', path)
    if not data:
        return None
    meta, name = data.rstrip(b'\0').split(b'\t', 1)
    if name.decode('utf-8', 'surrogateescape') != path:
        raise Refused('validation', 'ambiguous submodule path', details={'path': path})
    return meta.decode()


def capture(s, lease, end, prior):
    """Return frozen parent paths and immutable evidence for child paths."""
    start = (prior or {}).get('parent_start') or lease.work
    prior_children = (prior or {}).get('children', {})
    # Rebased ordinary repositories need no child provenance. Do not impose a
    # submodule ancestry requirement where no child gitlinks are involved.
    if not prior_children and not _links(s.git, end) and (not start or not _links(s.git, start)):
        return {'parent_start': end, 'children': {}}
    if not start or not s.git.is_ancestor(start, end):
        raise Refused('validation', 'submodule test checkpoint provenance is unavailable')
    commits = s.git.out('rev-list', '--reverse', f'{start}..{end}').split()
    parents = [start, *commits]
    mapping = _mapping(s.git, start)
    links = [_links(s.git, c) for c in parents]
    paths = set(prior_children)
    for previous, current in zip(links, links[1:]):
        paths.update(p for p in previous.keys() | current.keys() if previous.get(p) != current.get(p))
    children = {}
    for path in sorted(paths):
        if (not mapping or not _declared(s.git, start, path)
                or any(_mapping(s.git, c) != mapping for c in parents)):
            raise Refused('validation', 'submodule mapping changed or is missing', details={'path': path})
        repo = _child(s, lease.goal, path)
        _identity(s.git, start, path, repo)
        saved = prior_children.get(path) or {}
        initial = saved.get('baseline') or links[0].get(path)
        if not initial:
            raise Refused('validation', 'submodule baseline missing', details={'path': path})
        prev = initial
        protected = set((saved.get('entries') or {}).keys())
        for state in links:
            target = state.get(path)
            if not target:
                raise Refused('validation', 'submodule gitlink missing in test history', details={'path': path})
            if target == prev:
                continue
            if _git(repo, 'merge-base', '--is-ancestor', prev, target, missing_ok=True) is None:
                raise Refused('validation', 'submodule test history is not a descendant', details={'path': path})
            chain = _git(repo, 'rev-list', '--reverse', '--parents', f'{prev}..{target}').decode().splitlines()
            for line in chain:
                commits = line.split()
                if len(commits) < 2:
                    raise Refused('validation', 'unsupported or rewritten submodule test history', details={'path': path})
                for parent in commits[1:]:
                    if parent != prev and _git(repo, 'merge-base', '--is-ancestor', prev, parent, missing_ok=True) is None:
                        raise Refused('validation', 'submodule test history has an unverified parent', details={'path': path})
                    changes = _git(repo, 'diff', '--no-renames', '--name-only', '-z', parent, commits[0])
                    protected.update(x.decode('utf-8', 'surrogateescape') for x in changes.split(b'\0') if x)
            prev = target
        entries = {p: _entry(repo, prev, p) for p in sorted(protected)}
        children[path] = {'baseline': initial, 'accepted': prev, 'mapping': mapping, 'entries': entries}
    return {'parent_start': start, 'children': children}


def verify(s, goal, commit, evidence):
    """Verify an implementation commit against the accepted child entries."""
    if not evidence:
        return
    links = _links(s.git, commit)
    for path, entry in (evidence.get('children') or {}).items():
        if _mapping(s.git, commit) != entry['mapping'] or not _declared(s.git, commit, path):
            raise Refused('test_freeze', 'submodule mapping or repository identity changed', details={'path': path})
        repo = _child(s, goal, path)
        _identity(s.git, commit, path, repo)
        target = links.get(path)
        accepted = entry['accepted']
        if not target or _git(repo, 'merge-base', '--is-ancestor', accepted, target, missing_ok=True) is None:
            raise Refused('test_freeze', 'submodule implementation is not a descendant of accepted tests', details={'path': path})
        chain = _git(repo, 'rev-list', '--reverse', '--parents', f'{accepted}..{target}').decode().splitlines()
        commits = [accepted]
        for line in chain:
            parts = line.split()
            if len(parts) < 2 or any(parent != accepted and _git(
                    repo, 'merge-base', '--is-ancestor', accepted, parent, missing_ok=True) is None
                    for parent in parts[1:]):
                raise Refused('test_freeze', 'unsupported or rewritten submodule implementation history',
                              details={'path': path})
            commits.append(parts[0])
        for current in commits:
            for name, value in entry['entries'].items():
                if _entry(repo, current, name) != value:
                    raise Refused('test_freeze', f'submodule implementation changed accepted test path {path}/{name}',
                                  details={'path': f'{path}/{name}'})
