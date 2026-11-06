"""Factor catalogue loading and the locked-set lookup. No arithmetic and no model calls live here."""

from __future__ import annotations

import csv
import os
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from carbon_room import config
from carbon_room.calc.units import KNOWN_FACTOR_UNITS
from carbon_room.ledger import ledger
from carbon_room.models import NotFound

COLUMNS = ("factor_id", "source", "version", "year", "activity", "geography", "value", "unit", "citation")
_REF = re.compile(r"^\s*([A-Za-z0-9]+)\s+(\d{4})\s+([A-Za-z0-9]+)\s*$")


class FactorNotFound(NotFound):
    """The locked factor set has no row for this site and activity."""


def default_csv() -> Path:
    """Return ``factors.csv`` from the active config directory."""
    return Path(os.environ.get("CARBON_ROOM_CONFIG_DIR", config.DEFAULT_CONFIG_DIR)) / "factors.csv"


def read_csv(path: str | Path | None = None) -> list[dict]:
    """Read and validate the factor file; every row needs a decimal value, a known unit and a citation."""
    source = Path(path) if path else default_csv()
    with source.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != COLUMNS:
            raise ValueError(f"{source.name} must have exactly the columns {', '.join(COLUMNS)}")
        rows = []
        for number, raw in enumerate(reader, start=2):
            row = {key: (value or "").strip() for key, value in raw.items()}
            if not row["citation"]:
                raise ValueError(f"{source.name} line {number}: {row['factor_id'] or 'row'} has no citation")
            if row["unit"] not in KNOWN_FACTOR_UNITS:
                raise ValueError(f"{source.name} line {number}: unknown unit {row['unit']!r}")
            try:
                value = Decimal(row["value"])
            except InvalidOperation:
                raise ValueError(f"{source.name} line {number}: value {row['value']!r} is not a decimal") from None
            if not value.is_finite() or value <= 0:
                raise ValueError(f"{source.name} line {number}: value must be a positive finite decimal")
            rows.append(row)
    return rows


def load(conn, path: str | Path | None = None) -> int:
    """Load the catalogue into the ledger. Repeat loads of identical rows are safe; changed rows are rejected."""
    return ledger.load_factors(conn, read_csv(path))


def factor_set(name: str) -> dict[str, str]:
    """Return the source -> version pins of a configured factor set."""
    sets = config.load_config().get("factor_sets", {})
    if name not in sets:
        raise ValueError(f"unknown factor set {name!r}; configured: {', '.join(sorted(sets)) or 'none'}")
    return {str(source): str(version) for source, version in sets[name].items()}


def source_and_geography(site_id: str, activity: str) -> tuple[str, str]:
    """Return which published source and geography price an activity at a site."""
    if activity == "diesel_l":
        fuel = config.load_sites()["diesel_factor"]
        return str(fuel["source"]), str(fuel["geography"])
    if activity in ("electricity_kwh", "dc_it_kwh"):
        grid = config.site(site_id)["grid"]
        return str(grid["source"]), str(grid["geography"])
    raise ValueError(f"no factor source is configured for activity {activity!r}")


def locked_version(close: dict, source: str) -> str | None:
    """Return the version the close's locked set pins for ``source``."""
    return factor_set(close["factor_set"]).get(source)


def locked_factor(conn, close: dict, site_id: str, activity: str) -> dict:
    """Return the factor the close's locked set prescribes for an activity at a site."""
    source, geography = source_and_geography(site_id, activity)
    version = locked_version(close, source)
    if version is None:
        raise FactorNotFound(f"factor set {close['factor_set']} pins no version for {source}")
    row = ledger.find_factor(conn, source, version, activity, geography)
    if row is None:
        raise FactorNotFound(
            f"factor set {close['factor_set']} has no {source} {version} factor for {activity} "
            f"in {geography} (site {site_id}); load config/factors.csv or add the row"
        )
    return row


def factor_from_ref(conn, ref: str) -> dict | None:
    """Resolve a vendor's own factor reference such as ``Ember 2024 IE``; None when the catalogue lacks it."""
    match = _REF.match(ref or "")
    if match is None:
        return None
    source, version, geography = match.group(1).upper(), match.group(2), match.group(3).upper()
    return ledger.find_factor(conn, source, version, "dc_it_kwh", geography)


def is_locked(close: dict, factor: dict) -> bool:
    """True when ``factor`` is the version its source is pinned to in the close's locked set."""
    return locked_version(close, factor["source"]) == factor["version"]
