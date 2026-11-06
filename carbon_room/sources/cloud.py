"""Deterministic cloud-invoice mapping; cloud JSON never goes through an LLM."""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from pathlib import Path


def extract(path: str | Path) -> dict:
    """Map the contract cloud fields into one `dc_it_kwh` candidate and attributes."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("cloud invoice must be a JSON object")
    if "it_energy_kwh" not in payload:
        raise ValueError("cloud invoice is missing it_energy_kwh")
    try:
        value = Decimal(str(payload["it_energy_kwh"]))
    except InvalidOperation as error:
        raise ValueError("cloud invoice it_energy_kwh is not decimal") from error
    if not value.is_finite() or value <= 0:
        raise ValueError("cloud invoice it_energy_kwh must be a positive finite decimal")
    attributes = {
        key: payload[key]
        for key in (
            "pue",
            "region",
            "market_based_kgco2e",
            "vendor_factor_ref",
            "provider",
            "accounting_method",
            "methodology_version",
        )
        if key in payload
    }
    attributes["ai_breakdown_available"] = bool(
        payload.get("per_model_breakdown") or payload.get("per_service_breakdown")
    )
    return {
        "activity": "dc_it_kwh",
        "value": value,
        "unit": "kWh",
        "excerpt": json.dumps({"it_energy_kwh": payload["it_energy_kwh"]}, separators=(",", ":")),
        "page": 0,
        "attributes": attributes,
    }
