"""Room handlers against the actual SQLite ledger and fictional seed evidence."""

import asyncio
import shutil
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from pathlib import Path

from fakes.fake_room import FakeRoom

from carbon_room import config, core
from carbon_room.agents import hooks, orchestrator, publish, resolution
from carbon_room.calc import factors
from carbon_room.ledger import connect, init_db
from carbon_room.room import grammar, messages
from carbon_room.room.async_core import AsyncCore
from carbon_room.room.events import RoomEvent
from carbon_room.room.noise import NoiseGuard
from carbon_room.room.ports import Context

ROOT = Path(__file__).resolve().parents[2]


def make_event(body, message_id, *, sender="@switch-user-lead:test", thread=None,
               receiving="watchdog"):
    return RoomEvent("message", "room-1", message_id, thread, sender, sender.rsplit("-", 1)[-1],
                     body, (), True, 0, receiving, 1)


def test_real_room_flow_reaches_expected_published_total(tmp_path, monkeypatch):
    shutil.copytree(ROOT / "config", tmp_path / "config")
    shutil.copy(ROOT / "tests/room/fixtures/people.yaml", tmp_path / "config/people.yaml")
    shutil.copytree(ROOT / "data/seed", tmp_path / "data/seed")
    shutil.copytree(ROOT / "data/demo_uploads", tmp_path / "data/demo_uploads")
    (tmp_path / "data/inbox").mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CARBON_ROOM_CONFIG_DIR", str(tmp_path / "config"))
    config.clear_caches()
    try:
        with connect() as db:
            init_db(db)
            factors.load(db)
            db.commit()

        async def flow():
            executor = ThreadPoolExecutor(max_workers=4)
            room = FakeRoom()
            ctx = Context(core=AsyncCore(core, executor), room=NoiseGuard(room, max_posts=12),
                          display=lambda pid: f"@{pid}", today=lambda: date(2026, 11, 5),
                          inbox_dir=Path("data/inbox"))
            ctx.on_phase_end = lambda cid: hooks.after_phase(ctx, cid)
            try:
                start = make_event("@carbon-room close October", "h-1", receiving="carbon-room")
                await orchestrator.handle_close_start(
                    ctx, start, grammar.parse(start.body, in_thread=False, today=ctx.today()),
                    config_actor("lead"),
                )
                cid = await ctx.core.latest_close()
                assert cid == "2026-10-v1"
                initial = await ctx.core.summary(cid)
                assert (initial.verified_kgco2e, initial.excluded_kgco2e,
                        initial.coverage_pct, initial.sources_verified) == (
                            Decimal("0"), Decimal("24686.90828783499300"), Decimal("0"), 0)
                assert {g.rule for g in initial.open_gaps} == {"R2", "R3", "R4", "R5"}
                assert len([p for p in room.top_level() if p.agent == "watchdog"]) == 4

                async def assert_summary(verified, excluded, coverage, sources):
                    current = await ctx.core.summary(cid)
                    assert (current.verified_kgco2e, current.excluded_kgco2e,
                            current.coverage_pct, current.sources_verified) == (
                                Decimal(verified), Decimal(excluded), Decimal(coverage), sources)
                    assert room.docs["close-board"] == messages.board(
                        messages.month_label("2026-10"), current, ctx.display, ctx.room.link)

                async def reply(rule, body, message_id, actor):
                    gap = next(g for g in (await ctx.core.resume_state(cid))[1] if g.rule == rule)
                    event = make_event(body, message_id, sender=actor[0],
                                       thread=gap.thread_root_message_id)
                    intent = grammar.parse(body, in_thread=True, today=ctx.today())
                    await resolution.handle_gap_reply(ctx, event, intent, actor[1])

                shutil.copy(ROOT / "data/demo_uploads/warehouse2_electricity_2026-10_actual.pdf",
                            tmp_path / "data/inbox/warehouse2_electricity_2026-10_actual.pdf")
                await reply("R4", "upload warehouse2_electricity_2026-10_actual.pdf", "h-2",
                            ("@switch-user-priya:test", config_actor("priya")))
                await assert_summary("2422.76000", "24686.90828783499300", "9", 1)
                for rule, body, mid in (("R2", "pick A", "h-3"), ("R3", "approve", "h-4"),
                                        ("R5", "approve", "h-5")):
                    await reply(rule, body, mid, ("@switch-user-lead:test", config_actor("lead")))
                    await assert_summary(*{
                        "R2": ("8623.25600", "13319.33228783499300", "39", 2),
                        "R3": ("12521.6096000", "9420.28748783499300", "57", 3),
                        "R5": ("21941.89708783499300", "0", "100", 4),
                    }[rule])
                final = await ctx.core.summary(cid)
                assert final.verified_kgco2e == Decimal("21941.89708783499300")
                assert final.coverage_pct == Decimal("100")
                assert final.sources_verified == final.sources_expected == 4
                assert final.open_gaps == []
                assert len(room.top_level()) <= 12
                assert "close-board" in room.docs
                assert "100" in room.docs["close-board"]
                for root in (p for p in room.top_level() if p.agent == "watchdog"):
                    replies = [p.text for p in room.in_thread(root.message_id)]
                    assert replies[0] == "Checking…"
                    assert replies[1].startswith("Resolved.")
                draft = make_event("@reporter draft", "h-6", receiving="reporter")
                await publish.handle_draft(ctx, draft, grammar.parse(draft.body, in_thread=False,
                                                                   today=ctx.today()), config_actor("lead"))
                pub = make_event("@carbon-room publish", "h-7", receiving="carbon-room")
                await publish.handle_publish(ctx, pub, grammar.parse(pub.body, in_thread=False,
                                                                    today=ctx.today()), config_actor("lead"))
                assert (await ctx.core.resume_state(cid))[0] == "PUBLISHED"
                assert any("Published v1" in p.text for p in room.posts)
                assert {p.name for p in (tmp_path / "out/2026-10/v1").iterdir()} == {
                    "report.json", "report.md", "coverage.html", "report.pdf"}
                assert (await ctx.core.verify_audit(cid)).ok
            finally:
                executor.shutdown(wait=True)

        asyncio.run(flow())
    finally:
        config.clear_caches()


def config_actor(person_id):
    from carbon_room.models import Actor

    if person_id == "priya":
        return Actor("human", "priya", "Priya", "site_manager")
    return Actor("human", "lead", "Sustainability Lead", "lead")
