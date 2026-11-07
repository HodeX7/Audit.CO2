"""Deterministic, offline Markdown and presentation-size coverage view."""

from __future__ import annotations

from datetime import date
from html import escape
from pathlib import Path

from carbon_room import config
from carbon_room.ledger import ledger
from carbon_room.models import Report

TEMPLATES = Path(__file__).resolve().parent / "templates"


def _dc_text(report: Report) -> str:
    dc = report.datacentre_line
    if dc is None:
        return "No data-centre evidence."
    market = f"{dc.market_kgco2e} kgCO2e" if dc.market_kgco2e is not None else "not supplied"
    return "\n".join(
        (
            f"- Location-based: {dc.location_kgco2e} kgCO2e",
            f"- Market-based: {market}",
            f"- PUE: {dc.pue if dc.pue is not None else 'not supplied'}",
            f"- REC/certificate note: {dc.rec_flag or 'No market-based zero reported'}",
            f"- AI workload: {dc.ai_line_status}; {dc.note}",
        )
    )


def pack(report: Report, conn) -> tuple[str, str]:
    """Render without changing the close; HTML is self-contained and uses no external resources."""
    close = ledger.get_close(conn, report.close_id)
    excluded = [
        f"- {claim.site} / {claim.activity}: {claim.value} {claim.unit} — {claim.status}; reason: "
        + next(
            (
                item["reason"]
                for item in reversed(ledger.get_approvals(conn, report.close_id, subject_id=claim.claim_id))
                if item["decision"] == "reject"
            ),
            "not verified",
        )
        for claim in ledger.get_claims(conn, report.close_id, month=close["month"])
        if claim.status != "VERIFIED"
    ]
    sources = [
        f"- [{tag.tag}] {tag.file_name}, p.{tag.page}: {tag.excerpt} | SHA-256 {tag.sha256} | "
        f"{tag.activity} {tag.value} {tag.unit} | {tag.factor_id}@{tag.factor_version} "
        f"({tag.geography}) | {tag.kgco2e} kgCO2e | {tag.recompute} | "
        f"approver {tag.approver or 'tier 1'}; Switch message {tag.chat_message_id or 'none (tier 1)'}"
        for tag in report.s_tags
    ]
    gaps = [f"- {gap['gap_id']} {gap['title']} — owner {gap['owner']}" for gap in report.gaps]
    conflicts = [
        f"- {item['gap_id']}: selected {item['selected_claim_id'] or 'pending'}; "
        f"superseded {', '.join(item['superseded_loser_ids']) or 'none'}; "
        f"picked by {item['picked_by'] or 'pending'}; Switch message {item['chat_message_id'] or 'pending'}"
        for item in report.conflicts
    ]
    scope3 = config.load_config().get("scope3", {}).get("listed_as_no_data", [])
    markdown = (
        (TEMPLATES / "report.md.j2")
        .read_text(encoding="utf-8")
        .format(
            close_id=report.close_id,
            month=close["month"],
            month_name=date.fromisoformat(close["month"] + "-01").strftime("%B"),
            verified=report.verified_total_tCO2e,
            excluded=report.unverified_excluded_tCO2e,
            gap_count=len(report.gaps),
            coverage=report.coverage_pct,
            source_coverage=report.source_coverage,
            factor_set=close["factor_set"],
            factor_versions=", ".join(report.factor_versions) or "none",
            dc=_dc_text(report),
            sources="\n".join(sources) or "- None verified",
            excluded_rows="\n".join(excluded) or "- None",
            gaps="\n".join(gaps) or "- None",
            conflicts="\n".join(conflicts) or "- None",
            scope3="\n".join(f"- {item}: no data, not zero" for item in scope3) or "- No categories listed",
            flags="\n".join(f"- {flag}" for flag in report.compliance_flags),
            approver=report.approver or "pending human publish",
            published_at=report.published_at or "draft",
        )
    )
    cards = [
        f"<div class='card'><h2>{escape(tag.tag)}</h2><p>{escape(tag.activity)}</p>"
        f"<strong>{escape(str(tag.kgco2e))} kgCO2e</strong><small>{escape(tag.file_name)}</small></div>"
        for tag in report.s_tags
    ]
    html = (
        (TEMPLATES / "coverage.html.j2")
        .read_text(encoding="utf-8")
        .format(
            close_id=escape(report.close_id),
            coverage=escape(str(report.coverage_pct)),
            source_coverage=escape(report.source_coverage),
            verified=escape(str(report.verified_total_tCO2e)),
            excluded=escape(str(report.unverified_excluded_tCO2e)),
            cards="".join(cards),
            gap_count=len(report.gaps),
            dc=escape(_dc_text(report)).replace("\n", "<br>"),
        )
    )
    return markdown, html
