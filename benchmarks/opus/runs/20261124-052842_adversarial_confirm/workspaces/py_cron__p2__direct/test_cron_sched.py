import unittest
from datetime import datetime, timedelta, timezone

from cron_sched import CronExpr, next_runs, parse

UTC = timezone.utc


def dt(y, mo, d, h=0, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=UTC)


class TestParse(unittest.TestCase):
    def test_star_expands_full_range(self):
        c = parse("* * * * *")
        self.assertEqual(c.minutes, frozenset(range(60)))
        self.assertEqual(c.hours, frozenset(range(24)))
        self.assertEqual(c.days, frozenset(range(1, 32)))
        self.assertEqual(c.months, frozenset(range(1, 13)))
        self.assertEqual(c.weekdays, frozenset(range(7)))

    def test_list_range_and_steps(self):
        c = parse("1,2,30 9-17 */10 1-12/3 1-5")
        self.assertEqual(c.minutes, {1, 2, 30})
        self.assertEqual(c.hours, set(range(9, 18)))
        self.assertEqual(c.days, {1, 11, 21, 31})
        self.assertEqual(c.months, {1, 4, 7, 10})
        self.assertEqual(c.weekdays, {1, 2, 3, 4, 5})

    def test_mixed_list_with_ranges_and_steps(self):
        c = parse("0-10/5,30,50-52 * * * *")
        self.assertEqual(c.minutes, {0, 5, 10, 30, 50, 51, 52})

    def test_sunday_as_7(self):
        self.assertEqual(parse("0 0 * * 7").weekdays, {0})
        self.assertEqual(parse("0 0 * * 5-7").weekdays, {0, 5, 6})

    def test_invalid_expressions_raise(self):
        bad = [
            "", "* * * *", "* * * * * *", "60 * * * *", "* 24 * * *",
            "* * 0 * *", "* * 32 * *", "* * * 0 *", "* * * 13 *",
            "* * * * 8", "a * * * *", "*/0 * * * *", "5-1 * * * *",
            "1,,2 * * * *", "1, * * * *", "-1 * * * *", "1-2-3 * * * *",
            "*/ * * * *", "*/x * * * *", "1.5 * * * *", "5/15 * * * *",
            "** * * * *", "*-5 * * * *", "+5 * * * *",
        ]
        for expr in bad:
            with self.subTest(expr=expr):
                with self.assertRaises(ValueError):
                    parse(expr)
                with self.assertRaises(ValueError):
                    next_runs(expr, dt(2026, 1, 1))

    def test_non_string_raises_value_error(self):
        with self.assertRaises(ValueError):
            parse(None)
        with self.assertRaises(ValueError):
            next_runs(123, dt(2026, 1, 1))


