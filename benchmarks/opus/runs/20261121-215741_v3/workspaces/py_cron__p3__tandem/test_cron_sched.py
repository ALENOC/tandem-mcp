"""Test per cron_sched."""

import unittest
from datetime import datetime, timedelta, timezone

from cron_sched import next_runs, parse

U = timezone.utc


def d(*a):
    return datetime(*a, tzinfo=U)


class TestParse(unittest.TestCase):

    def test_parse_star(self):
        m, h, dom, mon, dow = parse('* * * * *')
        self.assertEqual(m, set(range(60)))
        self.assertEqual(h, set(range(24)))
        self.assertEqual(dom, set(range(1, 32)))
        self.assertEqual(mon, set(range(1, 13)))
        self.assertEqual(dow, set(range(7)))

    def test_parse_range_and_list(self):
        self.assertEqual(parse('1-3,7 * * * *')[0], {1, 2, 3, 7})

    def test_parse_step(self):
        self.assertEqual(parse('*/15 * * * *')[0], {0, 15, 30, 45})

    def test_parse_range_step(self):
        self.assertEqual(parse('10-20/5 * * * *')[0], {10, 15, 20})

    def test_parse_single_value(self):
        self.assertEqual(parse('5 * * * *')[0], {5})


class TestNextRuns(unittest.TestCase):

    def test_every_minute(self):
        r = next_runs('* * * * *', d(2026, 1, 1, 0, 0), 3)
        self.assertEqual(r, [d(2026, 1, 1, 0, 1), d(2026, 1, 1, 0, 2), d(2026, 1, 1, 0, 3)])

    def test_step_minutes(self):
        r = next_runs('*/15 * * * *', datetime(2026, 1, 1, 0, 7, 30), 3)
        self.assertEqual(r, [d(2026, 1, 1, 0, 15), d(2026, 1, 1, 0, 30), d(2026, 1, 1, 0, 45)])

    def test_new_year(self):
        r = next_runs('0 0 1 1 *', d(2026, 6, 1), 2)
        self.assertEqual(r, [d(2027, 1, 1), d(2028, 1, 1)])

    def test_leap_day(self):
        r = next_runs('0 0 29 2 *', d(2026, 1, 1), 1)
        self.assertEqual(r, [d(2028, 2, 29)])

    def test_weekday_range(self):
        r = next_runs('30 9 * * 1-5', d(2026, 11, 21, 10, 0), 2)
        self.assertEqual(r, [d(2026, 11, 23, 9, 30), d(2026, 11, 24, 9, 30)])

    def test_dom_and_dow_vixie(self):
        r = next_runs('0 12 13 * 5', d(2026, 11, 1), 3)
        self.assertEqual(r, [d(2026, 11, 6, 12), d(2026, 11, 13, 12), d(2026, 11, 20, 12)])

    def test_hour_range_step(self):
        r = next_runs('0 10-20/5 * * *', d(2026, 1, 1), 4)
        self.assertEqual(r, [d(2026, 1, 1, 10), d(2026, 1, 1, 15),
                            d(2026, 1, 1, 20), d(2026, 1, 2, 10)])

    def test_sunday(self):
        r = next_runs('0 0 * * 0', d(2026, 11, 21), 1)
        self.assertEqual(r, [d(2026, 11, 22)])

    def test_aware_start_converted(self):
        r = next_runs('5,10 * * * *',
                      datetime(2026, 1, 1, 1, 0, tzinfo=timezone(timedelta(hours=2))), 2)
        self.assertEqual(r, [d(2025, 12, 31, 23, 5), d(2025, 12, 31, 23, 10)])
        self.assertEqual(r[0].tzinfo, U)

    def test_default_count(self):
        r = next_runs('* * * * *', d(2026, 1, 1))
        self.assertEqual(len(r), 5)

    def test_strictly_after(self):
        r = next_runs('0 0 * * *', d(2026, 1, 1, 0, 0), 1)
        self.assertEqual(r, [d(2026, 1, 2, 0, 0)])


class TestErrors(unittest.TestCase):

    def test_non_string_expr(self):
        with self.assertRaises(ValueError):
            next_runs(None, d(2026, 1, 1))

    def test_wrong_field_count(self):
        with self.assertRaises(ValueError):
            next_runs('* * * *', d(2026, 1, 1))

    def test_out_of_range(self):
        with self.assertRaises(ValueError):
            next_runs('60 * * * *', d(2026, 1, 1))

    def test_bad_step(self):
        with self.assertRaises(ValueError):
            next_runs('*/0 * * * *', d(2026, 1, 1))

    def test_unsatisfiable(self):
        with self.assertRaises(ValueError):
            next_runs('0 0 30 2 *', d(2026, 1, 1))

    def test_negative_count(self):
        with self.assertRaises(ValueError):
            next_runs('* * * * *', d(2026, 1, 1), -1)


if __name__ == '__main__':
    unittest.main()
