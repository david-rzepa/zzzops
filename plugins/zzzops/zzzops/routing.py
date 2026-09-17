"""Policy-driven model-plus-effort routing decisions.

The module is deliberately provider-neutral. The coordinator supplies the
runtime model inventory and remains responsible for the actual delegation-tool
call; this module only validates and explains the decision.
"""

from __future__ import annotations

import json
from typing import Any


PHASES = ("discovery", "architecture", "implementation", "verification")
REQUIRED_FIELDS = {"model", "effort", "capability", "cost"}
DELEGATION_TERMS = ("delegat", "subagent", "sub-agent", "worker", "agent")


class RoutingError(ValueError):
    """The available inventory or requested launch does not satisfy policy."""


def discover_delegation_capability(tool_catalog: Any) -> dict[str, Any]:
    """Inspect the complete host tool catalog, including deferred tools."""
    if not isinstance(tool_catalog, list):
        return {"state": "unavailable", "matches": [], "evidence": "tool catalog unavailable"}
    matches = []
    for item in tool_catalog:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", ""))
        description = str(item.get("description", ""))
        haystack = f"{name} {description}".casefold()
        if any(term in haystack for term in DELEGATION_TERMS):
            matches.append(name or "<unnamed>")
    state = "available" if matches else "unavailable"
    return {"state": state, "matches": sorted(set(matches)), "evidence": "complete runtime tool catalog"}


def _pair(item: dict[str, Any]) -> tuple[str, str]:
    return str(item["model"]), str(item["effort"])


def _validate_inventory(inventory: Any) -> list[dict[str, Any]]:
    if not isinstance(inventory, list) or not inventory:
        raise RoutingError("model inventory is unavailable")
    normalized = []
    for index, item in enumerate(inventory):
        if not isinstance(item, dict) or not REQUIRED_FIELDS <= set(item):
            raise RoutingError(f"model inventory entry {index} is incomplete")
        if not isinstance(item["model"], str) or not item["model"]:
            raise RoutingError(f"model inventory entry {index} has an invalid model")
        if not isinstance(item["effort"], str) or not item["effort"]:
            raise RoutingError(f"model inventory entry {index} has an invalid effort")
        if not isinstance(item["capability"], int) or isinstance(item["capability"], bool) or item["capability"] < 0:
            raise RoutingError(f"model inventory entry {index} has an invalid capability")
        if not isinstance(item["cost"], int) or isinstance(item["cost"], bool) or item["cost"] < 0:
            raise RoutingError(f"model inventory entry {index} has an invalid cost")
        normalized.append(dict(item))
    return normalized


def route_phase(
    *,
    phase: str,
    required_capability: int,
    inventory: Any,
    root_pair: dict[str, Any],
    session_override: bool = False,
) -> dict[str, Any]:
    """Select the least-cost valid model-plus-effort pair for one phase."""
    if phase not in PHASES:
        raise RoutingError(f"unsupported routing phase: {phase}")
    if not isinstance(required_capability, int) or isinstance(required_capability, bool) or required_capability < 0:
        raise RoutingError("required capability must be a non-negative integer")
    root_items = _validate_inventory([root_pair])
    root = root_items[0]
    items = _validate_inventory(inventory)
    if _pair(root) not in {_pair(item) for item in items}:
        items.append(root)
    if required_capability > root["capability"] and not session_override:
        raise RoutingError("above-root capability requires a current-session override")
    if required_capability >= root["capability"]:
        if required_capability > root["capability"]:
            candidates = [item for item in items if item["capability"] >= required_capability and _pair(item) != _pair(root)]
            if not candidates:
                raise RoutingError("no available model-plus-effort pair satisfies the capability floor")
            selected = min(candidates, key=lambda item: (item["cost"], item["capability"], item["model"], item["effort"]))
            return {
                "phase": phase, "mode": "delegated_override",
                "selected": {"model": selected["model"], "effort": selected["effort"]},
                "required_capability": required_capability, "root_capability": root["capability"],
                "session_override": session_override,
            }
        return {
            "phase": phase,
            "mode": "direct_root" if required_capability == root["capability"] else "delegated_override",
            "selected": {"model": root["model"], "effort": root["effort"]} if required_capability == root["capability"] else None,
            "required_capability": required_capability,
            "root_capability": root["capability"],
            "session_override": session_override,
        }
    candidates = [item for item in items if item["capability"] >= required_capability and _pair(item) != _pair(root)]
    if not candidates:
        raise RoutingError("no delegated model-plus-effort pair satisfies the capability floor")
    selected = min(candidates, key=lambda item: (item["cost"], item["capability"], item["model"], item["effort"]))
    return {
        "phase": phase,
        "mode": "delegated",
        "selected": {"model": selected["model"], "effort": selected["effort"]},
        "required_capability": required_capability,
        "root_capability": root["capability"],
        "session_override": session_override,
    }


