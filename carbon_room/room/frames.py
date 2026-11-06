"""Classify raw Switch frames whatever their envelope."""

from __future__ import annotations

DOMAIN_KINDS: frozenset[str] = frozenset({"message", "command", "room_join"})
CONTROL_KINDS: frozenset[str] = frozenset(
    {"connection_state", "gap", "evicted", "subscription_changed", "room_released", "ping", "refused"}
)


def frame_kind(frame: object) -> str | None:
    raise NotImplementedError


def frame_fields(frame: object) -> dict:
    raise NotImplementedError


def sequence_of(frame: object) -> int | None:
    raise NotImplementedError


def pong(cursor: int) -> str:
    raise NotImplementedError
