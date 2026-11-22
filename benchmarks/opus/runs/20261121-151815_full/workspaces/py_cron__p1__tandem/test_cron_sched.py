"""Tests for cron_sched."""

import unittest
from datetime import datetime, timezone

from cron_sched import CronExpr, next_runs, parse


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


class TestBasicParsing(unittest.TestCase):
    def test_parse_returns_cron_expr(self):
        obj = parse("* * * * *")
        self.assertIsInstance(obj, CronExpr)

    def test_parse_stores_fields(self):
        obj = parse("5 10 15 6 3")
        self.assertEqual(obj.minutes, [5])
        self.assertEqual(obj.hours, [10])
        self.assertEqual(obj.days_of_month, [15])
        self.assertEqual(obj.months, [6])
        self.assertEqual(obj.days_of_week, [3])

    def test_star_expands_to_full_range(self):
        obj = parse("* * * * *")
        self.assertEqual(obj.minutes, list(range(60)))
        self.assertEqual(obj.hours, list(range(24)))
        self.assertEqual(obj.days_of_month, list(range(1, 32)))
        self.assertEqual(obj.months, list(range(1, 13)))
        self.assertEqual(obj.days_of_week, list(range(8)))


class TestSyntaxForms(unittest.TestCase):
    def test_single_number(self):
        obj = parse("30 12 * * *")
        self.assertEqual(obj.minutes, [30])
        self.assertEqual(obj.hours, [12])

    def test_range(self):
        obj = parse("0 9-17 * * *")
        self.assertEqual(obj.hours, list(range(9, 18)))

    def test_list(self):
        obj = parse("0 8,12,18 * * *")
        self.assertEqual(obj.hours, [8, 12, 18])

    def test_step_star(self):
        obj = parse("*/15 * * * *")
        self.assertEqual(obj.minutes, [0, 15, 30, 45])

    def test_step_range(self):
        obj = parse("5,10-20/5 1 * * *")
        self.assertEqual(obj.minutes, [5, 10, 15, 20])

    def test_list_of_ranges(self):
        obj = parse("0 9-11,14-16 * * *")
        self.assertEqual(obj.hours, [9, 10, 11, 14, 15, 16])


class TestNextRuns(unittest.TestCase):
    def test_every_15_minutes(self):
        result = next_runs("*/15 * * * *", utc(2026, 1, 1, 0, 0), 3)
        self.assertEqual(
            result,
            [utc(2026, 1, 1, 0, 15), utc(2026, 1, 1, 0, 30), utc(2026, 1, 1, 0, 45)],
        )

    def test_midnight_daily_year_rollover(self):
        result = next_runs("0 0 * * *", utc(2026, 12, 31, 12, 0), 2)
        self.assertEqual(result, [utc(2027, 1, 1), utc(2027, 1, 2)])

    def test_leap_day(self):
        result = next_runs("0 0 29 2 *", utc(2026, 1, 1), 2)
        self.assertEqual(result, [utc(2028, 2, 29), utc(2032, 2, 29)])

    def test_weekday_range(self):
        result = next_runs("30 9 * * 1-5", utc(2026, 11, 20, 10, 0), 2)
        self.assertEqual(
            result, [utc(2026, 11, 23, 9, 30), utc(2026, 11, 24, 9, 30)]
        )

    def test_dow_seven_is_sunday(self):
        result = next_runs("0 0 * * 7", utc(2026, 11, 21), 1)
        self.assertEqual(result, [utc(2026, 11, 22)])

    def test_dow_zero_is_sunday(self):
        result = next_runs("0 12 1 * 0", utc(2026, 11, 1, 13, 0), 3)
        self.assertEqual(
            result,
            [utc(2026, 11, 8, 12), utc(2026, 11, 15, 12), utc(2026, 11, 22, 12)],
        )

    def test_default_count_is_five(self):
        result = next_runs("* * * * *", utc(2026, 1, 1))
        self.assertEqual(len(result), 5)

    def test_results_are_aware_utc(self):
        result = next_runs("* * * * *", utc(2026, 1, 1), 1)
        self.assertEqual(result[0].tzinfo, timezone.utc)
        self.assertEqual(result[0].second, 0)
        self.assertEqual(result[0].microsecond, 0)

    def test_strictly_after_start(self):
        result = next_runs("* * * * *", utc(2026, 1, 1, 0, 0), 1)
        self.assertGreater(result[0], utc(2026, 1, 1, 0, 0))

    def test_naive_start_treated_as_utc(self):
        naive = datetime(2026, 1, 1, 0, 0)
        result = next_runs("0 0 * * *", naive, 1)
        self.assertEqual(result, [utc(2026, 1, 2, 0, 0)])


