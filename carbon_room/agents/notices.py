"""Budget warn and stop notices."""

from __future__ import annotations

import asyncio
from decimal import Decimal

from carbon_room import config
from carbon_room.room import messages
from carbon_room.room.ports import Context

DEFAULT_WARN_AT = 0.8


def _read_warn_at() -> float:
    try:
        settings = config.load_config()
    except FileNotFoundError:
        return DEFAULT_WARN_AT
    return (settings.get("budgets") or {}).get("warn_at", DEFAULT_WARN_AT)


async def warn_label() -> str:
    """Return the warn threshold as a percentage, e.g. "80%"."""
    value = await asyncio.to_thread(_read_warn_at)
    return messages.pct(Decimal(str(value)) * 100)


async def check_budgets(ctx: Context, close_id: str) -> list[str]:
    """Post one warn and one stop notice per agent per close; return the texts posted."""
    usage = await ctx.core.budget_usage(close_id)
    sent = ctx.state.setdefault("budget_notices", set())
    posted: list[str] = []
    for agent in sorted(usage):
        state = usage[agent]["state"]
        if state not in ("warn", "stopped"):
            continue
        key = (close_id, agent, state)
        if key in sent:
            continue
        if state == "warn":
            text = messages.budget_warn(agent, await warn_label())
        else:
            text = messages.budget_stopped(agent)
        await ctx.room.post("carbon-room", text, essential=False)
        sent.add(key)
        posted.append(text)
    return posted
