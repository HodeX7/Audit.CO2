"""Trace a published source tag back to evidence and exact arithmetic."""

from __future__ import annotations

from carbon_room.calc.calculator import recompute
from carbon_room.ledger import ledger
from carbon_room.models import SourceTag


def lookup(conn, close_id: str, tag: str) -> SourceTag:
    assignment = ledger.get_s_tag(conn, close_id, tag)
    row = conn.execute(
        "SELECT * FROM calculations WHERE calc_id=? AND claim_id=?",
        (assignment["calc_id"], assignment["claim_id"]),
    ).fetchone()
    if row is None:
        raise ValueError(f"source tag {tag} has no calculation")
    calculation = ledger._calc(row)
    claim = ledger.get_claim(conn, calculation.claim_id)
    source = next(item for item in ledger.get_sources(conn, close_id) if item.source_doc_id == claim.source_doc_id)
    factor = ledger.get_factor(conn, calculation.factor_id)
    formula, computed, matches = recompute(calculation, claim, factor)
    approvals = [
        item
        for item in ledger.get_approvals(conn, close_id, subject_id=claim.claim_id)
        if item["decision"] == "approve"
    ]
    approval = approvals[-1] if approvals else None
    return SourceTag(
        tag=tag,
        file_name=source.file_name,
        page=claim.source_page,
        excerpt=claim.source_excerpt,
        sha256=source.sha256,
        activity=claim.activity,
        value=claim.value,
        unit=claim.unit,
        factor_id=calculation.factor_id,
        factor_version=calculation.factor_version,
        geography=factor["geography"],
        recompute=f"{formula}; recomputed={computed} kgCO2e; matches={matches}",
        kgco2e=calculation.kgco2e,
        status=claim.status,
        approver=approval["actor_id"] if approval else None,
        chat_message_id=approval["chat_message_id"] if approval else None,
    )
