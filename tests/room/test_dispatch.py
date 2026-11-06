"""Dispatcher and worker lanes (SPEC-10)."""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import time

from fakes.fake_core import FakeCore

from carbon_room.room.async_core import AsyncCore
from carbon_room.room.dispatch import Dispatcher
from carbon_room.room.events import RoomEvent
from carbon_room.room.grammar import Intent


def ev(message_id, *, room="room-1", agent="watchdog", type="message", body="x"):
    return RoomEvent(type, room, message_id, None, "@u:s", "User", body, (), False, 0, agent, 0)


def decode(agent, frame):
    if "boom" in frame:
        raise ValueError("bad frame")
    if "event" not in frame:
        return None
    return dataclasses.replace(frame["event"], receiving_agent=agent)


def classify(event):
    if event.body == "explode":
        raise ValueError("bad classify")
    if event.body == "ignore@watchdog":
        kind = "ignore" if event.receiving_agent == "watchdog" else "ask"
        return Intent(kind, {}, "carbon-room")
    return Intent(event.body, {}, "carbon-room")


class Recorder:
    def __init__(self, sleep=None):
        self.sleep = sleep or {}
        self.starts = []
        self.ends = []
        self.start_t = {}
        self.end_t = {}
        self.errors = []
        self.running = 0
        self.peak = 0
        self.raise_for = {}
        self.on_error_raises = False

    async def handle(self, event, intent):
        self.starts.append((intent.kind, event.message_id))
        self.start_t[event.message_id] = time.monotonic()
        self.running += 1
        self.peak = max(self.peak, self.running)
        try:
            if event.message_id in self.raise_for:
                raise self.raise_for[event.message_id]
            await asyncio.sleep(self.sleep.get(intent.kind, 0))
        finally:
            self.running -= 1
        self.ends.append((intent.kind, event.message_id))
        self.end_t[event.message_id] = time.monotonic()

    async def on_error(self, event, intent, exc):
        self.errors.append((event, intent, exc))
        if self.on_error_raises:
            raise RuntimeError("x")

    def dispatcher(self, **kw):
        return Dispatcher(decode=decode, classify=classify, handle=self.handle,
                          on_error=self.on_error, room_id="room-1", **kw)


def frame(event):
    return {"event": event}


def drive(d, body):
    async def main():
        task = asyncio.create_task(d.run())
        await body()
        await asyncio.wait_for(d.join(), 3)
        await d.stop()
        await asyncio.wait_for(task, 3)

    asyncio.run(main())


def test_slow_core_call_does_not_delay_loop():
    core = AsyncCore(FakeCore(delay=1.0))
    done = []
    lateness = []

    async def handle(event, intent):
        await core.latest_close()
        done.append(event.message_id)

    async def on_error(event, intent, exc):
        raise AssertionError(exc)

    d = Dispatcher(decode=decode, classify=classify, handle=handle, on_error=on_error,
                   room_id="room-1")

    async def probe():
        end = time.monotonic() + 1.2
        while time.monotonic() < end:
            t0 = time.monotonic()
            await asyncio.sleep(0.05)
            lateness.append(time.monotonic() - t0 - 0.05)

    async def main():
        task = asyncio.create_task(d.run())
        d.submit("watchdog", frame(ev("m1", body="close.start")))
        await probe()
        await asyncio.wait_for(d.join(), 3)
        await d.stop()
        await asyncio.wait_for(task, 3)

    asyncio.run(main())
    assert done == ["m1"]
    assert max(lateness) < 0.2


def test_two_resolves_same_close_run_in_order():
    r = Recorder({"gap.reply": 0.1})
    d = r.dispatcher()

    async def body():
        d.submit("watchdog", frame(ev("a", body="gap.reply")))
        d.submit("watchdog", frame(ev("b", body="gap.reply")))

    drive(d, body)
    assert r.starts == [("gap.reply", "a"), ("gap.reply", "b")]
    assert r.start_t["b"] >= r.end_t["a"]


def test_mutations_fifo_across_kinds():
    r = Recorder({"close.start": 0.1})
    d = r.dispatcher()

    async def body():
        d.submit("watchdog", frame(ev("a", body="close.start")))
        d.submit("watchdog", frame(ev("b", body="gap.fallback")))
        d.submit("watchdog", frame(ev("c", body="report.draft")))

    drive(d, body)
    assert [m for _, m in r.starts] == ["a", "b", "c"]
    assert r.start_t["b"] >= r.end_t["a"]
    assert r.start_t["c"] >= r.end_t["b"]
    assert r.peak == 1


def test_reads_run_concurrently_with_mutation():
    r = Recorder({"gap.reply": 0.3, "ask": 0.0})
    d = r.dispatcher()

    async def body():
        d.submit("watchdog", frame(ev("a", body="gap.reply")))
        d.submit("watchdog", frame(ev("b", body="ask")))

    drive(d, body)
    assert r.end_t["b"] < r.end_t["a"]


def test_reads_capped_by_max_reads():
    r = Recorder({"ask": 0.2})
    d = r.dispatcher(max_reads=2)

    async def body():
        for i in range(5):
            d.submit("watchdog", frame(ev(f"m{i}", body="ask")))

    drive(d, body)
    assert r.peak == 2
    assert len(r.ends) == 5


