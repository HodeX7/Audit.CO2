"""P1 collection orchestration: source evidence first, claims always unverified."""

from __future__ import annotations

import re
import sqlite3
from decimal import Decimal
from pathlib import Path

from carbon_room import config
from carbon_room.ledger import ledger
from carbon_room.ledger.audit import append_event
from carbon_room.ledger.ids import next_id
from carbon_room.ledger.locks import claim_lock
from carbon_room.models import Actor, Claim, IngestReport, LockHeld, NeedsRoomEvent, Source
from carbon_room.sources import cache, cloud
from carbon_room.sources import extract as model_extract
from carbon_room.sources.period import parse_period
from carbon_room.sources.readers import read
from carbon_room.sources.store import store_file
from carbon_room.sources.validate import validate


def _site_for(path: Path, explicit_site: str | None, pages: list[str]) -> str:
    if explicit_site:
        config.site(explicit_site)
        return explicit_site
    haystack = re.sub(r"[^a-z0-9]", "", f"{path.name}\n{' '.join(pages)}".lower())
    for entry in config.load_sites()["sites"]:
        identifiers = (entry["id"], entry["name"])
        if any(re.sub(r"[^a-z0-9]", "", value.lower()) in haystack for value in identifiers):
            return entry["id"]
    raise ValueError(f"could not infer a configured site from {path.name}; provide site=")


def _candidate(pages: list[str]) -> dict | None:
    text = "\n".join(pages)
    match = re.search(r"([^\n]*?)(\d[\d,]*(?:\.\d+)?)\s*(kWh|L)\b", text, re.I)
    if not match:
        return None
    unit = match.group(3)
    return {
        "activity": "electricity_kwh" if unit.lower() == "kwh" else "diesel_l",
        "value": match.group(2).replace(",", ""),
        "unit": unit,
        "excerpt": match.group(0),
        "page": 0,
        "attributes": {},
    }


def _mode() -> str:
    """Use P2 configuration when available; deterministic rules remain the offline default."""
    try:
        return str(config.load_config().get("llm", {}).get("mode", "rules"))
    except FileNotFoundError:
        return "rules"


def _candidates(
    pages: list[str], kind: str, file_name: str, digest: str, close_id: str, conn: sqlite3.Connection
) -> list[dict]:
    if kind == "cloud_invoice":
        return []
    mode = _mode()
    if mode == "replay":
        return cache.load(digest)
    if mode == "live":
        candidates = model_extract.extract(pages, kind, file_name, close_id=close_id, conn=conn)
        cache.save(digest, candidates)
        return candidates
    candidate = _candidate(pages)
    return [candidate] if candidate else []


def _validated_candidates(kind: str, pages: list[str], candidates: list[dict]) -> tuple[list[dict], str | None]:
    """Return proof‑backed candidates and a stable failure reason when none survive."""
    if kind == "cloud_invoice":
        # Cloud invoices may produce zero candidates – that’s a legitimate “no activity” case.
        return candidates, None if candidates else "cloud invoice has no activity record"
    valid, reasons = [], []
    for candidate in candidates:
        accepted, reason = validate(candidate, pages)
        if accepted:
            valid.append(candidate)
        else:
            reasons.append(reason)
    # When no candidates are accepted we surface the first validation reason;
    # if validation never ran (empty candidates) we fall back to a generic message.
    return valid, (reasons[0] if reasons else ("no extractable activity found" if not candidates else None))


