"""The ledger as a knowledge graph.

Nodes and edges are the read-only SQL views `ledger_nodes` / `ledger_edges` (contracts/schema.sql),
computed live from the ledger tables, so the graph can never disagree with them. Traversal is a
recursive SQL query (WITH RECURSIVE) over `ledger_edges`.

Node references accepted everywhere: "type:id" (activity:ACT-..., doc:DOC-..., gap:GAP-001, site:austin,
period:2026-10, person:lena, room:cr-site-reno, run:RUN-..., factor:..., calculation:...), or the bare
forms ACT-/DOC-/GAP-/INS-/CALC-/APR-/EXP-/RUN- ids, @handle, YYYY-MM, a site id, a room name (cr-...),
or a printed document number such as ELB-AUS-2610.

Questions it answers:
  lineage(ACT)  - where did this number come from? (excerpt, page/line, file hash, sender, room, run,
                  corrections, calculations + factors, open gaps)
  impact(DOC)   - if this bill is wrong, which numbers, calculations and gaps depend on it?
  period_graph  - the month as one graph (Mermaid / JSON) for the README and the demo
"""

from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

from carbonroom.ledger import db

ID_PREFIXES = {
    "ACT-": "activity",
    "DOC-": "doc",
    "GAP-": "gap",
    "INS-": "instrument",
    "CALC-": "calculation",
    "APR-": "approval",
    "EXP-": "expected",
    "RUN-": "run",
}
NODE_TYPES = ("site", "period", "doc", "activity", "instrument", "gap", "calculation", "factor", "expected",
              "approval", "person", "room", "run")
# Shared hubs: a walk passes THROUGH them only from the start node, so "trace this number" doesn't
# drag in every other number from the same month, person or room.
HUBS = ("person", "room", "period", "run", "site")


def key(node_type: str, node_id: str) -> str:
    return f"{node_type}:{node_id}"


def split(node_key: str) -> tuple[str, str]:
    node_type, _, node_id = node_key.partition(":")
    return node_type, node_id


