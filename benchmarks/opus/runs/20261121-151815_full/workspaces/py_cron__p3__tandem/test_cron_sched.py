"""Unit tests for cron_sched."""

import unittest
from datetime import datetime, timezone

from cron_sched import parse, next_runs

UTC = timezone.utc


def dt(*args):
    return datetime(*args, tzinfo=UTC)


class ParseTests(unittest.TestCase):
    def test_parse_star(self):
        spec = parse("* * * * *")
        self.assertEqual(spec.minutes, set(range(0, 60)))
        self.assertEqual(spec.hours, set(range(0, 24)))
        self.assertEqual(spec.dom, set(range(1, 32)))
        self.assertEqual(spec.months, set(range(1, 13)))
        self.assertEqual(spec.dow, set(range(0, 7)))

    def test_parse_number(self):
        spec = parse("5 3 1 1 1")
        self.assertEqual(spec.minutes, {5})
        self.assertEqual(spec.hours, {3})
        self.assertEqual(spec.dom, {1})
        self.assertEqual(spec.months, {1})
        self.assertEqual(spec.dow, {1})

    def test_parse_range(self):
        spec = parse("0 9-17 * * *")
        self.assertEqual(spec.hours, set(range(9, 18)))

    def test_parse_list(self):
        spec = parse("0 0 1,15 * *")
        self.assertEqual(spec.dom, {1, 15})

    def test_parse_step(self):
        spec = parse("*/15 * * * *")
        self.assertEqual(spec.minutes, {0, 15, 30, 45})

    def test_parse_range_step(self):
        spec = parse("0 9-17/4 * * *")
        self.assertEqual(spec.hours, {9, 13, 17})

    def test_parse_dow_seven_normalized(self):
        spec = parse("0 0 * * 7")
        self.assertEqual(spec.dow, {0})

    def test_parse_mixed_list(self):
        spec = parse("1,5,10-12 * * * *")
        self.assertEqual(spec.minutes, {1, 5, 10, 11, 12})


class NextRunsTests(unittest.TestCase):
    def test_every_minute(self):
        start = dt(2024, 1, 1, 0, 0)
        result = next_runs("* * * * *", start, 3)
        self.assertEqual(
            result,
            [dt(2024, 1, 1, 0, 1), dt(2024, 1, 1, 0, 2), dt(2024, 1, 1, 0, 3)],
        )

    def test_step_minutes(self):
        start = dt(2024, 1, 1, 0, 0)
        result = next_runs("*/15 * * * *", start, 2)
        self.assertEqual(result, [dt(2024, 1, 1, 0, 15), dt(2024, 1, 1, 0, 30)])

    def test_range_step_hours(self):
        start = dt(2024, 1, 1, 0, 0)
        result = next_runs("0 9-17/4 * * *", start, 3)
        self.assertEqual(
            result,
            [dt(2024, 1, 1, 9, 0), dt(2024, 1, 1, 13, 0), dt(2024, 1, 1, 17, 0)],
        )

    def test_list_days(self):
        start = dt(2024, 1, 1, 0, 0)
        result = next_runs("30 2 1,15 * *", start, 2)
        self.assertEqual(result, [dt(2024, 1, 1, 2, 30), dt(2024, 1, 15, 2, 30)])

    def test_leap_day(self):
        start = dt(2024, 1, 1, 0, 0)
        result = next_runs("0 0 29 2 *", start, 2)
        self.assertEqual(result, [dt(2024, 2, 29), dt(2028, 2, 29)])

    def test_dow_seven_sunday(self):
        start = dt(2024, 1, 1, 0, 0)
        result = next_runs("0 0 * * 7", start, 1)
        self.assertEqual(result, [dt(2024, 1, 7)])

    def test_dom_dow_or_rule(self):
        # dom=13 (restricted) and dow=5 (Friday, restricted) -> OR rule.
        start = dt(2024, 1, 1, 0, 0)
        result = next_runs("0 0 13 * 5", start, 3)
        self.assertEqual(
            result,
            [dt(2024, 1, 5), dt(2024, 1, 12), dt(2024, 1, 13)],
        )

    def test_strictly_after_with_seconds(self):
        start = dt(2024, 1, 1, 0, 0, 30)
        result = next_runs("0 0 * * *", start, 1)
        self.assertEqual(result, [dt(2024, 1, 2)])

    def test_specific_datetime(self):
        start = dt(2024, 1, 1, 0, 0)
        result = next_runs("59 23 31 12 *", start, 1)
        self.assertEqual(result, [dt(2024, 12, 31, 23, 59)])

    def test_default_count(self):
        start = dt(2024, 1, 1, 0, 0)
        result = next_runs("0 0 1 1 *", start)
        self.assertEqual(len(result), 5)

    def test_naive_start_treated_as_utc(self):
        naive = datetime(2024, 1, 1, 0, 0)
        result = next_runs("* * * * *", naive, 1)
        self.assertEqual(result, [dt(2024, 1, 1, 0, 1)])

    def test_aware_start_converted_to_utc(self):
        from datetime import timedelta
        tz_plus2 = timezone(timedelta(hours=2))
        aware = datetime(2024, 1, 1, 2, 0, tzinfo=tz_plus2)  # 00:00 UTC
        result = next_runs("* * * * *", aware, 1)
        self.assertEqual(result, [dt(2024, 1, 1, 0, 1)])

    def test_results_are_utc_and_zeroed(self):
        start = dt(2024, 1, 1, 0, 0)
        result = next_runs("* * * * *", start, 2)
        for r in result:
            self.assertEqual(r.tzinfo, UTC)
            self.assertEqual(r.second, 0)
            self.assertEqual(r.microsecond, 0)


