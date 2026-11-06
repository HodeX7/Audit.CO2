"""Deterministic billing-period parsing; this never invokes a model."""

from __future__ import annotations

import re
from datetime import date, datetime


def _validated_period(start: str, end: str) -> tuple[str, str]:
    """Normalise a calendar-valid, non-reversed inclusive billing period."""
    try:
        start_date, end_date = date.fromisoformat(start), date.fromisoformat(end)
    except ValueError as error:
        raise ValueError("billing period contains an invalid calendar date") from error
    if end_date < start_date:
        raise ValueError("billing period end precedes its start")
    return start_date.isoformat(), end_date.isoformat()


def parse_period(text: str) -> tuple[str, str] | None:
    """Parse the contract seed's human and ISO period forms."""
    iso = re.search(r"(?:Period:\s*)?(\d{4}-\d{2}-\d{2})\s+(?:to|–|-)\s+(\d{4}-\d{2}-\d{2})", text)
    if iso:
        return _validated_period(*iso.groups())
    natural = re.search(
        r"Billing period:\s*(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})\s*(?:–|-)\s*(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})", text
    )
    if natural:
        try:
            values = tuple(datetime.strptime(value, "%d %b %Y").date().isoformat() for value in natural.groups())
        except ValueError as error:
            raise ValueError("billing period contains an invalid calendar date") from error
        return _validated_period(*values)
    json_dates = dict(re.findall(r'"(period_start|period_end)"\s*:\s*"(\d{4}-\d{2}-\d{2})"', text))
    if {"period_start", "period_end"} <= json_dates.keys():
        return _validated_period(json_dates["period_start"], json_dates["period_end"])
    return None
