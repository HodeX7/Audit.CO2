"""Placeholder demo data for `carbonroom seed-demo`.

This is NOT a substitute for Person 1's real Collector/Consolidator --
it exists only so `calc`/`check`/`report`/`resolve`/`approve`/`ask` have
something real to run against before their ingestion pipeline lands.
Delete this file's usage (or just stop calling seed-demo) the moment real
activities are flowing into the same `contracts/schema.sql` tables.

Models the brief's own demo traps: Reno's missing October electricity
bill, Austin's two conflicting diesel invoices, a stale-factor row, an
outlier, a false-done row, and the Nimbus Cloud data-centre line with a
matching REC.
"""

from __future__ import annotations

import hashlib

_NOW = "2026-11-03T00:00:00+00:00"


def _calc_id(activity_id: str, scope: str) -> str:
    """Matches carbonroom.calc.calculator._calc_id's scheme exactly, so a
    seeded row and a freshly computed one for the same (activity, scope)
    share the same id -- consistent with that module's own id contract."""
    return f"calc-{hashlib.sha256(f'{activity_id}:{scope}'.encode()).hexdigest()[:16]}"

SEED = {
    "sites": [
        {"id": "austin", "name": "Austin Plant", "region": "US-TX", "grid_subregion": "ERCT",
         "owner_handle": "omar", "room": "cr-site-austin"},
        {"id": "reno", "name": "Reno Office", "region": "US-NV", "grid_subregion": "NWPP",
         "owner_handle": "lena", "room": "cr-site-reno"},
        {"id": "cloud", "name": "Nimbus Cloud (Brightwell workload)", "region": "US-TX", "grid_subregion": "ERCT",
         "owner_handle": "dev", "room": "cr-cloud"},
    ],
    "periods": [
        {"id": "2026-09", "status": "CLOSED", "factor_set_version": "v1-2026-10", "approved_by": "grace", "closed_at": _NOW},
        {"id": "2026-10", "status": "OPEN", "factor_set_version": "v1-2026-10", "approved_by": None, "closed_at": None},
    ],
    "source_docs": [
        {"id": "doc-ng-sep", "superseded_by": None, "path": "data/seed/austin-natgas-2026-09.pdf", "kind": "utility_bill",
         "sha256": "sha-ng-sep", "received_from": "omar", "room": "cr-site-austin", "received_at": _NOW},
        {"id": "doc-ng-oct", "superseded_by": None, "path": "data/seed/austin-natgas-2026-10.pdf", "kind": "utility_bill",
         "sha256": "sha-ng-oct", "received_from": "omar", "room": "cr-site-austin", "received_at": _NOW},
        {"id": "doc-diesel-1", "superseded_by": None, "path": "data/seed/austin-diesel-INV-204.pdf", "kind": "fuel_invoice",
         "sha256": "sha-d1", "received_from": "omar", "room": "cr-site-austin", "received_at": _NOW},
        {"id": "doc-diesel-2", "superseded_by": None, "path": "data/seed/austin-diesel-INV-204B.pdf", "kind": "fuel_invoice",
         "sha256": "sha-d2", "received_from": "omar", "room": "cr-site-austin", "received_at": _NOW},
        {"id": "doc-elec-austin-sep", "superseded_by": None, "path": "data/seed/austin-elec-2026-09.pdf", "kind": "utility_bill",
         "sha256": "sha-ea-sep", "received_from": "omar", "room": "cr-site-austin", "received_at": _NOW},
        {"id": "doc-elec-austin-oct", "superseded_by": None, "path": "data/seed/austin-elec-2026-10.pdf", "kind": "utility_bill",
         "sha256": "sha-ea-oct", "received_from": "omar", "room": "cr-site-austin", "received_at": _NOW},
        {"id": "doc-elec-reno-sep", "superseded_by": None, "path": "data/seed/reno-elec-2026-09.pdf", "kind": "utility_bill",
         "sha256": "sha-er-sep", "received_from": "lena", "room": "cr-site-reno", "received_at": _NOW},
        {"id": "doc-cloud-oct", "superseded_by": None, "path": "data/seed/nimbus-invoice-2026-10.pdf", "kind": "cloud_invoice",
         "sha256": "sha-cloud-oct", "received_from": "dev", "room": "cr-cloud", "received_at": _NOW},
        # doc-elec-corrected must be inserted before doc-elec-prelim, since
        # prelim's superseded_by foreign key points at it.
        {"id": "doc-elec-corrected", "superseded_by": None, "path": "data/seed/austin-elec-corrected.pdf",
         "kind": "utility_bill", "sha256": "sha-corrected", "received_from": "omar", "room": "cr-site-austin", "received_at": _NOW},
        {"id": "doc-elec-prelim", "superseded_by": "doc-elec-corrected", "path": "data/seed/austin-elec-prelim.pdf",
         "kind": "utility_bill", "sha256": "sha-prelim", "received_from": "omar", "room": "cr-site-austin", "received_at": _NOW},
    ],
    "activities": [
        {"id": "act-ng-sep", "site_id": "austin", "period_id": "2026-09", "category": "natural_gas",
         "quantity": "150", "unit": "mmbtu", "source_doc_id": "doc-ng-sep", "excerpt": "Total: 150 mmBtu",
         "excerpt_locator": "p1", "excerpt_sha256": "sha-ng-sep", "status": "VERIFIED", "superseded_by": None,
         "created_by": "cr-consolidator", "updated_at": _NOW, "extra_json": None},
        {"id": "act-elec-austin-sep", "site_id": "austin", "period_id": "2026-09", "category": "electricity",
         "quantity": "45000", "unit": "kwh", "source_doc_id": "doc-elec-austin-sep", "excerpt": "Total: 45,000 kWh",
         "excerpt_locator": "p1", "excerpt_sha256": "sha-ea-sep", "status": "VERIFIED", "superseded_by": None,
         "created_by": "cr-consolidator", "updated_at": _NOW, "extra_json": None},
        {"id": "act-elec-reno-sep", "site_id": "reno", "period_id": "2026-09", "category": "electricity",
         "quantity": "10000", "unit": "kwh", "source_doc_id": "doc-elec-reno-sep", "excerpt": "Total: 10,000 kWh",
         "excerpt_locator": "p1", "excerpt_sha256": "sha-er-sep", "status": "VERIFIED", "superseded_by": None,
         "created_by": "cr-consolidator", "updated_at": _NOW, "extra_json": None},

        # Outlier trap: October gas is +60% vs September.
        {"id": "act-ng-oct", "site_id": "austin", "period_id": "2026-10", "category": "natural_gas",
         "quantity": "240", "unit": "mmbtu", "source_doc_id": "doc-ng-oct", "excerpt": "Total: 2,400 therms",
         "excerpt_locator": "p1", "excerpt_sha256": "sha-ng-oct", "status": "UNVERIFIED", "superseded_by": None,
         "created_by": "cr-consolidator", "updated_at": _NOW, "extra_json": None},

        # Conflict trap: two diesel invoices for the same delivery.
        {"id": "act-diesel-1", "site_id": "austin", "period_id": "2026-10", "category": "diesel",
         "quantity": "500", "unit": "gallon", "source_doc_id": "doc-diesel-1", "excerpt": "500 gal, delivered 10/12",
         "excerpt_locator": "p1", "excerpt_sha256": "sha-d1", "status": "UNVERIFIED", "superseded_by": None,
         "created_by": "cr-consolidator", "updated_at": _NOW, "extra_json": {"delivery_id": "DEL-310"}},
        {"id": "act-diesel-2", "site_id": "austin", "period_id": "2026-10", "category": "diesel",
         "quantity": "550", "unit": "gallon", "source_doc_id": "doc-diesel-2", "excerpt": "550 gal, delivered 10/12",
         "excerpt_locator": "p1", "excerpt_sha256": "sha-d2", "status": "UNVERIFIED", "superseded_by": None,
         "created_by": "cr-consolidator", "updated_at": _NOW, "extra_json": {"delivery_id": "DEL-310"}},

        # Clean -> should verify normally.
        {"id": "act-elec-austin-oct", "site_id": "austin", "period_id": "2026-10", "category": "electricity",
         "quantity": "48200", "unit": "kwh", "source_doc_id": "doc-elec-austin-oct", "excerpt": "Total: 48,200 kWh",
         "excerpt_locator": "p1", "excerpt_sha256": "sha-ea-oct", "status": "UNVERIFIED", "superseded_by": None,
         "created_by": "cr-consolidator", "updated_at": _NOW, "extra_json": None},

        # Stale-factor trap: already VERIFIED, but under last year's eGRID edition.
        {"id": "act-elec-legacy", "site_id": "austin", "period_id": "2026-10", "category": "electricity",
         "quantity": "2000", "unit": "kwh", "source_doc_id": "doc-elec-austin-oct", "excerpt": "Sub-meter 2: 2,000 kWh",
         "excerpt_locator": "p2", "excerpt_sha256": "sha-ea-oct", "status": "VERIFIED", "superseded_by": None,
         "created_by": "cr-consolidator", "updated_at": _NOW, "extra_json": None},

        # False-done trap: VERIFIED, but its source doc has since been superseded.
        {"id": "act-elec-prelim", "site_id": "austin", "period_id": "2026-10", "category": "electricity",
         "quantity": "1500", "unit": "kwh", "source_doc_id": "doc-elec-prelim", "excerpt": "Preliminary read: 1,500 kWh",
         "excerpt_locator": "p1", "excerpt_sha256": "sha-prelim", "status": "VERIFIED", "superseded_by": None,
         "created_by": "cr-consolidator", "updated_at": _NOW, "extra_json": None},

        # The data-centre / AI line.
        {"id": "act-cloud-oct", "site_id": "cloud", "period_id": "2026-10", "category": "cloud_compute",
         "quantity": "6000", "unit": "kwh", "source_doc_id": "doc-cloud-oct", "excerpt": "IT load: 6,000 kWh, PUE 1.3",
         "excerpt_locator": "p1", "excerpt_sha256": "sha-cloud-oct", "status": "UNVERIFIED", "superseded_by": None,
         "created_by": "cr-consolidator", "updated_at": _NOW, "extra_json": {"pue": "1.3", "wue": "0.5"}},

        # Reno's October electricity bill is simply absent -> missing_doc trap.
    ],
    "instruments": [
        {"id": "rec-1", "period_id": "2026-10", "kind": "REC", "mwh": "3", "region": "ERCT", "vintage": "2026",
         "source_doc_id": None, "quality_flags": "ok"},
    ],
    # act-elec-legacy was calculated and marked VERIFIED in an earlier
    # close attempt, before this period's factor set was locked to
    # v1-2026-10 -- it was never recalculated since. This is the
    # stale-factor trap; `carbonroom check` should catch it.
    "calculations": [
        {"id": _calc_id("act-elec-legacy", "2_location"),
         "activity_id": "act-elec-legacy", "factor_id": "ef-elec-erct-loc-v0", "scope": "2_location",
         "co2e_kg": "702.44", "computed_at": _NOW, "code_version": "calc-0.1.0"},
    ],
}


def _load_factor_rows() -> list[dict]:
    import pathlib
    from .calc import load_factor_set

    factors_dir = pathlib.Path(__file__).resolve().parent.parent / "data" / "factors"
    rows = []
    for name in ("v1-2026-10.csv", "v0-stale.csv"):
        for row in load_factor_set(factors_dir / name):
            row = dict(row)
            row["factor"] = str(row["factor"])  # Decimal -> text for SQLite storage
            row["valid_from"] = row.get("valid_from") or None
            row["valid_to"] = row.get("valid_to") or None
            rows.append(row)
    return rows


SEED["emission_factors"] = _load_factor_rows()
