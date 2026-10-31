"""Shared fixtures for the engine tests (IMPLEMENTATION_PLAN §1.2)."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_CODE = ROOT / "plugins" / "zzzops" / "zzzops"
TEMPLATES = PLUGIN_CODE / "templates" / "default"
if str(PLUGIN_CODE) not in sys.path:
    sys.path.insert(0, str(PLUGIN_CODE))

DEFAULT_NODES = ["design", "review_design", "approve_design", "base", "test_design", "review_tests", "implement",
                 "run_tests", "review_impl", "integrate", "approve_merge", "merge"]
RENAME = {n: f"n{i + 1:02d}_{chr(ord('a') + i)}" for i, n in enumerate(DEFAULT_NODES)}


def load_template(name: str) -> dict:
    return json.loads((TEMPLATES / name).read_text(encoding="utf-8"))


def prompt_exists(name: str) -> bool:
    return (TEMPLATES / "prompts" / name).is_file()


def renamed_workflow(wf: dict | None = None, mapping: dict | None = None) -> dict:
    """A copy of the workflow with every node id renamed, selectors and references included (DESIGN §10 item 3)."""
    wf = copy.deepcopy(wf or load_template("workflow.json"))
    mapping = mapping or RENAME

    def sel(text):
        parts = text.split(".")
        if parts[0] == "deps":
            parts[1] = mapping.get(parts[1], parts[1])
        elif parts[0] != "goal":
            parts[0] = mapping.get(parts[0], parts[0])
        return ".".join(parts)

    for g in wf["graphs"].values():
        g["terminal"] = [mapping.get(t, t) for t in g["terminal"]]
        nodes = {}
        for n, nd in g["nodes"].items():
            for spec in (nd.get("inputs") or {}).values():
                spec["from"] = sel(spec["from"])
            if "review" in nd:
                nd["review"]["subject"] = mapping.get(nd["review"]["subject"], nd["review"]["subject"])
            if "preserve" in nd:
                nd["preserve"] = mapping.get(nd["preserve"], nd["preserve"])
            nodes[mapping.get(n, n)] = nd
        g["nodes"] = nodes
    return wf


# --------------------------------------------------------------------------------------------- Git fixtures

import os
import shutil
import subprocess
import tempfile

GIT_ENV_KEYS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY", "GIT_CONFIG_GLOBAL",
                "GIT_CONFIG_NOSYSTEM", "GIT_ATTR_NOSYSTEM")


def isolated_env(home: str, extra: dict | None = None) -> dict:
    """An environment with an isolated HOME and global Git configuration."""
    env = {k: v for k, v in os.environ.items() if k not in GIT_ENV_KEYS and not k.startswith("ZZZOPS_")}
    gcfg = os.path.join(home, ".gitconfig")
    if not os.path.exists(gcfg):
        with open(gcfg, "w", encoding="utf-8") as fh:
            fh.write("[user]\n\tname = Test User\n\temail = test@example.com\n[init]\n\tdefaultBranch = dev\n"
                     "[advice]\n\tdetachedHead = false\n")
    env.update({"HOME": home, "GIT_CONFIG_GLOBAL": gcfg, "GIT_CONFIG_NOSYSTEM": "1", "LC_ALL": "C",
                "GIT_AUTHOR_DATE": "@1700000000 +0000", "GIT_COMMITTER_DATE": "@1700000000 +0000"})
    env.update(extra or {})
    return env


class GitDir:
    """A throwaway repository for identity tests."""

    def __init__(self, path: str, env: dict):
        self.path, self.env = path, env

    def git(self, *args, input=None, check=True) -> str:
        p = subprocess.run(["git", "-C", self.path, *args], input=input, capture_output=True, text=True, env=self.env)
        if check and p.returncode != 0:
            raise AssertionError(f"git {' '.join(args)}: {p.stderr}")
        return p.stdout.strip()

    def write(self, files: dict):
        for rel, content in files.items():
            full = os.path.join(self.path, rel)
            if content is None:
                if os.path.exists(full):
                    os.remove(full)
                continue
            os.makedirs(os.path.dirname(full) or self.path, exist_ok=True)
            mode = "wb" if isinstance(content, bytes) else "w"
            with open(full, mode) as fh:
                fh.write(content)

    def commit(self, files: dict, message: str) -> str:
        self.write(files)
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", message)
        return self.git("rev-parse", "HEAD")


def make_repo(tmp: str, name="repo", env=None) -> GitDir:
    path = os.path.join(tmp, name)
    os.makedirs(path)
    home = os.path.join(tmp, "home")
    os.makedirs(home, exist_ok=True)
    env = env or isolated_env(home)
    subprocess.run(["git", "init", "-q", "-b", "dev", path], check=True, env=env)
    return GitDir(path, env)


def engine_git(repo: GitDir, now=1700000000):
    """An engine Git runner on a fixture repository, with the fixture's environment."""
    from engine.gitrun import Git
    old = dict(os.environ)
    os.environ.clear()
    os.environ.update(repo.env)
    try:
        return Git.discover(repo.path, now)
    finally:
        os.environ.clear()
        os.environ.update(old)


