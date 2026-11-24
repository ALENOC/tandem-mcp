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
        self.assertEqual(c.days, frozenset(range(1, 32)))
        self.assertEqual(c.months, frozenset(range(1, 13)))
        self.assertEqual(c.weekdays, frozenset(range(7)))

    def test_number_range_list(self):
        c = parse("5 1-3 1,15,31 * *")
        self.assertEqual(c.minutes, {5})
        self.assertEqual(c.hours, {1, 2, 3})
        self.assertEqual(c.days, {1, 15, 31})

    def test_steps(self):
        c = parse("*/15 0-12/4 */10 * *")
        self.assertEqual(c.minutes, {0, 15, 30, 45})
        self.assertEqual(c.hours, {0, 4, 8, 12})
        self.assertEqual(c.days, {1, 11, 21, 31})

    def test_mixed_list(self):
        c = parse("1,10-12,*/20 * * * *")
        self.assertEqual(c.minutes, {0, 1, 10, 11, 12, 20, 40})

    def test_sunday_7_normalized(self):
        self.assertEqual(parse("0 0 * * 7").weekdays, {0})
        self.assertEqual(parse("0 0 * * 5-7").weekdays, {0, 5, 6})

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
            "1,,2 * * * *",
            "-1 * * * *",
            "1-2-3 * * * *",
            "*/2/3 * * * *",
            "1- * * * *",
            "*/-1 * * * *",
        ]
        for expr in bad:
            with self.subTest(expr=expr):
                with self.assertRaises(ValueError):
                    parse(expr)

    def test_non_string(self):
        with self.assertRaises(ValueError):
            parse(None)


class TestNextRuns(unittest.TestCase):
    def test_every_minute_strictly_after(self):
        res = next_runs("* * * * *", dt(2026, 1, 1, 10, 0))
        self.assertEqual(res, [dt(2026, 1, 1, 10, m) for m in range(1, 6)])

    def test_seconds_truncated(self):
        res = next_runs("* * * * *", datetime(2026, 1, 1, 10, 0, 30, 123), count=2)
        self.assertEqual(res, [dt(2026, 1, 1, 10, 1), dt(2026, 1, 1, 10, 2)])

    def test_default_count_and_utc(self):
        res = next_runs("0 * * * *", dt(2026, 1, 1, 0, 0))
        self.assertEqual(len(res), 5)
        for r in res:
            self.assertEqual(r.tzinfo, UTC)
        self.assertEqual(res[0], dt(2026, 1, 1, 1, 0))

    def test_step_minutes_across_hour(self):
        res = next_runs("*/20 * * * *", dt(2026, 3, 10, 23, 50), count=4)
        self.assertEqual(res, [
            dt(2026, 3, 11, 0, 0), dt(2026, 3, 11, 0, 20),
            dt(2026, 3, 11, 0, 40), dt(2026, 3, 11, 1, 0),
        ])

    def test_range_step_hours(self):
        res = next_runs("30 9-17/4 * * *", dt(2026, 5, 1, 12, 0), count=4)
        self.assertEqual(res, [
            dt(2026, 5, 1, 13, 30), dt(2026, 5, 1, 17, 30),
            dt(2026, 5, 2, 9, 30), dt(2026, 5, 2, 13, 30),
        ])

    def test_year_rollover(self):
        res = next_runs("0 0 1 1 *", dt(2026, 6, 1, 0, 0), count=2)
        self.assertEqual(res, [dt(2027, 1, 1), dt(2028, 1, 1)])

    def test_leap_day(self):
        res = next_runs("0 12 29 2 *", dt(2026, 11, 24), count=2)
        self.assertEqual(res, [dt(2028, 2, 29, 12), dt(2032, 2, 29, 12)])

    def test_day_31_skips_short_months(self):
        res = next_runs("0 0 31 * *", dt(2026, 1, 31, 0, 0), count=3)
        self.assertEqual(res, [dt(2026, 3, 31), dt(2026, 5, 31), dt(2026, 7, 31)])

    def test_weekday(self):
        # 2026-11-24 e' martedi'; lunedi'-venerdi' alle 9:00
        res = next_runs("0 9 * * 1-5", dt(2026, 11, 27, 10, 0), count=3)
        self.assertEqual(res, [dt(2026, 11, 30, 9), dt(2026, 12, 1, 9), dt(2026, 12, 2, 9)])

    def test_sunday_0_and_7_equivalent(self):
        start = dt(2026, 11, 24)
        self.assertEqual(next_runs("0 0 * * 0", start), next_runs("0 0 * * 7", start))
        self.assertEqual(next_runs("0 0 * * 0", start, count=1), [dt(2026, 11, 29)])

    def test_dom_dow_or_semantics(self):
        # Giorno 1 del mese OPPURE lunedi'
        res = next_runs("0 0 1 * 1", dt(2026, 11, 24), count=3)
        self.assertEqual(res, [dt(2026, 11, 30), dt(2026, 12, 1), dt(2026, 12, 7)])

    def test_aware_non_utc_start_converted(self):
        cet = timezone(timedelta(hours=1))
        start = datetime(2026, 1, 1, 10, 0, tzinfo=cet)  # 09:00 UTC
        res = next_runs("0 * * * *", start, count=1)
        self.assertEqual(res, [dt(2026, 1, 1, 10, 0)])

    def test_count_zero(self):
        self.assertEqual(next_runs("* * * * *", dt(2026, 1, 1), count=0), [])

    def test_invalid_count(self):
        with self.assertRaises(ValueError):
            next_runs("* * * * *", dt(2026, 1, 1), count=-1)

    def test_invalid_expr_raises(self):
        with self.assertRaises(ValueError):
            next_runs("61 * * * *", dt(2026, 1, 1))

    def test_impossible_date_raises(self):
        with self.assertRaises(ValueError):
            next_runs("0 0 30 2 *", dt(2026, 1, 1))

    def test_results_strictly_increasing_and_match(self):
        expr = "7,37 */3 */2 1-6 *"
        c = parse(expr)
        start = dt(2026, 1, 1)
        res = next_runs(expr, start, count=50)
        self.assertEqual(len(res), 50)
        prev = start
        for r in res:
            self.assertGreater(r, prev)
            self.assertTrue(c.matches(r))
            prev = r


if __name__ == "__main__":
    unittest.main()
