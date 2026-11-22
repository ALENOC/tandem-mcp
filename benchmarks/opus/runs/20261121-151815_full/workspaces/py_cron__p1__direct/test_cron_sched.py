import unittest
from datetime import datetime, timedelta, timezone

from cron_sched import iter_runs, next_runs, parse

UTC = timezone.utc


def dt(*args):
    return datetime(*args, tzinfo=UTC)


class ParseTests(unittest.TestCase):
    def test_star(self):
        c = parse("* * * * *")
        self.assertEqual(c.minutes, frozenset(range(60)))
        self.assertEqual(c.hours, frozenset(range(24)))
        self.assertEqual(c.days_of_week, frozenset(range(7)))

    def test_list_range_and_steps(self):
        c = parse("1,5,10 9-17 */10 1-12/3 1-5")
        self.assertEqual(c.minutes, {1, 5, 10})
        self.assertEqual(c.hours, set(range(9, 18)))
        self.assertEqual(c.days_of_month, {1, 11, 21, 31})
        self.assertEqual(c.months, {1, 4, 7, 10})
        self.assertEqual(c.days_of_week, {1, 2, 3, 4, 5})

    def test_step_minutes(self):
        self.assertEqual(parse("*/15 * * * *").minutes, {0, 15, 30, 45})

    def test_sunday_seven_equals_zero(self):
        self.assertEqual(parse("0 0 * * 7").days_of_week, {0})

    def test_invalid_expressions(self):
        bad = [
            "", "* * * *", "* * * * * *", "60 * * * *", "* 24 * * *",
            "* * 0 * *", "* * 32 * *", "* * * 13 *", "* * * * 8",
            "*/0 * * * *", "5-1 * * * *", "a * * * *", "1,,2 * * * *",
            "5/2 * * * *", "1-2-3 * * * *", "-1 * * * *", "*/x * * * *",
            "1-5/2/3 * * * *", "1, * * * *",
        ]
        for expr in bad:
            with self.subTest(expr=expr):
                with self.assertRaises(ValueError):
                    parse(expr)

    def test_non_string_raises(self):
        with self.assertRaises(ValueError):
            parse(None)


class NextRunsTests(unittest.TestCase):
    def test_every_minute_default_count(self):
        runs = next_runs("* * * * *", dt(2026, 1, 1, 12, 0, 30))
        self.assertEqual(len(runs), 5)
        self.assertEqual(runs[0], dt(2026, 1, 1, 12, 1))
        self.assertEqual(runs[-1], dt(2026, 1, 1, 12, 5))

    def test_strictly_after_start(self):
        runs = next_runs("0 * * * *", dt(2026, 1, 1, 12, 0), count=2)
        self.assertEqual(runs, [dt(2026, 1, 1, 13, 0), dt(2026, 1, 1, 14, 0)])

    def test_step_every_15(self):
        runs = next_runs("*/15 * * * *", dt(2026, 3, 1, 10, 7), count=4)
        self.assertEqual(
            runs,
            [dt(2026, 3, 1, 10, 15), dt(2026, 3, 1, 10, 30),
             dt(2026, 3, 1, 10, 45), dt(2026, 3, 1, 11, 0)],
        )

    def test_rollover_year(self):
        runs = next_runs("30 23 31 12 *", dt(2026, 12, 31, 23, 30), count=2)
        self.assertEqual(runs, [dt(2027, 12, 31, 23, 30), dt(2028, 12, 31, 23, 30)])

    def test_weekdays_only(self):
        # 2026-11-21 è sabato
        runs = next_runs("0 9 * * 1-5", dt(2026, 11, 21, 0, 0), count=3)
        self.assertEqual(
            runs, [dt(2026, 11, 23, 9), dt(2026, 11, 24, 9), dt(2026, 11, 25, 9)]
        )
        for r in runs:
            self.assertLess(r.weekday(), 5)

    def test_dom_or_dow_semantics(self):
        # giorno 1 del mese OPPURE lunedì
        runs = next_runs("0 0 1 * 1", dt(2026, 11, 25), count=3)
        # 2026-11-30 lunedì, 2026-12-01 giorno 1, 2026-12-07 lunedì
        self.assertEqual(runs, [dt(2026, 11, 30), dt(2026, 12, 1), dt(2026, 12, 7)])

    def test_leap_day(self):
        runs = next_runs("0 12 29 2 *", dt(2026, 1, 1), count=2)
        self.assertEqual(runs, [dt(2028, 2, 29, 12), dt(2032, 2, 29, 12)])

    def test_range_with_step(self):
        runs = next_runs("10-30/10 8 * * *", dt(2026, 5, 5, 8, 15), count=4)
        self.assertEqual(
            runs,
            [dt(2026, 5, 5, 8, 20), dt(2026, 5, 5, 8, 30),
             dt(2026, 5, 6, 8, 10), dt(2026, 5, 6, 8, 20)],
        )

    def test_naive_treated_as_utc_and_result_is_utc(self):
        runs = next_runs("0 0 * * *", datetime(2026, 6, 1, 5, 0), count=1)
        self.assertEqual(runs, [dt(2026, 6, 2)])
        self.assertEqual(runs[0].tzinfo, UTC)

    def test_aware_non_utc_converted(self):
        cet = timezone(timedelta(hours=1))
        # 2026-01-01 00:30+01:00 == 2025-12-31 23:30 UTC
        runs = next_runs("0 0 * * *", datetime(2026, 1, 1, 0, 30, tzinfo=cet), count=1)
        self.assertEqual(runs, [dt(2026, 1, 1)])

    def test_count_zero_and_invalid_count(self):
        self.assertEqual(next_runs("* * * * *", dt(2026, 1, 1), count=0), [])
        with self.assertRaises(ValueError):
            next_runs("* * * * *", dt(2026, 1, 1), count=-1)
        with self.assertRaises(ValueError):
            next_runs("bad", dt(2026, 1, 1), count=0)

    def test_impossible_date_raises(self):
        with self.assertRaises(ValueError):
            next_runs("0 0 30 2 *", dt(2026, 1, 1))

    def test_invalid_expression_raises(self):
        with self.assertRaises(ValueError):
            next_runs("61 * * * *", dt(2026, 1, 1))

    def test_month_end_rollover(self):
        runs = next_runs("0 0 31 * *", dt(2026, 4, 1), count=3)
        self.assertEqual(runs, [dt(2026, 5, 31), dt(2026, 7, 31), dt(2026, 8, 31)])

    def test_against_brute_force(self):
        expr = "5,35 */6 1-10/3 * 0,3"
        cron = parse(expr)
        start = dt(2026, 2, 1)
        expected = []
        cur = start + timedelta(minutes=1)
        while len(expected) < 20:
            if cron.matches(cur):
                expected.append(cur)
            cur += timedelta(minutes=1)
        self.assertEqual(next_runs(expr, start, count=20), expected)

    def test_iter_runs_is_increasing(self):
        it = iter_runs("*/7 * * * *", dt(2026, 1, 1, 23, 50))
        runs = [next(it) for _ in range(10)]
        self.assertEqual(runs, sorted(runs))
        self.assertTrue(all(r.minute % 7 == 0 for r in runs))


if __name__ == "__main__":
    unittest.main()
