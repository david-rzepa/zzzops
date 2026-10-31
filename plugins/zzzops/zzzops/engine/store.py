"""Fetch and snapshot (SPEC §4.2), reading goals and policy (§4.3), per-goal compare-and-swap writes (§4.4) and the
engine floor and ceiling (§4.5)."""

from __future__ import annotations

import json
import os
import random
import re
import time
from dataclasses import dataclass, field

from engine import ENGINE_VERSION, GOAL_SCHEMAS, POLICY_SCHEMA, REQUIRES_MIN
from engine.canon import goal_bytes, version_tuple
from engine.errors import Refused
from engine.gitrun import Git, GitError
from engine.leases import parse_message, to_lease
from engine.ops import OPS
from engine import schemas

GOAL_REF = re.compile(r"^g(\d+)$")


class RemoteError(Exception):
    pass


@dataclass
class Snapshot:
    R: str
    I: str
    integration: str | None = None
    goals: dict = field(default_factory=dict)        # id -> accepted tip
    rewritten: dict = field(default_factory=dict)    # id -> the force-pushed tip
    deleted: set = field(default_factory=set)
    leases: dict = field(default_factory=dict)       # (id, node) -> tip
    policy: dict = field(default_factory=dict)       # topic -> tip
    work: dict = field(default_factory=dict)         # id -> tip (requested goals only)
    pr: dict = field(default_factory=dict)
    stack: dict = field(default_factory=dict)
    dep_pr: dict = field(default_factory=dict)
    current: bool = True
    known: set = field(default_factory=set)          # every goal id this clone has seen

    def ref_value(self, ref: str):
        m = re.match(r"^refs/heads/zzzops/(goal|work|pr|stack)/g(\d+)$", ref)
        if m:
            kind, g = m.group(1), int(m.group(2))
            return {"goal": self.goals, "work": self.work, "pr": self.pr, "stack": self.stack}[kind].get(g)
        m = re.match(r"^refs/heads/zzzops/lease/g(\d+)/(.+)$", ref)
        if m:
            return self.leases.get((int(m.group(1)), m.group(2)))
        return None

    def advance(self, updates):
        """Apply this invocation's own successful push (SPEC §4.2: the embedded next reuses the snapshot)."""
        for ref, _, new in updates:
            m = re.match(r"^refs/heads/zzzops/(goal|work|pr|stack)/g(\d+)$", ref)
            if m:
                table = {"goal": self.goals, "work": self.work, "pr": self.pr, "stack": self.stack}[m.group(1)]
                g = int(m.group(2))
                if new:
                    table[g] = new
                    if m.group(1) == "goal":
                        self.known.add(g)
                else:
                    table.pop(g, None)
                continue
            m = re.match(r"^refs/heads/zzzops/lease/g(\d+)/(.+)$", ref)
            if m:
                key = (int(m.group(1)), m.group(2))
                if new:
                    self.leases[key] = new
                else:
                    self.leases.pop(key, None)


def resolve_remote(git: Git, remote: str | None) -> str:
    return remote or git.config("zzzops.remote") or "origin"


def resolve_integration(git: Git, R: str, integration: str | None) -> str:
    if integration:
        return integration
    v = git.config("zzzops.integrationBranch")
    if v:
        return v
    p = git.run("symbolic-ref", "--short", f"refs/remotes/{R}/HEAD", check=False)
    if p.returncode == 0 and p.stdout.strip().startswith(R + "/"):
        return p.stdout.strip()[len(R) + 1:]
    p = git.run("ls-remote", "--symref", R, "HEAD", check=False)
    for line in p.stdout.splitlines():
        if line.startswith("ref: refs/heads/") and line.endswith("\tHEAD"):
            return line[len("ref: refs/heads/"):-len("\tHEAD")]
    raise Refused("not_found", "cannot determine the integration branch", hint="set zzzops.integrationBranch")


# --------------------------------------------------------------------------------------------- fetch


