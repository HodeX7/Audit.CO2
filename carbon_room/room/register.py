"""Agent registration CLI: python -m carbon_room.room.register."""

from __future__ import annotations

from collections.abc import Sequence

import httpx

CONNECTOR_TYPE: str = "carbon-room-python"
DESCRIPTIONS: dict[str, str] = {
    "carbon-room": "Runs the month-end emissions close: posts the plan, the summary and the publish.",
    "collector": "Collects the month's bills and invoices into the ledger.",
    "watchdog": "Checks every ledger row and opens a thread for each gap, with a named owner.",
    "reporter": "Drafts the report and traces any figure back to its source.",
}


def registration_body(name: str) -> dict:
    raise NotImplementedError


def main(
    argv: Sequence[str] | None = None, *, transport: httpx.BaseTransport | None = None
) -> int:
    raise NotImplementedError


if __name__ == "__main__":
    raise SystemExit(main())
