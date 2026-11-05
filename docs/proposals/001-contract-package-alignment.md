# Contract package alignment

## Problem

The existing implementation uses the `carbonroom` package and a ledger schema that predates the supplied shared
contract. P2 and P3 have begun against that implementation, while the binding contract requires `carbon_room`.

## Change

Add the contract-compatible `carbon_room` package alongside the existing package. It provides the exact shared
types and subsequently the frozen ledger and core APIs. Keep `carbonroom` available during migration; do not
silently rename or break teammate imports.

## Who is affected

P1-1.1 through P1-9.2; P2 imports of the ledger and core facade; P3 room-router calls.

## Decision

