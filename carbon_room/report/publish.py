"""Human-gated publish of an honest, immutable close-version snapshot."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from carbon_room import config
from carbon_room.actors import REPORTER
from carbon_room.ledger import ledger
from carbon_room.ledger.audit import append_event
from carbon_room.models import NeedsRoomEvent, NotAllowed
from carbon_room.report import pdf, render, reporter

OUTPUT_ROOT = Path("out")


def publish(conn, close_id, actor, chat_message_id):
    if actor.kind != "human" or actor.role not in config.load_config()["approvals"]["publish_roles"]:
        raise NotAllowed("publishing requires a configured human publish role")
    if not chat_message_id:
        raise NeedsRoomEvent("publishing requires a Switch chat_message_id")
    close = ledger.get_close(conn, close_id)
    if close["phase"] == "PUBLISHED":
        raise ValueError("close is already published")
    report = reporter.draft(conn, close_id)
    if any("matches=False" in tag.recompute for tag in report.s_tags):
        raise ValueError("source-tag recomputation mismatch; publication refused")
    report.approver = actor.id
    report.published_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    markdown, html = render.pack(report, conn)
    pdf_bytes = pdf.render(report, conn)
    output = OUTPUT_ROOT / close["month"] / f"v{close['version']}"
    if output.exists():
        raise ValueError(f"publish output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=f".v{close['version']}-", dir=output.parent) as staging_dir:
        staging = Path(staging_dir)
        (staging / "report.json").write_text(
            json.dumps(asdict(report), default=str, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (staging / "report.md").write_text(markdown, encoding="utf-8")
        (staging / "coverage.html").write_text(html, encoding="utf-8")
        (staging / "report.pdf").write_bytes(pdf_bytes)
        ledger.add_approval(
            conn, close_id, "publish", close_id, 3, actor, "approve", "human published report", chat_message_id
        )
        conn.execute(
            "UPDATE closes SET published_by=?, published_message_id=?, published_at=? WHERE close_id=?",
            (actor.id, chat_message_id, report.published_at, close_id),
        )
        append_event(
            conn,
            close_id,
            actor,
            "report_published",
            chat_message_id=chat_message_id,
            payload={"version": close["version"], "published_at": report.published_at, "output": str(output)},
        )
        ledger.set_phase(conn, close_id, "PUBLISHED", REPORTER)
        staging.rename(output)
    return report
