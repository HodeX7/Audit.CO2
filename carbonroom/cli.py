"""`carbonroom` command line.

Base commands (Ujjwal): init, seed, ingest, extract, ledger, llm.
Teammates add their own commands WITHOUT editing this file: create a module with a
`register(subparsers)` function at one of PLUGIN_MODULES (e.g. carbonroom/calc/cli.py) and it is
picked up automatically. See docs/HANDOFF.md.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

from carbonroom import __version__, config

PLUGIN_MODULES = (
    "carbonroom.calc.cli",
    "carbonroom.check.cli",
    "carbonroom.report.cli",
    "carbonroom.switchbridge.cli",
)


def _print_json(data: Any) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def _connect(args, create: bool = False):
    from carbonroom.ledger import db

    return db.connect(args.db, create=create) if args.db else db.connect(create=create)


def _fmt_qty(q: str) -> str:
    d = Decimal(q)
    if d == d.to_integral_value():
        return f"{int(d):,}"
    return f"{d:,}"


# ---------------------------------------------------------------------------
# init / seed
# ---------------------------------------------------------------------------


def cmd_init(args) -> int:
    conn = _connect(args, create=True)
    print(f"ledger ready: {args.db or config.db_path()}")
    conn.close()
    return 0


def cmd_seed(args) -> int:
    from carbonroom.ingest.seed import run_seed

    summary = run_seed(
        args.db,
        regenerate_docs=args.regenerate_docs,
        include_later=args.with_later,
        proposer=args.proposer,
        refresh_cache=args.refresh_cache,
    )
    if args.json:
        _print_json(summary)
        return 0
    print(f"Seeded {summary['db']}: {summary['documents']} documents, {summary['activities']} activities "
          f"(all UNVERIFIED), {summary['instruments']} instrument(s), {summary['gaps']} gap(s).")
    for r in summary["results"]:
        acts = ", ".join(f"{a['category']} {_fmt_qty(a['quantity'])} {a['unit']}" for a in r["activities"])
        ins = ", ".join(f"{i['kind']} {_fmt_qty(i['mwh'])} MWh" for i in r["instruments"])
        print(f"  {r['doc_ref'] or Path(r['file']).name:<22} {r['site'] or '?':<13} {r['period'] or '?':<8} "
              f"{acts or ins}  [{r['proposer']}]")
    if summary["held_back"]:
        print("Held back for the live demo (ingest them during the demo):")
        for path in summary["held_back"]:
            print(f"  data/seed/{path}")
    return 0


# ---------------------------------------------------------------------------
# ingest / extract
# ---------------------------------------------------------------------------


def _print_result(r: dict[str, Any]) -> None:
    name = Path(r["file"]).name
    if r["status"] == "duplicate":
        print(f"= {name}: already in the ledger as {r['doc_id']} (skipped)")
        return
    print(f"+ {name} -> {r['doc_id']} {r['kind']} {r['doc_ref'] or ''} [{r.get('proposer')}]")
    for a in r["activities"]:
        replaces = f" (replaces {', '.join(a['replaces_activity_ids'])})" if a["replaces_activity_ids"] else ""
        print(f"    {a['id']} {a['site']} {a['period']} {a['category']} {_fmt_qty(a['quantity'])} {a['unit']} "
              f"{a['status']} @ {a['locator']}{replaces}")
    for i in r["instruments"]:
        print(f"    {i['id']} {i['kind']} {_fmt_qty(i['mwh'])} MWh region={i['region']} vintage={i['vintage']}")
    for s in r["supersedes"]:
        print(f"    supersedes document(s) {', '.join(s['old_docs'])}")
    for g in r["gaps"]:
        print(f"    {g['id']} {g['kind']} -> @{g['owner']} in {g['room']}: {g['detail']}")
    for note in r.get("notes") or []:
        print(f"    note: {note}")


def cmd_ingest(args) -> int:
    from carbonroom.ingest import pipeline

    conn = _connect(args, create=True)
    meta = {k: v for k, v in {"thread_id": args.thread, "message_id": args.message, "gap_id": args.gap}.items() if v}
    emit = (lambda r: print(json.dumps(r, ensure_ascii=False, default=str), flush=True)) if args.json else _print_result
    try:
        if args.watch:
            folder = Path(args.paths[0]) if args.paths else config.inbox_dir()
            print(f"watching {folder} every {args.interval}s (Ctrl-C to stop)", file=sys.stderr)
            pipeline.watch(conn, folder, interval=args.interval, proposer=args.proposer,
                           move_processed=not args.keep, on_result=emit)
            return 0
        if not args.paths:
            print("give a file or folder, or use --watch", file=sys.stderr)
            return 2
        if args.workers > 1 or args.summary or args.run_id or args.period:
            return _ingest_batch(conn, args, meta)
        results = pipeline.ingest_paths(
            conn, args.paths, received_from=args.sender, room=args.room, meta=meta or None,
            proposer=args.proposer, refresh_cache=args.refresh_cache, move_processed=args.move_processed,
        )
    except KeyboardInterrupt:
        return 0
    finally:
        conn.close()
    if args.json:
        _print_json({"type": "cr.ingest.v1", "results": results})
    else:
        for r in results:
            _print_result(r)
    return 0


def _ingest_batch(conn, args, meta) -> int:
    """Background batch run: parallel, one final summary (see docs/features/batch-run.md)."""
    from carbonroom.ingest import batch

    summary = batch.run_batch(
        conn, args.paths, workers=args.workers, received_from=args.sender, room=args.room, meta=meta or None,
        proposer=args.proposer, refresh_cache=args.refresh_cache, run_id=args.run_id,
        periods=[args.period] if args.period else None,
    )
    if args.summary:
        summary.pop("results", None)
        if args.json:
            _print_json(summary)
        else:
            print(f"{summary['run_id']}: {summary['summary_text']}")
            for err in summary["errors"]:
                print(f"  failed: {err['file']}: {err['error']}")
        return 0
    if args.json:
        results = summary.pop("results")
        _print_json({"type": "cr.ingest.v1", "results": results, "summary": summary})
    else:
        for r in summary["results"]:
            _print_result(r)
        print(f"\n{summary['run_id']}: {summary['summary_text']}")
    return 0


def cmd_ledger_trace(args) -> int:
    """Where did this come from? A number gets its full lineage; anything else, its outgoing graph."""
    from carbonroom.ledger import graph

    conn = _connect(args)
    node_type, node_id = graph.resolve(conn, args.ref)
    if node_type in ("activity", "calculation"):
        data = graph.lineage(conn, f"{node_type}:{node_id}")
        conn.close()
        if args.json:
            _print_json({k: v for k, v in data.items() if k != "text"})
        else:
            print(data["text"])
        return 0
    walked = graph.walk(conn, node_type, node_id, direction="out", max_depth=args.depth)
    conn.close()
    print(graph.to_json(walked) if args.json else "\n".join(graph.tree_lines(walked)))
    return 0


def cmd_ledger_impact(args) -> int:
    """What depends on this? (e.g. a bill -> its numbers -> their calculations, and gaps about them)"""
    from carbonroom.ledger import graph

    conn = _connect(args)
    walked = graph.impact(conn, args.ref, max_depth=args.depth)
    conn.close()
    if args.json:
        print(graph.to_json(walked))
        return 0
    print("\n".join(graph.tree_lines(walked)))
    deps = walked["depends"]
    summary = ", ".join(f"{len(v)} {graph.plural(k, len(v))}" for k, v in sorted(deps.items())) or "nothing"
    print(f"\nDepends on {walked['start']}: {summary}")
    return 0


def cmd_ledger_graph(args) -> int:
    """One month as a knowledge graph, as Mermaid (renders on GitHub) or JSON."""
    from carbonroom.ledger import graph

    conn = _connect(args)
    g = graph.period_graph(conn, args.period, max_depth=args.depth, site=args.site)
    conn.close()
    text = graph.to_json(g) if args.format == "json" else graph.to_mermaid(g)
    if args.out:
        body = text if args.format == "json" or not args.out.endswith(".md") else f"```mermaid\n{text}```\n"
        Path(args.out).write_text(body, encoding="utf-8")
        print(f"wrote {args.out}: {len(g['nodes'])} nodes, {len(g['edges'])} edges", file=sys.stderr)
    else:
        print(text, end="")
    return 0


def cmd_ledger_runs(args) -> int:
    from carbonroom.ingest import batch

    conn = _connect(args)
    data = batch.get_run(conn, args.id) if args.id else batch.list_runs(conn, limit=args.limit)
    conn.close()
    if args.id and data is None:
        print(f"no finished run {args.id}", file=sys.stderr)
        return 1
    if args.json:
        _print_json(data)
    elif args.id:
        print(f"{data['run_id']} ({data['finished_at']}, {data['seconds']}s, {data['workers']} workers)")
        print(data["summary_text"])
        for err in data.get("errors") or []:
            print(f"  failed: {err['file']}: {err['error']}")
    else:
        for run in data:
            print(f"{run['run_id']}  {run['finished_at']}  {run['summary_text']}")
        if not data:
            print("no runs yet")
    return 0


def cmd_extract(args) -> int:
    """Dry run: propose + verify one file, write nothing to the ledger."""
    from carbonroom.ingest import extract
    from carbonroom.ingest.hashing import sha256_file

    conn = _connect(args, create=True)
    out = []
    for target in args.paths:
        path = Path(target)
        pages = extract.read_pages(path)
        sha = sha256_file(path)
        proposed = extract.propose(path, pages, sha, mode=args.proposer or "auto", refresh=args.refresh_cache)
        ex = extract.verify(proposed.proposal, pages, extract.site_matcher_for(conn), proposed.proposer)
        out.append({
            "file": str(path),
            "sha256": sha,
            "proposer": proposed.proposer,
            "proposal": proposed.proposal,
            "verified": {
                "site": ex.site_id,
                "period": ex.period,
                "doc_ref": ex.doc_ref.value if ex.doc_ref else None,
                "claims": [{"category": c.category, "quantity": str(c.normalized.quantity), "unit": c.normalized.unit,
                            "excerpt": c.excerpt, "locator": c.locator,
                            "fields": {k: v.value for k, v in c.fields.items()}} for c in ex.claims],
                "instruments": [{"kind": i.kind, "mwh": str(i.normalized.quantity), "excerpt": i.excerpt,
                                 "fields": {k: v.value for k, v in i.fields.items()}} for i in ex.instruments],
            },
            "rejected": [{"scope": f.scope, "reason": f.reason} for f in ex.failures],
        })
    conn.close()
    if args.json:
        _print_json(out)
    else:
        for item in out:
            print(f"{item['file']} [{item['proposer']}] site={item['verified']['site']} period={item['verified']['period']}")
            for c in item["verified"]["claims"]:
                print(f"  OK  {c['category']} {c['quantity']} {c['unit']} @ {c['locator']}: {c['excerpt']}")
            for i in item["verified"]["instruments"]:
                print(f"  OK  {i['kind']} {i['mwh']} MWh: {i['excerpt']} {i['fields']}")
            for f in item["rejected"]:
                print(f"  REJECTED ({f['scope']}): {f['reason']}")
    return 0


# ---------------------------------------------------------------------------
# ledger
# ---------------------------------------------------------------------------


def cmd_ledger_show(args) -> int:
    from carbonroom.ledger import db

    conn = _connect(args)
    period = db.get_period(conn, args.period)
    if period is None:
        print(f"no period {args.period} in the ledger", file=sys.stderr)
        return 1
    acts = db.list_activities(conn, period_id=args.period, site_id=args.site, status=args.status)
    print(f"Period {args.period} [{period['status']}] factor set: {period['factor_set_version'] or '-'}")
    print(f"{'ID':<15}{'SITE':<14}{'CATEGORY':<15}{'QUANTITY':>14} {'UNIT':<6}{'STATUS':<12}{'DOC':<18}{'WHERE':<16}EXCERPT")
    for a in acts:
        doc = db.get_source_doc(conn, a["source_doc_id"])
        flag = " (doc superseded)" if doc["superseded_by"] else ""
        excerpt = a["excerpt"] if len(a["excerpt"]) <= 70 else a["excerpt"][:67] + "..."
        print(f"{a['id']:<15}{a['site_id']:<14}{a['category']:<15}{_fmt_qty(a['quantity']):>14} {a['unit']:<6}"
              f"{a['status']:<12}{(doc['doc_ref'] or doc['id']):<18}{a['excerpt_locator']:<16}{excerpt}{flag}")
    instruments = db.list_instruments(conn, period_id=args.period)
    if instruments:
        print("\nInstruments")
        for i in instruments:
            print(f"  {i['id']} {i['kind']} {i['certificate_id']} {_fmt_qty(i['mwh'])} MWh region={i['region']} "
                  f"vintage={i['vintage']} for={i['site_id']} status={i['status']} flags={i['quality_flags']}")
    missing = db.expected_but_missing(conn, args.period)
    if missing:
        print("\nExpected but missing")
        for m in missing:
            print(f"  {m['site_name']} {m['category']} ({m['doc_kind']}) - owner @{m['owner_handle']} in {m['room']}")
    gaps = db.list_gaps(conn, period_id=args.period)
    if gaps:
        print("\nGaps")
        for g in gaps:
            print(f"  {g['id']} {g['status']:<13}{g['kind']:<18}@{g['owner_handle']} {g['detail']}")
    counts: dict[str, int] = {}
    for a in acts:
        counts[a["status"]] = counts.get(a["status"], 0) + 1
    print("\n" + ", ".join(f"{k}: {v}" for k, v in sorted(counts.items())) if counts else "\n(no activities)")
    conn.close()
    return 0


def cmd_ledger_export(args) -> int:
    from carbonroom.ledger import db

    conn = _connect(args)
    data = db.export_period(conn, args.period)
    conn.close()
    text = json.dumps(data, indent=2, ensure_ascii=False, default=str)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(text)
    return 0


def cmd_ledger_gaps(args) -> int:
    from carbonroom.ledger import db

    conn = _connect(args)
    gaps = db.list_gaps(conn, period_id=args.period, status=args.status)
    conn.close()
    if args.json:
        _print_json(gaps)
    else:
        for g in gaps:
            print(f"{g['id']} {g['status']:<13}{g['kind']:<18}{g['period_id'] or '-':<8} @{g['owner_handle']} "
                  f"({g['room']}) {g['detail']}")
        if not gaps:
            print("no gaps")
    return 0


def cmd_ledger_events(args) -> int:
    from carbonroom.ledger import db

    conn = _connect(args)
    events = db.list_events(conn, limit=args.limit, ref=args.ref)
    conn.close()
    if args.json:
        _print_json(events)
    else:
        for e in reversed(events):
            print(f"{e['id']:>5} {e['at']} {e['actor']:<16}{e['action']:<24}{e['ref'] or ''} {json.dumps(e['detail'])}")
    return 0


def cmd_ledger_missing(args) -> int:
    from carbonroom.ledger import db

    conn = _connect(args)
    missing = db.expected_but_missing(conn, args.period)
    conn.close()
    if args.json:
        _print_json(missing)
    else:
        for m in missing:
            print(f"{m['site_name']} {m['category']} for {m['period_id']}: missing - owner @{m['owner_handle']} "
                  f"in {m['room']}")
        if not missing:
            print("nothing missing")
    return 0


def cmd_ledger_closes(args) -> int:
    """Read-only: each close's locked boundary and factor set, phase and publish record."""
    from carbonroom.ledger import db

    conn = _connect(args)
    closes = db.list_closes(conn, args.period)
    conn.close()
    if args.json:
        _print_json(closes)
        return 0
    for c in closes:
        published = (f", published by @{c['published_by']} (message {c['published_message_id']})"
                     if c["published_by"] else "")
        print(f"{c['id']} {c['phase']}: sites {', '.join(c['sites'])}; factor set {c['factor_set']}; "
              f"started by @{c['started_by']}{published}")
    if not closes:
        print("no closes yet")
    return 0


