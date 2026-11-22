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

    def test_numbers_ranges_lists(self):
        c = parse("5 1-3 1,15,31 2,4-5 1-5")
        self.assertEqual(c.minutes, {5})
        self.assertEqual(c.hours, {1, 2, 3})
        self.assertEqual(c.days, {1, 15, 31})
        self.assertEqual(c.months, {2, 4, 5})
        self.assertEqual(c.weekdays, {1, 2, 3, 4, 5})

    def test_steps(self):
        c = parse("*/15 0-12/4 */10 1-12/3 *")
        self.assertEqual(c.minutes, {0, 15, 30, 45})
        self.assertEqual(c.hours, {0, 4, 8, 12})
        self.assertEqual(c.days, {1, 11, 21, 31})
        self.assertEqual(c.months, {1, 4, 7, 10})

    def test_sunday_as_seven(self):
        self.assertEqual(parse("0 0 * * 7").weekdays, {0})
        self.assertEqual(parse("0 0 * * 5-7").weekdays, {5, 6, 0})

    def test_whitespace_tolerated(self):
        self.assertEqual(parse("  0   12 * *\t* ").hours, {12})


class TestInvalid(unittest.TestCase):
    INVALID = [
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
        "1,,2 * * * *",
        "a * * * *",
        "-1 * * * *",
        "1-2-3 * * * *",
        "1-10/2/3 * * * *",
        "* * * * MON",
    ]

    def test_invalid_expressions_raise(self):
        for expr in self.INVALID:
            with self.subTest(expr=expr):
                with self.assertRaises(ValueError):
                    parse(expr)
                with self.assertRaises(ValueError):
                    next_runs(expr, dt(2026, 1, 1))

    def test_non_string_raises(self):
        with self.assertRaises(ValueError):
            parse(None)

    def test_impossible_date_raises(self):
        with self.assertRaises(ValueError):
            next_runs("0 0 30 2 *", dt(2026, 1, 1))

    def test_invalid_count(self):
        with self.assertRaises(ValueError):
            next_runs("* * * * *", dt(2026, 1, 1), count=-1)


class TestNextRuns(unittest.TestCase):
    def test_every_minute_strictly_after(self):
        runs = next_runs("* * * * *", dt(2026, 1, 1, 10, 0), 3)
        self.assertEqual(
            runs, [dt(2026, 1, 1, 10, 1), dt(2026, 1, 1, 10, 2), dt(2026, 1, 1, 10, 3)]
        )

    def test_seconds_are_truncated(self):
        runs = next_runs("* * * * *", dt(2026, 1, 1, 10, 0, 30, 5), 1)
        self.assertEqual(runs, [dt(2026, 1, 1, 10, 1)])

    def test_default_count_is_five(self):
        self.assertEqual(len(next_runs("*/5 * * * *", dt(2026, 1, 1))), 5)

    def test_count_zero(self):
        self.assertEqual(next_runs("* * * * *", dt(2026, 1, 1), 0), [])

    def test_step_minutes_across_hour(self):
        runs = next_runs("*/20 * * * *", dt(2026, 3, 1, 9, 45), 4)
        self.assertEqual(
            runs,
            [dt(2026, 3, 1, 10, 0), dt(2026, 3, 1, 10, 20),
             dt(2026, 3, 1, 10, 40), dt(2026, 3, 1, 11, 0)],
        )

    def test_daily_rollover_month_and_year(self):
        runs = next_runs("30 23 * * *", dt(2026, 12, 30, 23, 30), 3)
        self.assertEqual(
            runs, [dt(2026, 12, 31, 23, 30), dt(2027, 1, 1, 23, 30), dt(2027, 1, 2, 23, 30)]
        )

    def test_day_31_skips_short_months(self):
        runs = next_runs("0 0 31 * *", dt(2026, 1, 31), 4)
        self.assertEqual(
            runs,
            [dt(2026, 3, 31), dt(2026, 5, 31), dt(2026, 7, 31), dt(2026, 8, 31)],
        )

    def test_leap_day(self):
        runs = next_runs("0 12 29 2 *", dt(2026, 1, 1), 2)
        self.assertEqual(runs, [dt(2028, 2, 29, 12), dt(2032, 2, 29, 12)])

    def test_weekdays_only(self):
        # 2026-11-20 è venerdì
        runs = next_runs("0 9 * * 1-5", dt(2026, 11, 20, 9, 0), 3)
        self.assertEqual(runs, [dt(2026, 11, 23, 9), dt(2026, 11, 24, 9), dt(2026, 11, 25, 9)])
        for r in runs:
            self.assertLess(r.weekday(), 5)

    def test_sunday_zero_and_seven_equivalent(self):
        start = dt(2026, 11, 21)
        self.assertEqual(next_runs("0 0 * * 0", start), next_runs("0 0 * * 7", start))
        self.assertEqual(next_runs("0 0 * * 0", start, 1), [dt(2026, 11, 22)])

    def test_dom_and_dow_are_ored(self):
        # giorno 1 del mese OPPURE lunedì; dicembre 2026: 1 è martedì
        runs = next_runs("0 0 1 * 1", dt(2026, 11, 30, 0, 0), 4)
        self.assertEqual(
            runs, [dt(2026, 12, 1), dt(2026, 12, 7), dt(2026, 12, 14), dt(2026, 12, 21)]
        )

    def test_dow_restricted_with_dom_star(self):
        # solo sabato: il '*' nel giorno del mese non allarga la selezione
        runs = next_runs("0 0 * * 6", dt(2026, 11, 21), 2)
        self.assertEqual(runs, [dt(2026, 11, 28), dt(2026, 12, 5)])

    def test_lists_and_ranges_combined(self):
        runs = next_runs("0,30 8-9 * * *", dt(2026, 6, 1, 8, 0), 4)
        self.assertEqual(
            runs,
            [dt(2026, 6, 1, 8, 30), dt(2026, 6, 1, 9, 0),
             dt(2026, 6, 1, 9, 30), dt(2026, 6, 2, 8, 0)],
        )

    def test_range_with_step_months(self):
        runs = next_runs("0 0 1 1-12/3 *", dt(2026, 2, 1), 4)
        self.assertEqual(
            runs, [dt(2026, 4, 1), dt(2026, 7, 1), dt(2026, 10, 1), dt(2027, 1, 1)]
        )

    def test_naive_start_treated_as_utc(self):
        runs = next_runs("0 * * * *", datetime(2026, 1, 1, 10, 15), 1)
        self.assertEqual(runs, [dt(2026, 1, 1, 11)])
        self.assertEqual(runs[0].tzinfo, UTC)

    def test_aware_start_converted_to_utc(self):
        rome = timezone(timedelta(hours=1))
        start = datetime(2026, 1, 1, 12, 0, tzinfo=rome)  # 11:00 UTC
        runs = next_runs("0 12 * * *", start, 1)
        self.assertEqual(runs, [dt(2026, 1, 1, 12)])

    def test_results_strictly_increasing_and_after_start(self):
        start = dt(2026, 5, 17, 13, 37)
        runs = next_runs("*/7 */5 */3 * *", start, 50)
        self.assertEqual(len(runs), 50)
        self.assertTrue(all(r > start for r in runs))
        self.assertTrue(all(a < b for a, b in zip(runs, runs[1:])))


if __name__ == "__main__":
    unittest.main()
