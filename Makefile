PY ?= .venv/bin/python
P3_PATHS := carbon_room/room carbon_room/agents tests/room tests/fakes

.PHONY: help setup seed register doctor run reset-demo test lint refresh-cache

help:
	@echo "→ Carbon Room make targets"
	@echo "  setup          create .venv and install carbon-room with pytest and ruff"
	@echo "  seed           rebuild the synthetic seed documents"
	@echo "  register       register the four Switch agents and write their keys to .env"
	@echo "  doctor         check Docker, Switch, .env, config and the database"
	@echo "  run            start the four room agents"
	@echo "  reset-demo     wipe the ledger, outputs and inbox (asks first)"
	@echo "  test           run the test suite"
	@echo "  lint           ruff on the P3 paths"
	@echo "  refresh-cache  rebuild the replay cache (needs an API key)"

setup:
	@echo "→ Creating .venv if missing and installing carbon-room with pytest and ruff"
	@test -x .venv/bin/python || python3 -m venv .venv
	$(PY) -m pip install -q -e . pytest ruff

seed:
	@echo "→ Rebuilding the synthetic seed documents in data/seed/"
	$(PY) scripts/make_seed.py

register:
	@echo "→ Registering the four Switch agents (keys go to .env, never to the screen)"
	$(PY) -m carbon_room.room.register

doctor:
	@echo "→ Checking Docker, Switch, .env, config and the database"
	$(PY) -m carbon_room.room.doctor

run:
	@echo "→ Starting carbon-room, collector, watchdog and reporter (Ctrl-C to stop)"
	$(PY) -m carbon_room.room.run

reset-demo:
	@echo "→ Resetting the demo (asks before deleting anything)"
	PY=$(PY) scripts/reset_demo.sh

test:
	@echo "→ Running the test suite"
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 $(PY) -m pytest -q

lint:
	@echo "→ Running ruff on the P3 paths"
	$(PY) -m ruff check $(P3_PATHS)

refresh-cache:
	@echo "→ refresh-cache needs P1's live-extraction command, which isn't provided yet"
	@exit 1
