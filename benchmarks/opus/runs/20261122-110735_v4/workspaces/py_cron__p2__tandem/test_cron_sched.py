"""Test per ``cron_sched``: parser e iteratore di espressioni cron a 5 campi.

Copre la sintassi (``*``, numeri, intervalli, liste, passi), la semantica OR
dei giorni, la normalizzazione 7 = domenica, gli errori, i datetime ``aware``
non UTC, il cambio d'anno e il 29 febbraio.
"""

import unittest
from datetime import datetime, timedelta, timezone

from cron_sched import CronExpr, next_runs, parse

UTC = timezone.utc


def d(*args):
    """Costruisce un datetime aware in UTC dai valori posizionali dati."""
    return datetime(*args, tzinfo=UTC)


class TestParse(unittest.TestCase):
    """Test del parser ``parse`` e degli attributi di ``CronExpr``."""

    def test_star_all_fields(self):
        """``* * * * *`` espande ogni campo al suo range completo."""
        c = parse("* * * * *")
        self.assertEqual(c.minutes, frozenset(range(0, 60)))
        self.assertEqual(c.hours, frozenset(range(0, 24)))
        self.assertEqual(c.days, frozenset(range(1, 32)))
        self.assertEqual(c.months, frozenset(range(1, 13)))
        self.assertEqual(c.weekdays, frozenset(range(0, 7)))

    def test_single_number(self):
        """Un numero semplice vale solo se stesso."""
        c = parse("5 10 15 6 3")
        self.assertEqual(c.minutes, frozenset({5}))
        self.assertEqual(c.hours, frozenset({10}))
        self.assertEqual(c.days, frozenset({15}))
        self.assertEqual(c.months, frozenset({6}))
        self.assertEqual(c.weekdays, frozenset({3}))

    def test_range(self):
        """Un intervallo ``a-b`` include tutti i valori da a a b."""
        c = parse("1-3 * * * *")
        self.assertEqual(c.minutes, frozenset({1, 2, 3}))

    def test_list(self):
        """Una lista ``a,b,c`` combina i singoli valori."""
        c = parse("1,15,30 * * * *")
        self.assertEqual(c.minutes, frozenset({1, 15, 30}))

    def test_step_star(self):
        """``*/n`` produce i valori 0, n, 2n, ... fino al massimo."""
        c = parse("*/15 * * * *")
        self.assertEqual(c.minutes, frozenset({0, 15, 30, 45}))

    def test_step_range(self):
        """``a-b/n`` produce i valori da a a b con passo n."""
        c = parse("5 10-20/5 * * *")
        self.assertEqual(c.hours, frozenset({10, 15, 20}))

    def test_step_number(self):
        """``N/n`` va da N fino al massimo del campo con passo n."""
        c = parse("0 12/6 * * *")
        self.assertEqual(c.hours, frozenset({12, 18}))

    def test_weekday_seven_is_sunday(self):
        """Il 7 viene normalizzato a 0 (domenica)."""
        c = parse("0 0 * * 0,7")
        self.assertEqual(c.weekdays, frozenset({0}))

    def test_attributes_are_frozensets(self):
        """Ogni attributo di ``CronExpr`` e' un ``frozenset`` di ``int``."""
        c = parse("* * * * *")
        for attr in ("minutes", "hours", "days", "months", "weekdays"):
            self.assertIsInstance(getattr(c, attr), frozenset)
            self.assertTrue(all(isinstance(v, int) for v in getattr(c, attr)))


