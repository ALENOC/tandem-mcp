"""Test unittest per :mod:`cron_sched`.

Copre ogni sintassi supportata (``*``, numero, ``a-b``, lista, ``*/n``,
``a-b/n``), la semantica OR di giorno_mese/giorno_settimana, la
normalizzazione 7=domenica, il cambio d'anno, il 29 febbraio, i
``start_dt`` aware non UTC e i casi di ``ValueError``.
"""

import unittest
from datetime import datetime, timedelta, timezone

from cron_sched import CronExpression, next_runs, parse

U = timezone.utc


def d(*a):
    """Costruisce un ``datetime`` aware UTC dai valori posizionali."""
    return datetime(*a, tzinfo=U)


class TestSintassi(unittest.TestCase):
    """Test delle singole sintassi dei campi."""

    def test_stella_minuti(self):
        s = datetime(2024, 1, 1, 0, 0)
        self.assertEqual(
            next_runs("* * * * *", s, 3),
            [d(2024, 1, 1, 0, 1), d(2024, 1, 1, 0, 2), d(2024, 1, 1, 0, 3)],
        )

    def test_numero_singolo(self):
        s = datetime(2024, 1, 1, 0, 0)
        self.assertEqual(
            next_runs("5 4 * * *", s, 2),
            [d(2024, 1, 1, 4, 5), d(2024, 1, 2, 4, 5)],
        )

    def test_intervallo(self):
        s = datetime(2024, 1, 1, 0, 0)
        self.assertEqual(
            next_runs("10-20/5 3 * * *", s, 3),
            [d(2024, 1, 1, 3, 10), d(2024, 1, 1, 3, 15), d(2024, 1, 1, 3, 20)],
        )

    def test_lista(self):
        s = datetime(2024, 1, 1, 0, 0)
        self.assertEqual(
            next_runs("0,30 1 1,15 3 *", s, 3),
            [d(2024, 3, 1, 1, 0), d(2024, 3, 1, 1, 30), d(2024, 3, 15, 1, 0)],
        )

    def test_step_stella(self):
        s = datetime(2024, 1, 1, 0, 0)
        self.assertEqual(
            next_runs("*/15 * * * *", s, 4),
            [d(2024, 1, 1, 0, 15), d(2024, 1, 1, 0, 30),
             d(2024, 1, 1, 0, 45), d(2024, 1, 1, 1, 0)],
        )

    def test_step_intervallo(self):
        s = datetime(2024, 1, 1, 0, 0)
        self.assertEqual(
            next_runs("0 9 * * 1-5", d(2024, 1, 5, 10, 0), 2),
            [d(2024, 1, 8, 9, 0), d(2024, 1, 9, 9, 0)],
        )

    def test_step_da_numero(self):
        # 'N/n' = da N al massimo del range con passo n.
        self.assertEqual(
            parse("30/15 * * * *").minutes, frozenset({30, 45})
        )


class TestSemanticaGiorni(unittest.TestCase):
    """Test della semantica Vixie cron dei giorni."""

    def test_domenica_7(self):
        s = datetime(2024, 1, 1, 0, 0)
        self.assertEqual(next_runs("0 0 * * 7", s, 1), [d(2024, 1, 7, 0, 0)])

    def test_domenica_0(self):
        s = datetime(2024, 1, 1, 0, 0)
        self.assertEqual(next_runs("0 0 * * 0", s, 1), [d(2024, 1, 7, 0, 0)])

    def test_normalizzazione_7_a_0(self):
        self.assertEqual(parse("* * * * 7").weekdays, frozenset({0}))

    def test_or_giorno_mese_e_settimana(self):
        # giorno_mese=13 OR giorno_settimana=5 (venerdì): entrambi contano.
        s = datetime(2024, 1, 1, 0, 0)
        self.assertEqual(
            next_runs("0 0 13 * 5", s, 2),
            [d(2024, 1, 5, 0, 0), d(2024, 1, 12, 0, 0)],
        )

    def test_and_con_stella(self):
        # giorno_mese='*' e giorno_settimana ristretto: vale solo il dow.
        # 2024-01-02 e' un martedi': il primo lunedi' strettamente dopo e'
        # 2024-01-08 (il giorno_mese non conta, solo il dow).
        s = datetime(2024, 1, 2, 0, 0)
        self.assertEqual(
            next_runs("0 0 * * 1", s, 1), [d(2024, 1, 8, 0, 0)]
        )


