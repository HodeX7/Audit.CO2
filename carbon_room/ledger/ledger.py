"""Frozen P1 ledger API used by P2; all quantities remain Decimal-backed text."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from carbon_room.models import (
    Actor, Calculation, Finding, Gap, NeedsRoomEvent, NotAllowed, NotFound, Option, Source,
)
from carbon_room.ledger.audit import actor_id, append_event
from carbon_room.ledger.ids import next_id

_CLAIM_STATUSES = {"VERIFIED", "UNVERIFIED", "CONFLICTING", "STALE"}
_CLOSE_PHASES = {
    "OPEN", "COLLECTING", "CALCULATING", "CHECKING", "AWAITING_HUMANS",
    "RECHECKING", "DRAFTED", "PUBLISHED",
}


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _json(value: Any) -> str:
    return json.dumps(value, default=str, sort_keys=True, separators=(",", ":"))


def _human_message(actor: Actor, message_id: str | None) -> None:
    if actor.kind == "human" and not message_id:
        raise NeedsRoomEvent("human state changes require a Switch chat_message_id")


def _close_or_raise(conn: sqlite3.Connection, close_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM closes WHERE close_id = ?", (close_id,)).fetchone()
    if row is None:
        raise NotFound(f"unknown close: {close_id}")
    return row


def _source(row: sqlite3.Row) -> Source:
    value = dict(row)
    value.pop("ingested_by"); value.pop("ingested_at")
    return Source(**value)


def _claim(row: sqlite3.Row):
    from carbon_room.models import Claim

    value = dict(row)
    value["value"] = Decimal(value["value"])
    value["attributes"] = json.loads(value["attributes"])
    value.pop("created_at")
    return Claim(**value)


def _calc(row: sqlite3.Row) -> Calculation:
    value = dict(row)
    for key in ("activity_value", "factor_value", "kgco2e"):
        value[key] = Decimal(value[key])
    value.pop("created_at"); value.pop("superseded_by")
    return Calculation(**value)


def _gap(row: sqlite3.Row) -> Gap:
    value = dict(row)
    value["claim_ids"] = json.loads(value["claim_ids"])
    value["options"] = [Option(**item) for item in json.loads(value["options"])]
    value["resolution"] = json.loads(value["resolution"]) if value["resolution"] else None
    return Gap(**value)


def create_close(conn, month, sites, factor_set, actor, chat_message_id) -> str:
    _human_message(actor, chat_message_id)
    if len(month) != 7 or month[4] != "-":
        raise ValueError("month must use YYYY-MM")
    version = int(conn.execute("SELECT COALESCE(MAX(version), 0) + 1 FROM closes WHERE month = ?", (month,)).fetchone()[0])
    close_id = f"{month}-v{version}"
    conn.execute(
        "INSERT INTO closes VALUES (?,?,?,?,?,?,?,?,NULL,NULL,NULL)",
        (close_id, month, _json(list(sites)), factor_set, "OPEN", version, actor_id(actor), chat_message_id),
    )
    append_event(conn, close_id, actor, "factor_set_locked", chat_message_id=chat_message_id,
                 payload={"factor_set": factor_set})
    return close_id


def get_close(conn, close_id) -> dict:
    row = _close_or_raise(conn, close_id)
    value = dict(row)
    value["sites"] = json.loads(value["sites"])
    return value


def latest_close(conn) -> str | None:
    row = conn.execute("SELECT close_id FROM closes ORDER BY month DESC, version DESC LIMIT 1").fetchone()
    return row["close_id"] if row else None


def set_phase(conn, close_id, phase, actor) -> None:
    if phase not in _CLOSE_PHASES:
        raise ValueError(f"unknown close phase: {phase!r}")
    if actor.kind == "human":
        raise NotAllowed("only an agent or system actor may change the close phase")
    before = _close_or_raise(conn, close_id)["phase"]
    conn.execute("UPDATE closes SET phase = ? WHERE close_id = ?", (phase, close_id))
    append_event(conn, close_id, actor, "phase_changed", before=before, after=phase)


def add_source(conn, source: Source, actor, chat_message_id: str | None = None) -> str:
    _human_message(actor, chat_message_id)
    _close_or_raise(conn, source.close_id)
    conn.execute(
        """INSERT INTO sources VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (*asdict(source).values(), actor_id(actor), _now()),
    )
    append_event(
        conn, source.close_id, actor, "source_added", chat_message_id=chat_message_id,
        payload={"source_doc_id": source.source_doc_id},
    )
    return source.source_doc_id


