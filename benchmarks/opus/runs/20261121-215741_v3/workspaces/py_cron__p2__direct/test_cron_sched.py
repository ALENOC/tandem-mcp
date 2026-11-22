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
        c = parse("5 1-3 1,15,31 6 0")
        self.assertEqual(c.minutes, {5})
        self.assertEqual(c.hours, {1, 2, 3})
        self.assertEqual(c.days_of_month, {1, 15, 31})
        self.assertEqual(c.months, {6})
        self.assertEqual(c.days_of_week, {0})

    def test_steps(self):
        c = parse("*/15 0-10/5 * * *")
        self.assertEqual(c.minutes, {0, 15, 30, 45})
        self.assertEqual(c.hours, {0, 5, 10})

    def test_mixed_list_with_ranges_and_steps(self):
        c = parse("1,10-12,50-59/4 * * * *")
        self.assertEqual(c.minutes, {1, 10, 11, 12, 50, 54, 58})

    def test_sunday_as_seven(self):
        self.assertEqual(parse("* * * * 7").days_of_week, {0})

    def test_invalid_expressions(self):
        bad = [
            "", "* * * *", "* * * * * *", "60 * * * *", "* 24 * * *",
            "* * 0 * *", "* * 32 * *", "* * * 0 *", "* * * 13 *",
            "* * * * 8", "5-1 * * * *", "*/0 * * * *", "a * * * *",
            "1,,2 * * * *", "-1 * * * *", "*/ * * * *", "1-2-3 * * * *",
            "1.5 * * * *", "* * * * */-1",
        ]
        for expr in bad:
            with self.subTest(expr=expr):
                with self.assertRaises(ValueError):
                    parse(expr)

    def test_non_string_raises(self):
        with self.assertRaises(ValueError):
            parse(None)


class TestNextRuns(unittest.TestCase):
    def test_every_minute_strictly_after_start(self):
        runs = next_runs("* * * * *", dt(2026, 1, 1, 12, 0, 30))
        self.assertEqual(runs, [dt(2026, 1, 1, 12, m) for m in range(1, 6)])

    def test_start_exactly_on_match_is_excluded(self):
        runs = next_runs("0 * * * *", dt(2026, 1, 1, 12, 0), count=2)
        self.assertEqual(runs, [dt(2026, 1, 1, 13, 0), dt(2026, 1, 1, 14, 0)])

    def test_default_count_is_five(self):
        self.assertEqual(len(next_runs("*/5 * * * *", dt(2026, 1, 1))), 5)

    def test_step_minutes_cross_hour(self):
        runs = next_runs("*/20 * * * *", dt(2026, 3, 1, 10, 41), count=4)
        self.assertEqual(runs, [dt(2026, 3, 1, 11, 0), dt(2026, 3, 1, 11, 20),
                                dt(2026, 3, 1, 11, 40), dt(2026, 3, 1, 12, 0)])

    def test_year_rollover(self):
        runs = next_runs("0 0 1 1 *", dt(2026, 6, 15), count=3)
        self.assertEqual(runs, [dt(2027, 1, 1), dt(2028, 1, 1), dt(2029, 1, 1)])

    def test_leap_day(self):
        runs = next_runs("0 12 29 2 *", dt(2026, 1, 1), count=2)
        self.assertEqual(runs, [dt(2028, 2, 29, 12), dt(2032, 2, 29, 12)])

    def test_day_31_skips_short_months(self):
        runs = next_runs("0 0 31 * *", dt(2026, 1, 31), count=3)
        self.assertEqual(runs, [dt(2026, 3, 31), dt(2026, 5, 31),
                                dt(2026, 7, 31)])

    def test_weekdays_range(self):
        # 2026-11-20 è venerdì: dal venerdì sera salta al lunedì
        runs = next_runs("30 9 * * 1-5", dt(2026, 11, 20, 10, 0), count=3)
        self.assertEqual(runs, [dt(2026, 11, 23, 9, 30), dt(2026, 11, 24, 9, 30),
                                dt(2026, 11, 25, 9, 30)])
        for r in runs:
            self.assertLess(r.weekday(), 5)

    def test_dom_or_dow_when_both_restricted(self):
        # giorno 1 del mese OPPURE domenica
        runs = next_runs("0 0 1 * 0", dt(2026, 11, 25), count=3)
        self.assertEqual(runs, [dt(2026, 11, 29), dt(2026, 12, 1),
                                dt(2026, 12, 6)])

    def test_hour_range_with_step(self):
        runs = next_runs("0 8-18/5 * * *", dt(2026, 5, 5, 9), count=4)
        self.assertEqual(runs, [dt(2026, 5, 5, 13), dt(2026, 5, 5, 18),
                                dt(2026, 5, 6, 8), dt(2026, 5, 6, 13)])

    def test_results_are_utc_aware_and_increasing(self):
        runs = next_runs("*/7 */3 * * *", dt(2026, 1, 1), count=20)
        for r in runs:
            self.assertEqual(r.utcoffset(), timedelta(0))
            self.assertEqual(r.second, 0)
        self.assertEqual(runs, sorted(set(runs)))

    def test_aware_non_utc_start_converted(self):
        cet = timezone(timedelta(hours=1))
        start = datetime(2026, 1, 1, 10, 0, tzinfo=cet)  # 09:00 UTC
        runs = next_runs("0 10 * * *", start, count=1)
        self.assertEqual(runs, [dt(2026, 1, 1, 10, 0)])

    def test_naive_start_treated_as_utc(self):
        runs = next_runs("15 3 * * *", datetime(2026, 2, 2, 3, 14), count=1)
        self.assertEqual(runs, [dt(2026, 2, 2, 3, 15)])

    def test_count_zero_and_negative(self):
        self.assertEqual(next_runs("* * * * *", dt(2026, 1, 1), count=0), [])
        with self.assertRaises(ValueError):
            next_runs("* * * * *", dt(2026, 1, 1), count=-1)

    def test_invalid_expression_raises(self):
        with self.assertRaises(ValueError):
            next_runs("61 * * * *", dt(2026, 1, 1))
        with self.assertRaises(ValueError):
            next_runs("* * * * * *", dt(2026, 1, 1), count=0)

    def test_impossible_date_raises(self):
        with self.assertRaises(ValueError):
            next_runs("0 0 30 2 *", dt(2026, 1, 1))

    def test_matches_brute_force(self):
        expr = "5-50/15 2,14 */10 * 1,3,5"
        start = dt(2026, 1, 1)
        expected, cur = [], start
        cron = parse(expr)
        while len(expected) < 10:
            cur += timedelta(minutes=1)
            if cron.matches(cur):
                expected.append(cur)
        self.assertEqual(next_runs(expr, start, count=10), expected)


if __name__ == "__main__":
    unittest.main()
