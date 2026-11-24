import unittest
from datetime import datetime, timedelta, timezone

from cron_sched import next_runs, parse

UTC = timezone.utc


def dt(*args):
    return datetime(*args, tzinfo=UTC)


class TestParse(unittest.TestCase):
    def test_star_expands_full_range(self):
        c = parse("* * * * *")
        self.assertEqual(c.minutes, frozenset(range(60)))
        self.assertEqual(c.hours, frozenset(range(24)))
        self.assertEqual(c.days, frozenset(range(1, 32)))
        self.assertEqual(c.months, frozenset(range(1, 13)))
        self.assertEqual(c.weekdays, frozenset(range(7)))

    def test_list_range_and_steps(self):
        c = parse("1,5,10 9-11 */10 1-12/3 *")
        self.assertEqual(c.minutes, {1, 5, 10})
        self.assertEqual(c.hours, {9, 10, 11})
        self.assertEqual(c.days, {1, 11, 21, 31})
        self.assertEqual(c.months, {1, 4, 7, 10})

    def test_mixed_list_with_steps(self):
        c = parse("0-10/5,30,50-59/3 * * * *")
        self.assertEqual(c.minutes, {0, 5, 10, 30, 50, 53, 56, 59})

    def test_weekday_seven_is_sunday(self):
        self.assertEqual(parse("0 0 * * 7").weekdays, {0})
        self.assertEqual(parse("0 0 * * 5-7").weekdays, {5, 6, 0})

    def test_invalid_expressions_raise(self):
        bad = [
            "", "* * * *", "* * * * * *", "60 * * * *", "* 24 * * *",
            "* * 0 * *", "* * 32 * *", "* * * 0 *", "* * * 13 *",
            "* * * * 8", "5-1 * * * *", "*/0 * * * *", "a * * * *",
            "1,,2 * * * *", "1, * * * *", "-1 * * * *", "1-2-3 * * * *",
            "*/ * * * *", "5/2 * * * *", "1.5 * * * *", "0 0 30 2 *",
            "0 0 31 4,6,9,11 *",
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


class TestNextRuns(unittest.TestCase):
    def test_every_minute_strictly_after_start(self):
        runs = next_runs("* * * * *", dt(2026, 1, 1, 12, 0, 0))
        self.assertEqual(runs, [dt(2026, 1, 1, 12, m) for m in range(1, 6)])

    def test_start_with_seconds_rounds_up(self):
        runs = next_runs("* * * * *", dt(2026, 1, 1, 12, 0, 30), count=2)
        self.assertEqual(runs, [dt(2026, 1, 1, 12, 1), dt(2026, 1, 1, 12, 2)])

    def test_default_count_is_five(self):
        self.assertEqual(len(next_runs("*/15 * * * *", dt(2026, 1, 1))), 5)

    def test_step_minutes(self):
        runs = next_runs("*/15 * * * *", dt(2026, 1, 1, 23, 50), count=4)
        self.assertEqual(
            runs,
            [dt(2026, 1, 2, 0, 0), dt(2026, 1, 2, 0, 15),
             dt(2026, 1, 2, 0, 30), dt(2026, 1, 2, 0, 45)],
        )

    def test_daily_rollover_across_year(self):
        runs = next_runs("30 9 * * *", dt(2026, 12, 31, 10, 0), count=2)
        self.assertEqual(runs, [dt(2027, 1, 1, 9, 30), dt(2027, 1, 2, 9, 30)])

    def test_weekdays_range(self):
        # 2026-11-20 è venerdì; lun-ven alle 8:00
        runs = next_runs("0 8 * * 1-5", dt(2026, 11, 20, 9, 0), count=3)
        self.assertEqual(
            runs, [dt(2026, 11, 23, 8), dt(2026, 11, 24, 8), dt(2026, 11, 25, 8)]
        )
        for r in runs:
            self.assertLess(r.weekday(), 5)

    def test_sunday_as_0_and_7(self):
        a = next_runs("0 0 * * 0", dt(2026, 11, 22, 1), count=3)
        b = next_runs("0 0 * * 7", dt(2026, 11, 22, 1), count=3)
        self.assertEqual(a, b)
        self.assertEqual(a[0], dt(2026, 11, 29))
        self.assertTrue(all(r.weekday() == 6 for r in a))

    def test_dom_and_dow_use_or_when_both_restricted(self):
        # giorno 1 del mese OPPURE lunedì
        runs = next_runs("0 0 1 * 1", dt(2026, 11, 25), count=4)
        self.assertEqual(
            runs, [dt(2026, 11, 30), dt(2026, 12, 1), dt(2026, 12, 7), dt(2026, 12, 14)]
        )

    def test_dom_with_star_dow_is_and(self):
        runs = next_runs("0 12 15 * *", dt(2026, 11, 22), count=2)
        self.assertEqual(runs, [dt(2026, 12, 15, 12), dt(2027, 1, 15, 12)])

    def test_month_skips_short_months(self):
        runs = next_runs("0 0 31 * *", dt(2026, 1, 31, 0, 0), count=3)
        self.assertEqual(runs, [dt(2026, 3, 31), dt(2026, 5, 31), dt(2026, 7, 31)])

    def test_leap_day(self):
        runs = next_runs("0 0 29 2 *", dt(2026, 1, 1), count=2)
        self.assertEqual(runs, [dt(2028, 2, 29), dt(2032, 2, 29)])

    def test_range_with_step_hours(self):
        runs = next_runs("0 8-18/4 * * *", dt(2026, 11, 22, 7, 0), count=4)
        self.assertEqual(
            runs,
            [dt(2026, 11, 22, 8), dt(2026, 11, 22, 12),
             dt(2026, 11, 22, 16), dt(2026, 11, 23, 8)],
        )

    def test_results_are_utc_aware_and_increasing(self):
        runs = next_runs("*/7 */5 * * *", dt(2026, 6, 1), count=20)
        self.assertEqual(len(runs), 20)
        for r in runs:
            self.assertEqual(r.utcoffset(), timedelta(0))
        self.assertEqual(runs, sorted(set(runs)))

    def test_naive_start_treated_as_utc(self):
        naive = datetime(2026, 1, 1, 12, 0)
        self.assertEqual(
            next_runs("0 * * * *", naive, count=1), [dt(2026, 1, 1, 13, 0)]
        )

    def test_aware_start_converted_to_utc(self):
        rome = timezone(timedelta(hours=1))
        start = datetime(2026, 1, 1, 12, 0, tzinfo=rome)  # 11:00 UTC
        self.assertEqual(
            next_runs("0 * * * *", start, count=1), [dt(2026, 1, 1, 12, 0)]
        )

    def test_count_zero_and_invalid_count(self):
        self.assertEqual(next_runs("* * * * *", dt(2026, 1, 1), count=0), [])
        with self.assertRaises(ValueError):
            next_runs("* * * * *", dt(2026, 1, 1), count=-1)

    def test_rare_expression_dow_or_leap_day(self):
        # 29 febbraio OPPURE lunedì, solo a febbraio
        runs = next_runs("0 0 29 2 1", dt(2027, 2, 27), count=3)
        self.assertEqual(runs, [dt(2028, 2, 7), dt(2028, 2, 14), dt(2028, 2, 21)])
        self.assertTrue(all(r.month == 2 for r in runs))


if __name__ == "__main__":
    unittest.main()
