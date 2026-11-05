"""@collector (P1): ingests every source into the store and the ledger, then reports what it collected.

Its "all collected" statement is a claim for @watchdog to check (check_report re-derives it from the ledger
and the files), never a verdict. It never marks anything VERIFIED: nothing here changes a status, resolves a
gap, approves or publishes.

Room contract (the router, P3, converts Switch events to this and executes the ops):

  event in   {"type": "message" | "command", "message_id", "thread_id", "room", "sender", "text",
              "addressed": bool, "attachments": [{"name", "path"?, "sha256"?}], "gap_id"?, "close_id"?,
              "command"?: "collect"}
  ops out    {"op": "post_message", "room", "thread_id", "text", "data"}
             {"op": "send_targeted_message", "to": "@carbon-room" | "@watchdog", "text", "data"}

handle() does ledger and file work and can take seconds: run it in the router's worker pool, never on the
socket loop (Switch evicts a socket that misses its pong).
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from carbonroom import budgets, config, llm
from carbonroom.ingest import batch, extract
from carbonroom.ingest.hashing import sha256_file
from carbonroom.ledger import db

ACTOR = "cr-collector"
REPORT_TYPE = "cr.ingest-report.v1"
CHECK_TYPE = "cr.ingest-report-check.v1"
HANDLE = "@collector"

MONTHS = {name: f"{i:02d}" for i, names in enumerate(
    [(), ("january", "jan"), ("february", "feb"), ("march", "mar"), ("april", "apr"), ("may",), ("june", "jun"),
     ("july", "jul"), ("august", "aug"), ("september", "sep", "sept"), ("october", "oct"), ("november", "nov"),
     ("december", "dec")]) for name in names}
CATEGORY_WORDS = {
    "electricity": {"electricity", "electric", "power", "utility", "kwh", "meter"},
    "natural_gas": {"gas", "therm", "therms"},
    "diesel": {"diesel", "fuel", "generator", "delivery"},
    "cloud_compute": {"cloud", "data", "datacenter", "datacentre", "centre", "center", "dc", "compute", "server",
                      "ai", "pue", "wue"},
    "REC": {"rec", "recs", "certificate", "renewable", "energy"},
}
_FILLER = {"why", "did", "didn", "didnt", "don", "dont", "t", "you", "not", "consider", "considered", "the", "a", "an",
           "report", "reports", "bill", "bills", "invoice", "invoices", "document", "documents", "doc", "file", "pdf",
           "about", "what", "happened", "to", "of", "for", "from", "is", "was", "were", "my", "our", "this", "that",
           "in", "on", "with", "and", "or", "get", "got", "use", "used", "please", "collector", "it", "its", "any",
           "include", "included", "skip", "skipped", "ignore", "ignored", "miss", "missed", "where", "s", "see",
           "receive", "received", "collect", "collected", "have", "has", "we", "i", "me", "us", "your", "do", "does"}
_WHY = re.compile(r"\bwhy\b|\bwhat happened to\b|\bdid you (?:get|receive|see|collect|use)\b|\bwhere(?:'s| is)\b",
                  re.IGNORECASE)
_COLLECT = re.compile(r"\b(?:collect|ingest|pull|gather|fetch)\b", re.IGNORECASE)
_STATUS = re.compile(r"\b(?:status|what did you collect|what have you collected|summary)\b", re.IGNORECASE)
_ASKS_WHY = re.compile(r"\bwhy\b", re.IGNORECASE)


# ---------------------------------------------------------------------------------------------------------
# Collect + the checkable report
# ---------------------------------------------------------------------------------------------------------


def collect(conn: sqlite3.Connection, close_id: str, *, files: Iterable[str | Path] | None = None,
            received_from: str | None = None, room: str | None = None, meta: dict[str, Any] | None = None,
            workers: int = 4) -> dict[str, Any]:
    """Ingest `files` (default: every source) for this close, then report. Model calls are charged to
    @collector's budget for this close; every claim created is UNVERIFIED."""
    from carbonroom import core

    close = db.get_close(conn, close_id)
    if close is None:
        raise db.LedgerError(f"unknown close {close_id}")
    targets = [Path(f) for f in files] if files else core.default_sources()
    with budgets.scope(conn, close_id, ACTOR):
        run = batch.run_batch(conn, targets, workers=workers, received_from=received_from, room=room,
                              meta={**(meta or {}), "close_id": close_id}, periods=[close["period_id"]])
    report = build_report(conn, close, run)
    db.log_event(conn, ACTOR, "collection_reported", close_id, report)
    from carbonroom.graphdb import store as graph_store

    report["graph_synced"] = graph_store.sync_if_enabled(conn, quiet=True) is not None
    return report


