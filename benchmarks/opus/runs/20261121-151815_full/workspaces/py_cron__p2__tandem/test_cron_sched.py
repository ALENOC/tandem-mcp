"""Unit tests for cron_sched."""

import unittest
from datetime import datetime, timedelta, timezone

from cron_sched import CronExpr, next_runs, parse

UTC = timezone.utc


def u(*a):
    return datetime(*a, tzinfo=UTC)


class ParseTests(unittest.TestCase):
    def test_parse_star(self):
        ce = parse('* * * * *')
        self.assertEqual(ce.minute, set(range(0, 60)))
        self.assertEqual(ce.hour, set(range(0, 24)))
        self.assertEqual(ce.dom, set(range(1, 32)))
        self.assertEqual(ce.month, set(range(1, 13)))
        self.assertEqual(ce.dow, set(range(0, 7)))

    def test_parse_single(self):
        ce = parse('5 4 3 2 1')
        self.assertEqual(ce.minute, {5})
        self.assertEqual(ce.hour, {4})
        self.assertEqual(ce.dom, {3})
        self.assertEqual(ce.month, {2})
        self.assertEqual(ce.dow, {1})

    def test_parse_range(self):
        ce = parse('1-5 * * * *')
        self.assertEqual(ce.minute, {1, 2, 3, 4, 5})

    def test_parse_list(self):
        ce = parse('1,15,30 * * * *')
        self.assertEqual(ce.minute, {1, 15, 30})

    def test_parse_step_star(self):
        ce = parse('*/15 * * * *')
        self.assertEqual(ce.minute, {0, 15, 30, 45})

    def test_parse_range_step(self):
        ce = parse('5 0-10/5 * * *')
        self.assertEqual(ce.hour, {0, 5, 10})

    def test_parse_list_mixed(self):
        ce = parse('1,3-5,*/20 * * * *')
        self.assertEqual(ce.minute, {0, 1, 3, 4, 5, 20, 40})

    def test_parse_returns_cronexpr(self):
        ce = parse('0 0 * * *')
        self.assertIsInstance(ce, CronExpr)


class NextRunsTests(unittest.TestCase):
    def test_every_fifteen_minutes(self):
        res = next_runs('*/15 * * * *', u(2024, 1, 1, 0, 0), 3)
        self.assertEqual(res, [u(2024, 1, 1, 0, 15), u(2024, 1, 1, 0, 30), u(2024, 1, 1, 0, 45)])

    def test_leap_day(self):
        res = next_runs('0 0 29 2 *', u(2023, 1, 1), 2)
        self.assertEqual(res, [u(2024, 2, 29), u(2028, 2, 29)])

    def test_weekday_range(self):
        res = next_runs('30 9 * * 1-5', u(2024, 1, 5, 10, 0), 2)
        self.assertEqual(res, [u(2024, 1, 8, 9, 30), u(2024, 1, 9, 9, 30)])

    def test_dom_dow_or_rule(self):
        res = next_runs('0 0 13 * 5', u(2024, 1, 1), 3)
        self.assertEqual(res, [u(2024, 1, 5), u(2024, 1, 12), u(2024, 1, 13)])

    def test_hour_range_step(self):
        res = next_runs('5 0-10/5 * * *', u(2024, 12, 31, 23, 59), 3)
        self.assertEqual(res, [u(2025, 1, 1, 0, 5), u(2025, 1, 1, 5, 5), u(2025, 1, 1, 10, 5)])

    def test_list_minutes(self):
        res = next_runs('1,2,3 * * * *', u(2024, 1, 1, 0, 2), 2)
        self.assertEqual(res, [u(2024, 1, 1, 0, 3), u(2024, 1, 1, 1, 1)])

    def test_default_count_five(self):
        res = next_runs('* * * * *', u(2024, 1, 1))
        self.assertEqual(len(res), 5)

    def test_month_rollover(self):
        res = next_runs('0 12 31 12 *', u(2024, 1, 1), 2)
        self.assertEqual(res, [u(2024, 12, 31, 12, 0), u(2025, 12, 31, 12, 0)])

    def test_year_rollover(self):
        res = next_runs('0 0 1 1 *', u(2024, 6, 15), 2)
        self.assertEqual(res, [u(2025, 1, 1, 0, 0), u(2026, 1, 1, 0, 0)])

    def test_strictly_after_start(self):
        res = next_runs('0 0 * * *', u(2024, 1, 1, 0, 0), 1)
        self.assertEqual(res, [u(2024, 1, 2, 0, 0)])

    def test_naive_treated_as_utc(self):
        res = next_runs('0 0 * * *', datetime(2024, 1, 1, 0, 0), 1)
        self.assertEqual(res, [u(2024, 1, 2, 0, 0)])

    def test_aware_converted_to_utc(self):
        tz = timezone(timedelta(hours=2))
        start = datetime(2024, 1, 1, 2, 0, tzinfo=tz)  # == 2024-01-01 00:00 UTC
        res = next_runs('0 0 * * *', start, 1)
        self.assertEqual(res, [u(2024, 1, 2, 0, 0)])

    def test_result_tz_and_fields(self):
        res = next_runs('0 0 * * *', u(2024, 1, 1), 1)
        self.assertEqual(res[0].tzinfo, UTC)
        self.assertEqual(res[0].second, 0)
        self.assertEqual(res[0].microsecond, 0)

    def test_ascending(self):
        res = next_runs('*/7 * * * *', u(2024, 1, 1), 10)
        self.assertEqual(res, sorted(res))
        self.assertEqual(len(res), 10)


