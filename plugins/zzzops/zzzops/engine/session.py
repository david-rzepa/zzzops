"""One invocation: the snapshot, the read state, the portfolio and the compare-and-swap write loop (SPEC §4.2–§4.4,
§4.19)."""

from __future__ import annotations

import copy
import os
import random
import re
import shlex
import sys
import time
from pathlib import Path

from engine import render
from engine.canon import iso, read_now
from engine.errors import Refused
from engine.frontier import orphan_leases, portfolio
from engine.gitrun import Git, require_environment
from engine import schemas
from engine.store import (RemoteError, State, coordinator_fetch, resolve_policy_ref, goal_commit, goal_message, offline_snapshot,
                          push_atomic, read_state, resolve_integration, resolve_remote, update_mirror)

WRITE_DEADLINE = 30.0


def cli_prefix() -> str:
    p = os.environ.get("ZZZOPS_PREFIX")
    if p:
        return p
    entry = Path(__file__).resolve().parent.parent / "zzzops.py"
    return f'"{sys.executable}" "{entry}"'


class GitReader(render.Reader):
    def __init__(self, session: "Session"):
        self.s = session

    def prompt(self, name: str):
        data = self.s.git.cat(f"{self.s.snap.policy_commit}:.zzzops/prompts/{name}")
        return data.decode("utf-8", "replace") if data is not None else None

    def diffstat(self, base, commit):
        p = self.s.git.run("diff", "--stat", "--no-color", base, commit, "--", ":/", ":(top,exclude).zzzops/reviews",
                           check=False)
        lines = [l for l in p.stdout.splitlines() if l.strip()]
        return lines[-1].strip() if p.returncode == 0 and lines else None

    def blob_view(self, text: str) -> dict:
        blob = self.s.git.hash_object(text.encode("utf-8"))
        return {"summary": render.first_line(text, 200), "blob": blob, "read": f"git cat-file -p {blob}"}

    def has(self, oid):
        return self.s.git.exists(oid)

    def human_decisions(self, g, graph, nodes):
        """Read once per goal tip per session (one `git log` plus one `git show` per answer), then filtered."""
        tip = self.s.snap.goals.get(g) if self.s.snap is not None else None
        if not tip:
            return []
        cache = self.s.__dict__.setdefault("_human_decisions", {})
        key = (g, tip)
        if key not in cache:
            cache[key] = render.human_decisions(self.s.git, tip, g, graph, list(graph.nodes))
        found = cache[key]
        wanted = set(nodes)
        return None if found is None else [e for e in found if e["node"] in wanted]

    def artifact_url(self, commit, path):
        web = self.s.web_base()
        return f"{web}/blob/{commit}/{path}" if web else None


