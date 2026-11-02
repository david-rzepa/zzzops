"""Code identities, artifact commits and the I1/I2 checks (SPEC §4.7)."""

from __future__ import annotations

import re

from engine.canon import EMPTY_TREE, ZERO
from engine.errors import EngineError, Refused
from engine.gitrun import Git

REVIEW = (".zzzops", "reviews")
REVIEW_PATH = ".zzzops/reviews"
REVIEW_PREFIX = "docs(review): "

DIFF = ["--binary", "--full-index", "--no-color", "--no-ext-diff", "--no-textconv", "--no-renames", "--no-relative",
        "--unified=3", "--inter-hunk-context=0", "--diff-algorithm=myers", "--indent-heuristic",
        "--src-prefix=a/", "--dst-prefix=b/", "-O/dev/null", "--submodule=short", "--ignore-submodules=none"]
CFG = ["-c", "diff.noprefix=false", "-c", "diff.mnemonicPrefix=false", "-c", "core.quotePath=true",
       "-c", "core.attributesFile=", "-c", "diff.suppressBlankEmpty=false"]
PATHSPEC = ["--", ":/", ":(top,exclude).zzzops/reviews"]
CONVENTIONAL_TYPES = {"feat", "fix", "perf", "revert", "docs", "style", "chore", "refactor", "test", "build", "ci"}
CONVENTIONAL = re.compile(r"^(" + "|".join(sorted(CONVENTIONAL_TYPES)) + r")(?P<scope>\([^()\r\n]+\))?(?P<bang>!)?: (?P<summary>\S.*)$")


def conventional(subject: str):
    m = CONVENTIONAL.fullmatch(subject)
    return (m.group(1), m.group("scope"), m.group("bang")) if m else None


def view_paths(scope=None, exclude=None):
    paths = [":(top,literal)" + p for p in scope] if scope is not None else [":/"]
    return [*paths, ":(top,exclude).zzzops/reviews", *[":(exclude,top,literal)" + p for p in exclude or []]]



