"""Evidence-candidate extraction boundary; validation remains deterministic."""

from __future__ import annotations

import sqlite3

from carbon_room import llm


def extract(pages: list[str], kind: str, file_name: str, *, agent: str = "collector", close_id: str = "",
            conn: sqlite3.Connection | None = None) -> list[dict]:
    """Ask the configured model for JSON candidates, never judgments or calculations."""
    response = llm.complete_json("extract", "Copy excerpts character-for-character; if unsure return nothing.",
                                 {"kind": kind, "file_name": file_name, "pages": pages}, agent, close_id, conn=conn)
    candidates = response.get("candidates", [])
    return [candidate for candidate in candidates if isinstance(candidate, dict)]