class InvalidExpressionTests(unittest.TestCase):
    def test_empty_string(self):
        with self.assertRaises(ValueError):
            next_runs("", dt(2024, 1, 1))

    def test_too_few_fields(self):
        with self.assertRaises(ValueError):
            next_runs("* * * *", dt(2024, 1, 1))

    def test_too_many_fields(self):
        with self.assertRaises(ValueError):
            next_runs("* * * * * *", dt(2024, 1, 1))

    def test_minute_out_of_range(self):
        with self.assertRaises(ValueError):
            next_runs("60 * * * *", dt(2024, 1, 1))

    def test_hour_out_of_range(self):
        with self.assertRaises(ValueError):
            next_runs("* 24 * * *", dt(2024, 1, 1))

    def test_dom_zero(self):
        with self.assertRaises(ValueError):
            next_runs("* * 0 * *", dt(2024, 1, 1))

    def test_month_out_of_range(self):
        with self.assertRaises(ValueError):
            next_runs("* * * 13 *", dt(2024, 1, 1))

    def test_dow_out_of_range(self):
        with self.assertRaises(ValueError):
            next_runs("* * * * 8", dt(2024, 1, 1))

    def test_range_reversed(self):
        with self.assertRaises(ValueError):
            next_runs("5-1 * * * *", dt(2024, 1, 1))

    def test_step_zero(self):
        with self.assertRaises(ValueError):
            next_runs("*/0 * * * *", dt(2024, 1, 1))

    def test_non_numeric(self):
        with self.assertRaises(ValueError):
            next_runs("a * * * *", dt(2024, 1, 1))

    def test_empty_list_item(self):
        with self.assertRaises(ValueError):
            next_runs("1,,2 * * * *", dt(2024, 1, 1))

    def test_non_numeric_step(self):
        with self.assertRaises(ValueError):
            next_runs("*/x * * * *", dt(2024, 1, 1))

    def test_never_matches(self):
        with self.assertRaises(ValueError):
            next_runs("0 0 31 2 *", dt(2024, 1, 1))

    def test_none_expr(self):
        with self.assertRaises(ValueError):
            next_runs(None, dt(2024, 1, 1))

    def test_non_string_expr(self):
        with self.assertRaises(ValueError):
            next_runs(123, dt(2024, 1, 1))

    def test_count_zero(self):
        with self.assertRaises(ValueError):
            next_runs("* * * * *", dt(2024, 1, 1), 0)

    def test_count_negative(self):
        with self.assertRaises(ValueError):
            next_runs("* * * * *", dt(2024, 1, 1), -1)


if __name__ == "__main__":
    unittest.main()
