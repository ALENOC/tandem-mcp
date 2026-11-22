import unittest
from datetime import datetime, timedelta, timezone

from cron_sched import next_runs, parse

UTC = timezone.utc


def dt(*args):
    return datetime(*args, tzinfo=UTC)


class TestParse(unittest.TestCase):
    def test_star(self):
        c = parse("* * * * *")
        self.assertEqual(c.minutes, frozenset(range(60)))
        self.assertEqual(c.hours, frozenset(range(24)))
        self.assertEqual(c.days_of_month, frozenset(range(1, 32)))
        self.assertEqual(c.months, frozenset(range(1, 13)))
        self.assertEqual(c.days_of_week, frozenset(range(7)))

    def test_numbers_ranges_lists(self):
        c = parse("5 1-3 1,15,31 6 1-5")
        self.assertEqual(c.minutes, {5})
        self.assertEqual(c.hours, {1, 2, 3})
        self.assertEqual(c.days_of_month, {1, 15, 31})
        self.assertEqual(c.months, {6})
        self.assertEqual(c.days_of_week, {1, 2, 3, 4, 5})

    def test_steps(self):
        c = parse("*/15 0-12/4 * */3 *")
        self.assertEqual(c.minutes, {0, 15, 30, 45})
        self.assertEqual(c.hours, {0, 4, 8, 12})
        self.assertEqual(c.months, {1, 4, 7, 10})

    def test_mixed_list(self):
        c = parse("1,10-12,*/20 * * * *")
        self.assertEqual(c.minutes, {0, 1, 10, 11, 12, 20, 40})

    def test_sunday_7_is_0(self):
        self.assertEqual(parse("0 0 * * 7").days_of_week, {0})
        self.assertEqual(parse("0 0 * * 5-7").days_of_week, {5, 6, 0})

    def test_invalid_expressions(self):
        bad = [
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
            "5/2 * * * *",
            "a * * * *",
            "1,,2 * * * *",
            "-1 * * * *",
            "1- * * * *",
            "* * 30 2 *",
            "1.5 * * * *",
        ]
        for expr in bad:
            with self.subTest(expr=expr):
                with self.assertRaises(ValueError):
                    parse(expr)
                with self.assertRaises(ValueError):
                    next_runs(expr, dt(2026, 1, 1))

    def test_non_string_raises(self):
        with self.assertRaises(ValueError):
            parse(None)


