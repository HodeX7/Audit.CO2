"""Throwaway M2 spike (plan §6 M2; SPEC-08 §8): S1 threads, S5 message ids, read_context shape,
targeted messages, S6 room documents, and setting addressing to "anyone" (SPEC-09B).

It writes to the live room in .env: two "[spike]" posts and one targeted post. It creates and then deletes one
"spike-board-<time>" document. It sets the four agents' addressing to "anyone". It never prints a key.
Stop `make run` first, then run from the repo root:

    .venv/bin/python scripts/spikes/m2_ops_check.py /tmp/m2-spike.json

Record the answers in docs/spikes.md (S1, S5, S6), and capture frames (keys are already scrubbed) into
tests/room/fixtures/frames/captured_*.json.
"""
import asyncio
import json
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import urlencode

import httpx
from dotenv import dotenv_values
from websockets.asyncio.client import connect

OUT = Path(sys.argv[1])
env = dotenv_values(".env")
SERVER = env["SWITCH_SERVER"].rstrip("/")
ROOM = env["SWITCH_ROOM_ID"]
CREDS = {
    n: (env[f"SWITCH_AGENT_{n.upper().replace('-', '_')}_ID"], env[f"SWITCH_AGENT_{n.upper().replace('-', '_')}_KEY"])
    for n in ("carbon-room", "collector", "watchdog", "reporter")
}
SECRETS = [k for _, k in CREDS.values()] + [env.get("SWITCH_REGISTRATION_KEY") or "x" * 40]


def scrub(obj):
    text = json.dumps(obj, default=str)
    for s in SECRETS:
        if s:
            text = text.replace(s, "<redacted>")
    return json.loads(text)


def show(label, obj, limit=1500):
    t = json.dumps(scrub(obj), indent=1, default=str)
    print(f"--- {label}\n{t[:limit]}")


class Sock:
    def __init__(self, name, filt):
        self.name, self.filt = name, filt
        self.agent_id, self.key = CREDS[name]
        self.cid = str(uuid.uuid4())
        self.frames, self.cursor, self.ready = [], 0, asyncio.Event()

    async def run(self):
        q = urlencode({"connection_id": self.cid, "rooms": ROOM, "filter": self.filt,
                       "client": "carbon-room-spike", "client_version": "0"})
        url = SERVER.replace("http", "ws", 1) + f"/agents/{self.agent_id}/connection/ws?{q}"
        async with connect(url, additional_headers={"Authorization": f"Bearer {self.key}"}, ping_interval=None) as ws:
            self.ws = ws
            async for raw in ws:
                f = json.loads(raw)
                kind = f.get("type") or f.get("event")
                if kind == "ping" or (isinstance(f.get("data"), dict) and f["data"].get("type") == "ping"):
                    await ws.send(json.dumps({"type": "pong", "cursor": self.cursor}))
                    if not any(x.get("_ping") for x in self.frames):
                        self.frames.append({"_ping": True, "raw": f})
                    continue
                seq = f.get("id") if isinstance(f.get("id"), int) else None
                if seq is not None:
                    self.cursor = max(self.cursor, seq)
                self.frames.append({"t": time.time(), "raw": f})
                if kind == "connection_state" or (
                    isinstance(f.get("data"), dict) and f["data"].get("type") == "connection_state"
                ):
                    self.ready.set()


