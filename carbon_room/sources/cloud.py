"""Deterministic cloud-invoice mapping; cloud JSON never goes through an LLM."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path


def extract(path: str | Path) -> dict:
    """Map the contract cloud fields into one `dc_it_kwh` candidate and attributes."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    attributes = {key: payload[key] for key in ("pue", "region", "market_based_kgco2e", "vendor_factor_ref") if key in payload}
    attributes["ai_breakdown_available"] = bool(payload.get("per_model_breakdown") or payload.get("per_service_breakdown"))
    value = Decimal(str(payload["it_energy_kwh"]))
    return {"activity": "dc_it_kwh", "value": value, "unit": "kWh", "excerpt": json.dumps({"it_energy_kwh": payload["it_energy_kwh"]}, separators=(",", ":")),
            "page": 0, "attributes": attributes}
