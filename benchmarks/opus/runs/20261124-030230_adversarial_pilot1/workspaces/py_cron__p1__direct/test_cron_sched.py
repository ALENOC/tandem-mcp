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
        self.assertEqual(c.days_of_month, frozenset(range(1, 32)))
        self.assertEqual(c.months, frozenset(range(1, 13)))
        self.assertEqual(c.days_of_week, frozenset(range(7)))

    def test_list_range_and_steps(self):
        c = parse("1,2,30 9-17 */10 1-12/3 1-5")
        self.assertEqual(c.minutes, {1, 2, 30})
        self.assertEqual(c.hours, set(range(9, 18)))
        self.assertEqual(c.days_of_month, {1, 11, 21, 31})
        self.assertEqual(c.months, {1, 4, 7, 10})
        self.assertEqual(c.days_of_week, {1, 2, 3, 4, 5})

    def test_mixed_list_with_ranges_and_steps(self):
        c = parse("0-5/2,30,50-52 * * * *")
        self.assertEqual(c.minutes, {0, 2, 4, 30, 50, 51, 52})

    def test_sunday_7_is_alias_of_0(self):
        self.assertEqual(parse("0 0 * * 7").days_of_week, {0})
        self.assertEqual(parse("0 0 * * 5-7").days_of_week, {5, 6, 0})

    def test_extra_whitespace_is_tolerated(self):
        self.assertEqual(parse("  0   12 * *\t* ").hours, {12})

    def test_invalid_expressions_raise_value_error(self):
        bad = [
            "",
            "* * * *",              # 4 campi
            "* * * * * *",          # 6 campi
            "60 * * * *",           # minuto fuori range
            "* 24 * * *",           # ora fuori range
            "* * 0 * *",            # giorno 0
            "* * 32 * *",
            "* * * 0 *",
            "* * * 13 *",
            "* * * * 8",
            "5-1 * * * *",          # intervallo invertito
            "*/0 * * * *",          # step zero
            "*/ * * * *",
            "1,,2 * * * *",         # elemento vuoto
            "1, * * * *",
            "a * * * *",
            "-1 * * * *",
            "1-2-3 * * * *",
            "5/10 * * * *",         # step senza * o intervallo
            "*/-2 * * * *",
            "1.5 * * * *",
            "JAN * * * *",
        ]
        for expr in bad:
            with self.subTest(expr=expr):
                with self.assertRaises(ValueError):
                    parse(expr)
                with self.assertRaises(ValueError):
                    next_runs(expr, dt(2026, 1, 1))

    def test_non_string_expression(self):
        with self.assertRaises(ValueError):
            next_runs(None, dt(2026, 1, 1))


