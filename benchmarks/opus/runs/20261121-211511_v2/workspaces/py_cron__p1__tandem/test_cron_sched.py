"""Tests for cron_sched."""

import datetime
import unittest

from cron_sched import next_runs, parse


UTC = datetime.timezone.utc


def u(*a):
    return datetime.datetime(*a, tzinfo=UTC)


class TestParse(unittest.TestCase):
    def test_parse_returns_sets(self):
        spec = parse('0 12 * * 1')
        self.assertEqual(spec['minute'], {0})
        self.assertEqual(spec['hour'], {12})
        self.assertEqual(spec['dom'], set(range(1, 32)))
        self.assertEqual(spec['month'], set(range(1, 13)))
        self.assertEqual(spec['dow'], {1})

    def test_parse_star(self):
        spec = parse('* * * * *')
        self.assertEqual(spec['minute'], set(range(0, 60)))
        self.assertEqual(spec['hour'], set(range(0, 24)))
        self.assertEqual(spec['dom'], set(range(1, 32)))
        self.assertEqual(spec['month'], set(range(1, 13)))
        self.assertEqual(spec['dow'], set(range(0, 7)))

    def test_parse_range(self):
        spec = parse('1-5 * * * *')
        self.assertEqual(spec['minute'], {1, 2, 3, 4, 5})

    def test_parse_list(self):
        spec = parse('5,10,20 * * * *')
        self.assertEqual(spec['minute'], {5, 10, 20})

    def test_parse_step(self):
        spec = parse('*/15 * * * *')
        self.assertEqual(spec['minute'], {0, 15, 30, 45})

    def test_parse_range_step(self):
        spec = parse('10-20/5 * * * *')
        self.assertEqual(spec['minute'], {10, 15, 20})

    def test_parse_list_of_ranges_and_steps(self):
        spec = parse('5,10-20/5 * * * *')
        self.assertEqual(spec['minute'], {5, 10, 15, 20})


class TestNextRuns(unittest.TestCase):
    def test_every_15_minutes(self):
        self.assertEqual(
            next_runs('*/15 * * * *', u(2024, 1, 1, 0, 0), 3),
            [u(2024, 1, 1, 0, 15), u(2024, 1, 1, 0, 30), u(2024, 1, 1, 0, 45)])

    def test_midnight_year_rollover(self):
        self.assertEqual(
            next_runs('0 0 * * *', u(2024, 12, 31, 12, 0), 2),
            [u(2025, 1, 1), u(2025, 1, 2)])

    def test_weekday_range(self):
        self.assertEqual(
            next_runs('30 9 * * 1-5', u(2024, 6, 7, 10, 0), 2),
            [u(2024, 6, 10, 9, 30), u(2024, 6, 11, 9, 30)])

    def test_leap_day(self):
        self.assertEqual(
            next_runs('0 0 29 2 *', u(2023, 1, 1), 1),
            [u(2024, 2, 29)])

    def test_first_of_month_and_sunday(self):
        self.assertEqual(
            next_runs('0 12 1 * 0', u(2024, 9, 1, 13, 0), 3),
            [u(2024, 9, 8, 12), u(2024, 9, 15, 12), u(2024, 9, 22, 12)])

    def test_list_and_range_step(self):
        self.assertEqual(
            next_runs('5,10-20/5 1 * * *', u(2024, 1, 1), 4),
            [u(2024, 1, 1, 1, 5), u(2024, 1, 1, 1, 10),
             u(2024, 1, 1, 1, 15), u(2024, 1, 1, 1, 20)])

    def test_new_year(self):
        self.assertEqual(
            next_runs('0 0 1 1 *', u(2024, 1, 1), 1),
            [u(2025, 1, 1)])

    def test_every_minute_count(self):
        self.assertEqual(len(next_runs('* * * * *', u(2024, 1, 1))), 5)

    def test_strictly_after_start(self):
        # start exactly on a matching minute must not be returned
        self.assertEqual(
            next_runs('* * * * *', u(2024, 1, 1, 0, 0), 1),
            [u(2024, 1, 1, 0, 1)])

    def test_naive_treated_as_utc(self):
        naive = datetime.datetime(2024, 1, 1, 0, 0)
        self.assertEqual(
            next_runs('*/15 * * * *', naive, 1),
            [u(2024, 1, 1, 0, 15)])

    def test_aware_converted_to_utc(self):
        other = datetime.timezone(datetime.timedelta(hours=2))
        aware = datetime.datetime(2024, 1, 1, 2, 0, tzinfo=other)
        # 02:00+02:00 == 00:00 UTC, so next is 00:15 UTC
        self.assertEqual(
            next_runs('*/15 * * * *', aware, 1),
            [u(2024, 1, 1, 0, 15)])

    def test_results_are_utc_aware_and_zero_seconds(self):
        runs = next_runs('0 0 * * *', u(2024, 1, 1), 2)
        for r in runs:
            self.assertEqual(r.tzinfo, UTC)
            self.assertEqual(r.second, 0)
            self.assertEqual(r.microsecond, 0)

    def test_ascending_order(self):
        runs = next_runs('*/15 * * * *', u(2024, 1, 1, 0, 0), 5)
        self.assertEqual(runs, sorted(runs))