def ingest_file(
    conn: sqlite3.Connection,
    close_id: str,
    path: str | Path,
    actor: Actor,
    *,
    site: str | None = None,
    month_from_period: bool = False,
    chat_message_id: str | None = None,
) -> list[str]:
    """Store, read and record one source; source text, not a model, is the proof boundary."""
    if actor.kind == "human" and not chat_message_id:
        raise NeedsRoomEvent("human uploads require a Switch chat_message_id")
    close = ledger.get_close(conn, close_id)
    source_path = Path(path)
    kind, result = read(source_path)
    pages = result if isinstance(result, list) else []
    resolved_site = _site_for(source_path, site, pages)
    if resolved_site not in close["sites"]:
        raise ValueError(f"{resolved_site} is outside the close boundary")
    stored_path, digest = store_file(source_path)
    with claim_lock(conn, close_id, resolved_site, close["month"], digest, actor.id):
        if ledger.source_for_sha(conn, close_id, digest) is not None:
            if chat_message_id:
                append_event(
                    conn,
                    close_id,
                    actor,
                    "room_file_ingested",
                    chat_message_id=chat_message_id,
                    payload={"claim_ids": [], "path": str(path), "duplicate": True},
                )
            return []
        source_id = next_id(conn, "SRC")
        period_error = None
        try:
            period = parse_period("\n".join(pages)) if pages else None
        except ValueError as error:
            period = None
            period_error = f"invalid billing period: {error}"
        try:
            candidates = (
                [cloud.extract(source_path)]
                if kind == "cloud_invoice" and pages
                else _candidates(pages, kind, source_path.name, digest, close_id, conn)
            )
            valid, extraction_error = _validated_candidates(kind, pages, candidates) if pages else ([], result)
        except ValueError as error:
            valid, extraction_error = [], str(error)
        if period_error:
            valid, extraction_error = [], period_error
        elif valid and period is None:
            valid, extraction_error = [], "billing period is required"
        source = Source(
            source_id,
            close_id,
            resolved_site,
            kind,
            source_path.name,
            stored_path,
            digest,
            len(pages),
            "\n\f".join(pages),
            period[0] if period else None,
            period[1] if period else None,
            "OK" if valid else "FAILED",
            None if valid else str(extraction_error),
        )
        ledger.add_source(conn, source, actor, chat_message_id)
        # A claim belongs to the billing period evidenced by its source, not the
        # close folder that happened to collect it.  The previous-period corpus
        # is deliberately collected with the close-month corpus for variance
        # checks, so using close["month"] here would corrupt that comparison.
        claim_month = period[0][:7] if period else close["month"]
        claim_ids = []
        for candidate in valid:
            scope = {"diesel_l": "1", "dc_it_kwh": "DC"}.get(candidate["activity"], "2")
            claim = Claim(
                next_id(conn, "CL"),
                close_id,
                resolved_site,
                claim_month,
                candidate["activity"],
                Decimal(str(candidate["value"])),
                candidate["unit"],
                scope,
                source_id,
                candidate["excerpt"],
                digest,
                candidate["page"],
                None,
                None,
                "UNVERIFIED",
                actor.id,
                None,
                None,
                candidate.get("attributes", {}),
            )
            claim_ids.append(ledger.add_claim(conn, claim, actor, chat_message_id))
        if chat_message_id:
            append_event(
                conn,
                close_id,
                actor,
                "room_file_ingested",
                chat_message_id=chat_message_id,
                payload={"claim_ids": claim_ids, "path": str(path)},
            )
        return claim_ids


def ingest(conn: sqlite3.Connection, close_id: str, actor: Actor) -> IngestReport:
    """Collect close-month and prior-month evidence, preserving each printed billing period."""
    close = ledger.get_close(conn, close_id)
    previous = (
        f"{int(close['month'][:4]) - (close['month'].endswith('-01')):04d}-{(int(close['month'][5:]) - 2) % 12 + 1:02d}"
    )
    files = [
        file
        for month in (close["month"], previous)
        for file in sorted((Path("data/seed") / month).glob("*"))
        if file.is_file()
    ]
    claims, failures = [], []
    for file in files:
        try:
            claims.extend(ingest_file(conn, close_id, file, actor))
        except (LockHeld, OSError, ValueError, sqlite3.IntegrityError) as exc:
            failures.append(f"{file.name}: {exc}")
    ledger.set_phase(conn, close_id, "COLLECTING", actor)
    # Keep the next ingestion invocation eligible to publish its own lease.
    conn.commit()
    current = sum(1 for file in files if file.parent.name == close["month"])
    return IngestReport(close_id, len(files), claims, failures, f"All {current} {close['month']} sources collected.")
