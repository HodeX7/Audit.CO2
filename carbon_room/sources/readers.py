"""Safe, deterministic source text readers."""

from __future__ import annotations

import json
from email import policy
from email.parser import BytesParser
from pathlib import Path

MAX_SOURCE_BYTES = 10 * 1024 * 1024


def read(path: str | Path) -> tuple[str, list[str] | str]:
    """Return `(SourceKind, pages)` or `(SourceKind, error)`; corrupt inputs never escape."""
    file = Path(path)
    suffix = file.suffix.lower()
    kinds = {".pdf": "utility_pdf", ".eml": "email_invoice", ".csv": "drive_csv", ".json": "cloud_invoice"}
    kind = kinds.get(suffix, "utility_pdf")
    try:
        if file.is_symlink() or not file.is_file() or file.stat().st_size > MAX_SOURCE_BYTES:
            return kind, f"unreadable {file.name}"
        if suffix == ".pdf":
            import pdfplumber

            with pdfplumber.open(file) as pdf:
                return kind, [(page.extract_text() or "") for page in pdf.pages]
        if suffix == ".eml":
            message = BytesParser(policy=policy.default).parsebytes(file.read_bytes())
            body = message.get_body(preferencelist=("plain",))
            text = body.get_content() if body else ""
            header = (
                f"Subject: {message.get('subject', '')}\n"
                f"From: {message.get('from', '')}\n"
                f"Date: {message.get('date', '')}\n"
            )
            return kind, [f"{header}{text}"]
        if suffix == ".json":
            return kind, [json.dumps(json.loads(file.read_text(encoding="utf-8")), sort_keys=True, indent=2)]
        return kind, [file.read_text(encoding="utf-8")]
    except Exception:  # input safety boundary; provider errors may include local details
        return kind, f"unreadable {file.name}"