def _fmt(qty: str) -> str:
    d = db.dec(qty)
    return f"{int(d):,}" if d == d.to_integral_value() else f"{d:,}"


def _in_scope(conn: sqlite3.Connection, close: dict, *, before: str | None = None) -> tuple[list[dict], list[dict]]:
    """Live claims and RECs for the close's month and boundary (optionally only those created by `before`)."""
    claims = [a for a in db.list_activities(conn, period_id=close["period_id"], include_superseded=False)
              if a["site_id"] in close["sites"] and (before is None or (a["created_at"] or "") <= before)]
    recs = [i for i in db.list_instruments(conn, period_id=close["period_id"])
            if (i["site_id"] is None or i["site_id"] in close["sites"]) and i["status"] != "SUPERSEDED"
            and (before is None or (i.get("created_at") or i.get("updated_at") or "") <= before)]
    return claims, recs


def build_report(conn: sqlite3.Connection, close: dict, run: dict[str, Any]) -> dict[str, Any]:
    """The IngestReport: what is in scope, what this run added, what is still expected, and a statement."""
    month, boundary = close["period_id"], close["sites"]
    claims, recs = _in_scope(conn, close)
    doc_ids = sorted({a["source_doc_id"] for a in claims} | {i["source_doc_id"] for i in recs})
    documents = []
    for doc_id in doc_ids:
        doc = db.get_source_doc(conn, doc_id)
        documents.append({"doc_id": doc_id, "sha256": doc["sha256"], "doc_ref": doc["doc_ref"], "kind": doc["kind"],
                          "path": doc["path"], "received_from": doc["received_from"]})
    new = [r for r in run.get("results", []) if r["status"] == "new"]
    elsewhere, unproven = [], []
    for r in new:
        rows = r["activities"] + r["instruments"]
        if not rows:
            unproven.append({"doc_id": r["doc_id"], "file": Path(r["file"]).name, "notes": r.get("notes") or [],
                             "gap_ids": [g["id"] for g in r["gaps"]]})
        for a in r["activities"]:
            if a["period"] != month or a["site"] not in boundary:
                elsewhere.append({"doc_id": r["doc_id"], "doc_ref": r.get("doc_ref"), "site": a["site"],
                                  "period": a["period"], "reason": "other month" if a["period"] != month
                                  else "site outside the close boundary"})
    missing = db.expected_but_missing(conn, month, sites=boundary)
    complete = not missing
    statement = (f"All expected {month} sources collected for {len(boundary)} site(s)" if complete
                 else f"{len(missing)} expected {month} source(s) still missing")
    by_status: dict[str, int] = {}
    for a in claims:
        by_status[a["status"]] = by_status.get(a["status"], 0) + 1
    head = db.audit_head(conn) or {}
    sites = {s["id"]: s["name"] for s in db.list_sites(conn)}
    text = (f"{close['id']} ({month}; {', '.join(sites.get(s, s) for s in boundary)}): "
            f"{run.get('new', 0)} new document(s), {run.get('duplicates', 0)} already in the ledger, "
            f"{run.get('failed', 0)} failed. In scope: {len(documents)} document(s), {len(claims)} claim(s) ("
            + ", ".join(f"{n} {s}" for s, n in sorted(by_status.items())) + ")"
            + (f", {len(recs)} REC(s)" if recs else "") + f". Statement: {statement}.")
    if missing:
        text += " Missing: " + "; ".join(f"{m['site_name']} {m['category']} (@{m['owner_handle']})" for m in missing) + "."
    if unproven:
        text += " Nothing proven from: " + ", ".join(u["file"] for u in unproven) + "."
    text += f" @watchdog: please check this, it's a claim, not a verdict. Audit head {(head.get('event_hash') or '')[:16]}."
    return {
        "type": REPORT_TYPE,
        "close_id": close["id"],
        "period": month,
        "sites": boundary,
        "made_by": ACTOR,
        "made_at": config.now_iso(),
        "run_id": run.get("run_id"),
        "new_documents": run.get("new", 0),
        "duplicates": run.get("duplicates", 0),
        "failed": run.get("failed", 0),
        "errors": run.get("errors", []),
        "claims_created": [a["id"] for r in new for a in r["activities"]],
        "documents": documents,
        "claims": [{"id": a["id"], "site": a["site_id"], "category": a["category"], "quantity": a["quantity"],
                    "unit": a["unit"], "status": a["status"], "source_doc_id": a["source_doc_id"]} for a in claims],
        "recs": [{"id": i["id"], "mwh": i["mwh"], "status": i["status"], "source_doc_id": i["source_doc_id"]}
                 for i in recs],
        "claims_by_status": by_status,
        "expected_missing": [{"site": m["site_id"], "category": m["category"], "owner": m["owner_handle"]}
                             for m in missing],
        "statement": statement,
        "statement_complete": complete,
        "outside_this_close": elsewhere,
        "nothing_proven": unproven,
        "audit_head": {"id": head.get("id"), "event_hash": head.get("event_hash")},
        "summary_text": text,
    }


