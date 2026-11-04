"""Ingest = collect -> extract (propose + verify) -> consolidate, one document at a time.

Used by the CLI (`carbonroom ingest`, `carbonroom seed`) and by Akshar's agents, which can
either drop files into data/inbox/<room>/ or call `carbonroom ingest <file> --json`.
Running ingest twice on the same files changes nothing (duplicates are skipped by sha256).
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from carbonroom import config
from carbonroom.ingest import collector, consolidator, extract, rules
from carbonroom.ledger import db

ACTOR = "cr-collector"


def _summary(path: Path, inc: collector.Incoming, status: str, **rest: Any) -> dict[str, Any]:
    return {"file": str(path), "sha256": inc.sha256, "status": status, "received_from": inc.received_from,
            "room": inc.room, **rest}


@dataclass
class Prepared:
    """Everything known about one file before touching the ledger (safe to build in a worker thread)."""

    path: Path
    inc: collector.Incoming
    pages: list[str]
    proposed: extract.Proposed


def prepare(inc: collector.Incoming, *, proposer: str | None = None, refresh_cache: bool = False) -> Prepared:
    """Read page text and get a proposal (cache / model / rules). No ledger access, so it can run in parallel;
    the model call happens here, outside any write lock."""
    pages = extract.read_pages(inc.path)
    mode = proposer or config.env("CR_PROPOSER", "auto")
    if pages and any(p.strip() for p in pages):
        proposed = extract.propose(inc.path, pages, inc.sha256, mode=mode, refresh=refresh_cache)
    else:
        proposed = extract.Proposed({}, "none", False, ["no readable text"])
    return Prepared(inc.path, inc, pages, proposed)


def _duplicate(conn: sqlite3.Connection, path: Path, inc: collector.Incoming, existing: dict) -> dict[str, Any]:
    db.log_event(conn, ACTOR, "duplicate_skipped", existing["id"], {"file": str(path)})
    return _summary(path, inc, "duplicate", doc_id=existing["id"], kind=existing["kind"],
                    doc_ref=existing["doc_ref"], activities=[], instruments=[], gaps=[], supersedes=[])


def ingest_file(
    conn: sqlite3.Connection,
    path: str | Path,
    *,
    received_from: str | None = None,
    room: str | None = None,
    meta: dict[str, Any] | None = None,
    proposer: str | None = None,
    refresh_cache: bool = False,
) -> dict[str, Any]:
    path = Path(path)
    inc = collector.describe(path, received_from=received_from, room=room, meta=meta)
    existing = db.get_source_doc_by_sha(conn, inc.sha256)
    if existing:  # checked before proposing, so a duplicate never costs a model call
        return _duplicate(conn, path, inc, existing)
    return commit(conn, prepare(inc, proposer=proposer, refresh_cache=refresh_cache))


def commit(conn: sqlite3.Connection, prep: Prepared) -> dict[str, Any]:
    """Verify a prepared file against its own text and write it to the ledger (main thread only)."""
    path, inc, pages, proposed = prep.path, prep.inc, prep.pages, prep.proposed
    existing = db.get_source_doc_by_sha(conn, inc.sha256)
    if existing:
        return _duplicate(conn, path, inc, existing)
    ex = extract.verify(proposed.proposal, pages, extract.site_matcher_for(conn), proposed.proposer)

    rules_kind = rules.classify(pages) if pages else "other"
    kind = rules_kind if rules_kind != "other" else (ex.doc_kind if ex.doc_kind in db.DOC_KINDS else "other")

    with db.transaction(conn):  # the document and its rows land together or not at all
        doc, created = db.add_source_doc(
            conn,
            sha256=inc.sha256,
            path=collector.store(inc),
            kind=kind,
            received_from=inc.received_from,
            room=inc.room,
            original_name=path.name,
            doc_ref=ex.doc_ref.value if ex.doc_ref else None,
            page_count=len(pages),
            meta={**inc.meta, "proposer": proposed.proposer, "notes": proposed.notes + ex.notes},
            actor=ACTOR,
        )
        if not created:  # another process won the race
            return _summary(path, inc, "duplicate", doc_id=doc["id"], kind=doc["kind"], doc_ref=doc["doc_ref"],
                            activities=[], instruments=[], gaps=[], supersedes=[])
        written = consolidator.consolidate(conn, doc, ex, received_from=inc.received_from, room=inc.room)

    return _summary(
        path,
        inc,
        "new",
        doc_id=doc["id"],
        kind=kind,
        doc_ref=doc["doc_ref"],
        proposer=proposed.proposer,
        notes=proposed.notes + ex.notes,
        site=ex.site_id,
        period=ex.period,
        activities=[
            {"id": a["id"], "site": a["site_id"], "period": a["period_id"], "category": a["category"],
             "quantity": a["quantity"], "unit": a["unit"], "status": a["status"], "excerpt": a["excerpt"],
             "locator": a["excerpt_locator"], "excerpt_sha256": a["excerpt_sha256"],
             "replaces_activity_ids": (a["extra"] or {}).get("replaces_activity_ids", [])}
            for a in written["activities"]
        ],
        instruments=[
            {"id": i["id"], "kind": i["kind"], "mwh": i["mwh"], "region": i["region"], "vintage": i["vintage"],
             "site": i["site_id"], "period": i["period_id"], "excerpt": i["excerpt"], "locator": i["excerpt_locator"]}
            for i in written["instruments"]
        ],
        gaps=[
            {"id": g["id"], "kind": g["kind"], "owner": g["owner_handle"], "room": g["room"], "detail": g["detail"]}
            for g in written["gaps"]
        ],
        supersedes=written["supersedes"],
    )


def ingest_paths(
    conn: sqlite3.Connection,
    targets: list[str | Path],
    *,
    received_from: str | None = None,
    room: str | None = None,
    meta: dict[str, Any] | None = None,
    proposer: str | None = None,
    refresh_cache: bool = False,
    move_processed: bool = False,
    on_result: Callable[[dict[str, Any]], None] | None = None,
) -> list[dict[str, Any]]:
    results = []
    inbox = config.inbox_dir()
    for target in targets:
        target = Path(target)
        if not target.exists():
            raise FileNotFoundError(target)
        for path in collector.iter_files(target):
            result = ingest_file(conn, path, received_from=received_from, room=room, meta=meta,
                                 proposer=proposer, refresh_cache=refresh_cache)
            if move_processed:
                moved = collector.move_processed(path, inbox)
                if moved:
                    result["moved_to"] = str(moved)
            results.append(result)
            if on_result:
                on_result(result)
    return results


def watch(
    conn: sqlite3.Connection,
    folder: Path,
    *,
    interval: float = 3.0,
    proposer: str | None = None,
    move_processed: bool = True,
    on_result: Callable[[dict[str, Any]], None] | None = None,
    max_cycles: int | None = None,
) -> None:
    """Poll the inbox; ingest anything new. Ctrl-C to stop."""
    folder.mkdir(parents=True, exist_ok=True)
    cycles = 0
    while max_cycles is None or cycles < max_cycles:
        ingest_paths(conn, [folder], proposer=proposer, move_processed=move_processed, on_result=on_result)
        cycles += 1
        if max_cycles is None or cycles < max_cycles:
            time.sleep(interval)
