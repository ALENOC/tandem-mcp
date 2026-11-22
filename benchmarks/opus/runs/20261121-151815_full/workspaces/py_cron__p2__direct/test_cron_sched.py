import unittest
from datetime import datetime, timedelta, timezone

from cron_sched import iter_runs, next_runs, parse

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

    def test_mixed_list_elements(self):
        c = parse("0-4/2,30,50-52 * * * *")
        self.assertEqual(c.minutes, {0, 2, 4, 30, 50, 51, 52})

    def test_weekday_seven_is_sunday(self):
        self.assertEqual(parse("0 0 * * 7").weekdays, {0})
        self.assertEqual(parse("0 0 * * 5-7").weekdays, {5, 6, 0})

    def test_invalid_expressions_raise(self):
        bad = [
            "", "* * * *", "* * * * * *", "60 * * * *", "* 24 * * *",
            "* * 0 * *", "* * 32 * *", "* * * 0 *", "* * * 13 *",
            "* * * * 8", "*/0 * * * *", "5/2 * * * *", "10-5 * * * *",
            "a * * * *", "1,,2 * * * *", "-1 * * * *", "1- * * * *",
            "*/ * * * *", "1-2-3 * * * *", "*/x * * * *", "1.5 * * * *",
            ", * * * *", "*/-1 * * * *",
        ]
        for expr in bad:
            with self.subTest(expr=expr):
                with self.assertRaises(ValueError):
                    parse(expr)
                with self.assertRaises(ValueError):
                    next_runs(expr, dt(2026, 1, 1))

    def test_non_string_raises_value_error(self):
        with self.assertRaises(ValueError):
            next_runs(None, dt(2026, 1, 1))


class TestNextRuns(unittest.TestCase):
    def test_every_minute_is_strictly_after_start(self):
        start = dt(2026, 3, 1, 10, 0, 0)
        self.assertEqual(
            next_runs("* * * * *", start, 3),
            [dt(2026, 3, 1, 10, 1), dt(2026, 3, 1, 10, 2), dt(2026, 3, 1, 10, 3)],
        )

    def test_seconds_are_rounded_up_to_next_minute(self):
        start = dt(2026, 3, 1, 10, 0, 30, 500)
        self.assertEqual(next_runs("* * * * *", start, 1), [dt(2026, 3, 1, 10, 1)])

    def test_default_count_is_five(self):
        runs = next_runs("*/15 * * * *", dt(2026, 1, 1, 0, 0))
        self.assertEqual(len(runs), 5)
        self.assertEqual(runs[0], dt(2026, 1, 1, 0, 15))
        self.assertEqual(runs[-1], dt(2026, 1, 1, 1, 15))

    def test_daily_rolls_over_month_and_year(self):
        runs = next_runs("30 2 * * *", dt(2026, 12, 30, 3, 0), 3)
        self.assertEqual(
            runs, [dt(2026, 12, 31, 2, 30), dt(2027, 1, 1, 2, 30), dt(2027, 1, 2, 2, 30)]
        )

    def test_weekday_range(self):
        # 2026-11-21 è sabato: i prossimi giorni lavorativi alle 9:00.
        runs = next_runs("0 9 * * 1-5", dt(2026, 11, 21, 12, 0), 3)
        self.assertEqual(runs, [dt(2026, 11, 23, 9), dt(2026, 11, 24, 9), dt(2026, 11, 25, 9)])
        for r in runs:
            self.assertLess(r.weekday(), 5)

    def test_dom_and_dow_use_or_semantics(self):
        # Il 13 del mese OPPURE venerdì.
        runs = next_runs("0 0 13 * 5", dt(2026, 11, 1), 4)
        self.assertEqual(
            runs, [dt(2026, 11, 6), dt(2026, 11, 13), dt(2026, 11, 20), dt(2026, 11, 27)]
        )

    def test_leap_day(self):
        runs = next_runs("0 12 29 2 *", dt(2026, 1, 1), 2)
        self.assertEqual(runs, [dt(2028, 2, 29, 12), dt(2032, 2, 29, 12)])

    def test_skips_months_without_day_31(self):
        runs = next_runs("0 0 31 * *", dt(2026, 1, 31, 0, 0), 3)
        self.assertEqual(runs, [dt(2026, 3, 31), dt(2026, 5, 31), dt(2026, 7, 31)])

    def test_impossible_date_raises(self):
        with self.assertRaises(ValueError):
            next_runs("0 0 30 2 *", dt(2026, 1, 1))

    def test_step_on_range_in_hours(self):
        runs = next_runs("0 8-18/4 * * *", dt(2026, 6, 1, 9, 0), 4)
        self.assertEqual(
            runs, [dt(2026, 6, 1, 12), dt(2026, 6, 1, 16), dt(2026, 6, 2, 8), dt(2026, 6, 2, 12)]
        )

    def test_naive_start_treated_as_utc_and_results_aware(self):
        runs = next_runs("0 * * * *", datetime(2026, 5, 5, 7, 59), 1)
        self.assertEqual(runs, [dt(2026, 5, 5, 8, 0)])
        self.assertIs(runs[0].tzinfo, UTC)

    def test_aware_non_utc_start_is_converted(self):
        cet = timezone(timedelta(hours=1))
        start = datetime(2026, 1, 1, 10, 0, tzinfo=cet)  # 09:00 UTC
        self.assertEqual(next_runs("0 * * * *", start, 1), [dt(2026, 1, 1, 10, 0)])

    def test_results_strictly_increasing_and_matching(self):
        expr = "*/7 1,13 */3 * 0,3"
        runs = next_runs(expr, dt(2026, 1, 1), 50)
        cron = parse(expr)
        self.assertEqual(len(runs), 50)
        for a, b in zip(runs, runs[1:]):
            self.assertLess(a, b)
        for r in runs:
            self.assertTrue(cron.matches(r))

    def test_brute_force_agreement(self):
        expr = "5-50/15 */5 1-10 * 2"
        start = dt(2026, 2, 3, 4, 5)
        cron = parse(expr)
        expected, t = [], start + timedelta(minutes=1)
        while len(expected) < 20:
            if cron.matches(t):
                expected.append(t)
            t += timedelta(minutes=1)
        self.assertEqual(next_runs(expr, start, 20), expected)

    def test_count_validation(self):
        self.assertEqual(next_runs("* * * * *", dt(2026, 1, 1), 0), [])
        for bad in (-1, 1.5, "3", True):
            with self.subTest(count=bad):
                with self.assertRaises(ValueError):
                    next_runs("* * * * *", dt(2026, 1, 1), bad)

    def test_iter_runs_is_lazy_generator(self):
        gen = iter_runs("0 0 1 1 *", dt(2026, 6, 1))
        self.assertEqual(next(gen), dt(2027, 1, 1))
        self.assertEqual(next(gen), dt(2028, 1, 1))


if __name__ == "__main__":
    unittest.main()