class env_of:
    """Context manager: run engine code with a fixture repository's environment."""

    def __init__(self, env: dict):
        self.env = env

    def __enter__(self):
        self.old = dict(os.environ)
        os.environ.clear()
        os.environ.update(self.env)

    def __exit__(self, *exc):
        os.environ.clear()
        os.environ.update(self.old)


# --------------------------------------------------------------------------------------------- World: remote + clones

import json as _json
import sys as _sys

REMOTE_URL = "https://github.com/test/repo.git"
NOW = 1_800_000_000


class World:
    """A bare remote reached as https://github.com/test/repo.git (via url.insteadOf), and clones of it."""

    def __init__(self, tmp: str, clones=("a", "b"), now: int = NOW):
        self.tmp = tmp
        self.now = now
        self.home = os.path.join(tmp, "home")
        os.makedirs(self.home, exist_ok=True)
        self.remote = os.path.join(tmp, "remote.git")
        self.env = isolated_env(self.home)
        gcfg = self.env["GIT_CONFIG_GLOBAL"]
        with open(gcfg, "a", encoding="utf-8") as fh:
            fh.write(f'[url "{self.remote}"]\n\tinsteadOf = {REMOTE_URL}\n[zzzops]\n\tcommitter = ZzzOps Test <zzzops@test>\n')
        self.env.pop("GIT_AUTHOR_DATE", None)
        self.env.pop("GIT_COMMITTER_DATE", None)
        subprocess.run(["git", "init", "-q", "--bare", "-b", "dev", self.remote], check=True, env=self.env)
        seed = os.path.join(tmp, "seed")
        subprocess.run(["git", "clone", "-q", REMOTE_URL, seed], check=True, env=self.env, capture_output=True)
        self.seed = GitDir(seed, self.env)
        self.seed.commit({"README.md": "# test repo\n", "src/app.py": "def app():\n    return 1\n"}, "chore: initial")
        self.seed.git("push", "-q", "origin", "HEAD:dev")
        self.clones = {}
        for name in clones:
            self.add_clone(name)
        self.trace = os.path.join(tmp, "trace.jsonl")
        self.files = 0

    def add_clone(self, name):
        path = os.path.join(self.tmp, name)
        subprocess.run(["git", "clone", "-q", REMOTE_URL, path], check=True, env=self.env, capture_output=True)
        self.clones[name] = GitDir(path, self.env)
        return self.clones[name]

    def bootstrap(self, policy=None, workflow=None, prompts=True, settings=None, first_id=1000):
        policy = policy or load_template("POLICY.json")
        policy["settings"]["integration_branch"] = "dev"
        policy["settings"]["goals"]["first_id"] = first_id
        for k, v in (settings or {}).items():
            node = policy["settings"]
            *path, last = k.split(".")
            for p in path:
                node = node[p]
            node[last] = v
        workflow = workflow or load_template("workflow.json")
        files = {".zzzops/POLICY.json": _json.dumps(policy, indent=2) + "\n",
                 ".zzzops/workflow.json": _json.dumps(workflow, indent=2) + "\n"}
        if prompts:
            for p in sorted((TEMPLATES / "prompts").iterdir()):
                files[f".zzzops/prompts/{p.name}"] = p.read_text(encoding="utf-8")
        self.seed.git("pull", "-q", "--ff-only", "origin", "dev")
        self.seed.commit(files, "chore(zzzops): bootstrap")
        self.seed.git("push", "-q", "origin", "HEAD:dev")
        self.policy, self.workflow = policy, workflow

    def push_dev(self, files: dict, message="chore: dev moves"):
        self.seed.git("pull", "-q", "--ff-only", "origin", "dev")
        c = self.seed.commit(files, message)
        self.seed.git("push", "-q", "origin", "HEAD:dev")
        return c

    def file(self, content) -> str:
        self.files += 1
        path = os.path.join(self.tmp, "files", f"f{self.files}.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content if isinstance(content, str) else _json.dumps(content))
        return path

    def cli_env(self, now=None, extra=None):
        env = dict(self.env)
        env.update({"PYTHONPATH": str(PLUGIN_CODE), "ZZZOPS_NOW": str(now if now is not None else self.now),
                    "ZZZOPS_TRACE": self.trace, "ZZZOPS_PREFIX": "zzzops", "GH_REPO": "test/repo"})
        env.update(extra or {})
        return env

    def run(self, clone: str, *argv, now=None, env=None, cwd=None):
        p = subprocess.run([_sys.executable, "-m", "engine", *argv], cwd=cwd or self.clones[clone].path,
                           capture_output=True, text=True, env=self.cli_env(now, env))
        out = None
        if p.stdout.strip().startswith("{"):
            try:
                out = _json.loads(p.stdout)
            except _json.JSONDecodeError:
                out = None
        if out is None:
            out = {"_stdout": p.stdout, "_stderr": p.stderr}
        if p.returncode != 0 and "_stderr" not in out:
            out["_stderr"] = p.stderr
        return p.returncode, out

    def ok(self, clone, *argv, **kw):
        rc, out = self.run(clone, *argv, **kw)
        if rc != 0:
            raise AssertionError(f"{' '.join(argv)} -> {rc}: {_json.dumps(out, indent=1)[:3000]}")
        return out

    def new(self, clone="a", title="Goal", **fields):
        return self.ok(clone, "new", "--file", self.file(dict({"title": title, "spec": f"spec for {title}"}, **fields)))

    def trace_lines(self):
        if not os.path.exists(self.trace):
            return []
        with open(self.trace) as fh:
            return [_json.loads(l) for l in fh if l.strip()]

    def reset_trace(self):
        if os.path.exists(self.trace):
            os.remove(self.trace)

    def remote_git(self, *args, check=True):
        p = subprocess.run(["git", "--git-dir", self.remote, *args], capture_output=True, text=True, env=self.env)
        if check and p.returncode != 0:
            raise AssertionError(p.stderr)
        return p.stdout.strip()


def stub_ops_workflow(wf=None):
    """The default graph with `base` and `run_tests` replaced by agent nodes (steps 5 tests, before the ops exist)."""
    import copy as _copy
    wf = _copy.deepcopy(wf or load_template("workflow.json"))
    nodes = wf["graphs"]["default"]["nodes"]
    b = nodes["base"]
    nodes["base"] = {"description": "stub base", "kind": "agent", "capability": "routine", "prompt": "design.md",
                     "stage": "delivery", "inputs": b["inputs"],
                     "outputs": {"base_commit": "sha", "stack": "list", "branch": "string"}}
    r = nodes["run_tests"]
    nodes["run_tests"] = {"description": "stub checks", "kind": "agent", "capability": "routine", "prompt": "design.md",
                          "stage": "delivery", "inputs": r["inputs"], "policy": r["policy"], "outputs": {"result": "object"}}
    return wf


class Agent:
    """Plays an agent against the CLI: start, do the work, submit."""

    def __init__(self, world: World, clone: str, label: str):
        self.w, self.clone, self.label = world, clone, label

    def start(self, g, node, *extra, ok=True):
        rc, out = self.w.run(self.clone, "start", str(g), node, "--as", self.label, *extra)
        if ok and rc != 0:
            raise AssertionError(f"start {g} {node} -> {rc}: {_json.dumps(out, indent=1)[:2500]}")
        return out if ok else (rc, out)

    def submit(self, g, node, card, output=None, artifact=None, blocked=None, ok=True):
        argv = ["submit", str(g), node, "--attempt", str(card["lease"]["attempt"]), "--as", self.label]
        if blocked is not None:
            argv += ["--blocked", self.w.file(blocked)]
        else:
            argv += ["--output", self.w.file(output or {})]
        if artifact is not None:
            path = os.path.join(self.w.tmp, "files", f"a{self.w.files}.md")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(artifact)
            argv += ["--artifact", path]
        rc, out = self.w.run(self.clone, *argv)
        if ok and rc != 0:
            raise AssertionError(f"submit {g} {node} -> {rc}: {_json.dumps(out, indent=1)[:2500]}")
        return out if ok else (rc, out)

    def worktree(self, g):
        return GitDir(os.path.join(self.w.clones[self.clone].path, ".zzzops", "worktrees", f"g{g}"), self.w.env)


def stub_base_workflow(wf=None):
    """The default graph with only `base` replaced by an agent node (step 6 tests)."""
    import copy as _copy
    wf = _copy.deepcopy(wf or load_template("workflow.json"))
    nodes = wf["graphs"]["default"]["nodes"]
    b = nodes["base"]
    nodes["base"] = {"description": "stub base", "kind": "agent", "capability": "routine", "prompt": "design.md",
                     "stage": "delivery", "inputs": b["inputs"],
                     "outputs": {"base_commit": "sha", "stack": "list", "branch": "string"}}
    return wf
