"""Match a gap-thread reply to one of the gap's options. Pure."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from carbon_room.models import Gap, Option


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
    raise NotImplementedError


def find_gap(gaps: list[Gap], gap_id: str) -> Gap | None:
    raise NotImplementedError
