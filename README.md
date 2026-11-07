# Carbon Room

## What it is

Carbon Room is a Switch room where a sustainability team closes a month of emissions. Collector agents retain
bills in an auditable SQLite ledger; a deterministic Watchdog opens a thread for each actionable gap with a
named owner. People resolve those gaps in Switch. Only VERIFIED calculations count in the verified total, and
only an authorised person can publish a report.

## How Switch is used

One Python process connects four Switch agents over the direct WebSocket and operations protocol:
`carbon-room` (orchestrator), `collector`, `watchdog`, and `reporter`. The `emissions-reporting` room is the
work surface. Watchdog receives all room events; the other agents receive addressed events. The orchestrator
sends targeted hand-offs; Watchdog posts gap roots and processes replies in their threads. If threads are
unavailable, a person can reply at the top level with the gap id, for example `G-1 pick A` in the current seed.

Switch is a hard boundary, not an optional notification channel: every human upload, resolution, approval and
publish action carries a Switch `chat_message_id`. The developer CLI intentionally has no publish, resolve or
approve command. [The room-gate tests](tests/test_publish_needs_room.py) enforce this. An offline test double
can verify the workflow, but it does not prove that a live Switch room is configured.

## Quick start

Requires Python 3.11+, Docker Desktop for the local Switch server, and Switch Console. The first dependency and
Console downloads depend on your connection; allow several minutes. See the numbered
[Switch setup guide](docs/setup-switch.md) for server, room, registration and person ids.

```bash
git clone https://github.com/HodeX7/Audit.CO2.git
cd Audit.CO2
make setup
make seed
```

Create a private `.env` from `.env.example`, start the server in Switch Console, create the room, and set its
id and a registration key. Never commit `.env`. Then run:

```bash
make register
make doctor
make test
make lint
make run
```

`make register` is for first registration; do not rerun it casually against agents already in use. `make
doctor` must pass before `make run`. `make run` connects to the configured room and may post a resume message;
it is not an offline smoke test. Ctrl-C stops the runtime. Run `uv run pytest` and `uv run ruff check .` for the
full repository checks. The synthetic expected result is checked with
`uv run python -m scripts.generate_expected --check`.

## Running the demo close

Use the October 2026 fictional seed and a clean disposable demo ledger. The numbers are defined only in
[data/seed/EXPECTED.md](data/seed/EXPECTED.md). Human actors must have their actual Switch sender ids in
`config/people.yaml` or their mutation is refused as a guest.

1. **Lead** types `@carbon-room close October` <!-- close.start -->
2. Watch for Collector's statement, four Watchdog gap threads and the honest partial-total response.
3. **Priya** copies `data/demo_uploads/warehouse2_electricity_2026-10_actual.pdf` into `data/inbox/`, then in
   the Warehouse-2 gap thread replies `upload warehouse2_electricity_2026-10_actual.pdf`.
4. **Lead** replies `pick A` in the diesel conflict thread.
5. **Lead** replies `approve` in the stale data-centre factor thread.
6. **Lead** replies `approve` in the HQ electricity variance thread.
7. **Anyone** asks `@collector what is Warehouse-2 October electricity?` <!-- ask -->
8. **Lead** types `@reporter draft` <!-- report.draft -->
9. **Lead** types `@carbon-room publish` <!-- close.publish -->
10. **Anyone** types `@reporter trace S-001` <!-- report.trace -->
11. **Anyone** types `@reporter verify audit` <!-- audit.verify -->

`@carbon-room status` <!-- close.status --> and `@carbon-room resume` <!-- close.resume --> report the current
state. When threads are unavailable, use `G-1 pick A` <!-- gap.fallback --> at the top level; copy the gap id
from its Watchdog post. Publication is allowed with open gaps, but their calculations remain excluded and the
report discloses them.

## Traps and the rules that catch them

| Fictional evidence trap | Check | Owner | Resolution |
| --- | --- | --- | --- |
| Warehouse-2's labelled October bill actually covers September | R4 period, with R1 missing consequence | Priya | Upload the real October bill |
| Two HQ diesel invoices disagree | R2 conflict | Lead | `pick A` or `pick B` in the thread |
| Data-centre invoice cites an older Ember factor | R3 stale | Lead | `approve` the locked factor or `reject` |
| HQ electricity is above September | R5 variance | Lead | `approve` or `reject` |
| Cloud invoice has no per-model AI breakdown | R6 informational | Lead | No unsupported AI allocation is invented |

## What is synthetic and what is not claimed

Every seed document and its figures are fictional and illustrative. The factors have source citations, but this
demo is not a real company's inventory, assurance opinion, or legal advice. Wispr is not integrated. Scope 3
categories without evidence are listed as **no data**, never zero. Market-based cloud electricity is shown
separately and is not silently added to the location-based total.

## Spike results and fallbacks

The live Switch spikes in [docs/spikes.md](docs/spikes.md) are still marked **not run**. The local fake-Switch
loop tests sockets, message routing and operations, but it is not a substitute for checking a real server.

| Spike | Question | Recorded live result | Current fallback |
| --- | --- | --- | --- |
| S1 | Thread posts | Not run | `CARBON_ROOM_THREADS=0` enables top-level `G-n` replies |
| S2 | Attachment download | Not run | `CARBON_ROOM_ATTACHMENTS=inbox` uses managed `data/inbox/` files |
| S3 | Distinct human sender ids | Not run | No mutation until real ids are mapped in `people.yaml` |
| S4 | Four stable sockets | Not run | `CARBON_ROOM_SINGLE_AGENT=1` uses one prefixed agent |
| S5 | Posted message ids | Not run | Ops client reads recent context if the response omits an id |
| S6 | Room documents | Not run | Posts and ledger remain authoritative if the board is unavailable |

The defaults are threads on (`CARBON_ROOM_THREADS=1`), inbox attachments, and four agents
(`CARBON_ROOM_SINGLE_AGENT=0`). Confirm each against the real server before calling the live demo ready.

## Architecture

The [architecture view](Carbon%20Room%20Architecture.html) provides the system overview.

1. Four Switch sockets feed one deduplicating room dispatcher.
2. Accepted messages reach role-aware handlers with their Switch message ids.
3. Collector stores evidence by SHA-256 and writes claims to the SQLite ledger.
4. Deterministic calculation and Watchdog checks create verifiable totals and gap threads.
5. Human thread actions update the ledger; Reporter publishes a versioned report and source trace.

Config files under `config/` are external to the built wheel; set `CARBON_ROOM_CONFIG_DIR` when installing
outside the repository. Local databases, `data/store/`, caches, uploads, and outputs are ignored by Git.

## Team and track

Ujjwal owns P1 ingestion and ledger; Richa owns P2 calculation, checks and report; Akshar owns P3 Switch room,
orchestration and demo. Flip the Switch, Track 01: Best Business Workflow.
