"""Developer CLI with no bypass for human resolution, approval, or publishing."""

from __future__ import annotations

import argparse
from dataclasses import asdict

from carbon_room import core
from carbon_room.ledger import connect, init_db, ledger
from carbon_room.models import Actor


def main() -> int:
    """Run safe inspection and system-actor development commands."""
    parser = argparse.ArgumentParser(prog="carbon-room")
    command = parser.add_subparsers(dest="command", required=True)
    command.add_parser("init")
    close = command.add_parser("close")
    close.add_argument("month")
    close.add_argument("--site", action="append", required=True)
    close.add_argument("--factor-set", required=True)
    ingest = command.add_parser("ingest")
    ingest.add_argument("close_id")
    for name in ("calculate", "check", "summary"):
        item = command.add_parser(name)
        item.add_argument("close_id")
    audit = command.add_parser("verify-audit")
    audit.add_argument("close_id")
    gaps = command.add_parser("gaps")
    gaps.add_argument("close_id")
    trace = command.add_parser("trace")
    trace.add_argument("close_id")
    trace.add_argument("tag")
    args = parser.parse_args()
    actor = Actor("system", "cli", "CLI")
    if args.command == "init":
        with connect() as db:
            init_db(db)
        print("initialized")
    elif args.command == "close":
        print(core.start_close(args.month, args.site, args.factor_set, actor, "cli-init"))
    elif args.command == "ingest":
        print(core.ingest(args.close_id, actor).statement)
    elif args.command == "verify-audit":
        print(asdict(core.verify_audit(args.close_id)))
    elif args.command == "gaps":
        with connect() as db:
            print([asdict(item) for item in ledger.get_gaps(db, args.close_id)])
    elif args.command in {"calculate", "check", "summary"}:
        print(getattr(core, args.command)(args.close_id))
    elif args.command == "trace":
        print(core.trace(args.close_id, args.tag))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
