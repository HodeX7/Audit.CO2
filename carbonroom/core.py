"""The core API seam (architecture section 03): the functions the room calls. Signatures are frozen.

    start_close(month, sites, factor_set, actor, chat_message_id) -> close_id      P1  (here)
    ingest(close_id) -> IngestReport          claims created, all UNVERIFIED      P1  (here, via @collector)
    calculate(close_id) -> list[Calculation]                                      P2
    check(close_id) -> list[Finding]          Watchdog; idempotent                P2
    resolve(gap_id, action, actor, chat_message_id, payload) -> list[Finding]     P2
    summary(close_id) -> CloseSummary                                             P2
    draft_report(close_id) -> Report                                              P2
    publish(close_id, actor, chat_message_id) -> PublishedReport                  P2 (+ the ledger's publish gate)
    trace(tag) -> SourceTag                   S-### to file, page, excerpt, SHA   P2
    verify_audit(close_id) -> AuditCheck                                          P1  (here)

P2 functions are implemented in Richa's modules and registered with `@core.implements("calculate")`; core imports
CORE_PLUGIN_MODULES on first use, so nobody edits this file to plug in. Until a function is registered, calling it
raises NotImplementedError naming its owner (P3 can test against a fake core meanwhile).

Every wrapper here also keeps the close's phase in the ledger (OPEN -> COLLECTING -> CALCULATING -> CHECKING ->
AWAITING_HUMANS <-> RECHECKING -> DRAFTED -> PUBLISHED): a step moves the phase only when the move is allowed
from where the close is, so a resumed orchestrator can repeat steps safely. Results are plain JSON-ready dicts.

Every function accepts `conn=` (an open ledger connection); without it, it opens and closes its own.
"""

from __future__ import annotations

import importlib
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator

from carbonroom import config
from carbonroom.ledger import db

ORCHESTRATOR = "cr-carbon-room"
P2_FUNCTIONS = ("calculate", "check", "resolve", "summary", "draft_report", "publish", "trace")
CORE_PLUGIN_MODULES = ("carbonroom.calc.core", "carbonroom.check.core", "carbonroom.report.core")

_IMPLS: dict[str, Callable[..., Any]] = {}
_PLUGINS_LOADED = False


