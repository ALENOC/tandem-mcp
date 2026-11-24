"""Test per cron_sched: parser, sintassi, errori e regola OR di Vixie."""

import unittest
from datetime import datetime, timedelta, timezone

import cron_sched as c

U = timezone.utc


def dt(y, mo, d, h=0, m=0):
    return datetime(y, mo, d, h, m, tzinfo=U)


class TestParseCron(unittest.TestCase):
    def test_parse_star(self):
        m, h, dom, mon, dow = c.parse_cron("* * * * *")
        self.assertEqual(m, set(range(0, 60)))
        self.assertEqual(h, set(range(0, 24)))
        self.assertEqual(dom, set(range(1, 32)))
        self.assertEqual(mon, set(range(1, 13)))
        self.assertEqual(dow, set(range(0, 7)))

    def test_parse_number(self):
        m, h, dom, mon, dow = c.parse_cron("5 3 15 6 2")
        self.assertEqual(m, {5})
        self.assertEqual(h, {3})
        self.assertEqual(dom, {15})
        self.assertEqual(mon, {6})
        self.assertEqual(dow, {2})

    def test_parse_range(self):
        m, h, dom, mon, dow = c.parse_cron("1-5 10-12 1-3 1-2 1-3")
        self.assertEqual(m, {1, 2, 3, 4, 5})
        self.assertEqual(h, {10, 11, 12})
        self.assertEqual(dom, {1, 2, 3})
        self.assertEqual(mon, {1, 2})
        self.assertEqual(dow, {1, 2, 3})

    def test_parse_list(self):
        m, h, dom, mon, dow = c.parse_cron("1,15,45 8,20 2,14 3,9 0,4")
        self.assertEqual(m, {1, 15, 45})
        self.assertEqual(h, {8, 20})
        self.assertEqual(dom, {2, 14})
        self.assertEqual(mon, {3, 9})
        self.assertEqual(dow, {0, 4})

    def test_parse_step_star(self):
        m, h, dom, mon, dow = c.parse_cron("*/15 */6 */10 */4 */2")
        self.assertEqual(m, {0, 15, 30, 45})
        self.assertEqual(h, {0, 6, 12, 18})
        self.assertEqual(dom, set(range(1, 32, 10)))
        self.assertEqual(mon, {1, 5, 9})
        self.assertEqual(dow, {0, 2, 4, 6})

    def test_parse_step_range(self):
        m, h, dom, mon, dow = c.parse_cron("10-20/5 1-10/3 2-10/2 1-12/3 1-6/2")
        self.assertEqual(m, {10, 15, 20})
        self.assertEqual(h, {1, 4, 7, 10})
        self.assertEqual(dom, {2, 4, 6, 8, 10})
        self.assertEqual(mon, {1, 4, 7, 10})
        self.assertEqual(dow, {1, 3, 5})

    def test_parse_dow_seven_as_sunday(self):
        m, h, dom, mon, dow = c.parse_cron("* * * * 7")
        self.assertEqual(dow, {0})

    def test_parse_mixed_list(self):
        m, h, dom, mon, dow = c.parse_cron("5,10-20/5 1 * 1,6 *")
        self.assertEqual(m, {5, 10, 15, 20})
        self.assertEqual(h, {1})
        self.assertEqual(mon, {1, 6})


