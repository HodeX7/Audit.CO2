# P3 Switch runtime and room gate

## Why

The close is a collaborative business workflow. Human evidence uploads, gap decisions and publication must be
traceable to a Switch message and a named role. A local CLI can inspect and prepare data, but cannot perform
those human decisions.

## Architecture

```text
four Switch WebSockets → one deduplicating Dispatcher → intent/identity gate → room handler
                                                                     ↓
                                                       AsyncCore → SQLite ledger
                                                                     ↓
                                           NoiseGuard → SwitchRoom → per-agent ops
```

`carbon_room.room.run` owns the process lifecycle. It builds one `AgentConnection` and one `OpsClient` per agent,
sharing a connection id for each pair. The Watchdog receives all room events; other agents receive addressed
events. `app.classify` accepts only an intended addressed command, or a gap reply from a known person or an
addressed sender. Dispatcher deduplicates by Switch message id and serializes mutations. Handler identity comes
from `config/people.yaml`; an unknown sender is a guest. The synchronous core runs off the event loop so socket
pings remain responsive during document parsing and report rendering.

Before opening sockets, the real runner initializes SQLite and loads the immutable factor rows from the active
`config/factors.csv`. The developer CLI's `init` command uses the same bootstrap, so a fresh ledger can calculate
without a separate manual factor-load step. A missing or changed catalogue fails startup rather than accepting
an incomplete close.

`SwitchRoom` selects the posting agent, routes targeted hand-offs and board documents, and applies the configured
thread fallback. `NoiseGuard` limits top-level chatter without suppressing essential posts. The ledger remains
authoritative; room messages and the Close Board are views of it. Starting the runtime resumes an unpublished
close rather than recreating gap roots.

## Decisions

- A four-agent runtime is the default; one prefixed agent is the explicit fallback if live four-socket operation
  fails. Do not silently switch modes.
- `make run` connects to a real room and can post a resume message. Tests inject a fake WebSocket server and
  in-memory operations transport; they never use live credentials.
- The source-tree `uuid_utils` test stub was removed. The real dependency is installed through LangGraph's
  dependency graph; shadowing it would cause source runs to generate UUID4 in place of UUID7.
- A PUBLISHED close is immutable. Before publication, newly blocking evidence or human rejection can demote a
  claim from VERIFIED with an audit event; otherwise the verified-only total could be false.

## Code map and verification

| Concern | Code | Tests |
| --- | --- | --- |
| Acceptance and error boundary | `carbon_room/room/app.py` | `tests/room/test_app.py` |
| Ops-backed room | `carbon_room/room/switch_room.py` | `tests/room/test_switch_room.py` |
| Startup, factor bootstrap, sockets and shutdown | `carbon_room/room/run.py`, `carbon_room/calc/factors.py` | `tests/room/test_room_loop.py`, `tests/room/test_run_guard.py`, `tests/test_bootstrap.py` |
| Real P1/P2 close and publication | `carbon_room/agents/`, `carbon_room/core.py` | `tests/room/test_real_core_flow.py`, `tests/room/test_runtime_real_core.py` |
| No local human bypass | `carbon_room/__main__.py`, `carbon_room/core.py` | `tests/test_publish_needs_room.py` |

Offline tests verify the fake-Switch loop, the real SQLite seed flow and the role/message gate. They do not prove
live Switch addressing, attachment download, room documents, person ids, or clean-machine setup. Those remain
manual release gates in `docs/P3-CHECKLIST.md`.
