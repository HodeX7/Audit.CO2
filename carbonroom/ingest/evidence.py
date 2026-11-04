"""Evidence re-check for one activity - a read-only helper for Richa's checker.

Ingestion owns the evidence; the checker owns the decision. This module only REPORTS:
  * does the source file still exist and hash to the recorded sha256?
  * is the stored excerpt still on the recorded page, and does its hash still match?
  * has the source document been superseded, and is the excerpt in the CURRENT version?
    (If not, a VERIFIED row is a "false done" and the checker should reopen it.)
"""

from __future__ import annotations

import sqlite3
from typing import Any

from carbonroom.ingest import extract
from carbonroom.ingest.hashing import excerpt_sha256, sha256_file
from carbonroom.ledger import db


def evidence_status(conn: sqlite3.Connection, activity_id: str) -> dict[str, Any]:
    act = db.get_activity(conn, activity_id)
    if act is None:
        raise db.LedgerError(f"unknown activity {activity_id}")
    doc = db.get_source_doc(conn, act["source_doc_id"])
    page = extract.locator_page(act["excerpt_locator"])
    path = extract.resolve_doc_path(doc["path"])
    problems: list[str] = []

    file_ok = path.exists() and sha256_file(path) == doc["sha256"]
    if not path.exists():
        problems.append(f"source file is missing: {doc['path']}")
    elif not file_ok:
        problems.append(f"source file changed since it was recorded: {doc['path']}")
    hash_ok = excerpt_sha256(act["excerpt"]) == act["excerpt_sha256"]
    if not hash_ok:
        problems.append("stored excerpt does not match its excerpt_sha256")
    excerpt_ok = file_ok and extract.excerpt_in_document(path, act["excerpt"], page)
    if file_ok and not excerpt_ok:
        problems.append(f"excerpt is no longer on {act['excerpt_locator']} of its document")

    current = db.current_doc(conn, doc["id"])
    superseded = current["id"] != doc["id"]
    in_current = True
    replacement_ids: list[str] = []
    if superseded:
        in_current = extract.excerpt_in_document(current["path"], act["excerpt"])
        replacement_ids = [
            a["id"]
            for a in db.list_activities(conn, source_doc_id=current["id"], include_superseded=False)
            if activity_id in ((a["extra"] or {}).get("replaces_activity_ids") or [])
        ]
        if not in_current:
            problems.append(
                f"source {doc['doc_ref'] or doc['id']} was replaced by {current['doc_ref'] or current['id']}, "
                f"and this excerpt is not in the corrected document"
            )
    return {
        "activity_id": activity_id,
        "status": act["status"],
        "ok": not problems,
        "file_ok": file_ok,
        "excerpt_hash_ok": hash_ok,
        "excerpt_on_page": excerpt_ok,
        "source_superseded": superseded,
        "current_doc_id": current["id"],
        "current_doc_ref": current["doc_ref"],
        "excerpt_in_current_doc": in_current,
        "replacement_activity_ids": replacement_ids,
        "problems": problems,
    }