def coordinator_fetch(git: Git, R: str, I: str, goals=(), deps=()) -> Snapshot:
    specs = [f"+refs/heads/{I}:refs/remotes/{R}/{I}",
             f"refs/heads/zzzops/goal/*:refs/zzzops/goal/{R}/*",
             f"+refs/heads/zzzops/lease/*:refs/remotes/{R}/zzzops/lease/*",
             f"+refs/heads/zzzops/policy/*:refs/remotes/{R}/zzzops/policy/*"]
    goals = sorted(set(int(g) for g in goals))
    for g in goals:
        for kind in ("work", "pr", "stack"):
            specs.append(f"+refs/heads/zzzops/{kind}/g{g}*:refs/remotes/{R}/zzzops/{kind}/g{g}*")
    for d in sorted(set(int(d) for d in deps)):
        specs.append(f"+refs/heads/zzzops/pr/g{d}*:refs/remotes/{R}/zzzops/pr/g{d}*")
    lines, locked, p = [], set(), None
    for attempt in range(1, 5):
        try:
            p = git.run("fetch", "-v", "--porcelain", "--no-tags", "--no-write-fetch-head", "--refmap=", R, *specs,
                        check=False, timeout=120)
        except GitError as exc:
            raise RemoteError(str(exc)) from exc
        lines = []
        for line in p.stdout.splitlines():
            if len(line) < 3 or line[1] != " ":
                continue
            parts = line[2:].split(" ")                    # "<flag> <old> <new> <local ref>"; flag may be a space
            if len(parts) >= 3:
                lines.append((line[0], parts[0], parts[1], parts[2]))
        locked = set(re.findall(r"cannot lock ref '([^']+)'", p.stderr))
        if locked and attempt < 4:
            time.sleep(random.uniform(0.05, 0.5))
            continue
        break
    prefix = f"refs/zzzops/goal/{R}/"
    rewritten = {ref for flag, _, _, ref in lines if flag == "!" and ref.startswith(prefix) and ref not in locked}
    if p.returncode != 0 and (not lines or locked or any(flag == "!" and ref not in rewritten for flag, _, _, ref in lines)):
        raise RemoteError(p.stderr.strip() or "git fetch failed")
    return build_snapshot(git, R, I, lines, rewritten, goals, deps)


def build_snapshot(git: Git, R: str, I: str, lines, rewritten, goals, deps) -> Snapshot:
    snap = Snapshot(R, I)
    gp = f"refs/zzzops/goal/{R}/"
    rp = f"refs/remotes/{R}/"
    seen_goals = set()
    for flag, old, new, ref in lines:
        if ref == f"{rp}{I}":
            snap.integration = new
        elif ref.startswith(gp):
            m = GOAL_REF.match(ref[len(gp):])
            if not m:
                continue
            g = int(m.group(1))
            seen_goals.add(g)
            if ref in rewritten:
                snap.goals[g] = old
                snap.rewritten[g] = new
            else:
                snap.goals[g] = new
        elif ref.startswith(rp + "zzzops/lease/"):
            rest = ref[len(rp + "zzzops/lease/"):]
            m = re.match(r"^g(\d+)/(.+)$", rest)
            if m:
                snap.leases[(int(m.group(1)), m.group(2))] = new
        elif ref.startswith(rp + "zzzops/policy/"):
            snap.policy[ref[len(rp + "zzzops/policy/"):]] = new
        else:
            for kind, table in (("work", snap.work), ("pr", snap.pr), ("stack", snap.stack)):
                pre = rp + f"zzzops/{kind}/"
                if ref.startswith(pre):
                    m = GOAL_REF.match(ref[len(pre):])
                    if m:
                        g = int(m.group(1))
                        if g in goals:
                            table[g] = new
                        if kind == "pr" and g in set(int(d) for d in deps):
                            snap.dep_pr[g] = new
    if snap.integration is None:
        raise Refused("not_found", f"integration branch `{I}` not found on `{R}`",
                      hint=f"push `{I}` to `{R}`, or set zzzops.integrationBranch")
    for g, tip in local_goal_refs(git, R).items():
        snap.known.add(g)
        if g not in seen_goals:
            snap.deleted.add(g)
            snap.goals[g] = tip
    snap.known |= set(snap.goals)
    return snap