def latest_report(conn: sqlite3.Connection, close_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM events WHERE action = 'collection_reported' AND ref = ? ORDER BY id DESC LIMIT 1",
                       (close_id,)).fetchone()
    return db.row_to_dict(row)["detail"] if row else None


def check_report(conn: sqlite3.Connection, report: dict[str, Any]) -> dict[str, Any]:
    """Re-derive the collector's report from the ledger and the stored files ("checked, never trusted").

    Checks: every listed document still exists and its file still hashes to the listed SHA-256; every listed claim
    exists, comes from a listed document, and is in the close's month and boundary; no claim that existed when the
    report was made is left out; the missing list and the statement match the ledger as of the report; the
    collector never set a status to VERIFIED; the audit head it quoted is in an intact chain."""
    problems: list[str] = []
    close = db.get_close(conn, report.get("close_id") or "")
    if close is None:
        return {"type": CHECK_TYPE, "ok": False, "problems": [f"unknown close {report.get('close_id')}"], "checked": {}}
    if sorted(report.get("sites") or []) != sorted(close["sites"]) or report.get("period") != close["period_id"]:
        problems.append("the report's month or sites differ from the close's locked boundary")
    listed_docs = {d["doc_id"]: d for d in report.get("documents") or []}
    rehashed = 0
    for doc_id, listed in listed_docs.items():
        doc = db.get_source_doc(conn, doc_id)
        if doc is None or doc["sha256"] != listed.get("sha256"):
            problems.append(f"{doc_id}: not in the ledger with the listed SHA-256")
            continue
        path = extract.resolve_doc_path(doc["path"])
        if not path.exists() or sha256_file(path) != doc["sha256"]:
            problems.append(f"{doc_id}: the stored file is missing or no longer matches its SHA-256")
        else:
            rehashed += 1
    listed_claims = {c["id"]: c for c in report.get("claims") or []}
    for claim_id in listed_claims:
        a = db.get_activity(conn, claim_id)
        if a is None:
            problems.append(f"{claim_id}: listed but not in the ledger")
        elif a["source_doc_id"] not in listed_docs:
            problems.append(f"{claim_id}: its source document {a['source_doc_id']} is not listed")
        elif a["period_id"] != close["period_id"] or a["site_id"] not in close["sites"]:
            problems.append(f"{claim_id}: outside the close's month or boundary")
    made_at = report.get("made_at")
    then_claims, _ = _in_scope(conn, close, before=made_at)
    for a in then_claims:
        if a["id"] not in listed_claims and a["status"] != "SUPERSEDED":
            problems.append(f"{a['id']}: in scope when the report was made but not listed")
    have = {(a["site_id"], a["category"]) for a in then_claims}
    expected = sorted((e["site_id"], e["category"]) for e in db.list_expected_documents(conn)
                      if e["frequency"] == "monthly" and e["site_id"] in close["sites"]
                      and (e["site_id"], e["category"]) not in have)
    said = sorted((m["site"], m["category"]) for m in report.get("expected_missing") or [])
    if said != expected:
        problems.append(f"missing list {said} does not match the ledger as of the report: {expected}")
    if bool(report.get("statement_complete")) != (not expected):
        problems.append(f"statement '{report.get('statement')}' does not match the ledger "
                        f"({len(expected)} expected source(s) missing)")
    verified_by_me = conn.execute(
        "SELECT COUNT(*) AS n FROM events WHERE actor = ? AND action = 'activity_status' "
        "AND json_extract(detail_json, '$.to') = 'VERIFIED'", (ACTOR,)).fetchone()["n"]
    if verified_by_me:
        problems.append(f"@collector marked {verified_by_me} claim(s) VERIFIED; it must never do that")
    chain = db.verify_audit_chain(conn)
    head = report.get("audit_head") or {}
    row = conn.execute("SELECT event_hash FROM events WHERE id = ?", (head.get("id"),)).fetchone()
    if not chain["ok"]:
        problems.append(f"audit chain broken at event {chain['problems'][0]['id']}")
    if head.get("id") is not None and (row is None or row["event_hash"] != head.get("event_hash")):
        problems.append("the audit head quoted in the report is not in the chain")
    return {"type": CHECK_TYPE, "close_id": close["id"], "ok": not problems, "problems": problems,
            "checked": {"documents": len(listed_docs), "rehashed": rehashed, "claims": len(listed_claims),
                        "expected_missing": len(expected)}}


