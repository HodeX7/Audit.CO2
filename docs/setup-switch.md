# Local Switch setup

This is a manual setup guide. The fake-Switch tests do **not** verify the installed Console or a live Mattermost
room. Never paste registration or agent keys into logs, screenshots, issues or commits.

1. Install Python 3.11+ and Docker Desktop, start Docker, then install Switch Console. In Console choose
   **Run a server on this computer**. Note the Console version, server address and first-start download time.
   <!-- TODO(M1): record Console version, first-start download time and exact tested platform. -->
2. Verify that `<server>/health` reports healthy. Use the server address shown by Console, not the Gateway
   browser address. Copy `.env.example` to `.env` and put this address in `SWITCH_SERVER`. `.env` is ignored by Git.
3. In Switch Gateway create a registration API key and set `SWITCH_REGISTRATION_KEY` privately in `.env`. If a
   local Gateway cannot issue one, register through Console and use the documented `register --from-console`
   path. Keep the key out of the repo.
4. Create a Switch-managed room named `emissions-reporting` and put its room id in `SWITCH_ROOM_ID`. A Mattermost
   channel made outside Switch may not be bridged. Set addressing so people can reach all four agents.
5. Run `make setup` (first dependency download may take several minutes), then `make seed`. Run `make register`
   once to create and invite the four agents; it writes their ids and private keys to `.env`. Do not rerun it
   casually against an existing room. Use `make doctor` to check Docker, health, keys, room, people and config.
   Its database check initializes SQLite and loads `config/factors.csv`; fix any catalogue error before `make run`.
6. Have the Lead and Priya each post a harmless message in the room. Copy their distinct Switch **sender ids**
   and Mattermost usernames into `config/people.yaml`. `make doctor` should then report no people placeholders.
   Without this mapping their messages are guests and cannot resolve or publish.
   <!-- TODO(M2): record the two distinct sender-id formats and the S1–S6 spike results in docs/spikes.md. -->
7. Run `make test` and `make lint`, then `make run`. This last command connects to the real room and can post a
   resume message. The default attachment mode is `inbox`; put the demo upload in `data/inbox/` before replying
   in its gap thread. Stop the runtime with Ctrl-C.
8. For a fresh demonstration only, use `make reset-demo` and read its confirmation prompt carefully. It clears
   local demo state; do not run it on a ledger you need to retain.

If `make doctor` fails, fix each reported item before attempting a live close. On a clean machine, have someone
other than the implementer run this guide and record snags in `docs/clean-machine-run.md`.