def local_goal_refs(git: Git, R: str) -> dict:
    out = {}
    p = git.run("for-each-ref", "--format=%(refname) %(objectname)", f"refs/zzzops/goal/{R}/", check=False)
    for line in p.stdout.splitlines():
        ref, oid = line.split(" ")
        m = GOAL_REF.match(ref.rsplit("/", 1)[-1])
        if m:
            out[int(m.group(1))] = oid
    return out


def offline_snapshot(git: Git, R: str, I: str) -> Snapshot:
    snap = Snapshot(R, I, current=False)
    snap.integration = git.rev_parse(f"refs/remotes/{R}/{I}")
    if snap.integration is None:
        raise Refused("not_found", f"integration branch `{I}` is unknown locally and the remote is unreachable")
    snap.goals = local_goal_refs(git, R)
    snap.known = set(snap.goals)
    return snap


# --------------------------------------------------------------------------------------------- reading (§4.3)


@dataclass
class Commit:
    oid: str
    tree: str
    parents: list
    author: str
    author_date: int
    committer_date: int
    message: str

    def trailer(self, key: str) -> str | None:
        for line in reversed(self.message.splitlines()):
            if line.startswith(key + ": "):
                return line[len(key) + 2:].strip()
        return None


def parse_commit(oid: str, raw: bytes) -> Commit:
    head, _, msg = raw.partition(b"\n\n")
    tree, parents, author, adate, cdate = "", [], "", 0, 0
    for line in head.decode("utf-8", "replace").splitlines():
        if line.startswith("tree "):
            tree = line[5:]
        elif line.startswith("parent "):
            parents.append(line[7:])
        elif line.startswith("author "):
            m = re.match(r"author (.*) <[^>]*> (\d+) ", line)
            if m:
                author, adate = m.group(1), int(m.group(2))
        elif line.startswith("committer "):
            m = re.search(r" (\d+) [+-]\d{4}$", line)
            if m:
                cdate = int(m.group(1))
    return Commit(oid, tree, parents, author, adate, cdate, msg.decode("utf-8", "replace"))


@dataclass
class State:
    snap: Snapshot
    policy_raw: dict | None = None
    workflow_raw: dict | None = None
    policy: dict | None = None
    workflow: dict | None = None
    graphs: dict = field(default_factory=dict)
    settings: dict | None = None
    blockers: list = field(default_factory=list)        # [{"kind", "message"}]
    pause: bool = False                                 # a blocker pauses every action
    write_block: Refused | None = None                  # why writes are refused, if they are
    docs: dict = field(default_factory=dict)            # id -> valid document
    invalid: dict = field(default_factory=dict)         # id -> errors
    invalid_raw: dict = field(default_factory=dict)     # id -> the parsed JSON of an invalid goal (for edit)
    newer: set = field(default_factory=set)
    goal_commits: dict = field(default_factory=dict)    # id -> Commit of the accepted tip
    leases: dict = field(default_factory=dict)          # (id, node) -> Lease (parsed)
    unparsable: list = field(default_factory=list)      # (id, node) of leases that do not parse
    lease_commits: dict = field(default_factory=dict)
    policy_branches: list = field(default_factory=list)  # open (unlanded) policy branches
    landed: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    @property
    def coordinator(self) -> dict:
        c = {"commit": self.snap.integration, "current": self.snap.current}
        if self.policy_branches:
            c["policy_branches"] = [{"name": f"zzzops/policy/{b['topic']}", "date": b["date"], "author": b["author"]}
                                    for b in self.policy_branches]
        return c