# ---------------------------------------------------------------------------------------------------------
# "Why didn't you consider X?"
# ---------------------------------------------------------------------------------------------------------


def _terms(query: str) -> list[str]:
    q = re.sub(r"@\w+", " ", query.lower())
    return [t for t in re.findall(r"[a-z0-9][a-z0-9._-]*", q) if t not in _FILLER]


def explain(conn: sqlite3.Connection, query: str, *, close: dict | None = None) -> dict[str, Any]:
    """What happened to a document someone names: received? from whom? which claims, which status, superseded,
    duplicate, outside this close, nothing provable, failed? If nothing matches, say so and list what's missing."""
    terms = _terms(query)
    sites = db.list_sites(conn)
    month_terms = {MONTHS[t] for t in terms if t in MONTHS} | {t[-2:] for t in terms if re.fullmatch(r"\d{4}-\d{2}", t)}
    category_terms = {cat for cat, words in CATEGORY_WORDS.items() for t in terms if t in words}
    site_terms = {s["id"] for s in sites for t in terms
                  if t == s["id"] or t in db._norm(s["name"]).split() or any(t in db._norm(a).split()
                                                                             for a in s["aliases"] or [])}
    generic = set().union(*CATEGORY_WORDS.values()) | set(MONTHS) | {s for s in site_terms}
    specific = [t for t in terms if t not in generic and not re.fullmatch(r"\d{4}-\d{2}", t)
                and not any(t in db._norm(s["name"]).split() for s in sites)]

    instruments = db.list_instruments(conn)
    found: list[tuple[dict, list[dict], list[dict]]] = []
    related: list[tuple[dict, list[dict], list[dict]]] = []
    for doc in db.list_source_docs(conn):
        acts = db.list_activities(conn, source_doc_id=doc["id"])
        recs = [i for i in instruments if i["source_doc_id"] == doc["id"]]
        hay = " ".join(str(x or "") for x in (doc["doc_ref"], doc["original_name"], doc["path"], doc["kind"],
                                              doc["received_from"])).lower()
        rows_sites = {a["site_id"] for a in acts} | {i["site_id"] for i in recs if i["site_id"]}
        rows_cats = {a["category"] for a in acts} | ({"REC"} if recs else set())
        rows_months = {a["period_id"][-2:] for a in acts} | {i["period_id"][-2:] for i in recs}
        generic_ok = bool(site_terms or category_terms or month_terms) and not (
            (site_terms and not site_terms & rows_sites) or (category_terms and not category_terms & rows_cats)
            or (month_terms and not month_terms & rows_months))
        if specific:
            if all(t in hay for t in specific):
                found.append((doc, acts, recs))
            elif generic_ok and doc["superseded_by"] is None:
                related.append((doc, acts, recs))
        elif generic_ok:
            found.append((doc, acts, recs))

    skipped, seen_names = [], set()
    for row in conn.execute("SELECT * FROM events WHERE action IN ('duplicate_skipped', 'ingest_error') ORDER BY id"):
        e = db.row_to_dict(row)
        name = Path((e["detail"] or {}).get("file") or "").name
        if not (specific and name and all(t in name.lower() for t in specific)) or name in seen_names:
            continue
        if e["action"] == "duplicate_skipped":
            same = db.get_source_doc(conn, e["ref"]) or {}
            if same.get("original_name") == name:
                continue  # the same file seen again (a re-scan), not a different upload
        seen_names.add(name)
        skipped.append(e)

    lines = [_describe(conn, doc, acts, recs, close) for doc, acts, recs in found[:6]]
    for e in skipped[:3]:
        name = Path(e["detail"].get("file") or "").name
        if e["action"] == "duplicate_skipped":
            lines.append(f"{name} was skipped: it is byte-for-byte the same file as {e['ref']} (identical SHA-256).")
        else:
            lines.append(f"{name} failed to ingest: {e['detail'].get('error')}.")
    if not lines:
        what = " ".join(specific) or query.strip()
        text = (f"Nothing matching \"{what}\" has reached me: no upload, inbox file or skipped duplicate by that "
                "name, so I could not consider it.")
        if related:
            text += " What I do have for that: " + " ".join(_describe(conn, d, a, r, close) for d, a, r in related[:3])
        if close:
            missing = db.expected_but_missing(conn, close["period_id"], sites=close["sites"])
            if missing:
                text += (f" Still expected for {close['period_id']}: "
                         + "; ".join(f"{m['site_name']} {m['category']} (@{m['owner_handle']})" for m in missing) + ".")
        text += " Drop the file in this thread and I'll ingest it."
    else:
        text = " ".join(lines) + (f" ({len(found) - 6} more match.)" if len(found) > 6 else "")
    return {"query": query, "terms": terms, "matched_documents": [d["id"] for d, _, _ in found],
            "related_documents": [d["id"] for d, _, _ in related], "skipped_events": [e["id"] for e in skipped],
            "summary_text": text}


