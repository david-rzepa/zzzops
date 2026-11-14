"""Deterministic tests/implementation tree overlay for git.integrate (G1038)."""
from __future__ import annotations

from collections import Counter
import re

from engine.identity import conventional


def rebuild(ctx, ident, base, work, code_tree):
    git = ctx.git
    graph, records = ctx.graph, (ctx.doc or {}).get("records") or {}
    preserved = {n.get("preserve") for n in graph.nodes.values() if n.get("preserve")} if graph else set()
    frozen = sorted({p for n in preserved for p in (records.get(n) or {}).get("frozen") or []})
    tests_tree = ident.code_tree(base)
    for path in frozen:
        tests_tree = ident.set_entry(tests_tree, path.split("/"), ident.path_entry(code_tree, path))
    own = [c for c in ident.own_commits(base, work) if not ident.is_review(c)]
    tests, code = [], []
    for c in own:
        parsed = conventional(ident.subject(c))
        bucket = tests if parsed and parsed[0] == "test" and set(ident.changed_paths(c)) <= set(frozen) else code
        bucket.append(c)
    typ = release_type(git, ident, code)
    breaking = any((conventional(ident.subject(c)) or (None, None, None))[2]
                   or breaking_notes(git.out("show", "-s", "--format=%B", c)) for c in code)
    title = f"{ctx.doc['title']} (G{ctx.goal})"
    parts = []
    def part(tree, commits, prefix):
        subjects = [ident.subject(c) for c in commits]
        body = "\n".join(subjects[:30])
        if len(subjects) > 30:
            body += f"\nand {len(subjects) - 30} more"
        if prefix != "test":
            footers = [x for c in commits for x in breaking_notes(git.out("show", "-s", "--format=%B", c))]
            body += ("\n\n" + "\n\n".join(footers)) if footers else ""
        subject = f"{prefix}: " + title[:max(1, 72 - len(prefix) - 2)]
        source = max(reversed(commits or own or [work]), key=lambda c: int(git.out("show", "-s", "--format=%at", c)))
        author = git.out("show", "-s", "--format=%an%x00%ae", source).split("\0")
        timestamp = max([int(git.out("show", "-s", "--format=%at", c)) for c in commits or [source]])
        parts.append((tree, subject + "\n\n" + body.strip() + "\n", author, timestamp))
    if tests_tree != ident.code_tree(base):
        part(tests_tree, tests, "test")
    if code_tree != tests_tree:
        part(code_tree, code, typ + ("!" if breaking else ""))
    previous = ctx.snap.pr.get(ctx.goal)
    if previous:
        old = git.out("rev-list", "--reverse", "--first-parent", f"{base}..{previous}").split()
        if len(old) == len(parts) and (not old or git.out("rev-parse", old[0] + "^") == base):
            if all(git.out("rev-parse", c + "^{tree}") == tree and
                   git.out("show", "-s", "--format=%B", c) == msg.strip() and
                   git.out("show", "-s", "--format=%an%x00%ae", c).split("\0") == author
                   for c, (tree, msg, author, _) in zip(old, parts)):
                return previous
    clock = 0
    if previous:
        for c in [previous, *git.out("rev-list", "--parents", "-n", "1", previous).split()[1:2]]:
            clock = max(clock, *(int(v) for v in git.out("show", "-s", "--format=%at %ct", c).split()))
    from engine.ops.integrate import committer
    cn, ce = committer(git)
    parent = base
    for tree, msg, author, timestamp in parts:
        clock = max(timestamp, clock + 1)
        env = {"GIT_AUTHOR_NAME": author[0], "GIT_AUTHOR_EMAIL": author[1],
               "GIT_COMMITTER_NAME": cn, "GIT_COMMITTER_EMAIL": ce,
               "GIT_AUTHOR_DATE": f"@{clock} +0000", "GIT_COMMITTER_DATE": f"@{clock} +0000"}
        parent = git.commit_tree(tree, [parent], msg, env=env)
    return parent


def breaking_notes(body):
    return re.findall(r"(?m)^BREAKING(?: CHANGE|-CHANGE):[^\n]*(?:\n(?!\n)[^\n]+)*", body)


def release_type(git, ident, commits):
    kinds = [(conventional(ident.subject(c)) or ("chore",))[0] for c in commits]
    for typ in ("feat", "fix", "perf", "revert"):
        if typ in kinds:
            return typ
    counts = Counter(kinds)
    return max(reversed(kinds), key=lambda x: counts[x]) if kinds else "chore"
