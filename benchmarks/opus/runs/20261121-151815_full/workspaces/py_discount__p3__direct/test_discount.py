import unittest

from discount import apply_discount, total


class DiscountTest(unittest.TestCase):
    def test_ten_percent(self):
        self.assertEqual(apply_discount(200, 10), 180.0)

    def test_zero(self):
        self.assertEqual(apply_discount(19.99, 0), 19.99)

    def test_rounding(self):
        self.assertEqual(apply_discount(10, 33), 6.7)

    def test_invalid_percent(self):
        with self.assertRaises(ValueError):
            apply_discount(10, 120)

    def test_negative_price(self):
        with self.assertRaises(ValueError):
            apply_discount(-1, 10)

    def test_total(self):
        self.assertEqual(total([(10, 2), (5, 1)], 20), 20.0)


if __name__ == "__main__":
    unittest.main()
