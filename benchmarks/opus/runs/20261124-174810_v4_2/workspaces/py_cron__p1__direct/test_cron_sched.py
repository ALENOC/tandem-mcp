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

    def test_numbers_ranges_lists(self):
        c = parse("5 1-3 1,15,31 2-4 1,3")
        self.assertEqual(c.minutes, {5})
        self.assertEqual(c.hours, {1, 2, 3})
        self.assertEqual(c.days_of_month, {1, 15, 31})
        self.assertEqual(c.months, {2, 3, 4})
        self.assertEqual(c.days_of_week, {1, 3})

    def test_steps(self):
        c = parse("*/15 0-10/5 */10 * 1-5/2")
        self.assertEqual(c.minutes, {0, 15, 30, 45})
        self.assertEqual(c.hours, {0, 5, 10})
        self.assertEqual(c.days_of_month, {1, 11, 21, 31})
        self.assertEqual(c.days_of_week, {1, 3, 5})

    def test_mixed_list_with_ranges_and_steps(self):
        c = parse("0,10-12,50-59/5 * * * *")
        self.assertEqual(c.minutes, {0, 10, 11, 12, 50, 55})

    def test_sunday_as_7(self):
        self.assertEqual(parse("0 0 * * 7").days_of_week, {0})
        self.assertEqual(parse("0 0 * * 0,7").days_of_week, {0})

    def test_extra_whitespace_is_tolerated(self):
        self.assertEqual(parse("  0   12 * *  * ").hours, {12})


class TestInvalid(unittest.TestCase):
    INVALID = [
        "",
        "* * * *",                 # 4 campi
        "* * * * * *",             # 6 campi
        "60 * * * *",              # minuto fuori range
        "* 24 * * *",              # ora fuori range
        "* * 0 * *",               # giorno 0
        "* * 32 * *",              # giorno 32
        "* * * 0 *",               # mese 0
        "* * * 13 *",              # mese 13
        "* * * * 8",               # dow 8
        "5-1 * * * *",             # intervallo invertito
        "*/0 * * * *",             # step zero
        "*/ * * * *",              # step mancante
        "1-5/2/3 * * * *",         # step doppio
        "1,,2 * * * *",            # elemento vuoto
        "1, * * * *",              # virgola finale
        "a * * * *",               # non numerico
        "-1 * * * *",              # negativo
        "1- * * * *",              # intervallo incompleto
        "5/2 * * * *",             # step su numero singolo
        "** * * * *",
        "JAN * * * *",
    ]

    def test_invalid_expressions_raise_value_error(self):
        for expr in self.INVALID:
            with self.subTest(expr=expr):
                with self.assertRaises(ValueError):
                    parse(expr)
                with self.assertRaises(ValueError):
                    next_runs(expr, dt(2026, 1, 1))

    def test_non_string_raises_value_error(self):
        with self.assertRaises(ValueError):
            next_runs(None, dt(2026, 1, 1))

    def test_never_matching_expression_raises(self):
        with self.assertRaises(ValueError):
            next_runs("0 0 30 2 *", dt(2026, 1, 1))

    def test_invalid_count(self):
        with self.assertRaises(ValueError):
            next_runs("* * * * *", dt(2026, 1, 1), count=-1)