class Session:
    def __init__(self, cwd=None, remote=None, integration=None, now=None, policy_ref=None, repo_flag=False):
        self.now = now if now is not None else read_now()
        self.git = Git.discover(cwd or os.getcwd(), self.now, flag=repo_flag)
        self.remote_arg, self.integration_arg = remote, integration
        self.policy_ref = policy_ref
        self.R = self.I = None
        self.snap = None
        self.state: State | None = None
        self._portfolio = None

    # ------------------------------------------------------------------ opening
    def check_environment(self):
        require_environment(self.git)

    def resolve(self):
        if self.R is None:
            self.R = resolve_remote(self.git, self.remote_arg)
            self.I = resolve_integration(self.git, self.R, self.integration_arg)

    def open(self, goals=(), deps=(), readonly=False, all_goals=False):
        self.resolve()
        try:
            self.snap = coordinator_fetch(self.git, self.R, self.I, goals, deps)
        except RemoteError as exc:
            if not readonly:
                raise Refused("remote", f"cannot reach `{self.R}`: {str(exc).splitlines()[0] if str(exc) else ''}",
                              hint="check the network and credentials, then retry") from exc
            self.snap = offline_snapshot(self.git, self.R, self.I)
        if self.policy_ref:
            self.snap.preview = resolve_policy_ref(self.git, self.snap, self.policy_ref)
        self.state = read_state(self.git, self.snap, all_goals=all_goals, wanted=goals)
        self._portfolio = None
        self._goals = list(goals)
        return self.state

    def refetch(self, goals=(), deps=(), all_goals=False):
        self.snap = coordinator_fetch(self.git, self.R, self.I, goals, deps)
        if self.policy_ref:
            self.snap.preview = resolve_policy_ref(self.git, self.snap, self.policy_ref)
        self.state = read_state(self.git, self.snap, all_goals=all_goals, wanted=goals)
        self._portfolio = None

    # ------------------------------------------------------------------ evaluation
    @property
    def settings(self):
        return self.state.settings

    def portfolio(self, docs=None, leases=None):
        st = self.state
        if docs is None and leases is None and self._portfolio is not None:
            return self._portfolio
        if st.settings is None:
            from engine.frontier import Portfolio
            return Portfolio({}, {}, dict(st.invalid), set(st.newer))
        p = portfolio(docs if docs is not None else st.docs, st.graphs, st.leases if leases is None else leases,
                      st.settings, self.now, st.invalid, st.newer)
        if docs is None and leases is None:
            self._portfolio = p
        return p

    def ctx(self, worker: bool = False) -> render.Ctx:
        """`worker`: output read by a phase's worker (cards, renew, abandon), whose commands carry --repo."""
        st = self.state
        settings = st.settings or {"parallelism": {"max_workers": 0}, "scheduling": {"order": "stage_first"},
                                   "releases": {"current": 1}}
        return render.Ctx(prefix=cli_prefix(), now=self.now, settings=settings, coordinator=st.coordinator,
                          reader=GitReader(self), goal_commits=dict(self.snap.goals),
                          goal_dates={g: c.committer_date for g, c in st.goal_commits.items()},
                          repo=self.git.primary if worker else None)

    def warnings(self, p) -> list:
        st = self.state
        out = list(st.warnings) + schemas.intent_warnings(st.settings)
        for (g, node) in orphan_leases(st.docs, st.graphs, st.leases):
            out.append({"kind": "orphan_lease", "message": f"lease zzzops/lease/g{g}/{node} is not valid for this goal "
                                                           "(see REPAIR.md to delete it)"})
        skew = [c for c in st.lease_commits.values() if c.committer_date > self.now + 300]
        if skew:
            newest = max(c.committer_date for c in skew)
            out.append({"kind": "clock_skew", "message": f"a lease tip is dated {iso(newest)}, after local now {iso(self.now)}"})
        if p.mass_expiry:
            newest = max((c.committer_date for c in st.lease_commits.values()), default=self.now)
            out.append({"kind": "mass_expiry", "message": "most leases expired at once; the likely cause is a machine that "
                                                          f"slept; local now {iso(self.now)}, newest committer date {iso(newest)}"})
        return out

    def render_next(self, scope=None, all_=False, legacy="cache") -> dict:
        """legacy: "check" in the `next` verb (a bounded legacy check may run), "cache" in the next embedded in a
        write (never checks)."""
        from engine import legacy as legacy_mod
        p = self.portfolio()
        warnings = self.warnings(p)
        paused = self.state.pause
        if not self.snap.current:
            # §4.2 offline_snapshot: leases are unknown, so lease-dependent states are unknown and nothing is offered
            paused = True
            warnings.append({"kind": "offline", "message": f"`{self.R}` is unreachable: showing the last fetch; leases "
                                                           "and policy branches are unknown, so no action is offered"})
        return render.render_next(self.ctx(), p, scope=scope, all_=all_, blockers=self.state.blockers,
                                  warnings=warnings, paused=paused, legacy=legacy_mod.status(self, legacy))

    def mirror(self):
        if self.snap is not None and self.snap.integration:
            update_mirror(self.git, self.snap.integration)

    def op_self_sync(self, nd: dict) -> bool:
        from engine.ops import OPS
        return nd.get("kind") == "op" and nd.get("op") in OPS and OPS[nd["op"]].self_sync

    def mirror_path(self) -> str:
        return os.path.join(self.git.common, "zzzops", "coordinator")

    def fetch_work_of(self, goal: int):
        """A missing artifact blob: fetch that goal's work branch once (SPEC §4.20)."""
        done = getattr(self, "_fetched_work", set())
        if goal in done:
            return
        done.add(goal)
        self._fetched_work = done
        self.git.run("fetch", "-q", "--no-tags", self.R,
                     f"+refs/heads/zzzops/work/g{goal}:refs/remotes/{self.R}/zzzops/work/g{goal}", check=False)

    def web_base(self) -> str | None:
        url = self.git.config(f"remote.{self.R}.url") or ""
        m = re.match(r"^(?:https://|git@|ssh://git@)(github\.com)[/:]([^/]+)/([^/]+?)(?:\.git)?$", url)
        return f"https://{m.group(1)}/{m.group(2)}/{m.group(3)}" if m else None

    # ------------------------------------------------------------------ writes (§4.4)
    def require_writable(self, goals=()):
        if self.policy_ref:
            raise Refused("usage", "--policy-ref is a read-only preview: it works with next, show and validate")
        st = self.state
        if st.write_block is not None:
            raise st.write_block
        for g in goals:
            if g in self.snap.rewritten:
                raise Refused("goal_rewritten", f"zzzops/goal/g{g} was force-pushed; writes are refused",
                              hint="see REPAIR.md: forward commit")
            if g in self.snap.deleted:
                raise Refused("goal_deleted", f"zzzops/goal/g{g} was deleted on the remote; writes are refused",
                              hint="see REPAIR.md")
            if g in st.newer:
                raise Refused("engine_too_old", f"G{g} has a newer goal schema than this engine", hint="upgrade the plugin")

    def write_goals(self, verb, ids, mutate, extra=None, retry=True, message=None, fetch_goals=None):
        """mutate(session, docs) -> {id: new doc}; extra(session, new) -> [(ref, expected, new)];
        message(g, old, new) -> commit message. Returns ("ok"|"applied", updates, closed ids)."""
        deadline = time.monotonic() + WRITE_DEADLINE
        delay = 0.25
        fetch_goals = list(fetch_goals if fetch_goals is not None else ids)
        while True:
            self.require_writable(ids)
            docs = copy.deepcopy(self.state.docs)
            new = mutate(self, docs)
            new, deletions, closed = self.apply_generic_close(docs, new)
            all_docs = dict(docs)
            all_docs.update(new)
            for g, d in new.items():
                errs, _ = schemas.validate_goal(d, self.state.docs.get(g), all_docs, self.state.workflow,
                                                lambda doc, g=g: self.terminals_current(g, doc, all_docs))
                errs = list(errs) + dependent_release_errors(g, d, all_docs)
                if errs:
                    raise Refused("too_large" if any("too_large" in e for e in errs) else "validation",
                                  f"G{g}: " + "; ".join(errs[:5]), details={"errors": list(errs)})
            updates = []
            for g, d in sorted(new.items()):
                if d != self.state.docs.get(g):
                    msg = message(g, self.state.docs.get(g), d) if message else goal_message(verb, g, "ok", d["state"])
                    c = goal_commit(self.git, d, self.snap.goals.get(g), msg)
                    updates.append((f"refs/heads/zzzops/goal/g{g}", self.snap.goals.get(g), c))
            seen = set()
            merged = []
            for u in updates + list(extra(self, new) if extra else []) + deletions:
                if u[0] not in seen:                       # a lease deleted by both the verb and the close
                    seen.add(u[0])
                    merged.append(u)
            updates = merged
            if not updates:
                return "noop", [], closed
            r, stderr = push_atomic(self.git, self.R, updates)
            if r == "ok":
                self.snap.advance(updates)
                for ref, _, nv in updates:
                    m = re.match(r"^refs/heads/zzzops/lease/g(\d+)/(.+)$", ref)
                    if m and not nv:
                        self.state.leases.pop((int(m.group(1)), m.group(2)), None)
                        self.state.lease_commits.pop((int(m.group(1)), m.group(2)), None)
                for g, d in new.items():
                    self.state.docs[g] = d
                self._portfolio = None
                self.housekeep(skip=set(new))
                return "ok", updates, closed
            if r == "remote":
                raise Refused("remote", f"push to `{self.R}` failed: {first_line(stderr)}")
            try:
                self.refetch(fetch_goals)
            except RemoteError as exc:
                raise Refused("remote", str(exc)) from exc
            if all(self.snap.ref_value(ref) == (nv or None) for ref, _, nv in updates):
                return "applied", updates, closed
            if all(self.snap.ref_value(ref) == (exp or None) for ref, exp, _ in updates):
                raise Refused("push_refused", "the remote refused the push (a branch rule or hook)",
                              details={"refs": [u[0] for u in updates],
                                       "remote": [l for l in stderr.splitlines() if l.startswith("remote:")]},
                              hint="exclude zzzops/** from branch rules (SETUP.md); retrying cannot help")
            if not retry:
                raise Refused("goal_changed", "the goal changed meanwhile: run show and redo the edit")
            if time.monotonic() > deadline:
                raise Refused("contention", "too many concurrent writes to this goal; retry shortly")
            time.sleep(random.uniform(0, delay))
            delay = min(2 * delay, 4)

    def housekeep(self, skip=()):
        """§4.4 worktree housekeeping: after a successful write, remove at most one local worktree of a closed goal
        whose branch tip is known to be on the remote and which is clean. Best effort; failures are ignored."""
        from engine import worktree as wt
        root = os.path.join(self.git.primary, ".zzzops", "worktrees")
        try:
            names = sorted(os.listdir(root))
        except OSError:
            return
        for name in names:
            m = re.match(r"^g(\d+)$", name)
            if not m or int(m.group(1)) in skip:
                continue
            g = int(m.group(1))
            c = self.state.goal_commits.get(g)
            if not c or c.trailer("State") != "closed":
                continue
            try:
                p = wt.worktree_path(self.git, g)
                local = wt.local_tip(self.git, g)
                known = self.snap.work.get(g) or self.git.rev_parse(f"refs/remotes/{self.R}/zzzops/work/g{g}")
                if local and local == known and wt.is_clean(self.git, p):
                    self.git.run("worktree", "remove", p)
                    self.git.run("branch", "-q", "-D", wt.branch(g), check=False)
            except Exception:
                pass
            return

    def terminals_current(self, g, doc, all_docs) -> bool:
        docs = dict(all_docs)
        docs[g] = dict(doc, state="open", closed=None)
        p = portfolio(docs, self.state.graphs, {}, self.state.settings, self.now, self.state.invalid, self.state.newer)
        res = p.goals.get(g)
        return bool(res) and all(res.st[t]["name"] == "current" for t in res.graph.terminal)

    def apply_generic_close(self, docs, new):
        """SPEC §4.19: close a goal whose terminal nodes are all current, in the same push."""
        deletions, closed = [], []
        all_docs = dict(docs)
        all_docs.update(new)
        for g, d in sorted(new.items()):
            if d["state"] != "closed" and self.terminals_current(g, d, all_docs):
                d["state"] = "closed"
                d["closed"] = {"reason": "done", "note": "every terminal node is current", "by": "zzzops", "at": iso(self.now)}
            if d["state"] == "closed" and (docs.get(g) or {}).get("state") != "closed":
                closed.append(g)
                for (lg, node), tip in sorted(self.snap.leases.items()):
                    if lg == g:
                        deletions.append((f"refs/heads/zzzops/lease/g{g}/{node}", tip, None))
                if self.snap.stack.get(g):
                    deletions.append((f"refs/heads/zzzops/stack/g{g}", self.snap.stack[g], None))
        return new, deletions, closed


def dependent_release_errors(g: int, d: dict, all_docs: dict) -> list:
    """SPEC §4.4: validation includes the dependents' release order."""
    out = []
    for x, xd in sorted(all_docs.items()):
        if x != g and isinstance(xd, dict) and g in (xd.get("depends_on") or []) and xd.get("state") != "closed":
            if isinstance(xd.get("release"), int) and isinstance(d.get("release"), int) and d["release"] > xd["release"]:
                out.append(f"goal.release: G{x} depends on G{g} but is in release {xd['release']}, before {d['release']}")
    return out


def first_line(text: str) -> str:
    for line in (text or "").splitlines():
        if line.strip():
            return line.strip()
    return ""
