"""Test per cron_sched: parser e iteratore di espressioni cron a 5 campi."""

import unittest
from datetime import datetime, timedelta, timezone
from itertools import islice

from cron_sched import CronExpr, iter_cron, next_runs, parse_cron

UTC = timezone.utc


def d(*args):
    """Costruisce un datetime UTC dai valori posizionali di datetime."""
    return datetime(*args, tzinfo=UTC)


class TestParseCron(unittest.TestCase):
    """Test del parser: campi, range, normalizzazione e flag."""

    def test_stella_tutti_i_campi(self):
        """'*' in ogni campo produce l'insieme completo e flag non ristretti."""
        c = parse_cron("* * * * *")
        self.assertEqual(c.minutes, frozenset(range(0, 60)))
        self.assertEqual(c.hours, frozenset(range(0, 24)))
        self.assertEqual(c.days, frozenset(range(1, 32)))
        self.assertEqual(c.months, frozenset(range(1, 13)))
        self.assertEqual(c.weekdays, frozenset(range(0, 7)))
        self.assertFalse(c.days_restricted)
        self.assertFalse(c.weekdays_restricted)

    def test_numero_singolo(self):
        """Un numero singolo produce un insieme con un solo elemento."""
        c = parse_cron("5 4 3 2 1")
        self.assertEqual(c.minutes, frozenset({5}))
        self.assertEqual(c.hours, frozenset({4}))
        self.assertEqual(c.days, frozenset({3}))
        self.assertEqual(c.months, frozenset({2}))
        self.assertEqual(c.weekdays, frozenset({1}))
        self.assertTrue(c.days_restricted)
        self.assertTrue(c.weekdays_restricted)

    def test_intervallo(self):
        """'a-b' produce tutti i valori da a a b inclusi."""
        c = parse_cron("10-20 * * * *")
        self.assertEqual(c.minutes, frozenset(range(10, 21)))

    def test_lista(self):
        """'a,b,c' produce esattamente i valori elencati."""
        c = parse_cron("1,15,20 * * * *")
        self.assertEqual(c.minutes, frozenset({1, 15, 20}))

    def test_step_stella(self):
        """'*/n' produce i valori 0, n, 2n, ... entro il range."""
        c = parse_cron("*/15 * * * *")
        self.assertEqual(c.minutes, frozenset({0, 15, 30, 45}))

    def test_step_intervallo(self):
        """'a-b/n' produce i valori da a a b con passo n."""
        c = parse_cron("10-20/5 * * * *")
        self.assertEqual(c.minutes, frozenset({10, 15, 20}))

    def test_step_da_numero(self):
        """'N/n' significa da N fino al massimo del campo con passo n."""
        c = parse_cron("30/10 * * * *")
        self.assertEqual(c.minutes, frozenset({30, 40, 50}))

    def test_giorno_settimana_7_normalizzato_a_0(self):
        """Il 7 (domenica) viene normalizzato a 0 nei weekdays."""
        c = parse_cron("0 0 * * 7")
        self.assertIn(0, c.weekdays)
        self.assertNotIn(7, c.weekdays)
        self.assertEqual(c.weekdays, frozenset({0}))

    def test_campi_ristretti_flag(self):
        """I flag riflettono se il campo testuale era esattamente '*'."""
        c = parse_cron("0 0 13 * 5")
        self.assertTrue(c.days_restricted)
        self.assertTrue(c.weekdays_restricted)
        c2 = parse_cron("0 0 * * 1-5")
        self.assertFalse(c2.days_restricted)
        self.assertTrue(c2.weekdays_restricted)
        c3 = parse_cron("0 0 * * *")
        self.assertFalse(c3.days_restricted)
        self.assertFalse(c3.weekdays_restricted)


