"""Offline, paginated PDF rendering of the same ledger-backed report snapshot."""

from __future__ import annotations

from html import escape
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import HRFlowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from carbon_room import config
from carbon_room.ledger import ledger
from carbon_room.models import Report

INK = colors.HexColor("#11283A")
TEAL = colors.HexColor("#087F76")
PALE = colors.HexColor("#E9F5F2")
MUTED = colors.HexColor("#526574")


def _paragraph(value: object, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(str(value)), style)


def _section(story: list, title: str, style: ParagraphStyle) -> None:
    story.extend((Spacer(1, 7 * mm), Paragraph(title, style), Spacer(1, 2 * mm)))


def _table(rows: list[list[object]], widths: list[float], body: ParagraphStyle) -> Table:
    wrapped = [[_paragraph(value, body) for value in row] for row in rows]
    table = Table(wrapped, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), PALE),
                ("TEXTCOLOR", (0, 0), (-1, 0), INK),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, 0), 0.6, TEAL),
                ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.HexColor("#D9E4E7")),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return table


def _page(canvas: Canvas, doc: SimpleDocTemplate) -> None:
    canvas.saveState()
    width, height = A4
    canvas.setStrokeColor(TEAL)
    canvas.setLineWidth(1)
    canvas.line(18 * mm, height - 15 * mm, width - 18 * mm, height - 15 * mm)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(18 * mm, 14 * mm, "CARBON ROOM  |  HUMAN REVIEW COPY")
    canvas.drawRightString(width - 18 * mm, 14 * mm, f"Page {doc.page}")
    canvas.restoreState()


def _invariant_canvas(*args, **kwargs) -> Canvas:
    kwargs["invariant"] = 1
    return Canvas(*args, **kwargs)


def render(report: Report, conn) -> bytes:
    """Return a PDF without changing the ledger or reading the Markdown output."""
    close = ledger.get_close(conn, report.close_id)
    month = close["month"]
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "cr-title",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=22,
        leading=26,
        textColor=INK,
        spaceAfter=8,
    )
    heading = ParagraphStyle(
        "cr-heading", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=12, leading=15, textColor=INK
    )
    body = ParagraphStyle(
        "cr-body",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=INK,
        splitLongWords=1,
    )
    small = ParagraphStyle("cr-small", parent=body, fontSize=8, leading=11, textColor=MUTED)
    callout = ParagraphStyle(
        "cr-callout", parent=body, fontName="Helvetica-Bold", fontSize=11, leading=16, textColor=TEAL
    )
    stream = BytesIO()
    doc = SimpleDocTemplate(
        stream,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=22 * mm,
        bottomMargin=22 * mm,
        title=f"Carbon Room {report.close_id}",
        author="Carbon Room",
    )
    width = A4[0] - 36 * mm
    story: list = [
        Paragraph("Carbon Room | Monthly emissions close", title),
        _paragraph(f"{month}  |  Version {report.version}  |  Factor set {close['factor_set']}", small),
        Spacer(1, 5 * mm),
        _paragraph(f"Verified only: {report.verified_total_tCO2e} tCO2e", callout),
        _paragraph(
            f"Unverified, excluded: {report.unverified_excluded_tCO2e} tCO2e. "
            f"Coverage: {report.coverage_pct}%. Sources: {report.source_coverage}. "
            f"Open gaps: {len(report.gaps)}.",
            body,
        ),
        Spacer(1, 2 * mm),
        _paragraph(
            "Only verified current-month location/basisless calculations enter the total. "
            "Market-based data-centre values are shown separately and are not additive.",
            small,
        ),
        HRFlowable(width=width, thickness=0.8, color=TEAL, spaceBefore=10, spaceAfter=3),
    ]

    dc = report.datacentre_line
    _section(story, "Data centre | separate accounting bases", heading)
    if dc is None:
        story.append(_paragraph("No data-centre evidence for this close.", body))
    else:
        story.append(
            _table(
                [
                    ["Location-based", "Market-based", "PUE"],
                    [
                        f"{dc.location_kgco2e} kgCO2e" if dc.location_kgco2e is not None else "not supplied",
                        f"{dc.market_kgco2e} kgCO2e" if dc.market_kgco2e is not None else "not supplied",
                        dc.pue if dc.pue is not None else "not supplied",
                    ],
                ],
                [width * 0.38, width * 0.38, width * 0.24],
                body,
            )
        )
        story.extend(
            (
                Spacer(1, 2 * mm),
                _paragraph(dc.rec_flag or "No market-based zero reported", small),
                _paragraph(f"AI workload: {dc.ai_line_status}. {dc.note}", small),
            )
        )

    _section(story, "Verified source trace", heading)
    if report.s_tags:
        rows = [["Tag", "Activity / basis", "Source", "kgCO2e"]]
        for tag in report.s_tags:
            basis = "market (not in total)" if "as reported by vendor" in tag.recompute else "location / standard"
            rows.append([tag.tag, f"{tag.activity} | {basis}", tag.file_name, str(tag.kgco2e)])
        story.append(_table(rows, [width * 0.11, width * 0.29, width * 0.33, width * 0.27], body))
    else:
        story.append(_paragraph("No verified calculations.", body))

    _section(story, "Excluded evidence and open gaps", heading)
    excluded = [claim for claim in ledger.get_claims(conn, report.close_id, month=month) if claim.status != "VERIFIED"]
    if excluded:
        for claim in excluded:
            story.append(
                _paragraph(
                    f"{claim.site} / {claim.activity}: {claim.value} {claim.unit} - "
                    f"{claim.status}; excluded from total.",
                    body,
                )
            )
    else:
        story.append(_paragraph("No live current-month claim is excluded.", body))
    for gap in report.gaps:
        story.append(_paragraph(f"{gap['gap_id']} ({gap['rule']}): {gap['title']} - owner {gap['owner']}", body))
    if not report.gaps:
        story.append(_paragraph("No open gaps.", body))

    _section(story, "Review cautions and boundaries", heading)
    for flag in report.compliance_flags:
        story.append(_paragraph(f"- {flag}", body))
    for category in config.load_config().get("scope3", {}).get("listed_as_no_data", []):
        story.append(_paragraph(f"{category}: no data, not zero.", small))

    if report.s_tags:
        story.append(PageBreak())
    _section(story, "Trace appendix", heading)
    for tag in report.s_tags:
        story.extend(
            (
                _paragraph(f"{tag.tag} | {tag.file_name}, page {tag.page}", callout),
                _paragraph(f"Evidence: {tag.excerpt}", body),
                _paragraph(f"SHA-256: {tag.sha256}", small),
                _paragraph(f"Factor: {tag.factor_id}@{tag.factor_version} ({tag.geography})", small),
                _paragraph(f"Recompute: {tag.recompute}", small),
                _paragraph(
                    f"Approval: {tag.approver or 'tier 1'}; Switch message: {tag.chat_message_id or 'none (tier 1)'}",
                    small,
                ),
                Spacer(1, 3 * mm),
            )
        )
    story.extend(
        (
            Spacer(1, 5 * mm),
            _paragraph(
                f"Published by {report.approver or 'pending'} at {report.published_at or 'draft'}.",
                small,
            ),
        )
    )
    doc.build(story, onFirstPage=_page, onLaterPages=_page, canvasmaker=_invariant_canvas)
    return stream.getvalue()
