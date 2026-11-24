"""Parser e iteratore di espressioni cron a 5 campi.

Supporta i campi classico stile Vixie cron:

    minuto, ora, giorno_mese, mese, giorno_settimana

con la sintassi ``*``, numeri, intervalli ``a-b``, liste ``a,b,c``,
step ``*/n`` e ``a-b/n`` (e ``N/n``).

La semantica dei giorni segue Vixie cron: se sia ``giorno_mese`` sia
``giorno_settimana`` sono ristretti (il campo non inizia con ``*``), il
giorno corrisponde se corrisponde ALMENO UNO dei due; se uno dei due
inizia con ``*`` vale solo l'altro.

Tutti i ``datetime`` restituiti sono ``aware`` con
``tzinfo=datetime.timezone.utc`` e secondi/microsecondi a zero.
"""

from __future__ import annotations

import calendar
from datetime import datetime, timedelta, timezone

__all__ = ["CronExpression", "parse", "next_runs"]

# (nome campo, minimo, massimo) nell'ordine dei 5 campi.
_FIELDS = (
    ("minuto", 0, 59),
    ("ora", 0, 23),
    ("giorno_mese", 1, 31),
    ("mese", 1, 12),
    ("giorno_settimana", 0, 7),
)

# Numero massimo di anni da cercare prima di dichiarare un'espressione
# valida ma mai soddisfacibile (es. "0 0 30 2 *").
_MAX_YEARS = 28


def _parse_field(field: str, name: str, lo: int, hi: int) -> frozenset:
    """Analizza un singolo campo cron e restituisce il frozenset di valori.

    ``name`` è il nome del campo (per i messaggi d'errore), ``lo`` e ``hi``
    i limiti del range. Solleva ``ValueError`` con messaggio descrittivo in
    italiano per ogni elemento non valido.
    """
    values: set[int] = set()
    for element in field.split(","):
        if element == "":
            raise ValueError(
                f"campo {name}: elemento vuoto nella lista (es. '1,,2' o ',')"
            )
        step = 1
        base = element
        has_step = False
        if "/" in element:
            base, _, step_text = element.partition("/")
            if step_text == "" or not step_text.isdigit():
                raise ValueError(
                    f"campo {name}: step non numerico '{step_text}' in '{element}'"
                )
            step = int(step_text)
            if step <= 0:
                raise ValueError(
                    f"campo {name}: step {step} deve essere maggiore di 0 in '{element}'"
                )
            has_step = True
        if base == "*":
            start, end = lo, hi
        elif "-" in base:
            a_text, _, b_text = base.partition("-")
            if not a_text.isdigit() or not b_text.isdigit():
                raise ValueError(
                    f"campo {name}: intervallo non numerico '{base}'"
                )
            start, end = int(a_text), int(b_text)
            if start > end:
                raise ValueError(
                    f"campo {name}: intervallo invertito {start}-{end} (a > b)"
                )
        elif base.isdigit():
            start = int(base)
            # 'N/n' = da N al massimo del range con passo n.
            end = hi if has_step else start
        else:
            raise ValueError(
                f"campo {name}: elemento non valido '{element}'"
            )
        if start < lo or end > hi:
            raise ValueError(
                f"campo {name}: valore {start if start == end else f'{start}-{end}'} "
                f"fuori range {lo}-{hi}"
            )
        values.update(range(start, end + 1, step))
    return frozenset(values)


