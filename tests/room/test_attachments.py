"""Attachment fetcher (SPEC-11 section 6)."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import pytest

from carbon_room.room.attachments import MAX_BYTES, AttachmentMissing, fetch, safe_name
from carbon_room.room.events import Attachment

ATT = Attachment("bill.pdf", "application/pdf", 12, "mxc://s/x", "m.file")
INBOX = Path("data/inbox")
TOO_BIG = "That file is over 10 MiB, so I can't take it."


def missing(name):
    return f"I can't see that file yet. Put it in data/inbox/ and reply upload {name}."


def run(**kw):
    args = dict(message_id="msg:1", attachment=ATT, typed_name=None, mode="inbox",
                inbox_dir=INBOX, download=None)
    args.update(kw)
    return asyncio.run(fetch(**args))


def put(name, data=b"x"):
    INBOX.mkdir(parents=True, exist_ok=True)
    (INBOX / name).write_bytes(data)


@pytest.fixture(autouse=True)
def _cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


@pytest.mark.parametrize("raw, expected", [
    ("../../etc/passwd", "passwd"),
    ("bill (1).pdf", "bill__1_.pdf"),
    ("C:\\Users\\me\\bill.pdf", "bill.pdf"),
    ("rapport_\u00e9t\u00e9.pdf", "rapport__t_.pdf"),
    ("a/b/ok-1.PDF", "ok-1.PDF"),
])
def test_safe_name_traversal_and_unicode(raw, expected):
    assert safe_name(raw) == expected


@pytest.mark.parametrize("raw", ["", ".", "..", ".env", "dir/", "x" * 151])
def test_safe_name_rejects(raw):
    with pytest.raises(AttachmentMissing) as ei:
        safe_name(raw)
    if len(raw) > 150:
        assert ei.value.text == "That file name is too long. Rename it and try again."
    else:
        assert ei.value.text == "That file name isn't usable. Rename it and try again."
    assert str(ei.value) == ei.value.text


def _dl(data):
    async def download(att):
        return data
    return download


def test_download_mode_writes_managed_file():
    p = run(mode="download", download=_dl(b"%PDF"))
    assert p == Path("data/inbox/msg_1_bill.pdf")
    assert p.read_bytes() == b"%PDF"
    assert INBOX.is_dir()


def test_download_existing_file_refused():
    put("msg_1_bill.pdf", b"old")
    with pytest.raises(AttachmentMissing) as ei:
        run(mode="download", download=_dl(b"new"))
    assert ei.value.text == "I already have a file called msg_1_bill.pdf. Rename it and try again."
    assert (INBOX / "msg_1_bill.pdf").read_bytes() == b"old"


def test_download_too_big():
    with pytest.raises(AttachmentMissing) as ei:
        run(mode="download", download=_dl(b"x" * (MAX_BYTES + 1)))
    assert ei.value.text == TOO_BIG
    assert not (INBOX / "msg_1_bill.pdf").exists()

    big = Attachment("bill.pdf", None, MAX_BYTES + 1, "mxc://s/x", "m.file")

    async def boom(att):
        raise AssertionError("download must not be called")

    with pytest.raises(AttachmentMissing) as ei:
        run(attachment=big, mode="download", download=boom)
    assert ei.value.text == TOO_BIG
    assert not (INBOX / "msg_1_bill.pdf").exists()


def test_download_failure_falls_back_to_inbox(caplog):
    put("bill.pdf")

    async def bad(att):
        raise RuntimeError("nope")

    with caplog.at_level(logging.WARNING):
        p = run(mode="download", download=bad)
    assert p == Path("data/inbox/bill.pdf")
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_download_mode_without_attachment_uses_inbox():
    put("typed.pdf")
    calls = []

    async def dl(att):
        calls.append(att)
        return b""

    p = run(attachment=None, typed_name="typed.pdf", mode="download", download=dl)
    assert p == Path("data/inbox/typed.pdf")
    assert calls == []


def test_inbox_mode_finds_file():
    put("bill.pdf")
    assert run() == Path("data/inbox/bill.pdf")


def test_inbox_typed_name_wins():
    put("other.pdf")
    assert run(typed_name="other.pdf") == Path("data/inbox/other.pdf")


def test_inbox_missing_gives_exact_text():
    with pytest.raises(AttachmentMissing) as ei:
        run(typed_name="Bill Oct.pdf")
    assert ei.value.text == missing("Bill_Oct.pdf")
    with pytest.raises(AttachmentMissing) as ei:
        run(attachment=None)
    assert ei.value.text == missing("<name>")


def test_inbox_rejects_symlink(tmp_path):
    (tmp_path / "outside.pdf").write_bytes(b"x")
    INBOX.mkdir(parents=True)
    (INBOX / "link.pdf").symlink_to(tmp_path / "outside.pdf")
    with pytest.raises(AttachmentMissing) as ei:
        run(typed_name="link.pdf")
    assert ei.value.text == missing("link.pdf")


def test_inbox_rejects_directory():
    (INBOX / "folder.pdf").mkdir(parents=True)
    with pytest.raises(AttachmentMissing) as ei:
        run(typed_name="folder.pdf")
    assert ei.value.text == missing("folder.pdf")


def test_inbox_rejects_oversize():
    INBOX.mkdir(parents=True)
    with open(INBOX / "big.pdf", "wb") as f:
        f.truncate(MAX_BYTES + 1)
    with pytest.raises(AttachmentMissing) as ei:
        run(typed_name="big.pdf")
    assert ei.value.text == TOO_BIG


def test_inbox_traversal_name_stays_inside(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "secret.pdf").write_bytes(b"x")
    INBOX.mkdir(parents=True, exist_ok=True)
    with pytest.raises(AttachmentMissing) as ei:
        run(typed_name="../secret.pdf")
    assert ei.value.text == missing("secret.pdf")


def test_unknown_mode():
    with pytest.raises(ValueError) as ei:
        run(mode="ftp")
    assert str(ei.value) == "unknown attachments mode 'ftp'"
