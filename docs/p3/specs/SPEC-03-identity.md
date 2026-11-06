# SPEC-03 · Identity and `people.yaml`
Stories: P3-3.2, P3-1.9 (template) · Branch: `p3-s03-identity` · PR title: "P3-S03 (3.2, 1.9): identity and people.yaml"
Depends on (must be merged): SPEC-01 · Wave: 1 · Estimated session time: 0.5 h

## 1. Goal
Map an authenticated Switch sender to an `Actor` with a role from `config/people.yaml`. Give templates a display
name for each person: the Mattermost `@username` when one is known. Ship the repo's `people.yaml` template, and
report placeholders for `make doctor`.

## 2. Read before starting
- `docs/p3/EXECUTION-PLAN.md` §0.3, §2 and §3.7
- `00-CONTRACTS.md` §2 (`Actor`) and §9 (`people.yaml`)
- `carbon_room/config.py` (`load_people`, `clear_caches`)
- `tests/room/conftest.py` (`people_config` fixture) and `tests/room/fixtures/people.yaml`

## 3. Files
- Create `carbon_room/room/identity.py`
- Create `config/people.yaml` (exact content in §7)
- Create `tests/room/test_identity.py`
- Create `docs/proposals/001-people-username.md` (exact content in §7)

## 4. Public interface
```python
def actor_for(sender_id: str, sender_name: str, *,
              agent_ids: Mapping[str, str] | None = None) -> Actor
def person(person_id: str) -> dict | None
def display(person_id: str) -> str
def is_known(sender_id: str) -> bool
def placeholders() -> list[str]
```

## 5. Behaviour
1. **Reading people.**
   - People come from `config.load_people()["people"]`, a list of dicts. They are read on every call, so the
     loader's `lru_cache` makes repeat reads cheap.
   - If `load_people()` raises `FileNotFoundError`, the list is empty, and a single WARNING
     `people.yaml is missing; every sender is a guest` is logged per process.
2. **`actor_for(sender_id, sender_name, *, agent_ids=None)`**, first match wins:
   1. A person whose `switch_ids` list contains `sender_id`, compared exactly:
      `Actor("human", p["id"], p["name"], p["role"])`.
   2. `agent_ids` is given and `sender_id in agent_ids`, where `agent_ids` maps a Switch id to an agent name:
      `Actor("agent", name, AGENT_TITLES[name], None)`.
   3. Anyone else is a guest: `Actor("human", f"guest:{sender_id}", sender_name or sender_id, None)`.
3. **`person(person_id)`** returns the person dict whose `id` equals `person_id`, else None.
4. **`display(person_id)`:**
   1. The person has a non-empty `username` (after `str(...).strip()`): `"@" + username`, with any leading `@`
      in the stored value removed first.
   2. Else the person has a non-empty `name`: the name.
   3. Else, including unknown ids: `person_id` itself.
5. **`is_known(sender_id)`** is True when any person's `switch_ids` contains `sender_id`.
6. **`placeholders()`** returns problem strings, in file order. For each person, the checks run in this order:
   - each `switch_ids` entry containing `<`: `f"{pid}: switch_ids contains a placeholder: {value}"`
   - a `username` containing `<`: `f"{pid}: username contains a placeholder: {value}"`
   - `pid` in `("lead", "priya")` with an empty `switch_ids`: `f"{pid}: switch_ids is empty"`

   If the file is missing, the result is `["people.yaml is missing"]`.
7. **Role checks.** No permission is decided here; P2's `resolve` and `publish` enforce roles. The room only
   passes the actor along.

## 6. Test plan
All tests except the repo-file test use the `people_config` fixture.