def cmd_ledger_verify(args) -> int:
    """Integrity check: every document still hashes the same, every excerpt is still on its page."""
    from carbonroom.ingest import extract
    from carbonroom.ingest.hashing import excerpt_sha256, sha256_file
    from carbonroom.ledger import db

    conn = _connect(args)
    problems = 0
    checked = 0
    bad_docs = set()
    for doc in db.list_source_docs(conn):
        path = extract.resolve_doc_path(doc["path"])
        if not path.exists():
            print(f"FAIL {doc['id']} file missing: {doc['path']}")
            problems += 1
            bad_docs.add(doc["id"])
        elif sha256_file(path) != doc["sha256"]:
            print(f"FAIL {doc['id']} sha256 changed: {doc['path']}")
            problems += 1
            bad_docs.add(doc["id"])
    for a in db.list_activities(conn, period_id=args.period):
        checked += 1
        doc = db.get_source_doc(conn, a["source_doc_id"])
        page = extract.locator_page(a["excerpt_locator"])
        ok = (doc["id"] not in bad_docs and excerpt_sha256(a["excerpt"]) == a["excerpt_sha256"]
              and extract.excerpt_in_document(doc["path"], a["excerpt"], page))
        if not ok:
            problems += 1
        if not ok or args.verbose:
            print(f"{'OK  ' if ok else 'FAIL'} {a['id']} {a['excerpt_locator']} of {doc['path']}: {a['excerpt']}")
    chain = db.verify_audit_chain(conn)
    conn.close()
    for p in chain["problems"]:
        print(f"FAIL event {p['id']}: {p['problem']}")
    head = chain["head"]
    print(f"{'OK  ' if chain['ok'] else 'FAIL'} audit chain: {chain['events']} events"
          + (f", {chain['broken']} broken link(s)" if chain["broken"] else "")
          + (f", head #{head['id']} {head['event_hash'][:16]}" if head and head["event_hash"] else ""))
    problems += chain["broken"]
    print(f"{checked} activities checked, {problems} problem(s)")
    return 1 if problems else 0