def prepare_phase_assignment(
    *,
    phase: str,
    required_capability: int,
    inventory: Any,
    root_pair: dict[str, Any],
    tool_catalog: Any,
    session_override: bool = False,
) -> dict[str, Any]:
    """Return an executable assignment or explicit harness blocker.

    Routing is deliberately separate from launching.  A coordinator must first
    inspect the complete tool catalog, then may ask the existing harness to
    launch the returned worker assignment.  This prevents an unavailable
    delegation tool from silently changing eligible work into root work.
    """
    plan = route_phase(
        phase=phase,
        required_capability=required_capability,
        inventory=inventory,
        root_pair=root_pair,
        session_override=session_override,
    )
    if plan["mode"] == "direct_root":
        return {
            "status": "ready",
            "assignment": plan,
            "delegation": None,
            "next_step": {
                "action": "continue_root",
                "instruction": f"Perform the {phase} phase on the root agent.",
            },
        }

    delegation = discover_delegation_capability(tool_catalog)
    if delegation["state"] != "available":
        return {
            "status": "blocked",
            "assignment": plan,
            "delegation": delegation,
            "blocker": {
                "category": "technical-unknown",
                "reason": "delegation_harness_unavailable",
                "next_action": "Run this phase in a harness that exposes delegation, then retry this assignment.",
            },
            "next_step": {
                "action": "resolve_blocker",
                "instruction": "Delegation is required for this phase, but this harness cannot delegate. Resolve the harness blocker, then retry.",
            },
        }
    selected = plan["selected"]
    return {
        "status": "ready",
        "assignment": plan,
        "delegation": delegation,
        "next_step": {
            "action": "delegate",
            "instruction": (
                f"Delegate the {phase} phase using model {selected['model']} "
                f"with effort {selected['effort']}."
            ),
        },
    }


def validate_launch_plan(
    plan: Any, *, root_pair: dict[str, Any], session_override: bool = False, max_workers: int = 3,
) -> dict[str, Any]:
    """Validate parameters before invoking the existing delegation harness."""
    if not isinstance(plan, dict) or set(plan) != {"phase", "mode", "selected", "required_capability", "root_capability", "session_override", "fork_turns", "parallelism"}:
        raise RoutingError("launch plan has an invalid shape")
    root = _validate_inventory([root_pair])[0]
    selected = plan["selected"]
    if plan["mode"] == "direct_root":
        if selected is not None or plan["fork_turns"] is not None:
            raise RoutingError("direct root execution must not carry a delegated launch")
        return {"valid": True, "mode": "direct_root", "phase": plan["phase"]}
    if not isinstance(selected, dict) or set(selected) != {"model", "effort"}:
        raise RoutingError("delegated launch must identify a model-plus-effort pair")
    if selected == {"model": root["model"], "effort": root["effort"]}:
        raise RoutingError("root-equivalent work must run directly on the root agent")
    if plan["required_capability"] >= root["capability"] and not session_override:
        raise RoutingError("root-level or above-root delegation requires a current-session override")
    if plan["parallelism"] > max_workers:
        raise RoutingError("delegated parallelism exceeds the reviewed worker limit")
    if not isinstance(plan["fork_turns"], str) or not plan["fork_turns"]:
        raise RoutingError("delegated launches require an explicit fork scope")
    return {"valid": True, "mode": "delegated", "phase": plan["phase"], "selected": selected}


def routing_event(plan: dict[str, Any], *, outcome: str, telemetry: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create compact append-only evidence without retaining prompts or source."""
    event = {
        "phase": plan.get("phase"), "mode": plan.get("mode"), "selected": plan.get("selected"),
        "required_capability": plan.get("required_capability"), "root_capability": plan.get("root_capability"),
        "session_override": bool(plan.get("session_override")), "outcome": outcome,
        "telemetry": telemetry if isinstance(telemetry, dict) else {"status": "unavailable"},
    }
    json.dumps(event, ensure_ascii=False, sort_keys=True)
    return event
