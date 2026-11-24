import unittest
from datetime import datetime, timedelta, timezone

from cron_sched import CronExpr, next_runs, parse

UTC = timezone.utc


def dt(*args):
    return datetime(*args, tzinfo=UTC)


class TestParsing(unittest.TestCase):
    def test_star_expands_full_range(self):
        c = parse("* * * * *")
        self.assertEqual(c.minutes, list(range(60)))
        self.assertEqual(c.hours, list(range(24)))
        self.assertEqual(c.days, set(range(1, 32)))
        self.assertEqual(c.months, set(range(1, 13)))
        self.assertEqual(c.weekdays, set(range(7)))

    def test_list_range_and_steps(self):
        c = parse("1,5,10 2-4 */10 1-12/3 *")
        self.assertEqual(c.minutes, [1, 5, 10])
        self.assertEqual(c.hours, [2, 3, 4])
        self.assertEqual(c.days, {1, 11, 21, 31})
        self.assertEqual(c.months, {1, 4, 7, 10})

    def test_mixed_list_with_ranges_and_steps(self):
        c = parse("0-10/5,30,50-52 * * * *")
        self.assertEqual(c.minutes, [0, 5, 10, 30, 50, 51, 52])

    def test_weekday_seven_is_sunday(self):
        self.assertEqual(parse("0 0 * * 7").weekdays, {0})
        self.assertEqual(parse("0 0 * * 5-7").weekdays, {0, 5, 6})

    def test_extra_whitespace_is_accepted(self):
        self.assertEqual(parse("  0   12 * *  1 ").hours, [12])

    def test_invalid_expressions_raise_value_error(self):
        invalid = [
            "",
            "* * * *",
            "* * * * * *",
            "60 * * * *",
            "* 24 * * *",
            "* * 0 * *",
            "* * 32 * *",
            "* * * 0 *",
            "* * * 13 *",
            "* * * * 8",
            "5-1 * * * *",
            "*/0 * * * *",
            "*/ * * * *",
            "/5 * * * *",
            "5/10 * * * *",
            "a * * * *",
            "-1 * * * *",
            "1,,2 * * * *",
            "1, * * * *",
            "1-2-3 * * * *",
            "*/-1 * * * *",
            "1-5/x * * * *",
        ]
        for expr in invalid:
            with self.subTest(expr=expr):
                with self.assertRaises(ValueError):
                    next_runs(expr, dt(2024, 1, 1))

    def test_non_string_expression_raises_value_error(self):
        with self.assertRaises(ValueError):
            CronExpr(None)