def node(conn: sqlite3.Connection, node_type: str, node_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM ledger_nodes WHERE type = ? AND id = ?", (node_type, node_id)).fetchone()
    return dict(row) if row else None


def resolve(conn: sqlite3.Connection, ref: str) -> tuple[str, str]:
    """Turn what a human types into (type, id). Raises LedgerError if nothing matches."""
    ref = ref.strip()
    if ":" in ref and ref.split(":", 1)[0] in NODE_TYPES:
        node_type, node_id = split(ref)
        if node(conn, node_type, node_id):
            return node_type, node_id
        raise db.LedgerError(f"no {node_type} {node_id!r} in the ledger")
    candidates: list[tuple[str, str]] = []
    if ref.startswith("@"):
        candidates.append(("person", ref[1:]))
    for prefix, node_type in ID_PREFIXES.items():
        if ref.upper().startswith(prefix):
            candidates.append((node_type, ref))
    if re.fullmatch(r"\d{4}-\d{2}", ref):
        candidates.append(("period", ref))
    candidates += [("site", ref), ("room", ref), ("factor", ref), ("person", ref)]
    for node_type, node_id in candidates:
        if node(conn, node_type, node_id):
            return node_type, node_id
    docs = db.find_source_docs_by_ref(conn, ref)
    if docs:
        return "doc", docs[0]["id"]
    raise db.LedgerError(f"nothing in the ledger matches {ref!r}")


def edges(conn: sqlite3.Connection, node_type: str | None = None, node_id: str | None = None,
          direction: str = "both") -> list[dict[str, Any]]:
    """Edges touching one node ('out', 'in' or 'both'), or every edge if no node is given."""
    if node_type is None:
        return [dict(r) for r in conn.execute("SELECT * FROM ledger_edges")]
    rows = []
    if direction in ("out", "both"):
        rows += conn.execute("SELECT * FROM ledger_edges WHERE src_type = ? AND src_id = ?", (node_type, node_id))
    if direction in ("in", "both"):
        rows += conn.execute("SELECT * FROM ledger_edges WHERE dst_type = ? AND dst_id = ?", (node_type, node_id))
    return [dict(r) for r in rows]


_WALK_SQL = {
    "out": """
        WITH RECURSIVE reach(type, id, depth) AS (
          SELECT ?, ?, 0
          UNION
          SELECT e.dst_type, e.dst_id, r.depth + 1
          FROM reach r JOIN ledger_edges e ON e.src_type = r.type AND e.src_id = r.id
          WHERE r.depth < ? AND (r.depth = 0 OR r.type NOT IN ({hubs}))
        )
        SELECT type, id, MIN(depth) AS depth FROM reach GROUP BY type, id ORDER BY depth, type, id""",
    "in": """
        WITH RECURSIVE reach(type, id, depth) AS (
          SELECT ?, ?, 0
          UNION
          SELECT e.src_type, e.src_id, r.depth + 1
          FROM reach r JOIN ledger_edges e ON e.dst_type = r.type AND e.dst_id = r.id
          WHERE r.depth < ? AND (r.depth = 0 OR r.type NOT IN ({hubs}))
        )
        SELECT type, id, MIN(depth) AS depth FROM reach GROUP BY type, id ORDER BY depth, type, id""",
}


def walk(conn: sqlite3.Connection, node_type: str, node_id: str, *, direction: str = "out",
         max_depth: int = 6) -> dict[str, Any]:
    """Every node reachable from (node_type, node_id) following edges 'out' or 'in', up to max_depth hops.

    One recursive SQL query does the traversal. Hubs (people, rooms, periods, runs, sites) are not walked
    through, except from the start node. Returns {"nodes": [...], "edges": [...]} with only edges among
    the reached nodes.
    """
    if direction not in _WALK_SQL:
        raise ValueError("direction must be 'out' or 'in'")
    sql = _WALK_SQL[direction].format(hubs=",".join(f"'{h}'" for h in HUBS))
    reached = conn.execute(sql, (node_type, node_id, max_depth)).fetchall()
    depth = {key(r["type"], r["id"]): r["depth"] for r in reached}
    nodes = []
    for node_key, d in depth.items():
        t, i = split(node_key)
        info = node(conn, t, i) or {"type": t, "id": i, "label": i, "status": None, "period_id": None}
        nodes.append({**info, "key": node_key, "depth": d})
    found = []
    for e in edges(conn):
        src, dst = key(e["src_type"], e["src_id"]), key(e["dst_type"], e["dst_id"])
        if src not in depth or dst not in depth:
            continue
        # keep exactly the edges the walk could follow: from a node it expanded (start, or not a hub)
        frm = src if direction == "out" else dst
        if depth[frm] < max_depth and (depth[frm] == 0 or split(frm)[0] not in HUBS):
            found.append({**e, "src": src, "dst": dst})
    found.sort(key=lambda e: (e["src"], e["rel"], e["dst"]))
    return {"start": key(node_type, node_id), "direction": direction, "nodes": nodes, "edges": found}


def impact(conn: sqlite3.Connection, ref: str, max_depth: int = 4) -> dict[str, Any]:
    """What depends on this node (walk the edges backwards): e.g. a bill -> its activities ->
    their calculations, plus every gap about any of them."""
    node_type, node_id = resolve(conn, ref)
    graph = walk(conn, node_type, node_id, direction="in", max_depth=max_depth)
    by_type: dict[str, list[str]] = {}
    for n in graph["nodes"][1:]:
        by_type.setdefault(n["type"], []).append(n["id"])
    graph["depends"] = by_type
    return graph


def lineage(conn: sqlite3.Connection, ref: str) -> dict[str, Any]:
    """Where a number came from, as data plus readable lines. Works for an activity or a calculation."""
    node_type, node_id = resolve(conn, ref)
    calc = None
    if node_type == "calculation":
        calc = db.row_to_dict(conn.execute("SELECT * FROM calculations WHERE id = ?", (node_id,)).fetchone())
        node_type, node_id = "activity", calc["activity_id"]
    if node_type != "activity":
        raise db.LedgerError(f"lineage needs a number (an activity or calculation), got {node_type} {node_id}")
    act = db.get_activity(conn, node_id)
    doc = db.get_source_doc(conn, act["source_doc_id"])
    site = db.get_site(conn, act["site_id"]) or {"name": act["site_id"]}
    chain = [doc]
    while chain[-1]["superseded_by"]:
        chain.append(db.get_source_doc(conn, chain[-1]["superseded_by"]))
    calcs = [c for c in db.list_calculations(conn, activity_id=act["id"]) if calc is None or c["id"] == calc["id"]]
    factors = {c["factor_id"]: db.row_to_dict(conn.execute("SELECT * FROM emission_factors WHERE id = ?",
                                                           (c["factor_id"],)).fetchone()) for c in calcs}
    gaps = sorted({e["src_id"] for e in edges(conn, "activity", act["id"], "in") if e["src_type"] == "gap"}
                  | {e["src_id"] for e in edges(conn, "doc", doc["id"], "in") if e["src_type"] == "gap"})
    gap_rows = [db.get_gap(conn, g) for g in gaps]
    replaced_by = act["superseded_by"] or next(
        (e["src_id"] for e in edges(conn, "activity", act["id"], "in") if e["rel"] == "replaces"), None)
    replaces = [e["dst_id"] for e in edges(conn, "activity", act["id"], "out") if e["rel"] == "replaces"]

    qty = f"{db.dec(act['quantity']):,}".rstrip("0").rstrip(".") if "." in act["quantity"] else f"{int(act['quantity']):,}"
    lines = [f"{qty} {act['unit']} {act['category']} · {site['name']} · {act['period_id']} · {act['status']}"]
    extra = act["extra"] or {}
    if extra.get("conversion") not in (None, "none"):
        lines.append(f"  = {extra['original_quantity']} {extra['original_unit']} as printed ({extra['conversion']})")
    where = act["excerpt_locator"].replace("=", " ").replace(";", ", ")
    lines.append(f"  ← proven by {where}: \"{act['excerpt']}\" "
                 f"(excerpt sha256 {act['excerpt_sha256'][:12]}…)")
    lines.append(f"  ← in {doc['doc_ref'] or doc['original_name']} ({doc['id']}, file sha256 {doc['sha256'][:12]}…, "
                 f"{doc['path']})")
    meta = doc["meta"] or {}
    who = f"  ← sent by @{doc['received_from']}" + (f" in {doc['room']}" if doc["room"] else "")
    if meta.get("run_id"):
        who += f" (run {meta['run_id']})"
    if meta.get("gap_id"):
        who += f", answering {meta['gap_id']}"
    lines.append(who)
    lines.append(f"  ← extracted by {extra.get('proposer', '?')}, then verified by code against the page text")
    for newer in chain[1:]:
        lines.append(f"  ⚠ that document was replaced by {newer['doc_ref'] or newer['id']} ({newer['id']})")
    if replaced_by:
        new = db.get_activity(conn, replaced_by)
        lines.append(f"  ⚠ corrected value: {replaced_by} = {new['quantity']} {new['unit']} ({new['status']})")
    for old in replaces:
        prev = db.get_activity(conn, old)
        lines.append(f"  ↺ replaces {old} ({prev['quantity']} {prev['unit']}, {prev['status']})")
    for c in calcs:
        f = factors.get(c["factor_id"]) or {}
        lines.append(f"  → {c['scope']}: {c['co2e_kg']} kg CO2e = quantity × factor {c['factor_id']} "
                     f"({f.get('factor')} {f.get('unit')}, {f.get('source_name')} {f.get('source_edition')})")
    for g in gap_rows:
        lines.append(f"  ! {g['id']} {g['kind']} {g['status']} → @{g['owner_handle']}: {g['detail'][:90]}")
    return {
        "activity": act,
        "document_chain": chain,
        "site": site,
        "calculations": calcs,
        "factors": list(factors.values()),
        "gaps": gap_rows,
        "replaced_by": replaced_by,
        "replaces": replaces,
        "lines": lines,
        "text": "\n".join(lines),
    }


SITE_LINKS = ("at_site", "about_site", "claimed_against")


def period_graph(conn: sqlite3.Connection, period_id: str, max_depth: int = 3,
                 hide_types: tuple[str, ...] = ("period",), site: str | None = None) -> dict[str, Any]:
    """One month as a graph: every activity, instrument, gap and approval of the period, walked outwards.
    The period node itself is hidden by default (every node in this graph belongs to it).
    With `site`, only what is at / about / claimed against that site (one site room's view)."""
    if db.get_period(conn, period_id) is None:
        raise db.LedgerError(f"unknown period {period_id}")
    starts = conn.execute(
        "SELECT type, id FROM ledger_nodes WHERE period_id = ? AND type IN ('activity','instrument','gap','approval') "
        "ORDER BY type, id",
        (period_id,),
    ).fetchall()
    if site:
        if db.get_site(conn, site) is None:
            raise db.LedgerError(f"unknown site {site}")
        starts = [s for s in starts if any(e["rel"] in SITE_LINKS and e["dst_id"] == site
                                           for e in edges(conn, s["type"], s["id"], "out"))]
    nodes: dict[str, dict[str, Any]] = {}
    edge_set: dict[tuple, dict[str, Any]] = {}
    for s in starts:
        g = walk(conn, s["type"], s["id"], direction="out", max_depth=max_depth)
        for n in g["nodes"]:
            nodes.setdefault(n["key"], n)
        for e in g["edges"]:
            edge_set[(e["src"], e["rel"], e["dst"])] = e
        for e in edges(conn, s["type"], s["id"], "in"):  # calculations point INTO activities
            if e["src_type"] == "calculation":
                src = key(e["src_type"], e["src_id"])
                nodes.setdefault(src, {**(node(conn, e["src_type"], e["src_id"]) or {}), "key": src, "depth": 1})
                edge_set[(src, e["rel"], key(s["type"], s["id"]))] = {**e, "src": src, "dst": key(s["type"], s["id"])}
                for fe in edges(conn, "calculation", e["src_id"], "out"):
                    if fe["dst_type"] == "factor":
                        dst = key("factor", fe["dst_id"])
                        nodes.setdefault(dst, {**(node(conn, "factor", fe["dst_id"]) or {}), "key": dst, "depth": 2})
                        edge_set[(src, fe["rel"], dst)] = {**fe, "src": src, "dst": dst}
    nodes = {k: n for k, n in nodes.items() if n.get("type") not in hide_types}
    edge_set = {k: e for k, e in edge_set.items() if e["src"] in nodes and e["dst"] in nodes}
    order = {t: i for i, t in enumerate(NODE_TYPES)}
    ordered_nodes = sorted(nodes.values(), key=lambda n: (order.get(n.get("type"), 99), n["key"]))
    ordered_edges = sorted(edge_set.values(), key=lambda e: (e["src"], e["rel"], e["dst"]))
    return {"period": period_id, "site": site, "nodes": ordered_nodes, "edges": ordered_edges}


# ---------------------------------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------------------------------

_STYLE = {
    "activity": "fill:#e8f1ec,stroke:#1f5c4a", "doc": "fill:#fff7e6,stroke:#9a6b00", "gap": "fill:#fdecea,stroke:#9a3412",
    "site": "fill:#eef2ff,stroke:#3730a3", "person": "fill:#f5f5f5,stroke:#555", "instrument": "fill:#e6f7ff,stroke:#0369a1",
    "calculation": "fill:#f3e8ff,stroke:#6b21a8", "factor": "fill:#f3e8ff,stroke:#6b21a8",
}


def _mid(node_key: str) -> str:
    return "n_" + re.sub(r"[^A-Za-z0-9_]", "_", node_key)


def _label(n: dict[str, Any]) -> str:
    text = n.get("label") or n.get("id") or n.get("key")
    if n.get("type") in ("activity", "instrument", "gap") and n.get("status"):
        text = f"{text} [{n['status']}]"
    if n.get("type") == "doc" and n.get("status") == "superseded":
        text = f"{text} [superseded]"
    return text.replace('"', "'")


def plural(word: str, n: int) -> str:
    if n == 1:
        return word
    return word[:-1] + "ies" if word.endswith("y") else word + "s"


def to_mermaid(graph: dict[str, Any]) -> str:
    lines = ["flowchart LR"]
    for n in graph["nodes"]:
        lines.append(f'  {_mid(n["key"])}["{n.get("type")}: {_label(n)}"]')
    for e in graph["edges"]:
        lines.append(f"  {_mid(e['src'])} -->|{e['rel']}| {_mid(e['dst'])}")
    for node_type, style in _STYLE.items():
        members = [_mid(n["key"]) for n in graph["nodes"] if n.get("type") == node_type]
        if members:
            lines.append(f"  classDef {node_type} {style}")
            lines.append(f"  class {','.join(members)} {node_type}")
    return "\n".join(lines) + "\n"


def to_json(graph: dict[str, Any]) -> str:
    return json.dumps({
        "type": "cr.graph.v1",
        **{k: v for k, v in graph.items() if k not in ("nodes", "edges")},
        "nodes": [{"key": n["key"], "type": n.get("type"), "id": n.get("id"), "label": n.get("label"),
                   "status": n.get("status")} for n in graph["nodes"]],
        "edges": [{"src": e["src"], "rel": e["rel"], "dst": e["dst"], "detail": e.get("detail")} for e in graph["edges"]],
    }, indent=2, ensure_ascii=False, default=str)


def tree_lines(graph: dict[str, Any]) -> list[str]:
    """Indented text view of a walk (start at the top)."""
    children: dict[str, list[tuple[str, str]]] = {}
    for e in graph["edges"]:
        a, b = (e["src"], e["dst"]) if graph["direction"] == "out" else (e["dst"], e["src"])
        children.setdefault(a, []).append((e["rel"], b))
    labels = {n["key"]: _label(n) for n in graph["nodes"]}
    arrow = "→" if graph["direction"] == "out" else "←"
    out = [f"{graph['start']}  {labels.get(graph['start'], '')}"]
    seen = {graph["start"]}

    def visit(k: str, indent: int) -> None:
        for rel, child in sorted(children.get(k, [])):
            out.append(f"{'  ' * indent}{arrow} {rel}: {child}  {labels.get(child, '')}")
            if child not in seen:
                seen.add(child)
                visit(child, indent + 1)

    visit(graph["start"], 1)
    return out