# ---------------------------------------------------------------------------
# llm
# ---------------------------------------------------------------------------


def _use_provider(args) -> None:
    """`--provider X` on any llm command = LLM_PROVIDER=X for this run only."""
    import os

    if getattr(args, "provider", None):
        os.environ["LLM_PROVIDER"] = args.provider


def cmd_llm_providers(args) -> int:
    from carbonroom import llm

    rows = llm.describe_providers()
    if args.json:
        _print_json(rows)
        return 0
    print(f"{'':2}{'PROVIDER':<19}{'KEY':<22}{'BASE URL':<42}NOTE")
    for r in rows:
        key = r["key_env"] + (" (set)" if r["key_set"] and r["key_env"] != "-" else "")
        print(f"{'*' if r['active'] else ' ':2}{r['name']:<19}{key:<22}{r['base_url']:<42}{r['note']}")
    print("\n* = active (LLM_PROVIDER). Any OpenAI-compatible server works with LLM_PROVIDER=openai_compatible "
          "+ LLM_BASE_URL.")
    return 0


def _listed_models(llm, args) -> list[str]:
    import re

    ids = llm.list_models()
    if getattr(args, "chat", True):
        ids = [m for m in ids if llm.looks_like_chat_model(m)]
    if args.grep:
        ids = [m for m in ids if re.search(args.grep, m, re.IGNORECASE)]
    return ids


