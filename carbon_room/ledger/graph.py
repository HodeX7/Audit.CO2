"""Ledger lineage queries for P2's trace and P1's fact-safe explanation boundary."""

from __future__ import annotations

import sqlite3

from carbon_room.ledger import ledger


def chain(conn: sqlite3.Connection, claim_id: str) -> dict:
    """Return the complete evidence lineage, naming the first missing required hop."""
    claim = ledger.get_claim(conn, claim_id)
    source = conn.execute("SELECT * FROM sources WHERE source_doc_id=?", (claim.source_doc_id,)).fetchone()
    calculation = conn.execute(
        "SELECT * FROM calculations WHERE claim_id=? AND superseded_by IS NULL ORDER BY created_at DESC LIMIT 1", (claim_id,)
    ).fetchone()
    factor = conn.execute("SELECT * FROM factors WHERE factor_id=?", (claim.factor_id,)).fetchone() if claim.factor_id else None
    gaps = [dict(row) for row in conn.execute("SELECT * FROM gaps WHERE claim_ids LIKE ?", (f'%"{claim_id}"%',))]
    approvals = [dict(row) for row in conn.execute("SELECT * FROM approvals WHERE subject_id=?", (claim_id,))]
    result = {"claim": claim, "source": dict(source) if source else None, "factor": dict(factor) if factor else None,
              "calculation": dict(calculation) if calculation else None, "gaps": gaps, "approvals": approvals,
              "complete": False, "missing": None}
    for name in ("source", "calculation", "factor"):
        if result[name] is None:
            result["missing"] = name
            return result
    result["complete"] = True
    return result
