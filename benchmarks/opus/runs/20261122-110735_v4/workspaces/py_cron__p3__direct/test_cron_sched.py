import unittest
from datetime import datetime, timedelta, timezone

from cron_sched import next_runs, parse

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

    def test_numbers_ranges_lists(self):
        c = parse("5 1-3 1,15,31 6 1-5")
        self.assertEqual(c.minutes, {5})
        self.assertEqual(c.hours, {1, 2, 3})
        self.assertEqual(c.days, {1, 15, 31})
        self.assertEqual(c.months, {6})
        self.assertEqual(c.weekdays, {1, 2, 3, 4, 5})

    def test_steps(self):
        c = parse("*/15 0-12/4 */10 * *")
        self.assertEqual(c.minutes, {0, 15, 30, 45})
        self.assertEqual(c.hours, {0, 4, 8, 12})
        self.assertEqual(c.days, {1, 11, 21, 31})

    def test_mixed_list_with_ranges_and_steps(self):
        c = parse("1,10-12,40-50/5 * * * *")
        self.assertEqual(c.minutes, {1, 10, 11, 12, 40, 45, 50})

    def test_sunday_as_seven(self):
        self.assertEqual(parse("0 0 * * 7").weekdays, {0})
        self.assertEqual(parse("0 0 * * 0,7").weekdays, {0})

    def test_invalid_expressions_raise(self):
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
            "5/2 * * * *",
            "a * * * *",
            "-1 * * * *",
            "1,,2 * * * *",
            "1, * * * *",
            "1-2-3 * * * *",
            "*/2/3 * * * *",
            "0 0 30 2 *",
            "0 0 31 4,6 *",
        ]
        for expr in invalid:
            with self.subTest(expr=expr):
                with self.assertRaises(ValueError):
                    next_runs(expr, dt(2026, 1, 1))

    def test_non_string_raises_value_error(self):
        with self.assertRaises(ValueError):
            parse(None)


class TestNextRuns(unittest.TestCase):
    def test_every_minute_strictly_after_start(self):
        runs = next_runs("* * * * *", dt(2026, 1, 1, 10, 0), 3)
        self.assertEqual(runs, [dt(2026, 1, 1, 10, 1), dt(2026, 1, 1, 10, 2),
                                dt(2026, 1, 1, 10, 3)])

    def test_seconds_in_start_are_handled(self):
        start = datetime(2026, 1, 1, 10, 0, 30, 123, tzinfo=UTC)
        self.assertEqual(next_runs("* * * * *", start, 1), [dt(2026, 1, 1, 10, 1)])

    def test_default_count_is_five(self):
        runs = next_runs("*/15 * * * *", dt(2026, 1, 1, 23, 40))
        self.assertEqual(runs, [dt(2026, 1, 1, 23, 45), dt(2026, 1, 2, 0, 0),
                                dt(2026, 1, 2, 0, 15), dt(2026, 1, 2, 0, 30),
                                dt(2026, 1, 2, 0, 45)])

    def test_daily_rollover_month_and_year(self):
        runs = next_runs("30 9 * * *", dt(2026, 12, 31, 9, 30), 2)
        self.assertEqual(runs, [dt(2027, 1, 1, 9, 30), dt(2027, 1, 2, 9, 30)])

    def test_weekdays_only(self):
        # 2026-11-20 è venerdì
        runs = next_runs("0 8 * * 1-5", dt(2026, 11, 20, 9, 0), 3)
        self.assertEqual(runs, [dt(2026, 11, 23, 8), dt(2026, 11, 24, 8),
                                dt(2026, 11, 25, 8)])
        for r in runs:
            self.assertLess(r.weekday(), 5)

    def test_dom_or_dow_when_both_restricted(self):
        # giorno 1 del mese OPPURE lunedì; 2026-11-22 è domenica
        runs = next_runs("0 0 1 * 1", dt(2026, 11, 22), 4)
        self.assertEqual(runs, [dt(2026, 11, 23), dt(2026, 11, 30),
                                dt(2026, 12, 1), dt(2026, 12, 7)])

    def test_day_31_skips_short_months(self):
        runs = next_runs("0 0 31 * *", dt(2026, 1, 31), 3)
        self.assertEqual(runs, [dt(2026, 3, 31), dt(2026, 5, 31), dt(2026, 7, 31)])

    def test_leap_day(self):
        runs = next_runs("0 12 29 2 *", dt(2026, 11, 22), 2)
        self.assertEqual(runs, [dt(2028, 2, 29, 12), dt(2032, 2, 29, 12)])

    def test_range_step_hours(self):
        runs = next_runs("0 9-17/4 * * *", dt(2026, 6, 1, 9, 0), 4)
        self.assertEqual(runs, [dt(2026, 6, 1, 13), dt(2026, 6, 1, 17),
                                dt(2026, 6, 2, 9), dt(2026, 6, 2, 13)])

    def test_naive_start_treated_as_utc(self):
        runs = next_runs("0 * * * *", datetime(2026, 1, 1, 10, 15), 1)
        self.assertEqual(runs, [dt(2026, 1, 1, 11)])
        self.assertEqual(runs[0].tzinfo, UTC)

    def test_aware_start_converted_to_utc(self):
        rome = timezone(timedelta(hours=1))
        start = datetime(2026, 1, 1, 10, 15, tzinfo=rome)  # 09:15 UTC
        runs = next_runs("0 * * * *", start, 1)
        self.assertEqual(runs, [dt(2026, 1, 1, 10)])
        self.assertEqual(runs[0].utcoffset(), timedelta(0))

    def test_results_match_and_are_increasing(self):
        expr = "*/7 1,13 */3 1-6 *"
        c = parse(expr)
        runs = next_runs(expr, dt(2026, 1, 1), 50)
        self.assertEqual(len(runs), 50)
        self.assertEqual(runs, sorted(set(runs)))
        for r in runs:
            self.assertTrue(c.matches(r), r)

    def test_count_zero_and_negative(self):
        self.assertEqual(next_runs("* * * * *", dt(2026, 1, 1), 0), [])
        with self.assertRaises(ValueError):
            next_runs("* * * * *", dt(2026, 1, 1), -1)

    def test_impossible_date_with_weekday_is_still_valid(self):
        # 30 febbraio non esiste, ma con OR sul giorno della settimana
        # l'espressione corrisponde a tutte le domeniche di febbraio.
        runs = next_runs("0 0 30 2 0", dt(2026, 1, 1), 2)
        self.assertEqual(runs, [dt(2026, 2, 1), dt(2026, 2, 8)])


if __name__ == "__main__":
    unittest.main()