def cmd_llm_models(args) -> int:
    from carbonroom import llm

    _use_provider(args)
    try:
        for model_id in _listed_models(llm, args):
            print(model_id)
    except llm.LLMNotConfigured as exc:
        print(f"not configured: {exc}", file=sys.stderr)
        return 2
    except llm.LLMError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def cmd_llm_probe(args) -> int:
    """One tiny call per model: which listed models actually answer for this key?"""
    from carbonroom import llm

    _use_provider(args)
    try:
        if args.models:
            models = [m.strip() for m in args.models.split(",") if m.strip()]
        else:
            models = _listed_models(llm, args)[: args.limit]
    except llm.LLMNotConfigured as exc:
        print(f"not configured: {exc}", file=sys.stderr)
        return 2
    if not models:
        print("no models matched", file=sys.stderr)
        return 1
    print(f"probing {len(models)} model(s), about {max(1, round(len(models) * 60 / 35 / 60))} min at the rate limit",
          file=sys.stderr)
    working = []
    for model in models:
        r = llm.probe(model)
        if r["ok"]:
            working.append(model)
            note = "JSON ok" if r["json_ok"] else "answers, but not clean JSON"
            print(f"OK    {model:<55}{r['seconds']:>6.1f}s  {note}", flush=True)
        else:
            print(f"FAIL  {model:<55}{r['seconds']:>6.1f}s  HTTP {r['status']}: {r['error'][-90:]}", flush=True)
    print(f"\n{len(working)} working. Next: carbonroom llm bench --models {','.join(working[:4])}" if working
          else "\nnone working")
    return 0 if working else 1


