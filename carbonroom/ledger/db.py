"""Ledger access layer (SQLite).

Owner: Ujjwal (Person 1). Used by everyone: Richa's calculator/checker/reporter and
Akshar's agents read and write the ledger only through these helpers (or read-only SQL).

Rules this module enforces (on top of the triggers in contracts/schema.sql):
  * rows are never deleted; corrected evidence supersedes old evidence
  * new activities always start as UNVERIFIED (only the checker verifies)
  * status changes follow ALLOWED_TRANSITIONS and are logged to `events`
  * quantities are Decimal strings, never floats

The full list of public functions is in docs/HANDOFF.md.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Iterator

from carbonroom import config

SCHEMA_VERSION = "1"
GRAPH_VERSION = "1"  # bump when the ledger_nodes / ledger_edges views in contracts/schema.sql change

ACTIVITY_STATUSES = ("UNVERIFIED", "VERIFIED", "FLAGGED", "EXCLUDED", "SUPERSEDED")
# SUPERSEDED is reached only through supersede_activity(), which also sets superseded_by.
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "UNVERIFIED": {"VERIFIED", "FLAGGED", "EXCLUDED"},
    "VERIFIED": {"FLAGGED", "EXCLUDED"},  # VERIFIED -> FLAGGED is the "false done" reopen
    "FLAGGED": {"VERIFIED", "UNVERIFIED", "EXCLUDED"},
    "EXCLUDED": {"UNVERIFIED"},  # a human can un-exclude
    "SUPERSEDED": set(),
}
GAP_KINDS = (
    "missing_doc",
    "conflict",
    "stale_factor",
    "outlier",
    "excerpt_mismatch",
    "unverified_claim",
    "rec_quality",
)
GAP_STATUSES = ("OPEN", "RESOLVED", "ACCEPTED_RISK")
DOC_KINDS = ("utility_bill", "fuel_invoice", "cloud_invoice", "rec_certificate", "other")
JSON_COLUMNS = {
    "aliases_json",
    "meta_json",
    "extra_json",
    "refs_json",
    "detail_json",
    "quality_flags",
}


class LedgerError(Exception):
    """A request that would break a ledger rule (bad transition, unknown id, ...)."""


# ---------------------------------------------------------------------------
# Small utilities
# ---------------------------------------------------------------------------


def dumps(obj: Any) -> str:
    """Stable JSON (sorted keys) so hashes and diffs are reproducible."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def loads(text: str | None, default: Any = None) -> Any:
    if text is None or text == "":
        return default
    return json.loads(text)


def dec(value: Any) -> Decimal:
    """Parse a quantity as Decimal. Accepts Decimal, int, or a numeric string ('191,300' ok)."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        raise LedgerError("floats are not allowed for quantities; pass a string or Decimal")
    try:
        return Decimal(str(value).replace(",", "").strip())
    except InvalidOperation as exc:
        raise LedgerError(f"not a number: {value!r}") from exc


def dec_str(value: Any) -> str:
    """Canonical decimal string without exponent or trailing zeros: 191300, 15080, 499.998."""
    d = dec(value)
    if d < 0:
        raise LedgerError(f"quantities must not be negative: {value!r}")
    text = format(d.normalize(), "f")
    return text


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    """Row -> dict, with *_json columns parsed."""
    if row is None:
        return None
    out: dict[str, Any] = {}
    for key in row.keys():
        value = row[key]
        if key in JSON_COLUMNS:
            parsed = loads(value, default=None)
            out[key.removesuffix("_json") if key.endswith("_json") else key] = parsed
        else:
            out[key] = value
    return out


# ---------------------------------------------------------------------------
# Connection, schema, transactions
# ---------------------------------------------------------------------------


def connect(path: str | Path | None = None, *, create: bool = True) -> sqlite3.Connection:
    """Open the ledger. Creates the file and schema if needed (create=True)."""
    db_file = Path(path) if path else config.db_path()
    if not create and not db_file.exists():
        raise LedgerError(f"ledger not found at {db_file}; run `carbonroom seed` or `carbonroom init`")
    db_file.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_file), timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")  # several agents share one file
    try:
        conn.execute("PRAGMA journal_mode = WAL")
    except sqlite3.DatabaseError:  # pragma: no cover - e.g. read-only media
        pass
    if create:
        init_db(conn)
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create every table/trigger (idempotent), then apply additive migrations."""
    conn.executescript(config.schema_path().read_text(encoding="utf-8"))
    migrate(conn)


