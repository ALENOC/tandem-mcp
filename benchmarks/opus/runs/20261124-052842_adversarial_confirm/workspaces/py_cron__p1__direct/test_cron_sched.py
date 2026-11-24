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
        c = parse("5 1-3 1,15,31 6 *")
        self.assertEqual(c.minutes, {5})
        self.assertEqual(c.hours, {1, 2, 3})
        self.assertEqual(c.days, {1, 15, 31})
        self.assertEqual(c.months, {6})

    def test_steps(self):
        c = parse("*/15 0-10/5 */10 * *")
        self.assertEqual(c.minutes, {0, 15, 30, 45})
        self.assertEqual(c.hours, {0, 5, 10})
        self.assertEqual(c.days, {1, 11, 21, 31})

    def test_mixed_list_with_steps(self):
        c = parse("1,10-12,50-59/4 * * * *")
        self.assertEqual(c.minutes, {1, 10, 11, 12, 50, 54, 58})

    def test_sunday_as_7(self):
        self.assertEqual(parse("0 0 * * 7").weekdays, {0})
        self.assertEqual(parse("0 0 * * 5-7").weekdays, {5, 6, 0})

    def test_invalid_expressions(self):
        bad = [
            "", "* * * *", "* * * * * *", "60 * * * *", "* 24 * * *",
            "* * 0 * *", "* * 32 * *", "* * * 0 *", "* * * 13 *",
            "* * * * 8", "5-1 * * * *", "*/0 * * * *", "a * * * *",
            "1,,2 * * * *", "1- * * * *", "-1 * * * *", "*/ * * * *",
            "1/2/3 * * * *", "** * * * *", "*-5 * * * *", "+1 * * * *",
            "0 0 30 2 *", "0 0 31 4,6,9,11 *",
        ]
        for expr in bad:
            with self.subTest(expr=expr):
                with self.assertRaises(ValueError):
                    parse(expr)
                with self.assertRaises(ValueError):
                    next_runs(expr, dt(2024, 1, 1))

    def test_non_string_raises_value_error(self):
        with self.assertRaises(ValueError):
            next_runs(None, dt(2024, 1, 1))


