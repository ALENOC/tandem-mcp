# Specification: `rate_limiter.py`

Create a Python module `rate_limiter.py` implementing a deterministic token-bucket rate limiter:

1. Class `TokenBucketRateLimiter(capacity: float, refill_rate: float, time_fn=None)`:
   - `capacity`: maximum number of tokens in the bucket (must be `> 0`, else raise `ValueError`).
   - `refill_rate`: tokens added per second (must be `>= 0`, else raise `ValueError`).
   - `time_fn`: optional zero-arg callable returning current time in seconds (defaults to `time.monotonic`).
   - Bucket starts full (`tokens = float(capacity)`).

2. Method `allow(tokens: float = 1.0) -> bool`:
   - If `tokens <= 0`, raise `ValueError`.
   - Refill the bucket based on elapsed time since last check, capped at `capacity`.
   - If current tokens `>= tokens`, subtract `tokens` and return `True`; otherwise do not subtract and return `False`.

3. Method `available_tokens() -> float`:
   - Refill based on elapsed time (capped at `capacity`) and return current available tokens.

4. Method `reset() -> None`:
   - Refill/reset the bucket back to `float(capacity)` at the current `time_fn()` timestamp.

Also create `test_rate_limiter.py` with unit tests covering initialization validation, consumption, refill over time, capacity capping, and `reset()`.
