from __future__ import annotations

import asyncio
import time


class AsyncRateLimiter:
    """Small dependency-free interval limiter for vendor REST APIs."""

    def __init__(self, requests_per_second: float) -> None:
        if requests_per_second <= 0:
            raise ValueError("requests_per_second must be positive")
        self.interval = 1.0 / requests_per_second
        self._next = 0.0
        self._lock = asyncio.Lock()

    async def __aenter__(self) -> AsyncRateLimiter:
        async with self._lock:
            now = time.monotonic()
            if self._next > now:
                await asyncio.sleep(self._next - now)
            self._next = max(now, self._next) + self.interval
        return self

    async def __aexit__(self, *_: object) -> None:
        return None
