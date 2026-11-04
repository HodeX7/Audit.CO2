"""Background batch run: ingest many files quietly, in parallel, and return ONE final summary.

The orchestrator (Switch + LangGraph, owned by teammates) starts a run, waits, and posts only
`summary_text` to the humans' channel. Nothing here talks to chat.

How a run works
  1. main thread: hash every file, skip duplicates (already in the ledger, or twice in this batch)
  2. worker threads (`workers`): read page text + get a proposal (cache / model / rules). No ledger
     access here, so the slow part - model calls - overlaps. The shared rate limiter in llm.py keeps
     the total within CR_LLM_RPM.
  3. main thread, in a fixed order (sorted paths): verify + write each file in its own transaction.
     Because of the fixed order, ids and GAP numbers are identical with 1 worker or 8.
  4. one file failing (crash, corrupt) is recorded in `errors`; the rest of the run continues.
  5. `batch_started` / `batch_finished` events (ref = run id) keep the summary; `carbonroom ledger runs`
     shows past runs, and every source document gets `meta.run_id`.

LangGraph: `collect_node(state)` is a plain function you can add as a node (or target with Send for
fan-out). Several nodes may run at once against the same ledger file: SQLite WAL + BEGIN IMMEDIATE
serialize the writes.
"""

from __future__ import annotations

import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

from carbonroom import config
from carbonroom.ingest import collector, pipeline
from carbonroom.ledger import db

ACTOR = "cr-collector"
SUMMARY_TYPE = "cr.batch.v1"


def new_run_id() -> str:
    stamp = config.now_iso().replace("-", "").replace(":", "").replace("Z", "")
    return f"RUN-{stamp}-{db.sha256_text(str(time.time_ns()))[:6]}"


def _fmt(qty: str) -> str:
    d = db.dec(qty)
    return f"{int(d):,}" if d == d.to_integral_value() else f"{d:,}"


