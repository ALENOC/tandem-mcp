"""Unit tests for cron_sched (5-field cron parser and iterator)."""

import unittest
from datetime import datetime, timedelta, timezone

from cron_sched import parse, next_runs

UTC = timezone.utc


def utc(y, mo, d, h=0, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=UTC)


class TestParse(unittest.TestCase):
    def test_parse_star(self):
        m, h, dom, mon, dow = parse("* * * * *")
        self.assertEqual(m, set(range(0, 60)))
        self.assertEqual(h, set(range(0, 24)))
        self.assertEqual(dom, set(range(1, 32)))
        self.assertEqual(mon, set(range(1, 13)))
        self.assertEqual(dow, set(range(0, 7)))

    def test_parse_single_numbers(self):
        m, h, dom, mon, dow = parse("5 4 3 2 1")
        self.assertEqual(m, {5})
        self.assertEqual(h, {4})
        self.assertEqual(dom, {3})
        self.assertEqual(mon, {2})
        self.assertEqual(dow, {1})

    def test_parse_range(self):
        m, h, dom, mon, dow = parse("1-5 0-2 10-12 3-4 1-3")
        self.assertEqual(m, {1, 2, 3, 4, 5})
        self.assertEqual(h, {0, 1, 2})
        self.assertEqual(dom, {10, 11, 12})
        self.assertEqual(mon, {3, 4})
        self.assertEqual(dow, {1, 2, 3})

    def test_parse_list(self):
        m, h, dom, mon, dow = parse("1,15,30 8,20 1,15 1,6 0,3,5")
        self.assertEqual(m, {1, 15, 30})
        self.assertEqual(h, {8, 20})
        self.assertEqual(dom, {1, 15})
        self.assertEqual(mon, {1, 6})
        self.assertEqual(dow, {0, 3, 5})

    def test_parse_step_star(self):
        m, h, dom, mon, dow = parse("*/15 */6 */10 */3 */2")
        self.assertEqual(m, {0, 15, 30, 45})
        self.assertEqual(h, {0, 6, 12, 18})
        self.assertEqual(dom, {1, 11, 21, 31})
        self.assertEqual(mon, {1, 4, 7, 10})
        self.assertEqual(dow, {0, 2, 4, 6})

    def test_parse_range_step(self):
        m, h, dom, mon, dow = parse("10-40/10 9-17/4 1-31/5 1-12/3 1-5/2")
        self.assertEqual(m, {10, 20, 30, 40})
        self.assertEqual(h, {9, 13, 17})
        self.assertEqual(dom, {1, 6, 11, 16, 21, 26, 31})
        self.assertEqual(mon, {1, 4, 7, 10})
        self.assertEqual(dow, {1, 3, 5})

    def test_parse_dow_seven_as_sunday(self):
        m, h, dom, mon, dow = parse("0 0 1 * 7")
        self.assertEqual(dow, {0})


