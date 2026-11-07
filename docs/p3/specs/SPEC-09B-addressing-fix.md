# SPEC-09B · Registration: set addressing with another agent's key
Stories: P3-1.2 (fix) · Branch: `p3-s09b-addressing` · PR title: "P3-S09B (1.2): set addressing with another agent's key"
Depends on (must be merged): SPEC-09 (merged in #19) · Wave: any · Estimated session time: 0.5 h

## 1. Goal
`docs/switch-ops.json` says `update_agent_detail` is owner-only, and "never yourself: your own settings are your
owner's to change, in Switch Console". Merged SPEC-09 calls it with each agent's own key, on its own path, so
Switch refuses all four calls and register prints the Console hint for every agent. Fix it so that one of our
agents changes another's addressing to `anyone`. The four agents share an owner.

## 2. Read before starting
- `carbon_room/room/register.py` (`_set_addressing`) and `tests/room/test_register.py`
- `docs/switch-ops.json`: the `update_agent_detail` entry
- `docs/p3/specs/SPEC-09-register.md` rule 8

## 3. Files
- Modify `carbon_room/room/register.py`: `_set_addressing` only
- Modify `tests/room/test_register.py`: in the red commit, replace `test_addressing_calls_use_agent_keys` with the
  two tests below. Leave every other test unchanged.
- Modify `docs/switch-protocol-notes.md`: in `## S09 register`, replace the Addressing bullet only

## 4. Public interface
No public change.

## 5. Behaviour
1. **Caller.** For each target agent `T` (in `AGENT_NAMES` order) that has an id and key, the caller is
   `carbon-room`. When `T` is carbon-room itself, the caller is `collector`. If that caller has no id or key, use
   the first other agent in `AGENT_NAMES` order that has them. If there is none, print
   `<T>: couldn't set addressing (no other agent to ask); set "Anyone" in Switch Console → agent settings.`
2. **Request.** `POST {server}/agents/{caller id}/ops/update_agent_detail` with `Authorization: Bearer <caller
   key>`, no `X-Switch-Connection-Id`, and `json={"agent_id": <T id>, "addressing": "anyone"}`.
3. **Unchanged.** The response handling and the printed lines for 2xx, 400/403, other statuses and network
   errors stay as they are (SPEC-09 rule 8). This still never changes the exit code.

## 6. Test plan
These use SPEC-09's `make_env`, `Recorder` and `run` helpers, which already exist in the test module.

| Test | Act | Assert |
|---|---|---|
| `test_addressing_uses_another_agents_key` | `run(path, rec)` | 4 `update_agent_detail` POSTs, in `AGENT_NAMES` order of target. The carbon-room target: path `/agents/agent-collector/ops/update_agent_detail`, auth `Bearer key-collector-secret`, body `{"agent_id": "agent-carbon-room", "addressing": "anyone"}`. The collector, watchdog and reporter targets: path `/agents/agent-carbon-room/ops/update_agent_detail`, auth `Bearer key-carbon-room-secret`, body `{"agent_id": "agent-<name>", "addressing": "anyone"}`. No connection-id header on any [1, 2] |
| `test_addressing_falls_back_when_carbon_room_missing` | a `.env` where carbon-room has no key and the registration POST for carbon-room returns 409 | `run(path, rec)` | collector, watchdog and reporter are each set by `agent-collector`'s key, except collector, which is set by `agent-watchdog`'s key; no request targets carbon-room; stdout has no addressing line for carbon-room [1] |

Every other test in `tests/room/test_register.py` must still pass unchanged.

## 7. Fixtures and doubles
SPEC-09's existing test helpers.

## 8. Manual check
`make register` (with a complete `.env`) prints `<name>: addressing set to anyone` for all four agents. In Switch
Console each agent's addressing shows "Anyone". Lead and Priya can then mention any agent.

## 9. Done when
- [ ] Every test in `tests/room/test_register.py` passes, and the full `pytest -q` passes
- [ ] ruff passes on `carbon_room/room tests/room`
- [ ] Manual check: the four agents show "Anyone" in Switch Console

## 10. Not in this spec
Inviting agents (SPEC-09 rule 9 works against the real schema: `room_id` and `agent_name`).

## 11. Open questions
If Switch still refuses an agent-to-agent change (403), the fallback stays: set "Anyone" by hand in Switch
Console. That takes four clicks.
