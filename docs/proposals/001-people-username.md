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
