-- Carbon Room ledger schema (graph-lite, SQLite)
-- Shared contract: Person 1 (Ujjwal) writes into `activities` and `source_docs`.
-- Person 2 (Richa) reads from here and writes `calculations`, `gaps`, `events`.
-- Person 3 (Akshar) only ever sees what the Reporter (report.schema.json) hands out of this.
-- Change only by team agreement (see contracts/CHANGES.md). Rows are never deleted.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS sites (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  region TEXT NOT NULL,              -- e.g. 'US-TX', 'US-NV'
  grid_subregion TEXT NOT NULL,      -- eGRID subregion code, e.g. 'ERCT', 'NWPP'
  owner_handle TEXT NOT NULL,
  room TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS periods (
  id TEXT PRIMARY KEY,               -- 'YYYY-MM'
  status TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN','CLOSED')),
  factor_set_version TEXT,
  approved_by TEXT,
  closed_at TEXT
);

CREATE TABLE IF NOT EXISTS source_docs (
  id TEXT PRIMARY KEY,
  superseded_by TEXT REFERENCES source_docs(id),
  path TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('utility_bill','fuel_invoice','cloud_invoice','rec_certificate','other')),
  sha256 TEXT NOT NULL,
  received_from TEXT,
  room TEXT,
  received_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS activities (
  id TEXT PRIMARY KEY,
  site_id TEXT NOT NULL REFERENCES sites(id),
  period_id TEXT NOT NULL REFERENCES periods(id),
  category TEXT NOT NULL CHECK (category IN ('electricity','natural_gas','diesel','cloud_compute','other')),
  quantity REAL NOT NULL,
  unit TEXT NOT NULL,
  source_doc_id TEXT REFERENCES source_docs(id),
  excerpt TEXT,
  excerpt_locator TEXT,
  excerpt_sha256 TEXT,
  status TEXT NOT NULL DEFAULT 'UNVERIFIED'
    CHECK (status IN ('UNVERIFIED','VERIFIED','FLAGGED','EXCLUDED','SUPERSEDED','MISSING','CONFLICTING')),
  superseded_by TEXT REFERENCES activities(id),
  created_by TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  extra_json TEXT                    -- free-form (PUE, WUE, rec linkage, delivery id, etc.)
);

CREATE TABLE IF NOT EXISTS emission_factors (
  id TEXT PRIMARY KEY,
  set_version TEXT NOT NULL,
  category TEXT NOT NULL,
  region TEXT NOT NULL,              -- eGRID subregion or 'US' for fuel factors
  scope TEXT NOT NULL CHECK (scope IN ('1','2_location','2_market','dc_location','dc_market')),
  factor REAL NOT NULL,
  unit TEXT NOT NULL,
  source_name TEXT NOT NULL,
  source_edition TEXT NOT NULL,
  valid_from TEXT,
  valid_to TEXT
);

CREATE TABLE IF NOT EXISTS calculations (
  id TEXT PRIMARY KEY,
  activity_id TEXT NOT NULL REFERENCES activities(id),
  factor_id TEXT NOT NULL REFERENCES emission_factors(id),
  scope TEXT NOT NULL CHECK (scope IN ('1','2_location','2_market','dc_location','dc_market')),
  co2e_kg REAL NOT NULL,
  computed_at TEXT NOT NULL,
  code_version TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS instruments (
  id TEXT PRIMARY KEY,
  period_id TEXT NOT NULL REFERENCES periods(id),
  kind TEXT NOT NULL CHECK (kind IN ('REC','PPA')),
  mwh REAL NOT NULL,
  region TEXT NOT NULL,
  vintage TEXT NOT NULL,
  source_doc_id TEXT REFERENCES source_docs(id),
  quality_flags TEXT                 -- e.g. 'region_mismatch', 'vintage_mismatch', 'ok'
);

CREATE TABLE IF NOT EXISTS gaps (
  id TEXT PRIMARY KEY,
  period_id TEXT NOT NULL REFERENCES periods(id),
  site_id TEXT REFERENCES sites(id),
  kind TEXT NOT NULL CHECK (kind IN ('missing_doc','conflict','stale_factor','outlier','excerpt_mismatch','unverified_claim','rec_quality')),
  detail TEXT NOT NULL,
  owner_handle TEXT NOT NULL,
  room TEXT NOT NULL,
  thread_id TEXT,
  status TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN','RESOLVED','ACCEPTED_RISK')),
  resolution TEXT,
  resolved_by TEXT,
  resolved_at TEXT,
  created_at TEXT NOT NULL,
  dedupe_key TEXT NOT NULL UNIQUE    -- same gap never created twice (idempotent checker)
);

CREATE TABLE IF NOT EXISTS approvals (
  id TEXT PRIMARY KEY,
  period_id TEXT NOT NULL REFERENCES periods(id),
  approver_handle TEXT NOT NULL,
  decision TEXT NOT NULL CHECK (decision IN ('APPROVE','REJECT')),
  note TEXT,
  report_sha256 TEXT,
  at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
  id TEXT PRIMARY KEY,
  at TEXT NOT NULL,
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  ref TEXT NOT NULL,                 -- json blob: {claim_id/gap_id, before_status, after_status, ...}
  prev_event_hash TEXT,
  event_hash TEXT NOT NULL
);