def _describe(conn: sqlite3.Connection, doc: dict, acts: list[dict], recs: list[dict], close: dict | None) -> str:
    """One sentence about one document: when and from whom, what it proved and each claim's status."""
    label = doc["doc_ref"] or doc["original_name"] or doc["id"]
    line = f"{label} ({doc['original_name']}) reached the ledger on {doc['received_at'][:10]}"
    line += f" from @{doc['received_from']}" if doc["received_from"] and doc["received_from"] != "seed" else " (seed)"
    if doc["superseded_by"]:
        new = db.get_source_doc(conn, doc["superseded_by"]) or {}
        line += f"; it was replaced by {new.get('doc_ref') or doc['superseded_by']}"
    parts = []
    for a in acts:
        part = f"{a['site_id']} {a['period_id']} {a['category']} {_fmt(a['quantity'])} {a['unit']} {a['status']}"
        if a["status_reason"]:
            part += f" ({a['status_reason']})"
        if close and (a["period_id"] != close["period_id"] or a["site_id"] not in close["sites"]):
            part += f", outside {close['id']}"
        parts.append(part)
    parts += [f"REC {_fmt(i['mwh'])} MWh {i['status']}" for i in recs]
    if parts:
        line += ": " + "; ".join(parts)
    else:
        notes = (doc["meta"] or {}).get("notes") or []
        gaps = [g["id"] for g in db.list_gaps(conn) if (g["refs"] or {}).get("source_doc_id") == doc["id"]]
        line += ": nothing could be proven from it" + (f" ({'; '.join(notes[:2])})" if notes else "")
        if gaps:
            line += f", see {', '.join(gaps)}"
    return line + "."


