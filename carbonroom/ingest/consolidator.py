"""Consolidator: verified extraction -> ledger rows.

* One `activities` row per verified claim, always UNVERIFIED (only the checker verifies).
* If two documents claim the same thing (e.g. two invoices for one delivery), BOTH are stored.
  The checker flags the conflict; we never pick one silently.
* A document that says it replaces another (a corrected bill) marks the old document
  `superseded_by` the new one, and the new activity lists `replaces_activity_ids`.
  The old activity is left exactly as it is: the checker sees that its source was replaced,
  reopens it if it was VERIFIED ("false done"), and supersedes it with db.supersede_activity().
* Anything the document did not prove becomes an `unverified_claim` gap for the owner.
* Every write is logged to `events` (inside the db helpers).
"""

from __future__ import annotations

import sqlite3
from typing import Any

from carbonroom.ingest.extract import Extraction, Failure
from carbonroom.ledger import db

ACTOR = "cr-consolidator"
# Extraction field -> the key Richa's calculator / checker read from activity extra (both are kept).
# delivery_id groups invoices for one fuel delivery (conflict rule); wue is litres per IT kWh (data-centre line).
CALC_FIELD_NAMES = {"delivery_ref": "delivery_id", "wue_l_per_kwh": "wue"}


def _gap_detail(doc: dict[str, Any], ex: Extraction, failure: Failure) -> str:
    name = doc.get("original_name") or doc["path"]
    ref = f" ({ex.doc_ref.value})" if ex.doc_ref else ""
    if failure.scope == "doc":
        return (f"Couldn't verify {name}{ref}: {failure.reason}. Nothing from this document was added to the "
                f"ledger as fact. Please check it, or re-send a clear text PDF.")
    if failure.scope in ("claim", "instrument"):
        return (f"{name}{ref}: a proposed value was rejected because {failure.reason}. "
                f"Please confirm the quantity printed on this document.")
    return (f"{name}{ref}: {failure.reason}. The main quantity was recorded, but this detail is unverified; "
            f"please confirm it.")


def _replaced_activities(conn: sqlite3.Connection, old_doc_ids: list[str], site_id: str, category: str,
                         period: str) -> list[str]:
    ids: list[str] = []
    for doc_id in old_doc_ids:
        for act in db.list_activities(conn, source_doc_id=doc_id, include_superseded=False):
            if (act["site_id"], act["category"], act["period_id"]) == (site_id, category, period):
                ids.append(act["id"])
    return ids


def consolidate(
    conn: sqlite3.Connection,
    doc: dict[str, Any],
    ex: Extraction,
    *,
    received_from: str | None,
    room: str | None,
) -> dict[str, Any]:
    """Write one verified document into the ledger. Call inside db.transaction()."""
    out: dict[str, Any] = {"activities": [], "instruments": [], "gaps": [], "supersedes": []}
    with db.transaction(conn):
        # 1. Corrected / re-issued documents
        superseded_docs: list[str] = []
        if ex.replaces_ref:
            olds = [d for d in db.find_source_docs_by_ref(conn, ex.replaces_ref.value) if d["id"] != doc["id"]]
            if not olds:
                db.log_event(conn, ACTOR, "replaces_unknown_doc", doc["id"], {"replaces_ref": ex.replaces_ref.value})
            for old in olds:
                if old["superseded_by"] is None:
                    db.mark_doc_superseded(
                        conn, old["id"], doc["id"], actor=ACTOR,
                        reason=f"{ex.doc_ref.value if ex.doc_ref else doc['id']} says it replaces {ex.replaces_ref.value}",
                    )
                    superseded_docs.append(old["id"])

        common_evidence: dict[str, Any] = {}
        if ex.site_evidence:
            common_evidence["site"] = ex.site_evidence.evidence()
        if ex.period_evidence:
            common_evidence["period"] = ex.period_evidence.evidence()
        if ex.doc_ref:
            common_evidence["doc_ref"] = ex.doc_ref.evidence()
        if ex.replaces_ref:
            common_evidence["replaces_ref"] = ex.replaces_ref.evidence()

        # 2. Activities
        for claim in ex.claims:
            extra: dict[str, Any] = {
                "original_quantity": claim.normalized.original_quantity,
                "original_unit": claim.normalized.original_unit,
                "conversion": claim.normalized.conversion,
                "proposer": ex.proposer,
                "doc_ref": ex.doc_ref.value if ex.doc_ref else None,
                "evidence": {**common_evidence, **{n: f.evidence() for n, f in claim.fields.items()}},
                "unverified_fields": claim.unverified_fields,
            }
            for name, vf in claim.fields.items():
                extra[name] = vf.value
            for ours, calc_name in CALC_FIELD_NAMES.items():  # the names Richa's calculator/checker read
                if ours in claim.fields:
                    extra[calc_name] = claim.fields[ours].value
            if superseded_docs:
                extra["replaces_doc_ids"] = superseded_docs
                extra["replaces_activity_ids"] = _replaced_activities(
                    conn, superseded_docs, claim.site_id, claim.category, claim.period)
            row, created = db.add_activity(
                conn,
                site_id=claim.site_id,
                period_id=claim.period,
                category=claim.category,
                quantity=claim.normalized.quantity,
                unit=claim.normalized.unit,
                source_doc_id=doc["id"],
                excerpt=claim.excerpt,
                excerpt_locator=claim.locator,
                excerpt_sha256=claim.excerpt_sha256,
                created_by=ACTOR,
                extra=extra,
            )
            out["activities"].append({**row, "created": created})

        # 3. Instruments (RECs)
        for ins in ex.instruments:
            extra = {
                "original_quantity": ins.normalized.original_quantity,
                "original_unit": ins.normalized.original_unit,
                "conversion": ins.normalized.conversion,
                "proposer": ex.proposer,
                "doc_ref": ex.doc_ref.value if ex.doc_ref else None,
                "evidence": {**common_evidence, **{n: f.evidence() for n, f in ins.fields.items()}},
                "unverified_fields": ins.unverified_fields,
            }
            row, created = db.add_instrument(
                conn,
                period_id=ins.period,
                kind=ins.kind,
                mwh=ins.normalized.quantity,
                source_doc_id=doc["id"],
                created_by=ACTOR,
                region=ins.fields["region"].value if "region" in ins.fields else None,
                vintage=ins.fields["vintage"].value if "vintage" in ins.fields else None,
                site_id=ins.site_id,
                certificate_id=ins.fields["certificate_id"].value if "certificate_id" in ins.fields else None,
                excerpt=ins.excerpt,
                excerpt_locator=ins.locator,
                excerpt_sha256=ins.excerpt_sha256,
                extra=extra,
            )
            out["instruments"].append({**row, "created": created})

        # 4. Anything unproven -> a gap for the person who owns the evidence
        site = db.get_site(conn, ex.site_id) if ex.site_id else None
        for failure in ex.failures:
            gap, created = db.create_gap(
                conn,
                kind="unverified_claim",
                detail=_gap_detail(doc, ex, failure),
                created_by=ACTOR,
                period_id=ex.period,
                site_id=ex.site_id,
                owner_handle=(site or {}).get("owner_handle") or received_from,
                room=(site or {}).get("room") or room,
                dedupe_key=f"unverified:{doc['sha256']}:{failure.key}",
                refs={"source_doc_id": doc["id"], "scope": failure.scope, "field": failure.field,
                      "reason": failure.reason},
            )
            out["gaps"].append({**gap, "created": created})

        if superseded_docs:
            out["supersedes"].append({"new_doc": doc["id"], "old_docs": superseded_docs})
    return out
