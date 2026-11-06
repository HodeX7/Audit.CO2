# Carbon Room — Shared Contracts

**This is the single source of truth for every type, table, function signature, config key and chat command that crosses a person's boundary.** Every story in `P1-*.md`, `P2-*.md` and `P3-*.md` names the sections it needs, for example "Read: §2, §5". An AI agent working on a story reads only those sections, never the whole file.

**Changing a contract:** don't edit this file in a feature branch. Write a proposal (see §11) and get the section owner to approve it, then update this file in its own small PR.

| § | Section | Owner |
|---|---|---|
| 1 | Conventions | P1 |
| 2 | Shared types (`carbon_room/models.py`) | P1 |
| 3 | Database schema (`carbon_room/ledger/schema.sql`) | P1 |
| 4 | Core API (`carbon_room/core.py`) | P1 (facade), implementers named per function |
| 5 | Ledger API (`carbon_room/ledger/ledger.py`) | P1 |
| 6 | Findings, options and resolve actions | P2 |
| 7 | Status, verification and phase rules | P2 |
| 8 | Room grammar (commands and replies) | P3 |
| 9 | Config files | P2 (`carbon_room.yaml`, `factors.csv`), P1 (`sites.yaml`), P3 (`people.yaml`) |
| 10 | Seed scenario and traps | P1, agreed with P2 |
| 11 | Proposal process | Team lead |

---

## §1 Conventions

- Python 3.11. Package name `carbon_room`. Tests with `pytest`. Lint with `ruff`. Dependencies go in `pyproject.toml`: `langgraph`, `anthropic`, `websockets`, `httpx`, `pdfplumber`, `reportlab`, `pyyaml`, `python-dotenv`.
- **Quantities are `decimal.Decimal` in code and `TEXT` in SQLite.** Never use `float` for a quantity or a factor.
- **Times** are ISO 8601 UTC strings (`2026-11-05T14:03:22Z`).
- **Months** are `YYYY-MM`.
- **Site ids** come from `sites.yaml` (`hq`, `warehouse-2`, `dc-eu-west`). Code outside the seed and config never contains a site id, month or claim id as a literal (the tests check for this).
- **Id formats:**

| Thing | Format | Example |
|---|---|---|
| Close | `<month>-v<n>` | `2026-10-v1` |
| Source | `SRC-<4 digits>` | `SRC-0007` |
| Claim | `CL-<4 digits>` | `CL-0012` |
| Calculation | `CA-<4 digits>` | `CA-0012` |
| Gap | `G-<n>`, numbered per close | `G-2` |
| Finding | `F-` + first 10 hex chars of sha256(`rule|kind|site|month|sorted claim_ids`) | `F-3fa91c02be` |
| Source tag | `S-<3 digits>`, numbered per close version | `S-014` |
| Event | Integer, auto-increment | `57` |

- **Units:** activity units are `kWh` and `L`. Factor units are `kgCO2e/kWh` and `kgCO2e/L`. Results are stored in `kgCO2e` and shown in `tCO2e` to 1 decimal place.
- **Rounding:** store full precision; round only when displaying.
- Each module uses `logging.getLogger(__name__)`. No `print` outside the CLI.
- **Any state change triggered by a human must carry a `chat_message_id` from a Switch event.** If it is missing, raise `NeedsRoomEvent`.

---

## §2 Shared types — `carbon_room/models.py`

Plain `@dataclass`es. Frozen at milestone M0. Only P1 edits this file, and only through a proposal.

