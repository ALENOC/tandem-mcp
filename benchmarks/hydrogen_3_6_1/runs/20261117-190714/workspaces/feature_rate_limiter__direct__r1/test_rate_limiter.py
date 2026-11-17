"""Unit tests for rate_limiter.py."""

import unittest

from rate_limiter import TokenBucketRateLimiter


class FakeClock:
    """Deterministic manual clock for testing."""

    def __init__(self, initial: float = 0.0) -> None:
        self.now = initial

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class TestTokenBucketRateLimiter(unittest.TestCase):
    """Tests for TokenBucketRateLimiter."""

    def test_init_validation(self) -> None:
        with self.assertRaises(ValueError):
            TokenBucketRateLimiter(capacity=0, refill_rate=1.0)
        with self.assertRaises(ValueError):
            TokenBucketRateLimiter(capacity=-5, refill_rate=1.0)
        with self.assertRaises(ValueError):
            TokenBucketRateLimiter(capacity=10, refill_rate=-0.1)

        clock = FakeClock(100.0)
        limiter = TokenBucketRateLimiter(capacity=5, refill_rate=0.0, time_fn=clock)
        self.assertEqual(limiter.available_tokens(), 5.0)
        self.assertIsInstance(limiter.available_tokens(), float)

    def test_default_time_fn(self) -> None:
        limiter = TokenBucketRateLimiter(capacity=2, refill_rate=1.0)
        self.assertEqual(limiter.available_tokens(), 2.0)
        self.assertTrue(limiter.allow())

    def test_allow_validation(self) -> None:
        clock = FakeClock()
        limiter = TokenBucketRateLimiter(capacity=5, refill_rate=1.0, time_fn=clock)
        with self.assertRaises(ValueError):
            limiter.allow(0)
        with self.assertRaises(ValueError):
            limiter.allow(-1.5)

    def test_consumption_and_rejection(self) -> None:
        clock = FakeClock()
        limiter = TokenBucketRateLimiter(capacity=5, refill_rate=1.0, time_fn=clock)

        self.assertTrue(limiter.allow())  # 5 -> 4
        self.assertEqual(limiter.available_tokens(), 4.0)

        self.assertTrue(limiter.allow(2.5))  # 4 -> 1.5
        self.assertAlmostEqual(limiter.available_tokens(), 1.5)

        # Insufficient tokens: should return False and not deduct
        self.assertFalse(limiter.allow(2.0))
        self.assertAlmostEqual(limiter.available_tokens(), 1.5)

        # Exact remaining tokens
        self.assertTrue(limiter.allow(1.5))
        self.assertAlmostEqual(limiter.available_tokens(), 0.0)
        self.assertFalse(limiter.allow())

    def test_refill_over_time(self) -> None:
        clock = FakeClock(10.0)
        limiter = TokenBucketRateLimiter(capacity=10, refill_rate=2.0, time_fn=clock)

        self.assertTrue(limiter.allow(10))
        self.assertEqual(limiter.available_tokens(), 0.0)

        clock.advance(1.5)  # +3.0 tokens
        self.assertAlmostEqual(limiter.available_tokens(), 3.0)

        self.assertTrue(limiter.allow(2.0))
        self.assertAlmostEqual(limiter.available_tokens(), 1.0)

        clock.advance(0.25)  # +0.5 tokens
        self.assertAlmostEqual(limiter.available_tokens(), 1.5)

    def test_zero_refill_rate(self) -> None:
        clock = FakeClock()
        limiter = TokenBucketRateLimiter(capacity=3, refill_rate=0.0, time_fn=clock)

        self.assertTrue(limiter.allow(3))
        clock.advance(1000.0)
        self.assertEqual(limiter.available_tokens(), 0.0)
        self.assertFalse(limiter.allow())

    def test_capacity_capping(self) -> None:
        clock = FakeClock()
        limiter = TokenBucketRateLimiter(capacity=5, refill_rate=10.0, time_fn=clock)

        self.assertTrue(limiter.allow(4))
        self.assertEqual(limiter.available_tokens(), 1.0)

        # Advancing 10 seconds would add 100 tokens, but must cap at 5.0
        clock.advance(10.0)
        self.assertEqual(limiter.available_tokens(), 5.0)
        self.assertFalse(limiter.allow(5.1))
        self.assertTrue(limiter.allow(5.0))

    def test_reset(self) -> None:
        clock = FakeClock(50.0)
        limiter = TokenBucketRateLimiter(capacity=4, refill_rate=1.0, time_fn=clock)

        self.assertTrue(limiter.allow(4))
        self.assertEqual(limiter.available_tokens(), 0.0)

        clock.advance(1.0)
        limiter.reset()
        self.assertEqual(limiter.available_tokens(), 4.0)

        # Ensure reset updated timestamp and bucket remains capped
        self.assertTrue(limiter.allow(3))
        self.assertEqual(limiter.available_tokens(), 1.0)
        clock.advance(2.0)
        self.assertEqual(limiter.available_tokens(), 3.0)


if __name__ == "__main__":
    unittest.main()