class TestDomDowOrRule(unittest.TestCase):
    def test_both_restricted_uses_or(self):
        # DOM=15 OR DOW=Monday. 2026-01-01 is a Thursday.
        # Matches: Jan 5 (Mon), Jan 12 (Mon), Jan 15 (DOM, a Thursday).
        result = next_runs("0 0 15 * 1", utc(2026, 1, 1), 3)
        self.assertEqual(result, [utc(2026, 1, 5), utc(2026, 1, 12), utc(2026, 1, 15)])

    def test_dom_only_restricted(self):
        # Only DOM restricted: only DOM matters.
        result = next_runs("0 0 15 * *", utc(2026, 1, 1), 1)
        self.assertEqual(result, [utc(2026, 1, 15)])

    def test_dow_only_restricted(self):
        # Only DOW restricted: only DOW matters.
        result = next_runs("0 0 * * 1", utc(2026, 1, 1), 1)
        self.assertEqual(result, [utc(2026, 1, 5)])


class TestValueErrors(unittest.TestCase):
    def test_empty_expression(self):
        with self.assertRaises(ValueError):
            next_runs("", utc(2026, 1, 1))

    def test_wrong_field_count_four(self):
        with self.assertRaises(ValueError):
            next_runs("* * * *", utc(2026, 1, 1))

    def test_wrong_field_count_six(self):
        with self.assertRaises(ValueError):
            next_runs("* * * * * *", utc(2026, 1, 1))

    def test_minute_out_of_range(self):
        with self.assertRaises(ValueError):
            next_runs("60 * * * *", utc(2026, 1, 1))

    def test_hour_out_of_range(self):
        with self.assertRaises(ValueError):
            next_runs("* 24 * * *", utc(2026, 1, 1))

    def test_dom_zero(self):
        with self.assertRaises(ValueError):
            next_runs("* * 0 * *", utc(2026, 1, 1))

    def test_month_out_of_range(self):
        with self.assertRaises(ValueError):
            next_runs("* * * 13 *", utc(2026, 1, 1))

    def test_dow_out_of_range(self):
        with self.assertRaises(ValueError):
            next_runs("* * * * 8", utc(2026, 1, 1))

    def test_range_a_gt_b(self):
        with self.assertRaises(ValueError):
            next_runs("5-1 * * * *", utc(2026, 1, 1))

    def test_step_zero(self):
        with self.assertRaises(ValueError):
            next_runs("*/0 * * * *", utc(2026, 1, 1))

    def test_non_numeric(self):
        with self.assertRaises(ValueError):
            next_runs("a * * * *", utc(2026, 1, 1))

    def test_empty_list_item(self):
        with self.assertRaises(ValueError):
            next_runs("1,,2 * * * *", utc(2026, 1, 1))

    def test_impossible_date(self):
        with self.assertRaises(ValueError):
            next_runs("0 0 30 2 *", utc(2026, 1, 1))

    def test_non_string_expr(self):
        with self.assertRaises(ValueError):
            next_runs(None, utc(2026, 1, 1))

    def test_count_zero(self):
        with self.assertRaises(ValueError):
            next_runs("* * * * *", utc(2026, 1, 1), 0)

    def test_count_non_int(self):
        with self.assertRaises(ValueError):
            next_runs("* * * * *", utc(2026, 1, 1), "5")


if __name__ == "__main__":
    unittest.main()
