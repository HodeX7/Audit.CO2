# Switch protocol notes

What the P3 room client actually uses, confirmed against a running server. Each section is owned by one spec and
edited only by it. Plan §1.5 has the documented facts; spikes are in docs/spikes.md.

## S06 events
- Domain envelope: `{"event": ..., "data": {"type", "room_id", "bridge_id", "channel_type", "payload",
  "sequence"}, "id": <sequence>}`. `decode` reads `room_id`, `payload` and the sequence (`id`, else
  `data.sequence`) and returns None if any is missing or the wrong type.
- `message` payload fields read: `addressed` (true only when exactly `true`), `sender`, `sender_name`,
  `message_id` (required), `body` (None becomes `""`, other non-str is malformed), `timestamp` (ms),
  `thread_id` (`""` becomes None) and `attachments[]` (`filename`, `mimetype`, `size`, `mxc`, `msgtype`;
  non-dict entries are skipped).
- `room_join` payload fields read: `member`, `member_name`, `timestamp`. The event gets
  `message_id = "join:<sequence>"`, an empty body and `addressed = False`.
- A domain kind in `data.type` wins over `event`: a `command` frame may arrive with `event: "message"`.
- `decode` drops: `command` frames (Switch handles bang commands), every control frame, messages from our own
  agents (sender id in `own_sender_ids`, or sender name equal to an agent name) and malformed frames. It never
  raises.
- The fixtures in `tests/room/fixtures/frames/` are documented shapes (`_source: docs`) until M2 captures real
  frames as `captured_*.json`.

## S07 connection
- URL: `ws(s)://<server><prefix>/agents/<agent_id>/connection/ws?connection_id=<uuid>&rooms=<ids, comma>&filter=<all|addressed>&client=carbon-room-python&client_version=<v>`, plus `start_from=<cursor>` and `expected_generation=<g>` once known.
- Auth: `Authorization: Bearer <agent api key>` on the handshake. The key is never logged.
- First frame: must be `connection_state`; its `generation` is stored. Anything else is a warning plus a reconnect.
- Ping: answered inside the read loop with `{"type":"pong","cursor":<cursor or 0>}` before anything else.
- Cursor: highest domain sequence seen; duplicates (`seq <= cursor`) are skipped.
  - Deviation 1: the `connection_state` cursor is adopted only when the client has none. `max(cursor, state)` would
    skip every replayed event if the state cursor is the server head.
  - Deviation 2: a `gap` frame sets `cursor = resumed_at - 1`. The docs don't say whether `resumed_at` is the next
    event or the last one skipped; one lower never loses an event, and dispatcher dedupe drops repeats.
- Close codes: 4401 or HTTP 401/403 raises `AuthError`, no retry. 4400, 4403, 4409 log ERROR and stop.
  Anything else (1000, 1001, 1011, 1012, no close frame, network errors) reconnects with the same
  `connection_id`, `start_from` and `expected_generation`.
- Eviction: `taken_over` and `closed` stop for good; `heartbeat_lapsed` and every other code reconnect.
- Backoff: 1, 2, 4, 8, 16, then 30 s forever; reset on every `connection_state`. `stop()` interrupts the wait.
- M2 must confirm: the `gap` `resumed_at` meaning, the control frame envelope (`{"type"}` vs `{"event","data"}`;
  both parsed), and whether a bad key is HTTP 401 at the handshake or close code 4401 (both handled).

## S08 ops
_Not written yet._

## S09 register
_Not written yet._
