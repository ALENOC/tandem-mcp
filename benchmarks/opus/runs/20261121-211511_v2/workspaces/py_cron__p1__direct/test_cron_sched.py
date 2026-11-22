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
        self.assertEqual(c.weekdays, frozenset(range(7)))

    def test_numbers_ranges_lists(self):
        c = parse("5 1-3 1,15,31 6 *")
        self.assertEqual(c.minutes, {5})
        self.assertEqual(c.hours, {1, 2, 3})
        self.assertEqual(c.days, {1, 15, 31})
        self.assertEqual(c.months, {6})

    def test_steps(self):
        c = parse("*/15 10-20/5 * * *")
        self.assertEqual(c.minutes, {0, 15, 30, 45})
        self.assertEqual(c.hours, {10, 15, 20})

    def test_mixed_list(self):
        c = parse("1,10-12,*/30 * * * *")
        self.assertEqual(c.minutes, {0, 1, 10, 11, 12, 30})

    def test_weekday_seven_is_sunday(self):
        self.assertEqual(parse("0 0 * * 7").weekdays, {0})
        self.assertEqual(parse("0 0 * * 0,7").weekdays, {0})

    def test_invalid_expressions(self):
        bad = [
            "", "* * * *", "* * * * * *", "60 * * * *", "* 24 * * *",
            "* * 0 * *", "* * 32 * *", "* * * 0 *", "* * * 13 *",
            "* * * * 8", "*/0 * * * *", "5-1 * * * *", "a * * * *",
            "1,,2 * * * *", "-1 * * * *", "1- * * * *", "*/ * * * *",
            "5/2 * * * *", "1.5 * * * *", "0 0 30 2 *", "0 0 31 4,6 *",
            "*/-1 * * * *", "1-2-3 * * * *",
        ]
        for expr in bad:
            with self.subTest(expr=expr):
                with self.assertRaises(ValueError):
                    parse(expr)

    def test_next_runs_invalid_raises(self):
        with self.assertRaises(ValueError):
            next_runs("bogus", dt(2026, 1, 1))
        with self.assertRaises(ValueError):
            next_runs("* * * * *", dt(2026, 1, 1), count=-1)


class TestNextRuns(unittest.TestCase):
    def test_every_minute_strictly_after(self):
        runs = next_runs("* * * * *", dt(2026, 1, 1, 12, 0, 0))
        self.assertEqual(runs, [dt(2026, 1, 1, 12, m) for m in range(1, 6)])

    def test_seconds_truncated(self):
        runs = next_runs("* * * * *", dt(2026, 1, 1, 12, 0, 30), count=2)
        self.assertEqual(runs, [dt(2026, 1, 1, 12, 1), dt(2026, 1, 1, 12, 2)])

    def test_default_count_and_custom_count(self):
        self.assertEqual(len(next_runs("*/5 * * * *", dt(2026, 1, 1))), 5)
        self.assertEqual(len(next_runs("*/5 * * * *", dt(2026, 1, 1), 12)), 12)
        self.assertEqual(next_runs("*/5 * * * *", dt(2026, 1, 1), 0), [])

    def test_daily_rollover(self):
        runs = next_runs("30 9 * * *", dt(2026, 3, 10, 9, 30), count=3)
        self.assertEqual(runs, [dt(2026, 3, 11, 9, 30), dt(2026, 3, 12, 9, 30),
                                dt(2026, 3, 13, 9, 30)])

    def test_year_rollover(self):
        runs = next_runs("0 0 1 1 *", dt(2026, 6, 1), count=2)
        self.assertEqual(runs, [dt(2027, 1, 1), dt(2028, 1, 1)])

    def test_leap_day(self):
        runs = next_runs("0 12 29 2 *", dt(2026, 1, 1), count=2)
        self.assertEqual(runs, [dt(2028, 2, 29, 12), dt(2032, 2, 29, 12)])

    def test_day_31_skips_short_months(self):
        runs = next_runs("0 0 31 * *", dt(2026, 1, 31), count=3)
        self.assertEqual(runs, [dt(2026, 3, 31), dt(2026, 5, 31), dt(2026, 7, 31)])

    def test_weekday(self):
        # 2026-11-21 è sabato; i lunedì successivi sono 23 e 30.
        runs = next_runs("0 8 * * 1", dt(2026, 11, 21), count=2)
        self.assertEqual(runs, [dt(2026, 11, 23, 8), dt(2026, 11, 30, 8)])
        for r in runs:
            self.assertEqual(r.weekday(), 0)

    def test_weekday_range_workdays(self):
        runs = next_runs("0 9 * * 1-5", dt(2026, 11, 20, 10), count=3)
        # ven 20 dopo le 9 -> lun 23, mar 24, mer 25
        self.assertEqual(runs, [dt(2026, 11, 23, 9), dt(2026, 11, 24, 9),
                                dt(2026, 11, 25, 9)])

    def test_dom_or_dow(self):
        # giorno 1 del mese OPPURE domenica
        runs = next_runs("0 0 1 * 0", dt(2026, 11, 21), count=3)
        self.assertEqual(runs, [dt(2026, 11, 22), dt(2026, 11, 29), dt(2026, 12, 1)])

    def test_impossible_dom_rescued_by_dow(self):
        # 30 febbraio non esiste, ma con la regola OR valgono i lunedì di febbraio
        runs = next_runs("0 0 30 2 1", dt(2026, 1, 1), count=1)
        self.assertEqual(runs, [dt(2026, 2, 2)])

    def test_step_range_hours(self):
        runs = next_runs("0 10-20/5 * * *", dt(2026, 1, 1, 11), count=4)
        self.assertEqual(runs, [dt(2026, 1, 1, 15), dt(2026, 1, 1, 20),
                                dt(2026, 1, 2, 10), dt(2026, 1, 2, 15)])

    def test_results_are_utc_and_increasing(self):
        runs = next_runs("*/7 */3 * * *", dt(2026, 1, 1), count=50)
        for r in runs:
            self.assertEqual(r.utcoffset(), timedelta(0))
        self.assertEqual(runs, sorted(set(runs)))

    def test_naive_and_aware_start(self):
        naive = next_runs("0 * * * *", datetime(2026, 1, 1, 10, 15), count=1)
        self.assertEqual(naive, [dt(2026, 1, 1, 11)])
        rome = timezone(timedelta(hours=1))
        aware = next_runs("0 * * * *", datetime(2026, 1, 1, 10, 15, tzinfo=rome), count=1)
        self.assertEqual(aware, [dt(2026, 1, 1, 10)])

    def test_month_end_rollover(self):
        runs = next_runs("59 23 * * *", dt(2026, 12, 31, 23, 58), count=2)
        self.assertEqual(runs, [dt(2026, 12, 31, 23, 59), dt(2027, 1, 1, 23, 59)])


if __name__ == "__main__":
    unittest.main()
