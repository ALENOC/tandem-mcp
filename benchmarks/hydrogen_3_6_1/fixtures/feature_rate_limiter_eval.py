import sys
import unittest
from pathlib import Path


class FakeClock:
    def __init__(self, start: float = 100.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class TestRateLimiterEval(unittest.TestCase):
    def setUp(self):
        import rate_limiter
        self.mod = rate_limiter

    def test_validation(self):
        with self.assertRaises(ValueError):
            self.mod.TokenBucketRateLimiter(0, 1.0)
        with self.assertRaises(ValueError):
            self.mod.TokenBucketRateLimiter(-5, 1.0)
        with self.assertRaises(ValueError):
            self.mod.TokenBucketRateLimiter(5, -0.1)
        rl = self.mod.TokenBucketRateLimiter(5, 1.0, time_fn=FakeClock())
        with self.assertRaises(ValueError):
            rl.allow(0)
        with self.assertRaises(ValueError):
            rl.allow(-1)

    def test_consume_and_refill(self):
        clk = FakeClock(10.0)
        rl = self.mod.TokenBucketRateLimiter(capacity=5.0, refill_rate=2.0, time_fn=clk)
        self.assertAlmostEqual(rl.available_tokens(), 5.0)
        self.assertTrue(rl.allow(3.0))
        self.assertAlmostEqual(rl.available_tokens(), 2.0)
        self.assertFalse(rl.allow(3.0))
        clk.advance(1.0)
        self.assertAlmostEqual(rl.available_tokens(), 4.0)
        self.assertTrue(rl.allow(4.0))
        self.assertAlmostEqual(rl.available_tokens(), 0.0)

    def test_cap_and_reset(self):
        clk = FakeClock(0.0)
        rl = self.mod.TokenBucketRateLimiter(capacity=4.0, refill_rate=10.0, time_fn=clk)
        self.assertTrue(rl.allow(4.0))
        clk.advance(5.0)
        self.assertAlmostEqual(rl.available_tokens(), 4.0)
        self.assertTrue(rl.allow(2.5))
        rl.reset()
        self.assertAlmostEqual(rl.available_tokens(), 4.0)


if __name__ == "__main__":
    unittest.main()