def implements(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Register the implementation of a P2 core function: `@core.implements("calculate")`.

    The implementation receives the same arguments as the core function plus `conn=` (an open connection)."""
    if name not in P2_FUNCTIONS:
        raise ValueError(f"core.{name} is not a P2 slot; slots: {', '.join(P2_FUNCTIONS)}")

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        _IMPLS[name] = fn
        return fn

    return decorator


def implemented() -> dict[str, bool]:
    """Which P2 functions are plugged in right now."""
    _load_plugins()
    return {name: name in _IMPLS for name in P2_FUNCTIONS}


def _load_plugins() -> None:
    global _PLUGINS_LOADED
    if _PLUGINS_LOADED:
        return
    _PLUGINS_LOADED = True
    for module_name in CORE_PLUGIN_MODULES:
        try:
            importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            if exc.name and module_name.startswith(exc.name):
                continue  # that teammate's module isn't merged yet
            raise


def _p2(name: str, *args: Any, conn: sqlite3.Connection, **kwargs: Any) -> Any:
    _load_plugins()
    fn = _IMPLS.get(name)
    if fn is None:
        raise NotImplementedError(f"core.{name} is P2 (Calc, Checks & Report): register it with "
                                  f"@carbonroom.core.implements({name!r}) in one of {', '.join(CORE_PLUGIN_MODULES)}")
    return fn(*args, conn=conn, **kwargs)


@contextmanager
def _ledger(conn: sqlite3.Connection | None) -> Iterator[sqlite3.Connection]:
    if conn is not None:
        yield conn
        return
    own = db.connect()
    try:
        yield own
    finally:
        own.close()


def _close(conn: sqlite3.Connection, close_id: str) -> dict:
    close = db.get_close(conn, close_id)
    if close is None:
        raise db.LedgerError(f"unknown close {close_id}")
    return close


def _move(conn: sqlite3.Connection, close_id: str, phase: str, *, actor: str = ORCHESTRATOR,
          chat_message_id: str | None = None, reason: str | None = None) -> dict:
    """Move the close to `phase` if that's allowed from where it is; otherwise leave it."""
    close = _close(conn, close_id)
    if close["phase"] == phase or phase in db.PHASE_TRANSITIONS.get(close["phase"], set()):
        return db.set_close_phase(conn, close_id, phase, actor=actor, chat_message_id=chat_message_id, reason=reason)
    return close


def _open_gaps(conn: sqlite3.Connection, close: dict) -> list[dict]:
    return [g for g in db.list_gaps(conn, period_id=close["period_id"], status="OPEN")
            if g["site_id"] is None or g["site_id"] in close["sites"]]


# ---------------------------------------------------------------------------------------------------------
# P1: start_close, room helpers, ingest, verify_audit
# ---------------------------------------------------------------------------------------------------------


def start_close(month: str, sites: Iterable[str] | None, factor_set: str | None, actor: str,
                chat_message_id: str | None, *, conn: sqlite3.Connection | None = None) -> str:
    """Open the next version of `month`'s close and lock its boundary and factor set. Returns the close id.

    `sites=None` means every site; `factor_set=None` means the month's set, else CR_FACTOR_SET. If the month
    already has an open close, that one is returned instead (the room asked twice, or the orchestrator resumed)."""
    with _ledger(conn) as c:
        existing = db.get_open_close(c, month)
        if existing:
            return existing["id"]
        return db.start_close(c, month, actor=actor, factor_set=factor_set, sites=sites,
                              chat_message_id=chat_message_id)["id"]


def latest_close(month: str | None = None, *, conn: sqlite3.Connection | None = None) -> dict | None:
    """Return the newest close, optionally for one month, so a room can resume after a restart."""
    with _ledger(conn) as c:
        if month is not None:
            closes = db.list_closes(c, month)
            return closes[-1] if closes else None
        row = c.execute("SELECT * FROM closes ORDER BY period_id DESC, version DESC LIMIT 1").fetchone()
        return db.row_to_dict(row)


def gap_for_thread(thread_id: str, *, conn: sqlite3.Connection | None = None) -> dict | None:
    """Look up the ledger gap represented by a Switch thread."""
    with _ledger(conn) as c:
        return db.row_to_dict(c.execute("SELECT * FROM gaps WHERE thread_id = ?", (thread_id,)).fetchone())


def record_gap_thread(gap_id: str, thread_id: str, actor: str, *, room: str | None = None,
                      conn: sqlite3.Connection | None = None) -> dict:
    """Persist the thread created for a Watchdog gap, making later human replies attributable."""
    with _ledger(conn) as c:
        return db.set_gap_thread(c, gap_id, thread_id, actor=actor, room=room)


def resume_state(close_id: str | None = None, *, month: str | None = None,
                 conn: sqlite3.Connection | None = None) -> dict | None:
    """Return recoverable state for one close or the newest close for `month` (or overall)."""
    with _ledger(conn) as c:
        close = _close(c, close_id) if close_id else latest_close(month, conn=c)
        return status(close["id"], conn=c) if close else None


def budget_usage(close_id: str, *, conn: sqlite3.Connection | None = None) -> list[dict[str, Any]]:
    """Return persisted model-token usage per agent for the close; no model call is made."""
    from carbonroom import budgets

    with _ledger(conn) as c:
        _close(c, close_id)
        return budgets.report(c, close_id)


def ingest(close_id: str, *, files: Iterable[str | Path] | None = None, received_from: str | None = None,
           room: str | None = None, meta: dict[str, Any] | None = None, workers: int = 4,
           conn: sqlite3.Connection | None = None) -> dict[str, Any]:
    """Collect every source (or just `files`) into the store and the ledger for this close. Every claim created is
    UNVERIFIED. Returns the collector's IngestReport (`cr.ingest-report.v1`), whose "all collected" statement is a
    claim for the Watchdog to check (carbonroom.agents.collector.check_report), never a verdict."""
    from carbonroom.agents import collector

    with _ledger(conn) as c:
        _move(c, close_id, "COLLECTING", actor=collector.ACTOR)
        return collector.collect(c, close_id, files=files, received_from=received_from, room=room, meta=meta,
                                 workers=workers)


def ingest_file(close_id: str, path: str | Path, actor: str, chat_message_id: str, *, site: str | None = None,
                conn: sqlite3.Connection | None = None) -> list[str]:
    """Ingest one room attachment and return its claim ids, retaining the human message in the audit chain.

    `site` is a room hint, not an extraction override: the document's own evidence remains authoritative.
    A hint outside the close boundary is rejected before the file is stored.
    """
    if not (chat_message_id and str(chat_message_id).strip()):
        raise db.LedgerError("ingest_file needs the Switch chat_message_id of the uploaded attachment")
    with _ledger(conn) as c:
        close = _close(c, close_id)
        if site is not None and site not in close["sites"]:
            raise db.LedgerError(f"{site} is outside the locked boundary for {close_id}")
        from carbonroom.ingest import pipeline

        _move(c, close_id, "COLLECTING", actor=actor, chat_message_id=chat_message_id)
        result = pipeline.ingest_file(c, path, received_from=actor, room=close_id,
                                      meta={"close_id": close_id, "declared_site": site})
        claim_ids = [item["id"] for item in result["activities"]]
        db.log_event(c, actor, "room_file_ingested", close_id,
                     {"doc_id": result["doc_id"], "claims": claim_ids, "declared_site": site},
                     chat_message_id=chat_message_id)
        return claim_ids


def verify_audit(close_id: str, *, conn: sqlite3.Connection | None = None) -> dict[str, Any]:
    """Walk the whole audit chain and count this close's events. `summary_text` is the room answer
    ("Audit chain intact: 57 events, 23 for CLOSE-2026-10-v1, head 3f2a9c1e5b7d0a42.")."""
    with _ledger(conn) as c:
        close = _close(c, close_id)
        chain = db.verify_audit_chain(c)
        mine = c.execute(
            "SELECT COUNT(*) AS n FROM events WHERE ref = ? OR json_extract(detail_json, '$.close_id') = ? "
            "OR (ref = ? AND action IN ('period_factor_set', 'period_closed'))",
            (close_id, close_id, close["period_id"])).fetchone()["n"]
        head = chain["head"] or {}
        if chain["ok"]:
            text = (f"Audit chain intact: {chain['events']} events, {mine} for {close_id}, "
                    f"head {(head.get('event_hash') or '')[:16]}.")
        else:
            first = chain["problems"][0]
            text = (f"Audit chain BROKEN at event {first['id']}: {first['problem']} "
                    f"({chain['broken']} broken link(s) of {chain['events']}).")
        return {"type": "cr.audit-check.v1", "close_id": close_id, "ok": chain["ok"], "events": chain["events"],
                "close_events": mine, "broken": chain["broken"], "head": chain["head"], "problems": chain["problems"],
                "summary_text": text}


def status(close_id: str, *, conn: sqlite3.Connection | None = None) -> dict[str, Any]:
    """The close row plus what the ledger knows about it right now (for resume and the Close Board)."""
    with _ledger(conn) as c:
        close = _close(c, close_id)
        acts = [a for a in db.list_activities(c, period_id=close["period_id"]) if a["site_id"] in close["sites"]]
        counts: dict[str, int] = {}
        for a in acts:
            counts[a["status"]] = counts.get(a["status"], 0) + 1
        return {"close": close, "claims_by_status": counts, "open_gaps": [g["id"] for g in _open_gaps(c, close)],
                "expected_missing": db.expected_but_missing(c, close["period_id"], sites=close["sites"]),
                "implemented": implemented()}


# ---------------------------------------------------------------------------------------------------------
# P2 slots (Richa): phase bookkeeping here, the work in her registered implementations
# ---------------------------------------------------------------------------------------------------------


def calculate(close_id: str, *, conn: sqlite3.Connection | None = None) -> list[dict[str, Any]]:
    """Activity x factor (Decimal, locked factor set) for every live claim in the close. P2."""
    with _ledger(conn) as c:
        _move(c, close_id, "CALCULATING")
        return _p2("calculate", close_id, conn=c)


def check(close_id: str, *, conn: sqlite3.Connection | None = None) -> list[dict[str, Any]]:
    """Watchdog rules R1-R7; idempotent. Moves the close to AWAITING_HUMANS while gaps are open. P2."""
    with _ledger(conn) as c:
        _move(c, close_id, "CHECKING")
        findings = _p2("check", close_id, conn=c)
        if _open_gaps(c, _close(c, close_id)):
            _move(c, close_id, "AWAITING_HUMANS")
        return findings


def resolve(gap_id: str, action: str, actor: str, chat_message_id: str, payload: dict[str, Any] | None = None, *,
            close_id: str | None = None, conn: sqlite3.Connection | None = None) -> list[dict[str, Any]]:
    """A human's reply in a gap thread (needs its chat_message_id; the ledger refuses without one). P2."""
    if not (chat_message_id and str(chat_message_id).strip()):
        raise db.LedgerError("resolve needs the Switch chat_message_id of the human's reply")
    with _ledger(conn) as c:
        gap = db.get_gap(c, gap_id)
        if gap is None:
            raise db.LedgerError(f"unknown gap {gap_id}")
        close = db.get_open_close(c, gap["period_id"]) if gap["period_id"] and not close_id else None
        cid = close_id or (close or {}).get("id")
        if cid:
            _move(c, cid, "RECHECKING", actor=actor, chat_message_id=chat_message_id, reason=f"{gap_id}: {action}")
        findings = _p2("resolve", gap_id, action, actor, chat_message_id, payload or {}, conn=c)
        if cid and _open_gaps(c, _close(c, cid)):
            _move(c, cid, "AWAITING_HUMANS")
        return findings


def summary(close_id: str, *, conn: sqlite3.Connection | None = None) -> dict[str, Any]:
    """verified_t, excluded_t, coverage_pct, source_coverage, gaps. P2."""
    with _ledger(conn) as c:
        return _p2("summary", close_id, conn=c)


def draft_report(close_id: str, *, conn: sqlite3.Connection | None = None) -> dict[str, Any]:
    """The report from VERIFIED rows only. Moves the close to DRAFTED. P2."""
    with _ledger(conn) as c:
        report = _p2("draft_report", close_id, conn=c)
        _move(c, close_id, "DRAFTED")
        return report


def publish(close_id: str, actor: str, chat_message_id: str, *,
            conn: sqlite3.Connection | None = None) -> dict[str, Any]:
    """P2 builds the final pack (and checks the approval tiers); then the ledger's gate publishes it, which
    refuses without `actor`'s chat message and their APPROVE from the room."""
    if not (chat_message_id and str(chat_message_id).strip()):
        raise db.LedgerError("publish needs the Switch chat_message_id of the publish command")
    with _ledger(conn) as c:
        published = _p2("publish", close_id, actor, chat_message_id, conn=c)
        db.publish_close(c, close_id, published_by=actor, chat_message_id=chat_message_id,
                         report_sha256=(published or {}).get("report_sha256"))
        return published


def trace(tag: str, *, conn: sqlite3.Connection | None = None) -> dict[str, Any]:
    """S-### -> file, page, excerpt, SHA-256, factor, recompute. P2 (the ledger graph has the links:
    carbonroom.ledger.graph.lineage)."""
    with _ledger(conn) as c:
        return _p2("trace", tag, conn=c)


def default_sources() -> list[Path]:
    """Where `ingest` looks when no files are given: the seeded documents and every room's inbox folder."""
    return [p for p in (config.seed_dir() / "docs", config.inbox_dir()) if p.exists()]
