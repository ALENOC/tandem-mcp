"""Test per cron_sched: parser, iteratore e next_runs."""

import unittest
from datetime import datetime, timezone

from cron_sched import parse, next_runs, CronExpr


U = timezone.utc


def d(*a):
    return datetime(*a, tzinfo=U)


class TestParse(unittest.TestCase):
    def test_parse_returns_sets(self):
        c = parse("* * * * *")
        self.assertEqual(c.minute, set(range(60)))
        self.assertEqual(c.hour, set(range(24)))
        self.assertEqual(c.day_of_month, set(range(1, 32)))
        self.assertEqual(c.month, set(range(1, 13)))
        self.assertEqual(c.day_of_week, set(range(7)))

    def test_parse_single_values(self):
        c = parse("5 10 15 6 3")
        self.assertEqual(c.minute, {5})
        self.assertEqual(c.hour, {10})
        self.assertEqual(c.day_of_month, {15})
        self.assertEqual(c.month, {6})
        self.assertEqual(c.day_of_week, {3})

    def test_parse_range(self):
        c = parse("0 9-17 * * *")
        self.assertEqual(c.hour, set(range(9, 18)))

    def test_parse_list(self):
        c = parse("5,10,20 * * * *")
        self.assertEqual(c.minute, {5, 10, 20})

    def test_parse_step_star(self):
        c = parse("*/15 * * * *")
        self.assertEqual(c.minute, {0, 15, 30, 45})

    def test_parse_step_range(self):
        c = parse("0 9-17/4 * * *")
        self.assertEqual(c.hour, {9, 13, 17})

    def test_parse_mixed_list(self):
        c = parse("1-3,7,10-12 * * * *")
        self.assertEqual(c.minute, {1, 2, 3, 7, 10, 11, 12})


class TestNextRuns(unittest.TestCase):
    def test_every_minute(self):
        s = datetime(2026, 1, 1, 0, 0)
        self.assertEqual(
            next_runs("* * * * *", s, 3),
            [d(2026, 1, 1, 0, 1), d(2026, 1, 1, 0, 2), d(2026, 1, 1, 0, 3)])

    def test_default_count(self):
        s = datetime(2026, 1, 1, 0, 0)
        self.assertEqual(len(next_runs("* * * * *", s)), 5)

    def test_step_minutes(self):
        s = datetime(2026, 1, 1, 0, 0)
        self.assertEqual(
            next_runs("*/15 * * * *", s, 3),
            [d(2026, 1, 1, 0, 15), d(2026, 1, 1, 0, 30), d(2026, 1, 1, 0, 45)])

    def test_hour_range_step(self):
        s = datetime(2026, 1, 1, 0, 0)
        self.assertEqual(
            next_runs("0 9-17/4 * * *", s, 4),
            [d(2026, 1, 1, 9, 0), d(2026, 1, 1, 13, 0),
             d(2026, 1, 1, 17, 0), d(2026, 1, 2, 9, 0)])

    def test_list_and_month(self):
        s = datetime(2026, 1, 1, 0, 0)
        self.assertEqual(
            next_runs("5,10 0 1 1,3 *", s, 3),
            [d(2026, 1, 1, 0, 5), d(2026, 1, 1, 0, 10), d(2026, 3, 1, 0, 5)])

    def test_dow_monday(self):
        s = datetime(2026, 1, 1, 0, 0)
        self.assertEqual(
            next_runs("0 0 * * 1", s, 2),
            [d(2026, 1, 5), d(2026, 1, 12)])

    def test_dow_sunday(self):
        s = datetime(2026, 1, 1, 0, 0)
        self.assertEqual(next_runs("0 0 * * 0", s, 1), [d(2026, 1, 4)])

    def test_or_semantics(self):
        s = datetime(2026, 1, 1, 0, 0)
        self.assertEqual(
            next_runs("0 0 13 * 5", s, 3),
            [d(2026, 1, 2), d(2026, 1, 9), d(2026, 1, 13)])

    def test_leap_day(self):
        s = datetime(2026, 1, 1, 0, 0)
        self.assertEqual(next_runs("0 0 29 2 *", s, 1), [d(2028, 2, 29)])

    def test_strictly_after_aware(self):
        self.assertEqual(
            next_runs("30 12 * * *", datetime(2026, 1, 1, 12, 30, 0, tzinfo=U), 1),
            [d(2026, 1, 2, 12, 30)])

    def test_strictly_after_seconds(self):
        self.assertEqual(
            next_runs("* * * * *", datetime(2026, 1, 1, 0, 0, 30), 1),
            [d(2026, 1, 1, 0, 1)])

    def test_year_rollover(self):
        self.assertEqual(
            next_runs("0 0 1 1 *", datetime(2026, 12, 31, 23, 59), 1),
            [d(2027, 1, 1)])

    def test_result_tz_and_zero_seconds(self):
        s = datetime(2026, 1, 1, 0, 0)
        for dt in next_runs("0 0 1 1 *", s, 1):
            self.assertEqual(dt.tzinfo, U)
            self.assertEqual(dt.second, 0)
            self.assertEqual(dt.microsecond, 0)

    def test_naive_treated_as_utc(self):
        s = datetime(2025, 12, 31, 23, 59)
        self.assertEqual(next_runs("0 0 * * *", s, 1), [d(2026, 1, 1, 0, 0)])


class TestErrors(unittest.TestCase):
    def test_wrong_field_count(self):
        for bad in ["* * * *", "* * * * * *", ""]:
            with self.assertRaises(ValueError):
                next_runs(bad, datetime(2026, 1, 1, 0, 0), 1)

    def test_out_of_range(self):
        s = datetime(2026, 1, 1, 0, 0)
        for bad in ["60 * * * *", "* 24 * * *", "* * 0 * *",
                    "* * * 13 *", "* * * * 7"]:
            with self.assertRaises(ValueError):
                next_runs(bad, s, 1)

    def test_bad_interval(self):
        with self.assertRaises(ValueError):
            next_runs("5-1 * * * *", datetime(2026, 1, 1, 0, 0), 1)

    def test_bad_step(self):
        s = datetime(2026, 1, 1, 0, 0)
        for bad in ["*/0 * * * *", "*/x * * * *"]:
            with self.assertRaises(ValueError):
                next_runs(bad, s, 1)

    def test_non_numeric_and_empty_tokens(self):
        s = datetime(2026, 1, 1, 0, 0)
        for bad in ["a * * * *", "1,,2 * * * *"]:
            with self.assertRaises(ValueError):
                next_runs(bad, s, 1)

    def test_non_string_expr(self):
        with self.assertRaises((ValueError, TypeError)):
            next_runs(None, datetime(2026, 1, 1, 0, 0), 1)

    def test_count_below_one(self):
        with self.assertRaises(ValueError):
            next_runs("* * * * *", datetime(2026, 1, 1, 0, 0), 0)

    def test_unsatisfiable(self):
        with self.assertRaises(ValueError):
            next_runs("0 0 31 2 *", datetime(2026, 1, 1, 0, 0), 1)


class TestIterator(unittest.TestCase):
    def test_iter_generator(self):
        c = parse("* * * * *")
        s = datetime(2026, 1, 1, 0, 0)
        it = c.iter(s)
        first = next(it)
        self.assertEqual(first, d(2026, 1, 1, 0, 1))
        second = next(it)
        self.assertEqual(second, d(2026, 1, 1, 0, 2))

    def test_parse_returns_cronexpr(self):
        self.assertIsInstance(parse("* * * * *"), CronExpr)


if __name__ == "__main__":
    unittest.main()
