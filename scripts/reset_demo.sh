#!/usr/bin/env bash
# Reset the demo: wipe var/, out/ and data/inbox/, re-initialise the ledger (asks first). Used by make reset-demo.
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PY:-.venv/bin/python}"
exec "$PY" -m carbon_room.room.reset "$@"
