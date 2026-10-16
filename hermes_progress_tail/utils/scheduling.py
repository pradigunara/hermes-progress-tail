from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from concurrent.futures import Future
from typing import Any


def submit_or_close(coro: Coroutine[Any, Any, Any], loop: asyncio.AbstractEventLoop) -> Future[Any]:
    try:
        return asyncio.run_coroutine_threadsafe(coro, loop)
    except BaseException:
        coro.close()
        raise


def create_task_or_close(
    loop: asyncio.AbstractEventLoop, coro: Coroutine[Any, Any, Any]
) -> asyncio.Task[Any]:
    try:
        return loop.create_task(coro)
    except BaseException:
        coro.close()
        raise
