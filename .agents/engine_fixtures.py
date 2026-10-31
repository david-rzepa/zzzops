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