def get_sources(conn, close_id, *, site=None) -> list[Source]:
    sql, params = "SELECT * FROM sources WHERE close_id = ?", [close_id]
    if site is not None:
        sql += " AND site = ?"; params.append(site)
    return [_source(row) for row in conn.execute(sql, params)]


def source_for_sha(conn, close_id, sha256) -> Source | None:
    """Return an existing source for a close-local content digest, if present."""
    row = conn.execute(
        "SELECT * FROM sources WHERE close_id = ? AND sha256 = ?", (close_id, sha256)
    ).fetchone()
    return _source(row) if row else None


def add_claim(conn, claim, actor, chat_message_id: str | None = None) -> str:
    _human_message(actor, chat_message_id)
    _close_or_raise(conn, claim.close_id)
    claim_id = claim.claim_id or next_id(conn, "CL")
    values = asdict(claim) | {"claim_id": claim_id, "value": str(claim.value), "status": "UNVERIFIED", "checked_by": None,
                              "attributes": _json(claim.attributes), "created_at": _now()}
    columns = ",".join(values); placeholders = ",".join(f":{key}" for key in values)
    conn.execute(f"INSERT INTO claims ({columns}) VALUES ({placeholders})", values)
    append_event(
        conn, claim.close_id, actor, "claim_added", claim_id=claim_id, after="UNVERIFIED",
        chat_message_id=chat_message_id,
    )
    return claim_id


def get_claim(conn, claim_id):
    row = conn.execute("SELECT * FROM claims WHERE claim_id = ?", (claim_id,)).fetchone()
    if row is None:
        raise NotFound(f"unknown claim: {claim_id}")
    return _claim(row)


def get_claims(conn, close_id, *, site=None, month=None, activity=None, live_only=True):
    sql, params = "SELECT * FROM claims WHERE close_id = ?", [close_id]
    for column, value in (("site", site), ("month", month), ("activity", activity)):
        if value is not None:
            sql += f" AND {column} = ?"; params.append(value)
    if live_only:
        sql += " AND superseded_by IS NULL"
    return [_claim(row) for row in conn.execute(sql, params)]


def set_status(conn, claim_id, new_status, actor, reason, chat_message_id=None) -> None:
    if new_status not in _CLAIM_STATUSES:
        raise ValueError(f"unknown claim status: {new_status!r}; MISSING is a finding or gap kind")
    _human_message(actor, chat_message_id)
    if new_status == "VERIFIED" and not (actor.kind == "system" or actor.id == "watchdog"):
        raise NotAllowed("only the system or watchdog may set VERIFIED")
    claim = get_claim(conn, claim_id)
    conn.execute("UPDATE claims SET status = ?, checked_by = ? WHERE claim_id = ?", (new_status, actor_id(actor), claim_id))
    append_event(conn, claim.close_id, actor, "status_changed", claim_id=claim_id, before=claim.status, after=new_status,
                 chat_message_id=chat_message_id, reason=reason)


def set_factor(conn, claim_id, factor_id, factor_version, actor, reason, chat_message_id=None) -> None:
    _human_message(actor, chat_message_id); claim = get_claim(conn, claim_id)
    conn.execute("UPDATE claims SET factor_id = ?, factor_version = ? WHERE claim_id = ?", (factor_id, factor_version, claim_id))
    append_event(conn, claim.close_id, actor, "factor_set", claim_id=claim_id, chat_message_id=chat_message_id, reason=reason,
                 payload={"factor_id": factor_id, "factor_version": factor_version})


def supersede(conn, old_claim_id, new_claim_id, actor, reason, chat_message_id) -> None:
    _human_message(actor, chat_message_id); old = get_claim(conn, old_claim_id)
    conn.execute("UPDATE claims SET superseded_by = ? WHERE claim_id = ?", (new_claim_id, old_claim_id))
    append_event(conn, old.close_id, actor, "claim_superseded", claim_id=old_claim_id, before=old.status,
                 chat_message_id=chat_message_id, reason=reason, payload={"superseded_by": new_claim_id})