```python
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

Status = Literal["VERIFIED", "UNVERIFIED", "CONFLICTING", "STALE", "MISSING"]
# Claims only ever use VERIFIED / UNVERIFIED / CONFLICTING / STALE.
# MISSING is used as a Finding/Gap kind (an expected source with no claim).
Phase = Literal["OPEN", "COLLECTING", "CALCULATING", "CHECKING",
                "AWAITING_HUMANS", "RECHECKING", "DRAFTED", "PUBLISHED"]
SourceKind = Literal["utility_pdf", "email_invoice", "drive_csv", "cloud_invoice"]
Activity = Literal["electricity_kwh", "diesel_l", "dc_it_kwh"]

@dataclass(frozen=True)
class Actor:
    kind: Literal["human", "agent", "system"]
    id: str            # person id from people.yaml, or agent name e.g. "watchdog"
    name: str
    role: str | None = None   # lead | finance | site_manager | auditor | None for agents

@dataclass
class Source:
    source_doc_id: str; close_id: str; site: str | None; kind: SourceKind
    file_name: str; stored_path: str; sha256: str; page_count: int; raw_text: str
    period_start: str | None; period_end: str | None   # dates read from the document text
    extract_status: Literal["OK", "FAILED"]; extract_error: str | None

@dataclass
class Claim:
    claim_id: str; close_id: str; site: str; month: str; activity: Activity
    value: Decimal; unit: str; scope: Literal["1", "2", "3", "DC"]
    source_doc_id: str; source_excerpt: str; source_sha256: str; source_page: int
    factor_id: str | None; factor_version: str | None
    status: Status; extracted_by: str; checked_by: str | None; superseded_by: str | None
    attributes: dict = field(default_factory=dict)  # e.g. pue, region, market_based_kgco2e, invoice_ref, vendor_factor_ref

@dataclass
class Calculation:
    calc_id: str; claim_id: str; factor_id: str; factor_version: str
    activity_value: Decimal; activity_unit: str; factor_value: Decimal; factor_unit: str
    kgco2e: Decimal; formula: str              # human-readable, e.g. "48200 kWh × 0.13100 kgCO2e/kWh"
    basis: Literal["location", "market"] | None

@dataclass
class Option:
    key: str            # exactly what a human types, e.g. "pick A", "approve", "upload"
    action: Literal["pick", "approve", "reject", "upload"]
    label: str          # shown in the thread, e.g. "Invoice 4471 — 2,150 L"
    params: dict = field(default_factory=dict)

@dataclass
class Finding:
    finding_id: str; rule: Literal["R1", "R2", "R3", "R4", "R5", "R6", "R7"]
    kind: Literal["MISSING", "CONFLICTING", "STALE", "PERIOD", "VARIANCE", "DATACENTRE", "FINANCE"]
    claim_ids: list[str]; site: str; month: str
    owner: str          # person id from people.yaml
    title: str          # one line, e.g. "Warehouse-2 October electricity bill is missing"
    evidence: list[str] # exact excerpts or computed facts, never paraphrase
    options: list[Option]; tier: Literal[1, 2, 3]
    blocking: bool      # True = the claims it names cannot be VERIFIED while it is open

@dataclass
class Gap:
    gap_id: str; close_id: str; finding_id: str; rule: str; kind: str; title: str
    owner: str; status: Literal["OPEN", "RESOLVED"]; claim_ids: list[str]
    options: list[Option]
    thread_root_message_id: str | None; opened_at: str
    resolved_by: str | None; resolved_message_id: str | None; resolution: dict | None

@dataclass
class IngestReport:
    close_id: str; sources_seen: int; claims_created: list[str]; failed_sources: list[str]
    statement: str      # the collector's own claim, e.g. "All 6 October sources collected."

@dataclass
class DcLine:
    location_kgco2e: Decimal | None; market_kgco2e: Decimal | None; pue: Decimal | None
    rec_flag: str       # e.g. "Market-based 0 relies on certificates; certificate quality not verified"
    ai_line_status: Literal["UNVERIFIED"]; note: str

@dataclass
class CloseSummary:
    close_id: str; phase: Phase
    verified_kgco2e: Decimal; excluded_kgco2e: Decimal; coverage_pct: Decimal
    sources_expected: int; sources_verified: int
    open_gaps: list[Gap]; dc_line: DcLine | None

@dataclass
class SourceTag:
    tag: str; file_name: str; page: int; excerpt: str; sha256: str
    activity: str; value: Decimal; unit: str
    factor_id: str; factor_version: str; geography: str
    recompute: str; kgco2e: Decimal; status: Status
    approver: str | None; chat_message_id: str | None

@dataclass
class Report:
    close_id: str; version: int
    verified_total_tCO2e: Decimal; unverified_excluded_tCO2e: Decimal; coverage_pct: Decimal
    source_coverage: str            # e.g. "5 of 6 expected sources verified"
    gaps: list[dict]; conflicts: list[dict]; factor_versions: list[str]
    datacentre_line: DcLine | None; s_tags: list[SourceTag]; compliance_flags: list[str]
    approver: str | None; published_at: str | None

@dataclass
class AuditCheck:
    ok: bool; events: int; first_bad_event_id: int | None

class CarbonRoomError(Exception): ...
class NeedsRoomEvent(CarbonRoomError): ...   # human action without chat_message_id
class NotAllowed(CarbonRoomError): ...       # actor's role may not do this
class LockHeld(CarbonRoomError): ...         # claim lock held by another actor
class BudgetExceeded(CarbonRoomError): ...   # agent token budget at 100%
class NotFound(CarbonRoomError): ...
```

