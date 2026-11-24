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

    def test_number_range_list(self):
        c = parse("5 1-3 1,15,31 6 *")
        self.assertEqual(c.minutes, {5})
        self.assertEqual(c.hours, {1, 2, 3})
        self.assertEqual(c.days_of_month, {1, 15, 31})
        self.assertEqual(c.months, {6})

    def test_steps(self):
        c = parse("*/15 0-12/4 * * *")
        self.assertEqual(c.minutes, {0, 15, 30, 45})
        self.assertEqual(c.hours, {0, 4, 8, 12})

    def test_mixed_list(self):
        c = parse("1,10-12,*/30 * * * *")
        self.assertEqual(c.minutes, {0, 1, 10, 11, 12, 30})

    def test_sunday_seven_alias(self):
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
            "a * * * *",
            "-1 * * * *",
            "1,,2 * * * *",
            "1, * * * *",
            "1-2-3 * * * *",
            "*/2/3 * * * *",
            "5/2 * * * *",
            "0 0 30 2 *",
            "0 0 31 4,6,9,11 *",
        ]
        for expr in bad:
            with self.subTest(expr=expr):
                with self.assertRaises(ValueError):
                    parse(expr)
                with self.assertRaises(ValueError):
                    next_runs(expr, dt(2026, 1, 1))

    def test_non_string(self):
        with self.assertRaises(ValueError):
            parse(None)


class TestNextRuns(unittest.TestCase):
    def test_every_minute_strictly_after(self):
        start = dt(2026, 1, 1, 10, 0)
        self.assertEqual(
            next_runs("* * * * *", start, 3),
            [dt(2026, 1, 1, 10, 1), dt(2026, 1, 1, 10, 2), dt(2026, 1, 1, 10, 3)],
        )

    def test_seconds_are_truncated(self):
        start = dt(2026, 1, 1, 10, 0, 30, 500)
        self.assertEqual(next_runs("* * * * *", start, 1), [dt(2026, 1, 1, 10, 1)])

    def test_default_count_is_five(self):
        runs = next_runs("*/10 * * * *", dt(2026, 1, 1, 23, 35))
        self.assertEqual(
            runs,
            [
                dt(2026, 1, 1, 23, 40),
                dt(2026, 1, 1, 23, 50),
                dt(2026, 1, 2, 0, 0),
                dt(2026, 1, 2, 0, 10),
                dt(2026, 1, 2, 0, 20),
            ],
        )

    def test_daily_rollover_month_and_year(self):
        runs = next_runs("30 2 * * *", dt(2026, 12, 31, 3, 0), 2)
        self.assertEqual(runs, [dt(2027, 1, 1, 2, 30), dt(2027, 1, 2, 2, 30)])

    def test_day_of_week(self):
        # 2026-11-24 è un martedì; lunedì successivi
        runs = next_runs("0 9 * * 1", dt(2026, 11, 24), 3)
        self.assertEqual(runs, [dt(2026, 11, 30, 9), dt(2026, 12, 7, 9), dt(2026, 12, 14, 9)])
        for r in runs:
            self.assertEqual(r.weekday(), 0)

    def test_dom_or_dow_semantics(self):
        # Giorno 1 del mese OPPURE venerdì
        runs = next_runs("0 0 1 * 5", dt(2026, 11, 24), 4)
        self.assertEqual(
            runs,
            [dt(2026, 11, 27), dt(2026, 12, 1), dt(2026, 12, 4), dt(2026, 12, 11)],
        )

    def test_leap_day(self):
        runs = next_runs("0 12 29 2 *", dt(2026, 1, 1), 2)
        self.assertEqual(runs, [dt(2028, 2, 29, 12), dt(2032, 2, 29, 12)])

    def test_day_31_skips_short_months(self):
        runs = next_runs("0 0 31 * *", dt(2026, 1, 31, 0, 0), 3)
        self.assertEqual(runs, [dt(2026, 3, 31), dt(2026, 5, 31), dt(2026, 7, 31)])

    def test_range_step_in_hours(self):
        runs = next_runs("0 9-17/4 * * 1-5", dt(2026, 11, 27, 14), 4)  # venerdì
        self.assertEqual(
            runs,
            [dt(2026, 11, 27, 17), dt(2026, 11, 30, 9), dt(2026, 11, 30, 13), dt(2026, 11, 30, 17)],
        )

    def test_naive_start_treated_as_utc(self):
        self.assertEqual(
            next_runs("0 * * * *", datetime(2026, 5, 1, 10, 15), 1),
            [dt(2026, 5, 1, 11)],
        )

    def test_aware_start_converted_to_utc(self):
        cet = timezone(timedelta(hours=1))
        start = datetime(2026, 1, 1, 0, 30, tzinfo=cet)  # = 2025-12-31 23:30 UTC
        runs = next_runs("0 0 * * *", start, 1)
        self.assertEqual(runs, [dt(2026, 1, 1, 0, 0)])
        self.assertEqual(runs[0].tzinfo, UTC)

    def test_results_utc_and_increasing(self):
        runs = next_runs("*/7 */5 * * *", dt(2026, 3, 3, 3, 3), 50)
        self.assertEqual(len(runs), 50)
        self.assertTrue(all(r.tzinfo == UTC for r in runs))
        self.assertTrue(all(a < b for a, b in zip(runs, runs[1:])))

    def test_count_zero_and_invalid(self):
        self.assertEqual(next_runs("* * * * *", dt(2026, 1, 1), 0), [])
        with self.assertRaises(ValueError):
            next_runs("* * * * *", dt(2026, 1, 1), -1)


if __name__ == "__main__":
    unittest.main()
