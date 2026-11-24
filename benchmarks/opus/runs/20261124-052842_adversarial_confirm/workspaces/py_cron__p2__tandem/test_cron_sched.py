"""Unit tests for cron_sched (5-field cron parser and next_runs iterator)."""

import unittest
from datetime import datetime, timezone, timedelta

from cron_sched import parse, next_runs, CronExpr

UTC = timezone.utc


def naive(year, month, day, hour=0, minute=0, second=0):
    return datetime(year, month, day, hour, minute, second)


class ParseTests(unittest.TestCase):

    def test_parse_star_expands_to_full_set(self):
        e = parse("* * * * *")
        self.assertEqual(e.minutes, set(range(0, 60)))
        self.assertEqual(e.hours, set(range(0, 24)))
        self.assertEqual(e.days, set(range(1, 32)))
        self.assertEqual(e.months, set(range(1, 13)))
        self.assertEqual(e.weekdays, set(range(0, 7)))

    def test_parse_single_values(self):
        e = parse("5 3 12 6 2")
        self.assertEqual(e.minutes, {5})
        self.assertEqual(e.hours, {3})
        self.assertEqual(e.days, {12})
        self.assertEqual(e.months, {6})
        self.assertEqual(e.weekdays, {2})

    def test_parse_range(self):
        e = parse("1-5 * * * *")
        self.assertEqual(e.minutes, {1, 2, 3, 4, 5})

    def test_parse_list(self):
        e = parse("1,15 * * * *")
        self.assertEqual(e.minutes, {1, 15})

    def test_parse_step_star(self):
        e = parse("*/15 * * * *")
        self.assertEqual(e.minutes, {0, 15, 30, 45})

    def test_parse_range_with_step(self):
        e = parse("0 9-17/4 * * *")
        self.assertEqual(e.hours, {9, 13, 17})

    def test_parse_weekday_seven_normalised_to_zero(self):
        e = parse("* * * * 7")
        self.assertEqual(e.weekdays, {0})

    def test_parse_returns_cronexpr(self):
        e = parse("0 0 * * *")
        self.assertIsInstance(e, CronExpr)


