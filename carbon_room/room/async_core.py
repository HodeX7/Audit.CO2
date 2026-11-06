"""Run the synchronous core on a thread pool."""

from __future__ import annotations

import concurrent.futures
from collections.abc import Awaitable, Callable
from typing import Any

CORE_FUNCTIONS: tuple[str, ...] = (
    "start_close", "ingest", "ingest_file", "calculate", "check", "resolve",
    "summary", "draft_report", "publish", "trace", "verify_audit", "resume_state", "latest_close",
    "gap_for_thread", "record_gap_thread", "budget_usage", "explain",
)


class AsyncCore:
    def __init__(self, core: Any, executor: concurrent.futures.Executor | None = None) -> None:
        raise NotImplementedError

    def __getattr__(self, name: str) -> Callable[..., Awaitable[Any]]:
        raise NotImplementedError
