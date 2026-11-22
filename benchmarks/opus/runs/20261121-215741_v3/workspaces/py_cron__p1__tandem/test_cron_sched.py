"""Test per cron_sched: parser e iteratore di espressioni cron a 5 campi."""

import unittest
from datetime import datetime, timezone

from cron_sched import parse_cron, next_runs

UTC = timezone.utc


class TestParseCron(unittest.TestCase):
    def test_parse_star(self):
        m, h, dom, mon, dow = parse_cron('* * * * *')
        self.assertEqual(m, frozenset(range(0, 60)))
        self.assertEqual(h, frozenset(range(0, 24)))
        self.assertEqual(dom, frozenset(range(1, 32)))
        self.assertEqual(mon, frozenset(range(1, 13)))
        self.assertEqual(dow, frozenset(range(0, 7)))

    def test_parse_single(self):
        m, h, dom, mon, dow = parse_cron('5 12 13 6 2')
        self.assertEqual(m, frozenset({5}))
        self.assertEqual(h, frozenset({12}))
        self.assertEqual(dom, frozenset({13}))
        self.assertEqual(mon, frozenset({6}))
        self.assertEqual(dow, frozenset({2}))

    def test_parse_range(self):
        m, h, dom, mon, dow = parse_cron('1-5 0-3 1-2 1-2 1-5')
        self.assertEqual(m, frozenset({1, 2, 3, 4, 5}))
        self.assertEqual(h, frozenset({0, 1, 2, 3}))
        self.assertEqual(dom, frozenset({1, 2}))
        self.assertEqual(mon, frozenset({1, 2}))
        self.assertEqual(dow, frozenset({1, 2, 3, 4, 5}))

    def test_parse_list(self):
        m, h, dom, mon, dow = parse_cron('1,15,45 8,20 1,15 3,9 0,3,6')
        self.assertEqual(m, frozenset({1, 15, 45}))
        self.assertEqual(h, frozenset({8, 20}))
        self.assertEqual(dom, frozenset({1, 15}))
        self.assertEqual(mon, frozenset({3, 9}))
        self.assertEqual(dow, frozenset({0, 3, 6}))

    def test_parse_step_star(self):
        m, h, dom, mon, dow = parse_cron('*/15 */6 */10 */4 */2')
        self.assertEqual(m, frozenset({0, 15, 30, 45}))
        self.assertEqual(h, frozenset({0, 6, 12, 18}))
        self.assertEqual(dom, frozenset({1, 11, 21, 31}))
        self.assertEqual(mon, frozenset({1, 5, 9}))
        self.assertEqual(dow, frozenset({0, 2, 4, 6}))

    def test_parse_step_range(self):
        m, h, dom, mon, dow = parse_cron('10-20/5 0-10/3 1-31/7 1-12/3 1-6/2')
        self.assertEqual(m, frozenset({10, 15, 20}))
        self.assertEqual(h, frozenset({0, 3, 6, 9}))
        self.assertEqual(dom, frozenset({1, 8, 15, 22, 29}))
        self.assertEqual(mon, frozenset({1, 4, 7, 10}))
        self.assertEqual(dow, frozenset({1, 3, 5}))

    def test_parse_dow_seven_is_sunday(self):
        m, h, dom, mon, dow = parse_cron('* * * * 7')
        self.assertEqual(dow, frozenset({0}))

    def test_parse_returns_frozensets(self):
        result = parse_cron('* * * * *')
        self.assertEqual(len(result), 5)
        for item in result:
            self.assertIsInstance(item, frozenset)