def cmd_llm_bench(args) -> int:
    """Try 2-3 models on every seed document and score them against the rules baseline."""
    from carbonroom import llm
    from carbonroom.ingest import extract, rules
    from carbonroom.ingest.seed import manifest

    _use_provider(args)
    try:
        default_model = llm.provider(need_model=False, task="extract").model
    except llm.LLMNotConfigured as exc:
        print(f"not configured: {exc}", file=sys.stderr)
        return 2
    models = [m.strip() for m in (args.models or "").split(",") if m.strip()] or ([default_model] if default_model else [])
    if not models:
        print("give --models a,b,c (find working ones with `carbonroom llm probe`)", file=sys.stderr)
        return 2
    conn = _connect(args)
    matcher = extract.site_matcher_for(conn)
    entries = manifest()
    rows = []
    for model in models:
        score = {"model": model, "docs": 0, "exact": 0, "rejected": 0, "errors": 0, "seconds": 0.0, "note": ""}
        failures_in_a_row = 0
        for entry in entries:
            path = config.seed_dir() / entry["path"]
            pages = extract.read_pages(path)
            expected = extract.verify(rules.propose(pages), pages, matcher, "rules")
            want = sorted((c.category, str(c.normalized.quantity)) for c in expected.claims) + sorted(
                ("REC", str(i.normalized.quantity)) for i in expected.instruments)
            score["docs"] += 1
            started = time.monotonic()
            try:
                proposal, _ = extract.llm_propose(path.name, pages, model=model, attempts=2)
            except Exception as exc:  # noqa: BLE001 - report and continue
                score["errors"] += 1
                failures_in_a_row += 1
                print(f"  {model} {path.name}: error {exc}", file=sys.stderr)
                if getattr(exc, "status_code", None) in llm.UNAVAILABLE_STATUS:
                    score["note"] = f"unavailable (HTTP {exc.status_code}); skipped the other documents"
                    break
                if failures_in_a_row >= 2:
                    score["note"] = "unreliable (2 failures in a row); skipped the other documents"
                    break
                continue
            finally:
                score["seconds"] += time.monotonic() - started
            failures_in_a_row = 0
            got_ex = extract.verify(proposal, pages, matcher, model)
            got = sorted((c.category, str(c.normalized.quantity)) for c in got_ex.claims) + sorted(
                ("REC", str(i.normalized.quantity)) for i in got_ex.instruments)
            score["rejected"] += len(got_ex.failures)
            if got == want and got_ex.site_id == expected.site_id and got_ex.period == expected.period:
                score["exact"] += 1
            elif args.verbose:
                print(f"  {model} {path.name}: got {got} want {want} rejected={[f.reason for f in got_ex.failures]}")
        rows.append(score)
    conn.close()
    total = len(entries)
    print(f"{'MODEL':<45}{'EXACT':>8}{'REJECTED':>10}{'ERRORS':>8}{'SEC':>8}  NOTE")
    for s in rows:
        print(f"{s['model']:<45}{s['exact']:>4}/{total:<3}{s['rejected']:>10}{s['errors']:>8}{s['seconds']:>8.1f}  "
              f"{s['note']}")
    print("Record the winner in docs/DECISIONS.md and set LLM_MODEL in .env.")
    return 0


# ---------------------------------------------------------------------------
# graphdb (the knowledge graph in Neo4j; see docs/features/knowledge-graph.md)
# ---------------------------------------------------------------------------


