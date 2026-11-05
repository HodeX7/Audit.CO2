# Carbon Room

Carbon Room is a month-end emissions-close workflow for sustainability teams. Evidence is collected into an
auditable SQLite ledger; deterministic checks identify problems; the shared Switch room is where people own,
resolve, approve, and publish the close.

Switch is a required business boundary, not a notification channel. Removing it must prevent human-resolution and
publishing workflows from completing.

## Current ownership and readiness

This branch delivers **P1: ingestion and ledger**. It is ready for P2/P3 integration, but it is not a complete
application by itself.

| Owner | Responsibility | Current boundary |
| --- | --- | --- |
| Ujjwal / P1 | Evidence ingestion, SQLite ledger, audit chain, source storage, contract models | Implemented in `carbon_room` |
| Richa / P2 | Calculations, checks, report generation and publish rules | Stable `carbon_room.core` seams; implementation pending |
| Akshar / P3 | Switch event adapter, room threads, orchestration and demo | Stable room-message fields; implementation pending |

## Architecture

```text
Switch message / scheduled collector
            │
            ▼
 Collector → evidence store → SQLite ledger → append-only audit events
                                      │
                         P2 calculations/checks/report
                                      │
                         P3 Switch threads and human actions
```

P1 preserves source bytes by SHA-256, records `Decimal` quantities as exact text, creates only `UNVERIFIED`
claims during ingestion, and records human-originated mutations with a Switch message identifier. The hash chain
is independently verifiable with `carbon-room verify-audit <close-id>`.

## Local development

Requirements: Python 3.11+ and an internet connection for the first dependency installation.

```bash
uv sync --all-groups
uv run pytest
uv run ruff check .
uv run carbon-room --help
```

Copy `.env.example` to `.env` only when live model extraction is needed. Never commit `.env`. Offline and demo
workflows use rule-based parsing and the synthetic files in `data/seed/`; they do not require a model API key.
Live extraction defaults to Anthropic, but deployments can register a vendor-neutral JSON completion provider through
`carbon_room.llm.set_completion_provider`; deterministic validation remains outside the model boundary.

## Demonstrating P1

```bash
uv run carbon-room init
uv run carbon-room close 2026-10 --site hq --site warehouse-2 --site dc-eu-west --factor-set demo
uv run carbon-room ingest 2026-10-v1
uv run carbon-room verify-audit 2026-10-v1
```

The `calculate`, `check`, `summary`, and `trace` CLI commands are reserved P2 integration seams and intentionally
remain unavailable until their owners implement them. Do not present them as a working demo before that merge.

## Configuration and data safety

- `config/sites.yaml` defines P1 site boundaries and expected evidence.
- `CARBON_ROOM_CONFIG_DIR` can point to an alternate configuration directory for tests or deployments.
- `var/`, `data/store/`, extraction caches, databases, and uploads are ignored by Git.
- `scripts/make_seed.py` regenerates only synthetic demo evidence.

See `docs/HANDOFF.md` for the P1 contract and integration checklist.