| Test | Arrange | Act | Assert |
|---|---|---|---|
| `test_known_person_maps_to_role` | fixture people | `actor_for("@switch-user-priya:test", "priya")` | `== Actor("human", "priya", "Priya", "site_manager")` [2.1] |
| `test_lead_maps_to_lead` | fixture | `actor_for("@switch-user-lead:test", "whatever")` | `== Actor("human", "lead", "Sustainability Lead", "lead")` [2.1] |
| `test_unknown_sender_is_guest` | fixture | `actor_for("@switch-user-zed:test", "zed")`; `actor_for("@x:test", "")` | `Actor("human", "guest:@switch-user-zed:test", "zed", None)`; `Actor("human", "guest:@x:test", "@x:test", None)` [2.3] |
| `test_agent_sender_maps_to_agent` | fixture | `actor_for("agent-wd", "watchdog", agent_ids={"agent-wd": "watchdog"})` | `== Actor("agent", "watchdog", "Watchdog", None)` [2.2] |
| `test_person_wins_over_agent_map` | fixture | `actor_for("@switch-user-lead:test", "lead", agent_ids={"@switch-user-lead:test": "watchdog"})` | `.kind == "human"` and `.id == "lead"` [2] |
| `test_person_lookup` | fixture | `person("priya")`, `person("nobody")` | `["sites"] == ["warehouse-2"]`; None [3] |
| `test_display_prefers_username` | fixture | `display("priya")`, `display("finance")`, `display("guest:x")` | `"@priya"`; `"Finance Approver"` (username is empty); `"guest:x"` [4] |
| `test_display_strips_at_and_falls_back_to_id` | a tmp config dir holding the repo `sites.yaml` and a `people.yaml` of `people: [{id: a, name: "", username: "@ann", switch_ids: []}, {id: b, name: "", username: "", switch_ids: []}]`, with `CARBON_ROOM_CONFIG_DIR` set and caches cleared | `display("a")`, `display("b")` | `"@ann"`, `"b"` [4] |
| `test_is_known` | fixture | `is_known("@switch-user-lead:test")`, `is_known("@nobody:test")`, `is_known("")` | True, False, False [5] |
| `test_placeholders_clean_fixture` | fixture | `placeholders()` | `[]` [6] |
| `test_placeholders_flags_empty_lead_and_priya` | tmp `people.yaml`: lead with `switch_ids: []`, priya with `switch_ids: ["<filled in>"]` and `username: "<priya>"` | `placeholders()` | `["lead: switch_ids is empty", "priya: switch_ids contains a placeholder: <filled in>", "priya: username contains a placeholder: <priya>"]` [6] |
| `test_missing_people_yaml_means_guests` | a tmp config dir with `sites.yaml` only | `actor_for("@switch-user-lead:test", "lead")`, `placeholders()`, `is_known(...)` | a guest actor; `["people.yaml is missing"]`; False [1, 6] |
| `test_repo_people_yaml_parses_and_has_four_people` | `monkeypatch.delenv("CARBON_ROOM_CONFIG_DIR", raising=False)`, then `config.clear_caches()` before and after | `config.load_people()["people"]` | ids `["lead", "priya", "finance", "auditor"]`; roles `["lead", "site_manager", "finance", "auditor"]`; every entry has `username == ""` and `switch_ids == []`; priya's `sites == ["warehouse-2"]`; `placeholders() == ["lead: switch_ids is empty", "priya: switch_ids is empty"]` [§7] |

## 7. Fixtures and doubles
This uses the SPEC-01 fixture `people.yaml` through `people_config`.

**`config/people.yaml` (exact):**
```yaml
# P3-owned (contracts §9, proposal 001). Maps Switch senders to people and roles.
# switch_ids: the sender id the room agent sees for that person (spike S3 records them).
# username:   the Mattermost username, without @, used to mention the person in gap threads.
# A sender who isn't listed is a guest: they can ask questions but can't resolve, approve or publish.
# make doctor fails until lead and priya have switch_ids.
people:
  - { id: lead,    name: "Sustainability Lead", role: lead,         username: "", switch_ids: [] }
  - { id: priya,   name: "Priya",               role: site_manager, username: "", sites: [warehouse-2], switch_ids: [] }
  - { id: finance, name: "Finance Approver",    role: finance,      username: "", switch_ids: [] }
  - { id: auditor, name: "External Auditor",    role: auditor,      username: "", switch_ids: [] }
```

**`docs/proposals/001-people-username.md` (exact):**
```markdown
# 001 · Optional `username` in people.yaml

## Problem
Gap threads must mention their owner so Mattermost notifies them (P3-4.3). A Switch sender id such as
`@switch-user-…:<server>` is not a Mattermost @-mention, and `people.yaml` has no field for the username.

## Change
In `00-CONTRACTS.md` §9, `config/people.yaml`, add an optional `username` key to each person, for example:
`- { id: priya, name: "Priya", role: site_manager, username: priya, sites: [warehouse-2], switch_ids: ["@switch-user-priya:local"] }`.
Add this sentence under the block: "`username` is the Mattermost username without `@`. The room mentions a person as
`@username` when it is set, and by name otherwise."

## Who is affected
P3-3.2, P3-4.3, P3-1.9. P1 and P2 are not affected; `config.load_people()` already returns the whole mapping.

## Decision
Approved by P3, the owner of `people.yaml`.
```

## 8. Manual check
None. M3 fills in the real ids later.

## 9. Done when
- [ ] Known, guest and agent cases are tested
- [ ] Every demo human (lead, priya) has a role in `config/people.yaml`
- [ ] Every test in §6 passes, and the full `pytest -q` passes
- [ ] ruff passes on `carbon_room/room tests/room`
- [ ] No literal site id, `YYYY-MM` month or `CL-`/`G-`/`S-<digits>` id under `carbon_room/`. Note
      `identity.py` must not contain the strings `hq`, `warehouse-2` or `dc-eu-west`.

## 10. Not in this spec
- Permission checks (P2), and real sender ids (M3).
- Editing `00-CONTRACTS.md`; that is a later small PR that applies proposal 001.

## 11. Open questions
None block execution.
