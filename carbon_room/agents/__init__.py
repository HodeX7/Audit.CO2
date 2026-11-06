"""P1-owned agent entry points.

All P1 agents live in this one module. The collector is deliberately limited to
evidence ingestion; it cannot verify, approve, resolve, or publish a close.
"""

from __future__ import annotations

from pathlib import Path

from carbon_room import core
from carbon_room.models import Actor, IngestReport


class Collector:
    """Thin collector boundary for a room router or scheduled collection run."""

    name = "collector"

    def ingest(self, close_id: str, actor: Actor) -> IngestReport:
        """Collect the close's configured seed and baseline evidence."""
        return core.ingest(close_id, actor)

    def ingest_file(self, close_id: str, path: str | Path, actor: Actor, chat_message_id: str,
                    site: str | None = None) -> list[str]:
        """Record a human-uploaded attachment with its originating Switch message."""
        return core.ingest_file(close_id, path, actor, chat_message_id, site)


__all__ = ["Collector"]
