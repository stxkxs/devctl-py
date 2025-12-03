"""Async utilities for bulk operations."""

import asyncio
from collections.abc import Awaitable, Callable, Iterable
from typing import TypeVar

T = TypeVar("T")
R = TypeVar("R")


async def gather_with_concurrency(
    n: int,
    *coros: Awaitable[T],
) -> list[T]:
    """Run coroutines with limited concurrency.

    Args:
        n: Maximum number of concurrent coroutines
        *coros: Coroutines to run

    Returns:
        List of results in the same order as input
    """
    semaphore = asyncio.Semaphore(n)

    async def sem_coro(coro: Awaitable[T]) -> T:
        async with semaphore:
            return await coro

    return await asyncio.gather(*[sem_coro(coro) for coro in coros])


async def map_async(
    func: Callable[[T], Awaitable[R]],
    items: Iterable[T],
    concurrency: int = 10,
) -> list[R]:
    """Apply an async function to items with limited concurrency.

    Args:
        func: Async function to apply
        items: Items to process
        concurrency: Maximum concurrent operations

    Returns:
        List of results
    """
    return await gather_with_concurrency(
        concurrency,
        *[func(item) for item in items],
    )


async def run_with_timeout(
    coro: Awaitable[T],
    timeout: float,
    timeout_message: str = "Operation timed out",
) -> T:
    """Run a coroutine with a timeout.

    Args:
        coro: Coroutine to run
        timeout: Timeout in seconds
        timeout_message: Message for timeout error

    Returns:
        Result of the coroutine

    Raises:
        TimeoutError: If the operation times out
    """
    from devctl.core.exceptions import TimeoutError

    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        raise TimeoutError(timeout_message, timeout_seconds=int(timeout))


def run_sync(coro: Awaitable[T]) -> T:
    """Run an async function synchronously.

    This is useful for integrating async code with Click commands.

    Args:
        coro: Coroutine to run

    Returns:
        Result of the coroutine
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # If we're already in an async context, create a new loop
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()
    else:
        return asyncio.run(coro)


class AsyncBatcher:
    """Batch async operations for efficiency."""

    def __init__(
        self,
        batch_size: int = 100,
        concurrency: int = 10,
    ):
        self.batch_size = batch_size
        self.concurrency = concurrency

    async def process(
        self,
        items: list[T],
        processor: Callable[[list[T]], Awaitable[list[R]]],
    ) -> list[R]:
        """Process items in batches.

        Args:
            items: Items to process
            processor: Async function that processes a batch

        Returns:
            Combined results from all batches
        """
        results: list[R] = []

        # Split into batches
        batches = [
            items[i : i + self.batch_size] for i in range(0, len(items), self.batch_size)
        ]

        # Process batches with limited concurrency
        batch_results = await map_async(processor, batches, self.concurrency)

        for batch_result in batch_results:
            results.extend(batch_result)

        return results


class RateLimiter:
    """Simple rate limiter for API calls."""

    def __init__(self, calls_per_second: float = 10.0):
        self.calls_per_second = calls_per_second
        self.min_interval = 1.0 / calls_per_second
        self._last_call = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Wait for rate limit slot."""
        async with self._lock:
            import time

            now = time.monotonic()
            elapsed = now - self._last_call
            if elapsed < self.min_interval:
                await asyncio.sleep(self.min_interval - elapsed)
            self._last_call = time.monotonic()

    async def __aenter__(self) -> "RateLimiter":
        await self.acquire()
        return self

    async def __aexit__(self, *args: object) -> None:
        pass
