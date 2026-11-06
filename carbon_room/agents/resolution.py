"""Gap reply resolution (SPEC-13)."""

from __future__ import annotations

import logging

from carbon_room.agents import gaps
from carbon_room.models import Actor, CarbonRoomError, NotAllowed
from carbon_room.room import attachments, errors, messages, router
from carbon_room.room.events import RoomEvent
from carbon_room.room.grammar import Intent
from carbon_room.room.ports import Context

log = logging.getLogger(__name__)

_STILL_FLAGGED = "the next check still flags it"


async def handle_gap_reply(ctx: Context, event: RoomEvent, intent: Intent, actor: Actor) -> None:
    core = ctx.core
    command_thread = event.thread_id or event.message_id

    if intent.kind == "gap.fallback":
        close_id = await core.latest_close()
        if close_id is None:
            await ctx.room.post("watchdog", messages.no_close(), thread_id=command_thread)
            return
        _, open_gaps = await core.resume_state(close_id)
        gap = router.find_gap(open_gaps, intent.args["gap_id"])
        if gap is None:
            await ctx.room.post("watchdog", messages.gap_not_found(intent.args["gap_id"]),
                                thread_id=command_thread)
            return
    else:
        if event.thread_id is None:
            return
        gap = await core.gap_for_thread(event.thread_id)
        if gap is None:
            log.debug("reply in thread %s is not a gap thread", event.thread_id)
            return
        latest = await core.latest_close()
        if gap.close_id != latest:
            await ctx.room.post("watchdog", messages.old_close_gap(gap), thread_id=event.thread_id)
            return
        close_id = gap.close_id

    thread = gap.thread_root_message_id or event.thread_id or event.message_id

    async def say(text: str) -> None:
        await ctx.room.post("watchdog", text, thread_id=thread)

    if actor.role is None:
        await say(errors.reply_for(NotAllowed("guest"), owner_name=ctx.display(gap.owner)).text)
        return

    m = router.match_reply(gap, intent.args["text"], bool(event.attachments))
    if isinstance(m, router.NoMatch):
        if m.reason == "unknown_reply":
            await say(messages.options_help(gap))
        elif m.reason == "gap_resolved":
            await say(messages.already_resolved(gap))
        else:
            await say(messages.no_reply_needed())
        return

    await say(messages.checking())
    payload = dict(m.payload)
    if m.option.action == "upload":
        try:
            path = await attachments.fetch(
                message_id=event.message_id,
                attachment=event.attachments[0] if event.attachments else None,
                typed_name=m.filename,
                mode=ctx.attachments_mode,
                inbox_dir=ctx.inbox_dir,
                download=ctx.download,
            )
        except attachments.AttachmentMissing as exc:
            await say(exc.text)
            return
        payload["path"] = str(path)
    try:
        before = await core.summary(close_id)
        findings = await core.resolve(gap.gap_id, m.option.action, actor, event.message_id, payload)
    except (CarbonRoomError, ValueError) as exc:
        await say(errors.reply_for(exc, owner_name=ctx.display(gap.owner)).text)
        return

    _, open_after = await core.resume_state(close_id)
    if gap.gap_id not in {g.gap_id for g in open_after}:
        await say(messages.outcome_resolved(gap))
    else:
        reason = next((f.title for f in findings if f.finding_id == gap.finding_id), _STILL_FLAGGED)
        await say(messages.outcome_open(gap, reason))

    await gaps.post_new_gaps(ctx, close_id, findings)
    after = await core.summary(close_id)
    if (after.verified_kgco2e != before.verified_kgco2e
            or after.coverage_pct != before.coverage_pct):
        await ctx.room.post("carbon-room", messages.total_moved(before, after), essential=False)
    await ctx.on_phase_end(close_id)