def _refresh_graph_views(conn: sqlite3.Connection) -> bool:
    """Recreate the knowledge-graph views if contracts/schema.sql has a newer definition (GRAPH_VERSION)."""
    import re

    row = conn.execute("SELECT value FROM schema_meta WHERE key = 'graph_version'").fetchone()
    if row and row["value"] == GRAPH_VERSION:
        return False
    statements = re.findall(r"CREATE VIEW IF NOT EXISTS (\w+).*?;", config.schema_path().read_text(encoding="utf-8"),
                            flags=re.S)
    with transaction(conn):
        row = conn.execute("SELECT value FROM schema_meta WHERE key = 'graph_version'").fetchone()
        if row and row["value"] == GRAPH_VERSION:
            return False
        text = config.schema_path().read_text(encoding="utf-8")
        for name in reversed(statements):  # ledger_nodes reads ledger_edges, so drop it first
            conn.execute(f"DROP VIEW IF EXISTS {name}")
        for match in re.finditer(r"CREATE VIEW IF NOT EXISTS \w+.*?;", text, flags=re.S):
            conn.execute(match.group(0))
        conn.execute("INSERT INTO schema_meta(key, value) VALUES ('graph_version', ?) "
                     "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (GRAPH_VERSION,))
    return True


# Additive columns added after schema v1 go here as (table, column, DDL type clause).
_ADDITIVE_COLUMNS: list[tuple[str, str, str]] = [
    ("events", "chat_message_id", "TEXT"),
    ("events", "prev_event_hash", "TEXT"),
    ("events", "event_hash", "TEXT"),
]


def migrate(conn: sqlite3.Connection) -> list[str]:
    """Add any additive columns an older database is missing. Never drops anything."""
    applied: list[str] = []
    for table, column, ddl in _ADDITIVE_COLUMNS:
        cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        if column not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
            applied.append(f"{table}.{column}")
    conn.execute(
        "INSERT INTO schema_meta(key, value) VALUES ('schema_version', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (SCHEMA_VERSION,),
    )
    if _refresh_graph_views(conn):
        applied.append(f"graph views v{GRAPH_VERSION}")
    hashed = _backfill_event_chain(conn)
    if hashed:
        applied.append(f"audit chain: hashed {hashed} older event(s)")
    return applied


def _backfill_event_chain(conn: sqlite3.Connection) -> int:
    """Hash events written before the audit chain existed. Fills only empty hash columns, in id order,
    chaining onto the stored hash of the event before; never rewrites an event or an existing hash."""
    if conn.execute("SELECT 1 FROM events WHERE event_hash IS NULL LIMIT 1").fetchone() is None:
        return 0
    guard = conn.execute("SELECT sql FROM sqlite_master WHERE type = 'trigger' AND name = 'events_append_only'"
                         ).fetchone()
    filled = 0
    with transaction(conn):
        if guard:
            conn.execute("DROP TRIGGER events_append_only")  # put back below, in the same transaction
        prev: str | None = None
        for row in conn.execute("SELECT * FROM events ORDER BY id").fetchall():
            if row["event_hash"] is None:
                link = event_hash(prev, row["at"], row["actor"], row["action"], row["ref"], row["chat_message_id"],
                                  row["detail_json"])
                conn.execute("UPDATE events SET prev_event_hash = ?, event_hash = ? WHERE id = ?",
                             (prev, link, row["id"]))
                prev = link
                filled += 1
            else:
                prev = row["event_hash"]
        if guard:
            conn.execute(guard["sql"])
        log_event(conn, "cr-ledger", "audit_chain_backfilled", None, {"events": filled})
    return filled


def reset_db_file(path: str | Path | None = None) -> Path:
    """Remove the ledger file (used only by `carbonroom seed`). No SQL DELETE is ever run."""
    db_file = Path(path) if path else config.db_path()
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(str(db_file) + suffix)
        if candidate.exists():
            candidate.unlink()
    return db_file


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """BEGIN IMMEDIATE ... COMMIT. Joins an outer transaction if one is already open."""
    if conn.in_transaction:
        yield conn
        return
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def event_hash(prev_event_hash: str | None, at: str, actor: str, action: str, ref: str | None,
               chat_message_id: str | None, detail_json: str) -> str:
    """One link of the audit chain. Anyone can recompute it from an exported event row."""
    payload = [prev_event_hash or "", at, actor, action, ref or "", chat_message_id or "", detail_json]
    return sha256_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def log_event(
    conn: sqlite3.Connection,
    actor: str,
    action: str,
    ref: str | None = None,
    detail: dict[str, Any] | None = None,
    *,
    chat_message_id: str | None = None,
) -> int:
    """Append one event to the audit chain. `actor` is who did it: an agent ('cr-collector') or a human;
    `chat_message_id` is the Switch message that caused it (required for human actions, see close rules)."""
    at, detail_json = config.now_iso(), dumps(detail or {})
    with transaction(conn):  # holds the write lock between reading the newest hash and inserting
        row = conn.execute("SELECT event_hash FROM events ORDER BY id DESC LIMIT 1").fetchone()
        prev = row["event_hash"] if row else None
        cur = conn.execute(
            "INSERT INTO events(at, actor, action, ref, detail_json, chat_message_id, prev_event_hash, event_hash) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (at, actor, action, ref, detail_json, chat_message_id, prev,
             event_hash(prev, at, actor, action, ref, chat_message_id, detail_json)),
        )
    return int(cur.lastrowid)


def audit_head(conn: sqlite3.Connection) -> dict | None:
    """The newest event and its hash. Post it in the room at each close step: anyone can later prove
    the log up to that point was not changed (verify_audit_chain + the posted hash)."""
    row = conn.execute("SELECT id, at, actor, action, event_hash FROM events ORDER BY id DESC LIMIT 1").fetchone()
    return dict(row) if row else None


def verify_audit_chain(conn: sqlite3.Connection, *, max_problems: int = 20) -> dict[str, Any]:
    """Recompute every link. Returns {ok, events, head, problems: [{id, problem}]}; the first problem
    is where the log was changed (every link after it breaks too, so only the first few are listed)."""
    problems: list[dict[str, Any]] = []
    prev: str | None = None
    count = 0
    last = None
    broken = 0
    for row in conn.execute("SELECT * FROM events ORDER BY id"):
        count += 1
        last = row
        found = []
        if row["prev_event_hash"] != prev:
            found.append("prev_event_hash does not match the event before")
        expected = event_hash(row["prev_event_hash"], row["at"], row["actor"], row["action"], row["ref"],
                              row["chat_message_id"], row["detail_json"])
        if row["event_hash"] != expected:
            found.append("event_hash does not match the event's content")
        if found:
            broken += 1
            if len(problems) < max_problems:
                problems.append({"id": row["id"], "problem": "; ".join(found)})
        prev = row["event_hash"]
    head = {"id": last["id"], "event_hash": last["event_hash"]} if last is not None else None
    return {"ok": broken == 0, "events": count, "broken": broken, "head": head, "problems": problems}