---

## §3 Database schema — `carbon_room/ledger/schema.sql`

One SQLite file at `var/carbon_room.db`, with `PRAGMA foreign_keys=ON` and `journal_mode=WAL`. **Never `DELETE` or `UPDATE` a history column**; supersede instead. The only updatable columns are `status`, `checked_by`, `superseded_by`, `factor_id`, `factor_version` on claims, `phase`/`published_*` on closes, and `status`/`thread_root_message_id`/`resolved_*`/`resolution` on gaps. Every one of those updates also writes an event.

| Table | Key columns |
|---|---|
| `closes` | `close_id` PK, `month`, `sites` (JSON), `factor_set`, `phase`, `version`, `created_by`, `created_message_id`, `published_by`, `published_message_id`, `published_at` |
| `sources` | `source_doc_id` PK, `close_id` FK, `site`, `kind`, `file_name`, `stored_path`, `sha256`, `page_count`, `raw_text`, `period_start`, `period_end`, `extract_status`, `extract_error`, `ingested_by`, `ingested_at`. UNIQUE(`close_id`, `sha256`) |
| `claims` | all `Claim` fields (`attributes` as JSON), `created_at` |
| `factors` | `factor_id` PK, `source` (DEFRA/EGRID/EMBER), `version`, `year`, `activity`, `geography`, `value`, `unit`, `citation` |
| `calculations` | all `Calculation` fields, `created_at`, `superseded_by` |
| `gaps` | all `Gap` fields (`claim_ids`, `options`, `resolution` as JSON). UNIQUE(`close_id`, `finding_id`) |
| `approvals` | `approval_id` PK, `close_id`, `subject_type` (claim/gap/publish), `subject_id`, `tier`, `actor_id`, `role`, `decision` (approve/reject), `reason`, `chat_message_id` NOT NULL, `created_at` |
| `events` | `event_id` INTEGER PK, `close_id`, `actor`, `kind`, `claim_id`, `before_status`, `after_status`, `chat_message_id`, `timestamp`, `reason`, `payload` (JSON), `prev_hash`, `hash` |
| `locks` | PK(`close_id`, `site`, `month`, `source_doc_id`), `holder`, `acquired_at` |
| `budgets` | PK(`close_id`, `agent`), `tokens_used`, `limit_tokens` |
| `s_tags` | PK(`close_id`, `version`, `tag`), `calc_id`, `claim_id` |
| view `edges` | `(src, rel, dst)` rows derived from foreign keys: site–CONSUMED→claim, claim–FROM→source, claim–USES→factor, calculation–OF→claim, gap–ABOUT→claim, approval–APPROVES→subject |

---

## §4 Core API — `carbon_room/core.py`

The **only** module the room layer (P3) calls. `core.py` is a thin facade (P1 owns the file) that delegates to the module named in the Impl column. Every function takes `db` implicitly from `carbon_room.ledger.connect()`.