class TestNextRuns(unittest.TestCase):
    def test_next_runs_star(self):
        r = next_runs("* * * * *", utc(2024, 1, 1, 10, 30), 3)
        self.assertEqual(
            r,
            [utc(2024, 1, 1, 10, 31), utc(2024, 1, 1, 10, 32), utc(2024, 1, 1, 10, 33)],
        )

    def test_next_runs_month_end_crossing(self):
        r = next_runs("*/15 * * * *", utc(2024, 1, 31, 23, 58), 3)
        self.assertEqual(
            r,
            [utc(2024, 2, 1, 0, 0), utc(2024, 2, 1, 0, 15), utc(2024, 2, 1, 0, 30)],
        )

    def test_next_runs_year_end_crossing(self):
        r = next_runs("0 0 1 1 *", utc(2024, 12, 31, 12, 0), 2)
        self.assertEqual(r, [utc(2025, 1, 1, 0, 0), utc(2026, 1, 1, 0, 0)])

    def test_next_runs_leap_day(self):
        r = next_runs("0 12 29 2 *", utc(2024, 3, 1), 2)
        self.assertEqual(r, [utc(2028, 2, 29, 12, 0), utc(2032, 2, 29, 12, 0)])

    def test_next_runs_dow_only(self):
        r = next_runs("0 13 * * 5", utc(2024, 9, 1), 3)
        self.assertEqual(
            r, [utc(2024, 9, 6, 13, 0), utc(2024, 9, 13, 13, 0), utc(2024, 9, 20, 13, 0)]
        )

    def test_next_runs_or_rule(self):
        # Both dom and dow restricted: a date matches if it satisfies either.
        # dom=1 (1st of month) OR dow=5 (Friday).
        r = next_runs("0 0 1 1,7 *", utc(2024, 1, 1), 2)
        self.assertEqual(r, [utc(2024, 7, 1, 0, 0), utc(2025, 1, 1, 0, 0)])

    def test_next_runs_or_rule_friday(self):
        # dom=15 OR dow=0 (Sunday). First two Sundays after start.
        r = next_runs("0 6 15 * 0", utc(2024, 6, 1), 2)
        self.assertEqual(r, [utc(2024, 6, 2, 6, 0), utc(2024, 6, 9, 6, 0)])

    def test_next_runs_dow_seven_as_sunday(self):
        # 7 is accepted as Sunday (0). 2024-01-07 is a Sunday.
        r = next_runs("0 0 * * 7", utc(2024, 1, 1), 2)
        self.assertEqual(r, [utc(2024, 1, 7, 0, 0), utc(2024, 1, 14, 0, 0)])

    def test_next_runs_dow_friday(self):
        # dow=5 is Friday. 2024-09-06 is a Friday.
        r = next_runs("0 0 * * 5", utc(2024, 9, 1), 2)
        self.assertEqual(r, [utc(2024, 9, 6, 0, 0), utc(2024, 9, 13, 0, 0)])

    def test_next_runs_naive_vs_aware(self):
        naive = datetime(2024, 1, 1, 10, 0)
        aware = utc(2024, 1, 1, 10, 0)
        self.assertEqual(next_runs("* * * * *", naive, 1), next_runs("* * * * *", aware, 1))
        # A non-UTC tzinfo is converted to UTC.
        plus2 = timezone(timedelta(hours=2))
        aware2 = datetime(2024, 1, 1, 12, 0, tzinfo=plus2)  # == 10:00 UTC
        self.assertEqual(next_runs("* * * * *", aware2, 1), next_runs("* * * * *", aware, 1))

    def test_next_runs_strictly_after(self):
        # start exactly on a matching minute: the first result is the next one.
        r = next_runs("0 * * * *", utc(2024, 1, 1, 10, 0), 2)
        self.assertEqual(r, [utc(2024, 1, 1, 11, 0), utc(2024, 1, 1, 12, 0)])

    def test_next_runs_zero_seconds_microseconds(self):
        start = datetime(2024, 1, 1, 0, 0, 30, 123456, tzinfo=UTC)
        r = next_runs("30 14 * * *", start, 1)
        self.assertEqual(r, [utc(2024, 1, 1, 14, 30)])
        self.assertEqual(r[0].second, 0)
        self.assertEqual(r[0].microsecond, 0)


class TestValueError(unittest.TestCase):
    def test_wrong_field_count(self):
        with self.assertRaises(ValueError):
            next_runs("* * * *", utc(2024, 1, 1))
        with self.assertRaises(ValueError):
            next_runs("* * * * * *", utc(2024, 1, 1))

    def test_out_of_range(self):
        with self.assertRaises(ValueError):
            next_runs("60 * * * *", utc(2024, 1, 1))
        with self.assertRaises(ValueError):
            next_runs("* 24 * * *", utc(2024, 1, 1))
        with self.assertRaises(ValueError):
            next_runs("* * 0 * *", utc(2024, 1, 1))
        with self.assertRaises(ValueError):
            next_runs("* * * 13 *", utc(2024, 1, 1))

    def test_interval_a_gt_b(self):
        with self.assertRaises(ValueError):
            next_runs("5-1 * * * *", utc(2024, 1, 1))

    def test_step_zero(self):
        with self.assertRaises(ValueError):
            next_runs("*/0 * * * *", utc(2024, 1, 1))

    def test_non_numeric(self):
        with self.assertRaises(ValueError):
            next_runs("a * * * *", utc(2024, 1, 1))

    def test_empty_token(self):
        with self.assertRaises(ValueError):
            next_runs("1,,2 * * * *", utc(2024, 1, 1))

    def test_count_not_positive(self):
        with self.assertRaises(ValueError):
            next_runs("* * * * *", utc(2024, 1, 1), 0)
        with self.assertRaises(ValueError):
            next_runs("* * * * *", utc(2024, 1, 1), -1)

    def test_no_valid_date(self):
        with self.assertRaises(ValueError):
            next_runs("0 0 31 2 *", utc(2024, 1, 1))


if __name__ == "__main__":
    unittest.main()