class TestNextRuns(unittest.TestCase):
    def test_every_minute_strictly_after_start(self):
        start = dt(2024, 1, 1, 12, 0, 0)
        self.assertEqual(
            next_runs("* * * * *", start, 3),
            [dt(2024, 1, 1, 12, 1), dt(2024, 1, 1, 12, 2), dt(2024, 1, 1, 12, 3)],
        )

    def test_start_with_seconds(self):
        start = dt(2024, 1, 1, 12, 0, 30, 500)
        self.assertEqual(next_runs("* * * * *", start, 1), [dt(2024, 1, 1, 12, 1)])

    def test_default_count_is_five(self):
        runs = next_runs("*/10 * * * *", dt(2024, 1, 1, 0, 5))
        self.assertEqual(
            runs,
            [dt(2024, 1, 1, 0, m) for m in (10, 20, 30, 40, 50)],
        )

    def test_rollover_hour_day_month_year(self):
        start = dt(2023, 12, 31, 23, 59)
        self.assertEqual(
            next_runs("0 0 * * *", start, 2),
            [dt(2024, 1, 1), dt(2024, 1, 2)],
        )

    def test_specific_hours_and_minutes(self):
        start = dt(2024, 3, 10, 9, 30)
        self.assertEqual(
            next_runs("0,30 9,17 * * *", start, 4),
            [dt(2024, 3, 10, 17, 0), dt(2024, 3, 10, 17, 30),
             dt(2024, 3, 11, 9, 0), dt(2024, 3, 11, 9, 30)],
        )

    def test_day_31_skips_short_months(self):
        runs = next_runs("0 0 31 * *", dt(2024, 1, 31), 3)
        self.assertEqual(runs, [dt(2024, 3, 31), dt(2024, 5, 31), dt(2024, 7, 31)])

    def test_leap_day(self):
        runs = next_runs("0 0 29 2 *", dt(2024, 3, 1), 2)
        self.assertEqual(runs, [dt(2028, 2, 29), dt(2032, 2, 29)])
        # 2100 non è bisestile
        self.assertEqual(next_runs("0 0 29 2 *", dt(2096, 3, 1), 1), [dt(2104, 2, 29)])

    def test_weekday(self):
        # 2024-01-01 è lunedì
        runs = next_runs("30 8 * * 1-5", dt(2024, 1, 5, 9, 0), 3)
        self.assertEqual(runs, [dt(2024, 1, 8, 8, 30), dt(2024, 1, 9, 8, 30),
                                dt(2024, 1, 10, 8, 30)])
        sundays = next_runs("0 12 * * 0", dt(2024, 1, 1), 2)
        self.assertEqual(sundays, [dt(2024, 1, 7, 12), dt(2024, 1, 14, 12)])
        self.assertEqual(next_runs("0 12 * * 7", dt(2024, 1, 1), 2), sundays)

    def test_dom_or_dow_when_both_restricted(self):
        # giorno 13 OPPURE venerdì
        runs = next_runs("0 0 13 * 5", dt(2024, 9, 1), 4)
        self.assertEqual(runs, [dt(2024, 9, 6), dt(2024, 9, 13),
                                dt(2024, 9, 20), dt(2024, 9, 27)])

    def test_dom_and_dow_when_one_is_star(self):
        # dom con step che inizia con '*' -> semantica AND
        runs = next_runs("0 0 */10 * 1", dt(2024, 1, 1), 2)
        for r in runs:
            self.assertEqual(r.weekday(), 0)
            self.assertIn(r.day, {1, 11, 21, 31})
        self.assertEqual(runs, [dt(2024, 3, 11), dt(2024, 4, 1)])

    def test_month_list_and_range_step(self):
        runs = next_runs("15 6 1 1-12/3 *", dt(2024, 2, 1), 4)
        self.assertEqual(runs, [dt(2024, 4, 1, 6, 15), dt(2024, 7, 1, 6, 15),
                                dt(2024, 10, 1, 6, 15), dt(2025, 1, 1, 6, 15)])

    def test_timezone_handling(self):
        naive = datetime(2024, 1, 1, 10, 0)
        self.assertEqual(next_runs("0 * * * *", naive, 1), [dt(2024, 1, 1, 11, 0)])
        plus2 = timezone(timedelta(hours=2))
        aware = datetime(2024, 1, 1, 12, 0, tzinfo=plus2)  # = 10:00 UTC
        res = next_runs("0 * * * *", aware, 1)
        self.assertEqual(res, [dt(2024, 1, 1, 11, 0)])
        self.assertEqual(res[0].tzinfo, UTC)

    def test_count_values(self):
        self.assertEqual(next_runs("* * * * *", dt(2024, 1, 1), 0), [])
        self.assertEqual(len(next_runs("* * * * *", dt(2024, 1, 1), 100)), 100)
        with self.assertRaises(ValueError):
            next_runs("* * * * *", dt(2024, 1, 1), -1)
        with self.assertRaises(ValueError):
            next_runs("bad", dt(2024, 1, 1), 0)

    def test_results_strictly_increasing_and_match(self):
        expr = "*/7 */5 1-10,20 * 2,4"
        c = parse(expr)
        runs = next_runs(expr, dt(2024, 5, 17, 13, 37), 50)
        self.assertEqual(len(runs), 50)
        for a, b in zip(runs, runs[1:]):
            self.assertLess(a, b)
        for r in runs:
            self.assertTrue(c.matches(r))

    def test_against_brute_force(self):
        exprs = ["*/7 */5 1-10,20 * 2,4", "0 0 13 * 5", "5-50/9 3,22 * 2-4 *",
                 "59 23 31 1,3,12 *", "0 12 */3 * 0"]
        for expr in exprs:
            with self.subTest(expr=expr):
                c = parse(expr)
                start = dt(2024, 2, 27, 22, 58)
                expected, cur = [], start
                while len(expected) < 8:
                    cur += timedelta(minutes=1)
                    if c.matches(cur):
                        expected.append(cur)
                    if cur.year > 2026:
                        break
                self.assertEqual(next_runs(expr, start, len(expected)), expected)


if __name__ == "__main__":
    unittest.main()