class Identity:
    def __init__(self, git: Git):
        self.git = git
        self._trees = {}

    # ------------------------------------------------------------------ trees
    def ls_tree(self, tree: str) -> dict:
        out = self.git.run("ls-tree", "-z", tree, text=False).stdout
        entries = {}
        for rec in out.split(b"\0"):
            if not rec:
                continue
            meta, name = rec.split(b"\t", 1)
            mode, typ, oid = meta.decode().split(" ")
            entries[name] = (mode, typ, oid)
        return entries

    def mktree(self, entries: dict) -> str:
        data = b"".join(f"{m} {t} {o}\t".encode() + name + b"\0" for name, (m, t, o) in entries.items())
        return self.git.run("mktree", "-z", input=data, text=False).stdout.decode().strip()

    def strip(self, tree: str, parts: tuple) -> str:
        E = self.ls_tree(tree)
        key = parts[0].encode()
        if key not in E:
            return tree
        if len(parts) == 1:
            del E[key]
        else:
            sub = E[key][2]
            s = self.strip(sub, parts[1:])
            if s == sub:
                return tree
            if s == EMPTY_TREE:
                del E[key]
            else:
                E[key] = ("040000", "tree", s)
        return self.mktree(E)

    def code_tree(self, commit: str) -> str:
        if commit not in self._trees:
            tree = self.git.out("rev-parse", f"{commit}^{{tree}}")
            self._trees[commit] = self.strip(tree, REVIEW)
        return self._trees[commit]

    # ------------------------------------------------------------------ change and patch ids
    def change(self, base: str, commit: str, paths: list[str] | None = None) -> str:
        if paths == []:
            return ZERO
        d = self.git.run(*CFG, f"--attr-source={commit}", "diff", *DIFF, base, commit, "--", *view_paths(paths), identity=True,
                         check=False, text=False)
        if d.returncode != 0:
            raise EngineError(f"git diff failed: {d.stderr.decode('utf-8', 'replace').strip().splitlines()[:1]}")
        if not d.stdout.strip():
            return ZERO
        out = self.git.run("patch-id", "--verbatim", input=d.stdout, identity=True, check=False, text=False)
        if out.returncode != 0:
            raise EngineError("git patch-id failed")
        text = out.stdout.decode().strip()
        return text.split()[0] if text else ZERO

    def patch_ids(self, a: str | None, b: str) -> list:
        """[(commit, patch id)] for a..b in --reverse --topo-order order; empty diffs get ZERO."""
        rng = f"{a}..{b}" if a else b
        commits = [c for c in self.git.out("rev-list", "--reverse", "--topo-order", "--no-merges", rng).split() if c]
        if not commits:
            return []
        log = self.git.run(*CFG, f"--attr-source={b}", "log", "-p", "--no-merges", "--format=commit %H", *DIFF, rng,
                           identity=True, check=False, text=False)
        if log.returncode != 0:
            raise EngineError("git log -p failed")
        ids = self.git.run("patch-id", "--verbatim", input=log.stdout, identity=True, text=False).stdout.decode()
        pid = {}
        for line in ids.splitlines():
            parts = line.split()
            if len(parts) == 2:
                pid[parts[1]] = parts[0]
        return [(c, pid.get(c, ZERO)) for c in commits]

    # ------------------------------------------------------------------ review commits, I1/I2
    def subject(self, c: str) -> str:
        return self.git.out("log", "-1", "--format=%s", c)

    def changed_paths(self, c: str) -> list:
        out = self.git.run("diff-tree", "-r", "--no-commit-id", "--no-renames", "--name-only", "-z", "--root", c,
                           text=False).stdout
        return [p.decode("utf-8", "surrogateescape") for p in out.split(b"\0") if p]

    def is_review(self, c: str) -> bool:
        return (self.subject(c).startswith(REVIEW_PREFIX)
                and all(p.startswith(REVIEW_PATH + "/") for p in self.changed_paths(c)))

    def own_commits(self, base, tip, merges=False):
        """First-parent work history, excluding all previous synced bases (G1038)."""
        syncs = self.git.out("rev-list", "--first-parent", "--merges", tip, *( ["^" + base] if base else [])).split()
        exclude = [base] if base else []
        for c in syncs:
            ps = self.git.out("rev-list", "--parents", "-n", "1", c).split()[1:]
            exclude.extend(ps[1:])
            body = self.git.out("show", "-s", "--format=%B", c)
            exclude.extend(re.findall(r"^Zzzops-Old-Base: ([0-9a-f]{40})$", body, re.M))
        return self.git.out("rev-list", "--reverse", "--first-parent", *([] if merges else ["--no-merges"]),
                            tip, *("^" + b for b in dict.fromkeys(exclude))).split()

    def sync_merges(self, base, tip):
        return [c for c in self.git.out("rev-list", "--reverse", "--first-parent", "--merges", tip,
                                       *(["^" + base] if base else [])).split()
                if self.subject(c).startswith("chore(sync): ") and
                re.search(r"^Zzzops-Old-Base: [0-9a-f]{40}$", self.git.out("show", "-s", "--format=%B", c), re.M)]

    def check_i1_i2(self, a: str | None, b: str):
        for c in self.own_commits(a, b, merges=True):
            parents = self.git.out("rev-list", "--parents", "-n", "1", c).split()[1:]
            subject = self.subject(c)
            if len(parents) > 1:
                if len(parents) != 2 or not subject.startswith("chore(sync): "):
                    raise Refused("validation", f"merge commit {c[:12]}: only base makes merge commits in a work branch")
                if self.entry(c, REVIEW_PATH) != self.entry(parents[0], REVIEW_PATH):
                    raise Refused("validation", f"I2 violated by {c[:12]}: a sync merge changes {REVIEW_PATH}")
                continue
            paths = self.changed_paths(c)
            if subject.startswith(REVIEW_PREFIX) and any(not p.startswith(REVIEW_PATH + "/") for p in paths):
                raise Refused("validation", f"I1 violated by {c[:12]}: a docs(review): commit touches code",
                              hint="split the commit: review files only in docs(review): commits")
            if not subject.startswith(REVIEW_PREFIX) and any(p.startswith(REVIEW_PATH + "/") for p in paths):
                raise Refused("validation", f"I2 violated by {c[:12]}: a code commit touches {REVIEW_PATH}",
                              hint=f"move the {REVIEW_PATH} change into a docs(review): commit")

    # ------------------------------------------------------------------ artifacts
    def put(self, tree: str | None, parts: list, blob: str) -> str:
        E = self.ls_tree(tree) if tree else {}
        key = parts[0].encode()
        if len(parts) == 1:
            E[key] = ("100644", "blob", blob)
        else:
            sub = E[key][2] if key in E and E[key][1] == "tree" else None
            E[key] = ("040000", "tree", self.put(sub, parts[1:], blob))
        return self.mktree(E)

    def entry(self, commit: str, path: str) -> str | None:
        p = self.git.run("rev-parse", "--verify", "--quiet", f"{commit}:{path}", check=False)
        return p.stdout.strip() or None if p.returncode == 0 else None

    def set_entry(self, tree, parts, entry):
        E = self.ls_tree(tree) if tree else {}
        name = parts[0].encode("utf-8", "surrogateescape")
        if len(parts) == 1:
            if entry is None:
                E.pop(name, None)
            else:
                E[name] = entry
        else:
            sub = E[name][2] if name in E and E[name][1] == "tree" else None
            result = self.set_entry(sub, parts[1:], entry)
            if result == EMPTY_TREE:
                E.pop(name, None)
            else:
                E[name] = ("040000", "tree", result)
        return self.mktree(E)

    def path_entry(self, tree, path):
        parts = path.split("/")
        for i, part in enumerate(parts):
            e = self.ls_tree(tree).get(part.encode("utf-8", "surrogateescape"))
            if e is None:
                return None
            if i == len(parts) - 1:
                return e
            if e[1] != "tree":
                return None
            tree = e[2]

    def artifact_commit(self, tip: str | None, integration: str, goal: int, node: str, data: bytes) -> tuple:
        """(new tip, artifact value). The first artifact of a goal is born at the integration tip."""
        path = f"{REVIEW_PATH}/{goal}/{node}.md"
        blob = self.git.hash_object(data)
        parent = tip or integration
        if self.entry(parent, path) == blob:
            return parent, {"path": path, "blob": blob, "commit": parent}
        tree = self.put(self.git.out("rev-parse", f"{parent}^{{tree}}"), path.split("/"), blob)
        c = self.git.commit_tree(tree, [parent], f"{REVIEW_PREFIX}{node} for G{goal}\n")
        return c, {"path": path, "blob": blob, "commit": c}
