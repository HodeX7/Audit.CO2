"""Fake core implementing the contracts section 10 story with fake numbers."""

from __future__ import annotations


class FakeCore:
    def __init__(self, *, delay: float = 0.0) -> None:
        raise NotImplementedError

    def start_close(self, month, sites, factor_set, actor, chat_message_id):
        raise NotImplementedError

    def ingest(self, close_id, actor):
        raise NotImplementedError

    def ingest_file(self, close_id, path, actor, chat_message_id, site=None):
        raise NotImplementedError

    def calculate(self, close_id):
        raise NotImplementedError

    def check(self, close_id):
        raise NotImplementedError

    def resolve(self, gap_id, action, actor, chat_message_id, payload):
        raise NotImplementedError

    def summary(self, close_id):
        raise NotImplementedError

    def draft_report(self, close_id):
        raise NotImplementedError

    def publish(self, close_id, actor, chat_message_id):
        raise NotImplementedError

    def trace(self, close_id, tag):
        raise NotImplementedError

    def verify_audit(self, close_id):
        raise NotImplementedError

    def resume_state(self, close_id):
        raise NotImplementedError

    def latest_close(self):
        raise NotImplementedError

    def gap_for_thread(self, thread_root_message_id):
        raise NotImplementedError

    def record_gap_thread(self, close_id, gap_id, message_id):
        raise NotImplementedError

    def budget_usage(self, close_id):
        raise NotImplementedError

    def explain(self, close_id, question, actor):
        raise NotImplementedError
