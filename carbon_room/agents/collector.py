"""The P1 collector agent: evidence in, unverified ledger claims out."""

from __future__ import annotations

from pathlib import Path

from carbon_room import core
from carbon_room.models import Actor, IngestReport


class Collector:
    """Thin agent boundary for a room router or scheduled collection run.

    It deliberately cannot verify, approve, resolve, or publish anything. Those
    decisions belong to the Watchdog and report workflow.
    """

    name = "collector"

    def ingest(self, close_id: str, actor: Actor) -> IngestReport:
        """Collect the close's configured seed and baseline evidence."""
        return core.ingest(close_id, actor)

    def ingest_file(self, close_id: str, path: str | Path, actor: Actor, chat_message_id: str,
                    site: str | None = None) -> list[str]:
        """Record a human-uploaded attachment with its originating Switch message."""
        return core.ingest_file(close_id, path, actor, chat_message_id, site)
