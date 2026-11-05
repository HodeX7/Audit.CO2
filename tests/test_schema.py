from __future__ import annotations

import sqlite3

from carbon_room.ledger import init_db


def test_init_is_idempotent_and_contract_uniques_hold(db):
    init_db(db)
    db.execute(
        "INSERT INTO closes VALUES (?, ?, ?, ?, ?, ?, ?, ? ,NULL,NULL,NULL)",
        ("2026-10-v1", "2026-10", "[]", "FS-test", "OPEN", 1, "system", "message-1"),
    )
    source = ("SRC-0001", "2026-10-v1", None, "utility_pdf", "bill.pdf", "var/store/x.pdf", "hash", 1,
              "text", None, None, "OK", None, "collector", "2026-11-05T00:00:00Z")
    db.execute("INSERT INTO sources VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", source)
    with __import__("pytest").raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO sources VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", source)
    gap = ("G-1", "2026-10-v1", "F-abc", "R1", "MISSING", "missing", "lead", "OPEN", "[]", "[]",
           None, "2026-11-05T00:00:00Z", None, None, None)
    db.execute("INSERT INTO gaps VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", gap)
    with __import__("pytest").raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO gaps VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", gap)
