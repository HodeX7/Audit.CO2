"""Close flow orchestrator: plan, collect, calculate, check, gaps, summary."""

from __future__ import annotations

import asyncio
import dataclasses
from typing import TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from carbon_room import config, models
from carbon_room.agents import gaps
from carbon_room.models import Actor, Finding
from carbon_room.room import messages
from carbon_room.room.events import RoomEvent
from carbon_room.room.grammar import Intent
from carbon_room.room.ports import Context


class CloseState(TypedDict):
    close_id: str
    month: str
    site_ids: list[str]
    site_names: list[str]
    factor_set: str
    findings: list[dict]


COLLECTOR: Actor = Actor("agent", "collector", "Collector")


def _read_close_config() -> tuple[list[str], list[str], str]:
    try:
        sites = config.load_sites()
    except FileNotFoundError:
        raise ValueError("config/sites.yaml is missing") from None
    try:
        settings = config.load_config()
    except FileNotFoundError:
        raise ValueError("config/carbon_room.yaml is missing; P2 provides it") from None
    factor_set = settings.get("default_factor_set")
    if not factor_set:
        raise ValueError("config/carbon_room.yaml has no default_factor_set")
    site_ids = [entry["id"] for entry in sites["sites"]]
    site_names = [config.site(site_id).get("name") or site_id for site_id in site_ids]
    return site_ids, site_names, str(factor_set)


async def load_close_config() -> tuple[list[str], list[str], str]:
    """Return (site ids, site names, default factor set) from config."""
    return await asyncio.to_thread(_read_close_config)


def build_close_graph(ctx: Context) -> CompiledStateGraph:
    async def plan(state: CloseState) -> dict:
        m = messages.month_label(state["month"])
        await ctx.room.post(
            "carbon-room", messages.close_plan(m, state["close_id"], state["site_names"], state["factor_set"])
        )
        return {}

    async def collect(state: CloseState) -> dict:
        m = messages.month_label(state["month"])
        await ctx.room.send_targeted("carbon-room", "collector", messages.handoff_collect(m, state["site_names"]))
        report = await ctx.core.ingest(state["close_id"], COLLECTOR)
        await ctx.room.post("collector", messages.collector_statement(report))
        await ctx.on_phase_end(state["close_id"])
        return {}

    async def calculate(state: CloseState) -> dict:
        await ctx.core.calculate(state["close_id"])
        await ctx.on_phase_end(state["close_id"])
        return {}

    async def check(state: CloseState) -> dict:
        m = messages.month_label(state["month"])
        await ctx.room.send_targeted("carbon-room", "watchdog", messages.handoff_check(m))
        found = await ctx.core.check(state["close_id"])
        return {"findings": [dataclasses.asdict(f) for f in found]}

    async def post_gaps(state: CloseState) -> dict:
        found = [models.from_dict(Finding, d) for d in state["findings"]]
        await gaps.post_new_gaps(ctx, state["close_id"], found)
        return {}

    async def summary(state: CloseState) -> dict:
        m = messages.month_label(state["month"])
        s = await ctx.core.summary(state["close_id"])
        await ctx.room.post("carbon-room", messages.summary_post(m, s, ctx.display))
        await ctx.on_phase_end(state["close_id"])
        return {}

    graph = StateGraph(CloseState)
    order = [
        ("plan", plan), ("collect", collect), ("calculate", calculate),
        ("check", check), ("post_gaps", post_gaps), ("summary", summary),
    ]
    for name, fn in order:
        graph.add_node(name, fn)
    graph.add_edge(START, "plan")
    for (a, _), (b, _) in zip(order, order[1:]):
        graph.add_edge(a, b)
    graph.add_edge("summary", END)
    return graph.compile(checkpointer=MemorySaver())


async def handle_close_start(ctx: Context, event: RoomEvent, intent: Intent, actor: Actor) -> None:
    month = intent.args["month"]
    site_ids, site_names, factor_set = await load_close_config()
    close_id = await ctx.core.start_close(month, site_ids, factor_set, actor, event.message_id)
    ctx.room.begin_close(close_id)
    state: CloseState = {
        "close_id": close_id,
        "month": month,
        "site_ids": site_ids,
        "site_names": site_names,
        "factor_set": factor_set,
        "findings": [],
    }
    await build_close_graph(ctx).ainvoke(state, {"configurable": {"thread_id": close_id}})


async def resume(ctx: Context, close_id: str) -> None:
    raise NotImplementedError


async def handle_resume(ctx: Context, event: RoomEvent, intent: Intent, actor: Actor) -> None:
    raise NotImplementedError


async def resume_on_startup(ctx: Context) -> bool:
    raise NotImplementedError
