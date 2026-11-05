"""Deterministic billing-period parsing; this never invokes a model."""

from __future__ import annotations

import re
from datetime import datetime


def parse_period(text: str) -> tuple[str, str] | None:
    """Parse the contract seed's human and ISO period forms."""
    iso = re.search(r"(?:Period:\s*)?(\d{4}-\d{2}-\d{2})\s+(?:to|–|-)\s+(\d{4}-\d{2}-\d{2})", text)
    if iso:
        return iso.group(1), iso.group(2)
    natural = re.search(r"Billing period:\s*(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})\s*(?:–|-)\s*(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})", text)
    if natural:
        return tuple(datetime.strptime(value, "%d %b %Y").date().isoformat() for value in natural.groups())
    json_dates = re.search(r'"period_start"\s*:\s*"(\d{4}-\d{2}-\d{2})".*?"period_end"\s*:\s*"(\d{4}-\d{2}-\d{2})"', text, re.S)
    return json_dates.groups() if json_dates else None
