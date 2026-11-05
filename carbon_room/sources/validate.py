"""Proof validator for LLM candidate excerpts."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation


def _normalise(text: str) -> str:
    return " ".join(text.split())


def validate(candidate: dict, pages: list[str]) -> tuple[bool, str]:
    """Accept only a verbatim excerpt that itself contains the claimed number."""
    page = candidate.get("page", 0)
    if not isinstance(page, int) or not 0 <= page < len(pages):
        return False, "candidate page is outside the source"
    excerpt, text = _normalise(str(candidate.get("excerpt", ""))), _normalise(pages[page])
    if not excerpt or excerpt not in text:
        return False, "excerpt is not verbatim source text"
    try:
        number = Decimal(str(candidate["value"]).replace(",", ""))
    except (KeyError, InvalidOperation):
        return False, "candidate value is not decimal"
    values = [Decimal(item.replace(",", "")) for item in re.findall(r"\d[\d,]*(?:\.\d+)?", excerpt)]
    return (True, "") if number in values else (False, "value is absent from excerpt")