class TestNextRuns(unittest.TestCase):
    """Test di next_runs: valori, ordine, fusi e casi limite."""

    def test_ogni_giorno_alle_zero(self):
        """'0 0 * * *' salta il giorno corrente già passato."""
        self.assertEqual(
            next_runs("0 0 * * *", datetime(2026, 1, 1, 0, 0), 2),
            [d(2026, 1, 2), d(2026, 1, 3)],
        )

    def test_strettamente_successivo_con_secondi(self):
        """Con secondi > 0 il primo match è il minuto successivo."""
        self.assertEqual(
            next_runs("* * * * *", datetime(2026, 1, 1, 0, 0, 30), 1),
            [d(2026, 1, 1, 0, 1)],
        )

    def test_step_quarter_ora(self):
        """'*/15 * * * *' produce i minuti 15, 30, 45 dopo le 00:00."""
        self.assertEqual(
            next_runs("*/15 * * * *", datetime(2026, 1, 1, 0, 0), 3),
            [d(2026, 1, 1, 0, 15), d(2026, 1, 1, 0, 30), d(2026, 1, 1, 0, 45)],
        )

    def test_intervallo_con_step_in_ora(self):
        """'10-20/5 3 * * *' produce le ore 3:10, 3:15, 3:20."""
        self.assertEqual(
            next_runs("10-20/5 3 * * *", datetime(2026, 1, 1), 3),
            [d(2026, 1, 1, 3, 10), d(2026, 1, 1, 3, 15), d(2026, 1, 1, 3, 20)],
        )

    def test_lista_giorni_del_mese(self):
        """'0 12 1,15 * *' salta al 15 gennaio poi al 1 febbraio."""
        self.assertEqual(
            next_runs("0 12 1,15 * *", datetime(2026, 1, 2), 2),
            [d(2026, 1, 15, 12), d(2026, 2, 1, 12)],
        )

    def test_29_febbraio_bisestile(self):
        """'0 0 29 2 *' restituisce i 29 febbraio degli anni bisestili."""
        self.assertEqual(
            next_runs("0 0 29 2 *", datetime(2026, 1, 1), 2),
            [d(2028, 2, 29), d(2032, 2, 29)],
        )

    def test_domenica_7_e_0_equivalenti(self):
        """'0 0 * * 7' e '0 0 * * 0' danno la stessa domenica."""
        self.assertEqual(
            next_runs("0 0 * * 7", datetime(2026, 11, 22), 1),
            [d(2026, 11, 29)],
        )
        self.assertEqual(
            next_runs("0 0 * * 0", datetime(2026, 11, 22), 1),
            [d(2026, 11, 29)],
        )

    def test_rollover_fine_anno(self):
        """'59 23 31 12 *' dal 31/12 alle 23:59 salta all'anno successivo."""
        self.assertEqual(
            next_runs("59 23 31 12 *", datetime(2026, 12, 31, 23, 59), 1),
            [d(2027, 12, 31, 23, 59)],
        )

    def test_intervallo_giorni_settimana(self):
        """'0 9 * * 1-5' da un sabato salta al lunedì successivo."""
        self.assertEqual(
            next_runs("0 9 * * 1-5", datetime(2026, 11, 21), 1),
            [d(2026, 11, 23, 9)],
        )

    def test_ora_locale_convertita_in_utc(self):
        """Un start_dt aware in +02:00 viene convertito in UTC."""
        start = datetime(2026, 1, 1, 1, 0, tzinfo=timezone(timedelta(hours=2)))
        self.assertEqual(next_runs("0 0 * * *", start, 1), [d(2026, 1, 1)])

    def test_naive_interpretato_come_utc(self):
        """Un start_dt naive è interpretato come UTC."""
        r = next_runs("5 4 * * *", datetime(2026, 1, 1))
        self.assertEqual(len(r), 5)
        self.assertTrue(all(x.tzinfo == UTC for x in r))
        self.assertEqual(r[0], d(2026, 1, 1, 4, 5))

    def test_count_zero(self):
        """count=0 restituisce una lista vuota."""
        self.assertEqual(next_runs("* * * * *", datetime(2026, 1, 1), 0), [])

    def test_count_negativo(self):
        """count negativo solleva ValueError."""
        with self.assertRaises(ValueError):
            next_runs("* * * * *", datetime(2026, 1, 1), -1)

    def test_count_non_intero(self):
        """count non intero (es. float) solleva ValueError."""
        with self.assertRaises(ValueError):
            next_runs("* * * * *", datetime(2026, 1, 1), 2.5)

    def test_ordinamento_crescente(self):
        """I risultati sono in ordine strettamente crescente."""
        r = next_runs("*/15 * * * *", datetime(2026, 1, 1, 0, 0), 10)
        self.assertEqual(r, sorted(r))
        self.assertEqual(len(set(r)), len(r))