class NextRunsTests(unittest.TestCase):

    def test_every_minute(self):
        s = naive(2026, 1, 1, 0, 0, 30)
        res = next_runs("* * * * *", s, 3)
        self.assertEqual(
            res,
            [datetime(2026, 1, 1, 0, 1, tzinfo=UTC),
             datetime(2026, 1, 1, 0, 2, tzinfo=UTC),
             datetime(2026, 1, 1, 0, 3, tzinfo=UTC)])

    def test_strictly_after_and_aware_utc(self):
        s = datetime(2026, 1, 1, 0, 0, 30)
        res = next_runs("* * * * *", s, 1)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0], datetime(2026, 1, 1, 0, 1, tzinfo=UTC))
        self.assertIsNotNone(res[0].tzinfo)
        self.assertEqual(res[0].tzinfo, UTC)

    def test_default_count_is_five(self):
        s = naive(2026, 1, 1, 0, 0, 30)
        res = next_runs("* * * * *", s)
        self.assertEqual(len(res), 5)

    def test_step_minutes(self):
        res = next_runs("*/15 * * * *", naive(2026, 1, 1, 0, 0), 2)
        self.assertEqual(
            res,
            [datetime(2026, 1, 1, 0, 15, tzinfo=UTC),
             datetime(2026, 1, 1, 0, 30, tzinfo=UTC)])

    def test_range_with_step_hours(self):
        res = next_runs("0 9-17/4 * * *", naive(2026, 1, 1), 4)
        self.assertEqual(
            res,
            [datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
             datetime(2026, 1, 1, 13, 0, tzinfo=UTC),
             datetime(2026, 1, 1, 17, 0, tzinfo=UTC),
             datetime(2026, 1, 2, 9, 0, tzinfo=UTC)])

    def test_dom_list_across_months(self):
        res = next_runs("30 12 1,15 * *", naive(2026, 1, 15, 12, 30), 2)
        self.assertEqual(
            res,
            [datetime(2026, 2, 1, 12, 30, tzinfo=UTC),
             datetime(2026, 2, 15, 12, 30, tzinfo=UTC)])

    def test_weekday_seven_and_zero_both_sunday(self):
        s = naive(2026, 11, 24)  # a Tuesday
        self.assertEqual(
            next_runs("0 0 * * 7", s, 1),
            [datetime(2026, 11, 29, tzinfo=UTC)])
        self.assertEqual(
            next_runs("0 0 * * 0", s, 1),
            [datetime(2026, 11, 29, tzinfo=UTC)])

    def test_or_rule_dom_and_dow(self):
        # dom=13 and dow=5 (Friday): matches either the 13th or any Friday.
        res = next_runs("0 0 13 * 5", naive(2026, 11, 1), 3)
        self.assertEqual(
            res,
            [datetime(2026, 11, 6, tzinfo=UTC),
             datetime(2026, 11, 13, tzinfo=UTC),
             datetime(2026, 11, 20, tzinfo=UTC)])

    def test_leap_year_feb_29(self):
        res = next_runs("0 0 29 2 *", naive(2026, 1, 1), 2)
        self.assertEqual(
            res,
            [datetime(2028, 2, 29, tzinfo=UTC),
             datetime(2032, 2, 29, tzinfo=UTC)])

    def test_month_end_dec_31(self):
        res = next_runs("59 23 31 12 *", naive(2026, 12, 31, 23, 59), 1)
        self.assertEqual(
            res, [datetime(2027, 12, 31, 23, 59, tzinfo=UTC)])

    def test_aware_start_converted_to_utc(self):
        s = datetime(2026, 1, 1, 10, 0, tzinfo=timezone(timedelta(hours=2)))
        res = next_runs("0 12 * * *", s, 1)
        self.assertEqual(
            res, [datetime(2026, 1, 1, 12, 0, tzinfo=UTC)])

    def test_increasing_order(self):
        res = next_runs("* * * * *", naive(2026, 1, 1), 10)
        for a, b in zip(res, res[1:]):
            self.assertLess(a, b)


class ErrorTests(unittest.TestCase):

    def test_wrong_field_count(self):
        with self.assertRaises(ValueError):
            next_runs("* * * *", naive(2026, 1, 1), 1)
        with self.assertRaises(ValueError):
            next_runs("* * * * * *", naive(2026, 1, 1), 1)

    def test_out_of_range_values(self):
        for bad in ["60 * * * *", "* 24 * * *", "* * 0 * *",
                    "* * 32 * *", "* * * 13 *", "* * * * 8"]:
            with self.assertRaises(ValueError):
                next_runs(bad, naive(2026, 1, 1), 1)

    def test_bad_range_and_step(self):
        for bad in ["5-1 * * * *", "*/0 * * * *", "*/-1 * * * *"]:
            with self.assertRaises(ValueError):
                next_runs(bad, naive(2026, 1, 1), 1)

    def test_non_numeric_and_empty_tokens(self):
        for bad in ["a * * * *", "1,,2 * * * *", "1- * * * *", "*/x * * * *"]:
            with self.assertRaises(ValueError):
                next_runs(bad, naive(2026, 1, 1), 1)

    def test_impossible_dates_raise(self):
        for bad in ["0 0 30 2 *", "0 0 31 4 *"]:
            with self.assertRaises(ValueError):
                next_runs(bad, naive(2026, 1, 1), 1)

    def test_non_string_expression(self):
        for bad in [None, 5]:
            with self.assertRaises(ValueError):
                next_runs(bad, naive(2026, 1, 1), 1)

    def test_empty_expression(self):
        with self.assertRaises(ValueError):
            next_runs("", naive(2026, 1, 1), 1)

    def test_count_zero(self):
        with self.assertRaises(ValueError):
            next_runs("* * * * *", naive(2026, 1, 1), 0)


if __name__ == "__main__":
    unittest.main()