class TestNextRuns(unittest.TestCase):
    def test_every_minute_strictly_after_start(self):
        start = dt(2026, 11, 24, 10, 0)
        self.assertEqual(
            next_runs("* * * * *", start, 3),
            [dt(2026, 11, 24, 10, 1), dt(2026, 11, 24, 10, 2), dt(2026, 11, 24, 10, 3)],
        )

    def test_seconds_are_truncated(self):
        start = dt(2026, 11, 24, 10, 0, 59, 999999)
        self.assertEqual(next_runs("* * * * *", start, 1), [dt(2026, 11, 24, 10, 1)])

    def test_default_count_is_five(self):
        runs = next_runs("*/15 * * * *", dt(2026, 11, 24, 10, 7))
        self.assertEqual(
            runs,
            [
                dt(2026, 11, 24, 10, 15),
                dt(2026, 11, 24, 10, 30),
                dt(2026, 11, 24, 10, 45),
                dt(2026, 11, 24, 11, 0),
                dt(2026, 11, 24, 11, 15),
            ],
        )

    def test_results_are_utc_aware(self):
        for r in next_runs("0 * * * *", dt(2026, 1, 1)):
            self.assertIs(r.tzinfo, UTC)

    def test_rollover_hour_day_month_year(self):
        self.assertEqual(
            next_runs("30 23 31 12 *", dt(2026, 12, 31, 23, 30), 2),
            [dt(2027, 12, 31, 23, 30), dt(2028, 12, 31, 23, 30)],
        )

    def test_leap_day(self):
        self.assertEqual(
            next_runs("0 0 29 2 *", dt(2026, 1, 1), 2),
            [dt(2028, 2, 29), dt(2032, 2, 29)],
        )

    def test_day_31_skips_short_months(self):
        runs = next_runs("0 12 31 * *", dt(2026, 1, 1), 4)
        self.assertEqual([(r.month, r.day) for r in runs], [(1, 31), (3, 31), (5, 31), (7, 31)])

    def test_weekdays_range(self):
        # 2026-11-27 è venerdì: i prossimi giorni feriali sono ven, lun, mar
        runs = next_runs("0 9 * * 1-5", dt(2026, 11, 27, 9, 0), 3)
        self.assertEqual(runs, [dt(2026, 11, 30, 9), dt(2026, 12, 1, 9), dt(2026, 12, 2, 9)])

    def test_sunday_0_and_7_equivalent(self):
        start = dt(2026, 11, 24)
        self.assertEqual(next_runs("0 0 * * 0", start), next_runs("0 0 * * 7", start))
        self.assertEqual(next_runs("0 0 * * 7", start, 1), [dt(2026, 11, 29)])

    def test_dom_or_dow_when_both_restricted(self):
        # giorno 1 del mese OPPURE lunedì
        runs = next_runs("0 0 1 * 1", dt(2026, 11, 24), 3)
        self.assertEqual(runs, [dt(2026, 11, 30), dt(2026, 12, 1), dt(2026, 12, 7)])

    def test_dow_only_when_dom_is_star(self):
        runs = next_runs("0 0 * * 1", dt(2026, 11, 24), 2)
        self.assertEqual(runs, [dt(2026, 11, 30), dt(2026, 12, 7)])

    def test_naive_start_treated_as_utc(self):
        self.assertEqual(
            next_runs("0 * * * *", datetime(2026, 11, 24, 10, 30), 1),
            [dt(2026, 11, 24, 11, 0)],
        )

    def test_aware_non_utc_start_converted(self):
        cet = timezone(timedelta(hours=1))
        start = datetime(2026, 11, 24, 10, 30, tzinfo=cet)  # = 09:30 UTC
        self.assertEqual(next_runs("0 * * * *", start, 1), [dt(2026, 11, 24, 10, 0)])

    def test_count_zero(self):
        self.assertEqual(next_runs("* * * * *", dt(2026, 1, 1), 0), [])

    def test_results_match_and_are_increasing(self):
        expr = "*/7 3-5,22 1-10/3 1,6-8 *"
        c = parse(expr)
        runs = next_runs(expr, dt(2026, 11, 24), 50)
        self.assertEqual(len(runs), 50)
        for a, b in zip(runs, runs[1:]):
            self.assertLess(a, b)
        for r in runs:
            self.assertTrue(c.matches(r), r)

    def test_brute_force_agreement(self):
        expr = "5,35 */6 * * 2,4"
        c = parse(expr)
        start = dt(2026, 11, 24, 7, 12)
        expected, t = [], start.replace(second=0) + timedelta(minutes=1)
        while len(expected) < 10:
            if c.matches(t):
                expected.append(t)
            t += timedelta(minutes=1)
        self.assertEqual(next_runs(expr, start, 10), expected)


if __name__ == "__main__":
    unittest.main()
