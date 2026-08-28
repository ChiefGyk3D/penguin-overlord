# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Bounded request queue for LLM calls.

Caps concurrency, enforces a minimum delay between dispatches, and —
unlike a bare semaphore — refuses new work once too many callers are
already waiting. Refusal (returning None) is the correct behavior for
this bot: a roast or analysis that would arrive minutes late is worthless,
and an unbounded backlog would keep enforcing stale moderation decisions.
"""

import asyncio
import logging
import time

logger = logging.getLogger(__name__)


class BoundedRequestQueue:
    def __init__(self, max_concurrent: int = 2, max_pending: int = 20, min_delay: float = 0.5):
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._max_pending = max_pending
        self._min_delay = min_delay
        self._pending = 0
        self._last_dispatch = 0.0
        self._delay_lock = asyncio.Lock()
        self.rejected_count = 0

    @property
    def pending(self) -> int:
        return self._pending

    async def submit(self, coro_func, *args, **kwargs):
        """Run coro_func(*args, **kwargs) under the queue's limits.

        Returns the coroutine's result, or None when the queue is full.
        Exceptions propagate to the caller — swallowing them here made
        genuine bugs look like "AI unavailable".
        """
        if self._pending >= self._max_pending:
            self.rejected_count += 1
            logger.warning(
                f"AI request queue full ({self._pending} pending); dropping request "
                f"(total dropped: {self.rejected_count})"
            )
            return None

        self._pending += 1
        try:
            async with self._semaphore:
                async with self._delay_lock:
                    elapsed = time.monotonic() - self._last_dispatch
                    if elapsed < self._min_delay:
                        await asyncio.sleep(self._min_delay - elapsed)
                    self._last_dispatch = time.monotonic()
                return await coro_func(*args, **kwargs)
        finally:
            self._pending -= 1
