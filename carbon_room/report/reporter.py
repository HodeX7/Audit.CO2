"""Draft an evidence-linked report from one close's authoritative ledger."""

from __future__ import annotations

from carbon_room.actors import REPORTER
from carbon_room.ledger import ledger
from carbon_room.models import Report
from carbon_room.report import compliance, stags, summary, trace


def draft(conn, close_id: str) -> Report:
    close = ledger.get_close(conn, close_id)
    if close["phase"] == "PUBLISHED":
        raise ValueError("close is already published")
    totals = summary.build(conn, close_id)
    tags = [trace.lookup(conn, close_id, tag) for tag in stags.assign(conn, close_id, close["version"], close["month"])]
    gaps = [
        {
            "gap_id": gap.gap_id,
            "rule": gap.rule,
            "kind": gap.kind,
            "title": gap.title,
            "owner": gap.owner,
            "claim_ids": gap.claim_ids,
        }
        for gap in totals.open_gaps
    ]
    conflicts = []
    for gap in ledger.get_gaps(conn, close_id):
        if gap.rule != "R2":
            continue
        selected = (gap.resolution or {}).get("claim_id")
        conflicts.append(
            {
                "gap_id": gap.gap_id,
                "title": gap.title,
                "owner": gap.owner,
                "status": gap.status,
                "selected_claim_id": selected,
                "superseded_loser_ids": [claim_id for claim_id in gap.claim_ids if claim_id != selected],
                "picked_by": gap.resolved_by,
                "chat_message_id": gap.resolved_message_id,
            }
        )
    report = Report(
        close_id=close_id,
        version=close["version"],
        verified_total_tCO2e=totals.verified_kgco2e / 1000,
        unverified_excluded_tCO2e=totals.excluded_kgco2e / 1000,
        coverage_pct=totals.coverage_pct,
        source_coverage=f"{totals.sources_verified}/{totals.sources_expected}",
        gaps=gaps,
        conflicts=conflicts,
        factor_versions=sorted({f"{tag.factor_id}@{tag.factor_version}" for tag in tags}),
        datacentre_line=totals.dc_line,
        s_tags=tags,
        compliance_flags=compliance.flags(totals),
        approver=None,
        published_at=None,
    )
    if close["phase"] != "DRAFTED":
        ledger.set_phase(conn, close_id, "DRAFTED", REPORTER)
    return report