class TestNextRuns(unittest.TestCase):
    """Test di ``next_runs``: valori, ordine, fuso orario, semantica giorni."""

    def test_every_minute(self):
        """``* * * * *`` restituisce i minuti successivi a ``start_dt``."""
        got = next_runs("* * * * *", datetime(2026, 1, 1, 0, 0), 3)
        self.assertEqual(got, [d(2026, 1, 1, 0, 1),
                               d(2026, 1, 1, 0, 2),
                               d(2026, 1, 1, 0, 3)])

    def test_strictly_greater_and_aware(self):
        """I risultati sono aware UTC, strettamente maggiori, in ordine."""
        start = datetime(2026, 1, 1, 0, 0, 0, 500)
        got = next_runs("* * * * *", start, 5)
        self.assertEqual(len(got), 5)
        self.assertEqual(got[0], d(2026, 1, 1, 0, 1))
        for dt in got:
            self.assertEqual(dt.tzinfo, UTC)
            self.assertEqual(dt.second, 0)
            self.assertEqual(dt.microsecond, 0)
        self.assertEqual(got, sorted(got))

    def test_year_change(self):
        """Il 1 gennaio e' trovato anche oltre il cambio d'anno."""
        got = next_runs("0 0 1 1 *", datetime(2026, 12, 31, 23, 59, 30), 2)
        self.assertEqual(got, [d(2027, 1, 1), d(2028, 1, 1)])

    def test_february_29(self):
        """Il 29 febbraio e' trovato solo negli anni bisestili."""
        got = next_runs("0 0 29 2 *", datetime(2026, 1, 1), 2)
        self.assertEqual(got, [d(2028, 2, 29), d(2032, 2, 29)])

    def test_day_or_semantics_both_restricted(self):
        """Con entrambi i campi giorno ristretti vale l'OR (giorno 13 o venerdi)."""
        got = next_runs("0 0 13 * 5", datetime(2026, 11, 1), 3)
        self.assertEqual(got, [d(2026, 11, 6), d(2026, 11, 13), d(2026, 11, 20)])

    def test_day_or_semantics_one_star(self):
        """Con ``giorno_mese = *`` vale solo il giorno della settimana."""
        got = next_runs("30 9 * * 1-5", datetime(2026, 11, 21, 10, 0), 2)
        self.assertEqual(got, [d(2026, 11, 23, 9, 30), d(2026, 11, 24, 9, 30)])

    def test_start_dt_aware_non_utc(self):
        """Un ``start_dt`` aware non UTC viene convertito in UTC."""
        start = datetime(2026, 1, 1, 1, 0, tzinfo=timezone(timedelta(hours=2)))
        got = next_runs("0 * * * *", start, 1)
        self.assertEqual(got, [d(2026, 1, 1, 0, 0)])

    def test_count_zero(self):
        """``count == 0`` restituisce una lista vuota."""
        self.assertEqual(next_runs("* * * * *", datetime(2026, 1, 1), 0), [])

    def test_accepts_cronexpr(self):
        """``next_runs`` accetta anche un oggetto ``CronExpr`` gia' costruito."""
        got = next_runs(parse("*/15 * * * *"), datetime(2026, 1, 1, 0, 0), 3)
        self.assertEqual(got, [d(2026, 1, 1, 0, 15),
                               d(2026, 1, 1, 0, 30),
                               d(2026, 1, 1, 0, 45)])


class TestErrors(unittest.TestCase):
    """Test dei ``ValueError`` sollevati per input non validi."""

    def test_error_not_string(self):
        """Un'espressione non stringa solleva ``ValueError``."""
        with self.assertRaises(ValueError):
            next_runs(None, datetime(2026, 1, 1))

    def test_error_wrong_field_count(self):
        """Un numero di campi diverso da 5 solleva ``ValueError``."""
        for bad in ("* * * *", "* * * * * *"):
            with self.assertRaises(ValueError):
                next_runs(bad, datetime(2026, 1, 1))

    def test_error_out_of_range(self):
        """Un valore fuori range solleva ``ValueError``."""
        for bad in ("60 * * * *", "* 24 * * *", "* * 0 * *",
                    "* * * 13 *", "* * * * 8"):
            with self.assertRaises(ValueError):
                next_runs(bad, datetime(2026, 1, 1))

    def test_error_reversed_range(self):
        """Un intervallo con ``a > b`` solleva ``ValueError``."""
        with self.assertRaises(ValueError):
            next_runs("5-1 * * * *", datetime(2026, 1, 1))

    def test_error_bad_step(self):
        """Un passo <= 0 o non numerico solleva ``ValueError``."""
        for bad in ("*/0 * * * *", "*/x * * * *"):
            with self.assertRaises(ValueError):
                next_runs(bad, datetime(2026, 1, 1))

    def test_error_non_numeric(self):
        """Un token non numerico (es. 'a', 'JAN') solleva ``ValueError``."""
        for bad in ("a * * * *", "JAN * * * *"):
            with self.assertRaises(ValueError):
                next_runs(bad, datetime(2026, 1, 1))

    def test_error_empty_element(self):
        """Elementi vuoti o segni orfani sollevano ``ValueError``."""
        for bad in ("1,,2 * * * *", "1- * * * *", "-5 * * * *", ""):
            with self.assertRaises(ValueError):
                next_runs(bad, datetime(2026, 1, 1))

    def test_error_impossible_expression(self):
        """Un'espressione valida ma impossibile solleva ``ValueError``."""
        for bad in ("0 0 30 2 *", "0 0 31 4 *"):
            with self.assertRaises(ValueError):
                next_runs(bad, datetime(2026, 1, 1))

    def test_error_negative_count(self):
        """Un ``count`` negativo o non intero solleva ``ValueError``."""
        with self.assertRaises(ValueError):
            next_runs("* * * * *", datetime(2026, 1, 1), -1)
        with self.assertRaises(ValueError):
            next_runs("* * * * *", datetime(2026, 1, 1), 2.5)


if __name__ == "__main__":
    unittest.main()
