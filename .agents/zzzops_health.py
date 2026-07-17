#!/usr/bin/env python3
"""Pure, privacy-bounded health policy for ZzzOps."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

SCHEMA_VERSION = 1
PRECISIONS = {"exact_message", "observed_receipt", "current_only"}


def default_preferences() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "enabled": False,
        "timezone": "UTC",
        "signals": {"allow_exact_message": True, "allow_observed_receipt": False},
        "schedule": {
            "work_days": [0, 1, 2, 3, 4],
            "work_start": "09:00",
            "work_end": "18:00",
            "wind_down": "22:30",
            "bedtime": "23:30",
            "wake": "07:00",
            "quiet_start": "23:45",
            "quiet_end": "07:00",
        },
        "reminders": {
            "late_night": {"enabled": True},
            "weekend": {"enabled": True},
            "long_session": {"enabled": True, "after_minutes": 180},
            "break": {"enabled": True, "after_minutes": 90},
            "hydration": {"enabled": True, "after_minutes": 60},
        },
        "delivery": {
            "cooldown_minutes": 60,
            "snooze_minutes": 30,
            "inactivity_reset_minutes": 45,
            "tone": "gentle",
            "blocking": False,
        },
        "privacy": {"retention_hours": 48},
    }


def default_state() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "session_started_at": None,
        "last_activity_at": None,
        "activity_precision": None,
        "last_nudge_at": {},
        "snoozed_until": None,
        "paused_until": None,
        "nudge_count": {},
    }


def merged_preferences(value: dict[str, Any] | None) -> dict[str, Any]:
    merged = default_preferences()
    _deep_merge(merged, value or {})
    return merged


def merged_state(value: dict[str, Any] | None) -> dict[str, Any]:
    merged = default_state()
    _deep_merge(merged, value or {})
    return merged


def _deep_merge(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_merge(target[key], value)
        else:
            target[key] = deepcopy(value)


def validate_preferences(value: dict[str, Any]) -> list[str]:
    p = merged_preferences(value)
    errors: list[str] = []
    if p.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    _boolean(errors, p, "enabled")
    if not isinstance(p.get("timezone"), str) or not p["timezone"].strip():
        errors.append("timezone must be a non-empty IANA zone")
    signals = p.get("signals", {})
    for key in ("allow_exact_message", "allow_observed_receipt"):
        _boolean(errors, signals, f"signals.{key}", key)
    schedule = p.get("schedule", {})
    days = schedule.get("work_days")
    if not isinstance(days, list) or not days or len(set(days)) != len(days) or any(not isinstance(x, int) or isinstance(x, bool) or x < 0 or x > 6 for x in days):
        errors.append("schedule.work_days must be unique integers from 0 to 6")
    for key in ("work_start", "work_end", "wind_down", "bedtime", "wake", "quiet_start", "quiet_end"):
        if not _parse_clock(schedule.get(key)):
            errors.append(f"schedule.{key} must be HH:MM")
    reminders = p.get("reminders", {})
    for key in ("late_night", "weekend", "long_session", "break", "hydration"):
        group = reminders.get(key)
        if not isinstance(group, dict):
            errors.append(f"reminders.{key} must be an object")
            continue
        _boolean(errors, group, f"reminders.{key}.enabled", "enabled")
    for key in ("long_session", "break", "hydration"):
        _integer(errors, reminders.get(key, {}), f"reminders.{key}.after_minutes", "after_minutes", 1, 1440)
    delivery = p.get("delivery", {})
    for key, low, high in (
        ("cooldown_minutes", 1, 1440), ("snooze_minutes", 1, 1440),
        ("inactivity_reset_minutes", 1, 1440),
    ):
        _integer(errors, delivery, f"delivery.{key}", key, low, high)
    if delivery.get("tone") not in {"gentle", "direct", "humorous"}:
        errors.append("delivery.tone must be gentle, direct, or humorous")
    _boolean(errors, delivery, "delivery.blocking", "blocking")
    if delivery.get("blocking") is True:
        errors.append("delivery.blocking is unsupported; health nudges are nonblocking")
    _integer(errors, p.get("privacy", {}), "privacy.retention_hours", "retention_hours", 1, 720)
    return errors


def validate_state(value: dict[str, Any]) -> list[str]:
    state = merged_state(value)
    errors = []
    if state.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"state.schema_version must be {SCHEMA_VERSION}")
    for key in ("session_started_at", "last_activity_at", "snoozed_until", "paused_until"):
        if state.get(key) is not None and _parse_instant(state.get(key)) is None:
            errors.append(f"state.{key} must be an ISO-8601 instant or null")
    if state.get("activity_precision") not in PRECISIONS | {None}:
        errors.append("state.activity_precision is invalid")
    if not isinstance(state.get("last_nudge_at"), dict) or not isinstance(state.get("nudge_count"), dict):
        errors.append("state nudge fields must be objects")
    return errors


def evaluate(
    now: datetime,
    activity: dict[str, Any] | None,
    preferences: dict[str, Any],
    state: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return one explainable decision and minimal derived state."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    now = now.astimezone(timezone.utc)
    prefs = merged_preferences(preferences)
    current = merged_state(state)
    errors = validate_preferences(prefs) + validate_state(current)
    if errors:
        return _decision(False, "invalid_configuration", errors=errors), current
    current = _prune(current, now, prefs["privacy"]["retention_hours"])
    if not prefs["enabled"]:
        return _decision(False, "disabled"), current
    try:
        zone = ZoneInfo(prefs["timezone"])
    except ZoneInfoNotFoundError:
        return _decision(False, "timezone_unavailable", evidence={"timezone": prefs["timezone"]}), current
    precision = "current_only"
    if activity is not None:
        precision = activity.get("precision", "")
        stamp = _parse_instant(activity.get("timestamp"))
        if precision not in PRECISIONS or stamp is None:
            return _decision(False, "invalid_activity"), current
        if stamp > now + timedelta(minutes=5):
            return _decision(False, "future_activity"), current
        allowed = precision == "exact_message" and prefs["signals"]["allow_exact_message"]
        allowed = allowed or precision == "observed_receipt" and prefs["signals"]["allow_observed_receipt"]
        if allowed:
            current = _record_activity(current, stamp, precision, prefs)
    for gate in ("paused_until", "snoozed_until"):
        until = _parse_instant(current.get(gate))
        if until and now < until:
            return _decision(False, gate.removesuffix("_until"), evidence={"until": _iso(until)}), current
    last_any = _parse_instant(current["last_nudge_at"].get("any"))
    cooldown = timedelta(minutes=prefs["delivery"]["cooldown_minutes"])
    if last_any and now - last_any < cooldown:
        return _decision(False, "cooldown", evidence={"until": _iso(last_any + cooldown)}), current
    local = now.astimezone(zone)
    reason = _select_reason(local, now, prefs, current)
    if reason is None:
        return _decision(False, "not_due", evidence={"precision": precision}), current
    current["last_nudge_at"]["any"] = _iso(now)
    current["last_nudge_at"][reason] = _iso(now)
    current["nudge_count"][reason] = int(current["nudge_count"].get(reason, 0)) + 1
    evidence = {"local_time": local.isoformat(), "timezone": prefs["timezone"], "precision": precision}
    return _decision(True, reason, message=_message(reason, prefs["delivery"]["tone"]), evidence=evidence), current


def _record_activity(state: dict[str, Any], stamp: datetime, precision: str, prefs: dict[str, Any]) -> dict[str, Any]:
    last = _parse_instant(state.get("last_activity_at"))
    reset = timedelta(minutes=prefs["delivery"]["inactivity_reset_minutes"])
    if last is None or stamp - last >= reset or stamp < last:
        state["session_started_at"] = _iso(stamp)
    state["last_activity_at"] = _iso(stamp)
    state["activity_precision"] = precision
    return state


def _select_reason(local: datetime, now: datetime, prefs: dict[str, Any], state: dict[str, Any]) -> str | None:
    schedule, reminders = prefs["schedule"], prefs["reminders"]
    clock = local.timetz().replace(tzinfo=None)
    if reminders["late_night"]["enabled"] and _in_overnight(clock, _parse_clock(schedule["bedtime"]), _parse_clock(schedule["wake"])):
        return "late_night"
    if reminders["weekend"]["enabled"] and local.weekday() not in schedule["work_days"]:
        return "weekend"
    session = _parse_instant(state.get("session_started_at"))
    if session is None:
        return None
    elapsed = (now - session).total_seconds() / 60
    for reason in ("long_session", "break", "hydration"):
        rule = reminders[reason]
        if rule["enabled"] and elapsed >= rule["after_minutes"]:
            last = _parse_instant(state["last_nudge_at"].get(reason))
            if last is None or (now - last).total_seconds() / 60 >= rule["after_minutes"]:
                return reason
    return None


def _prune(state: dict[str, Any], now: datetime, retention_hours: int) -> dict[str, Any]:
    last = _parse_instant(state.get("last_activity_at"))
    if last and now - last > timedelta(hours=retention_hours):
        kept = {"paused_until": state.get("paused_until"), "snoozed_until": state.get("snoozed_until")}
        state = default_state()
        state.update(kept)
    cutoff = now - timedelta(hours=retention_hours)
    state["last_nudge_at"] = {
        key: value for key, value in state["last_nudge_at"].items()
        if (_parse_instant(value) or datetime.min.replace(tzinfo=timezone.utc)) >= cutoff
    }
    return state


def _decision(nudge: bool, reason: str, **extra: Any) -> dict[str, Any]:
    return {"nudge": nudge, "reason_code": reason, "blocking": False, **extra}


def _message(reason: str, tone: str) -> str:
    messages = {
        "late_night": "It is after your configured bedtime. Consider wrapping up and sleeping.",
        "weekend": "It is outside your configured work days. Consider leaving this for your next work day.",
        "long_session": "This has been a long session. Consider stopping for a proper break.",
        "break": "You have been active for a while. Consider taking a short break.",
        "hydration": "Consider taking a water break.",
    }
    prefixes = {"gentle": "", "direct": "Health check: ", "humorous": "ZzzOps bedtime enforcement: "}
    return prefixes[tone] + messages[reason]


def _parse_instant(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_clock(value: Any) -> time | None:
    if not isinstance(value, str) or len(value) != 5:
        return None
    try:
        parsed = time.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.second == 0 and parsed.microsecond == 0 else None


def _in_overnight(value: time, start: time, end: time) -> bool:
    return value >= start or value < end if start > end else start <= value < end


def _boolean(errors: list[str], group: dict[str, Any], label: str, key: str | None = None) -> None:
    if not isinstance(group, dict) or not isinstance(group.get(key or label), bool):
        errors.append(f"{label} must be boolean")


def _integer(errors: list[str], group: dict[str, Any], label: str, key: str, low: int, high: int) -> None:
    value = group.get(key) if isinstance(group, dict) else None
    if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
        errors.append(f"{label} must be an integer from {low} to {high}")