class TestNextRuns(unittest.TestCase):
    def test_every_minute_strictly_after_start(self):
        runs = next_runs("* * * * *", dt(2026, 1, 1, 10, 0), 3)
        self.assertEqual(runs, [dt(2026, 1, 1, 10, 1), dt(2026, 1, 1, 10, 2),
                                dt(2026, 1, 1, 10, 3)])

    def test_seconds_are_truncated(self):
        start = datetime(2026, 1, 1, 10, 0, 59, 999999, tzinfo=UTC)
        self.assertEqual(next_runs("* * * * *", start, 1),
                         [dt(2026, 1, 1, 10, 1)])

    def test_default_count_is_five(self):
        runs = next_runs("*/15 * * * *", dt(2026, 1, 1, 0, 7))
        self.assertEqual(runs, [dt(2026, 1, 1, 0, 15), dt(2026, 1, 1, 0, 30),
                                dt(2026, 1, 1, 0, 45), dt(2026, 1, 1, 1, 0),
                                dt(2026, 1, 1, 1, 15)])

    def test_rollover_year(self):
        runs = next_runs("0 0 1 1 *", dt(2026, 6, 15), 2)
        self.assertEqual(runs, [dt(2027, 1, 1), dt(2028, 1, 1)])

    def test_rollover_hour_day_month(self):
        runs = next_runs("30 23 * * *", dt(2026, 1, 31, 23, 30), 2)
        self.assertEqual(runs, [dt(2026, 2, 1, 23, 30), dt(2026, 2, 2, 23, 30)])

    def test_weekdays_business_hours(self):
        # 2026-11-27 è venerdì
        runs = next_runs("0 9 * * 1-5", dt(2026, 11, 27, 9, 0), 2)
        self.assertEqual(runs, [dt(2026, 11, 30, 9), dt(2026, 12, 1, 9)])

    def test_dom_and_dow_are_ored_when_both_restricted(self):
        # giorno 13 OPPURE venerdì; 2026-11-13 è venerdì
        runs = next_runs("0 0 13 * 5", dt(2026, 11, 10), 4)
        self.assertEqual(runs, [dt(2026, 11, 13), dt(2026, 11, 20),
                                dt(2026, 11, 27), dt(2026, 12, 4)])
        runs = next_runs("0 0 13 * 5", dt(2026, 12, 5), 3)
        self.assertEqual(runs, [dt(2026, 12, 11), dt(2026, 12, 13),
                                dt(2026, 12, 18)])

    def test_dom_restricted_dow_star_is_and(self):
        runs = next_runs("0 12 15 * *", dt(2026, 11, 24), 2)
        self.assertEqual(runs, [dt(2026, 12, 15, 12), dt(2027, 1, 15, 12)])

    def test_leap_day(self):
        runs = next_runs("0 0 29 2 *", dt(2026, 1, 1), 2)
        self.assertEqual(runs, [dt(2028, 2, 29), dt(2032, 2, 29)])

    def test_day_31_skips_short_months(self):
        runs = next_runs("0 0 31 * *", dt(2026, 1, 31), 3)
        self.assertEqual(runs, [dt(2026, 3, 31), dt(2026, 5, 31),
                                dt(2026, 7, 31)])

    def test_impossible_date_raises(self):
        with self.assertRaises(ValueError):
            next_runs("0 0 30 2 *", dt(2026, 1, 1))
        with self.assertRaises(ValueError):
            next_runs("0 0 31 4,6,9,11 *", dt(2026, 1, 1))

    def test_naive_start_treated_as_utc(self):
        runs = next_runs("0 * * * *", datetime(2026, 1, 1, 10, 30), 1)
        self.assertEqual(runs, [dt(2026, 1, 1, 11)])
        self.assertIs(runs[0].tzinfo, UTC)

    def test_aware_start_converted_to_utc(self):
        rome = timezone(timedelta(hours=1))
        start = datetime(2026, 1, 1, 10, 30, tzinfo=rome)  # 09:30 UTC
        runs = next_runs("0 * * * *", start, 2)
        self.assertEqual(runs, [dt(2026, 1, 1, 10), dt(2026, 1, 1, 11)])
        for r in runs:
            self.assertEqual(r.utcoffset(), timedelta(0))

    def test_results_strictly_increasing_and_matching(self):
        expr = "5-50/15 1,13 */2 * 0,3"
        c = CronExpr(expr)
        runs = next_runs(expr, dt(2026, 11, 24, 7, 51), 40)
        self.assertEqual(len(runs), 40)
        for a, b in zip(runs, runs[1:]):
            self.assertLess(a, b)
        for r in runs:
            self.assertTrue(c.matches(r))

    def test_matches_brute_force(self):
        expr = "*/7 3-5 1-10 * 1"
        c = CronExpr(expr)
        start = dt(2026, 3, 1)
        expected, cur = [], start
        while len(expected) < 10:
            cur += timedelta(minutes=1)
            if c.matches(cur):
                expected.append(cur)
        self.assertEqual(next_runs(expr, start, 10), expected)

    def test_count_zero_and_invalid_count(self):
        self.assertEqual(next_runs("* * * * *", dt(2026, 1, 1), 0), [])
        with self.assertRaises(ValueError):
            next_runs("* * * * *", dt(2026, 1, 1), -1)

    def test_whitespace_tolerant(self):
        runs = next_runs("  0   12\t* * *  ", dt(2026, 1, 1), 1)
        self.assertEqual(runs, [dt(2026, 1, 1, 12)])


if __name__ == "__main__":
    unittest.main()
