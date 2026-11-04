-- Carbon Room ledger schema (SQLite, "graph-lite").
-- Contract owner: Ujjwal (Person 1). Agreed by the team; change only via contracts/CHANGES.md.
--
-- Conventions
--   * Every quantity, factor and result is a DECIMAL STRING (TEXT), e.g. '191300' or '499.998'.
--     Read it with decimal.Decimal(row["quantity"]); never float. This keeps the math deterministic.
--   * Timestamps are ISO-8601 UTC strings ('2026-11-03T18:31:00Z').
--   * Periods are 'YYYY-MM'.
--   * HONESTY RULE 3: rows are never deleted. Every table has a trigger that aborts DELETE.
--     A corrected document SUPERSEDES the old one; the old row stays queryable (superseded_by).
--   * Additive columns beyond the Section 5.3 contract are marked "additive" and listed in
--     contracts/CHANGES.md.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

-- Sites, plus the cloud provider line (kind = 'cloud'). Cloud is Scope 3 Cat 1, never Scope 2.
CREATE TABLE IF NOT EXISTS sites (
  id             TEXT PRIMARY KEY,                -- 'austin', 'reno', 'nimbus-cloud'
  name           TEXT NOT NULL,                   -- 'Austin Plant'
  region         TEXT,                            -- 'TX'
  grid_subregion TEXT,                            -- eGRID subregion acronym, e.g. 'ERCT'
  owner_handle   TEXT,                            -- chat handle of the person who owns the evidence
  room           TEXT,                            -- Switch room for this site's gaps
  kind           TEXT NOT NULL DEFAULT 'facility' CHECK (kind IN ('facility','cloud')),  -- additive
  aliases_json   TEXT NOT NULL DEFAULT '[]'       -- additive: names that identify the site in documents
);

CREATE TABLE IF NOT EXISTS periods (
  id                 TEXT PRIMARY KEY CHECK (id GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]'),
  status             TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN','CLOSED')),
  factor_set_version TEXT,
  approved_by        TEXT,
  closed_at          TEXT
);

CREATE TABLE IF NOT EXISTS source_docs (
  id            TEXT PRIMARY KEY,                 -- 'DOC-' + first 12 hex chars of sha256
  superseded_by TEXT REFERENCES source_docs(id),
  path          TEXT NOT NULL,                    -- repo-relative where possible
  kind          TEXT NOT NULL CHECK (kind IN ('utility_bill','fuel_invoice','cloud_invoice','rec_certificate','other')),
  sha256        TEXT NOT NULL UNIQUE,             -- duplicates are skipped by this hash
  received_from TEXT,                             -- chat handle or 'seed' / 'inbox'
  room          TEXT,
  received_at   TEXT NOT NULL,
  original_name TEXT,                             -- additive: file name as uploaded
  doc_ref       TEXT,                             -- additive: number printed on the doc, e.g. 'INV-204'
  page_count    INTEGER,                          -- additive
  meta_json     TEXT NOT NULL DEFAULT '{}'        -- additive: thread_id, message_id, notes
);

CREATE TABLE IF NOT EXISTS activities (
  id              TEXT PRIMARY KEY,               -- 'ACT-' + 10 hex chars (deterministic)
  site_id         TEXT NOT NULL REFERENCES sites(id),
  period_id       TEXT NOT NULL REFERENCES periods(id),
  category        TEXT NOT NULL,                  -- electricity / natural_gas / diesel / cloud_compute
  quantity        TEXT NOT NULL CHECK (quantity GLOB '*[0-9]*' AND quantity NOT GLOB '*[^0-9.]*'),
  unit            TEXT NOT NULL,                  -- normalized: kWh / therm / gal
  source_doc_id   TEXT NOT NULL REFERENCES source_docs(id),
  excerpt         TEXT NOT NULL,                  -- verbatim text found in the source page
  excerpt_locator TEXT NOT NULL,                  -- 'page=1;line=14' (computed by code, not by the LLM)
  excerpt_sha256  TEXT NOT NULL,                  -- sha256 of the whitespace-normalized excerpt
  status          TEXT NOT NULL DEFAULT 'UNVERIFIED'
                  CHECK (status IN ('UNVERIFIED','VERIFIED','FLAGGED','EXCLUDED','SUPERSEDED')),
  superseded_by   TEXT REFERENCES activities(id),
  created_by      TEXT NOT NULL,
  updated_at      TEXT NOT NULL,
  extra_json      TEXT NOT NULL DEFAULT '{}',     -- original unit/quantity, evidence for extra fields
  status_reason   TEXT,                           -- additive: why the status last changed
  created_at      TEXT                            -- additive
);