def test_duplicate_message_id_handled_once():
    r = Recorder()
    d = r.dispatcher()

    async def body():
        d.submit("carbon-room", frame(ev("m1", body="close.start")))
        d.submit("watchdog", frame(ev("m1", body="close.start")))
        await asyncio.wait_for(d.join(), 3)
        d.submit("carbon-room", frame(ev("m1", body="close.start")))

    drive(d, body)
    assert r.starts == [("close.start", "m1")]
    assert d.handled_count == 1


def test_ignored_copy_does_not_block_addressed_copy():
    r = Recorder()
    d = r.dispatcher()

    async def body():
        d.submit("watchdog", frame(ev("m1", body="ignore@watchdog")))
        d.submit("carbon-room", frame(ev("m1", body="ignore@watchdog")))

    drive(d, body)
    assert r.starts == [("ask", "m1")]


def test_other_room_dropped():
    r = Recorder()
    d = r.dispatcher()

    async def body():
        d.submit("watchdog", frame(ev("m1", room="room-2", body="ask")))

    drive(d, body)
    assert r.starts == []


def test_non_message_dropped():
    r = Recorder()
    d = r.dispatcher()

    async def body():
        d.submit("watchdog", frame(ev("j1", type="room_join", body="ask")))
        d.submit("watchdog", {"nothing": True})

    drive(d, body)
    assert r.starts == []


def test_decode_or_classify_error_is_logged_and_dropped(caplog):
    r = Recorder()
    d = r.dispatcher()

    async def body():
        d.submit("watchdog", {"boom": 1})
        d.submit("watchdog", frame(ev("m2", body="explode")))
        d.submit("watchdog", frame(ev("m3", body="ask")))

    with caplog.at_level(logging.DEBUG):
        drive(d, body)
    assert r.starts == [("ask", "m3")]
    assert len([x for x in caplog.records if x.levelno == logging.WARNING]) == 2


def test_handler_exception_goes_to_on_error():
    r = Recorder()
    r.raise_for = {"m1": ValueError("bad")}
    d = r.dispatcher()

    async def body():
        d.submit("watchdog", frame(ev("m1", body="gap.reply")))
        d.submit("watchdog", frame(ev("m2", body="gap.reply")))

    drive(d, body)
    assert len(r.errors) == 1
    event, intent, exc = r.errors[0]
    assert event.message_id == "m1"
    assert intent.kind == "gap.reply"
    assert str(exc) == "bad"
    assert ("gap.reply", "m2") in r.ends


def test_on_error_failure_is_logged_not_raised(caplog):
    r = Recorder()
    r.raise_for = {"m1": ValueError("bad")}
    r.on_error_raises = True
    d = r.dispatcher()

    async def body():
        d.submit("watchdog", frame(ev("m1", body="gap.reply")))
        d.submit("watchdog", frame(ev("m2", body="gap.reply")))

    with caplog.at_level(logging.DEBUG):
        drive(d, body)
    assert any(x.levelno == logging.ERROR for x in caplog.records)
    assert ("gap.reply", "m2") in r.ends


def test_seen_limit_evicts_oldest():
    r = Recorder()
    d = r.dispatcher(seen_limit=2)

    async def body():
        for m in ("m1", "m2", "m3", "m1"):
            d.submit("watchdog", frame(ev(m, body="ask")))

    drive(d, body)
    ids = [m for _, m in r.starts]
    assert ids.count("m1") == 2
    assert ids.count("m3") == 1


def test_submit_never_blocks():
    r = Recorder()
    d = r.dispatcher()
    results = []

    async def main():
        f = frame(ev("m1", body="ask"))
        t0 = time.perf_counter()
        for _ in range(1000):
            results.append(d.submit("watchdog", f))
        assert time.perf_counter() - t0 < 0.05

    asyncio.run(main())
    assert results == [None] * 1000


def test_stop_waits_for_inflight_mutation(caplog):
    r = Recorder({"gap.reply": 0.3})
    d = r.dispatcher()

    async def main():
        task = asyncio.create_task(d.run())
        d.submit("watchdog", frame(ev("a", body="gap.reply")))
        d.submit("watchdog", frame(ev("b", body="gap.reply")))
        while not r.starts:
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.05)
        await d.stop()
        await asyncio.wait_for(task, 3)

    with caplog.at_level(logging.DEBUG):
        asyncio.run(main())
    assert ("gap.reply", "a") in r.ends
    assert all(m != "b" for _, m in r.starts)
    assert "dropping 1 queued mutation(s) on stop" in caplog.text


def test_stop_cancels_reads():
    r = Recorder({"ask": 5})
    d = r.dispatcher()
    elapsed = []

    async def main():
        task = asyncio.create_task(d.run())
        d.submit("watchdog", frame(ev("a", body="ask")))
        while not r.starts:
            await asyncio.sleep(0.01)
        t0 = time.monotonic()
        await d.stop()
        elapsed.append(time.monotonic() - t0)
        await asyncio.wait_for(task, 3)

    asyncio.run(main())
    assert elapsed[0] < 1
    assert r.ends == []
    assert r.errors == []


def test_submit_after_stop_ignored():
    r = Recorder()
    d = r.dispatcher()

    async def main():
        task = asyncio.create_task(d.run())
        await asyncio.sleep(0)
        await d.stop()
        d.submit("watchdog", frame(ev("m1", body="ask")))
        await asyncio.sleep(0.05)
        await asyncio.wait_for(task, 3)

    asyncio.run(main())
    assert r.starts == []