def _graphdb_store():
    from carbonroom.graphdb import store

    if not store.reachable():
        print(f"Neo4j isn't reachable at {store.settings()['uri']}. Start it with:\n"
              "  docker compose -f infra/neo4j/docker-compose.yml up -d", file=sys.stderr)
        return None
    return store.Neo4jStore()


def _with_graphdb(fn):
    neo = _graphdb_store()
    if neo is None:
        return None, 2
    try:
        return fn(neo), 0
    finally:
        neo.close()


def _emit(args, data, text_fn) -> int:
    if getattr(args, "json", False):
        _print_json(data)
    else:
        text_fn(data)
    return 0


def cmd_graphdb_status(args) -> int:
    from carbonroom.graphdb import store

    conn = _connect(args)
    st = store.status(conn)
    conn.close()

    def text(s):
        print(f"mode={s['mode']} uri={s['uri']} reachable={s['reachable']}")
        if s.get("error"):
            print(f"error: {s['error']}")
        if s.get("synced_at"):
            state = "in sync" if s["in_sync"] else f"behind (ledger event {s['ledger_event_id']}, graph {s['event_id']})"
            print(f"last sync {s['synced_at']}: {s['nodes']} nodes, {s['relationships']} links, {state}")
            print("  " + ", ".join(f"{k}: {v}" for k, v in s.get("counts", {}).items()))
        elif s["reachable"]:
            print("never synced: run `carbonroom graphdb sync`")

    return _emit(args, st, text)


def cmd_graphdb_sync(args) -> int:
    from carbonroom.graphdb import store

    neo = _graphdb_store()
    if neo is None:
        return 2
    conn = _connect(args)
    try:
        result = store.sync(conn, neo)
    finally:
        conn.close()
        neo.close()
    return _emit(args, result, lambda r: print(
        f"synced {r['nodes']} nodes and {r['relationships']} links (ledger event {r['event_id']}): "
        + ", ".join(f"{k} {v}" for k, v in r["counts"].items())))


def cmd_graphdb_why(args) -> int:
    from carbonroom.graphdb import queries

    data, code = _with_graphdb(lambda neo: queries.why(neo, args.site, args.period))
    if code:
        return code
    if data is None:
        print(f"unknown site {args.site} (or the graph isn't synced yet)", file=sys.stderr)
        return 1
    return _emit(args, data, lambda d: print(d["summary"]))


def cmd_graphdb_conflicts(args) -> int:
    from carbonroom.graphdb import queries

    data, code = _with_graphdb(lambda neo: queries.conflicts(neo, args.period))
    if code:
        return code

    def text(rows):
        for r in rows:
            claims = " vs ".join(f"{c.get('doc_ref') or c['id']} {c['quantity']} {c['unit']}" for c in r["claims"])
            print(f"{r['delivery']}: {claims}")
        if not rows:
            print("no conflicting deliveries")

    return _emit(args, data, text)


def cmd_graphdb_gaps(args) -> int:
    from carbonroom.graphdb import queries

    data, code = _with_graphdb(queries.gaps_by_owner)
    if code:
        return code

    def text(rows):
        for r in rows:
            print(f"@{r['owner']}: " + "; ".join(f"{g['id']} {g['kind']}" for g in r["gaps"]))
        if not rows:
            print("no open gaps")

    return _emit(args, data, text)


def cmd_graphdb_find(args) -> int:
    from carbonroom.graphdb import queries

    data, code = _with_graphdb(lambda neo: queries.find(neo, args.text, args.limit))
    if code:
        return code

    def text(rows):
        for r in rows:
            print(f"{r['label']:<12}{r['id']:<22}{r['summary'] or ''}")
        if not rows:
            print("nothing found")

    return _emit(args, data, text)


def cmd_graphdb_query(args) -> int:
    from carbonroom.graphdb import queries

    params = dict(item.partition("=")[::2] for item in args.param or [])
    try:
        data, code = _with_graphdb(lambda neo: queries.read_only(neo, args.cypher, params))
    except queries.QueryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if code:
        return code
    _print_json(data)
    return 0


def cmd_graphdb_selftest(args) -> int:
    from carbonroom.graphdb import queries

    neo = _graphdb_store()
    if neo is None:
        return 2
    conn = _connect(args)
    try:
        rows = queries.selftest(conn, neo)
    finally:
        conn.close()
        neo.close()
    for name, ok, detail in rows:
        print(f"{'OK  ' if ok else 'FAIL'} {name}" + (f": {detail}" if detail else ""))
    failed = sum(1 for _, ok, _ in rows if not ok)
    print(f"{len(rows) - failed}/{len(rows)} passed")
    return 1 if failed else 0