class TestNextRuns(unittest.TestCase):
    def test_every_15_minutes(self):
        r = c.next_runs("*/15 * * * *", dt(2026, 1, 1, 0, 0), 3)
        self.assertEqual(
            r, [dt(2026, 1, 1, 0, 15), dt(2026, 1, 1, 0, 30), dt(2026, 1, 1, 0, 45)]
        )

    def test_daily_midnight_naive_start(self):
        r = c.next_runs("0 0 * * *", datetime(2026, 1, 1, 0, 0), 2)
        self.assertEqual(r, [dt(2026, 1, 2, 0, 0), dt(2026, 1, 3, 0, 0)])

    def test_weekday_range(self):
        r = c.next_runs("30 9 * * 1-5", dt(2026, 11, 27, 10, 0), 2)
        self.assertEqual(r, [dt(2026, 11, 30, 9, 30), dt(2026, 12, 1, 9, 30)])

    def test_leap_day(self):
        r = c.next_runs("0 0 29 2 *", dt(2026, 1, 1), 1)
        self.assertEqual(r, [dt(2028, 2, 29, 0, 0)])

    def test_mixed_syntax(self):
        r = c.next_runs("5,10-20/5 1 * 1,6 *", dt(2026, 6, 30, 23, 59), 4)
        self.assertEqual(
            r,
            [
                dt(2027, 1, 1, 1, 5),
                dt(2027, 1, 1, 1, 10),
                dt(2027, 1, 1, 1, 15),
                dt(2027, 1, 1, 1, 20),
            ],
        )

    def test_default_count_is_five(self):
        r = c.next_runs("* * * * *", dt(2026, 1, 1))
        self.assertEqual(len(r), 5)

    def test_seven_is_sunday(self):
        r = c.next_runs("0 0 * * 7", dt(2026, 11, 24), 1)
        self.assertEqual(r, [dt(2026, 11, 29, 0, 0)])

    def test_results_are_utc_aware(self):
        r = c.next_runs("* * * * *", dt(2026, 1, 1), 2)
        for x in r:
            self.assertIsNotNone(x.tzinfo)
            self.assertEqual(x.utcoffset().total_seconds(), 0)
            self.assertEqual(x.second, 0)
            self.assertEqual(x.microsecond, 0)

    def test_strictly_after_start(self):
        # start esattamente su uno scatto: il primo risultato e' il successivo
        r = c.next_runs("0 0 * * *", dt(2026, 1, 1, 0, 0), 1)
        self.assertEqual(r, [dt(2026, 1, 2, 0, 0)])

    def test_aware_start_converted_to_utc(self):
        # start in fuso +2h: 2026-01-01 02:00+02:00 == 2026-01-01 00:00 UTC
        start = datetime(2026, 1, 1, 2, 0, tzinfo=timezone(timedelta(hours=2)))
        r = c.next_runs("0 0 * * *", start, 1)
        self.assertEqual(r, [dt(2026, 1, 2, 0, 0)])

    def test_increasing_order(self):
        r = c.next_runs("*/10 * * * *", dt(2026, 1, 1, 0, 0), 10)
        self.assertEqual(r, sorted(r))
        self.assertEqual(len(r), 10)


class TestOrRule(unittest.TestCase):
    def test_or_rule_dom_or_dow(self):
        # dom=1 (giorno 1 del mese) OR dow=0 (domenica)
        # 2026-11-24 e' martedi; prossimo: 2026-11-29 (domenica) poi 2026-12-01
        r = c.next_runs("0 12 1 * 0", dt(2026, 11, 24), 3)
        self.assertEqual(
            r, [dt(2026, 11, 29, 12, 0), dt(2026, 12, 1, 12, 0), dt(2026, 12, 6, 12, 0)]
        )

    def test_only_dom_when_dow_star(self):
        # solo giorno_mese ristretto, dow='*' -> vale solo dom
        r = c.next_runs("0 0 1 * *", dt(2026, 1, 15), 2)
        self.assertEqual(r, [dt(2026, 2, 1, 0, 0), dt(2026, 3, 1, 0, 0)])

    def test_only_dow_when_dom_star(self):
        # solo giorno_settimana ristretto, dom='*' -> vale solo dow
        r = c.next_runs("0 0 * * 0", dt(2026, 1, 1), 2)
        self.assertEqual(r, [dt(2026, 1, 4, 0, 0), dt(2026, 1, 11, 0, 0)])


class TestErrors(unittest.TestCase):
    def test_wrong_field_count(self):
        with self.assertRaises(ValueError):
            c.next_runs("* * * *", dt(2026, 1, 1), 1)
        with self.assertRaises(ValueError):
            c.next_runs("* * * * * *", dt(2026, 1, 1), 1)

    def test_out_of_range(self):
        for bad in ["60 * * * *", "* 24 * * *", "* * 0 * *", "* * * 13 *", "* * * * 8"]:
            with self.assertRaises(ValueError):
                c.next_runs(bad, dt(2026, 1, 1), 1)

    def test_interval_a_gt_b(self):
        with self.assertRaises(ValueError):
            c.next_runs("5-1 * * * *", dt(2026, 1, 1), 1)

    def test_step_zero_or_nonnumeric(self):
        for bad in ["*/0 * * * *", "*/x * * * *"]:
            with self.assertRaises(ValueError):
                c.next_runs(bad, dt(2026, 1, 1), 1)

    def test_non_numeric_and_empty_tokens(self):
        for bad in ["a * * * *", "1,,2 * * * *", "", "-1 * * * *"]:
            with self.assertRaises(ValueError):
                c.next_runs(bad, dt(2026, 1, 1), 1)

    def test_non_string_expr(self):
        with self.assertRaises(ValueError):
            c.next_runs(None, dt(2026, 1, 1), 1)
        with self.assertRaises(ValueError):
            c.next_runs(12345, dt(2026, 1, 1), 1)

    def test_impossible_expression(self):
        with self.assertRaises(ValueError):
            c.next_runs("0 0 30 2 *", dt(2026, 1, 1), 1)

    def test_count_validation(self):
        for bc in [0, -1]:
            with self.assertRaises(ValueError):
                c.next_runs("* * * * *", dt(2026, 1, 1), bc)


if __name__ == "__main__":
    unittest.main()
