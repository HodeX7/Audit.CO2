"""Rules proposer: label patterns for common bill/invoice layouts. No network, deterministic.

It is a PROPOSER like the LLM: everything it returns still goes through the same excerpt
verification in extract.py. It exists so the demo and the tests run without an API key, and
as a fallback when the LLM is rate-limited. Unknown layouts produce no claims (and therefore
a gap), never a guess.
"""

from __future__ import annotations

import re
from typing import Any

PROPOSER = "rules-v1"

_NUM = r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"

DOC_REF = re.compile(r"^(?:bill|invoice|statement)\s+(?:number|no\.?|#)\s*:\s*([A-Z0-9][A-Z0-9-]{2,})", re.I)
CERT_ID = re.compile(r"^certificate\s+id\s*:\s*([A-Z0-9][A-Z0-9-]{2,})", re.I)
REPLACES = re.compile(r"^(?:replaces|supersedes|corrects)\s+(?:bill|invoice|statement)?\s*(?:number)?\s*:?\s*"
                      r"([A-Z0-9][A-Z0-9-]{2,})", re.I)
SITE_LINE = re.compile(r"^(service location|deliver to|claimed against|site|facility)\s*:\s*(.+)$", re.I)
REGION_LINE = re.compile(r"^region\s*:\s*(\S+)", re.I)
PERIOD_LINE = re.compile(r"^(service period|billing period|delivery date|consumption period claimed|period)\s*:\s*(.+)$",
                         re.I)

CLAIM_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("electricity", re.compile(r"total (?:electricity|energy) used[^:]*:\s*" + _NUM + r"\s*(kWh|MWh)\b", re.I)),
    ("natural_gas", re.compile(r"total (?:natural )?gas used[^:]*:\s*" + _NUM + r"\s*(therms?|Dth|MMBtu)\b", re.I)),
    ("diesel", re.compile(r"quantity delivered\s*:\s*" + _NUM + r"\s*(gal|gallons|L|litres|liters)\b", re.I)),
    ("cloud_compute", re.compile(r"IT equipment energy[^:]*:\s*" + _NUM + r"\s*(kWh|MWh)\b", re.I)),
]
FIELD_PATTERNS: dict[str, list[tuple[str, re.Pattern[str]]]] = {
    "diesel": [
        ("delivery_ref", re.compile(r"^delivery ticket\s*:\s*([A-Z0-9][A-Z0-9-]+)", re.I)),
        ("delivery_date", re.compile(r"^delivery date\s*:\s*(.+)$", re.I)),
    ],
    "cloud_compute": [
        ("pue", re.compile(r"\(PUE\)[^:]*:\s*(\d+(?:\.\d+)?)", re.I)),
        ("wue_l_per_kwh", re.compile(r"\(WUE\)[^:]*:\s*(\d+(?:\.\d+)?)\s*L/kWh", re.I)),
        ("cloud_region", re.compile(r"^region\s*:\s*(\S+)", re.I)),
    ],
    "electricity": [("meter_id", re.compile(r"^meter\s*:\s*([A-Z0-9][A-Z0-9-]+)", re.I))],
    "natural_gas": [("meter_id", re.compile(r"^meter\s*:\s*([A-Z0-9][A-Z0-9-]+)", re.I))],
}
REC_QTY = re.compile(r"quantity retired\s*:\s*" + _NUM + r"\s*(MWh|kWh)\b", re.I)
REC_FIELDS = [
    ("certificate_id", CERT_ID),
    ("region", re.compile(r"^generation region\s*:\s*(.+)$", re.I)),
    ("vintage", re.compile(r"^vintage[^:]*:\s*(\d{4})\b", re.I)),
]


def _lines(pages: list[str]):
    for page_no, text in enumerate(pages, start=1):
        for line in text.split("\n"):
            line = " ".join(line.split())
            if line:
                yield page_no, line


def _first(pages: list[str], pattern: re.Pattern[str], group: int = 1) -> dict[str, Any] | None:
    for page_no, line in _lines(pages):
        m = pattern.search(line)
        if m:
            return {"value": m.group(group).strip(), "excerpt": line, "page": page_no}
    return None


def classify(pages: list[str]) -> str:
    """Document kind from keywords. 'other' when unsure (the LLM may then decide)."""
    text = " ".join(pages).lower()
    if "renewable energy certificate" in text or "certificate id" in text:
        return "rec_certificate"
    if "cloud" in text and ("it equipment energy" in text or "pue" in text):
        return "cloud_invoice"
    if "fuel invoice" in text or ("diesel" in text and "quantity delivered" in text):
        return "fuel_invoice"
    if ("electric" in text and "kwh" in text) or ("electric" in text and "mwh" in text) or (
        "gas" in text and "therm" in text
    ):
        return "utility_bill"
    return "other"


def propose(pages: list[str]) -> dict[str, Any]:
    kind = classify(pages)
    proposal: dict[str, Any] = {
        "schema": "cr.extraction.v1",
        "doc_kind": kind,
        "doc_ref": _first(pages, CERT_ID) if kind == "rec_certificate" else _first(pages, DOC_REF),
        "replaces_ref": _first(pages, REPLACES),
        "site": None,
        "period": None,
        "claims": [],
        "instruments": [],
    }
    site = _first(pages, SITE_LINE, group=2)
    if site is None and kind == "cloud_invoice":
        site = _first(pages, REGION_LINE)
    proposal["site"] = site
    proposal["period"] = _first(pages, PERIOD_LINE, group=2)
    if proposal["period"]:
        from carbonroom.ingest.extract import parse_period

        proposal["period"]["value"] = parse_period(proposal["period"]["value"]) or proposal["period"]["value"]

    full_text = " ".join(pages).lower()
    for category, pattern in CLAIM_PATTERNS:
        if category == "diesel" and "diesel" not in full_text:
            continue  # a fuel delivery of something else is not diesel; leave it to a human
        for page_no, line in _lines(pages):
            m = pattern.search(line)
            if not m:
                continue
            fields = {}
            for name, fpat in FIELD_PATTERNS.get(category, []):
                found = _first(pages, fpat)
                if found:
                    fields[name] = found
            proposal["claims"].append(
                {"category": category, "quantity": m.group(1), "unit": m.group(2), "excerpt": line,
                 "page": page_no, "fields": fields}
            )
    if kind == "rec_certificate":
        for page_no, line in _lines(pages):
            m = REC_QTY.search(line)
            if not m:
                continue
            fields = {name: found for name, pat in REC_FIELDS if (found := _first(pages, pat))}
            proposal["instruments"].append(
                {"kind": "REC", "mwh": m.group(1), "unit": m.group(2), "excerpt": line, "page": page_no,
                 "fields": fields}
            )
    return proposal
