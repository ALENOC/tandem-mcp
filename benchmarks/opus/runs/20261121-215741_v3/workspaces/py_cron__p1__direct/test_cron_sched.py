import unittest
from datetime import datetime, timedelta, timezone

from cron_sched import next_runs, parse

UTC = timezone.utc


def dt(*a):
    return datetime(*a, tzinfo=UTC)


class TestParse(unittest.TestCase):
    def test_star(self):
        c = parse("* * * * *")
        self.assertEqual(c.minutes, frozenset(range(60)))
        self.assertEqual(c.hours, frozenset(range(24)))
        self.assertEqual(c.weekdays, frozenset(range(7)))

    def test_number_range_list(self):
        c = parse("5 1-3 1,15,31 2-4 *")
        self.assertEqual(c.minutes, {5})
        self.assertEqual(c.hours, {1, 2, 3})
        self.assertEqual(c.days, {1, 15, 31})
        self.assertEqual(c.months, {2, 3, 4})

    def test_steps(self):
        c = parse("*/15 0-10/5 */10 * *")
        self.assertEqual(c.minutes, {0, 15, 30, 45})
        self.assertEqual(c.hours, {0, 5, 10})
        self.assertEqual(c.days, {1, 11, 21, 31})

    def test_mixed_list_with_steps(self):
        c = parse("1,10-20/5,*/30 * * * *")
        self.assertEqual(c.minutes, {0, 1, 10, 15, 20, 30})

    def test_sunday_as_7(self):
        self.assertEqual(parse("0 0 * * 7").weekdays, {0})
        self.assertEqual(parse("0 0 * * 5-7").weekdays, {5, 6, 0})

    def test_invalid_expressions(self):
        bad = [
            "", "* * * *", "* * * * * *", "60 * * * *", "* 24 * * *",
            "* * 0 * *", "* * 32 * *", "* * * 0 *", "* * * 13 *",
            "* * * * 8", "5-1 * * * *", "*/0 * * * *", "a * * * *",
            "1,,2 * * * *", "-1 * * * *", "1- * * * *", "*/ * * * *",
            "1/2/3 * * * *", "** * * * *", "1.5 * * * *",
        ]
        for e in bad:
            with self.subTest(expr=e):
                with self.assertRaises(ValueError):
                    parse(e)

    def test_non_string(self):
        with self.assertRaises(ValueError):
            parse(None)


class TestNextRuns(unittest.TestCase):
    def test_every_minute_strictly_after(self):
        runs = next_runs("* * * * *", dt(2026, 1, 1, 10, 0), 3)
        self.assertEqual(runs, [dt(2026, 1, 1, 10, 1), dt(2026, 1, 1, 10, 2),
                                dt(2026, 1, 1, 10, 3)])

    def test_seconds_truncated(self):
        runs = next_runs("* * * * *", dt(2026, 1, 1, 10, 0, 30, 5), 1)
        self.assertEqual(runs, [dt(2026, 1, 1, 10, 1)])

    def test_default_count_is_5(self):
        runs = next_runs("*/15 * * * *", dt(2026, 1, 1, 23, 20))
        self.assertEqual(runs, [dt(2026, 1, 1, 23, 30), dt(2026, 1, 1, 23, 45),
                                dt(2026, 1, 2, 0, 0), dt(2026, 1, 2, 0, 15),
                                dt(2026, 1, 2, 0, 30)])

    def test_year_rollover(self):
        runs = next_runs("0 0 1 1 *", dt(2026, 6, 1), 2)
        self.assertEqual(runs, [dt(2027, 1, 1), dt(2028, 1, 1)])

    def test_leap_day(self):
        runs = next_runs("0 12 29 2 *", dt(2026, 11, 21), 2)
        self.assertEqual(runs, [dt(2028, 2, 29, 12), dt(2032, 2, 29, 12)])

    def test_day_31_skips_short_months(self):
        runs = next_runs("0 0 31 * *", dt(2026, 1, 31), 3)
        self.assertEqual(runs, [dt(2026, 3, 31), dt(2026, 5, 31), dt(2026, 7, 31)])

    def test_weekday(self):
        # 2026-11-21 è sabato; lun-ven alle 9:00
        runs = next_runs("0 9 * * 1-5", dt(2026, 11, 21), 3)
        self.assertEqual(runs, [dt(2026, 11, 23, 9), dt(2026, 11, 24, 9),
                                dt(2026, 11, 25, 9)])
        for r in runs:
            self.assertLess(r.weekday(), 5)

    def test_dom_or_dow(self):
        # giorno 1 del mese OPPURE domenica
        runs = next_runs("0 0 1 * 0", dt(2026, 11, 21), 3)
        self.assertEqual(runs, [dt(2026, 11, 22), dt(2026, 11, 29), dt(2026, 12, 1)])

    def test_dst_irrelevant_and_aware_input_converted(self):
        tz = timezone(timedelta(hours=2))
        start = datetime(2026, 3, 29, 3, 0, tzinfo=tz)  # = 01:00 UTC
        runs = next_runs("30 1 * * *", start, 2)
        self.assertEqual(runs, [dt(2026, 3, 29, 1, 30), dt(2026, 3, 30, 1, 30)])
        for r in runs:
            self.assertEqual(r.utcoffset(), timedelta(0))

    def test_naive_treated_as_utc(self):
        runs = next_runs("0 * * * *", datetime(2026, 1, 1, 5, 59), 1)
        self.assertEqual(runs, [dt(2026, 1, 1, 6, 0)])
        self.assertIs(runs[0].tzinfo, UTC)

    def test_results_strictly_increasing_and_match(self):
        expr = "*/7 1-23/3 1-15 1,6,12 1-5"
        runs = next_runs(expr, dt(2026, 1, 1), 50)
        c = parse(expr)
        self.assertEqual(len(runs), 50)
        for a, b in zip(runs, runs[1:]):
            self.assertLess(a, b)
        for r in runs:
            self.assertTrue(c.matches(r))

    def test_impossible_date_raises(self):
        with self.assertRaises(ValueError):
            next_runs("0 0 30 2 *", dt(2026, 1, 1), 1)

    def test_invalid_expr_and_count(self):
        with self.assertRaises(ValueError):
            next_runs("bad", dt(2026, 1, 1))
        with self.assertRaises(ValueError):
            next_runs("* * * * *", dt(2026, 1, 1), -1)
        with self.assertRaises(ValueError):
            next_runs("* * * * *", "2026-01-01")
        self.assertEqual(next_runs("* * * * *", dt(2026, 1, 1), 0), [])


if __name__ == "__main__":
    unittest.main()