def run_batch(
    conn: sqlite3.Connection,
    targets: list[str | Path],
    *,
    workers: int = 4,
    received_from: str | None = None,
    room: str | None = None,
    meta: dict[str, Any] | None = None,
    proposer: str | None = None,
    refresh_cache: bool = False,
    run_id: str | None = None,
    periods: list[str] | None = None,
    on_result: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Ingest every supported file under `targets`. Returns a `cr.batch.v1` summary."""
    run_id = run_id or new_run_id()
    started = time.monotonic()
    started_at = config.now_iso()
    files: list[Path] = []
    for target in targets:
        target = Path(target)
        if not target.exists():
            raise FileNotFoundError(target)
        files.extend(collector.iter_files(target))
    files = sorted(set(files), key=lambda p: str(p))
    db.log_event(conn, ACTOR, "batch_started", run_id, {"files": len(files), "workers": workers})

    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    todo: list[collector.Incoming] = []
    seen: dict[str, Path] = {}
    for path in files:  # 1. hash + dedupe (cheap, main thread)
        try:
            inc = collector.describe(path, received_from=received_from, room=room,
                                     meta={**(meta or {}), "run_id": run_id})
        except OSError as exc:
            errors.append({"file": str(path), "error": f"{type(exc).__name__}: {exc}"})
            continue
        existing = db.get_source_doc_by_sha(conn, inc.sha256)
        if existing or inc.sha256 in seen:
            if existing:
                result = pipeline._duplicate(conn, path, inc, existing)
            else:
                result = pipeline._summary(path, inc, "duplicate", duplicate_of=str(seen[inc.sha256]),
                                           activities=[], instruments=[], gaps=[], supersedes=[])
            results.append(result)
            if on_result:
                on_result(result)
            continue
        seen[inc.sha256] = path
        todo.append(inc)

    def _prepare(inc: collector.Incoming):
        try:
            return pipeline.prepare(inc, proposer=proposer, refresh_cache=refresh_cache), None
        except Exception as exc:  # noqa: BLE001 - one bad file must not stop a background run
            return None, f"{type(exc).__name__}: {exc}"

    # 2. parallel prepare; map() keeps input order, so 3. commits in a fixed order
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for inc, (prep, err) in zip(todo, pool.map(_prepare, todo)):
            if err is None:
                try:
                    result = pipeline.commit(conn, prep)
                except Exception as exc:  # noqa: BLE001
                    err = f"{type(exc).__name__}: {exc}"
            if err is not None:
                errors.append({"file": str(inc.path), "error": err})
                db.log_event(conn, ACTOR, "ingest_error", run_id, {"file": str(inc.path), "error": err})
                continue
            results.append(result)
            if on_result:
                on_result(result)

    summary = summarize(conn, run_id, results, errors, periods=periods, workers=workers,
                        started_at=started_at, seconds=time.monotonic() - started)
    compact = {k: v for k, v in summary.items() if k not in ("results", "activities")}
    db.log_event(conn, ACTOR, "batch_finished", run_id, compact)
    return summary


def summarize(
    conn: sqlite3.Connection,
    run_id: str,
    results: list[dict[str, Any]],
    errors: list[dict[str, str]],
    *,
    periods: list[str] | None = None,
    workers: int = 1,
    started_at: str | None = None,
    seconds: float = 0.0,
) -> dict[str, Any]:
    new = [r for r in results if r["status"] == "new"]
    activities = [a for r in new for a in r["activities"]]
    instruments = [i for r in new for i in r["instruments"]]
    gaps = [g for r in new for g in r["gaps"]]
    unreadable = [r for r in new if "no readable text" in " ".join(r.get("notes") or [])]
    touched = sorted({r["period"] for r in new if r.get("period")} | set(periods or []))
    missing = {p: db.expected_but_missing(conn, p) for p in touched}
    by_owner: dict[str, list[str]] = {}
    for g in gaps:
        by_owner.setdefault(g["owner"] or "unassigned", []).append(g["id"])
    proposers: dict[str, int] = {}
    for r in new:
        proposers[r.get("proposer") or "none"] = proposers.get(r.get("proposer") or "none", 0) + 1

    parts = [f"Collected {len(new)} new document{'s' if len(new) != 1 else ''}"
             f" ({len(results) - len(new)} duplicate, {len(unreadable)} unreadable, {len(errors)} failed)"]
    parts.append(f"{len(activities)} activit{'ies' if len(activities) != 1 else 'y'} (all UNVERIFIED)"
                 + (f" and {len(instruments)} REC{'s' if len(instruments) != 1 else ''}" if instruments else ""))
    parts.append(f"{len(gaps)} new gap{'s' if len(gaps) != 1 else ''}"
                 + (" (" + ", ".join(f"@{o}: {', '.join(ids)}" for o, ids in sorted(by_owner.items())) + ")"
                    if gaps else ""))
    still_missing = [f"{m['site_name']} {m['category']} {m['period_id']} (@{m['owner_handle']})"
                     for p in touched for m in missing[p]]
    text = " · ".join(parts) + "."
    if still_missing:
        text += " Still missing: " + "; ".join(still_missing) + "."

    return {
        "type": SUMMARY_TYPE,
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": config.now_iso(),
        "seconds": round(seconds, 1),
        "workers": workers,
        "files": len(results) + len(errors),
        "new": len(new),
        "duplicates": len(results) - len(new),
        "unreadable": len(unreadable),
        "failed": len(errors),
        "errors": errors,
        "activities_count": len(activities),
        "instruments_count": len(instruments),
        "activities": [{"id": a["id"], "site": a["site"], "period": a["period"], "category": a["category"],
                        "quantity": a["quantity"], "unit": a["unit"], "summary":
                        f"{a['site']} {a['period']} {a['category']} {_fmt(a['quantity'])} {a['unit']}"}
                       for a in activities],
        "gaps": gaps,
        "gaps_by_owner": by_owner,
        "expected_but_missing": missing,
        "periods": touched,
        "proposers": proposers,
        "summary_text": text,
        "results": results,
    }


def list_runs(conn: sqlite3.Connection, limit: int = 20) -> list[dict[str, Any]]:
    """Finished runs, newest first, from the append-only events log."""
    rows = conn.execute(
        "SELECT * FROM events WHERE action = 'batch_finished' ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [db.row_to_dict(r)["detail"] for r in rows]


def get_run(conn: sqlite3.Connection, run_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM events WHERE action = 'batch_finished' AND ref = ? ORDER BY id DESC LIMIT 1", (run_id,)
    ).fetchone()
    return db.row_to_dict(row)["detail"] if row else None


def collect_node(state: dict[str, Any]) -> dict[str, Any]:
    """LangGraph-ready node: state in, partial state out.

    Reads   state["files"] (paths or folders) and optionally "db_path", "room", "received_from",
            "run_id", "workers", "periods", "proposer".
    Returns {"ingest_summaries": [summary]} - a list, so parallel branches can be merged with an
            `operator.add` reducer.
    """
    conn = db.connect(state.get("db_path")) if state.get("db_path") else db.connect()
    try:
        summary = run_batch(
            conn,
            list(state["files"]),
            workers=int(state.get("workers", 4)),
            received_from=state.get("received_from"),
            room=state.get("room"),
            run_id=state.get("run_id"),
            periods=state.get("periods"),
            proposer=state.get("proposer"),
        )
        from carbonroom.graphdb import store as graph_store

        summary["graph_synced"] = graph_store.sync_if_enabled(conn, quiet=True) is not None
    finally:
        conn.close()
    summary.pop("results", None)
    return {"ingest_summaries": [summary]}
