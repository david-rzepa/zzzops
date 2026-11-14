"""Review hints for a moved base, independent of carry and review decisions (G1039)."""
from __future__ import annotations

import re

from engine.render import scoped_git_command
from engine.schemas import SHA


def diff_lines(git, base, tip):
    """Two views of one diff: NUL-delimited paths and the corresponding zero-context patches."""
    data = git.run('-c', 'core.quotePath=true', 'diff', '--raw', '-z', '--patch', '--unified=0',
                   '--no-renames', '--no-color', '--no-ext-diff', '--no-textconv', '--no-relative',
                   base, tip, '--', ':/', ':(top,exclude).zzzops/reviews', text=False).stdout
    if not data:
        return {}
    raw, _, patch = data.partition(b'\0\0')
    fields = raw.split(b'\0')
    paths = [p.decode('utf-8', 'surrogateescape') for p in fields[1::2]]
    sections = []
    for line in patch.splitlines():
        if line.startswith(b'diff --git '):
            sections.append([])
        elif sections:
            sections[-1].append(line)
    result = {}
    for path, lines in zip(paths, sections):
        added, removed, hunk = [], [], False
        for line in lines:
            if line.startswith(b'@@'):
                hunk = True
            elif hunk and line[:1] in (b'+', b'-'):
                (added if line[:1] == b'+' else removed).append(line[1:].decode('utf-8', 'replace').strip())
        result[path] = (added, removed)
    return result


def names(lines):
    return {word for line in lines for word in re.findall(r'\b[A-Za-z_][A-Za-z0-9_]*\b', line)
            if ('_' in word and any(c.isalpha() for c in word)) or
            (len(word) > 1 and word.isupper()) or re.search(r'[a-z][A-Z]', word)}


def build(git, graph, doc, node, stale, values, reader):
    if not graph.is_review(node):
        return None
    subject = graph.subject(node)
    records = doc.get('records') or {}
    reviewed = (records.get(node) or {}).get('reviewed') or {}
    current = (records.get(subject) or {}).get('output') or {}
    pair = next(((old, current.get(key)) for key, old in reviewed.items()
                 if isinstance(old, dict) and 'base' in old and isinstance(current.get(key), dict)), None)
    if not pair:
        return None
    old, checkpoint = pair
    for name, selector in graph.selectors[node].items():
        if ('inputs.' + name not in stale or selector.kind != 'node' or
                graph.nodes[selector.node].get('op') != 'git.base'):
            continue
        onto = values.get(name)
        if not isinstance(onto, str) or not SHA.fullmatch(onto) or onto == old['base']:
            continue
        before = old['base']
        trunk = diff_lines(git, before, onto)
        goal = diff_lines(git, checkpoint['base'], checkpoint['commit'])
        goal_added = {line for added, _ in goal.values() for line in added}
        goal_removed = {line for _, removed in goal.values() for line in removed} - goal_added
        goal_removed = {line for line in goal_removed if len(line) >= 8 and any(c.isalpha() for c in line)}
        removed_names = names(line for _, lines in goal.values() for line in lines) - names(goal_added)
        used_names = names(goal_added)
        trunk_added_names = names(line for lines, _ in trunk.values() for line in lines)
        synced = ((records.get(selector.node) or {}).get('output') or {}).get('synced') or {}
        resolved = set(synced.get('resolved') or []) if synced.get('merge') else set()
        touching = []
        for path in sorted(set(trunk) | resolved):
            added, removed = trunk.get(path, ([], []))
            line_hits = sorted(set(added) & goal_removed)
            use_hits = sorted(names(added) & removed_names)
            remove_hits = sorted((names(removed) - trunk_added_names) & used_names)
            if path in resolved:
                rank, why = 0, f"resolved by hand in sync {synced['merge'][:7]}"
            elif line_hits:
                rank, why = 1, f'trunk adds `{line_hits[0]}`, a line the goal removes'
            elif use_hits:
                rank, why = 1, 'trunk uses `' + ', '.join(use_hits) + '`, which the goal removes'
            elif remove_hits:
                rank, why = 1, 'trunk removes `' + ', '.join(remove_hits) + '`, which the goal uses'
            elif path in goal:
                a, r = goal[path]
                rank, why = 2, f'the goal also changes this file (+{len(a)}/-{len(r)})'
            else:
                continue
            touching.append((rank, path, why))
        entries = [{'path': path, 'why': why} for _, path, why in sorted(touching)]
        inline = entries[:12]
        # With no touching paths, show an empty scoped diff rather than an unbounded trunk diff.
        diff_tip = onto if inline else before
        result = {'from': before, 'to': onto,
                  'commits': int(git.out('rev-list', '--count', '--first-parent', f'{before}..{onto}')),
                  'files': len(trunk), 'touching': inline, 'more': max(0, len(entries) - 12),
                  'diff': scoped_git_command(['diff', before, diff_tip], [entry['path'] for entry in inline]),
                  'log': f'git log --oneline --first-parent {before}..{onto}'}
        if len(entries) > 12:
            import json
            result['all'] = reader.blob_view(json.dumps(entries, indent=2, ensure_ascii=False))
        return result
    return None
