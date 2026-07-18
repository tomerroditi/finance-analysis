import asyncio
from typing import Awaitable, Callable, TypeVar

from scraper.exceptions import TimeoutError

T = TypeVar("T")


async def wait_until(
    async_test: Callable[[], Awaitable[T]],
    description: str = "",
    timeout: float = 10.0,
    interval: float = 0.1,
) -> T:
    """Poll an async function until it returns a truthy value or timeout.

    The timeout is measured against wall-clock time, so it accounts for time
    spent inside ``async_test`` itself (e.g. a slow page evaluation or network
    probe), not just the sleeps between polls.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        result = await async_test()
        if result:
            return result
        await asyncio.sleep(interval)
    raise TimeoutError(f"Timeout: {description}" if description else "Timeout")


async def sleep(seconds: float) -> None:
    """Async sleep wrapper."""
    await asyncio.sleep(seconds)


async def wait_for_first(*coros: Awaitable) -> None:
    """Run awaitables concurrently and return once the first one finishes.

    The remaining awaitables are cancelled. Exceptions raised by completed
    awaitables (e.g. a timed-out element wait) are consumed, not re-raised —
    this helper exists for "wait until any of these signals appears" races
    where the caller inspects the page state afterwards.

    Parameters
    ----------
    *coros : Awaitable
        The awaitables to race against each other.
    """
    tasks = [asyncio.create_task(coro) for coro in coros]
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()
    for task in done:
        task.exception()  # consume so asyncio doesn't warn about unretrieved errors
