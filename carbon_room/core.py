"""Frozen room-facing facade; P1 owns signatures and P2 owns calculation behaviour."""

from __future__ import annotations

from carbon_room import config
from carbon_room.ledger import connect
from carbon_room.ledger import budget, ledger
from carbon_room.ledger.audit import verify_audit as verify_chain
from carbon_room.models import Actor

def _unimplemented(owner: str, story: str) -> None:
    raise NotImplementedError(f"owner: {owner}, story {story}")


def start_close(month, sites, factor_set, actor, chat_message_id):
    """P1 implementation: create a close and lock its factor set."""
    if len(month) != 7 or month[4] != "-":
        raise ValueError("month must use YYYY-MM")
    try:
        factor_sets = config.load_config().get("factor_sets", {})
    except FileNotFoundError as error:
        raise ValueError("factor-set configuration is unavailable; add config/carbon_room.yaml") from error
    if factor_set not in factor_sets:
        available = ", ".join(sorted(factor_sets)) or "none"
        raise ValueError(f"unknown factor set {factor_set!r}; configured factor sets: {available}")
    boundary = list(sites)
    for site_id in boundary:
        config.site(site_id)
    with connect() as db:
        return ledger.create_close(db, month, boundary, factor_set, actor, chat_message_id)


def ingest(close_id, actor):
    """P1 implementation: collect close and baseline source documents."""
    from carbon_room import collect

    with connect() as db:
        return collect.ingest(db, close_id, actor)


def ingest_file(close_id, path, actor, chat_message_id, site=None):
    """P1 implementation: ingest one human-uploaded source."""
    from carbon_room import collect
    from carbon_room.models import NeedsRoomEvent

    if actor.kind == "human" and not chat_message_id:
        raise NeedsRoomEvent("human uploads require a Switch chat_message_id")
    with connect() as db:
        return collect.ingest_file(
            db, close_id, path, actor, site=site, month_from_period=True,
            chat_message_id=chat_message_id,
        )


def calculate(close_id):
    """P2 implementation: calculate all applicable live claims."""
    from carbon_room.calc import run

    with connect() as db:
        return run.calculate(db, close_id)


def check(close_id):
    """P2 implementation: apply rules and verification pass."""
    _unimplemented("P2", "P2-3.9")


def resolve(gap_id, action, actor, chat_message_id, payload):
    """P2 implementation: resolve a gap option and re-run checks."""
    _unimplemented("P2", "P2-4.1")


def summary(close_id):
    """P2 implementation: return a pure close summary."""
    _unimplemented("P2", "P2-5.1")


def draft_report(close_id):
    """P2 implementation: create a draft report and source tags."""
    _unimplemented("P2", "P2-5.2")


def publish(close_id, actor, chat_message_id):
    """P2 implementation: publish an honest report through its role gate."""
    _unimplemented("P2", "P2-5.3")


def trace(close_id, tag):
    """P2 implementation: recompute a source tag from the ledger."""
    _unimplemented("P2", "P2-5.4")


def verify_audit(close_id):
    """P1 implementation: verify the close's hash chain."""
    with connect() as db:
        return verify_chain(db, close_id)


def resume_state(close_id):
    """P1 implementation: return phase and open gaps after a crash."""
    with connect() as db:
        return ledger.get_close(db, close_id)["phase"], ledger.get_gaps(db, close_id, status="OPEN")


def latest_close():
    """P1 implementation: return the most recent close identifier, if any."""
    with connect() as db:
        return ledger.latest_close(db)


def gap_for_thread(thread_root_message_id):
    """P1 implementation: map a Switch thread root to its gap."""
    with connect() as db:
        return ledger.get_gap_by_thread(db, thread_root_message_id)


def record_gap_thread(close_id, gap_id, message_id):
    """P1 implementation: persist the root message for a gap."""
    with connect() as db:
        return ledger.set_gap_thread(db, close_id, gap_id, message_id)


def budget_usage(close_id):
    """P1 implementation: expose per-agent close-level token usage."""
    with connect() as db:
        return budget.usage(db, close_id)


def explain(close_id, question, actor):
    """P1 implementation: phrase only verified ledger facts or UNKNOWN."""
    from carbon_room import explain as explainer

    with connect() as db:
        return explainer.answer(db, close_id, question, actor)
