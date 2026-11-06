from __future__ import annotations

from carbon_room.agents import Collector
from carbon_room import core
from carbon_room.models import Actor


def test_collector_delegates_only_to_p1_ingestion_boundaries(monkeypatch):
    actor = Actor("system", "collector", "Collector")
    collector = Collector()
    monkeypatch.setattr(core, "ingest", lambda close_id, received_actor: (close_id, received_actor.id))
    monkeypatch.setattr(core, "ingest_file", lambda *args: ["CL-0001"])
    assert collector.name == "collector"
    assert collector.ingest("close", actor) == ("close", "collector")
    assert collector.ingest_file("close", "bill.pdf", actor, "message") == ["CL-0001"]
