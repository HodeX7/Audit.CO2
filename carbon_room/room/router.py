"""Match a gap-thread reply to one of the gap's options. Pure."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from carbon_room.models import Gap, Option
from carbon_room.room.grammar import normalize_reply


@dataclass(frozen=True)
class GapAction:
    gap: Gap
    option: Option
    payload: dict
    filename: str | None


@dataclass(frozen=True)
class NoMatch:
    gap: Gap
    reason: Literal["unknown_reply", "gap_resolved", "no_options"]


def match_reply(gap: Gap, text: str, has_attachment: bool) -> GapAction | NoMatch:
    if gap.status == "RESOLVED":
        return NoMatch(gap, "gap_resolved")
    if not gap.options:
        return NoMatch(gap, "no_options")
    if has_attachment:
        for option in gap.options:
            if option.action == "upload":
                return GapAction(gap, option, dict(option.params), None)
    key, rest = normalize_reply(text)
    for option in gap.options:
        if key != normalize_reply(option.key)[0]:
            continue
        payload = dict(option.params)
        if option.action == "reject" and rest:
            payload["reason"] = rest
        filename = (rest or None) if option.action == "upload" else None
        return GapAction(gap, option, payload, filename)
    return NoMatch(gap, "unknown_reply")


def find_gap(gaps: list[Gap], gap_id: str) -> Gap | None:
    wanted = gap_id.lower()
    for gap in gaps:
        if gap.gap_id.lower() == wanted:
            return gap
    return None
