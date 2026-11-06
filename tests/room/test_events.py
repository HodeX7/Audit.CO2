import copy
import json
from pathlib import Path

import pytest

from carbon_room.room.events import Attachment, RoomEvent, decode

FRAMES = Path(__file__).parent / "fixtures" / "frames"


def load(name):
    return json.loads((FRAMES / name).read_text())


def top():
    return load("message_top.json")


def test_decode_top_level_message():
    ev = decode(load("message_top.json"), "carbon-room")
    assert ev == RoomEvent(
        "message", "room-1", "msg-top-1", None, "@switch-user-lead:test", "lead",
        "@carbon-room close October", (), True, 1793000000000, "carbon-room", 101,
    )
    assert ev.in_thread is False


def test_decode_thread_reply():
    ev = decode(load("message_thread_reply.json"), "watchdog")
    assert ev.thread_id == "msg-root-1"
    assert ev.message_id == "msg-reply-1"
    assert ev.body == "pick a"
    assert ev.in_thread is True


def test_thread_id_equal_to_message_id_is_not_in_thread():
    f = top()
    f["data"]["payload"]["thread_id"] = "msg-top-1"
    assert decode(f, "carbon-room").in_thread is False


def test_decode_attachment_fields():
    ev = decode(load("message_with_attachment.json"), "watchdog")
    assert ev.attachments == (
        Attachment(
            "warehouse2_electricity_2026-10_actual.pdf", "application/pdf", 48213,
            "mxc://switch.local/abc123", "m.file",
        ),
    )
    assert ev.body == ""


def test_decode_attachment_odd_entries():
    f = top()
    f["data"]["payload"]["attachments"] = ["x", {"size": "12"}]
    assert decode(f, "carbon-room").attachments == (Attachment("", None, None, None, None),)


def test_decode_drops_own_agents_by_id_and_name():
    assert decode(load("message_from_own_agent.json"), "carbon-room") is None
    f = top()
    f["data"]["payload"]["sender_name"] = " Reporter "
    assert decode(f, "carbon-room") is None
    assert decode(top(), "carbon-room", frozenset({"@switch-user-lead:test"})) is None


@pytest.mark.parametrize("name", ["command.json", "ping.json", "connection_state.json", "evicted.json"])
def test_decode_skips_command_and_control(name):
    assert decode(load(name), "carbon-room") is None


def test_decode_room_join():
    ev = decode(load("room_join.json"), "watchdog")
    assert ev.type == "room_join"
    assert ev.message_id == "join:106"
    assert ev.sender == "@switch-user-priya:test"
    assert ev.sender_name == "priya"
    assert ev.body == ""
    assert ev.addressed is False


def _no_room():
    f = top()
    del f["data"]["room_id"]
    return f


def _no_seq():
    f = top()
    del f["id"]
    del f["data"]["sequence"]
    return f


def _body5():
    f = top()
    f["data"]["payload"]["body"] = 5
    return f


@pytest.mark.parametrize(
    "frame",
    [load("message_no_id.json"), load("message_bad_payload.json"), _no_room(), _no_seq(), _body5(), {}, []],
    ids=["no_id", "bad_payload", "no_room", "no_seq", "body5", "empty_dict", "list"],
)
def test_decode_malformed_returns_none(frame):
    assert decode(frame, "carbon-room") is None


def test_decode_body_none_is_empty():
    f = copy.deepcopy(top())
    f["data"]["payload"]["body"] = None
    assert decode(f, "carbon-room").body == ""


def test_captured_frames_decode_without_error():
    files = sorted(FRAMES.glob("captured_*.json"))
    if not files:
        pytest.skip("no captured frames yet")
    for p in files:
        result = decode(json.loads(p.read_text()), "watchdog")
        assert result is None or isinstance(result, RoomEvent)


def test_fixtures_are_labelled():
    for p in FRAMES.glob("*.json"):
        assert json.loads(p.read_text()).get("_source") in ("docs", "captured"), p.name