class ErrorTests(unittest.TestCase):
    def test_wrong_field_count(self):
        with self.assertRaises(ValueError):
            next_runs('* * * *', u(2024, 1, 1))

    def test_minute_out_of_range(self):
        with self.assertRaises(ValueError):
            next_runs('60 * * * *', u(2024, 1, 1))

    def test_hour_out_of_range(self):
        with self.assertRaises(ValueError):
            next_runs('* 24 * * *', u(2024, 1, 1))

    def test_dom_out_of_range(self):
        with self.assertRaises(ValueError):
            next_runs('* * 0 * *', u(2024, 1, 1))

    def test_month_out_of_range(self):
        with self.assertRaises(ValueError):
            next_runs('* * * 13 *', u(2024, 1, 1))

    def test_dow_out_of_range(self):
        with self.assertRaises(ValueError):
            next_runs('* * * * 7', u(2024, 1, 1))

    def test_range_start_gt_end(self):
        with self.assertRaises(ValueError):
            next_runs('5-1 * * * *', u(2024, 1, 1))

    def test_step_zero(self):
        with self.assertRaises(ValueError):
            next_runs('*/0 * * * *', u(2024, 1, 1))

    def test_non_numeric(self):
        with self.assertRaises(ValueError):
            next_runs('a * * * *', u(2024, 1, 1))

    def test_empty_list_item(self):
        with self.assertRaises(ValueError):
            next_runs('1,,2 * * * *', u(2024, 1, 1))

    def test_never_matches(self):
        with self.assertRaises(ValueError):
            next_runs('0 0 31 2 *', u(2024, 1, 1))

    def test_empty_string(self):
        with self.assertRaises(ValueError):
            next_runs('', u(2024, 1, 1))

    def test_non_string_expr(self):
        with self.assertRaises(ValueError):
            next_runs(None, u(2024, 1, 1))

    def test_count_zero(self):
        with self.assertRaises(ValueError):
            next_runs('* * * * *', u(2024, 1, 1), 0)

    def test_count_negative(self):
        with self.assertRaises(ValueError):
            next_runs('* * * * *', u(2024, 1, 1), -1)


if __name__ == '__main__':
    unittest.main()
