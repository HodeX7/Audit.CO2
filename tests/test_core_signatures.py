from __future__ import annotations

import inspect

from carbon_room import core


def test_contract_core_parameter_names_are_frozen():
    expected = {
        "start_close": ("month", "sites", "factor_set", "actor", "chat_message_id"),
        "ingest": ("close_id", "actor"),
        "ingest_file": ("close_id", "path", "actor", "chat_message_id", "site"),
        "calculate": ("close_id",),
        "check": ("close_id",),
        "resolve": ("gap_id", "action", "actor", "chat_message_id", "payload"),
        "summary": ("close_id",),
        "draft_report": ("close_id",),
        "publish": ("close_id", "actor", "chat_message_id"),
        "trace": ("close_id", "tag"),
        "verify_audit": ("close_id",),
        "resume_state": ("close_id",),
        "latest_close": (),
        "gap_for_thread": ("thread_root_message_id",),
        "record_gap_thread": ("close_id", "gap_id", "message_id"),
        "budget_usage": ("close_id",),
        "explain": ("close_id", "question", "actor"),
    }
    for name, parameters in expected.items():
        assert tuple(inspect.signature(getattr(core, name)).parameters) == parameters


def test_ingest_file_site_is_optional():
    assert inspect.signature(core.ingest_file).parameters["site"].default is None
