"""Guards for a public demo: per-client rate limits and a daily cap on model calls.

Counts live in this process, so they suit a single instance and reset on restart.
The API key's own spend limit is the backstop.
"""

import math
import threading
from collections import deque
from datetime import datetime, timedelta

from fastapi import HTTPException, Request, status


class RateLimiter:
    def __init__(self) -> None:
        self._attempts: dict[str, deque[datetime]] = {}
        self._lock = threading.Lock()

    def attempt(self, key: str, limit: int, window: timedelta, now: datetime) -> timedelta | None:
        with self._lock:
            attempts = self._attempts.setdefault(key, deque())
            while attempts and attempts[0] <= now - window:
                attempts.popleft()
            if len(attempts) >= limit:
                return attempts[0] + window - now
            attempts.append(now)
            return None


class DailyBudget:
    """At most `limit` model calls per UTC day across all clients."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self._day: str | None = None
        self._used = 0
        self._lock = threading.Lock()

    def spend(self, now: datetime) -> bool:
        with self._lock:
            day = now.date().isoformat()
            if day != self._day:
                self._day, self._used = day, 0
            if self._used >= self.limit:
                return False
            self._used += 1
            return True


def rate_limited(name: str, limit: int, window: timedelta):
    def check(request: Request) -> None:
        state = request.app.state
        client = request.client.host if request.client else "unknown"
        wait = state.rate_limiter.attempt(f"{name}:{client}", limit, window, state.clock())
        if wait is not None:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Too many requests. Please try again later.",
                headers={"Retry-After": str(math.ceil(wait.total_seconds()))},
            )

    return check


def spend_model_call(request: Request) -> None:
    state = request.app.state
    if not state.daily_budget.spend(state.clock()):
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "The demo has reached its daily limit. Please try again tomorrow.",
        )
