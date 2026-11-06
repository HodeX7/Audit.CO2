"""Close flow orchestrator."""

from __future__ import annotations

from typing import TypedDict

from langgraph.graph.state import CompiledStateGraph

from carbon_room.models import Actor
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


async def load_close_config() -> tuple[list[str], list[str], str]:
    raise NotImplementedError


def build_close_graph(ctx: Context) -> CompiledStateGraph:
    raise NotImplementedError


async def handle_close_start(ctx: Context, event: RoomEvent, intent: Intent, actor: Actor) -> None:
    raise NotImplementedError