class CronExpression:
    """Espressione cron a 5 campi analizzata.

    Attributi ``minutes``, ``hours``, ``days``, ``months`` e ``weekdays``
    sono ``frozenset`` di ``int``. I ``weekdays`` sono normalizzati: ``7``
    (domenica) diventa ``0``.
    """

    def __init__(self, expr: str) -> None:
        if not isinstance(expr, str):
            raise ValueError(
                f"espressione cron non valida: atteso str, ricevuto {type(expr).__name__}"
            )
        fields = expr.split()
        if len(fields) != 5:
            raise ValueError(
                f"espressione cron non valida: attesi 5 campi, trovati {len(fields)}"
            )
        self.minutes = _parse_field(fields[0], *_FIELDS[0])
        self.hours = _parse_field(fields[1], *_FIELDS[1])
        self.days = _parse_field(fields[2], *_FIELDS[2])
        self.months = _parse_field(fields[3], *_FIELDS[3])
        self.weekdays = _parse_field(fields[4], *_FIELDS[4])
        # Normalizza 7 -> 0 (domenica).
        if 7 in self.weekdays:
            self.weekdays = frozenset(
                (0 if v == 7 else v) for v in self.weekdays
            )
        # Semantica Vixie cron: un campo "ristretto" è quello che non inizia
        # con '*'.
        self._dom_restricted = not fields[2].startswith("*")
        self._dow_restricted = not fields[4].startswith("*")

    def _day_matches(self, dt: datetime) -> bool:
        """Verifica il giorno secondo la semantica Vixie cron."""
        dom_ok = dt.day in self.days
        dow_ok = (dt.weekday() + 1) % 7 in self.weekdays
        if self._dom_restricted and self._dow_restricted:
            return dom_ok or dow_ok
        if self._dom_restricted:
            return dom_ok
        if self._dow_restricted:
            return dow_ok
        return True

    def matches(self, dt: datetime) -> bool:
        """Restituisce ``True`` se ``dt`` (a livello di minuto) corrisponde."""
        if dt.minute not in self.minutes:
            return False
        if dt.hour not in self.hours:
            return False
        if dt.month not in self.months:
            return False
        return self._day_matches(dt)

    def iter(self, start_dt: datetime):
        """Generatore infinito dei ``datetime`` UTC successivi a ``start_dt``.

        ``start_dt`` naive è interpretato come UTC; ``start_dt`` aware viene
        convertito in UTC. I risultati sono ``aware`` con
        ``tzinfo=datetime.timezone.utc`` e secondi/microsecondi a zero,
        strettamente successivi a ``start_dt``.

        La ricerca salta interi mesi/giorni/ore non corrispondenti invece di
        iterare minuto per minuto. Un'espressione valida ma mai soddisfacibile
        (es. "0 0 30 2 *") solleva ``ValueError`` dopo _MAX_YEARS anni.
        """
        if start_dt.tzinfo is None:
            start = start_dt.replace(tzinfo=timezone.utc)
        else:
            start = start_dt.astimezone(timezone.utc)
        # Primo minuto strettamente successivo a start.
        cur = (start + timedelta(minutes=1)).replace(second=0, microsecond=0)
        # Limita la ricerca a _MAX_YEARS anni: un'espressione valida ma mai
        # soddisfacibile (es. "0 0 30 2 *") solleva ValueError.
        limit = cur + timedelta(days=366 * _MAX_YEARS)
        hours = sorted(self.hours)
        minutes = sorted(self.minutes)
        while cur < limit:
            if cur.month not in self.months:
                # Salta al primo giorno del mese successivo.
                if cur.month == 12:
                    cur = cur.replace(year=cur.year + 1, month=1, day=1,
                                      hour=0, minute=0)
                else:
                    cur = cur.replace(month=cur.month + 1, day=1,
                                      hour=0, minute=0)
                continue
            if not self._day_matches(cur):
                # Salta al giorno successivo.
                cur = (cur + timedelta(days=1)).replace(hour=0, minute=0)
                continue
            # Mese e giorno corrispondono: trova il primo (ora, minuto) valido
            # maggiore o uguale a (cur.hour, cur.minute).
            found = None
            for h in hours:
                if h < cur.hour:
                    continue
                for m in minutes:
                    if h == cur.hour and m < cur.minute:
                        continue
                    found = (h, m)
                    break
                if found is not None:
                    break
            if found is None:
                # Nessuna ora valida oggi: salta al giorno successivo.
                cur = (cur + timedelta(days=1)).replace(hour=0, minute=0)
                continue
            h, m = found
            yield cur.replace(hour=h, minute=m)
            # Avanza oltre il minuto appena prodotto (gestisce gli overflow).
            cur = cur.replace(hour=h, minute=m) + timedelta(minutes=1)
        raise ValueError(
            "espressione cron non soddisfacibile: nessun risultato trovato "
            f"nei {_MAX_YEARS} anni successivi a {start.isoformat()}"
        )


def parse(expr: str) -> CronExpression:
    """Analizza ``expr`` e restituisce un :class:`CronExpression`."""
    return CronExpression(expr)


def next_runs(expr: str, start_dt: datetime, count: int = 5) -> list[datetime]:
    """Restituisce i prossimi ``count`` ``datetime`` UTC successivi a ``start_dt``.

    ``count`` deve essere un ``int`` maggiore o uguale a zero; ``count=0``
    restituisce ``[]``. Solleva ``ValueError`` per espressioni non valide o
    mai soddisfabili.
    """
    if isinstance(count, bool) or not isinstance(count, int):
        raise ValueError(
            f"count non valido: atteso int, ricevuto {type(count).__name__}"
        )
    if count < 0:
        raise ValueError(f"count non valido: {count} deve essere maggiore o uguale a 0")
    if count == 0:
        return []
    expr_obj = CronExpression(expr)
    results: list[datetime] = []
    for dt in expr_obj.iter(start_dt):
        results.append(dt)
        if len(results) == count:
            break
    return results
