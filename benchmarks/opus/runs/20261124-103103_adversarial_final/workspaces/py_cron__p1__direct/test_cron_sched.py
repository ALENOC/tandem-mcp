import unittest
from datetime import datetime, timedelta, timezone

from cron_sched import iter_runs, next_runs, parse

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
        c = parse("*/15 0-12/4 */10 1-12/3 *")
        self.assertEqual(c.minutes, {0, 15, 30, 45})
        self.assertEqual(c.hours, {0, 4, 8, 12})
        self.assertEqual(c.days_of_month, {1, 11, 21, 31})
        self.assertEqual(c.months, {1, 4, 7, 10})

    def test_mixed_list_and_sunday_7(self):
        c = parse("1,10-12,*/20 * * * 7")
        self.assertEqual(c.minutes, {0, 1, 10, 11, 12, 20, 40})
        self.assertEqual(c.days_of_week, {0})

    def test_extra_whitespace_allowed(self):
        self.assertEqual(parse("  0   0 * *  * ").minutes, {0})

    def test_invalid_expressions(self):
        bad = [
            "", "* * * *", "* * * * * *", "60 * * * *", "* 24 * * *",
            "* * 0 * *", "* * 32 * *", "* * * 0 *", "* * * 13 *",
            "* * * * 8", "5-1 * * * *", "*/0 * * * *", "*/ * * * *",
            "1,,2 * * * *", ",1 * * * *", "a * * * *", "-1 * * * *",
            "1-2-3 * * * *", "*/2/3 * * * *", "1.5 * * * *", "+1 * * * *",
            "* * 30 2 *", "* * 31 4,6,9,11 *", "１ * * * *", "1- * * * *",
        ]
        for expr in bad:
            with self.subTest(expr=expr):
                with self.assertRaises(ValueError):
                    parse(expr)

    def test_non_string_raises_value_error(self):
        with self.assertRaises(ValueError):
            parse(None)


class TestNextRuns(unittest.TestCase):
    def test_every_minute_strictly_after(self):
        runs = next_runs("* * * * *", dt(2026, 1, 1, 10, 0), 3)
        self.assertEqual(runs, [dt(2026, 1, 1, 10, 1), dt(2026, 1, 1, 10, 2),
                                dt(2026, 1, 1, 10, 3)])

    def test_seconds_truncated(self):
        runs = next_runs("* * * * *", dt(2026, 1, 1, 10, 0, 59, 999999), 1)
        self.assertEqual(runs, [dt(2026, 1, 1, 10, 1)])

    def test_default_count_is_five(self):
        runs = next_runs("0 * * * *", dt(2026, 1, 1, 23, 30))
        self.assertEqual(len(runs), 5)
        self.assertEqual(runs[0], dt(2026, 1, 2, 0, 0))
        self.assertEqual(runs[-1], dt(2026, 1, 2, 4, 0))

    def test_step_minutes_cross_hour(self):
        runs = next_runs("*/20 * * * *", dt(2026, 3, 1, 9, 41), 4)
        self.assertEqual(runs, [dt(2026, 3, 1, 10, 0), dt(2026, 3, 1, 10, 20),
                                dt(2026, 3, 1, 10, 40), dt(2026, 3, 1, 11, 0)])

    def test_range_step_hours(self):
        runs = next_runs("30 8-18/5 * * *", dt(2026, 5, 5, 13, 30), 3)
        self.assertEqual(runs, [dt(2026, 5, 5, 18, 30), dt(2026, 5, 6, 8, 30),
                                dt(2026, 5, 6, 13, 30)])

    def test_year_rollover(self):
        runs = next_runs("0 0 1 1 *", dt(2026, 12, 31, 23, 59), 2)
        self.assertEqual(runs, [dt(2027, 1, 1), dt(2028, 1, 1)])

    def test_leap_day(self):
        runs = next_runs("0 12 29 2 *", dt(2026, 11, 24), 2)
        self.assertEqual(runs, [dt(2028, 2, 29, 12), dt(2032, 2, 29, 12)])

    def test_day_31_skips_short_months(self):
        runs = next_runs("0 0 31 * *", dt(2026, 1, 31, 0, 0), 3)
        self.assertEqual(runs, [dt(2026, 3, 31), dt(2026, 5, 31), dt(2026, 7, 31)])

    def test_weekdays_only(self):
        # 2026-11-27 è venerdì
        runs = next_runs("0 9 * * 1-5", dt(2026, 11, 27, 9, 0), 2)
        self.assertEqual(runs, [dt(2026, 11, 30, 9), dt(2026, 12, 1, 9)])
        for r in runs:
            self.assertLess(r.weekday(), 5)

    def test_sunday_0_and_7_equivalent(self):
        start = dt(2026, 11, 24)
        self.assertEqual(next_runs("0 0 * * 0", start), next_runs("0 0 * * 7", start))
        self.assertEqual(next_runs("0 0 * * 0", start, 1), [dt(2026, 11, 29)])

    def test_dom_dow_or_semantics(self):
        # giorno 1 del mese OPPURE lunedì; 2026-11-24 è martedì
        runs = next_runs("0 0 1 * 1", dt(2026, 11, 24), 3)
        self.assertEqual(runs, [dt(2026, 11, 30), dt(2026, 12, 1), dt(2026, 12, 7)])

    def test_dom_star_step_with_dow_is_and(self):
        # '*/2' inizia con '*' => non ristretto => AND con giorno_settimana
        runs = next_runs("0 0 */2 * 1", dt(2026, 11, 1), 2)
        for r in runs:
            self.assertEqual(r.weekday(), 0)
            self.assertEqual(r.day % 2, 1)

    def test_aware_input_converted_to_utc(self):
        rome = timezone(timedelta(hours=1))
        runs = next_runs("0 * * * *", datetime(2026, 1, 1, 10, 30, tzinfo=rome), 1)
        self.assertEqual(runs, [dt(2026, 1, 1, 10, 0)])
        self.assertIs(runs[0].tzinfo, UTC)

    def test_naive_input_treated_as_utc(self):
        runs = next_runs("15 * * * *", datetime(2026, 1, 1, 10, 0), 1)
        self.assertEqual(runs, [dt(2026, 1, 1, 10, 15)])
        self.assertEqual(runs[0].utcoffset(), timedelta(0))

    def test_results_strictly_increasing(self):
        runs = next_runs("*/7 */3 * * *", dt(2026, 2, 28, 22), 50)
        self.assertEqual(len(runs), 50)
        self.assertTrue(all(a < b for a, b in zip(runs, runs[1:])))

    def test_count_zero_and_negative(self):
        self.assertEqual(next_runs("* * * * *", dt(2026, 1, 1), 0), [])
        with self.assertRaises(ValueError):
            next_runs("* * * * *", dt(2026, 1, 1), -1)

    def test_invalid_expression_raises(self):
        with self.assertRaises(ValueError):
            next_runs("99 * * * *", dt(2026, 1, 1))

    def test_near_datetime_max_stops(self):
        runs = next_runs("0 0 1 1 *", datetime(9999, 6, 1, tzinfo=UTC), 5)
        self.assertEqual(runs, [])

    def test_iter_runs_is_lazy_generator(self):
        it = iter_runs("0 0 * * *", dt(2026, 1, 1))
        self.assertEqual(next(it), dt(2026, 1, 2))
        self.assertEqual(next(it), dt(2026, 1, 3))


if __name__ == "__main__":
    unittest.main()
