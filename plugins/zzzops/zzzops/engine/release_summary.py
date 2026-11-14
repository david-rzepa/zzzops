"""Read-only release summaries derived from the portfolio and recorded line operations."""
from __future__ import annotations

from engine.lines import members
from engine.schemas import SHA


def publication(doc, nodes, unavailable=False):
    """Closure alone proves nothing; report only a recorded production merge."""
    for n, nd in nodes.items():
        if nd.get('op') != 'git.line_finish':
            continue
        record = (doc.get('records') or {}).get(n) or {}
        evidence = {}
        if record.get('status') == 'done' and record.get('ok'):
            evidence = record.get('output') or {}
        elif record.get('status') == 'blocked':
            evidence = (record.get('blocked') or {}).get('op_state') or {}
        commit = evidence.get('production_merge')
        if isinstance(commit, str) and SHA.fullmatch(commit):
            back = evidence.get('back_merges', evidence.get('back', {}))
            if not isinstance(back, dict) or any(
                    not isinstance(branch, str) or (sha is not None and
                    (not isinstance(sha, str) or not SHA.fullmatch(sha))) for branch, sha in back.items()):
                back = None
            return {'state': 'published', 'merge_commit': commit,
                    'back_merges': dict(back) if back is not None else None}
    return {'state': 'unknown' if unavailable or doc.get('state') == 'closed' else 'not_recorded'}


def reference(item, fields):
    """Keep advisory references distinct from the actionable item schema."""
    return {('item_kind' if key == 'kind' else key): item[key] for key in fields if key in item}


def build(ctx, p, items, paused=False, global_blockers=()):
    from engine.render import command, goal_summary, state_string
    out = []
    target = ctx.settings['branching']['production']
    for line in p.lines:
        res = p.goals.get(line.goal)
        doc = res.doc if res else ctx.goal_docs.get(line.goal)
        view = p.views.get(line.goal) or {}
        nodes = res.graph.nodes if res else view.get('nodes') or {}
        ids = members(p.ledger, line)
        counts = {'total': len(ids), 'done': 0, 'closed_other': 0, 'open': 0, 'held': 0}
        unfinished = []
        for g in ids:
            entry = p.ledger[g]
            if entry['state'] == 'closed':
                counts['done' if entry.get('closed') == 'done' else 'closed_other'] += 1
                continue
            counts[entry['state']] += 1
            member = p.goals.get(g)
            detail = goal_summary(member, ctx) if member else {'id': g, 'state': entry['state']}
            detail['goal'] = detail.pop('id')
            detail['expand'] = command(ctx, ['next', '--goal', str(g)])
            unfinished.append(detail)
        relevant = set(ids) | {line.goal}
        next_items, blockers = [], [reference(b, b) for b in global_blockers] if paused else []
        if ctx.coordinator.get("current") is False:
            blockers.append({"item_kind": "offline", "reason": "showing the last fetch; refresh repository state"})
        for kind, values in items.items():
            for item in values:
                goals = {item['goal']} if 'goal' in item else set(item.get('goals') or [])
                if not goals & relevant:
                    continue
                if kind in ('actions', 'needs_human') and not paused:
                    ref = reference(item, ('goal', 'node', 'kind'))
                    ref.setdefault('goal', line.goal)
                    ref['expand'] = item.get('expand') or command(ctx, ['next', '--goal', str(ref['goal'])])
                    next_items.append(ref)
                if kind == 'waiting' or kind == 'needs_human' and item['kind'] != 'approve':
                    blockers.append(reference(item, ('goal', 'node', 'kind', 'reason', 'until', 'question', 'since', 'expand')))
        for member in unfinished:
            if member['state'] == 'held':
                blockers.append({'goal': member['goal'], 'reason': 'goal held'})
            elif member['goal'] in p.invalid:
                blockers.append({'goal': member['goal'], 'reason': 'invalid goal', 'errors': p.invalid[member['goal']]})
        workflow = []
        if res:
            for n in res.graph.topo:
                s = res.st[n]
                workflow.append({'node': n, 'state': s['name'], 'description': state_string(s)})
        elif doc:
            for n in nodes:
                record = (doc.get('records') or {}).get(n) or {}
                status = record.get('status', 'not_recorded')
                workflow.append({'node': n, 'state': status, 'description': 'recorded ' + status})
        out.append({'kind': line.kind, 'name': line.name, 'goal': line.goal, 'state': line.state,
                    'branch': line.branch, 'head': ctx.targets.get(line.branch), 'target': target,
                    'members': counts, 'unfinished': unfinished, 'workflow': workflow,
                    'next': next_items, 'blockers': blockers,
                    'publication': publication(doc or {}, nodes, unavailable=doc is None)})
    return out


def trim(out, limit, canonical):
    """Advisory summaries yield space before the existing actions and human decisions."""
    releases = out['releases']
    summaries = releases['summaries']
    while len(canonical(out)) > limit and summaries:
        candidates = [(len(canonical(summary[key])), summary, key)
                      for summary in summaries for key in ('unfinished', 'workflow', 'next', 'blockers')
                      if summary[key]]
        if candidates:
            _, summary, key = max(candidates, key=lambda x: x[0])
            summary[key].pop()
            summary.setdefault('truncated', {})[key] = summary.get('truncated', {}).get(key, 0) + 1
        else:
            # Keep active lines in preference to historical summaries.
            index = next((i for i, summary in enumerate(summaries) if summary['state'] == 'closed'), len(summaries) - 1)
            summaries.pop(index)
        releases['summaries_expand'] = 'next --all'
