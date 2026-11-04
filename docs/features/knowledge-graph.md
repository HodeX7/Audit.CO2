# Knowledge graph (ledger as a graph, mirrored into Neo4j)

**Owner:** Ujjwal · **Code:** views in `contracts/schema.sql`, `carbonroom/ledger/graph.py`, `carbonroom/graphdb/` ·
**Infra:** `infra/neo4j/docker-compose.yml` · **Tests:** `tests/test_graph.py`, `tests/test_graphdb.py`

## Why

The story the product tells: every number is linked to its site, month, source bill, sender, factor and
approver, and "where did this come from?" is one click away. An auditor picks a number and follows it to
the bill. The checker asks "this bill was replaced: which numbers depend on it?" Humans in chat ask a
specialist agent "why is this number what it is?" Those are graph questions.

Two layers, one graph model. The graph is defined once, as views over the SQLite ledger, so it works from a
clone with nothing to install and can never disagree with the ledger. It's then mirrored into a graph database,
Neo4j, for Cypher queries by agents, the visual browser in the demo, and graph-native questions (see "Graph
database (Neo4j)" below).

## Design

### Nodes and edges are live SQL views

`ledger_nodes(type, id, label, status, period_id)` and `ledger_edges(src_type, src_id, rel, dst_type, dst_id,
detail)` are **views** over the ledger tables. Nothing is stored twice, so the graph can never disagree with
the ledger, and new rows appear in the graph immediately.

| Edge (`rel`) | From → to | Comes from |
| --- | --- | --- |
| `evidenced_by` | activity / instrument → doc | `source_doc_id` (the locator rides on the edge) |
| `at_site`, `in_period` | activity → site, period | `site_id`, `period_id` |
| `superseded_by` | activity → activity, doc → doc, instrument → instrument | `superseded_by` |
| `replaces` | new activity → old activity | `extra_json.replaces_activity_ids` (corrected bills) |
| `received_from`, `posted_in` | doc → person, room | who sent it, from which room |
| `collected_in` | doc → run | `meta.run_id` (background batch runs) |
| `answers` | doc → gap | `meta.gap_id` (an upload that answers a gap) |
| `claimed_against` | instrument → site | REC claimed against a load |
| `of`, `uses_factor` | calculation → activity, factor | Richa's calculations |
| `about`, `about_site`, `owned_by`, `raised_in`, `resolved_by` | gap → doc / activity / instrument, site, person, room | gap columns + `refs_json` keys `source_doc_id`, `activity_id`, `activity_ids[]`, `instrument_id` |
| `owned_by`, `has_room` | site → person, room | site owner and room |
| `for_site` | expected → site | `expected_documents` |
| `for_period`, `by`, `approved_by` | approval → period, person; period → person | human approvals |

Node types: site, period, doc, activity, instrument, gap, calculation, factor, expected, approval, person,
room, run.

### Traversal is a recursive SQL query

`carbonroom.ledger.graph.walk` runs one `WITH RECURSIVE` query over `ledger_edges`, either **out** (what this
depends on) or **in** (what depends on this), up to a depth. Shared hubs (person, room, period, run, site)
are only walked *through* from the start node, so tracing one number doesn't pull in every other number from
the same month or person.

### Questions it answers

| Question | Function | Command |
| --- | --- | --- |
| Where did this number come from? | `carbonroom.ledger.graph.lineage` | `carbonroom ledger trace ACT-...` (or a `CALC-...`) |
| What does this bill / gap / person connect to? | `carbonroom.ledger.graph.walk` | `carbonroom ledger trace ELB-AUS-2610` |
| If this bill is wrong, what changes? | `carbonroom.ledger.graph.impact` | `carbonroom ledger impact ELB-AUS-2610` |
| Show the month (or one site) as a graph | `carbonroom.ledger.graph.period_graph` | `carbonroom ledger graph --period 2026-10 [--site austin]` |

References are what a human types: `ACT-…`, `DOC-…`, `GAP-…`, a printed bill number such as `ELB-AUS-2610`,
`@lena`, `austin`, `2026-10`, `cr-site-reno`, or explicit `type:id` (`carbonroom.ledger.graph.resolve`).

### Example (seed data + the corrected Austin bill)

`carbonroom seed`, then `carbonroom ingest data/seed/later/2026-10_austin_electricity_ELB-AUS-2610-C.pdf --from omar --room cr-site-austin`:

<!-- example:trace:start -->
```text
$ carbonroom ledger trace ACT-0739d5932d
191,300 kWh electricity · Austin Plant · 2026-10 · UNVERIFIED
  ← proven by page 1, line 10: "Total energy used this period: 191,300 kWh" (excerpt sha256 69191233c656…)
  ← in ELB-AUS-2610 (DOC-a0ac18b17109, file sha256 a0ac18b17109…, data/seed/docs/2026-10_austin_electricity_ELB-AUS-2610.pdf)
  ← sent by @omar in cr-site-austin
  ← extracted by cache:llm:nvidia:nvidia/nemotron-3-ultra-550b-a55b, then verified by code against the page text
  ⚠ that document was replaced by ELB-AUS-2610-C (DOC-1c5fa805b8af)
  ⚠ corrected value: ACT-0c96e79c12 = 196800 kWh (UNVERIFIED)
```
<!-- example:trace:end -->

<!-- example:impact:start -->
```text
$ carbonroom ledger impact ELB-AUS-2610
doc:DOC-a0ac18b17109  ELB-AUS-2610 [superseded]
  ← evidenced_by: activity:ACT-0739d5932d  electricity 191300 kWh [UNVERIFIED]
    ← replaces: activity:ACT-0c96e79c12  electricity 196800 kWh [UNVERIFIED]

Depends on doc:DOC-a0ac18b17109: 2 activities
```
<!-- example:impact:end -->

`carbonroom ledger graph --period 2026-10 --site austin` (GitHub renders this):

<!-- example:graph:start -->
```mermaid
flowchart LR
  n_site_austin["site: Austin Plant"]
  n_doc_DOC_1c5fa805b8af["doc: ELB-AUS-2610-C"]
  n_doc_DOC_4169211ec33c["doc: INV-204"]
  n_doc_DOC_6beed661d47c["doc: INV-204B"]
  n_doc_DOC_979e61f23184["doc: GAS-AUS-2610"]
  n_doc_DOC_a0ac18b17109["doc: ELB-AUS-2610 [superseded]"]
  n_activity_ACT_0739d5932d["activity: electricity 191300 kWh [UNVERIFIED]"]
  n_activity_ACT_0c96e79c12["activity: electricity 196800 kWh [UNVERIFIED]"]
  n_activity_ACT_3a85554a7c["activity: diesel 500 gal [UNVERIFIED]"]
  n_activity_ACT_8d9bef9233["activity: natural_gas 7700 therm [UNVERIFIED]"]
  n_activity_ACT_d90b35bdce["activity: diesel 550 gal [UNVERIFIED]"]
  n_person_omar["person: @omar"]
  n_room_cr_site_austin["room: cr-site-austin"]
  n_activity_ACT_0739d5932d -->|at_site| n_site_austin
  n_activity_ACT_0739d5932d -->|evidenced_by| n_doc_DOC_a0ac18b17109
  n_activity_ACT_0c96e79c12 -->|at_site| n_site_austin
  n_activity_ACT_0c96e79c12 -->|evidenced_by| n_doc_DOC_1c5fa805b8af
  n_activity_ACT_0c96e79c12 -->|replaces| n_activity_ACT_0739d5932d
  n_activity_ACT_3a85554a7c -->|at_site| n_site_austin
  n_activity_ACT_3a85554a7c -->|evidenced_by| n_doc_DOC_4169211ec33c
  n_activity_ACT_8d9bef9233 -->|at_site| n_site_austin
  n_activity_ACT_8d9bef9233 -->|evidenced_by| n_doc_DOC_979e61f23184
  n_activity_ACT_d90b35bdce -->|at_site| n_site_austin
  n_activity_ACT_d90b35bdce -->|evidenced_by| n_doc_DOC_6beed661d47c
  n_doc_DOC_1c5fa805b8af -->|posted_in| n_room_cr_site_austin
  n_doc_DOC_1c5fa805b8af -->|received_from| n_person_omar
  n_doc_DOC_4169211ec33c -->|posted_in| n_room_cr_site_austin
  n_doc_DOC_4169211ec33c -->|received_from| n_person_omar
  n_doc_DOC_6beed661d47c -->|posted_in| n_room_cr_site_austin
  n_doc_DOC_6beed661d47c -->|received_from| n_person_omar
  n_doc_DOC_979e61f23184 -->|posted_in| n_room_cr_site_austin
  n_doc_DOC_979e61f23184 -->|received_from| n_person_omar
  n_doc_DOC_a0ac18b17109 -->|posted_in| n_room_cr_site_austin
  n_doc_DOC_a0ac18b17109 -->|received_from| n_person_omar
  n_doc_DOC_a0ac18b17109 -->|superseded_by| n_doc_DOC_1c5fa805b8af
  classDef activity fill:#e8f1ec,stroke:#1f5c4a
  class n_activity_ACT_0739d5932d,n_activity_ACT_0c96e79c12,n_activity_ACT_3a85554a7c,n_activity_ACT_8d9bef9233,n_activity_ACT_d90b35bdce activity
  classDef doc fill:#fff7e6,stroke:#9a6b00
  class n_doc_DOC_1c5fa805b8af,n_doc_DOC_4169211ec33c,n_doc_DOC_6beed661d47c,n_doc_DOC_979e61f23184,n_doc_DOC_a0ac18b17109 doc
  classDef site fill:#eef2ff,stroke:#3730a3
  class n_site_austin site
  classDef person fill:#f5f5f5,stroke:#555
  class n_person_omar person
```
<!-- example:graph:end -->

The three examples above are regenerated and compared by `tests/test_docs.py`, so they always match the code.

### Graph database (Neo4j)

The same graph is mirrored into **Neo4j**, a graph database: same node types, same links (names upper-cased:
`EVIDENCED_BY`, `REPLACES`, `SUPERSEDED_BY`, `ABOUT`, `OWNED_BY`, …), same ids. It adds what SQLite can't:
Cypher for agents, the visual browser for the demo video, and graph-native questions. SQLite stays the system of
record (honesty triggers, append-only), and the views stay the one definition of the graph.

```mermaid
flowchart LR
  W["any CLI command that writes (ours or a teammate's plugin)"] --> L[(SQLite ledger: system of record)]
  L --> V["ledger_nodes / ledger_edges views: THE graph model"]
  V --> T["ledger trace / impact / graph (offline)"]
  V -->|"auto-sync when the event log grew"| N[(Neo4j: graph database)]
  N --> Q["graphdb why / conflicts / gaps / find / query"]
  N --> B["Neo4j Browser :7474 for the demo"]
```

- **Projection** (`carbonroom.graphdb.store.projection`): every row of `ledger_nodes` becomes a node, with label
  `Site`, `Period`, `Document`, `Activity`, `Instrument`, `Gap`, `Calculation`, `Factor`, `Expected`, `Approval`,
  `Person`, `Room` or `Run`, plus the extra label `CR`. Its useful details become properties (quantity as a decimal
  string, excerpt, locator, delivery ticket, PUE, doc number, gap detail, REC region and vintage…). Every row of
  `ledger_edges` becomes a relationship (`detail`, such as the locator, rides on it). A link whose end doesn't exist,
  like an upload that names a gap id never opened, is skipped and counted.
- **Sync** (`carbonroom.graphdb.store.sync`): uniqueness constraints, then **one write transaction** that removes
  the `CR` nodes and recreates the graph with `UNWIND … MERGE`. Readers never see half a graph, nothing outside `CR`
  is touched, labels come from a fixed map, link types are checked against `[A-Z_]+`, and every value travels as a
  query parameter. The ledger never deletes; only this disposable copy is rebuilt (well under a second at this scale).
- **When:** after any `carbonroom` command whose run grew the ledger's event log, including teammates' plugin
  commands, with no change on their side; at the end of `collect_node`; or on demand. `CR_GRAPH=auto` (default) syncs
  when Neo4j answers a 0.4 s TCP check and is silent otherwise; `on` warns; `off` never syncs. A failed sync prints a
  warning and never fails the command.

| Question | Function | Command |
| --- | --- | --- |
| Why wasn't X considered? What's recorded, open or still missing for a site and month, in one sentence | `carbonroom.graphdb.queries.why` | `carbonroom graphdb why reno 2026-10` |
| Which fuel deliveries have two different quantities? | `carbonroom.graphdb.queries.conflicts` | `carbonroom graphdb conflicts --period 2026-10` |
| Who owns which open gaps? | `carbonroom.graphdb.queries.gaps_by_owner` | `carbonroom graphdb gaps` |
| Find by id, name, doc number, file name, excerpt, gap detail | `carbonroom.graphdb.queries.find` | `carbonroom graphdb find "data center"` |
| Anything else, for agents (writes refused, READ routing) | `carbonroom.graphdb.queries.read_only` | `carbonroom graphdb query "MATCH …"` |

Example `why` answer an agent can post: "No document for Reno Office 2026-10 has reached the ledger. Open gaps:
GAP-012 missing_doc: … Still missing: electricity (owner @lena)."

**Verification:** these Cypher queries need a live server, so `carbonroom graphdb selftest` syncs the current
ledger and runs every one. It checks node, link and number-to-bill counts against the views, a why for every site
and month, the conflicts the ledger implies, and the read-only guard. Built and unit-tested 2026-11-04 without a
live Neo4j (the build environment couldn't pull the image). **Run `carbonroom graphdb selftest` once with Docker and
record the result in `docs/STATUS.md`.**

In Neo4j Browser (http://localhost:7474), for the demo:

```cypher
MATCH p = (:Activity)-[:EVIDENCED_BY]->(:Document)-[:RECEIVED_FROM]->(:Person) RETURN p
MATCH p = (:Activity)-[:REPLACES]->(:Activity)-[:EVIDENCED_BY]->(:Document)-[:SUPERSEDED_BY]->(:Document) RETURN p
MATCH p = (g:Gap)-[:ABOUT|OWNED_BY|ABOUT_SITE]->() RETURN p
```

## Decisions

See `docs/DECISIONS.md`: graph as SQL views (no duplicate storage, never stale); recursive-CTE traversal with hub
stopping; gap `refs_json` keys as the way to link gaps to rows; `graph_version` for view changes; Neo4j as a mirrored
graph database (one model, rebuilt per sync in one transaction, auto-synced after writes).

## Code map

| Name | Does |
| --- | --- |
| `contracts/schema.sql` | `ledger_edges` and `ledger_nodes` views |
| `carbonroom.ledger.db.GRAPH_VERSION` | bump when the views change; `carbonroom.ledger.db.migrate` rebuilds them |
| `carbonroom.ledger.graph.resolve` | human reference → (type, id) |
| `carbonroom.ledger.graph.edges` | edges touching a node (or all) |
| `carbonroom.ledger.graph.walk` | recursive traversal, out or in |
| `carbonroom.ledger.graph.lineage` | full provenance of one number, as data + text |
| `carbonroom.ledger.graph.impact` | everything that depends on a node |
| `carbonroom.ledger.graph.period_graph` | one month (or one site's month) as a graph |
| `carbonroom.ledger.graph.to_mermaid` | Mermaid flowchart |
| `carbonroom.ledger.graph.to_json` | `cr.graph.v1` JSON (nodes + edges) |
| `carbonroom.ledger.graph.tree_lines` | indented text view of a walk |
| `carbonroom.graphdb.store.projection` | the views as Neo4j nodes + relationships (pure) |
| `carbonroom.graphdb.store.sync` | rebuild the Neo4j copy in one transaction |
| `carbonroom.graphdb.store.sync_if_enabled` | the post-write hook; never fails the caller |
| `carbonroom.graphdb.store.status` | reachable? last sync? in sync with the ledger? counts |
| `carbonroom.graphdb.queries.selftest` | every Cypher query against the live server |

## Tests

`tests/test_graph.py`: every activity has exactly its evidence, site and period edges, with the locator on the
evidence edge; the graph is live (new rows appear without a sync step); reference resolution; lineage of a
number through a corrected bill, a calculation and a gap, and of a CO2e number; unit conversion shown; impact of
a replaced bill (activities, calculation, gap); walks don't leak through hubs; gap refs, gap resolution, uploads
answering a gap and batch runs become edges; month and per-site graphs with consistent Mermaid/JSON; views rebuilt
when `graph_version` changes; the CLI commands. `tests/test_docs.py` regenerates the examples on this page.
`tests/test_graphdb.py`: the Neo4j projection is exactly the views (every node, every link or a counted skip, only
link shapes the views produce); details and Neo4j-safe values; a sync is one transaction touching only `CR` nodes,
with values as parameters; READ routing; `CR_GRAPH` auto/on/off; a failed sync never breaks the caller; the CLI syncs
after writing commands only; `collect_node` reports the sync; every Cypher query is well-formed, read-only and uses
only link names the views produce; the read-only guard; `why` wording; commands explain how to start Neo4j.

## Commands

| Command | Flags |
| --- | --- |
| `carbonroom ledger trace REF` | `--depth` (default 6) for non-number nodes, `--json` |
| `carbonroom ledger impact REF` | `--depth` (default 4), `--json` |
| `carbonroom ledger graph` | `--period` (required), `--site`, `--format mermaid\|json`, `--depth` (default 3), `--out FILE` (`.md` gets a mermaid fence) |
| `carbonroom graphdb status` | `--json` |
| `carbonroom graphdb sync` | `--json` |
| `carbonroom graphdb why SITE PERIOD` | `--json` (includes the one-sentence `summary`) |
| `carbonroom graphdb conflicts` | `--period`, `--json` |
| `carbonroom graphdb gaps` | `--json` |
| `carbonroom graphdb find TEXT` | `--limit` (default 25), `--json` |
| `carbonroom graphdb query CYPHER` | `--param key=value` (repeatable); always prints JSON |
| `carbonroom graphdb selftest` | (none) |

Settings (`.env.example`): `CR_GRAPH`, `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`.

## How to use

```bash
uv run carbonroom ledger trace ACT-0739d5932d          # where did this number come from?
uv run carbonroom ledger trace ELB-AUS-2610            # what does this bill connect to?
uv run carbonroom ledger impact ELB-AUS-2610           # if this bill is wrong, what changes?
uv run carbonroom ledger graph --period 2026-10 --site austin --out austin-october.md

docker compose -f infra/neo4j/docker-compose.yml up -d  # Neo4j at http://localhost:7474 (neo4j / carbonroom-local)
uv run carbonroom seed                                  # the graph database syncs automatically
uv run carbonroom graphdb selftest                      # every Cypher query against the live server
uv run carbonroom graphdb why reno 2026-10
uv run carbonroom graphdb conflicts --period 2026-10
```
