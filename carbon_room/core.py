"""Frozen room-facing facade; P1 owns signatures and P2 owns calculation behaviour."""

from __future__ import annotations


def _unimplemented(owner: str, story: str) -> None:
    raise NotImplementedError(f"owner: {owner}, story {story}")


def start_close(month, sites, factor_set, actor, chat_message_id):
    """P1 implementation: create a close and lock its factor set."""
    _unimplemented("P1", "P1-8.1")


def ingest(close_id, actor):
    """P1 implementation: collect close and baseline source documents."""
    _unimplemented("P1", "P1-8.2")


def ingest_file(close_id, path, actor, chat_message_id, site=None):
    """P1 implementation: ingest one human-uploaded source."""
    _unimplemented("P1", "P1-8.2")


def calculate(close_id):
    """P2 implementation: calculate all applicable live claims."""
    _unimplemented("P2", "P2-2.1")


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
    _unimplemented("P1", "P1-3.2")


def resume_state(close_id):
    """P1 implementation: return phase and open gaps after a crash."""
    _unimplemented("P1", "P1-8.4")


def latest_close():
    """P1 implementation: return the most recent close identifier, if any."""
    _unimplemented("P1", "P1-2.1")


def gap_for_thread(thread_root_message_id):
    """P1 implementation: map a Switch thread root to its gap."""
    _unimplemented("P1", "P1-2.5")


def record_gap_thread(close_id, gap_id, message_id):
    """P1 implementation: persist the root message for a gap."""
    _unimplemented("P1", "P1-2.5")


def budget_usage(close_id):
    """P1 implementation: expose per-agent close-level token usage."""
    _unimplemented("P1", "P1-4.2")


def explain(close_id, question, actor):
    """P1 implementation: phrase only verified ledger facts or UNKNOWN."""
    _unimplemented("P1", "P1-8.5")
