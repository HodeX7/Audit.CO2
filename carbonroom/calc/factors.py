"""Loads data/factors/*.csv into the shape of the `emission_factors` table
(contracts/schema.sql) and indexes it for lookup by the Calculator.

Never hand-type a factor value in code — every row here was read from a
CSV that cites a real published source (see data/factors/*.csv headers).
"""

import csv
from decimal import Decimal
from pathlib import Path


class FactorNotFoundError(KeyError):
    """Raised when no factor exists for a (category, region, scope) in a set."""


def load_factor_set(csv_path: str | Path) -> list[dict]:
    """Reads one factor CSV into a list of dicts matching the
    `emission_factors` table columns, with `factor` parsed as Decimal."""
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            row["factor"] = Decimal(row["factor"])
            rows.append(row)
    return rows


def index_factors(rows: list[dict]) -> dict[tuple[str, str, str], dict]:
    """Indexes factor rows by (category, region, scope) for O(1) lookup.

    All rows must share the same set_version — mixing versions in one
    index would silently blend a locked close with a different vintage.
    """
    versions = {row["set_version"] for row in rows}
    if len(versions) > 1:
        raise ValueError(f"index_factors got mixed set_version values: {versions}")
    index: dict[tuple[str, str, str], dict] = {}
    for row in rows:
        key = (row["category"], row["region"], row["scope"])
        if key in index:
            raise ValueError(f"duplicate factor for {key} in set {row['set_version']}")
        index[key] = row
    return index


def get_factor(index: dict[tuple[str, str, str], dict], category: str, region: str, scope: str) -> dict:
    key = (category, region, scope)
    if key not in index:
        raise FactorNotFoundError(
            f"no factor for category={category!r} region={region!r} scope={scope!r}"
        )
    return index[key]
