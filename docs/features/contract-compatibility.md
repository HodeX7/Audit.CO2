# Contract-compatible package

Owner: Ujjwal (P1). Code: `carbon_room/models.py`.

## Why

The shared team contract names `carbon_room` as the boundary package. The existing `carbonroom` implementation
continues to work during migration, while the contract-compatible package gives P2 and P3 stable types to import.

## Design

`carbon_room.models` defines the frozen dataclasses, literals, and typed errors from contract section 2. `to_dict`
and `from_dict` make the dataclasses JSON-ready without converting Decimal values through float.

## Decisions

The package is additive during migration. This avoids breaking P2/P3 branches that currently import `carbonroom`.
The package-alignment proposal is `docs/proposals/001-contract-package-alignment.md`.

## Code map

| Path | Responsibility |
| --- | --- |
| `carbon_room/models.py` | Shared dataclasses, literals, errors, and Decimal-safe serializers |
| `tests/test_contract_models.py` | Contract-type round-trip coverage |

## Tests

`tests/test_contract_models.py` verifies that a Claim round-trips through JSON-ready data without Decimal loss.
