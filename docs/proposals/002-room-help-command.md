# 002 · Room help command and fallback mention

## Problem
Contracts §8 has no way for a person to ask the room what it understands. A bare `@carbon-room`, or a known
command with bad arguments (`@carbon-room close Smarch`), currently has no defined intent.

## Change
Add these rows to the table in `00-CONTRACTS.md` §8:

| Who | Text | Intent | Calls |
|---|---|---|---|
| any human | `@<agent> help`, or a bare `@<agent>` | help | none |
| any human | a known command with bad arguments | help (with a reason) | none |

Add this sentence under the table: "`G-2 pick A` may follow an agent mention, as in `@watchdog G-2 pick A`.
Commands are bound to their agent: `@reporter publish` is a question (`ask`), not a publish."

## Who is affected
P3-3.1 (grammar), P3-6.4 (README command list). P1 and P2 are not affected; no core call changes.

## Decision
Approved by P3, the owner of §8.
