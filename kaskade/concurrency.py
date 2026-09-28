import asyncio
from collections.abc import Callable
from typing import Any, TypeVar

from kaskade import logger

T = TypeVar("T")


async def run_blocking(func: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
    """Run a blocking call in a worker thread without blocking the event loop.

    A thread cannot be interrupted, so cancelling the caller waits for the call to
    finish before re-raising ``CancelledError``: locks the caller holds stay held,
    and a client it closes next is never still in use. The cancellation wins over
    the call's own outcome; a failure is logged instead of raised. Cancelling the
    caller again while it waits stops the wait, not the call.
    """
    call = asyncio.ensure_future(asyncio.to_thread(func, *args, **kwargs))
    try:
        return await asyncio.shield(call)
    except asyncio.CancelledError:
        await asyncio.wait({call})
        if not call.cancelled() and (error := call.exception()) is not None:
            logger.warning("blocking call failed after its caller was cancelled: %r", error)
        raise
