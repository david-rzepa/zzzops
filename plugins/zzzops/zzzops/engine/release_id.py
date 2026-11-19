"""Canonical, numerically ordered identities for target release labels."""

from __future__ import annotations

import re

_LABEL = re.compile(r"[0-9]+(?:\.[0-9]+)*\Z")


def components(value: object) -> tuple[int, ...]:
    """Parse an integer or dotted label, removing only redundant trailing zeros."""
    if isinstance(value, bool):
        raise ValueError("release must be a positive integer or dotted numeric label")
    if isinstance(value, int):
        if value < 1:
            raise ValueError("release must begin with a positive component")
        return (value,)
    if not isinstance(value, str) or not _LABEL.fullmatch(value):
        raise ValueError("release must be a positive integer or dotted numeric label")
    try:
        parts = [int(part) for part in value.split(".")]
    except ValueError as exc:
        raise ValueError("release component is too large") from exc
    if parts[0] < 1:
        raise ValueError("release must begin with a positive component")
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    return tuple(parts)


def canonical(value: object) -> int | str:
    """Keep integer targets as integers and dotted identities as canonical strings."""
    parts = components(value)
    return parts[0] if len(parts) == 1 else ".".join(map(str, parts))


def label(value: object) -> str:
    return str(canonical(value))


def equal(left: object, right: object) -> bool:
    try:
        return components(left) == components(right)
    except ValueError:
        return False
