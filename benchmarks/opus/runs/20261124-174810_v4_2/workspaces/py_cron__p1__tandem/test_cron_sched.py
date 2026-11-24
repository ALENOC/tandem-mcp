"""Test per cron_sched.next_runs."""

import unittest
from datetime import datetime, timedelta, timezone

from cron_sched import next_runs

UTC = timezone.utc


def dt(y, mo, d, h=0, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=UTC)


class TestNextRuns(unittest.TestCase):
    def test_star_step_minutes(self):
        # */15: minuti 0,15,30,45; strettamente dopo 00:00.
        self.assertEqual(
            next_runs("*/15 * * * *", dt(2024, 1, 1, 0, 0), 3),
            [dt(2024, 1, 1, 0, 15), dt(2024, 1, 1, 0, 30), dt(2024, 1, 1, 0, 45)],
        )

    def test_single_value(self):
        # Un solo valore per campo: ogni giorno alle 03:07.
        self.assertEqual(
            next_runs("7 3 * * *", dt(2024, 1, 1), 2),
            [dt(2024, 1, 1, 3, 7), dt(2024, 1, 2, 3, 7)],
        )

    def test_range(self):
        # Intervallo di ore 1-3, minuto 5.
        self.assertEqual(
            next_runs("5 1-3 * * *", dt(2024, 1, 1, 0, 0), 3),
            [dt(2024, 1, 1, 1, 5), dt(2024, 1, 1, 2, 5), dt(2024, 1, 1, 3, 5)],
        )

    def test_list(self):
        # Lista di minuti 1,2,3.
        self.assertEqual(
            next_runs("1,2,3 * * * *", dt(2024, 1, 1, 0, 0), 3),
            [dt(2024, 1, 1, 0, 1), dt(2024, 1, 1, 0, 2), dt(2024, 1, 1, 0, 3)],
        )

    def test_range_with_step(self):
        # a-b/n: ore 1-10 passo 3 -> 1,4,7,10.
        self.assertEqual(
            next_runs("5 1-10/3 * * *", dt(2024, 12, 31, 23, 0), 4),
            [dt(2025, 1, 1, 1, 5), dt(2025, 1, 1, 4, 5),
             dt(2025, 1, 1, 7, 5), dt(2025, 1, 1, 10, 5)],
        )

    def test_month_and_year_rollover(self):
        # Cambio di mese e di anno: 00:00 del 1 gennaio.
        self.assertEqual(
            next_runs("0 0 1 1 *", dt(2024, 12, 31, 0, 0), 2),
            [dt(2025, 1, 1, 0, 0), dt(2026, 1, 1, 0, 0)],
        )

    def test_leap_year(self):
        # 29 febbraio: solo negli anni bisestili.
        self.assertEqual(
            next_runs("0 0 29 2 *", dt(2023, 1, 1), 2),
            [dt(2024, 2, 29), dt(2028, 2, 29)],
        )

    def test_weekday_seven_is_sunday(self):
        # 7 = domenica.
        self.assertEqual(
            next_runs("0 0 * * 7", dt(2024, 1, 1), 1),
            [dt(2024, 1, 7)],
        )

    def test_weekday_zero_is_sunday(self):
        # 0 = domenica, stesso risultato di 7.
        self.assertEqual(
            next_runs("0 0 * * 0", dt(2024, 1, 1), 1),
            [dt(2024, 1, 7)],
        )

    def test_or_semantics_dom_dow(self):
        # Entrambi ristretti: OR. 1 gennaio 2024 e' lunedi -> 1 e 8.
        self.assertEqual(
            next_runs("0 12 1 * 1", dt(2024, 1, 1, 12, 0), 2),
            [dt(2024, 1, 8, 12, 0), dt(2024, 1, 15, 12, 0)],
        )

    def test_or_semantics_includes_dom(self):
        # OR: il 1 (dom) e' incluso anche se non e' lunedi.
        self.assertEqual(
            next_runs("0 12 1 * 1", dt(2023, 12, 31), 2),
            [dt(2024, 1, 1, 12, 0), dt(2024, 1, 8, 12, 0)],
        )

    def test_strictly_after(self):
        # Risultati strettamente successivi a start_dt.
        res = next_runs("0 0 * * *", dt(2024, 1, 1, 0, 0), 1)
        self.assertEqual(res, [dt(2024, 1, 2, 0, 0)])

    def test_aware_start_converted_to_utc(self):
        # start_dt aware convertito in UTC.
        tz_plus2 = timezone(timedelta(hours=2))
        start = datetime(2024, 1, 1, 2, 0, tzinfo=tz_plus2)  # 00:00 UTC
        self.assertEqual(
            next_runs("0 0 * * *", start, 1),
            [dt(2024, 1, 2, 0, 0)],
        )

    def test_result_tz_and_zero_seconds(self):
        # Timezone-aware UTC, secondi e microsecondi a zero.
        res = next_runs("30 12 * * *", dt(2024, 1, 1), 1)
        self.assertEqual(res[0].tzinfo, UTC)
        self.assertEqual(res[0].second, 0)
        self.assertEqual(res[0].microsecond, 0)

    def test_default_count(self):
        # count predefinito 5.
        self.assertEqual(len(next_runs("1,2,3 * * * *", dt(2024, 1, 1))), 5)

    def test_error_wrong_field_count(self):
        with self.assertRaises(ValueError):
            next_runs("* * * *", dt(2024, 1, 1))
        with self.assertRaises(ValueError):
            next_runs("* * * * * *", dt(2024, 1, 1))

    def test_error_out_of_range(self):
        for bad in ("60 * * * *", "* * 0 * *", "* * * 13 *", "* * * * 8"):
            with self.assertRaises(ValueError):
                next_runs(bad, dt(2024, 1, 1))

    def test_error_interval_reversed(self):
        with self.assertRaises(ValueError):
            next_runs("5-1 * * * *", dt(2024, 1, 1))

    def test_error_step_zero(self):
        with self.assertRaises(ValueError):
            next_runs("*/0 * * * *", dt(2024, 1, 1))

    def test_error_non_numeric(self):
        with self.assertRaises(ValueError):
            next_runs("a * * * *", dt(2024, 1, 1))

    def test_error_empty_token(self):
        with self.assertRaises(ValueError):
            next_runs("1,,2 * * * *", dt(2024, 1, 1))

    def test_error_not_string(self):
        with self.assertRaises(ValueError):
            next_runs(None, dt(2024, 1, 1))

    def test_error_count_less_than_one(self):
        with self.assertRaises(ValueError):
            next_runs("* * * * *", dt(2024, 1, 1), 0)

    def test_error_impossible_expression(self):
        # 31 febbraio non esiste: ValueError, non loop infinito.
        with self.assertRaises(ValueError):
            next_runs("0 0 31 2 *", dt(2024, 1, 1))


if __name__ == "__main__":
    unittest.main()
