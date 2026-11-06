"""Insert-only, per-close hash-chained audit events."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, is_dataclass
from decimal import Decimal
from typing import Any

from carbon_room.models import Actor, AuditCheck

ZERO_HASH = "0" * 64


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Actor):
        return value.id
    if is_dataclass(value):
        return {key: _json_value(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def canonical(value: Any) -> str:
    """Stable JSON with Decimal values represented as exact text."""
    return json.dumps(_json_value(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def actor_id(actor: Actor | str) -> str:
    return actor.id if isinstance(actor, Actor) else actor


def append_event(
    conn: sqlite3.Connection,
    close_id: str,
    actor: Actor | str,
    kind: str,
    *,
    claim_id: str | None = None,
    before: str | None = None,
    after: str | None = None,
    chat_message_id: str | None = None,
    reason: str = "",
    payload: dict[str, Any] | None = None,
) -> int:
    """Append exactly one event and return its auto-incremented identifier."""
    previous = conn.execute(
        "SELECT hash FROM events WHERE close_id = ? ORDER BY event_id DESC LIMIT 1", (close_id,)
    ).fetchone()
    prev_hash = previous["hash"] if previous else ZERO_HASH
    event = {
        "close_id": close_id,
        "actor": actor_id(actor),
        "kind": kind,
        "claim_id": claim_id,
        "before_status": before,
        "after_status": after,
        "chat_message_id": chat_message_id,
        "timestamp": _timestamp(),
        "reason": reason,
        "payload": payload or {},
        "prev_hash": prev_hash,
    }
    digest = hashlib.sha256((prev_hash + canonical(event)).encode("utf-8")).hexdigest()
    cursor = conn.execute(
        """INSERT INTO events(close_id,actor,kind,claim_id,before_status,after_status,chat_message_id,timestamp,
                              reason,payload,prev_hash,hash) VALUES (:close_id,:actor,:kind,:claim_id,:before_status,
                              :after_status,:chat_message_id,:timestamp,:reason,:payload,:prev_hash,:hash)""",
        {**event, "payload": canonical(event["payload"]), "hash": digest},
    )
    return int(cursor.lastrowid)


def _timestamp() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def verify_audit(conn: sqlite3.Connection, close_id: str) -> AuditCheck:
    """Recompute a close's chain and report the first changed or broken event."""
    previous = ZERO_HASH
    rows = conn.execute("SELECT * FROM events WHERE close_id = ? ORDER BY event_id", (close_id,))
    count = 0
    for row in rows:
        count += 1
        event = {
            "close_id": row["close_id"],
            "actor": row["actor"],
            "kind": row["kind"],
            "claim_id": row["claim_id"],
            "before_status": row["before_status"],
            "after_status": row["after_status"],
            "chat_message_id": row["chat_message_id"],
            "timestamp": row["timestamp"],
            "reason": row["reason"],
            "payload": json.loads(row["payload"]),
            "prev_hash": previous,
        }
        expected = hashlib.sha256((previous + canonical(event)).encode("utf-8")).hexdigest()
        if row["prev_hash"] != previous or row["hash"] != expected:
            return AuditCheck(False, count, int(row["event_id"]))
        previous = row["hash"]
    return AuditCheck(True, count, None)
