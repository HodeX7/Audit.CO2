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
_Not written yet._

## S08 ops
_Not written yet._

## S09 register
_Not written yet._
