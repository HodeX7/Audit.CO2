# Sourced synthetic reference fixtures

Owner: Ujjwal (P1). Code and data: `tests/fixtures/emissions_reference/`.

## Why

P1 needs realistic evidence inputs without silently turning test data into a production factor catalog. The fixture
corpus exercises CSV, email, and deterministic cloud-JSON ingestion with public-source provenance that reviewers can
trace and tests can run without network access.

## Design

`pinned_reference_cases.json` holds three fictional UK activities with expected *test-only* arithmetic plus one
provider-allocation cloud envelope, each with a pinned publisher, edition, row description, metric, boundary, and
official URL. The companion files are fictional evidence documents. Tests verify the metadata, read every document
through P1 readers, ingest each file into an isolated
SQLite ledger, preserve its printed period even when JSON key order changes, and confirm that the claims remain
`UNVERIFIED`.

```text
official, versioned publication
              │ URL + edition + boundary (test metadata)
              ▼
fictional source document → P1 reader/collector → UNVERIFIED SQLite claim
```

## Decisions

The corpus never downloads live data, never writes a production factor table, and never treats its expected result as
a customer-facing calculation. The DESNZ rows are deliberately separate Scope 2 generated-electricity and Scope 3
transmission-and-distribution activities. The cloud envelope tests provider-allocation metadata only; it does not
calculate cloud emissions from a national grid factor.

The public sources are [DESNZ 2026 conversion factors](https://www.gov.uk/government/publications/greenhouse-gas-reporting-conversion-factors-2026),
[the revised DESNZ flat file](https://assets.publishing.service.gov.uk/media/6a6c9748862aaf18d9c62ac9/ghg-conversion-factors-2026-flat-format-revised.xlsx),
and [AWS's allocation methodology](https://docs.aws.amazon.com/sustainability/latest/userguide/methodology-allocation.html).

## Code map and tests

| Path | Responsibility |
| --- | --- |
| `tests/fixtures/emissions_reference/pinned_reference_cases.json` | Reviewable source edition, boundary, and expected test-only value |
| `tests/fixtures/emissions_reference/*` | Fictional CSV, email, and cloud-JSON input documents |
| `tests/test_reference_fixture_data.py` | Metadata, reader, and P1 ledger-ingestion regression coverage |

Run `uv run pytest tests/test_reference_fixture_data.py` to exercise this corpus.
