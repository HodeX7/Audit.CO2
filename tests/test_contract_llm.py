from __future__ import annotations

from types import SimpleNamespace

from carbon_room import llm
from carbon_room.ledger import ledger
from carbon_room.ledger.budget import usage
from carbon_room.models import Actor


class _Messages:
    def create(self, **_kwargs):
        return SimpleNamespace(
            content=[SimpleNamespace(text='{"candidates": []}')],
            usage=SimpleNamespace(input_tokens=3, output_tokens=2),
        )


class _Client:
    messages = _Messages()


def test_live_provider_charges_the_caller_ledger(db):
    close_id = ledger.create_close(db, "2026-10", ["test-site"], "FS-test", Actor("system", "seed", "Seed"), "msg")
    llm.set_client_factory(_Client)
    try:
        assert llm.complete_json("extract", "system", {}, "collector", close_id, conn=db) == {"candidates": []}
    finally:
        llm.set_client_factory(None)
    assert usage(db, close_id)["collector"]["used"] == 5


def test_vendor_neutral_provider_has_a_small_explicit_contract(db):
    close_id = ledger.create_close(db, "2026-10", ["test-site"], "FS-test", Actor("system", "seed", "Seed"), "msg")
    received = {}

    def provider(**kwargs):
        received.update(kwargs)
        return {"candidates": []}, 7

    llm.set_completion_provider(provider)
    try:
        result = llm.complete_json("extract", "system", {"pages": []}, "collector", close_id, conn=db)
    finally:
        llm.set_completion_provider(None)
    assert result == {"candidates": []}
    assert received["task"] == "extract"
    assert received["max_tokens"] == 2048
    assert usage(db, close_id)["collector"]["used"] == 7
