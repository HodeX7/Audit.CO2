"""`carbonroom seed`: reset the ledger and load the fictional seed company.

Loads data/seed/sites.json (sites, owners, rooms, expected documents), opens the demo periods,
and ingests every document in data/seed/manifest.json whose folder is `docs`. Documents in
`later/` are held back for the live demo (the missing Reno bill and the corrected Austin bill);
ingest them with `carbonroom ingest data/seed/later/<file> --from <owner> --room <room>`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from carbonroom import config
from carbonroom.ingest import pipeline, seedgen
from carbonroom.ledger import db

ACTOR = "seed"


def load_sites(conn, sites_file: Path) -> dict[str, Any]:
    data = json.loads(sites_file.read_text(encoding="utf-8"))
    for site in data["sites"]:
        db.upsert_site(
            conn,
            id=site["id"],
            name=site["name"],
            region=site.get("region"),
            grid_subregion=site.get("grid_subregion"),
            owner_handle=site.get("owner_handle"),
            room=site.get("room"),
            kind=site.get("kind", "facility"),
            aliases=site.get("aliases", []),
            actor=ACTOR,
        )
        for exp in site.get("expected", []):
            db.upsert_expected_document(
                conn,
                site_id=site["id"],
                category=exp["category"],
                doc_kind=exp["doc_kind"],
                frequency=exp.get("frequency", "monthly"),
                owner_handle=site.get("owner_handle"),
                note=exp.get("note"),
                actor=ACTOR,
            )
    for period in data.get("periods", []):
        db.ensure_period(conn, period, factor_set_version=config.factor_set(), actor=ACTOR)
    return data


def manifest(seed_dir: Path | None = None) -> list[dict[str, Any]]:
    seed_dir = seed_dir or config.seed_dir()
    return json.loads((seed_dir / "manifest.json").read_text(encoding="utf-8"))


def run_seed(
    db_path: str | Path | None = None,
    *,
    regenerate_docs: bool = False,
    include_later: bool = False,
    proposer: str | None = None,
    refresh_cache: bool = False,
) -> dict[str, Any]:
    seed_dir = config.seed_dir()
    if regenerate_docs or not (seed_dir / "manifest.json").exists():
        seedgen.generate(seed_dir)
    db_file = db.reset_db_file(db_path)
    conn = db.connect(db_file)
    try:
        load_sites(conn, seed_dir / "sites.json")
        results = []
        for entry in manifest(seed_dir):
            if entry["folder"] != "docs" and not include_later:
                continue
            results.append(
                pipeline.ingest_file(
                    conn,
                    seed_dir / entry["path"],
                    received_from=entry["received_from"],
                    room=entry["room"],
                    meta={"seed_traps": entry["traps"]},
                    proposer=proposer,
                    refresh_cache=refresh_cache,
                )
            )
        held_back = [e["path"] for e in manifest(seed_dir) if e["folder"] != "docs" and not include_later]
        return {
            "db": str(db_file),
            "documents": len(results),
            "activities": sum(len(r["activities"]) for r in results),
            "instruments": sum(len(r["instruments"]) for r in results),
            "gaps": sum(len(r["gaps"]) for r in results),
            "held_back": held_back,
            "results": results,
        }
    finally:
        conn.close()
