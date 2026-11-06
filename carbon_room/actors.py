"""Non-human actors that P2 code acts as; the ledger only lets these set VERIFIED or change a close phase."""

from __future__ import annotations

from carbon_room.models import Actor

CALCULATOR = Actor("system", "calculator", "Calculator")
WATCHDOG = Actor("agent", "watchdog", "Watchdog")
REPORTER = Actor("agent", "reporter", "Reporter")