# ---------------------------------------------------------------------------
# parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="carbonroom", description="Carbon Room: month-end emissions close, run from chat.")
    parser.add_argument("--version", action="version", version=f"carbonroom {__version__}")
    parser.add_argument("--db", help="ledger file (default: CR_DB_PATH or ./carbonroom.db)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="create an empty ledger")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("seed", help="reset the ledger and load the fictional seed company (minus held-back docs)")
    p.add_argument("--regenerate-docs", action="store_true", help="rebuild the seed PDFs first")
    p.add_argument("--with-later", action="store_true", help="also load the held-back documents")
    p.add_argument("--proposer", choices=["auto", "rules", "llm"], help="default: CR_PROPOSER or auto")
    p.add_argument("--refresh-cache", action="store_true", help="ignore cached extractions")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_seed)

    p = sub.add_parser("ingest", help="ingest files or folders into the ledger")
    p.add_argument("paths", nargs="*", help="files or folders (default with --watch: data/inbox)")
    p.add_argument("--from", dest="sender", help="chat handle of the sender (e.g. lena)")
    p.add_argument("--room", help="Switch room the file came from (e.g. cr-site-reno)")
    p.add_argument("--thread", help="chat thread id (kept with the document)")
    p.add_argument("--message", help="chat message id")
    p.add_argument("--gap", help="gap id this upload answers (e.g. GAP-012)")
    p.add_argument("--proposer", choices=["auto", "rules", "llm"])
    p.add_argument("--refresh-cache", action="store_true")
    p.add_argument("--move-processed", action="store_true", help="move inbox files to data/inbox/_processed")
    p.add_argument("--watch", action="store_true", help="keep polling the inbox")
    p.add_argument("--interval", type=float, default=3.0)
    p.add_argument("--keep", action="store_true", help="with --watch: leave files in place")
    p.add_argument("--workers", type=int, default=1, help="background batch: files prepared in parallel")
    p.add_argument("--summary", action="store_true", help="background batch: print only the final summary")
    p.add_argument("--run-id", help="background batch: id to record (default: generated RUN-...)")
    p.add_argument("--period", help="background batch: also report missing evidence for this YYYY-MM")
    p.add_argument("--json", action="store_true", help="machine-readable output (for agents)")
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("extract", help="dry run: propose + verify a file without writing to the ledger")
    p.add_argument("paths", nargs="+")
    p.add_argument("--proposer", choices=["auto", "rules", "llm"])
    p.add_argument("--refresh-cache", action="store_true")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_extract)

    ledger = sub.add_parser("ledger", help="read the ledger").add_subparsers(dest="ledger_cmd", required=True)
    p = ledger.add_parser("show", help="activities, instruments, missing docs and gaps for a period")
    p.add_argument("--period", required=True)
    p.add_argument("--site")
    p.add_argument("--status", choices=["UNVERIFIED", "VERIFIED", "FLAGGED", "EXCLUDED", "SUPERSEDED"])
    p.set_defaults(func=cmd_ledger_show)
    p = ledger.add_parser("export", help="the whole period as JSON (cr.ledger.v1)")
    p.add_argument("--period", required=True)
    p.add_argument("--json", action="store_true", help="accepted for clarity; output is always JSON")
    p.add_argument("--out")
    p.set_defaults(func=cmd_ledger_export)
    p = ledger.add_parser("gaps", help="list gaps")
    p.add_argument("--period")
    p.add_argument("--status", choices=["OPEN", "RESOLVED", "ACCEPTED_RISK"])
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_ledger_gaps)
    p = ledger.add_parser("events", help="the append-only audit log")
    p.add_argument("--limit", type=int, default=40)
    p.add_argument("--ref")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_ledger_events)
    p = ledger.add_parser("missing", help="expected monthly evidence with no document yet")
    p.add_argument("--period", required=True)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_ledger_missing)
    p = ledger.add_parser("closes", help="each close: locked sites + factor set, phase, who published")
    p.add_argument("--period")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_ledger_closes)
    p = ledger.add_parser("trace", help="knowledge graph: where did this number / bill / gap come from?")
    p.add_argument("ref", help="ACT-..., CALC-..., GAP-..., DOC-..., a bill number (ELB-AUS-2610), @person, site, YYYY-MM")
    p.add_argument("--depth", type=int, default=6)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_ledger_trace)
    p = ledger.add_parser("impact", help="knowledge graph: what depends on this (if this bill is wrong...)?")
    p.add_argument("ref")
    p.add_argument("--depth", type=int, default=4)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_ledger_impact)
    p = ledger.add_parser("graph", help="knowledge graph of one month as Mermaid or JSON")
    p.add_argument("--period", required=True)
    p.add_argument("--site", help="only this site's part of the month (e.g. austin)")
    p.add_argument("--format", choices=["mermaid", "json"], default="mermaid")
    p.add_argument("--depth", type=int, default=3)
    p.add_argument("--out", help="write to a file (.md gets a ```mermaid fence)")
    p.set_defaults(func=cmd_ledger_graph)
    p = ledger.add_parser("runs", help="past background batch runs and their final summaries")
    p.add_argument("--id", help="one run's summary")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_ledger_runs)
    p = ledger.add_parser("verify", help="re-hash every document and re-find every excerpt")
    p.add_argument("--period")
    p.add_argument("--verbose", "-v", action="store_true")
    p.set_defaults(func=cmd_ledger_verify)

    llm_p = sub.add_parser("llm", help="model provider tools").add_subparsers(dest="llm_cmd", required=True)
    from carbonroom.llm import PROVIDERS

    provider_help = "provider for this run (overrides LLM_PROVIDER)"
    p = llm_p.add_parser("providers", help="list provider presets and which one is active")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_llm_providers)
    p = llm_p.add_parser("models", help="list chat models from the provider (GET /models)")
    p.add_argument("--provider", choices=sorted(PROVIDERS), help=provider_help)
    p.add_argument("--all", dest="chat", action="store_false", help="include embedding/safety/OCR models")
    p.add_argument("--grep", help="regex filter, e.g. 'nemotron|deepseek|qwen'")
    p.set_defaults(func=cmd_llm_models)
    p = llm_p.add_parser("probe", help="one tiny call per model: which ones answer for this key?")
    p.add_argument("--provider", choices=sorted(PROVIDERS), help=provider_help)
    p.add_argument("--models", help="comma-separated model ids (default: listed chat models)")
    p.add_argument("--grep", default="nemotron|deepseek|llama|qwen|mistral|gpt-oss|kimi|glm|gemma|phi",
                   help="regex filter on listed models")
    p.add_argument("--all", dest="chat", action="store_false", help="include embedding/safety/OCR models")
    p.add_argument("--limit", type=int, default=25)
    p.set_defaults(func=cmd_llm_probe)
    p = llm_p.add_parser("bench", help="score candidate models on the seed documents")
    p.add_argument("--provider", choices=sorted(PROVIDERS), help=provider_help)
    p.add_argument("--models", help="comma-separated model ids")
    p.add_argument("--verbose", "-v", action="store_true")
    p.set_defaults(func=cmd_llm_bench)

    gdb = sub.add_parser("graphdb", help="the knowledge graph in Neo4j (graph database)").add_subparsers(
        dest="graphdb_cmd", required=True)
    p = gdb.add_parser("status", help="is Neo4j up, when was the last sync, is it current")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_graphdb_status)
    p = gdb.add_parser("sync", help="copy the ledger's graph into Neo4j now")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_graphdb_sync)
    p = gdb.add_parser("why", help="what was recorded, is open or is missing for a site and month, as one sentence")
    p.add_argument("site")
    p.add_argument("period")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_graphdb_why)
    p = gdb.add_parser("conflicts", help="fuel deliveries with two different quantities")
    p.add_argument("--period")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_graphdb_conflicts)
    p = gdb.add_parser("gaps", help="open gaps grouped by owner")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_graphdb_gaps)
    p = gdb.add_parser("find", help="search ids, names, doc numbers, file names, excerpts, gap details")
    p.add_argument("text")
    p.add_argument("--limit", type=int, default=25)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_graphdb_find)
    p = gdb.add_parser("query", help="run read-only Cypher (for agents); prints JSON")
    p.add_argument("cypher")
    p.add_argument("--param", action="append", help="key=value, repeatable")
    p.set_defaults(func=cmd_graphdb_query)
    p = gdb.add_parser("selftest", help="sync, then run every query against the live Neo4j")
    p.set_defaults(func=cmd_graphdb_selftest)

    for module_name in PLUGIN_MODULES:
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            if exc.name and module_name.startswith(exc.name):
                continue  # teammate's module not merged yet
            raise
        register = getattr(module, "register", None)
        if callable(register):
            register(sub)
    return parser


