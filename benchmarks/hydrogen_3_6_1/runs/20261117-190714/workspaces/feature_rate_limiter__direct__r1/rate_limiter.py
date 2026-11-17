"""Deterministic token-bucket rate limiter."""

from __future__ import annotations

import time
from typing import Callable


class TokenBucketRateLimiter:
    """A deterministic token-bucket rate limiter."""

    def __init__(
        self,
        capacity: float,
        refill_rate: float,
        time_fn: Callable[[], float] | None = None,
    ) -> None:
        """Initialize the rate limiter.

        Args:
            capacity: Maximum number of tokens in the bucket (must be > 0).
            refill_rate: Tokens added per second (must be >= 0).
            time_fn: Optional zero-arg callable returning current time in seconds.
        """
        if capacity <= 0:
            raise ValueError("capacity must be > 0")
        if refill_rate < 0:
            raise ValueError("refill_rate must be >= 0")

        self._capacity: float = float(capacity)
        self._refill_rate: float = float(refill_rate)
        self._time_fn: Callable[[], float] = (
            time.monotonic if time_fn is None else time_fn
        )
        self._tokens: float = float(capacity)
        self._last_refill: float = self._time_fn()

    def _refill(self) -> None:
        """Refill tokens based on elapsed time since the last check."""
        now = self._time_fn()
        elapsed = now - self._last_refill
        if elapsed > 0:
            self._tokens = min(
                self._capacity, self._tokens + elapsed * self._refill_rate
            )
            self._last_refill = now
        elif elapsed < 0:
            # Keep timestamp aligned if a non-monotonic clock steps backwards
            self._last_refill = now

    def allow(self, tokens: float = 1.0) -> bool:
        """Attempt to consume `tokens` from the bucket.

        Args:
            tokens: Number of tokens to consume (must be > 0).

        Returns:
            True if the tokens were available and consumed, False otherwise.
        """
        if tokens <= 0:
            raise ValueError("tokens must be > 0")

        self._refill()
        if self._tokens >= tokens:
            self._tokens -= tokens
            return True
        return False

    def available_tokens(self) -> float:
        """Return the current number of available tokens after refilling."""
        self._refill()
        return self._tokens

    def reset(self) -> None:
        """Reset the bucket back to full capacity at the current timestamp."""
        self._tokens = self._capacity
        self._last_refill = self._time_fn()
