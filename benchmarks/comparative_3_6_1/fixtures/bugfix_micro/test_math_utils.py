import unittest
from math_utils import clamp

class TestClamp(unittest.TestCase):
    def test_within(self): self.assertEqual(clamp(5, 0, 10), 5)
    def test_low(self): self.assertEqual(clamp(-3, 0, 10), 0)
    def test_high(self): self.assertEqual(clamp(15, 0, 10), 10)

if __name__ == "__main__":
    unittest.main()
