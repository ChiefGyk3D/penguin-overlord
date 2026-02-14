# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Request Queue - Async request queue for AI generation.

Manages concurrent requests across features to prevent overloading
individual Ollama servers. Uses asyncio.Semaphore for concurrency
control and enforces minimum delay between requests to respect
rate limits.

This is crucial for multi-feature bots where news analysis, CVE analysis,
roasting, and moderation requests can all overlap in time.
"""

import asyncio
import logging
import time
from typing import Any, Callable, Coroutine, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar('T')


class RequestQueue:
    """
    Async request queue with concurrency control and rate limiting.

    Ensures that even when multiple features fire simultaneously
    (e.g., news check + CVE check + arch roast), requests are
    serialized per-server to prevent overload.
    """

    def __init__(
        self,
        max_concurrent: int = 4,
        min_delay: float = 1.0,
    ):
        """
        Initialize the request queue.

        Args:
            max_concurrent: Maximum concurrent requests
            min_delay: Minimum seconds between requests
        """
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._min_delay = min_delay
        self._last_request_time: float = 0
        self._delay_lock = asyncio.Lock()
        self._pending_count: int = 0
        self._total_requests: int = 0
        self._total_failures: int = 0

    async def submit(
        self,
        coro_func: Callable[..., Coroutine[Any, Any, T]],
        *args: Any,
        **kwargs: Any,
    ) -> Optional[T]:
        """
        Submit an async function to the queue.

        Waits for a semaphore slot, enforces minimum delay,
        then executes the coroutine.

        Args:
            coro_func: Async function to call
            *args: Positional arguments for the function
            **kwargs: Keyword arguments for the function

        Returns:
            Result of the coroutine or None on failure
        """
        self._pending_count += 1
        try:
            async with self._semaphore:
                # Enforce minimum delay between requests
                async with self._delay_lock:
                    now = time.monotonic()
                    elapsed = now - self._last_request_time
                    if elapsed < self._min_delay:
                        wait_time = self._min_delay - elapsed
                        logger.debug(f"Queue rate limit: waiting {wait_time:.1f}s")
                        await asyncio.sleep(wait_time)
                    self._last_request_time = time.monotonic()

                self._total_requests += 1
                try:
                    result = await coro_func(*args, **kwargs)
                    return result
                except Exception as e:
                    self._total_failures += 1
                    logger.error(f"Queue request failed: {e}")
                    return None
        finally:
            self._pending_count -= 1

    @property
    def pending_count(self) -> int:
        """Number of requests currently waiting or executing."""
        return self._pending_count

    @property
    def stats(self) -> dict:
        """Queue statistics."""
        return {
            'pending': self._pending_count,
            'total_requests': self._total_requests,
            'total_failures': self._total_failures,
            'success_rate': (
                f"{(1 - self._total_failures / max(1, self._total_requests)) * 100:.1f}%"
            ),
        }