# ---------------------------------------------------------------------------------------------------------
# Room handler
# ---------------------------------------------------------------------------------------------------------


def post(room: str | None, text: str, thread_id: str | None = None, data: dict | None = None) -> dict[str, Any]:
    return {"op": "post_message", "room": room, "thread_id": thread_id, "text": text, "data": data or {}}


def targeted(to: str, text: str, data: dict | None = None) -> dict[str, Any]:
    return {"op": "send_targeted_message", "to": to, "text": text, "data": data or {}}


def _say(text: str, question: str | None = None) -> str:
    return llm.phrase(text, question=question).text  # plain text unless CR_PHRASE=auto (and facts unchanged)


def find_close(conn: sqlite3.Connection, event: dict[str, Any]) -> dict | None:
    """The close an event is about: given id, else a month named in the text, else the gap's month, else the
    most recently started open close."""
    if event.get("close_id"):
        return db.get_close(conn, event["close_id"])
    text = (event.get("text") or "").lower()
    months = {MONTHS[w] for w in re.findall(r"[a-z]+", text) if w in MONTHS}
    months |= {m[-2:] for m in re.findall(r"\b\d{4}-\d{2}\b", text)}
    open_closes = [c for c in db.list_closes(conn) if c["phase"] != "PUBLISHED"]
    if months:
        matches = [c for c in open_closes if c["period_id"][-2:] in months]
        if matches:
            return sorted(matches, key=lambda c: c["started_at"])[-1]
    if event.get("gap_id"):
        gap = db.get_gap(conn, event["gap_id"])
        if gap and gap["period_id"]:
            found = db.get_open_close(conn, gap["period_id"])
            if found:
                return found
    return sorted(open_closes, key=lambda c: c["started_at"])[-1] if open_closes else None


def _attachment_paths(event: dict[str, Any]) -> tuple[list[Path], list[str]]:
    """Files the router passed, or the same file saved under data/inbox/ (Switch spike S2's fallback)."""
    found, missing = [], []
    inbox = config.inbox_dir()
    for att in event.get("attachments") or []:
        candidates = [Path(att["path"])] if att.get("path") else []
        if att.get("name") and inbox.exists():
            candidates += sorted(inbox.rglob(Path(att["name"]).name))
        ok = [p for p in candidates if p.is_file() and (not att.get("sha256") or sha256_file(p) == att["sha256"])]
        (found.append(ok[0]) if ok else missing.append(att.get("name") or att.get("path") or "attachment"))
    return found, missing


def handle(event: dict[str, Any], *, conn: sqlite3.Connection | None = None) -> list[dict[str, Any]]:
    """One room event in, ops out. Silent unless addressed or handed files or a command."""
    own = conn is None
    conn = conn or db.connect()
    try:
        return _handle(conn, event)
    finally:
        if own:
            conn.close()