| Function | Returns | Impl | Notes |
|---|---|---|---|
| `start_close(month, sites, factor_set, actor, chat_message_id)` | `close_id` | P1 | Creates the close (phase OPEN), locks the factor set |
| `ingest(close_id, actor)` | `IngestReport` | P1 | Ingests every file in `data/seed/<month>/` plus `data/seed/<prev month>/`; phase COLLECTING |
| `ingest_file(close_id, path, actor, chat_message_id, site=None)` | `list[claim_id]` | P1 | Used when a human uploads a source |
| `calculate(close_id)` | `list[Calculation]` | P2 | Phase CALCULATING. Idempotent |
| `check(close_id)` | `list[Finding]` | P2 | Runs R1–R7, upserts gaps, runs the verification pass; phase CHECKING then AWAITING_HUMANS or DRAFTED-ready. Idempotent |
| `resolve(gap_id, action, actor, chat_message_id, payload)` | `list[Finding]` | P2 | Applies an Option action (§6), then re-runs calculate + check. Phase RECHECKING |
| `summary(close_id)` | `CloseSummary` | P2 | Pure read |
| `draft_report(close_id)` | `Report` | P2 | Phase DRAFTED. Assigns S-tags |
| `publish(close_id, actor, chat_message_id)` | `Report` | P2 | Role check (§9 `publish_roles`), writes `out/<month>/v<n>/`, phase PUBLISHED |
| `trace(close_id, tag)` | `SourceTag` | P2 | Recomputes from the ledger, not from the report file |
| `verify_audit(close_id)` | `AuditCheck` | P1 | Walks the hash chain |
| `resume_state(close_id)` | `(Phase, list[Gap])` | P1 | Used by `@carbon-room resume` after a crash |
| `latest_close()` | `close_id or None` | P1 | |
| `gap_for_thread(thread_root_message_id)` | `Gap or None` | P1 | Router uses it to map a thread reply to its gap |
| `record_gap_thread(close_id, gap_id, message_id)` | `None` | P1 | Called right after the gap's root post |
| `budget_usage(close_id)` | `dict[agent, {used, limit, state}]` | P1 | `state` is `ok`, `warn` or `stopped`; the room posts a warning once per agent |
| `explain(close_id, question, actor)` | `str` | P1 | Answers a free-text question. The LLM may only phrase facts that a ledger query returned; if the query finds no VERIFIED rows, it answers UNKNOWN with reason and owner |

---

## §5 Ledger API — `carbon_room/ledger/ledger.py`

P2 uses these. P3 never imports the ledger directly.

```python
connect(path="var/carbon_room.db") -> sqlite3.Connection
init_db(conn) -> None
create_close(conn, month, sites, factor_set, actor, chat_message_id) -> str
get_close(conn, close_id) -> dict
set_phase(conn, close_id, phase, actor) -> None
add_source(conn, source: Source, actor) -> str
get_sources(conn, close_id, *, site=None) -> list[Source]
add_claim(conn, claim: Claim, actor) -> str                  # status forced to UNVERIFIED
get_claim(conn, claim_id) -> Claim
get_claims(conn, close_id, *, site=None, month=None, activity=None, live_only=True) -> list[Claim]
set_status(conn, claim_id, new_status, actor, reason, chat_message_id=None) -> None
set_factor(conn, claim_id, factor_id, factor_version, actor, reason, chat_message_id=None) -> None
supersede(conn, old_claim_id, new_claim_id | None, actor, reason, chat_message_id) -> None
add_calculation(conn, calc: Calculation) -> str              # supersedes the previous calc for that claim
latest_calculation(conn, claim_id) -> Calculation | None
upsert_gap(conn, close_id, finding: Finding) -> Gap          # same finding_id → same gap, no duplicate
get_gaps(conn, close_id, *, status=None) -> list[Gap]
get_gap(conn, gap_id, close_id) -> Gap
get_gap_by_thread(conn, thread_root_message_id) -> Gap | None
set_gap_thread(conn, close_id, gap_id, message_id) -> None
resolve_gap(conn, close_id, gap_id, actor, chat_message_id, resolution: dict) -> None
add_approval(conn, close_id, subject_type, subject_id, tier, actor, decision, reason, chat_message_id) -> str
get_approvals(conn, close_id, *, subject_id=None) -> list[dict]
load_factors(conn, rows: list[dict]) -> int
get_factor(conn, factor_id) -> dict
find_factor(conn, source, version, activity, geography) -> dict | None
assign_s_tags(conn, close_id, version, calc_ids: list[str]) -> dict[str, str]   # calc_id → S-###
get_s_tag(conn, close_id, tag) -> dict
append_event(conn, close_id, actor, kind, *, claim_id=None, before=None, after=None,
             chat_message_id=None, reason="", payload=None) -> int
```