class TestNextRuns(unittest.TestCase):
    def test_every_minute_strictly_after_start(self):
        start = dt(2026, 3, 10, 8, 15)
        self.assertEqual(
            next_runs("* * * * *", start, 3),
            [dt(2026, 3, 10, 8, 16), dt(2026, 3, 10, 8, 17), dt(2026, 3, 10, 8, 18)],
        )

    def test_start_with_seconds_rounds_up(self):
        start = dt(2026, 3, 10, 8, 15, 30, 123)
        self.assertEqual(next_runs("* * * * *", start, 1), [dt(2026, 3, 10, 8, 16)])

    def test_default_count_is_five(self):
        runs = next_runs("*/15 * * * *", dt(2026, 1, 1, 0, 0))
        self.assertEqual(
            runs,
            [dt(2026, 1, 1, 0, 15), dt(2026, 1, 1, 0, 30), dt(2026, 1, 1, 0, 45),
             dt(2026, 1, 1, 1, 0), dt(2026, 1, 1, 1, 15)],
        )

    def test_results_are_utc_aware(self):
        for r in next_runs("0 * * * *", dt(2026, 1, 1)):
            self.assertEqual(r.utcoffset(), timedelta(0))

    def test_daily_rolls_over_day_month_year(self):
        self.assertEqual(
            next_runs("30 23 * * *", dt(2026, 12, 31, 23, 30), 2),
            [dt(2027, 1, 1, 23, 30), dt(2027, 1, 2, 23, 30)],
        )

    def test_weekdays_only(self):
        # 2026-11-27 è venerdì
        runs = next_runs("0 9 * * 1-5", dt(2026, 11, 27, 10, 0), 3)
        self.assertEqual(runs, [dt(2026, 11, 30, 9), dt(2026, 12, 1, 9), dt(2026, 12, 2, 9)])
        for r in runs:
            self.assertLess(r.weekday(), 5)

    def test_sunday_via_0_and_7_equivalent(self):
        start = dt(2026, 11, 24)
        a = next_runs("0 0 * * 0", start, 4)
        self.assertEqual(a, next_runs("0 0 * * 7", start, 4))
        self.assertEqual(a[0], dt(2026, 11, 29))
        self.assertTrue(all(r.weekday() == 6 for r in a))

    def test_dom_and_dow_both_restricted_is_or(self):
        # giorno 1 del mese OPPURE lunedì (comportamento Vixie cron)
        runs = next_runs("0 0 1 * 1", dt(2026, 11, 24), 4)
        self.assertEqual(
            runs,
            [dt(2026, 11, 30), dt(2026, 12, 1), dt(2026, 12, 7), dt(2026, 12, 14)],
        )

    def test_dom_restricted_dow_star_is_and(self):
        runs = next_runs("0 0 13 * *", dt(2026, 1, 1), 2)
        self.assertEqual(runs, [dt(2026, 1, 13), dt(2026, 2, 13)])

    def test_feb_29_leap_years(self):
        self.assertEqual(
            next_runs("0 12 29 2 *", dt(2026, 1, 1), 3),
            [dt(2028, 2, 29, 12), dt(2032, 2, 29, 12), dt(2036, 2, 29, 12)],
        )

    def test_day_31_skips_short_months(self):
        runs = next_runs("0 0 31 * *", dt(2026, 1, 31, 0, 0), 3)
        self.assertEqual(runs, [dt(2026, 3, 31), dt(2026, 5, 31), dt(2026, 7, 31)])

    def test_range_with_step_in_hours(self):
        self.assertEqual(
            next_runs("0 8-18/4 * * *", dt(2026, 6, 1, 13, 0), 4),
            [dt(2026, 6, 1, 16), dt(2026, 6, 2, 8), dt(2026, 6, 2, 12), dt(2026, 6, 2, 16)],
        )

    def test_naive_start_treated_as_utc(self):
        self.assertEqual(
            next_runs("0 * * * *", datetime(2026, 1, 1, 5, 10), 1),
            [dt(2026, 1, 1, 6)],
        )

    def test_aware_start_converted_to_utc(self):
        cet = timezone(timedelta(hours=1))
        start = datetime(2026, 1, 1, 10, 0, tzinfo=cet)  # = 09:00 UTC
        self.assertEqual(next_runs("0 * * * *", start, 1), [dt(2026, 1, 1, 10)])

    def test_impossible_date_raises_value_error(self):
        with self.assertRaises(ValueError):
            next_runs("0 0 30 2 *", dt(2026, 1, 1))
        with self.assertRaises(ValueError):
            next_runs("0 0 31 4,6,9,11 *", dt(2026, 1, 1))

    def test_count_validation(self):
        self.assertEqual(next_runs("* * * * *", dt(2026, 1, 1), 0), [])
        for bad in (-1, 1.5, "3", True):
            with self.subTest(count=bad):
                with self.assertRaises(ValueError):
                    next_runs("* * * * *", dt(2026, 1, 1), bad)

    def test_results_strictly_increasing_and_matching(self):
        expr = "*/7 1,13 */3 * 2-4"
        c = parse(expr)
        runs = next_runs(expr, dt(2026, 1, 1), 50)
        self.assertEqual(len(runs), 50)
        for a, b in zip(runs, runs[1:]):
            self.assertLess(a, b)
        for r in runs:
            self.assertTrue(c.matches(r), r)

    def test_matches_brute_force(self):
        expr = "5,35 */5 1-10 */2 *"
        c = parse(expr)
        start = dt(2026, 1, 1)
        expected, cur = [], start + timedelta(minutes=1)
        while len(expected) < 20:
            if c.matches(cur):
                expected.append(cur)
            cur += timedelta(minutes=1)
        self.assertEqual(next_runs(expr, start, 20), expected)


if __name__ == "__main__":
    unittest.main()
