# Carbon Room demo script — rehearsal draft

This script is **not** a record of a timed live rehearsal. Run it in the real Switch room after `make doctor`
passes, the Lead/Priya sender ids are mapped, and a disposable ledger is reset. Figures below are from
[`data/seed/EXPECTED.md`](../data/seed/EXPECTED.md); the final verified figure is 21.941897087834993 tCO2e
(displayed as 21.9 tCO2e), with 4/4 expected sources verified. Do not use fake-core figures in the video.

| Target time | Actor and exact action | What to show and say | Judge question |
| --- | --- | --- | --- |
| 0–10 s | Lead: `@carbon-room close October` | “This is the shared monthly close room. The agents plan, collect, calculate and check against one SQLite ledger.” | Why Switch? Human actions and ownership happen in the room. |
| 10–25 s | Collector posts the source statement | Show evidence retention, then the apparent “all five collected” statement. “Collected is not verified.” | Can an agent invent a total? No; arithmetic and checks are deterministic. |
| 25–55 s | Watchdog opens four roots | Show Warehouse-2 period, diesel conflict, stale factor and HQ variance threads, each with an owner. Show the partial verified/excluded summary. | What if evidence is wrong? Its calculation is excluded until resolved. |
| 55–75 s | Priya: `upload warehouse2_electricity_2026-10_actual.pdf`; Lead: `pick A`; Lead: `approve` in stale-factor thread; Lead: `approve` in variance thread | Pre-copy the upload into `data/inbox/` if inbox mode is used. Show the total moving after thread replies and the updated Close Board. | Who authorised it? Each action carries a human role and Switch message id in the audit ledger. |
| 75–85 s | Lead: `@reporter draft`, then `@carbon-room publish` | Show 21.9 tCO2e and 4/4 verified sources. Open `out/2026-10/v1/coverage.html`. | What if a gap stays open? Publication can proceed, but it is disclosed and excluded. |
| 85–90 s | Anyone: `@reporter trace S-001` | Show the source evidence, factor version and recomputation. | Can an auditor reproduce it? The source tag and audit chain point back to evidence. |

After the main sequence, demonstrate `@reporter verify audit`, `@carbon-room status`, and
`@carbon-room resume` if the judge asks. `G-1 pick A` is the top-level fallback for the current seed when threaded replies are
unavailable; use the actual gap id displayed by Watchdog.

## Rehearsal notes

- Run 1: not yet performed against live Switch.
- Run 2: not yet performed against live Switch.
- Check that all four traps fire, the participant ids are distinct, and the output files are from the same run
  as the recording.