class TestNextRuns(unittest.TestCase):
    def test_every_minute(self):
        start = datetime(2024, 1, 1, 0, 0, 30, tzinfo=UTC)
        runs = next_runs('* * * * *', start, 1)
        self.assertEqual(runs, [datetime(2024, 1, 1, 0, 1, tzinfo=UTC)])

    def test_step_minutes(self):
        start = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
        runs = next_runs('*/15 * * * *', start, 3)
        self.assertEqual(runs, [
            datetime(2024, 1, 1, 0, 15, tzinfo=UTC),
            datetime(2024, 1, 1, 0, 30, tzinfo=UTC),
            datetime(2024, 1, 1, 0, 45, tzinfo=UTC),
        ])

    def test_month_year_change(self):
        start = datetime(2024, 6, 1, tzinfo=UTC)
        runs = next_runs('0 0 1 1 *', start, 1)
        self.assertEqual(runs, [datetime(2025, 1, 1, tzinfo=UTC)])

    def test_feb_29_leap_year(self):
        start = datetime(2024, 3, 1, tzinfo=UTC)
        runs = next_runs('0 0 29 2 *', start, 1)
        self.assertEqual(runs, [datetime(2028, 2, 29, tzinfo=UTC)])

    def test_weekday_range(self):
        start = datetime(2024, 1, 5, 10, 0, tzinfo=UTC)
        runs = next_runs('30 9 * * 1-5', start, 2)
        self.assertEqual(runs, [
            datetime(2024, 1, 8, 9, 30, tzinfo=UTC),
            datetime(2024, 1, 9, 9, 30, tzinfo=UTC),
        ])

    def test_dom_dow_or_semantics(self):
        start = datetime(2024, 1, 1, tzinfo=UTC)
        runs = next_runs('0 12 13 * 5', start, 3)
        self.assertEqual(runs, [
            datetime(2024, 1, 5, 12, tzinfo=UTC),
            datetime(2024, 1, 12, 12, tzinfo=UTC),
            datetime(2024, 1, 13, 12, tzinfo=UTC),
        ])

    def test_dow_seven_runs_on_sunday(self):
        start = datetime(2024, 1, 1, tzinfo=UTC)
        runs = next_runs('0 0 * * 7', start, 1)
        self.assertEqual(runs, [datetime(2024, 1, 7, tzinfo=UTC)])

    def test_naive_start_treated_as_utc(self):
        start = datetime(2024, 1, 1, 0, 0, 30)
        runs = next_runs('* * * * *', start, 1)
        self.assertEqual(runs, [datetime(2024, 1, 1, 0, 1, tzinfo=UTC)])

    def test_aware_start_converted_to_utc(self):
        from datetime import timedelta
        tz = timezone(timedelta(hours=2))
        start = datetime(2024, 1, 1, 2, 0, 30, tzinfo=tz)
        runs = next_runs('* * * * *', start, 1)
        self.assertEqual(runs, [datetime(2024, 1, 1, 0, 1, tzinfo=UTC)])

    def test_results_strictly_after_start(self):
        start = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
        runs = next_runs('0 0 * * *', start, 2)
        self.assertEqual(runs, [
            datetime(2024, 1, 2, 0, 0, tzinfo=UTC),
            datetime(2024, 1, 3, 0, 0, tzinfo=UTC),
        ])

    def test_results_have_zero_seconds_and_utc(self):
        start = datetime(2024, 1, 1, 0, 0, 30, tzinfo=UTC)
        runs = next_runs('* * * * *', start, 5)
        for r in runs:
            self.assertEqual(r.second, 0)
            self.assertEqual(r.microsecond, 0)
            self.assertEqual(r.tzinfo, UTC)


class TestValueErrors(unittest.TestCase):
    def test_empty_expression(self):
        with self.assertRaises(ValueError):
            next_runs('', datetime(2024, 1, 1), 1)

    def test_wrong_field_count(self):
        with self.assertRaises(ValueError):
            next_runs('* * * *', datetime(2024, 1, 1), 1)
        with self.assertRaises(ValueError):
            next_runs('* * * * * *', datetime(2024, 1, 1), 1)

    def test_out_of_range_values(self):
        for expr in ['60 * * * *', '* 24 * * *', '* * 0 * *',
                     '* * * 13 *', '* * * * 8']:
            with self.assertRaises(ValueError):
                next_runs(expr, datetime(2024, 1, 1), 1)

    def test_range_a_greater_than_b(self):
        with self.assertRaises(ValueError):
            next_runs('5-1 * * * *', datetime(2024, 1, 1), 1)

    def test_step_zero(self):
        with self.assertRaises(ValueError):
            next_runs('*/0 * * * *', datetime(2024, 1, 1), 1)

    def test_non_numeric_tokens(self):
        for expr in ['a * * * *', '*/x * * * *', '1,,2 * * * *']:
            with self.assertRaises(ValueError):
                next_runs(expr, datetime(2024, 1, 1), 1)

    def test_impossible_date_raises(self):
        with self.assertRaises(ValueError):
            next_runs('0 0 30 2 *', datetime(2024, 1, 1), 1)

    def test_count_zero_raises(self):
        with self.assertRaises(ValueError):
            next_runs('* * * * *', datetime(2024, 1, 1), 0)

    def test_non_string_expression(self):
        with self.assertRaises(ValueError):
            next_runs(None, datetime(2024, 1, 1), 1)


if __name__ == '__main__':
    unittest.main()
