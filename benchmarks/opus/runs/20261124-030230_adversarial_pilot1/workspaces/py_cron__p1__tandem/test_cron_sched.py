"""Unit tests for cron_sched."""

import unittest
from datetime import datetime, timedelta, timezone

from cron_sched import parse, next_runs

U = timezone.utc


def d(*a):
    return datetime(*a, tzinfo=U)


class TestParse(unittest.TestCase):
    def test_parse_basic_sets(self):
        spec = parse("* * * * *")
        self.assertEqual(spec.minutes, set(range(60)))
        self.assertEqual(spec.hours, set(range(24)))
        self.assertEqual(spec.days, set(range(1, 32)))
        self.assertEqual(spec.months, set(range(1, 13)))
        self.assertEqual(spec.weekdays, set(range(7)))

    def test_parse_ranges_and_lists(self):
        spec = parse("1-3,10 * * * 7")
        self.assertEqual(spec.minutes, {1, 2, 3, 10})
        self.assertEqual(spec.weekdays, {0})

    def test_parse_step(self):
        spec = parse("*/15 * * * *")
        self.assertEqual(spec.minutes, {0, 15, 30, 45})

    def test_parse_range_step(self):
        spec = parse("0 9-17/4 * * *")
        self.assertEqual(spec.hours, {9, 13, 17})

    def test_parse_weekday_seven_normalized(self):
        spec = parse("* * * * 7")
        self.assertEqual(spec.weekdays, {0})


class TestNextRuns(unittest.TestCase):
    def test_every_minute(self):
        self.assertEqual(
            next_runs("* * * * *", d(2026, 1, 1, 0, 0), 3),
            [d(2026, 1, 1, 0, 1), d(2026, 1, 1, 0, 2), d(2026, 1, 1, 0, 3)],
        )

    def test_step_minutes(self):
        self.assertEqual(
            next_runs("*/15 * * * *", datetime(2026, 1, 1, 0, 7, 30), 3),
            [d(2026, 1, 1, 0, 15), d(2026, 1, 1, 0, 30), d(2026, 1, 1, 0, 45)],
        )

    def test_hour_range_step(self):
        self.assertEqual(
            next_runs("0 9-17/4 * * *", d(2026, 1, 1, 0, 0), 4),
            [d(2026, 1, 1, 9, 0), d(2026, 1, 1, 13, 0), d(2026, 1, 1, 17, 0), d(2026, 1, 2, 9, 0)],
        )

    def test_leap_day(self):
        self.assertEqual(
            next_runs("30 2 29 2 *", d(2026, 1, 1, 0, 0), 1),
            [d(2028, 2, 29, 2, 30)],
        )

    def test_weekday_sunday_zero(self):
        self.assertEqual(
            next_runs("0 0 * * 0", d(2026, 11, 24, 0, 0), 2),
            [d(2026, 11, 29), d(2026, 12, 6)],
        )

    def test_weekday_sunday_seven(self):
        self.assertEqual(
            next_runs("0 0 * * 7", d(2026, 11, 24, 0, 0), 1),
            [d(2026, 11, 29)],
        )

    def test_dom_dow_or_semantics(self):
        self.assertEqual(
            next_runs("0 0 1 * 1", d(2026, 11, 24, 0, 0), 3),
            [d(2026, 11, 30), d(2026, 12, 1), d(2026, 12, 7)],
        )

    def test_multiple_months(self):
        self.assertEqual(
            next_runs("5,10 0 1 1,6 *", d(2026, 1, 1, 0, 5), 3),
            [d(2026, 1, 1, 0, 10), d(2026, 6, 1, 0, 5), d(2026, 6, 1, 0, 10)],
        )

    def test_year_boundary(self):
        self.assertEqual(
            next_runs("0 0 1 1 *", d(2026, 12, 31, 23, 59), 1),
            [d(2027, 1, 1)],
        )

    def test_aware_start_converted_to_utc(self):
        r = next_runs("0 12 * * *", datetime(2026, 1, 1, 11, 0, tzinfo=timezone(timedelta(hours=2))), 1)
        self.assertEqual(r, [d(2026, 1, 1, 12, 0)])
        self.assertIsNotNone(r[0].tzinfo)
        self.assertEqual(r[0].utcoffset(), timedelta(0))

    def test_default_count_and_zero(self):
        self.assertEqual(len(next_runs("* * * * *", d(2026, 1, 1))), 5)
        self.assertEqual(next_runs("* * * * *", d(2026, 1, 1), 0), [])

    def test_results_are_utc_and_strictly_after(self):
        start = d(2026, 1, 1, 0, 0)
        r = next_runs("* * * * *", start, 3)
        for dt in r:
            self.assertEqual(dt.tzinfo, U)
            self.assertGreater(dt, start)
            self.assertEqual(dt.second, 0)
            self.assertEqual(dt.microsecond, 0)


class TestErrors(unittest.TestCase):
    def test_bad_field_count(self):
        for bad in ("* * * *", "* * * * * *"):
            with self.assertRaises(ValueError):
                next_runs(bad, d(2026, 1, 1), 1)

    def test_out_of_range(self):
        for bad in ("60 * * * *", "* 24 * * *", "* * 0 * *", "* * 32 * *",
                   "* * * 13 *", "* * * * 8"):
            with self.assertRaises(ValueError):
                next_runs(bad, d(2026, 1, 1), 1)

    def test_bad_range_and_step(self):
        for bad in ("5-1 * * * *", "*/0 * * * *", "*/x * * * *", "1- * * * *",
                   "-1 * * * *", "1,,2 * * * *", "a * * * *"):
            with self.assertRaises(ValueError):
                next_runs(bad, d(2026, 1, 1), 1)

    def test_empty_and_non_string(self):
        for bad in ("", None):
            with self.assertRaises(ValueError):
                next_runs(bad, d(2026, 1, 1), 1)

    def test_never_matches(self):
        for bad in ("0 0 30 2 *", "0 0 31 4,6 *"):
            with self.assertRaises(ValueError):
                next_runs(bad, d(2026, 1, 1), 1)

    def test_bad_count(self):
        for c in (-1, 1.5):
            with self.assertRaises(ValueError):
                next_runs("* * * * *", d(2026, 1, 1), c)


if __name__ == "__main__":
    unittest.main()