def read_state(git: Git, snap: Snapshot, all_goals: bool = False, wanted=()) -> State:
    """`wanted`: goals the verb names, read whatever their state."""
    from engine.canon import iso
    st = State(snap)
    I = snap.integration

    def blob_json(spec):
        data = git.cat(spec)
        if data is None:
            return None, None
        try:
            return json.loads(data.decode("utf-8")), None
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            return None, f"{spec.split(':', 1)[1]}: not valid JSON ({exc})"

    # 1. policy and workflow
    st.policy_raw, perr = blob_json(f"{I}:.zzzops/POLICY.json")
    st.workflow_raw, werr = blob_json(f"{I}:.zzzops/workflow.json")
    if st.workflow_raw is None and werr is None:
        st.blockers.append({"kind": "not_bootstrapped", "message": f"this repository has no ZzzOps policy on `{snap.I}`; "
                                                                   "run the bootstrap skill"})
        st.pause = True
        st.write_block = Refused("not_bootstrapped", f"this repository has no ZzzOps policy on `{snap.I}`",
                                 hint="run the bootstrap skill")
    else:
        floor_check(st)
        if st.write_block is None:
            errors = [e for e in (perr, werr) if e]
            if not errors:
                errors = list(schemas.validate_policy(st.policy_raw))
            if not errors:
                errors = list(schemas.validate_workflow(st.workflow_raw, st.policy_raw,
                                                        lambda f: git.cat(f"{I}:.zzzops/prompts/{f}") is not None, OPS))
            if errors:
                msg = "the ZzzOps policy is invalid: " + "; ".join(errors[:5])
                st.blockers.append({"kind": "policy_invalid", "message": msg, "errors": errors})
                st.pause = True
                st.write_block = Refused("policy_invalid", msg, details={"errors": errors},
                                         hint="fix .zzzops/ through a zzzops/policy/* branch")
            else:
                st.policy, st.workflow = st.policy_raw, st.workflow_raw
                st.settings = st.policy["settings"]
                st.graphs = {n: schemas.build_graph(n, g) for n, g in st.workflow["graphs"].items()}
                want = st.settings["integration_branch"]
                if want != snap.I:
                    msg = (f"this clone is configured for `{snap.I}`; the policy says `{want}`: run "
                           f"`git config zzzops.integrationBranch {want}`")
                    st.blockers.append({"kind": "wrong_integration_branch", "message": msg})
                    st.pause = True
                    st.write_block = Refused("wrong_integration_branch", msg)
    # 2. tips
    commits = {}
    for g, tip in sorted(snap.goals.items()):
        raw = git.cat(tip)
        if raw is not None:
            commits[g] = parse_commit(tip, raw)
    st.goal_commits = commits
    for key, tip in sorted(snap.leases.items()):
        raw = git.cat(tip)
        if raw is None:
            continue
        c = parse_commit(tip, raw)
        st.lease_commits[key] = c
        fields = parse_message(c.message)
        if fields is None or fields["goal"] != key[0] or fields["node"] != key[1]:
            st.unparsable.append(key)
            continue
        st.leases[key] = to_lease(fields, tip, c.committer_date)
    for topic, tip in sorted(snap.policy.items()):
        raw = git.cat(tip)
        if raw is None:
            continue
        c = parse_commit(tip, raw)
        info = {"topic": topic, "tip": tip, "date": iso(c.author_date), "author": c.author}
        if policy_landed(git, tip, I):
            st.landed.append(info)
            st.warnings.append({"kind": "policy_branch_landed",
                                "message": f"zzzops/policy/{topic} has landed on `{snap.I}`: delete the branch"})
        else:
            st.policy_branches.append(info)
    # 3. and 4. goal documents
    named = {int(g) for g in wanted}
    wanted = [g for g, c in sorted(commits.items()) if all_goals or g in named or c.trailer("State") != "closed"]
    raw_docs = {}
    for g in wanted:
        raw_docs[g] = read_goal_json(git, snap.goals[g])
    needed = set()
    for g, (doc, _) in raw_docs.items():
        if isinstance(doc, dict):
            needed |= {d for d in doc.get("depends_on") or [] if isinstance(d, int)}
    for d in sorted(needed - set(raw_docs)):
        if d in snap.goals:
            raw_docs[d] = read_goal_json(git, snap.goals[d])
    for g, (doc, err) in sorted(raw_docs.items()):
        if err:
            st.invalid[g] = [err]
            continue
        if isinstance(doc, dict) and isinstance(doc.get("schema"), int) and doc["schema"] > max(GOAL_SCHEMAS):
            st.newer.add(g)
            continue
        st.docs[g] = doc
    if st.workflow is not None:
        # dependencies that exist but are newer or unreadable are placeholders: the dependent waits or is stuck
        known = {g: {} for g in set(snap.goals) | st.newer | set(st.invalid)}
        known.update(st.docs)
        for g in sorted(list(st.docs)):
            doc = st.docs[g]
            closed = doc.get("state") == "closed"
            errs, warns = schemas.validate_goal(doc, None, None if closed else known, st.workflow)
            if not errs and doc.get("id") != g:
                errs = [f"goal.id {doc.get('id')} does not match the branch g{g}"]
            if errs:
                st.invalid[g] = list(errs)
                st.invalid_raw[g] = st.docs.pop(g)
            st.warnings += warns
    for g, errs in sorted(st.invalid.items()):
        st.warnings.append({"kind": "invalid_goal", "message": f"G{g} is invalid: " + "; ".join(errs[:3])})
    for g, new in sorted(snap.rewritten.items()):
        st.warnings.append({"kind": "goal_rewritten",
                            "message": f"zzzops/goal/g{g} was force-pushed: accepted {snap.goals[g][:12]}, remote {new[:12]}; "
                                       "see REPAIR.md (forward commit)"})
    for g in sorted(snap.deleted):
        st.warnings.append({"kind": "goal_deleted", "message": f"zzzops/goal/g{g} was deleted on the remote; see REPAIR.md"})
    for key in st.unparsable:
        st.warnings.append({"kind": "orphan_lease", "message": f"lease zzzops/lease/g{key[0]}/{key[1]} does not parse"})
    if st.policy_branches and st.write_block is None:
        b = st.policy_branches[0]
        st.blockers.append({"kind": "policy_branch", "message":
                            f"A policy change is in progress on `zzzops/policy/{b['topic']}` (last commit {b['date']} by "
                            f"{b['author']}). New work is paused everywhere: {{n}} actions paused. To resolve it, land the "
                            f"branch on `{snap.I}` and delete it, or delete the branch to abandon the change. Running "
                            "phases may still submit."})
        st.pause = True
    return st


