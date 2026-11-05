# Contract-compatible package

Owner: Ujjwal (P1). Code: `carbon_room/models.py`.

## Why

The shared team contract names `carbon_room` as the boundary package. The existing `carbonroom` implementation
continues to work during migration, while the contract-compatible package gives P2 and P3 stable imports.

## Design

`carbon_room.models` defines the frozen dataclasses, literals, and typed errors from contract section 2. `to_dict`
and `from_dict` make the dataclasses JSON-ready without converting Decimal values through float. The package also
adds the separate contract schema, site-boundary configuration, and exact room-facing facade signatures.

## Decisions

The package is additive during migration. This avoids breaking P2/P3 branches that currently import `carbonroom`.
The package-alignment proposal is `docs/proposals/001-contract-package-alignment.md`.

## Code map

| Path | Responsibility |
| --- | --- |
| `carbon_room/models.py` | Shared dataclasses, literals, errors, and Decimal-safe serializers |
| `carbon_room/ledger/schema.sql`, `carbon_room/ledger/__init__.py` | Contract SQLite schema and connection defaults |
| `carbon_room/config.py`, `config/sites.yaml` | Cached P1 site boundary and expected-source lookup |
| `carbon_room/core.py` | Frozen facade signatures; P2 behavior remains explicitly unimplemented |
| `tests/test_contract_models.py`, `tests/test_schema.py`, `tests/test_config.py`, `tests/test_core_signatures.py` | Compatibility proof tests |

## Tests

Focused compatibility tests prove Decimal round-trips, schema uniqueness and idempotence, environment-overrideable
site configuration, and frozen function parameter names. The legacy suite also runs unchanged.