CREATE TABLE IF NOT EXISTS emission_factors (
  id             TEXT PRIMARY KEY,
  set_version    TEXT NOT NULL,
  category       TEXT NOT NULL,
  region         TEXT,
  scope          TEXT NOT NULL,
  factor         TEXT NOT NULL,                   -- decimal string
  unit           TEXT NOT NULL,                   -- e.g. 'kg CO2e/kWh'
  source_name    TEXT NOT NULL,
  source_edition TEXT NOT NULL,
  valid_from     TEXT,
  valid_to       TEXT
);

CREATE TABLE IF NOT EXISTS calculations (
  id           TEXT PRIMARY KEY,
  activity_id  TEXT NOT NULL REFERENCES activities(id),
  factor_id    TEXT NOT NULL REFERENCES emission_factors(id),
  scope        TEXT NOT NULL CHECK (scope IN ('1','2_location','2_market','dc_location','dc_market')),
  co2e_kg      TEXT NOT NULL,                     -- decimal string
  computed_at  TEXT NOT NULL,
  code_version TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS instruments (
  id             TEXT PRIMARY KEY,                -- 'INS-' + 10 hex chars
  period_id      TEXT NOT NULL REFERENCES periods(id),
  kind           TEXT NOT NULL CHECK (kind IN ('REC','PPA')),
  mwh            TEXT NOT NULL CHECK (mwh GLOB '*[0-9]*' AND mwh NOT GLOB '*[^0-9.]*'),
  region         TEXT,                            -- generation region as printed, e.g. 'WECC Northwest (Oregon)'
  vintage        TEXT,                            -- generation year, e.g. '2023'
  source_doc_id  TEXT NOT NULL REFERENCES source_docs(id),
  quality_flags  TEXT NOT NULL DEFAULT '[]',      -- JSON list, set by the checker (e.g. ["region_mismatch"])
  site_id        TEXT REFERENCES sites(id),       -- additive: the load the certificate is claimed against
  certificate_id TEXT,                            -- additive
  excerpt         TEXT,                           -- additive: evidence for mwh
  excerpt_locator TEXT,                           -- additive
  excerpt_sha256  TEXT,                           -- additive
  status          TEXT NOT NULL DEFAULT 'UNVERIFIED'
                  CHECK (status IN ('UNVERIFIED','VERIFIED','FLAGGED','EXCLUDED','SUPERSEDED')),  -- additive
  superseded_by   TEXT REFERENCES instruments(id),  -- additive
  extra_json      TEXT NOT NULL DEFAULT '{}',     -- additive: evidence for region, vintage, claimed site
  created_by      TEXT,                           -- additive
  updated_at      TEXT                            -- additive
);

CREATE TABLE IF NOT EXISTS gaps (
  id           TEXT PRIMARY KEY,                  -- 'GAP-001'
  period_id    TEXT REFERENCES periods(id),
  site_id      TEXT REFERENCES sites(id),
  kind         TEXT NOT NULL CHECK (kind IN ('missing_doc','conflict','stale_factor','outlier',
                                             'excerpt_mismatch','unverified_claim','rec_quality')),
  detail       TEXT NOT NULL,
  owner_handle TEXT,
  room         TEXT,
  thread_id    TEXT,
  status       TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN','RESOLVED','ACCEPTED_RISK')),
  resolution   TEXT,
  resolved_by  TEXT,
  resolved_at  TEXT,
  created_at   TEXT NOT NULL,                     -- additive
  created_by   TEXT NOT NULL,                     -- additive
  dedupe_key   TEXT UNIQUE,                       -- additive: stops the same gap being opened twice
  refs_json    TEXT NOT NULL DEFAULT '{}'         -- additive: activity / doc ids the gap is about
);

CREATE TABLE IF NOT EXISTS approvals (
  id              TEXT PRIMARY KEY,
  period_id       TEXT NOT NULL REFERENCES periods(id),
  approver_handle TEXT NOT NULL,
  decision        TEXT NOT NULL CHECK (decision IN ('APPROVE','REJECT')),
  note            TEXT,
  report_sha256   TEXT,
  at              TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  at          TEXT NOT NULL,
  actor       TEXT NOT NULL,
  action      TEXT NOT NULL,
  ref         TEXT,
  detail_json TEXT NOT NULL DEFAULT '{}'          -- additive
);

-- Additive: which evidence each site is expected to provide, so a missing bill is detectable.
CREATE TABLE IF NOT EXISTS expected_documents (
  id           TEXT PRIMARY KEY,                  -- 'EXP-reno-electricity'
  site_id      TEXT NOT NULL REFERENCES sites(id),
  category     TEXT NOT NULL,
  doc_kind     TEXT NOT NULL,
  frequency    TEXT NOT NULL CHECK (frequency IN ('monthly','as_delivered')),
  owner_handle TEXT,
  note         TEXT
);

CREATE INDEX IF NOT EXISTS idx_activities_period ON activities(period_id, site_id, category);
CREATE INDEX IF NOT EXISTS idx_activities_doc    ON activities(source_doc_id);
CREATE INDEX IF NOT EXISTS idx_gaps_period       ON gaps(period_id, status);
CREATE INDEX IF NOT EXISTS idx_instruments_period ON instruments(period_id);
CREATE INDEX IF NOT EXISTS idx_calculations_act  ON calculations(activity_id);
CREATE INDEX IF NOT EXISTS idx_source_docs_ref   ON source_docs(doc_ref);

-- ---------------------------------------------------------------------------
-- Guards (HONESTY RULES enforced by the database itself)
-- ---------------------------------------------------------------------------

-- Rule 3: nothing is ever deleted.
CREATE TRIGGER IF NOT EXISTS no_delete_sites BEFORE DELETE ON sites
BEGIN SELECT RAISE(ABORT, 'carbonroom: rows are never deleted (supersede instead)'); END;
CREATE TRIGGER IF NOT EXISTS no_delete_periods BEFORE DELETE ON periods
BEGIN SELECT RAISE(ABORT, 'carbonroom: rows are never deleted (supersede instead)'); END;
CREATE TRIGGER IF NOT EXISTS no_delete_source_docs BEFORE DELETE ON source_docs
BEGIN SELECT RAISE(ABORT, 'carbonroom: rows are never deleted (supersede instead)'); END;
CREATE TRIGGER IF NOT EXISTS no_delete_activities BEFORE DELETE ON activities
BEGIN SELECT RAISE(ABORT, 'carbonroom: rows are never deleted (supersede instead)'); END;
CREATE TRIGGER IF NOT EXISTS no_delete_emission_factors BEFORE DELETE ON emission_factors
BEGIN SELECT RAISE(ABORT, 'carbonroom: rows are never deleted (supersede instead)'); END;
CREATE TRIGGER IF NOT EXISTS no_delete_calculations BEFORE DELETE ON calculations
BEGIN SELECT RAISE(ABORT, 'carbonroom: rows are never deleted (supersede instead)'); END;
CREATE TRIGGER IF NOT EXISTS no_delete_instruments BEFORE DELETE ON instruments
BEGIN SELECT RAISE(ABORT, 'carbonroom: rows are never deleted (supersede instead)'); END;
CREATE TRIGGER IF NOT EXISTS no_delete_gaps BEFORE DELETE ON gaps
BEGIN SELECT RAISE(ABORT, 'carbonroom: rows are never deleted (supersede instead)'); END;
CREATE TRIGGER IF NOT EXISTS no_delete_approvals BEFORE DELETE ON approvals
BEGIN SELECT RAISE(ABORT, 'carbonroom: rows are never deleted (supersede instead)'); END;
CREATE TRIGGER IF NOT EXISTS no_delete_events BEFORE DELETE ON events
BEGIN SELECT RAISE(ABORT, 'carbonroom: rows are never deleted (supersede instead)'); END;
CREATE TRIGGER IF NOT EXISTS no_delete_expected_documents BEFORE DELETE ON expected_documents
BEGIN SELECT RAISE(ABORT, 'carbonroom: rows are never deleted (supersede instead)'); END;

-- The audit log and recorded approvals are append-only.
CREATE TRIGGER IF NOT EXISTS events_append_only BEFORE UPDATE ON events
BEGIN SELECT RAISE(ABORT, 'carbonroom: the events log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS approvals_append_only BEFORE UPDATE ON approvals
BEGIN SELECT RAISE(ABORT, 'carbonroom: approvals are append-only'); END;

-- Evidence never changes after it is recorded: a new document means a new row.
CREATE TRIGGER IF NOT EXISTS source_docs_evidence_immutable
BEFORE UPDATE OF id, path, sha256, kind, received_at ON source_docs
WHEN NEW.id IS NOT OLD.id OR NEW.path IS NOT OLD.path OR NEW.sha256 IS NOT OLD.sha256
  OR NEW.kind IS NOT OLD.kind OR NEW.received_at IS NOT OLD.received_at
BEGIN SELECT RAISE(ABORT, 'carbonroom: source document evidence is immutable'); END;

CREATE TRIGGER IF NOT EXISTS source_docs_supersede_once
BEFORE UPDATE OF superseded_by ON source_docs
WHEN OLD.superseded_by IS NOT NULL AND NEW.superseded_by IS NOT OLD.superseded_by
BEGIN SELECT RAISE(ABORT, 'carbonroom: a superseded document cannot be re-pointed'); END;

CREATE TRIGGER IF NOT EXISTS activities_evidence_immutable
BEFORE UPDATE OF id, site_id, period_id, category, quantity, unit, source_doc_id,
                 excerpt, excerpt_locator, excerpt_sha256, created_by ON activities
WHEN NEW.id IS NOT OLD.id OR NEW.site_id IS NOT OLD.site_id OR NEW.period_id IS NOT OLD.period_id
  OR NEW.category IS NOT OLD.category OR NEW.quantity IS NOT OLD.quantity OR NEW.unit IS NOT OLD.unit
  OR NEW.source_doc_id IS NOT OLD.source_doc_id OR NEW.excerpt IS NOT OLD.excerpt
  OR NEW.excerpt_locator IS NOT OLD.excerpt_locator OR NEW.excerpt_sha256 IS NOT OLD.excerpt_sha256
  OR NEW.created_by IS NOT OLD.created_by
BEGIN SELECT RAISE(ABORT, 'carbonroom: activity evidence is immutable (supersede instead)'); END;

CREATE TRIGGER IF NOT EXISTS activities_superseded_is_final
BEFORE UPDATE OF status, superseded_by ON activities
WHEN OLD.status = 'SUPERSEDED' AND (NEW.status IS NOT OLD.status OR NEW.superseded_by IS NOT OLD.superseded_by)
BEGIN SELECT RAISE(ABORT, 'carbonroom: a SUPERSEDED activity is final'); END;

CREATE TRIGGER IF NOT EXISTS activities_superseded_needs_pointer
BEFORE UPDATE OF status ON activities
WHEN NEW.status = 'SUPERSEDED' AND NEW.superseded_by IS NULL
BEGIN SELECT RAISE(ABORT, 'carbonroom: SUPERSEDED requires superseded_by'); END;

CREATE TRIGGER IF NOT EXISTS instruments_evidence_immutable
BEFORE UPDATE OF id, period_id, kind, mwh, region, vintage, source_doc_id,
                 excerpt, excerpt_locator, excerpt_sha256 ON instruments
WHEN NEW.id IS NOT OLD.id OR NEW.period_id IS NOT OLD.period_id OR NEW.kind IS NOT OLD.kind
  OR NEW.mwh IS NOT OLD.mwh OR NEW.region IS NOT OLD.region OR NEW.vintage IS NOT OLD.vintage
  OR NEW.source_doc_id IS NOT OLD.source_doc_id OR NEW.excerpt IS NOT OLD.excerpt
  OR NEW.excerpt_locator IS NOT OLD.excerpt_locator OR NEW.excerpt_sha256 IS NOT OLD.excerpt_sha256
BEGIN SELECT RAISE(ABORT, 'carbonroom: instrument evidence is immutable (supersede instead)'); END;

-- A recorded calculation is never rewritten; recompute by inserting a new row.
CREATE TRIGGER IF NOT EXISTS calculations_append_only BEFORE UPDATE ON calculations
BEGIN SELECT RAISE(ABORT, 'carbonroom: calculations are append-only (insert a new row)'); END;

-- Rule 2: a gap is never closed without a named human and a written resolution.
CREATE TRIGGER IF NOT EXISTS gaps_resolution_needs_human
BEFORE UPDATE OF status ON gaps
WHEN NEW.status IN ('RESOLVED','ACCEPTED_RISK')
  AND (NEW.resolved_by IS NULL OR trim(NEW.resolved_by) = '' OR NEW.resolution IS NULL OR trim(NEW.resolution) = '')
BEGIN SELECT RAISE(ABORT, 'carbonroom: closing a gap needs resolved_by and a resolution'); END;

-- Only a recorded human APPROVE can close a period.
CREATE TRIGGER IF NOT EXISTS periods_close_needs_approval
BEFORE UPDATE OF status ON periods
WHEN NEW.status = 'CLOSED' AND NOT EXISTS (
  SELECT 1 FROM approvals a
  WHERE a.period_id = NEW.id AND a.decision = 'APPROVE' AND a.approver_handle = NEW.approved_by)
BEGIN SELECT RAISE(ABORT, 'carbonroom: a period closes only after a recorded human APPROVE'); END;

INSERT OR IGNORE INTO schema_meta(key, value) VALUES ('schema_version', '1');