def _ledger_event_id(args) -> int | None:
    from carbonroom.graphdb import store

    if store.mode() == "off":
        return None
    path = Path(args.db) if args.db else config.db_path()
    if not path.exists():
        return 0
    from carbonroom.ledger import db

    try:
        conn = db.connect(path, create=False)
    except Exception:  # noqa: BLE001 - not a ledger (yet)
        return None
    try:
        return int(conn.execute("SELECT COALESCE(MAX(id), 0) FROM events").fetchone()[0])
    except Exception:  # noqa: BLE001
        return None
    finally:
        conn.close()


def _auto_sync_graphdb(args, before: int | None) -> None:
    """After ANY command (ours or a teammate's plugin) that wrote to the ledger, refresh the graph database."""
    if before is None:
        return
    after = _ledger_event_id(args)
    if after is None or after == before:
        return
    from carbonroom.graphdb import store
    from carbonroom.ledger import db

    conn = db.connect(Path(args.db) if args.db else config.db_path(), create=False)
    try:
        store.sync_if_enabled(conn)
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    config.load_env()
    parser = build_parser()
    args = parser.parse_args(argv)
    from carbonroom.ledger.db import LedgerError

    try:
        before = _ledger_event_id(args)
        code = int(args.func(args) or 0)
        if args.command != "graphdb":
            _auto_sync_graphdb(args, before)
        return code
    except LedgerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(f"error: file not found: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