class TestNextRuns(unittest.TestCase):
    def test_every_minute_strictly_after(self):
        start = dt(2026, 11, 21, 10, 30, 0)
        self.assertEqual(
            next_runs("* * * * *", start, 3),
            [dt(2026, 11, 21, 10, 31), dt(2026, 11, 21, 10, 32), dt(2026, 11, 21, 10, 33)],
        )

    def test_seconds_truncated(self):
        start = dt(2026, 11, 21, 10, 30, 45, 123)
        self.assertEqual(next_runs("* * * * *", start, 1), [dt(2026, 11, 21, 10, 31)])

    def test_default_count_is_5(self):
        runs = next_runs("*/10 * * * *", dt(2026, 1, 1, 0, 0))
        self.assertEqual(len(runs), 5)
        self.assertEqual(runs[0], dt(2026, 1, 1, 0, 10))
        self.assertEqual(runs[-1], dt(2026, 1, 1, 0, 50))

    def test_hour_rollover(self):
        runs = next_runs("0,30 9-10 * * *", dt(2026, 3, 10, 10, 30), 3)
        self.assertEqual(
            runs, [dt(2026, 3, 11, 9, 0), dt(2026, 3, 11, 9, 30), dt(2026, 3, 11, 10, 0)]
        )

    def test_month_and_year_rollover(self):
        runs = next_runs("0 0 1 * *", dt(2026, 11, 15), 3)
        self.assertEqual(runs, [dt(2026, 12, 1), dt(2027, 1, 1), dt(2027, 2, 1)])

    def test_day_31_skips_short_months(self):
        runs = next_runs("0 12 31 * *", dt(2026, 1, 31, 12, 0), 3)
        self.assertEqual(runs, [dt(2026, 3, 31, 12), dt(2026, 5, 31, 12), dt(2026, 7, 31, 12)])

    def test_leap_day(self):
        runs = next_runs("0 0 29 2 *", dt(2026, 1, 1), 3)
        self.assertEqual(runs, [dt(2028, 2, 29), dt(2032, 2, 29), dt(2036, 2, 29)])

    def test_leap_day_skips_2100(self):
        runs = next_runs("0 0 29 2 *", dt(2097, 1, 1), 2)
        self.assertEqual(runs, [dt(2104, 2, 29), dt(2108, 2, 29)])

    def test_weekdays(self):
        # 2026-11-21 è sabato
        runs = next_runs("0 9 * * 1-5", dt(2026, 11, 21, 12), 6)
        self.assertEqual(
            runs,
            [dt(2026, 11, d, 9) for d in (23, 24, 25, 26, 27)] + [dt(2026, 11, 30, 9)],
        )

    def test_sunday_as_7(self):
        self.assertEqual(
            next_runs("0 0 * * 7", dt(2026, 11, 21), 2),
            next_runs("0 0 * * 0", dt(2026, 11, 21), 2),
        )
        self.assertEqual(next_runs("0 0 * * 7", dt(2026, 11, 21), 1), [dt(2026, 11, 22)])

    def test_dom_or_dow_when_both_restricted(self):
        # giorno 1 del mese OPPURE lunedì
        runs = next_runs("0 0 1 * 1", dt(2026, 11, 21), 4)
        self.assertEqual(
            runs, [dt(2026, 11, 23), dt(2026, 11, 30), dt(2026, 12, 1), dt(2026, 12, 7)]
        )

    def test_range_step(self):
        runs = next_runs("10-30/10 * * * *", dt(2026, 1, 1, 0, 25), 4)
        self.assertEqual(
            runs,
            [dt(2026, 1, 1, 0, 30), dt(2026, 1, 1, 1, 10), dt(2026, 1, 1, 1, 20), dt(2026, 1, 1, 1, 30)],
        )

    def test_naive_start_treated_as_utc(self):
        runs = next_runs("0 * * * *", datetime(2026, 5, 5, 7, 15), 1)
        self.assertEqual(runs, [dt(2026, 5, 5, 8)])
        self.assertIs(runs[0].tzinfo, UTC)

    def test_aware_start_converted_to_utc(self):
        rome = timezone(timedelta(hours=1))
        runs = next_runs("0 * * * *", datetime(2026, 1, 1, 10, 15, tzinfo=rome), 1)
        self.assertEqual(runs, [dt(2026, 1, 1, 10)])
        self.assertEqual(runs[0].utcoffset(), timedelta(0))

    def test_results_strictly_increasing_and_match(self):
        expr = "*/7 3,15 */2 1-6 *"
        c = parse(expr)
        runs = next_runs(expr, dt(2026, 1, 1), 50)
        self.assertEqual(len(runs), 50)
        for a, b in zip(runs, runs[1:]):
            self.assertLess(a, b)
        for r in runs:
            self.assertTrue(c.matches(r))

    def test_matches_brute_force(self):
        expr = "15,45 */6 * * 0,3"
        c = parse(expr)
        start = dt(2026, 11, 1)
        expected = []
        t = start + timedelta(minutes=1)
        while len(expected) < 10:
            if c.matches(t):
                expected.append(t)
            t += timedelta(minutes=1)
        self.assertEqual(next_runs(expr, start, 10), expected)

    def test_count_zero_and_invalid_count(self):
        self.assertEqual(next_runs("* * * * *", dt(2026, 1, 1), 0), [])
        with self.assertRaises(ValueError):
            next_runs("* * * * *", dt(2026, 1, 1), -1)


if __name__ == "__main__":
    unittest.main()
