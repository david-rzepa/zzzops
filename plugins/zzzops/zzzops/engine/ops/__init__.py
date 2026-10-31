"""Op registry (SPEC §5.1). Each op module provides `run(ctx)`; it is imported only when the op runs."""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field


@dataclass(frozen=True)
class OpSpec:
    name: str
    version: int
    gh: bool
    self_sync: bool
    module: str
    required_inputs: tuple = ()
    outputs: dict = field(default_factory=dict)
    workspace: bool = False
    policy: tuple = ()

    def validate(self, node: dict) -> list:
        """The op's check of the node's inputs and outputs (SPEC §3.1 rule 11)."""
        errors = []
        inputs = node.get("inputs") or {}
        for name in self.required_inputs:
            if name not in inputs:
                errors.append(f"input {name!r} is required")
        outs = node.get("outputs") or {}
        for name, t in self.outputs.items():
            if outs.get(name) != t:
                errors.append(f"output {name!r} of type {t!r} is required")
        if self.workspace and node.get("workspace") is not True:
            errors.append("workspace: true is required")
        for key in self.policy:
            if key not in (node.get("policy") or []):
                errors.append(f"policy must declare {key!r}")
        return errors

    def run(self, ctx):
        return importlib.import_module(self.module).run(ctx)


OPS = {
    "git.base": OpSpec("git.base", 1, gh=False, self_sync=True, module="engine.ops.base",
                       required_inputs=("heads", "merges"),
                       outputs={"branch": "string", "base_commit": "sha", "stack": "list",
                                "replay_map": "object", "replay_pos": "object"},
                       workspace=True),
    "checks.run": OpSpec("checks.run", 1, gh=False, self_sync=False, module="engine.ops.checks",
                         required_inputs=("code",), outputs={"result": "object"}, workspace=True,
                         policy=("verification.commands",)),
    "git.integrate": OpSpec("git.integrate", 1, gh=True, self_sync=True, module="engine.ops.integrate",
                            required_inputs=("code", "base"), outputs={"pr": "object", "ci": "object"},
                            workspace=True, policy=("verification.required_ci",)),
    "github.merge": OpSpec("github.merge", 1, gh=True, self_sync=False, module="engine.ops.merge",
                           required_inputs=("pr",), outputs={"merge_commit": "sha", "merged_at": "string"}),
}