def read_goal_json(git: Git, tip: str):
    data = git.cat(f"{tip}:goal.json")
    if data is None:
        return None, "goal.json is missing"
    try:
        return json.loads(data.decode("utf-8")), None
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, f"goal.json is not valid JSON ({exc})"


def policy_landed(git: Git, tip: str, integration: str) -> bool:
    if git.is_ancestor(tip, integration):
        return True
    return git.run("diff", "--quiet", tip, integration, "--", ".zzzops/", check=False).returncode == 0


def floor_check(st: State):
    """SPEC §4.5: the floor first (tolerant), then the ceiling."""
    sv, mn = schemas.policy_floor(st.policy_raw)
    try:
        too_old = (sv is not None and sv > POLICY_SCHEMA) or (mn is not None and version_tuple(mn) > version_tuple(ENGINE_VERSION))
    except ValueError:
        too_old = False
    if too_old:
        msg = f"this engine ({ENGINE_VERSION}) is older than the policy requires (engine.min {mn}): upgrade the plugin"
        st.blockers.append({"kind": "engine_too_old", "message": msg})
        st.pause = True
        st.write_block = Refused("engine_too_old", msg, hint="upgrade the plugin")
        return
    try:
        too_new = mn is not None and version_tuple(mn) < version_tuple(REQUIRES_MIN)
    except ValueError:
        too_new = False
    if too_new:
        msg = f"waiting for policy to raise engine.min to `{REQUIRES_MIN}`"
        st.blockers.append({"kind": "engine_too_new", "message": msg})
        st.pause = True
        st.write_block = Refused("engine_too_new", msg)