def list_events(conn: sqlite3.Connection, *, limit: int = 50, ref: str | None = None) -> list[dict]:
    if ref:
        rows = conn.execute(
            "SELECT * FROM events WHERE ref = ? ORDER BY id DESC LIMIT ?", (ref, limit)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [row_to_dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Sites, periods, expected documents
# ---------------------------------------------------------------------------


def upsert_site(
    conn: sqlite3.Connection,
    *,
    id: str,
    name: str,
    region: str | None = None,
    grid_subregion: str | None = None,
    owner_handle: str | None = None,
    room: str | None = None,
    kind: str = "facility",
    aliases: Iterable[str] = (),
    actor: str = "system",
) -> dict:
    alias_list = sorted({a.strip() for a in [name, *aliases] if a and a.strip()})
    with transaction(conn):
        conn.execute(
            """INSERT INTO sites(id, name, region, grid_subregion, owner_handle, room, kind, aliases_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET name=excluded.name, region=excluded.region,
                 grid_subregion=excluded.grid_subregion, owner_handle=excluded.owner_handle,
                 room=excluded.room, kind=excluded.kind, aliases_json=excluded.aliases_json""",
            (id, name, region, grid_subregion, owner_handle, room, kind, dumps(alias_list)),
        )
        log_event(conn, actor, "site_upserted", id, {"owner": owner_handle, "room": room})
    return get_site(conn, id)


def get_site(conn: sqlite3.Connection, site_id: str) -> dict | None:
    return row_to_dict(conn.execute("SELECT * FROM sites WHERE id = ?", (site_id,)).fetchone())


def list_sites(conn: sqlite3.Connection) -> list[dict]:
    return [row_to_dict(r) for r in conn.execute("SELECT * FROM sites ORDER BY id")]


def _norm(text: str) -> str:
    return " ".join(text.split()).casefold()


def match_sites(conn: sqlite3.Connection, text: str) -> list[str]:
    """Site ids whose name or alias appears in `text` (case/whitespace-insensitive)."""
    hay = _norm(text)
    found = []
    for site in list_sites(conn):
        if any(_norm(alias) in hay for alias in site["aliases"] or [site["name"]]):
            found.append(site["id"])
    return found


def ensure_period(
    conn: sqlite3.Connection,
    period_id: str,
    *,
    factor_set_version: str | None = None,
    actor: str = "system",
) -> dict:
    with transaction(conn):
        existing = conn.execute("SELECT * FROM periods WHERE id = ?", (period_id,)).fetchone()
        if existing is None:
            conn.execute(
                "INSERT INTO periods(id, status, factor_set_version) VALUES (?, 'OPEN', ?)",
                (period_id, factor_set_version),
            )
            log_event(conn, actor, "period_opened", period_id, {"factor_set": factor_set_version})
    return get_period(conn, period_id)


def get_period(conn: sqlite3.Connection, period_id: str) -> dict | None:
    return row_to_dict(conn.execute("SELECT * FROM periods WHERE id = ?", (period_id,)).fetchone())


def list_periods(conn: sqlite3.Connection) -> list[dict]:
    return [row_to_dict(r) for r in conn.execute("SELECT * FROM periods ORDER BY id")]


def set_period_factor_set(conn: sqlite3.Connection, period_id: str, version: str, *, actor: str) -> dict:
    with transaction(conn):
        period = get_period(conn, period_id)
        if period is None:
            raise LedgerError(f"unknown period {period_id}")
        if period["status"] == "CLOSED":
            raise LedgerError(f"period {period_id} is CLOSED; its factor set is locked")
        conn.execute("UPDATE periods SET factor_set_version = ? WHERE id = ?", (version, period_id))
        log_event(conn, actor, "period_factor_set", period_id, {"from": period["factor_set_version"], "to": version})
    return get_period(conn, period_id)


def close_period(conn: sqlite3.Connection, period_id: str, *, approved_by: str, actor: str) -> dict:
    """Mark a period CLOSED. The database refuses unless `approved_by` recorded an APPROVE."""
    with transaction(conn):
        period = get_period(conn, period_id)
        if period is None:
            raise LedgerError(f"unknown period {period_id}")
        if period["status"] == "CLOSED":
            raise LedgerError(f"period {period_id} is already CLOSED")
        try:
            conn.execute(
                "UPDATE periods SET status='CLOSED', approved_by=?, closed_at=? WHERE id=?",
                (approved_by, config.now_iso(), period_id),
            )
        except sqlite3.IntegrityError as exc:
            raise LedgerError(str(exc)) from exc
        log_event(conn, actor, "period_closed", period_id, {"approved_by": approved_by})
    return get_period(conn, period_id)


def upsert_expected_document(
    conn: sqlite3.Connection,
    *,
    site_id: str,
    category: str,
    doc_kind: str,
    frequency: str = "monthly",
    owner_handle: str | None = None,
    note: str | None = None,
    actor: str = "system",
) -> dict:
    exp_id = f"EXP-{site_id}-{category}"
    with transaction(conn):
        conn.execute(
            """INSERT INTO expected_documents(id, site_id, category, doc_kind, frequency, owner_handle, note)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET doc_kind=excluded.doc_kind, frequency=excluded.frequency,
                 owner_handle=excluded.owner_handle, note=excluded.note""",
            (exp_id, site_id, category, doc_kind, frequency, owner_handle, note),
        )
        log_event(conn, actor, "expected_document_upserted", exp_id, {"frequency": frequency})
    return row_to_dict(conn.execute("SELECT * FROM expected_documents WHERE id=?", (exp_id,)).fetchone())


def list_expected_documents(conn: sqlite3.Connection, site_id: str | None = None) -> list[dict]:
    if site_id:
        rows = conn.execute("SELECT * FROM expected_documents WHERE site_id=? ORDER BY id", (site_id,))
    else:
        rows = conn.execute("SELECT * FROM expected_documents ORDER BY id")
    return [row_to_dict(r) for r in rows]


def expected_but_missing(conn: sqlite3.Connection, period_id: str) -> list[dict]:
    """Monthly evidence that has no live (non-superseded) activity for `period_id`.

    Read-only helper for the checker; it does not open gaps itself.
    """
    missing = []
    for exp in list_expected_documents(conn):
        if exp["frequency"] != "monthly":
            continue
        row = conn.execute(
            """SELECT 1 FROM activities WHERE site_id=? AND period_id=? AND category=?
               AND status != 'SUPERSEDED' LIMIT 1""",
            (exp["site_id"], period_id, exp["category"]),
        ).fetchone()
        if row is None:
            site = get_site(conn, exp["site_id"]) or {}
            missing.append(
                {
                    "site_id": exp["site_id"],
                    "site_name": site.get("name"),
                    "category": exp["category"],
                    "doc_kind": exp["doc_kind"],
                    "period_id": period_id,
                    "owner_handle": exp["owner_handle"] or site.get("owner_handle"),
                    "room": site.get("room"),
                }
            )
    return missing


# ---------------------------------------------------------------------------
# Source documents
# ---------------------------------------------------------------------------


def make_doc_id(sha256: str) -> str:
    return f"DOC-{sha256[:12]}"


def add_source_doc(
    conn: sqlite3.Connection,
    *,
    sha256: str,
    path: str,
    kind: str,
    received_from: str | None,
    room: str | None,
    original_name: str | None = None,
    doc_ref: str | None = None,
    page_count: int | None = None,
    meta: dict[str, Any] | None = None,
    actor: str = "cr-collector",
) -> tuple[dict, bool]:
    """Insert a document. Returns (row, created). A known sha256 returns the existing row."""
    if kind not in DOC_KINDS:
        raise LedgerError(f"unknown document kind {kind!r}")
    with transaction(conn):
        existing = get_source_doc_by_sha(conn, sha256)
        if existing:
            return existing, False
        doc_id = make_doc_id(sha256)
        conn.execute(
            """INSERT INTO source_docs(id, path, kind, sha256, received_from, room, received_at,
                                       original_name, doc_ref, page_count, meta_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                doc_id,
                path,
                kind,
                sha256,
                received_from,
                room,
                config.now_iso(),
                original_name,
                doc_ref,
                page_count,
                dumps(meta or {}),
            ),
        )
        log_event(conn, actor, "source_doc_added", doc_id, {"sha256": sha256, "kind": kind, "path": path})
    return get_source_doc(conn, doc_id), True


def get_source_doc(conn: sqlite3.Connection, doc_id: str) -> dict | None:
    return row_to_dict(conn.execute("SELECT * FROM source_docs WHERE id = ?", (doc_id,)).fetchone())


def get_source_doc_by_sha(conn: sqlite3.Connection, sha256: str) -> dict | None:
    return row_to_dict(conn.execute("SELECT * FROM source_docs WHERE sha256 = ?", (sha256,)).fetchone())


def find_source_docs_by_ref(conn: sqlite3.Connection, doc_ref: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM source_docs WHERE upper(doc_ref) = upper(?) ORDER BY received_at, id", (doc_ref,)
    )
    return [row_to_dict(r) for r in rows]


def list_source_docs(conn: sqlite3.Connection) -> list[dict]:
    return [row_to_dict(r) for r in conn.execute("SELECT * FROM source_docs ORDER BY received_at, id")]


def update_source_doc_ref(conn: sqlite3.Connection, doc_id: str, doc_ref: str, *, actor: str) -> None:
    """Record the printed document number once extraction has verified it."""
    with transaction(conn):
        conn.execute("UPDATE source_docs SET doc_ref = ? WHERE id = ? AND doc_ref IS NULL", (doc_ref, doc_id))
        log_event(conn, actor, "source_doc_ref", doc_id, {"doc_ref": doc_ref})


def mark_doc_superseded(
    conn: sqlite3.Connection, old_doc_id: str, new_doc_id: str, *, actor: str, reason: str
) -> None:
    """The old document stays; it now points to the corrected one."""
    with transaction(conn):
        old = get_source_doc(conn, old_doc_id)
        if old is None or get_source_doc(conn, new_doc_id) is None:
            raise LedgerError("unknown document id")
        if old_doc_id == new_doc_id:
            raise LedgerError("a document cannot supersede itself")
        if old["superseded_by"] == new_doc_id:
            return
        if old["superseded_by"] is not None:
            raise LedgerError(f"{old_doc_id} is already superseded by {old['superseded_by']}")
        conn.execute("UPDATE source_docs SET superseded_by = ? WHERE id = ?", (new_doc_id, old_doc_id))
        log_event(conn, actor, "source_doc_superseded", old_doc_id, {"by": new_doc_id, "reason": reason})


def current_doc(conn: sqlite3.Connection, doc_id: str) -> dict | None:
    """Follow superseded_by to the latest version of a document."""
    seen = set()
    doc = get_source_doc(conn, doc_id)
    while doc and doc["superseded_by"] and doc["id"] not in seen:
        seen.add(doc["id"])
        doc = get_source_doc(conn, doc["superseded_by"])
    return doc


# ---------------------------------------------------------------------------
# Activities
# ---------------------------------------------------------------------------


def make_activity_id(doc_sha256: str, category: str, excerpt_sha256: str) -> str:
    return "ACT-" + sha256_text(f"{doc_sha256}|{category}|{excerpt_sha256}")[:10]


def add_activity(
    conn: sqlite3.Connection,
    *,
    site_id: str,
    period_id: str,
    category: str,
    quantity: Any,
    unit: str,
    source_doc_id: str,
    excerpt: str,
    excerpt_locator: str,
    excerpt_sha256: str,
    created_by: str,
    extra: dict[str, Any] | None = None,
    activity_id: str | None = None,
) -> tuple[dict, bool]:
    """Insert one claim as UNVERIFIED. Returns (row, created); an existing id is left untouched."""
    doc = get_source_doc(conn, source_doc_id)
    if doc is None:
        raise LedgerError(f"unknown source document {source_doc_id}")
    act_id = activity_id or make_activity_id(doc["sha256"], category, excerpt_sha256)
    with transaction(conn):
        existing = get_activity(conn, act_id)
        if existing:
            return existing, False
        ensure_period(conn, period_id, factor_set_version=config.factor_set(), actor=created_by)
        now = config.now_iso()
        conn.execute(
            """INSERT INTO activities(id, site_id, period_id, category, quantity, unit, source_doc_id,
                    excerpt, excerpt_locator, excerpt_sha256, status, created_by, updated_at,
                    extra_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'UNVERIFIED', ?, ?, ?, ?)""",
            (
                act_id,
                site_id,
                period_id,
                category,
                dec_str(quantity),
                unit,
                source_doc_id,
                excerpt,
                excerpt_locator,
                excerpt_sha256,
                created_by,
                now,
                dumps(extra or {}),
                now,
            ),
        )
        log_event(
            conn,
            created_by,
            "activity_added",
            act_id,
            {"site": site_id, "period": period_id, "category": category, "quantity": dec_str(quantity),
             "unit": unit, "doc": source_doc_id},
        )
    return get_activity(conn, act_id), True


def get_activity(conn: sqlite3.Connection, activity_id: str) -> dict | None:
    return row_to_dict(conn.execute("SELECT * FROM activities WHERE id = ?", (activity_id,)).fetchone())


def list_activities(
    conn: sqlite3.Connection,
    *,
    period_id: str | None = None,
    site_id: str | None = None,
    category: str | None = None,
    status: str | Iterable[str] | None = None,
    include_superseded: bool = True,
    source_doc_id: str | None = None,
) -> list[dict]:
    sql = "SELECT * FROM activities WHERE 1=1"
    args: list[Any] = []
    if period_id:
        sql += " AND period_id = ?"
        args.append(period_id)
    if site_id:
        sql += " AND site_id = ?"
        args.append(site_id)
    if category:
        sql += " AND category = ?"
        args.append(category)
    if source_doc_id:
        sql += " AND source_doc_id = ?"
        args.append(source_doc_id)
    if status:
        statuses = [status] if isinstance(status, str) else list(status)
        sql += f" AND status IN ({','.join('?' * len(statuses))})"
        args.extend(statuses)
    if not include_superseded:
        sql += " AND status != 'SUPERSEDED'"
    sql += " ORDER BY period_id, site_id, category, created_at, id"
    return [row_to_dict(r) for r in conn.execute(sql, args)]


def activity_quantity(activity: dict) -> Decimal:
    return Decimal(activity["quantity"])


def set_activity_status(
    conn: sqlite3.Connection, activity_id: str, new_status: str, *, actor: str, reason: str | None = None
) -> dict:
    """Move an activity along ALLOWED_TRANSITIONS. EXCLUDED and FLAGGED need a reason."""
    if new_status not in ACTIVITY_STATUSES:
        raise LedgerError(f"unknown status {new_status!r}")
    if new_status == "SUPERSEDED":
        raise LedgerError("use supersede_activity() so superseded_by is recorded")
    if new_status in ("EXCLUDED", "FLAGGED") and not (reason and reason.strip()):
        raise LedgerError(f"{new_status} needs a reason")
    with transaction(conn):
        act = get_activity(conn, activity_id)
        if act is None:
            raise LedgerError(f"unknown activity {activity_id}")
        old = act["status"]
        if old == new_status:
            return act
        if new_status not in ALLOWED_TRANSITIONS[old]:
            raise LedgerError(f"{activity_id}: {old} -> {new_status} is not allowed")
        conn.execute(
            "UPDATE activities SET status=?, status_reason=?, updated_at=? WHERE id=?",
            (new_status, reason, config.now_iso(), activity_id),
        )
        log_event(conn, actor, "activity_status", activity_id, {"from": old, "to": new_status, "reason": reason})
    return get_activity(conn, activity_id)


def supersede_activity(
    conn: sqlite3.Connection, old_id: str, new_id: str, *, actor: str, reason: str
) -> dict:
    """Old row -> SUPERSEDED, pointing at the new row. Both rows stay in the ledger."""
    if not (reason and reason.strip()):
        raise LedgerError("superseding needs a reason")
    with transaction(conn):
        old = get_activity(conn, old_id)
        new = get_activity(conn, new_id)
        if old is None or new is None:
            raise LedgerError("unknown activity id")
        if old_id == new_id:
            raise LedgerError("an activity cannot supersede itself")
        if new["status"] == "SUPERSEDED":
            raise LedgerError(f"{new_id} is itself superseded")
        if (old["site_id"], old["category"]) != (new["site_id"], new["category"]):
            raise LedgerError("only a claim about the same site and category can supersede another")
        conn.execute(
            "UPDATE activities SET status='SUPERSEDED', superseded_by=?, status_reason=?, updated_at=? WHERE id=?",
            (new_id, reason, config.now_iso(), old_id),
        )
        log_event(conn, actor, "activity_superseded", old_id, {"by": new_id, "from": old["status"], "reason": reason})
    return get_activity(conn, old_id)


def add_activity_note(conn: sqlite3.Connection, activity_id: str, key: str, value: Any, *, actor: str) -> dict:
    """Attach a note under extra_json['notes'][key] (never touches the evidence fields)."""
    with transaction(conn):
        act = get_activity(conn, activity_id)
        if act is None:
            raise LedgerError(f"unknown activity {activity_id}")
        extra = act["extra"] or {}
        extra.setdefault("notes", {})[key] = value
        conn.execute(
            "UPDATE activities SET extra_json=?, updated_at=? WHERE id=?",
            (dumps(extra), config.now_iso(), activity_id),
        )
        log_event(conn, actor, "activity_note", activity_id, {"key": key})
    return get_activity(conn, activity_id)


# ---------------------------------------------------------------------------
# Instruments (RECs / PPAs)
# ---------------------------------------------------------------------------


def make_instrument_id(doc_sha256: str, certificate_id: str | None, excerpt_sha256: str) -> str:
    return "INS-" + sha256_text(f"{doc_sha256}|{certificate_id}|{excerpt_sha256}")[:10]


def add_instrument(
    conn: sqlite3.Connection,
    *,
    period_id: str,
    kind: str,
    mwh: Any,
    source_doc_id: str,
    created_by: str,
    region: str | None = None,
    vintage: str | None = None,
    site_id: str | None = None,
    certificate_id: str | None = None,
    excerpt: str | None = None,
    excerpt_locator: str | None = None,
    excerpt_sha256: str | None = None,
    extra: dict[str, Any] | None = None,
) -> tuple[dict, bool]:
    doc = get_source_doc(conn, source_doc_id)
    if doc is None:
        raise LedgerError(f"unknown source document {source_doc_id}")
    ins_id = make_instrument_id(doc["sha256"], certificate_id, excerpt_sha256 or "")
    with transaction(conn):
        existing = get_instrument(conn, ins_id)
        if existing:
            return existing, False
        ensure_period(conn, period_id, factor_set_version=config.factor_set(), actor=created_by)
        conn.execute(
            """INSERT INTO instruments(id, period_id, kind, mwh, region, vintage, source_doc_id,
                    quality_flags, site_id, certificate_id, excerpt, excerpt_locator, excerpt_sha256,
                    status, extra_json, created_by, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, '[]', ?, ?, ?, ?, ?, 'UNVERIFIED', ?, ?, ?)""",
            (
                ins_id,
                period_id,
                kind,
                dec_str(mwh),
                region,
                vintage,
                source_doc_id,
                site_id,
                certificate_id,
                excerpt,
                excerpt_locator,
                excerpt_sha256,
                dumps(extra or {}),
                created_by,
                config.now_iso(),
            ),
        )
        log_event(
            conn,
            created_by,
            "instrument_added",
            ins_id,
            {"kind": kind, "mwh": dec_str(mwh), "region": region, "vintage": vintage, "doc": source_doc_id},
        )
    return get_instrument(conn, ins_id), True


def get_instrument(conn: sqlite3.Connection, instrument_id: str) -> dict | None:
    return row_to_dict(conn.execute("SELECT * FROM instruments WHERE id = ?", (instrument_id,)).fetchone())


def list_instruments(
    conn: sqlite3.Connection, *, period_id: str | None = None, include_superseded: bool = True
) -> list[dict]:
    sql = "SELECT * FROM instruments WHERE 1=1"
    args: list[Any] = []
    if period_id:
        sql += " AND period_id = ?"
        args.append(period_id)
    if not include_superseded:
        sql += " AND status != 'SUPERSEDED'"
    sql += " ORDER BY period_id, id"
    return [row_to_dict(r) for r in conn.execute(sql, args)]


def set_instrument_quality_flags(
    conn: sqlite3.Connection, instrument_id: str, flags: list[str], *, actor: str
) -> dict:
    with transaction(conn):
        ins = get_instrument(conn, instrument_id)
        if ins is None:
            raise LedgerError(f"unknown instrument {instrument_id}")
        conn.execute(
            "UPDATE instruments SET quality_flags=?, updated_at=? WHERE id=?",
            (dumps(sorted(set(flags))), config.now_iso(), instrument_id),
        )
        log_event(conn, actor, "instrument_quality_flags", instrument_id, {"flags": sorted(set(flags))})
    return get_instrument(conn, instrument_id)


def set_instrument_status(
    conn: sqlite3.Connection, instrument_id: str, new_status: str, *, actor: str, reason: str | None = None
) -> dict:
    if new_status not in ACTIVITY_STATUSES or new_status == "SUPERSEDED":
        raise LedgerError(f"bad instrument status {new_status!r}")
    if new_status in ("EXCLUDED", "FLAGGED") and not (reason and reason.strip()):
        raise LedgerError(f"{new_status} needs a reason")
    with transaction(conn):
        ins = get_instrument(conn, instrument_id)
        if ins is None:
            raise LedgerError(f"unknown instrument {instrument_id}")
        old = ins["status"]
        if old == new_status:
            return ins
        if new_status not in ALLOWED_TRANSITIONS[old]:
            raise LedgerError(f"{instrument_id}: {old} -> {new_status} is not allowed")
        conn.execute(
            "UPDATE instruments SET status=?, updated_at=? WHERE id=?", (new_status, config.now_iso(), instrument_id)
        )
        log_event(conn, actor, "instrument_status", instrument_id, {"from": old, "to": new_status, "reason": reason})
    return get_instrument(conn, instrument_id)


# ---------------------------------------------------------------------------
# Gaps
# ---------------------------------------------------------------------------


def _next_gap_id(conn: sqlite3.Connection) -> str:
    row = conn.execute(
        "SELECT MAX(CAST(substr(id, 5) AS INTEGER)) AS n FROM gaps WHERE id GLOB 'GAP-[0-9]*'"
    ).fetchone()
    return f"GAP-{(row['n'] or 0) + 1:03d}"


def create_gap(
    conn: sqlite3.Connection,
    *,
    kind: str,
    detail: str,
    created_by: str,
    period_id: str | None = None,
    site_id: str | None = None,
    owner_handle: str | None = None,
    room: str | None = None,
    dedupe_key: str | None = None,
    refs: dict[str, Any] | None = None,
) -> tuple[dict, bool]:
    """Open a gap (GAP-###). With a dedupe_key, the same problem is never opened twice.

    owner_handle and room default to the site's owner and room.
    Returns (row, created).
    """
    if kind not in GAP_KINDS:
        raise LedgerError(f"unknown gap kind {kind!r}")
    with transaction(conn):
        if dedupe_key:
            existing = conn.execute("SELECT * FROM gaps WHERE dedupe_key = ?", (dedupe_key,)).fetchone()
            if existing:
                return row_to_dict(existing), False
        if period_id:
            ensure_period(conn, period_id, factor_set_version=config.factor_set(), actor=created_by)
        site = get_site(conn, site_id) if site_id else None
        owner = owner_handle or (site or {}).get("owner_handle")
        gap_room = room or (site or {}).get("room")
        gap_id = _next_gap_id(conn)
        conn.execute(
            """INSERT INTO gaps(id, period_id, site_id, kind, detail, owner_handle, room, status,
                                created_at, created_by, dedupe_key, refs_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, ?, ?, ?)""",
            (gap_id, period_id, site_id, kind, detail, owner, gap_room, config.now_iso(), created_by,
             dedupe_key, dumps(refs or {})),
        )
        log_event(conn, created_by, "gap_opened", gap_id, {"kind": kind, "owner": owner, "room": gap_room})
    return get_gap(conn, gap_id), True


def get_gap(conn: sqlite3.Connection, gap_id: str) -> dict | None:
    return row_to_dict(conn.execute("SELECT * FROM gaps WHERE id = ?", (gap_id,)).fetchone())


def list_gaps(
    conn: sqlite3.Connection,
    *,
    period_id: str | None = None,
    status: str | None = None,
    site_id: str | None = None,
    kind: str | None = None,
) -> list[dict]:
    sql = "SELECT * FROM gaps WHERE 1=1"
    args: list[Any] = []
    for col, val in (("period_id", period_id), ("status", status), ("site_id", site_id), ("kind", kind)):
        if val:
            sql += f" AND {col} = ?"
            args.append(val)
    sql += " ORDER BY id"
    return [row_to_dict(r) for r in conn.execute(sql, args)]


def set_gap_thread(
    conn: sqlite3.Connection, gap_id: str, thread_id: str, *, actor: str, room: str | None = None
) -> dict:
    """Record the chat thread a gap was posted in (Akshar's agents call this)."""
    with transaction(conn):
        gap = get_gap(conn, gap_id)
        if gap is None:
            raise LedgerError(f"unknown gap {gap_id}")
        conn.execute(
            "UPDATE gaps SET thread_id = ?, room = COALESCE(?, room) WHERE id = ?", (thread_id, room, gap_id)
        )
        log_event(conn, actor, "gap_thread", gap_id, {"thread_id": thread_id, "room": room})
    return get_gap(conn, gap_id)


def resolve_gap(
    conn: sqlite3.Connection,
    gap_id: str,
    *,
    resolution: str,
    resolved_by: str,
    status: str = "RESOLVED",
    actor: str | None = None,
) -> dict:
    """Close a gap. Needs the human who resolved it and their words. Never automatic."""
    if status not in ("RESOLVED", "ACCEPTED_RISK"):
        raise LedgerError("status must be RESOLVED or ACCEPTED_RISK")
    if not (resolution and resolution.strip()) or not (resolved_by and resolved_by.strip()):
        raise LedgerError("a resolution and the resolving human's handle are required")
    with transaction(conn):
        gap = get_gap(conn, gap_id)
        if gap is None:
            raise LedgerError(f"unknown gap {gap_id}")
        if gap["status"] != "OPEN":
            raise LedgerError(f"{gap_id} is already {gap['status']}")
        conn.execute(
            "UPDATE gaps SET status=?, resolution=?, resolved_by=?, resolved_at=? WHERE id=?",
            (status, resolution, resolved_by, config.now_iso(), gap_id),
        )
        log_event(conn, actor or resolved_by, "gap_resolved", gap_id,
                  {"status": status, "resolved_by": resolved_by, "resolution": resolution})
    return get_gap(conn, gap_id)


# ---------------------------------------------------------------------------
# Approvals
# ---------------------------------------------------------------------------


def record_approval(
    conn: sqlite3.Connection,
    *,
    period_id: str,
    approver_handle: str,
    decision: str,
    note: str | None = None,
    report_sha256: str | None = None,
    actor: str | None = None,
) -> dict:
    """Append a human decision. Checking that the handle is THE approver is the caller's job."""
    if decision not in ("APPROVE", "REJECT"):
        raise LedgerError("decision must be APPROVE or REJECT")
    with transaction(conn):
        if get_period(conn, period_id) is None:
            raise LedgerError(f"unknown period {period_id}")
        n = conn.execute("SELECT COUNT(*) AS n FROM approvals WHERE period_id=?", (period_id,)).fetchone()["n"]
        apr_id = f"APR-{period_id}-{n + 1}"
        conn.execute(
            "INSERT INTO approvals(id, period_id, approver_handle, decision, note, report_sha256, at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (apr_id, period_id, approver_handle, decision, note, report_sha256, config.now_iso()),
        )
        log_event(conn, actor or approver_handle, "approval_recorded", apr_id,
                  {"decision": decision, "report_sha256": report_sha256})
    return row_to_dict(conn.execute("SELECT * FROM approvals WHERE id=?", (apr_id,)).fetchone())


def list_approvals(conn: sqlite3.Connection, period_id: str) -> list[dict]:
    rows = conn.execute("SELECT * FROM approvals WHERE period_id=? ORDER BY at, id", (period_id,))
    return [row_to_dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Emission factors and calculations (thin helpers; the logic is Richa's)
# ---------------------------------------------------------------------------


def add_emission_factor(conn: sqlite3.Connection, *, actor: str = "cr-calc", **row: Any) -> dict:
    cols = ("id", "set_version", "category", "region", "scope", "factor", "unit",
            "source_name", "source_edition", "valid_from", "valid_to")
    values = {c: row.get(c) for c in cols}
    values["factor"] = dec_str(values["factor"])
    with transaction(conn):
        conn.execute(
            f"INSERT OR IGNORE INTO emission_factors({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
            [values[c] for c in cols],
        )
        log_event(conn, actor, "emission_factor_added", values["id"], {"set": values["set_version"]})
    return row_to_dict(conn.execute("SELECT * FROM emission_factors WHERE id=?", (values["id"],)).fetchone())


def list_emission_factors(conn: sqlite3.Connection, set_version: str | None = None) -> list[dict]:
    if set_version:
        rows = conn.execute("SELECT * FROM emission_factors WHERE set_version=? ORDER BY id", (set_version,))
    else:
        rows = conn.execute("SELECT * FROM emission_factors ORDER BY set_version, id")
    return [row_to_dict(r) for r in rows]


def add_calculation(
    conn: sqlite3.Connection,
    *,
    activity_id: str,
    factor_id: str,
    scope: str,
    co2e_kg: Any,
    code_version: str,
    actor: str = "cr-calc",
    calc_id: str | None = None,
) -> dict:
    computed_at = config.now_iso()
    cid = calc_id or "CALC-" + sha256_text(f"{activity_id}|{factor_id}|{scope}|{code_version}|{computed_at}")[:12]
    with transaction(conn):
        conn.execute(
            "INSERT INTO calculations(id, activity_id, factor_id, scope, co2e_kg, computed_at, code_version) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (cid, activity_id, factor_id, scope, dec_str(co2e_kg), computed_at, code_version),
        )
        log_event(conn, actor, "calculation_added", cid, {"activity": activity_id, "scope": scope})
    return row_to_dict(conn.execute("SELECT * FROM calculations WHERE id=?", (cid,)).fetchone())


def list_calculations(
    conn: sqlite3.Connection, *, activity_id: str | None = None, period_id: str | None = None
) -> list[dict]:
    sql = "SELECT c.* FROM calculations c JOIN activities a ON a.id = c.activity_id WHERE 1=1"
    args: list[Any] = []
    if activity_id:
        sql += " AND c.activity_id = ?"
        args.append(activity_id)
    if period_id:
        sql += " AND a.period_id = ?"
        args.append(period_id)
    sql += " ORDER BY c.computed_at, c.id"
    return [row_to_dict(r) for r in conn.execute(sql, args)]


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def export_period(conn: sqlite3.Connection, period_id: str) -> dict[str, Any]:
    """Everything the ledger knows about one period, as plain JSON-able data."""
    period = get_period(conn, period_id)
    if period is None:
        raise LedgerError(f"unknown period {period_id}")
    activities = list_activities(conn, period_id=period_id)
    instruments = list_instruments(conn, period_id=period_id)
    doc_ids = sorted({a["source_doc_id"] for a in activities} | {i["source_doc_id"] for i in instruments})
    docs = {d: get_source_doc(conn, d) for d in doc_ids}
    for act in activities:
        doc = docs[act["source_doc_id"]]
        act["source_doc"] = {
            "id": doc["id"],
            "path": doc["path"],
            "sha256": doc["sha256"],
            "doc_ref": doc["doc_ref"],
            "superseded_by": doc["superseded_by"],
        }
    counts: dict[str, int] = {}
    for act in activities:
        counts[act["status"]] = counts.get(act["status"], 0) + 1
    return {
        "type": "cr.ledger.v1",
        "period": period_id,
        "period_info": period,
        "exported_at": config.now_iso(),
        "sites": list_sites(conn),
        "expected_documents": list_expected_documents(conn),
        "expected_but_missing": expected_but_missing(conn, period_id),
        "source_docs": [docs[d] for d in doc_ids],
        "activities": activities,
        "instruments": instruments,
        "gaps": list_gaps(conn, period_id=period_id),
        "approvals": list_approvals(conn, period_id),
        "counts": {"activities_by_status": counts, "gaps_open": sum(
            1 for g in list_gaps(conn, period_id=period_id) if g["status"] == "OPEN")},
    }