class TestSemanticaGiorno(unittest.TestCase):
    """Test della semantica Vixie per giorno_mese/giorno_settimana."""

    def test_or_quando_entrambi_ristretti(self):
        """Con entrambi i campi ristretti vale l'OR dei due."""
        # 13 del mese OPPURE venerdì: da 2026-11-01 (sabato) i match sono
        # venerdì 6, 13 (anche il 13) e 20 novembre.
        self.assertEqual(
            next_runs("0 0 13 * 5", datetime(2026, 11, 1), 3),
            [d(2026, 11, 6), d(2026, 11, 13), d(2026, 11, 20)],
        )

    def test_solo_giorno_mese_ristretto(self):
        """Con solo giorno_mese ristretto vale solo quello."""
        c = parse_cron("0 0 13 * *")
        self.assertTrue(c.day_matches(13, 0))
        self.assertFalse(c.day_matches(14, 0))

    def test_solo_giorno_settimana_ristretto(self):
        """Con solo giorno_settimana ristretto vale solo quello."""
        c = parse_cron("0 0 * * 1")
        self.assertTrue(c.day_matches(1, 1))
        self.assertFalse(c.day_matches(1, 2))


class TestIterCron(unittest.TestCase):
    """Test del generatore iter_cron."""

    def test_iter_cron_accetta_cronexpr(self):
        """iter_cron accetta anche un oggetto CronExpr già analizzato."""
        c = parse_cron("0 0 * * *")
        r = list(islice(iter_cron(c, datetime(2026, 1, 1, 0, 0)), 2))
        self.assertEqual(r, [d(2026, 1, 2), d(2026, 1, 3)])

    def test_iter_cron_secondi_a_zero(self):
        """I datetime restituiti hanno secondi e microsecondi a zero."""
        r = list(islice(iter_cron("* * * * *", datetime(2026, 1, 1, 0, 0, 30)), 3))
        self.assertTrue(all(x.second == 0 and x.microsecond == 0 for x in r))
        self.assertTrue(all(x.tzinfo == UTC for x in r))


class TestValueError(unittest.TestCase):
    """Test dei casi di errore: ogni espressione deve sollevare ValueError."""

    def test_espressioni_non_valide(self):
        """Un insieme di espressioni non valide solleva ValueError."""
        bad = [
            "",
            "* * * *",
            "* * * * * *",
            "60 * * * *",
            "* 24 * * *",
            "* * 0 * *",
            "* * 32 * *",
            "* * * 13 *",
            "* * * * 8",
            "5-1 * * * *",
            "*/0 * * * *",
            "1,,2 * * * *",
            "a * * * *",
            "* * * * MON",
            "-1 * * * *",
            "0 0 31 2 *",
            "0 0 30 2 *",
            "*/x * * * *",
            "L * * * *",
        ]
        for expr in bad:
            with self.assertRaises(ValueError, msg=repr(expr)):
                next_runs(expr, datetime(2026, 1, 1))

    def test_expr_non_stringa(self):
        """Un'espressione non stringa solleva ValueError."""
        with self.assertRaises(ValueError):
            parse_cron(None)
        with self.assertRaises(ValueError):
            parse_cron(12345)

    def test_messaggi_indicano_il_campo(self):
        """I messaggi di errore indicano il campo coinvolto."""
        with self.assertRaises(ValueError) as ctx:
            parse_cron("60 * * * *")
        self.assertIn("minuto", str(ctx.exception))
        with self.assertRaises(ValueError) as ctx:
            parse_cron("* 24 * * *")
        self.assertIn("ora", str(ctx.exception))
        with self.assertRaises(ValueError) as ctx:
            parse_cron("* * 32 * *")
        self.assertIn("giorno_mese", str(ctx.exception))
        with self.assertRaises(ValueError) as ctx:
            parse_cron("* * * 13 *")
        self.assertIn("mese", str(ctx.exception))
        with self.assertRaises(ValueError) as ctx:
            parse_cron("* * * * 8")
        self.assertIn("giorno_settimana", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
