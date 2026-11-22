"""Test per cron_sched: parser e iteratore di espressioni cron a 5 campi."""

import unittest
from datetime import datetime, timedelta, timezone

from cron_sched import next_runs, parse_cron

U = timezone.utc


class TestParseCron(unittest.TestCase):
    def test_star_fields(self):
        m, h, dom, mon, dow = parse_cron("* * * * *")
        self.assertEqual(m, set(range(0, 60)))
        self.assertEqual(h, set(range(0, 24)))
        self.assertEqual(dom, set(range(1, 32)))
        self.assertEqual(mon, set(range(1, 13)))
        self.assertEqual(dow, set(range(0, 7)))

    def test_single_numbers(self):
        m, h, dom, mon, dow = parse_cron("5 10 15 6 3")
        self.assertEqual(m, {5})
        self.assertEqual(h, {10})
        self.assertEqual(dom, {15})
        self.assertEqual(mon, {6})
        self.assertEqual(dow, {3})

    def test_range(self):
        m, h, dom, mon, dow = parse_cron("0 9-11 * * *")
        self.assertEqual(h, {9, 10, 11})

    def test_list(self):
        m, h, dom, mon, dow = parse_cron("0,15,30,45 * * * *")
        self.assertEqual(m, {0, 15, 30, 45})

    def test_step_star(self):
        m, h, dom, mon, dow = parse_cron("*/15 * * * *")
        self.assertEqual(m, {0, 15, 30, 45})

    def test_step_range(self):
        m, h, dom, mon, dow = parse_cron("0 10-14/2 * * *")
        self.assertEqual(h, {10, 12, 14})

    def test_dow_seven_normalized(self):
        m, h, dom, mon, dow = parse_cron("0 0 * * 7")
        self.assertEqual(dow, {0})


class TestNextRuns(unittest.TestCase):
    def test_every_fifteen_minutes(self):
        r = next_runs("*/15 * * * *", datetime(2026, 1, 1, 0, 0, tzinfo=U), 3)
        self.assertEqual(
            r,
            [
                datetime(2026, 1, 1, 0, 15, tzinfo=U),
                datetime(2026, 1, 1, 0, 30, tzinfo=U),
                datetime(2026, 1, 1, 0, 45, tzinfo=U),
            ],
        )

    def test_feb_29_leap_years(self):
        r = next_runs("0 0 29 2 *", datetime(2026, 1, 1), 2)
        self.assertEqual(
            r,
            [
                datetime(2028, 2, 29, tzinfo=U),
                datetime(2032, 2, 29, tzinfo=U),
            ],
        )

    def test_year_rollover(self):
        r = next_runs("59 23 31 12 *", datetime(2026, 12, 31, 23, 59, 30), 1)
        self.assertEqual(r, [datetime(2027, 12, 31, 23, 59, tzinfo=U)])

    def test_naive_start_treated_as_utc(self):
        r = next_runs("* * * * *", datetime(2026, 1, 1), 1)
        self.assertEqual(r, [datetime(2026, 1, 1, 0, 1, tzinfo=U)])

    def test_aware_start_converted_to_utc(self):
        start = datetime(2026, 3, 1, 11, 0, tzinfo=timezone(timedelta(hours=2)))
        r = next_runs("0 10-14/2 * * *", start, 3)
        self.assertEqual(
            r,
            [
                datetime(2026, 3, 1, 10, 0, tzinfo=U),
                datetime(2026, 3, 1, 12, 0, tzinfo=U),
                datetime(2026, 3, 1, 14, 0, tzinfo=U),
            ],
        )

    def test_count_zero(self):
        self.assertEqual(next_runs("* * * * *", datetime(2026, 1, 1), 0), [])

    def test_default_count_five(self):
        self.assertEqual(len(next_runs("* * * * *", datetime(2026, 1, 1))), 5)

    def test_dow_seven_is_sunday(self):
        r = next_runs("0 0 * * 7", datetime(2026, 11, 21), 1)
        self.assertEqual(r, [datetime(2026, 11, 22, tzinfo=U)])

    def test_dow_list(self):
        r = next_runs("0 0 * * 0,3", datetime(2026, 11, 21), 2)
        self.assertEqual(
            r,
            [
                datetime(2026, 11, 22, tzinfo=U),
                datetime(2026, 11, 25, tzinfo=U),
            ],
        )

    def test_dom_dow_or_semantics(self):
        # 1 del mese OPPURE lunedi: 2026-06-01 e' lunedi (e' il 1), poi 8, 15.
        r = next_runs("30 9 1 * 1", datetime(2026, 6, 1, 9, 30, tzinfo=U), 2)
        self.assertEqual(
            r,
            [
                datetime(2026, 6, 8, 9, 30, tzinfo=U),
                datetime(2026, 6, 15, 9, 30, tzinfo=U),
            ],
        )


class TestValueErrors(unittest.TestCase):
    def _assert_raises(self, expr):
        with self.assertRaises(ValueError):
            next_runs(expr, datetime(2026, 1, 1))

    def test_wrong_field_count(self):
        self._assert_raises("* * * *")
        self._assert_raises("* * * * * *")

    def test_out_of_range(self):
        self._assert_raises("60 * * * *")
        self._assert_raises("* 24 * * *")
        self._assert_raises("* * 0 * *")
        self._assert_raises("* * * 13 *")
        self._assert_raises("* * * * 8")

    def test_bad_interval(self):
        self._assert_raises("5-1 * * * *")

    def test_bad_step(self):
        self._assert_raises("*/0 * * * *")

    def test_non_numeric(self):
        self._assert_raises("a * * * *")

    def test_empty_token(self):
        self._assert_raises("1,,2 * * * *")

    def test_empty_expr(self):
        self._assert_raises("")

    def test_impossible_date(self):
        self._assert_raises("0 0 31 2 *")

    def test_count_negative(self):
        with self.assertRaises(ValueError):
            next_runs("* * * * *", datetime(2026, 1, 1), -1)

    def test_count_not_int(self):
        with self.assertRaises(ValueError):
            next_runs("* * * * *", datetime(2026, 1, 1), 1.5)


if __name__ == "__main__":
    unittest.main()