class TestOrDayRule(unittest.TestCase):
    def test_or_rule_both_restricted(self):
        # dom=1 and dow=0 (Sunday) both restricted -> OR
        # 2024-09-01 is a Sunday, so it matches via both
        runs = next_runs('0 12 1 * 0', u(2024, 9, 1, 13, 0), 3)
        self.assertEqual(runs, [u(2024, 9, 8, 12), u(2024, 9, 15, 12),
                                u(2024, 9, 22, 12)])

    def test_or_rule_matches_either(self):
        # dom=15 OR Sunday. 2024-09-01 is a Sunday but 12:00 is before the
        # start, so the next Sunday 2024-09-08 12:00 matches via dow.
        runs = next_runs('0 12 15 * 0', u(2024, 9, 1, 13, 0), 1)
        self.assertEqual(runs, [u(2024, 9, 8, 12)])


class TestValueErrors(unittest.TestCase):
    def test_wrong_field_count(self):
        with self.assertRaises(ValueError):
            next_runs('* * * *', u(2024, 1, 1))
        with self.assertRaises(ValueError):
            next_runs('* * * * * *', u(2024, 1, 1))

    def test_non_numeric(self):
        with self.assertRaises(ValueError):
            next_runs('a * * * *', u(2024, 1, 1))

    def test_out_of_range(self):
        with self.assertRaises(ValueError):
            next_runs('60 * * * *', u(2024, 1, 1))
        with self.assertRaises(ValueError):
            next_runs('* 24 * * *', u(2024, 1, 1))
        with self.assertRaises(ValueError):
            next_runs('* * 0 * *', u(2024, 1, 1))
        with self.assertRaises(ValueError):
            next_runs('* * * 13 *', u(2024, 1, 1))
        with self.assertRaises(ValueError):
            next_runs('* * * * 7', u(2024, 1, 1))

    def test_range_reversed(self):
        with self.assertRaises(ValueError):
            next_runs('5-1 * * * *', u(2024, 1, 1))

    def test_step_zero(self):
        with self.assertRaises(ValueError):
            next_runs('*/0 * * * *', u(2024, 1, 1))

    def test_empty_item(self):
        with self.assertRaises(ValueError):
            next_runs('1,,2 * * * *', u(2024, 1, 1))

    def test_non_string_expr(self):
        with self.assertRaises(ValueError):
            next_runs(None, u(2024, 1, 1))

    def test_never_matches(self):
        with self.assertRaises(ValueError):
            next_runs('0 0 31 2 *', u(2024, 1, 1))

    def test_count_zero(self):
        with self.assertRaises(ValueError):
            next_runs('* * * * *', u(2024, 1, 1), 0)

    def test_count_negative(self):
        with self.assertRaises(ValueError):
            next_runs('* * * * *', u(2024, 1, 1), -1)


if __name__ == '__main__':
    unittest.main()
