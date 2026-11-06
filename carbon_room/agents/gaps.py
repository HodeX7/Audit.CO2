"""Gap root posts for the close flow."""

from __future__ import annotations

import logging

from carbon_room.models import Finding
from carbon_room.room import messages
from carbon_room.room.ports import Context

log = logging.getLogger(__name__)

_MALFORMED = 10**9


def gap_number(gap_id: str) -> int:
    """Return the numeric part of a gap id; a malformed id sorts last."""
    try:
        return int(gap_id.split("-", 1)[1])
    except (IndexError, ValueError):
        return _MALFORMED


async def post_new_gaps(ctx: Context, close_id: str, findings: list[Finding]) -> list[str]:
    """Post one root per gap that has none yet, and record it in core."""
    _, open_gaps = await ctx.core.resume_state(close_id)
    by_id = {f.finding_id: f for f in findings}
    posted: list[str] = []
    for gap in sorted(open_gaps, key=lambda g: gap_number(g.gap_id)):
        if gap.thread_root_message_id is not None:
            continue
        text = messages.gap_root(
            gap, by_id.get(gap.finding_id), ctx.display(gap.owner), fallback_hint=not ctx.threads
        )
        mid = await ctx.room.post("watchdog", text)
        if not mid:
            log.warning("gap %s root not posted", gap.gap_id)
            continue
        try:
            await ctx.core.record_gap_thread(close_id, gap.gap_id, mid)
        except ValueError:
            log.error("gap %s root %s could not be recorded", gap.gap_id, mid, exc_info=True)
            continue
        posted.append(gap.gap_id)
    return posted
