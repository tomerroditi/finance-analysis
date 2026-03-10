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
    """Poll an async function until it returns a truthy value or timeout."""
    elapsed = 0.0
    while elapsed < timeout:
        result = await async_test()
        if result:
            return result
        await asyncio.sleep(interval)
        elapsed += interval
    raise TimeoutError(f"Timeout: {description}" if description else "Timeout")


async def sleep(seconds: float) -> None:
    """Async sleep wrapper."""
    await asyncio.sleep(seconds)
