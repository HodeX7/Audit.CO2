PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS closes (
    close_id TEXT PRIMARY KEY,
    month TEXT NOT NULL,
    sites TEXT NOT NULL,
    factor_set TEXT NOT NULL,
    phase TEXT NOT NULL,
    version INTEGER NOT NULL,
    created_by TEXT NOT NULL,
    created_message_id TEXT NOT NULL,
    published_by TEXT,
    published_message_id TEXT,
    published_at TEXT,
    UNIQUE(month, version)
);

CREATE TABLE IF NOT EXISTS sources (
    source_doc_id TEXT PRIMARY KEY,
    close_id TEXT NOT NULL REFERENCES closes(close_id),
    site TEXT,
    kind TEXT NOT NULL,
    file_name TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    page_count INTEGER NOT NULL,
    raw_text TEXT NOT NULL,
    period_start TEXT,
    period_end TEXT,
    extract_status TEXT NOT NULL,
    extract_error TEXT,
    ingested_by TEXT NOT NULL,
    ingested_at TEXT NOT NULL,
    UNIQUE(close_id, sha256)
);

CREATE TABLE IF NOT EXISTS claims (
    claim_id TEXT PRIMARY KEY,
    close_id TEXT NOT NULL REFERENCES closes(close_id),
    site TEXT NOT NULL,
    month TEXT NOT NULL,
    activity TEXT NOT NULL,
    value TEXT NOT NULL,
    unit TEXT NOT NULL,
    scope TEXT NOT NULL,
    source_doc_id TEXT NOT NULL REFERENCES sources(source_doc_id),
    source_excerpt TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    source_page INTEGER NOT NULL,
    factor_id TEXT,
    factor_version TEXT,
    status TEXT NOT NULL,
    extracted_by TEXT NOT NULL,
    checked_by TEXT,
    superseded_by TEXT REFERENCES claims(claim_id),
    attributes TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS factors (
    factor_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    version TEXT NOT NULL,
    year TEXT NOT NULL,
    activity TEXT NOT NULL,
    geography TEXT NOT NULL,
    value TEXT NOT NULL,
    unit TEXT NOT NULL,
    citation TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS calculations (
    calc_id TEXT PRIMARY KEY,
    claim_id TEXT NOT NULL REFERENCES claims(claim_id),
    factor_id TEXT NOT NULL REFERENCES factors(factor_id),
    factor_version TEXT NOT NULL,
    activity_value TEXT NOT NULL,
    activity_unit TEXT NOT NULL,
    factor_value TEXT NOT NULL,
    factor_unit TEXT NOT NULL,
    kgco2e TEXT NOT NULL,
    formula TEXT NOT NULL,
    basis TEXT,
    created_at TEXT NOT NULL,
    superseded_by TEXT REFERENCES calculations(calc_id)
);

CREATE TABLE IF NOT EXISTS gaps (
    gap_id TEXT PRIMARY KEY,
    close_id TEXT NOT NULL REFERENCES closes(close_id),
    finding_id TEXT NOT NULL,
    rule TEXT NOT NULL,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    owner TEXT NOT NULL,
    status TEXT NOT NULL,
    claim_ids TEXT NOT NULL,
    options TEXT NOT NULL,
    thread_root_message_id TEXT,
    opened_at TEXT NOT NULL,
    resolved_by TEXT,
    resolved_message_id TEXT,
    resolution TEXT,
    UNIQUE(close_id, finding_id)
);

CREATE TABLE IF NOT EXISTS approvals (
    approval_id TEXT PRIMARY KEY,
    close_id TEXT NOT NULL REFERENCES closes(close_id),
    subject_type TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    tier INTEGER NOT NULL,
    actor_id TEXT NOT NULL,
    role TEXT,
    decision TEXT NOT NULL,
    reason TEXT NOT NULL,
    chat_message_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    close_id TEXT NOT NULL REFERENCES closes(close_id),
    actor TEXT NOT NULL,
    kind TEXT NOT NULL,
    claim_id TEXT,
    before_status TEXT,
    after_status TEXT,
    chat_message_id TEXT,
    timestamp TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    payload TEXT NOT NULL DEFAULT '{}',
    prev_hash TEXT NOT NULL,
    hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS locks (
    close_id TEXT NOT NULL REFERENCES closes(close_id),
    site TEXT NOT NULL,
    month TEXT NOT NULL,
    source_doc_id TEXT NOT NULL,
    holder TEXT NOT NULL,
    acquired_at TEXT NOT NULL,
    PRIMARY KEY(close_id, site, month, source_doc_id)
);

CREATE TABLE IF NOT EXISTS budgets (
    close_id TEXT NOT NULL REFERENCES closes(close_id),
    agent TEXT NOT NULL,
    tokens_used INTEGER NOT NULL,
    limit_tokens INTEGER NOT NULL,
    PRIMARY KEY(close_id, agent)
);

CREATE TABLE IF NOT EXISTS s_tags (
    close_id TEXT NOT NULL REFERENCES closes(close_id),
    version INTEGER NOT NULL,
    tag TEXT NOT NULL,
    calc_id TEXT NOT NULL REFERENCES calculations(calc_id),
    claim_id TEXT NOT NULL REFERENCES claims(claim_id),
    PRIMARY KEY(close_id, version, tag)
);

CREATE VIEW IF NOT EXISTS edges AS
SELECT site AS src, 'CONSUMED' AS rel, claim_id AS dst FROM claims
UNION ALL SELECT claim_id, 'FROM', source_doc_id FROM claims
UNION ALL SELECT claim_id, 'USES', factor_id FROM claims WHERE factor_id IS NOT NULL
UNION ALL SELECT calc_id, 'OF', claim_id FROM calculations
UNION ALL SELECT gap_id, 'ABOUT', value FROM gaps, json_each(gaps.claim_ids)
UNION ALL SELECT approval_id, 'APPROVES', subject_id FROM approvals;
