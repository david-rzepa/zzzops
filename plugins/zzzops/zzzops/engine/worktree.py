"""The goal worktree and the sync rule (SPEC §4.13)."""

from __future__ import annotations

import os

from engine.errors import Refused
from engine.gitrun import Git, GitError
from engine.identity import Identity

EXCLUDE = "/.zzzops/worktrees/"


def worktree_path(git: Git, g: int) -> str:
    return os.path.join(git.primary, ".zzzops", "worktrees", f"g{g}")


def branch(g: int) -> str:
    return f"zzzops/work/g{g}"


def registered_worktrees(git: Git) -> list:
    """Paths from `git worktree list --porcelain`, retried while a concurrent worktree change makes Git fail
    (G1041); GitError with Git's last exit code and stderr when every try failed."""
    paths, rc, stderr = Git.worktree_paths(git.primary)
    if paths is None:
        raise GitError(["worktree", "list", "--porcelain"], rc, stderr)
    return paths


def install_ignore(git: Git):
    path = os.path.join(git.common, "info", "exclude")
    try:
        existing = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
        if EXCLUDE not in existing.splitlines():
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a", encoding="utf-8") as fh:
                if existing and not existing.endswith("\n"):
                    fh.write("\n")
                fh.write(EXCLUDE + "\n")
    except OSError:
        pass


def rebase_in_progress(git: Git, p: str) -> bool:
    gd = git.run("rev-parse", "--git-dir", cwd=p).stdout.strip()
    gd = gd if os.path.isabs(gd) else os.path.join(p, gd)
    return os.path.isdir(os.path.join(gd, "rebase-merge")) or os.path.isdir(os.path.join(gd, "rebase-apply"))


def ensure_worktree(git: Git, snap, g: int, self_sync: bool = False) -> str:
    p = worktree_path(git, g)
    install_ignore(git)
    known = [os.path.realpath(x) for x in registered_worktrees(git)]
    if os.path.realpath(p) not in known:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        if git.rev_parse(f"refs/heads/{branch(g)}"):
            git.run("worktree", "add", "-q", p, branch(g))
        elif snap.work.get(g):
            git.run("worktree", "add", "-q", "--no-track", "-b", branch(g), p, snap.work[g])
        else:
            git.run("worktree", "add", "-q", "--no-track", "-b", branch(g), p, snap.integration)
    if not self_sync:
        head = git.run("symbolic-ref", "-q", "HEAD", cwd=p, check=False).stdout.strip()
        if head != f"refs/heads/{branch(g)}":
            raise Refused("dirty_worktree", f"the goal worktree is not on {branch(g)}", details={"worktree": p},
                          hint=f"git -C {p} checkout {branch(g)}")
        if rebase_in_progress(git, p):
            raise Refused("dirty_worktree", f"finish or abort the rebase in {p}", details={"worktree": p})
    return p


def is_clean(git: Git, p: str) -> bool:
    return git.run("status", "--porcelain=v1", "-z", "--untracked-files=all", cwd=p).stdout == ""


def salvage_lines(git: Git, snap, g: int, node: str, attempt, local_tip: str | None = None) -> list:
    p = worktree_path(git, g)
    lc = local_tip or "HEAD"
    return [f"git -C {p} branch zzzops-salvage/g{g}-{node}-a{attempt} {lc}",
            f"git -C {p} reset --keep {snap.R}/zzzops/work/g{g}",
            "Tell the human which commits were saved; nothing was pushed."]


def sync(git: Git, ident: Identity, snap, g: int, mode: str, node: str = "?", attempt="?", self_sync=False) -> str:
    """'equal' or 'ahead' (the caller pushes the local tip); refuses `dirty_worktree` or `sync_refused`."""
    p = ensure_worktree(git, snap, g, self_sync=self_sync)
    if mode == "clean" and not is_clean(git, p):
        raise Refused("dirty_worktree", f"the goal worktree {p} has uncommitted changes",
                      hint="commit or stash them, then retry", details={"worktree": p})
    Lc = git.rev_parse(f"refs/heads/{branch(g)}")
    Rc = snap.work.get(g)
    if Rc is None:
        return "ahead"
    if Lc == Rc:
        return "equal"
    if git.is_ancestor(Lc, Rc):
        git.run("rebase", "-q", "--autostash", Rc, cwd=p)
        return "equal"
    if git.is_ancestor(Rc, Lc):
        return "ahead"
    remote_only = git.out("rev-list", f"{Lc}..{Rc}").split()
    local_only = git.out("rev-list", f"{Rc}..{Lc}").split()
    if remote_only and all(ident.is_review(c) for c in remote_only):
        r = git.run("rebase", "-q", "--autostash", Rc, cwd=p, check=False)
        if r.returncode == 0:
            return "ahead"
        git.run("rebase", "--abort", cwd=p, check=False)
    mb = git.out("merge-base", Lc, Rc)
    remote_ids = {pid for _, pid in ident.patch_ids(mb, Rc)}
    local_ids = ident.patch_ids(mb, Lc)
    if local_ids and all(pid in remote_ids for _, pid in local_ids):
        git.run("reset", "-q", "--keep", Rc, cwd=p)
        return "equal"
    subj = lambda c: git.out("log", "-1", "--format=%s", c)
    raise Refused("sync_refused", "the goal worktree and the remote work branch have diverged",
                  details={"local_only": [{"commit": c, "subject": subj(c),
                                           "patch_equivalent_on_remote": dict(local_ids).get(c) in remote_ids}
                                          for c in local_only],
                           "remote_only": [{"commit": c, "subject": subj(c),
                                            "author": git.out("log", "-1", "--format=%an", c)} for c in remote_only],
                           "merge_base": mb},
                  hint="\n".join(salvage_lines(git, snap, g, node, attempt, Lc)))


def local_tip(git: Git, g: int) -> str | None:
    return git.rev_parse(f"refs/heads/{branch(g)}")


def remove_if_safe(git: Git, snap, g: int) -> str:
    p = worktree_path(git, g)
    if not os.path.isdir(p):
        return "absent"
    try:
        if not is_clean(git, p):
            return "kept: uncommitted changes"
        if local_tip(git, g) != snap.work.get(g):
            return "kept: local commits are not on the remote"
        git.run("worktree", "remove", p)
        git.run("branch", "-q", "-D", branch(g), check=False)
        return "removed"
    except Exception as exc:                                     # best effort
        return f"kept: {exc}"