**Guardrails inside the ledger (P1 builds them, everyone relies on them):**
- `set_status`, `supersede`, `resolve_gap`, `add_approval` and `set_factor` raise `NeedsRoomEvent` if `actor.kind == "human"` and `chat_message_id` is empty.
- `set_status(..., "VERIFIED")` raises `NotAllowed` unless the actor is `system` or the agent `watchdog`.
- No function deletes a row.
- Every mutating call writes exactly one event.

---

## §6 Findings, options and resolve actions

Each rule produces a Finding with fixed option keys. P3's router matches a human's thread reply to one of the gap's option keys, case-insensitively, and calls `resolve(gap_id, option.action, actor, chat_message_id, option.params | extra)`.

| Rule | Kind | Blocking | Tier | Options (`key` → `action`, `params`) | Default owner |
|---|---|---|---|---|---|
| R1 | MISSING | n/a (no claim) | 2 | `upload` → upload, `{site, month, activity}` | Site owner (`sites.yaml`) |
| R2 | CONFLICTING | yes | 2 | `pick A` → pick `{claim_id: A}`; `pick B` → pick `{claim_id: B}` | Lead |
| R3 | STALE | yes | 2 | `approve` → approve `{use_factor_id: <locked>}`; `reject` → reject | Lead |
| R4 | PERIOD | yes | 2 | `upload` → upload `{site, month, activity}` | Site owner |
| R5 | VARIANCE | yes | 2 | `approve` → approve; `reject` → reject | Lead |
| R6 | DATACENTRE | no (AI line is excluded by policy, not by a gap) | 2 | none; informational, names who must ask the vendor | Lead |
| R7 | FINANCE | no | 2 | `approve`, `reject` | Finance |

**What each action does in `resolve` (P2):**
- **pick** — The chosen claim stays live. Each other claim in `claim_ids` is superseded by the chosen one with reason `"human picked <chosen> in <gap_id>"`. Records an approval for the chosen claim. Resolves the gap.
- **approve** — Records an approval (tier 2) for every claim in `claim_ids`. If `use_factor_id` is present, calls `set_factor` first. Resolves the gap.
- **reject** — Records a reject approval. The claims stay excluded. Resolves the gap with `resolution={"outcome": "excluded", "reason": ...}`.
- **upload** — `payload["path"]` is required (a downloaded attachment, or `data/inbox/<file>` under spike fallback S2). Calls `core.ingest_file`. If the gap lists claims (the R4 case), each one is superseded by the new claim with reason `"replaced by upload in <gap_id>"`. The gap resolves only if the next `check` no longer produces the same finding.
- After every action: `calculate` → `check`. Return the new findings.

---

## §7 Status, verification and phase rules

