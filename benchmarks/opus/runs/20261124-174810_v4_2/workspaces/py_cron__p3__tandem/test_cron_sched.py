"""Test per cron_sched.next_runs."""

import unittest
from datetime import datetime, timezone

from cron_sched import next_runs

UTC = timezone.utc


def dt(*args):
    return datetime(*args, tzinfo=UTC)


class TestNextRuns(unittest.TestCase):
    def test_every_15_minutes(self):
        r = next_runs("*/15 * * * *", dt(2024, 1, 1, 0, 0), 3)
        self.assertEqual(
            r, [dt(2024, 1, 1, 0, 15), dt(2024, 1, 1, 0, 30), dt(2024, 1, 1, 0, 45)]
        )

    def test_weekday_range(self):
        r = next_runs("0 9 * * 1-5", dt(2024, 1, 5, 10, 0), 2)
        self.assertEqual(r, [dt(2024, 1, 8, 9, 0), dt(2024, 1, 9, 9, 0)])

    def test_leap_day(self):
        r = next_runs("0 0 29 2 *", dt(2023, 1, 1), 1)
        self.assertEqual(r, [dt(2024, 2, 29)])

    def test_dow_zero_sunday(self):
        r = next_runs("30 2 1 * 0", dt(2024, 9, 1, 3, 0), 2)
        self.assertEqual(r, [dt(2024, 9, 8, 2, 30), dt(2024, 9, 15, 2, 30)])

    def test_dow_seven_sunday(self):
        r = next_runs("0 0 * * 7", dt(2024, 1, 1), 1)
        self.assertEqual(r, [dt(2024, 1, 7)])

    def test_list_and_step(self):
        r = next_runs("5,10-20/5 1 * * *", dt(2024, 1, 1), 4)
        self.assertEqual([x.minute for x in r], [5, 10, 15, 20])

    def test_default_count_is_five(self):
        r = next_runs("* * * * *", dt(2024, 1, 1))
        self.assertEqual(len(r), 5)

    def test_results_are_utc_aware(self):
        r = next_runs("* * * * *", dt(2024, 1, 1), 2)
        for x in r:
            self.assertEqual(x.tzinfo, UTC)
            self.assertEqual(x.second, 0)
            self.assertEqual(x.microsecond, 0)

    def test_strictly_after_start(self):
        start = dt(2024, 1, 1, 0, 0)
        r = next_runs("* * * * *", start, 3)
        for x in r:
            self.assertGreater(x, start)

    def test_ascending_order(self):
        r = next_runs("*/15 * * * *", dt(2024, 1, 1), 10)
        self.assertEqual(r, sorted(r))

    def test_naive_interpreted_as_utc(self):
        naive = datetime(2024, 1, 1, 0, 0)
        r = next_runs("0 0 * * *", naive, 1)
        self.assertEqual(r, [dt(2024, 1, 2)])

    def test_aware_converted_to_utc(self):
        from datetime import timedelta
        tz = timezone(timedelta(hours=2))
        start = datetime(2024, 1, 1, 23, 30, tzinfo=tz)  # 21:30 UTC
        r = next_runs("0 0 * * *", start, 1)
        self.assertEqual(r, [dt(2024, 1, 2)])

    def test_vixie_or_semantics(self):
        # dom e dow entrambi ristretti: OR (giorno 1 o domenica)
        r = next_runs("0 0 1 * 0", dt(2024, 1, 1), 2)
        self.assertEqual(r, [dt(2024, 1, 7), dt(2024, 1, 14)])

    def test_vixie_and_semantics(self):
        # solo dow ristretto: deve corrispondere il dow (lunedi)
        r = next_runs("0 0 * * 1", dt(2024, 1, 1), 1)
        self.assertEqual(r, [dt(2024, 1, 8)])

    def test_impossible_expression_raises(self):
        with self.assertRaises(ValueError):
            next_runs("0 0 31 2 *", dt(2024, 1, 1))

    def test_wrong_field_count_raises(self):
        for bad in ["* * * *", "* * * * * *"]:
            with self.assertRaises(ValueError):
                next_runs(bad, dt(2024, 1, 1))

    def test_out_of_range_raises(self):
        for bad in ["60 * * * *", "* 24 * * *", "* * 0 * *", "* * * 13 *", "* * * * 8"]:
            with self.assertRaises(ValueError):
                next_runs(bad, dt(2024, 1, 1))

    def test_bad_interval_raises(self):
        with self.assertRaises(ValueError):
            next_runs("5-1 * * * *", dt(2024, 1, 1))

    def test_bad_step_raises(self):
        for bad in ["*/0 * * * *", "*/x * * * *"]:
            with self.assertRaises(ValueError):
                next_runs(bad, dt(2024, 1, 1))

    def test_non_numeric_and_empty_token_raises(self):
        for bad in ["a * * * *", "1,,2 * * * *"]:
            with self.assertRaises(ValueError):
                next_runs(bad, dt(2024, 1, 1))

    def test_non_string_expr_raises(self):
        with self.assertRaises(ValueError):
            next_runs(None, dt(2024, 1, 1))

    def test_count_below_one_raises(self):
        with self.assertRaises(ValueError):
            next_runs("* * * * *", dt(2024, 1, 1), 0)


if __name__ == "__main__":
    unittest.main()