def _handle(conn: sqlite3.Connection, event: dict[str, Any]) -> list[dict[str, Any]]:
    from carbonroom import core

    text = event.get("text") or ""
    room = event.get("room")
    thread = event.get("thread_id") or event.get("message_id")
    sender = event.get("sender")
    is_command = event.get("type") == "command"
    if not (event.get("addressed") or is_command or event.get("attachments")):
        return []
    close = find_close(conn, event)

    if event.get("attachments"):
        paths, missing = _attachment_paths(event)
        ops: list[dict[str, Any]] = []
        if missing:
            ops.append(post(room, f"I can't open {', '.join(missing)} from here. Save the same file under "
                            f"data/inbox/{room or '<room>'}/ and mention {HANDLE} again; I check its SHA-256.",
                            thread))
        if not paths:
            return ops
        meta = {k: event[k] for k in ("thread_id", "message_id", "gap_id") if event.get(k)}
        if close:
            report = core.ingest(close["id"], files=paths, received_from=sender, room=room, meta=meta, conn=conn)
            claim_ids = report["claims_created"]
        else:
            run = batch.run_batch(conn, paths, received_from=sender, room=room, meta=meta)
            claim_ids = [a["id"] for r in run["results"] if r["status"] == "new" for a in r["activities"]]
        replies = []
        for path in paths:
            row = db.get_source_doc_by_sha(conn, sha256_file(path))
            if row is None:
                replies.append(f"{path.name}: could not be stored.")
                continue
            acts = db.list_activities(conn, source_doc_id=row["id"])
            fresh = [a for a in acts if a["id"] in claim_ids]
            if not fresh and acts:
                replies.append(f"{path.name} is the same file as {row['doc_ref'] or row['id']}, already in the "
                               "ledger (identical SHA-256): nothing new.")
            elif fresh:
                replies.append(f"Got {row['doc_ref'] or path.name}: " + "; ".join(
                    f"{a['site_id']} {a['period_id']} {a['category']} {_fmt(a['quantity'])} {a['unit']} {a['status']}"
                    for a in fresh) + ".")
            else:
                replies.append(explain(conn, row["doc_ref"] or row["original_name"] or path.name,
                                       close=close)["summary_text"])
        ops.append(post(room, _say(" ".join(replies)), thread, {"claim_ids": claim_ids}))
        if event.get("gap_id") or claim_ids:
            ops.append(targeted("@watchdog", f"New evidence from @{sender}: please re-check "
                                + (event.get("gap_id") or "the affected claims") + ".",
                                {"action": "recheck", "gap_ids": [event["gap_id"]] if event.get("gap_id") else [],
                                 "claim_ids": claim_ids, "close_id": (close or {}).get("id"),
                                 "chat_message_id": event.get("message_id")}))
        return ops

    if not is_command and _STATUS.search(text) and not _ASKS_WHY.search(text):
        report = latest_report(conn, close["id"]) if close else None
        msg = report["summary_text"] if report else (
            f"I haven't collected for {close['id']} yet." if close else "No close is open.")
        return [post(room, _say(msg, question=text), thread)]

    if not is_command and _WHY.search(text):
        answer = explain(conn, text, close=close)
        return [post(room, _say(answer["summary_text"], question=text), thread,
                     {"matched_documents": answer["matched_documents"]})]

    if (is_command and event.get("command", "collect") == "collect") or _COLLECT.search(text):
        if close is None:
            return [post(room, "No close is open, so there is nothing to collect for. Ask @carbon-room to start "
                               "one (\"close October\").", thread)]
        report = core.ingest(close["id"], conn=conn)
        return [post(room, _say(report["summary_text"]), thread,
                     {"close_id": close["id"], "statement": report["statement"]}),
                targeted("@carbon-room", f"Collection done for {close['id']}: {report['statement']}.",
                         {"event": "collected", "close_id": close["id"], "statement": report["statement"],
                          "statement_complete": report["statement_complete"],
                          "claims_created": report["claims_created"]})]

    return [post(room, f"I'm {HANDLE}: I ingest sources into the ledger (every claim UNVERIFIED) and report what I "
                       "collected. Try: \"collect\", \"status\", \"why didn't you consider INV-204B?\", or drop a "
                       "file in a thread.", thread)]


def collector_node(state: dict[str, Any]) -> dict[str, Any]:
    """LangGraph-ready node: reads state["close_id"] (and optional "files", "db_path"); returns
    {"ingest_reports": [report]} - a list, so parallel branches merge with an operator.add reducer."""
    from carbonroom import core

    conn = db.connect(state.get("db_path")) if state.get("db_path") else db.connect()
    try:
        report = core.ingest(state["close_id"], files=state.get("files"), conn=conn)
    finally:
        conn.close()
    return {"ingest_reports": [report]}