def add_calculation(conn, calc: Calculation) -> str:
    claim = get_claim(conn, calc.claim_id); previous = latest_calculation(conn, calc.claim_id)
    calc_id = calc.calc_id or next_id(conn, "CA")
    values = asdict(calc) | {"calc_id": calc_id, "activity_value": str(calc.activity_value), "factor_value": str(calc.factor_value),
                              "kgco2e": str(calc.kgco2e), "created_at": _now(), "superseded_by": None}
    columns = ",".join(values); placeholders = ",".join(f":{key}" for key in values)
    conn.execute(f"INSERT INTO calculations ({columns}) VALUES ({placeholders})", values)
    if previous:
        conn.execute("UPDATE calculations SET superseded_by = ? WHERE calc_id = ?", (calc_id, previous.calc_id))
    append_event(conn, claim.close_id, "system", "calculation_added", claim_id=calc.claim_id, payload={"calc_id": calc_id})
    return calc_id


def latest_calculation(conn, claim_id):
    row = conn.execute("SELECT * FROM calculations WHERE claim_id = ? AND superseded_by IS NULL ORDER BY created_at DESC, calc_id DESC LIMIT 1", (claim_id,)).fetchone()
    return _calc(row) if row else None


def upsert_gap(conn, close_id, finding: Finding):
    existing = conn.execute("SELECT * FROM gaps WHERE close_id = ? AND finding_id = ?", (close_id, finding.finding_id)).fetchone()
    if existing:
        return _gap(existing)
    count = conn.execute("SELECT COUNT(*) FROM gaps WHERE close_id = ?", (close_id,)).fetchone()[0]
    gap_id = f"G-{count + 1}"
    conn.execute(
        "INSERT INTO gaps VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (gap_id, close_id, finding.finding_id, finding.rule, finding.kind, finding.title, finding.owner, "OPEN",
         _json(finding.claim_ids), _json([asdict(option) for option in finding.options]), None, _now(), None, None, None),
    )
    append_event(conn, close_id, "system", "gap_opened", payload={"gap_id": gap_id, "finding_id": finding.finding_id})
    return get_gap(conn, gap_id, close_id)


def get_gaps(conn, close_id, *, status=None):
    sql, params = "SELECT * FROM gaps WHERE close_id = ?", [close_id]
    if status is not None:
        sql += " AND status = ?"; params.append(status)
    return [_gap(row) for row in conn.execute(sql, params)]


def get_gap(conn, gap_id, close_id):
    row = conn.execute("SELECT * FROM gaps WHERE gap_id = ? AND close_id = ?", (gap_id, close_id)).fetchone()
    if row is None:
        raise NotFound(f"unknown gap: {gap_id}")
    return _gap(row)


def get_gap_by_thread(conn, thread_root_message_id):
    row = conn.execute("SELECT * FROM gaps WHERE thread_root_message_id = ?", (thread_root_message_id,)).fetchone()
    return _gap(row) if row else None


def set_gap_thread(conn, close_id, gap_id, message_id) -> None:
    gap = get_gap(conn, gap_id, close_id)
    if not message_id:
        raise ValueError("gap thread message_id is required")
    if gap.thread_root_message_id is not None:
        return
    existing = get_gap_by_thread(conn, message_id)
    if existing and (existing.close_id != close_id or existing.gap_id != gap_id):
        raise ValueError(f"Switch thread {message_id!r} is already linked to gap {existing.gap_id}")
    conn.execute(
        "UPDATE gaps SET thread_root_message_id = ? WHERE close_id = ? AND gap_id = ?",
        (message_id, close_id, gap_id),
    )
    append_event(
        conn, close_id, "system", "gap_thread_recorded",
        payload={"gap_id": gap_id, "message_id": message_id},
    )


def resolve_gap(conn, close_id, gap_id, actor, chat_message_id, resolution) -> None:
    _human_message(actor, chat_message_id); gap = get_gap(conn, gap_id, close_id)
    if gap.status != "OPEN":
        raise ValueError(f"gap {gap_id} is already resolved")
    conn.execute(
        """UPDATE gaps SET status = 'RESOLVED', resolved_by = ?, resolved_message_id = ?, resolution = ?
           WHERE close_id = ? AND gap_id = ?""",
        (actor_id(actor), chat_message_id, _json(resolution), close_id, gap_id),
    )
    append_event(conn, close_id, actor, "gap_resolved", chat_message_id=chat_message_id, payload={"gap_id": gap_id})