async def main():
    results = {}
    cr, wd = Sock("carbon-room", "addressed"), Sock("watchdog", "all")
    tasks = [asyncio.create_task(s.run()) for s in (cr, wd)]
    try:
        await asyncio.wait_for(asyncio.gather(cr.ready.wait(), wd.ready.wait()), 10)
    except TimeoutError:
        print("sockets did not connect; frames:", scrub([s.frames for s in (cr, wd)]))
        raise
    show("carbon-room first frame", cr.frames[0]["raw"])
    async with httpx.AsyncClient(base_url=SERVER, timeout=15) as http:
        async def op(sock, name, args, *, conn=True):
            h = {"Authorization": f"Bearer {sock.key}"}
            if conn:
                h["X-Switch-Connection-Id"] = sock.cid
            r = await http.post(f"/agents/{sock.agent_id}/ops/{name}", json=args, headers=h)
            try:
                body = r.json()
            except Exception:
                body = r.text[:500]
            results.setdefault("ops", []).append({"op": name, "args": args, "status": r.status_code, "body": body})
            show(f"{sock.name} {name} -> {r.status_code}", body, 1200)
            return r.status_code, body

        # S1 + S5: post without connect_to_room first
        st, body = await op(cr, "post_message", {"body": "[spike S1] root message, please ignore"})
        if st >= 400:
            await op(cr, "connect_to_room", {"room_id": ROOM, "include_general_instructions": False})
            st, body = await op(cr, "post_message", {"body": "[spike S1] root message, please ignore"})
        root_id = (body.get("result") or {}).get("event_id") if isinstance(body, dict) else None
        results["root_event_id"] = root_id
        st, body = await op(
            cr, "post_message", {"body": "[spike S1] threaded reply, please ignore", "thread_id": root_id}
        )
        reply_id = (body.get("result") or {}).get("event_id") if isinstance(body, dict) else None
        results["reply_event_id"] = reply_id
        await asyncio.sleep(2)

        # targeted message to watchdog
        await op(
            cr, "send_targeted_message", {"body": "[spike] targeted hello, please ignore", "target_names": ["watchdog"]}
        )
        await asyncio.sleep(2)

        # read_context shape
        st, ctx = await op(cr, "read_context", {"limit": 6})
        results["read_context"] = ctx

        # S6 docs + connect_to_room payload documents
        name = f"spike-board-{int(time.time())}"
        st, created = await op(
            cr,
            "create_room_document",
            {"name": name, "description": "spike", "instructions": "spike, ignore", "content": "# spike\nv1"},
        )
        doc_id = (created.get("result") or {}).get("document_id") if isinstance(created, dict) else None
        st, dup = await op(
            cr,
            "create_room_document",
            {"name": name, "description": "spike", "instructions": "spike", "content": "dup"},
        )
        if doc_id:
            await op(cr, "update_room_document", {"document_id": doc_id, "content": "# spike\nv2"})
        st, conn_payload = await op(
            cr, "connect_to_room", {"room_id": ROOM, "include_general_instructions": False}
        )
        if isinstance(conn_payload, dict):
            res = conn_payload.get("result") or {}
            results["connect_documents"] = res.get("documents")
            results["connect_warning"] = res.get("warning")
            results["connect_keys"] = sorted(res)
        if doc_id:
            await op(cr, "delete_room_document", {"document_id": doc_id})

        # Addressing: owner-only, never yourself. Carbon-room sets the other three;
        # collector sets carbon-room.
        col = Sock("collector", "addressed")
        for target in ("collector", "watchdog", "reporter"):
            await op(cr, "update_agent_detail", {"agent_id": CREDS[target][0], "addressing": "anyone"}, conn=False)
        await op(col, "update_agent_detail", {"agent_id": CREDS["carbon-room"][0], "addressing": "anyone"}, conn=False)
        await op(cr, "update_agent_detail", {"agent_id": CREDS["carbon-room"][0], "addressing": "anyone"}, conn=False)

    await asyncio.sleep(1)
    for s in (cr, wd):
        await s.ws.close()
    for t in tasks:
        t.cancel()
    results["frames"] = {s.name: s.frames for s in (cr, wd)}
    OUT.write_text(json.dumps(scrub(results), indent=1, default=str))
    print("\n=== watchdog message frames (summary)")
    for f in wd.frames:
        raw = f.get("raw", {})
        d = raw.get("data") if isinstance(raw.get("data"), dict) else {}
        p = d.get("payload") if isinstance(d.get("payload"), dict) else {}
        print(json.dumps({"event": raw.get("event"), "type": raw.get("type") or d.get("type"), "id": raw.get("id"),
                          "message_id": p.get("message_id"), "thread_id": p.get("thread_id"),
                          "sender": p.get("sender"), "sender_name": p.get("sender_name"),
                          "addressed": p.get("addressed"), "body": (p.get("body") or "")[:60]}))
    print("root_event_id:", root_id, "reply_event_id:", reply_id)


asyncio.run(main())
