"""Lease commits (SPEC §3.8) and the lease verbs (§4.12)."""

from __future__ import annotations

import json
import secrets

from engine.frontier import Lease
from engine.schemas import HOLDER, START_REASONS

FIELDS = ("Goal", "Node", "Attempt", "Holder", "Reason", "Timeout", "Work", "Input-Fp", "Fp-Parts", "Prompt", "Nonce")
SUBJECTS = {"lease": "zzzops lease", "renew": "zzzops renew", "abandon": "zzzops abandon"}


def lease_ref(goal: int, node: str) -> str:
    return f"refs/heads/zzzops/lease/g{goal}/{node}"


def parse_message(message: str) -> dict | None:
    """The trailer fields of a lease message, or None when it does not parse (unknown fields are ignored)."""
    lines = message.splitlines()
    if not lines or not any(lines[0].startswith(s + " ") for s in SUBJECTS.values()):
        return None
    fields = {}
    for line in lines[1:]:
        if ": " in line:
            k, v = line.split(": ", 1)
            fields.setdefault(k.strip(), v.strip())
    if any(f not in fields for f in FIELDS):
        return None
    try:
        out = {"goal": int(fields["Goal"]), "node": fields["Node"], "attempt": int(fields["Attempt"]),
               "holder": fields["Holder"], "reason": fields["Reason"], "timeout": int(fields["Timeout"]),
               "work": None if fields["Work"] == "-" else fields["Work"], "input_fp": fields["Input-Fp"],
               "fp_parts": json.loads(fields["Fp-Parts"]), "prompt": None if fields["Prompt"] == "-" else fields["Prompt"],
               "nonce": fields["Nonce"], "body": "\n".join(lines[1:]).strip("\n")}
    except (ValueError, json.JSONDecodeError):
        return None
    if (out["attempt"] < 1 or out["timeout"] < 0 or not HOLDER.match(out["holder"]) or out["reason"] not in START_REASONS
            or not isinstance(out["fp_parts"], dict)):
        return None
    return out


def to_lease(fields: dict, tip: str, last_active: int, claimed_at: int | None = None) -> Lease:
    return Lease(fields["goal"], fields["node"], fields["attempt"], fields["holder"], fields["reason"], fields["timeout"],
                 last_active, work=fields["work"], input_fp=fields["input_fp"], fp_parts=fields["fp_parts"],
                 prompt=fields["prompt"], tip=tip, claimed_at=claimed_at)


def message(kind: str, goal: int, node: str, attempt: int, holder: str, reason: str, timeout: int, work: str | None,
            input_fp: str, fp_parts: dict, prompt: str | None, nonce: str | None = None) -> str:
    from engine.canon import canonical
    body = [f"Goal: {goal}", f"Node: {node}", f"Attempt: {attempt}", f"Holder: {holder}", f"Reason: {reason}",
            f"Timeout: {timeout}", f"Work: {work or '-'}", f"Input-Fp: {input_fp}",
            f"Fp-Parts: {canonical(fp_parts).decode('utf-8')}", f"Prompt: {prompt or '-'}",
            f"Nonce: {nonce or secrets.token_hex(8)}"]
    return f"{SUBJECTS[kind]} G{goal} {node}\n\n" + "\n".join(body) + "\n"