def add_approval(conn, close_id, subject_type, subject_id, tier, actor, decision, reason, chat_message_id) -> str:
    _human_message(actor, chat_message_id)
    if not chat_message_id:
        raise NeedsRoomEvent("approvals require a Switch chat_message_id")
    approval_id = f"AP-{conn.execute('SELECT COUNT(*) FROM approvals').fetchone()[0] + 1:04d}"
    conn.execute("INSERT INTO approvals VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                 (approval_id, close_id, subject_type, subject_id, tier, actor.id, actor.role, decision, reason, chat_message_id, _now()))
    append_event(conn, close_id, actor, "approval_recorded", chat_message_id=chat_message_id, payload={"approval_id": approval_id})
    return approval_id


def get_approvals(conn, close_id, *, subject_id=None):
    sql, params = "SELECT * FROM approvals WHERE close_id = ?", [close_id]
    if subject_id is not None:
        sql += " AND subject_id = ?"; params.append(subject_id)
    return [dict(row) for row in conn.execute(sql, params)]


def load_factors(conn, rows):
    for row in rows:
        conn.execute("""INSERT INTO factors VALUES (:factor_id,:source,:version,:year,:activity,:geography,:value,:unit,:citation)
                     ON CONFLICT(factor_id) DO UPDATE SET source=excluded.source,version=excluded.version,year=excluded.year,
                     activity=excluded.activity,geography=excluded.geography,value=excluded.value,unit=excluded.unit,citation=excluded.citation""",
                     {**row, "value": str(row["value"])})
    return len(rows)


def get_factor(conn, factor_id):
    row = conn.execute("SELECT * FROM factors WHERE factor_id = ?", (factor_id,)).fetchone()
    if row is None:
        raise NotFound(f"unknown factor: {factor_id}")
    return dict(row)


def find_factor(conn, source, version, activity, geography):
    row = conn.execute("SELECT * FROM factors WHERE source=? AND version=? AND activity=? AND geography=?", (source, version, activity, geography)).fetchone()
    return dict(row) if row else None


def assign_s_tags(conn, close_id, version, calc_ids):
    mapping = {}
    used_tags = {
        row["tag"] for row in conn.execute(
            "SELECT tag FROM s_tags WHERE close_id=? AND version=?", (close_id, version)
        )
    }
    next_number = 1
    new_tags = 0
    for calc_id in calc_ids:
        existing = conn.execute("SELECT tag FROM s_tags WHERE close_id=? AND version=? AND calc_id=?", (close_id, version, calc_id)).fetchone()
        if existing:
            mapping[calc_id] = existing["tag"]; continue
        calc = conn.execute(
            """SELECT calculations.claim_id, claims.close_id
               FROM calculations JOIN claims ON claims.claim_id = calculations.claim_id
               WHERE calculations.calc_id = ?""",
            (calc_id,),
        ).fetchone()
        if calc is None:
            raise NotFound(f"unknown calculation: {calc_id}")
        if calc["close_id"] != close_id:
            raise ValueError(f"calculation {calc_id} does not belong to close {close_id}")
        while f"S-{next_number:03d}" in used_tags:
            next_number += 1
        tag = f"S-{next_number:03d}"
        conn.execute("INSERT INTO s_tags VALUES (?,?,?,?,?)", (close_id, version, tag, calc_id, calc["claim_id"]))
        mapping[calc_id] = tag
        used_tags.add(tag)
        next_number += 1
        new_tags += 1
    if new_tags:
        append_event(conn, close_id, "system", "s_tags_assigned", payload={"version": version, "count": new_tags})
    return mapping


def get_s_tag(conn, close_id, tag):
    row = conn.execute("SELECT * FROM s_tags WHERE close_id = ? AND tag = ?", (close_id, tag)).fetchone()
    if row is None:
        raise NotFound(f"unknown source tag: {tag}")
    return dict(row)
