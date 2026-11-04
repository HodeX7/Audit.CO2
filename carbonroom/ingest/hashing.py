"""Hashing and text normalization used for evidence.

* A document is identified by the sha256 of its bytes (duplicates are skipped by this hash).
* An excerpt is stored whitespace-normalized; excerpt_sha256 = sha256(normalized excerpt, UTF-8).
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path

_DASHES = dict.fromkeys(map(ord, "‐‑‒–—―−"), "-")
_QUOTES = {ord("‘"): "'", ord("’"): "'", ord("“"): '"', ord("”"): '"'}
_WS = re.compile(r"\s+")


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_ws(text: str) -> str:
    """NFKC, ASCII dashes/quotes, non-breaking spaces -> spaces, collapse whitespace, strip."""
    text = unicodedata.normalize("NFKC", text).translate(_DASHES).translate(_QUOTES)
    return _WS.sub(" ", text).strip()


def excerpt_sha256(excerpt: str) -> str:
    return sha256_text(normalize_ws(excerpt))
