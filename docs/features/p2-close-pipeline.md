# P2 close pipeline (Richa)

## Why

An emissions close must separate evidence gathering from calculation and human judgment. P2 turns P1's unverified,
audited claims into exact results, actionable Watchdog threads and a report that never counts unresolved evidence as
verified. P3 owns Switch identity, transport and thread routing; it calls the frozen `carbon_room.core` facade.

## Architecture

```text
P1 claims + versioned factor catalogue
    │
    ▼
calc.run → Decimal calculations (DC: location and vendor market separately)
    │
    ▼
checks.run → R1–R7 findings → one durable gap per actionable finding
    │                  │
    │                  └─ checks.resolve ← authenticated P3 Actor + message id
    │                                       then recalculate and recheck
    ▼
report.summary → current-month verified/excluded totals and coverage (read-only)
    │
    ▼
report.reporter → stable S-tags → trace exact source/factor/recompute
    │
    ▼
report.publish → human lead gate → JSON + Markdown + PDF + 1920×1080 offline HTML
```

Every source value is `Decimal`; only the data-centre location result contributes to the verified total. Its
vendor-reported market result is retained with its own S-tag, shown separately, and marked certificate-based when
zero. The AI workload line is always UNVERIFIED without per-model vendor data. Scope 3 categories with no evidence
are disclosed as “no data, not zero.”

## Decisions and boundaries

- Factor precedence is an already selected allowed factor, then a vendor reference, then the locked factor set. R3
  judges age and locked-set mismatch; a stale approval must select the offered locked factor.
- Watchdog IDs derive from rule, kind, site, month and sorted claim IDs. The R1 missing consequence of a mislabeled
  current-month Warehouse source is merged into the R4 period thread. Non-blocking R6 AI findings do not open a gap.
- A human resolution needs P3-authenticated identity and a Switch message id. P2 does not parse room text or verify
  transport signatures. Gap IDs are close-local, so `resolve` acts only on the latest close and P3 rejects old
  threads. Failed gap uploads cannot commit unmatched source or claim rows. A rejection remains excluded even if
  tier 1 would otherwise pass.
- A published version rejects P1 collection and ledger mutations as well as P2 calculate/check/resolve; later
  evidence needs a new close version. Open gaps may be published, but are disclosed and their claims excluded.
- Reporter Markdown/HTML templates use built-in string formatting, not a model or Jinja dependency. The paginated
  offline PDF uses ReportLab and is generated from the same ledger snapshot before output files are written. The
  publish pack is staged in a temporary sibling directory and renamed into place after all files and ledger updates
  succeed, avoiding partial visible versions from ordinary write failures.
  The report is general information for human review, not a legal or certification conclusion.
- The shared contract's immutable-VERIFIED sentence conflicts with rejecting or newly blocking a once-verified
  claim. P2 rechecks and demotes it for safety; the proposed clarification is in `contracts/CHANGES.md`.

## Code map and verification

| Path | Responsibility |
| --- | --- |
| `carbon_room/calc/` | Factor selection, unit conversion, pure arithmetic and basis-aware recomputation |
| `carbon_room/checks/` | Rule registry, tier-1 gate, gap upsert/clear and human options |
| `carbon_room/report/` | Summary, compliance, S-tags, source trace, rendering and publish gate |
| `config/carbon_room.yaml`, `config/compliance_checks.yaml` | Factor editions, thresholds, roles and review wording |
| `scripts/generate_expected.py`, `data/seed/EXPECTED.md` | Generated fictional end-to-end expected output |
| `tests/p2/`, `tests/test_traps.py`, `tests/test_generalised.py`, `tests/test_calc_recompute.py` | Focused and end-to-end offline checks |

Run `pytest`, repository-wide `ruff check .`, and `python -m scripts.generate_expected --check`.