# --------------------------------------------------------------------------------------------- mirror


def update_mirror(git: Git, integration: str):
    """Best effort (SPEC §4.3): a detached worktree of the coordinator commit for agents to browse."""
    lock_path = os.path.join(git.common, "zzzops", "coordinator.lock")
    path = os.path.join(git.common, "zzzops", "coordinator")
    try:
        os.makedirs(os.path.dirname(lock_path), exist_ok=True)
        fh = open(lock_path, "a+")
    except OSError:
        return
    try:
        if not _try_lock(fh):
            return
        if os.path.isdir(path):
            git.run("checkout", "--detach", "--force", "-q", integration, cwd=path, check=False)
        else:
            git.run("worktree", "add", "--detach", "-q", path, integration, check=False)
    except Exception:
        pass
    finally:
        try:
            _unlock(fh)
        finally:
            fh.close()


def _try_lock(fh) -> bool:
    try:
        import fcntl
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False
    except ImportError:
        import msvcrt
        try:
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False


def _unlock(fh):
    try:
        import fcntl
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    except ImportError:
        try:
            import msvcrt
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
    except OSError:
        pass


# --------------------------------------------------------------------------------------------- writes (§4.4)

ENGINE_REFS = ("refs/heads/zzzops/goal/", "refs/heads/zzzops/lease/", "refs/heads/zzzops/stack/")


def push_atomic(git: Git, R: str, updates) -> tuple:
    """('ok'|'rejected'|'remote', stderr). updates: [(ref, expected or None, new or None)]."""
    updates = [(ref, exp, new) for ref, exp, new in updates if (exp or None) != (new or None)]
    if not updates:
        return "ok", ""
    engine_only = all(ref.startswith(ENGINE_REFS) for ref, _, _ in updates)
    args = ["push", "--atomic", "--porcelain"]
    if engine_only:
        args.append("--no-verify")
    args.append(R)
    for ref, exp, _ in updates:
        args.append(f"--force-with-lease={ref}:{exp or ''}")
    for ref, _, new in updates:
        args.append(f"{new}:{ref}" if new else f":{ref}")
    try:
        p = git.run(*args, check=False, hooks=not engine_only, timeout=300)
    except GitError as exc:
        return "remote", str(exc)
    if p.returncode == 0:
        return "ok", p.stderr
    ref_lines = [l for l in p.stdout.splitlines() if "\t" in l and l[:1] in " +-*=!"]
    if any(l.startswith("!") for l in ref_lines):
        return "rejected", p.stderr
    return "remote", p.stderr


def goal_message(verb: str, g: int, outcome: str, state: str, node: str | None = None, attempt: int | None = None,
                 holder: str | None = None, note: str | None = None) -> str:
    head = f"zzzops: {verb} G{g}"
    if node:
        head += f" {node}"
    if attempt is not None:
        head += f" attempt {attempt}"
    if holder:
        head += f" by {holder}"
    body = f"{note.strip()}\n\n" if note else ""
    return f"{head}\n\n{body}Outcome: {outcome}\nState: {state}\nEngine: {ENGINE_VERSION}\n"


def goal_commit(git: Git, doc: dict, parent: str | None, message: str) -> str:
    blob = git.hash_object(goal_bytes(doc))
    tree = git.run("mktree", input=f"100644 blob {blob}\tgoal.json\n").stdout.strip()
    return git.commit_tree(tree, [parent] if parent else [], message)
