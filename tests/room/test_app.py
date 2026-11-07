"""The Switch acceptance rule and handler table are the room security boundary."""

from datetime import date

import pytest

from carbon_room.room.events import RoomEvent


def event(body: str, *, receiving: str, addressed: bool, thread: str | None = None,
          sender: str = "@switch-user-lead:test") -> RoomEvent:
    return RoomEvent("message", "room-1", "h-1", thread, sender, "lead", body, (),
                     addressed, 0, receiving, 1)


@pytest.mark.parametrize(("receiving", "addressed", "body", "thread", "sender", "single", "kind"), [
    ("carbon-room", True, "@carbon-room close October", None, "@switch-user-lead:test", False, "close.start"),
    ("watchdog", False, "@carbon-room close October", None, "@switch-user-lead:test", False, "ignore"),
    ("reporter", True, "@carbon-room close October", None, "@switch-user-lead:test", False, "ignore"),
    ("carbon-room", False, "@carbon-room close October", None, "@switch-user-lead:test", True, "close.start"),
    ("collector", True, "@collector what is HQ diesel?", None, "@switch-user-lead:test", False, "ask"),
    ("watchdog", False, "pick a", "m-4", "@switch-user-lead:test", False, "gap.reply"),
    ("watchdog", False, "pick a", "m-4", "@x:test", False, "ignore"),
    ("watchdog", True, "pick a", "m-4", "@x:test", False, "gap.reply"),
    ("watchdog", False, "G-2 pick A", None, "@switch-user-lead:test", False, "gap.fallback"),
    ("carbon-room", True, "@carbon-room G-2 pick A", None, "@switch-user-lead:test", False, "gap.fallback"),
    ("watchdog", False, "hello everyone", None, "@switch-user-lead:test", False, "ignore"),
    ("reporter", True, "@reporter trace S-1", None, "@switch-user-lead:test", False, "report.trace"),
    ("carbon-room", True, "@reporter trace S-1", None, "@switch-user-lead:test", False, "ignore"),
])
def test_classify_acceptance_matrix(people_config, receiving, addressed, body, thread, sender, single, kind):
    from carbon_room.room.app import classify

    got = classify(event(body, receiving=receiving, addressed=addressed, thread=thread, sender=sender),
                   today=date(2026, 11, 5), single_agent=single)
    assert got.kind == kind


def test_handler_table_covers_every_intent():
    from carbon_room.room.app import HANDLERS

    assert set(HANDLERS) == {"close.start", "close.status", "close.resume", "close.publish",
                             "report.draft", "report.trace", "audit.verify", "help", "ask",
                             "gap.reply", "gap.fallback"}
    assert HANDLERS["gap.reply"] is HANDLERS["gap.fallback"]