class TestNextRuns(unittest.TestCase):
    def test_every_minute_strictly_after_start(self):
        runs = next_runs("* * * * *", dt(2024, 1, 1, 10, 0))
        self.assertEqual(runs, [dt(2024, 1, 1, 10, m) for m in range(1, 6)])

    def test_start_with_seconds_rounds_to_next_minute(self):
        runs = next_runs("* * * * *", dt(2024, 1, 1, 10, 0, 30), count=2)
        self.assertEqual(runs, [dt(2024, 1, 1, 10, 1), dt(2024, 1, 1, 10, 2)])

    def test_default_count_is_five(self):
        self.assertEqual(len(next_runs("*/15 * * * *", dt(2024, 1, 1))), 5)

    def test_step_minutes_crosses_hour(self):
        runs = next_runs("*/20 * * * *", dt(2024, 1, 1, 10, 41), count=4)
        self.assertEqual(runs, [
            dt(2024, 1, 1, 11, 0), dt(2024, 1, 1, 11, 20),
            dt(2024, 1, 1, 11, 40), dt(2024, 1, 1, 12, 0),
        ])

    def test_daily_at_fixed_time_crosses_year(self):
        runs = next_runs("30 9 * * *", dt(2024, 12, 30, 9, 30), count=3)
        self.assertEqual(runs, [
            dt(2024, 12, 31, 9, 30), dt(2025, 1, 1, 9, 30),
            dt(2025, 1, 2, 9, 30),
        ])

    def test_range_with_step_hours(self):
        runs = next_runs("0 8-18/4 * * *", dt(2024, 3, 1, 0, 0), count=4)
        self.assertEqual(runs, [
            dt(2024, 3, 1, 8), dt(2024, 3, 1, 12), dt(2024, 3, 1, 16),
            dt(2024, 3, 2, 8),
        ])

    def test_weekdays_only(self):
        # 2024-03-01 è venerdì
        runs = next_runs("0 9 * * 1-5", dt(2024, 3, 1, 10, 0), count=3)
        self.assertEqual(runs, [
            dt(2024, 3, 4, 9), dt(2024, 3, 5, 9), dt(2024, 3, 6, 9),
        ])
        for r in runs:
            self.assertLess(r.weekday(), 5)

    def test_sunday_as_zero_and_seven(self):
        a = next_runs("0 0 * * 0", dt(2024, 3, 1), count=3)
        b = next_runs("0 0 * * 7", dt(2024, 3, 1), count=3)
        self.assertEqual(a, b)
        self.assertEqual(a[0], dt(2024, 3, 3))
        self.assertTrue(all(r.weekday() == 6 for r in a))

    def test_day_of_month_skips_short_months(self):
        runs = next_runs("0 0 31 * *", dt(2024, 1, 31), count=3)
        self.assertEqual(runs, [
            dt(2024, 3, 31), dt(2024, 5, 31), dt(2024, 7, 31),
        ])

    def test_leap_day(self):
        runs = next_runs("0 0 29 2 *", dt(2024, 3, 1), count=2)
        self.assertEqual(runs, [dt(2028, 2, 29), dt(2032, 2, 29)])

    def test_dom_and_dow_use_or_semantics(self):
        # giorno 13 OPPURE venerdì, a marzo 2024
        runs = next_runs("0 0 13 3 5", dt(2024, 3, 1), count=5)
        self.assertEqual(runs, [
            dt(2024, 3, 8), dt(2024, 3, 13), dt(2024, 3, 15),
            dt(2024, 3, 22), dt(2024, 3, 29),
        ])

    def test_month_list(self):
        runs = next_runs("0 0 1 1,7 *", dt(2024, 2, 1), count=3)
        self.assertEqual(runs, [dt(2024, 7, 1), dt(2025, 1, 1), dt(2025, 7, 1)])

    def test_results_are_utc_aware_and_increasing(self):
        runs = next_runs("*/7 */5 * * *", dt(2024, 1, 1), count=50)
        self.assertEqual(len(runs), 50)
        for r in runs:
            self.assertEqual(r.utcoffset(), timedelta(0))
        self.assertEqual(runs, sorted(set(runs)))

    def test_naive_start_treated_as_utc(self):
        naive = next_runs("0 * * * *", datetime(2024, 1, 1, 10, 15), count=1)
        self.assertEqual(naive, [dt(2024, 1, 1, 11)])

    def test_aware_non_utc_start_is_converted(self):
        cet = timezone(timedelta(hours=1))
        start = datetime(2024, 1, 1, 10, 15, tzinfo=cet)  # 09:15 UTC
        self.assertEqual(next_runs("0 * * * *", start, count=1),
                         [dt(2024, 1, 1, 10)])

    def test_count_zero_and_invalid_count(self):
        self.assertEqual(next_runs("* * * * *", dt(2024, 1, 1), count=0), [])
        with self.assertRaises(ValueError):
            next_runs("* * * * *", dt(2024, 1, 1), count=-1)

    def test_impossible_date_raises_value_error(self):
        with self.assertRaises(ValueError):
            next_runs("0 0 30 2 *", dt(2024, 1, 1))
        with self.assertRaises(ValueError):
            next_runs("0 0 31 4,6,9,11 *", dt(2024, 1, 1))

    def test_accepts_precompiled_expression(self):
        c = parse("0 12 * * *")
        self.assertEqual(next_runs(c, dt(2024, 1, 1), count=1),
                         [dt(2024, 1, 1, 12)])


if __name__ == "__main__":
    unittest.main()
