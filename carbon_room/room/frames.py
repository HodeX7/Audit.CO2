"""Classify raw Switch frames whatever their envelope."""

from __future__ import annotations

import json

DOMAIN_KINDS: frozenset[str] = frozenset({"message", "command", "room_join"})
CONTROL_KINDS: frozenset[str] = frozenset(
    {"connection_state", "gap", "evicted", "subscription_changed", "room_released", "ping", "refused"}
)


def frame_kind(frame: object) -> str | None:
    if not isinstance(frame, dict):
        return None
    data = frame.get("data")
    if isinstance(data, dict) and data.get("type") in DOMAIN_KINDS:
        return data["type"]
    for key in ("event", "type"):
        value = frame.get(key)
        if isinstance(value, str) and value in DOMAIN_KINDS | CONTROL_KINDS:
            return value
    if isinstance(data, dict) and data.get("type") in CONTROL_KINDS:
        return data["type"]
    return None


def frame_fields(frame: object) -> dict:
    if not isinstance(frame, dict):
        return {}
    data = frame.get("data")
    if isinstance(data, dict):
        return data
    return {k: v for k, v in frame.items() if k not in ("event", "type") and not str(k).startswith("_")}


def _as_sequence(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str) and value.isascii() and value.isdigit():
        return int(value)
    return None


def sequence_of(frame: object) -> int | None:
    if not isinstance(frame, dict):
        return None
    found = _as_sequence(frame.get("id"))
    if found is not None:
        return found
    data = frame.get("data")
    if isinstance(data, dict):
        return _as_sequence(data.get("sequence"))
    return None


def pong(cursor: int) -> str:
    return json.dumps({"type": "pong", "cursor": cursor})
