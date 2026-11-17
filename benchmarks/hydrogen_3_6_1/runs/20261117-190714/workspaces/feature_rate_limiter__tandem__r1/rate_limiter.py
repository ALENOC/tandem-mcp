"""Token-bucket rate limiter."""

import time


class TokenBucketRateLimiter:
    """A deterministic token-bucket rate limiter."""

    def __init__(self, capacity: float, refill_rate: float, time_fn=None):
        if capacity <= 0:
            raise ValueError("capacity must be > 0")
        if refill_rate < 0:
            raise ValueError("refill_rate must be >= 0")
        self._capacity = float(capacity)
        self._refill_rate = float(refill_rate)
        self._time_fn = time_fn if time_fn is not None else time.monotonic
        self._tokens = float(capacity)
        self._last_time = self._time_fn()

    def _refill(self):
        now = self._time_fn()
        elapsed = now - self._last_time
        if elapsed > 0:
            self._tokens = min(self._capacity, self._tokens + elapsed * self._refill_rate)
        self._last_time = now

    def allow(self, tokens: float = 1.0) -> bool:
        if tokens <= 0:
            raise ValueError("tokens must be > 0")
        self._refill()
        if self._tokens >= tokens:
            self._tokens -= tokens
            return True
        return False

    def available_tokens(self) -> float:
        self._refill()
        return self._tokens

    def reset(self) -> None:
        self._tokens = float(self._capacity)
        self._last_time = self._time_fn()