class TestCasiSpeciali(unittest.TestCase):
    """Test di cambio d'anno, 29 febbraio e start_dt aware."""

    def test_cambio_anno(self):
        self.assertEqual(
            next_runs("0 0 1 1 *", d(2024, 12, 31, 23, 59), 1),
            [d(2025, 1, 1, 0, 0)],
        )

    def test_29_febbraio(self):
        s = datetime(2024, 1, 1, 0, 0)
        self.assertEqual(
            next_runs("0 0 29 2 *", s, 2),
            [d(2024, 2, 29, 0, 0), d(2028, 2, 29, 0, 0)],
        )

    def test_start_aware_non_utc(self):
        tz = timezone(timedelta(hours=2))
        start = datetime(2024, 1, 1, 2, 30, tzinfo=tz)
        self.assertEqual(
            next_runs("0 * * * *", start, 1), [d(2024, 1, 1, 1, 0)]
        )

    def test_risultati_sempre_aware_utc(self):
        r = next_runs("5 4 * * *", datetime(2024, 1, 1, 0, 0))
        self.assertEqual(len(r), 5)
        for x in r:
            self.assertEqual(x.tzinfo, U)
            self.assertEqual(x.second, 0)
            self.assertEqual(x.microsecond, 0)

    def test_strettamente_successivo(self):
        # start 00:00:30 -> primo risultato 00:01 (non 00:00).
        self.assertEqual(
            next_runs("* * * * *", datetime(2024, 1, 1, 0, 0, 30), 1),
            [d(2024, 1, 1, 0, 1)],
        )

    def test_count_zero(self):
        self.assertEqual(next_runs("* * * * *", datetime(2024, 1, 1, 0, 0), 0), [])


class TestErrori(unittest.TestCase):
    """Test dei ValueError per espressioni non valide."""

    def test_campi_diversi_da_5(self):
        for bad in ["", "* * * *", "* * * * * *"]:
            with self.assertRaises(ValueError):
                next_runs(bad, datetime(2024, 1, 1, 0, 0), 1)

    def test_valore_fuori_range(self):
        for bad in ["60 * * * *", "* 24 * * *", "* * 0 * *",
                    "* * * 13 *", "* * * * 8"]:
            with self.assertRaises(ValueError):
                next_runs(bad, datetime(2024, 1, 1, 0, 0), 1)

    def test_intervallo_invertito(self):
        with self.assertRaises(ValueError):
            next_runs("5-1 * * * *", datetime(2024, 1, 1, 0, 0), 1)

    def test_step_zero_o_non_numerico(self):
        for bad in ["*/0 * * * *", "*/x * * * *"]:
            with self.assertRaises(ValueError):
                next_runs(bad, datetime(2024, 1, 1, 0, 0), 1)

    def test_token_non_numerico(self):
        with self.assertRaises(ValueError):
            next_runs("a * * * *", datetime(2024, 1, 1, 0, 0), 1)

    def test_lista_vuota(self):
        with self.assertRaises(ValueError):
            next_runs("1,,2 * * * *", datetime(2024, 1, 1, 0, 0), 1)

    def test_intervallo_multi(self):
        with self.assertRaises(ValueError):
            next_runs("1-2-3 * * * *", datetime(2024, 1, 1, 0, 0), 1)

    def test_espressione_non_soddisfacibile(self):
        for bad in ["0 0 30 2 *", "0 0 31 4 *"]:
            with self.assertRaises(ValueError):
                next_runs(bad, datetime(2024, 1, 1, 0, 0), 1)

    def test_count_non_valido(self):
        s = datetime(2024, 1, 1, 0, 0)
        for c in [-1, 1.5]:
            with self.assertRaises(ValueError):
                next_runs("* * * * *", s, c)

    def test_expr_non_stringa(self):
        with self.assertRaises(ValueError):
            next_runs(None, datetime(2024, 1, 1, 0, 0), 1)


if __name__ == "__main__":
    unittest.main()
