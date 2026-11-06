"""Run the synchronous core on a thread pool."""

from __future__ import annotations

import asyncio
import concurrent.futures
import functools
from collections.abc import Awaitable, Callable
from typing import Any

CORE_FUNCTIONS: tuple[str, ...] = (
    "start_close", "ingest", "ingest_file", "calculate", "check", "resolve",
    "summary", "draft_report", "publish", "trace", "verify_audit", "resume_state", "latest_close",
    "gap_for_thread", "record_gap_thread", "budget_usage", "explain",
)


class AsyncCore:
    def __init__(self, core: Any, executor: concurrent.futures.Executor | None = None) -> None:
        self._core = core
        self._executor = executor or concurrent.futures.ThreadPoolExecutor(
            max_workers=4, thread_name_prefix="core"
        )

    def __getattr__(self, name: str) -> Callable[..., Awaitable[Any]]:
        if name not in CORE_FUNCTIONS:
            raise AttributeError(name)
        core, executor = self._core, self._executor

        async def call(*args: Any, **kwargs: Any) -> Any:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(executor, functools.partial(getattr(core, name), *args, **kwargs))

        call.__name__ = name
        return call