**Verification pass** (run at the end of every `check`, P2): a live claim becomes `VERIFIED` only if **all** of these hold:
1. It has a calculation whose factor belongs to the close's locked factor set.
2. No OPEN gap with `blocking=True` lists it.
3. Either Tier 1 applies (same factor version as the previous month's claim for that site and activity, variance below threshold, source present), **or** there is an `approve` approval for it.

Otherwise its status is the strongest open finding on it: `CONFLICTING` > `STALE` > `UNVERIFIED`. A VERIFIED claim never goes back; a new close version starts over.

**Totals:**
- Only claims whose `month` equals the close month count. Previous-month claims are ingested into the same close as a baseline for R5 and Tier 1, and are never added to a total.
- `verified_kgco2e` = sum of the latest calculation of each VERIFIED claim. Data-centre market-based is excluded; the location-based figure counts if verified.
- `excluded_kgco2e` = the same sum over live non-VERIFIED claims that have a calculation.
- `coverage_pct` = verified ÷ (verified + excluded) × 100, to 0 decimals.
- `sources_expected` comes from `sites.yaml` for the close month. `sources_verified` = expected (site, activity) pairs with a VERIFIED claim.
- The AI line is never a number. It is listed as UNVERIFIED with a reason.

**Phases:** `start_close` → OPEN; `ingest` → COLLECTING; `calculate` → CALCULATING; `check` → CHECKING, then AWAITING_HUMANS if any gap is OPEN; `resolve` → RECHECKING, then back to AWAITING_HUMANS or CHECKING; `draft_report` → DRAFTED; `publish` → PUBLISHED. **A report with open gaps can be published.** The gaps are listed and their rows excluded. That honesty is the product.

---

## §8 Room grammar

Commands are parsed by P3's router. Matching ignores case and extra spaces.

| Who | Text | Intent | Calls |
|---|---|---|---|
| any human | `@carbon-room close <Month> [<YYYY>]` | close.start | start_close → ingest → calculate → check |
| any human | `@carbon-room status` | close.status | summary |
| any human | `@carbon-room resume` | close.resume | resume_state, then reposts open gaps |
| lead | `@carbon-room publish` | close.publish | draft_report if needed, then publish |
| any human | `@reporter draft` | report.draft | draft_report |
| any human | `@reporter trace S-014` | report.trace | trace |
| any human | `@reporter verify audit` | audit.verify | verify_audit |
| any human | `@collector …`, `@watchdog …`, other free text addressed to an agent | ask | explain |
| owner or lead, **reply inside a gap thread** | an option key: `pick A`, `pick B`, `approve`, `reject <reason>`, `upload` | gap.resolve | resolve |
| owner, reply inside a gap thread | any message with a file attachment | gap.resolve (upload) | resolve with `path` |
| anyone (fallback if threads fail, spike S1) | `G-2 pick A` anywhere in the room | gap.resolve | resolve |

**Reactions (emoji) are never an approval.** Switch does not deliver reaction events.

**Agent names** registered in Switch: `carbon-room`, `collector`, `watchdog`, `reporter`.

---

## §9 Config files

### `config/carbon_room.yaml` (P2)
```yaml
factor_sets:
  FS-2026-10: { DEFRA: "2026", EGRID: "2024", EMBER: "2025" }
default_factor_set: FS-2026-10
rules:
  variance_threshold: 0.10
  conflict_tolerance: 0.005      # relative difference
  stale_max_age_months: 12
approvals:
  approve_roles: [lead, finance]
  publish_roles: [lead]
  tier1: { same_factor_version: true, max_variance: 0.10 }
budgets:
  default_tokens: 200000
  warn_at: 0.8
llm:
  provider: anthropic
  model: claude-sonnet-5-5
  temperature: 0
  mode: replay                   # replay | live
noise:
  max_top_level_posts: 12
datacentre:
  show_market: true
  ai_line_policy: UNVERIFIED
scope3:
  computed: []
  listed_as_no_data: ["Cat 1 Purchased goods and services", "Cat 6 Business travel"]
```

### `config/sites.yaml` (P1)
```yaml
sites:
  - id: hq
    name: HQ
    country: US
    grid: { source: EGRID, geography: CAMX }
    owner: lead
    expected: [ {kind: utility_pdf, activity: electricity_kwh}, {kind: email_invoice, activity: diesel_l} ]
  - id: warehouse-2
    name: Warehouse-2
    country: GB
    grid: { source: DEFRA, geography: UK }
    owner: priya
    expected: [ {kind: utility_pdf, activity: electricity_kwh} ]
  - id: dc-eu-west
    name: Data Centre EU-West
    country: IE
    grid: { source: EMBER, geography: IE }
    owner: lead
    expected: [ {kind: cloud_invoice, activity: dc_it_kwh} ]
diesel_factor: { source: DEFRA, geography: UK }   # fuel factor used for every site
```

### `config/people.yaml` (P3)
```yaml
people:
  - { id: lead,    name: "Sustainability Lead", role: lead,         switch_ids: ["<filled in by P3>"] }
  - { id: priya,   name: "Priya",               role: site_manager, sites: [warehouse-2], switch_ids: ["<filled in>"] }
  - { id: finance, name: "Finance Approver",    role: finance,      switch_ids: [] }
  - { id: auditor, name: "External Auditor",    role: auditor,      switch_ids: [] }
```
If a sender's Switch id isn't listed, they are treated as a guest. They can ask questions but can't resolve, approve or publish.

### `config/factors.csv` (P2)
Columns: `factor_id, source, version, year, activity, geography, value, unit, citation`. Every row's `citation` names the publication, its table and the URL. **Values come from the published sources. Never invent one.** Must include one deliberately outdated row (`EMBER 2024 IE`) for the stale trap.

---

## §10 Seed scenario and traps

All seed documents are synthetic and labelled `SAMPLE — synthetic demo data` on every page. Generated by `scripts/make_seed.py` (P1), so they can be rebuilt.

| Month | File | Site | Purpose |
|---|---|---|---|
| 2026-09 | `hq_electricity_2026-09.pdf` | hq | Baseline for variance |
| 2026-09 | `hq_diesel_2026-09_inv-4402.eml` | hq | Clean |
| 2026-09 | `warehouse2_electricity_2026-09.pdf` | warehouse-2 | Clean |
| 2026-09 | `dc_euwest_cloud_2026-09.json` | dc-eu-west | Clean, current Ember factor |
| 2026-10 | `hq_electricity_2026-10.pdf` | hq | **Variance trap (R5):** kWh = September × 1.38 |
| 2026-10 | `hq_diesel_2026-10_inv-4471.eml` | hq | **Conflict trap (R2), A** |
| 2026-10 | `hq_diesel_2026-10_inv-4471-rev.eml` | hq | **Conflict trap (R2), B:** same period, 400 L different |
| 2026-10 | `warehouse2_electricity_2026-10.pdf` | warehouse-2 | **False-done trap (R4):** file name says October, printed billing period is 1–30 Sep 2026. This also causes **R1 MISSING** for Warehouse-2 October (owner Priya) |
| 2026-10 | `dc_euwest_cloud_2026-10.json` | dc-eu-west | **Stale trap (R3):** vendor's figure uses `vendor_factor_ref: "Ember 2024 IE"`; locked set is Ember 2025. Also has PUE and region, market-based 0 from certificates, and **no per-model AI breakdown** (R6) |
| — | `data/demo_uploads/warehouse2_electricity_2026-10_actual.pdf` | warehouse-2 | Not in the seed. The bill Priya uploads in the demo |

**Collector's statement after ingest:** "All 5 October sources collected." This is the false "done" the Watchdog disproves.

**Change from the architecture page:** the MISSING and false-done traps share one file and one thread (Warehouse-2). This saves demo time and is more realistic, since a mislabelled bill is usually *why* a bill goes missing. The stale trap sits on the cloud invoice, so it also feeds the data-centre line.

`data/seed/EXPECTED.md` is generated by running the pipeline, never written by hand. It records the expected findings, totals before resolution, and totals after the scripted demo resolutions.

---

## §11 Proposal process (spec-driven development)

1. **Every story is a spec.** Before writing code, the developer or AI agent writes a plan of five lines or fewer in the PR description: files to touch, functions to add, and tests to add. If the plan needs anything outside the story's "Files" list, stop and ask.
2. **A contract change needs a proposal.** Create `docs/proposals/NNN-short-title.md` with four headings: *Problem*, *Change* (exact diff to this file), *Who is affected* (story ids), and *Decision* (left blank for the section owner). Post its link in the team chat. The section owner approves or rejects within 2 hours during build days.
3. **One story = one branch = one PR.** Branch name: `p1-2.3-set-status`. Each PR has the story id in its title.
4. **Definition of done for every story:**
   - `pytest` passes.
   - `ruff check` passes.
   - The story's "Done when" boxes are ticked in the PR.
   - No site id, month or claim id is a literal outside `config/`, `data/` and `tests/fixtures/`.
   - No contract change without a merged proposal.
