"""Parser e iteratore di espressioni cron a 5 campi.

Questo modulo implementa un sottoinsieme della sintassi cron di Vixie:
cinque campi (minuto, ora, giorno_mese, mese, giorno_settimana) con
supporto per ``*``, numeri singoli, intervalli ``a-b``, liste ``a,b,c``,
step ``*/n`` e ``a-b/n`` (e anche ``N/n``).

Sono esposti:

* :func:`parse_cron` -> :class:`CronExpr`
* :func:`iter_cron`  -> generatore infinito di ``datetime`` UTC
* :func:`next_runs`  -> lista dei prossimi ``count`` ``datetime`` UTC

Tutti i ``datetime`` restituiti sono *timezone-aware* con
``tzinfo=datetime.timezone.utc``.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterator, List, Optional, Tuple

__all__ = ["CronExpr", "parse_cron", "iter_cron", "next_runs"]

# Ordine dei campi e loro range validi (inclusi).
# giorno_settimana: 0 e 7 = domenica, 1 = lunedi ... 6 = sabato.
_FIELD_SPECS: Tuple[Tuple[str, int, int], ...] = (
    ("minuto", 0, 59),
    ("ora", 0, 23),
    ("giorno_mese", 1, 31),
    ("mese", 1, 12),
    ("giorno_settimana", 0, 7),
)

# Numero massimo di anni da esplorare oltre start_dt prima di dichiarare
# un'espressione mai soddisfacibile (evita cicli infiniti).
_MAX_SEARCH_YEARS = 10


@dataclass(frozen=True)
class CronExpr:
    """Espressione cron a 5 campi già analizzata.

    Attributi:
        minutes: insieme dei minuti validi (0-59).
        hours: insieme delle ore valide (0-23).
        days: insieme dei giorni del mese validi (1-31).
        months: insieme dei mesi validi (1-12).
        weekdays: insieme dei giorni della settimana validi; il 7 è
            normalizzato a 0 (domenica).
        days_restricted: True se il campo giorno_mese non era ``*``.
        weekdays_restricted: True se il campo giorno_settimana non era ``*``.
    """

    minutes: frozenset
    hours: frozenset
    days: frozenset
    months: frozenset
    weekdays: frozenset
    days_restricted: bool
    weekdays_restricted: bool

    def day_matches(self, day: int, weekday: int) -> bool:
        """Restituisce True se il giorno corrisponde secondo la semantica Vixie.

        ``day`` è il giorno del mese (1-31), ``weekday`` è il giorno della
        settimana con 0 = domenica (come :meth:`datetime.weekday` + 1 mod 7).
        """
        dom_ok = day in self.days
        dow_ok = weekday in self.weekdays
        if self.days_restricted and self.weekdays_restricted:
            # Entrambi ristretti: corrisponde se corrisponde ALMENO UNO (OR).
            return dom_ok or dow_ok
        if self.days_restricted:
            return dom_ok
        if self.weekdays_restricted:
            return dow_ok
        return True


def _parse_int(token: str, field: str) -> int:
    """Converte ``token`` in intero, sollevando ValueError descrittivo."""
    try:
        return int(token)
    except ValueError:
        raise ValueError(
            f"campo {field}: valore non intero {token!r}"
        ) from None


def _parse_field(field: str, text: str, lo: int, hi: int) -> frozenset:
    """Analizza un singolo campo cron e restituisce l'insieme dei valori.

    ``field`` è il nome del campo (usato nei messaggi di errore), ``lo`` e
    ``hi`` i limiti del range. Il campo non può essere vuoto.
    """
    if text == "":
        raise ValueError(f"campo {field}: elemento vuoto")

    values: set[int] = set()
    for element in text.split(","):
        if element == "":
            raise ValueError(f"campo {field}: elemento vuoto nella lista")

        step = 1
        if "/" in element:
            base, sep, step_text = element.partition("/")
            if step_text == "":
                raise ValueError(
                    f"campo {field}: step mancante dopo '/' in {element!r}"
                )
            step = _parse_int(step_text, field)
            if step < 1:
                raise ValueError(
                    f"campo {field}: step deve essere >= 1 (ricevuto {step})"
                )
        else:
            base = element

        if base == "*":
            start, end = lo, hi
        elif "-" in base:
            a, sep, b = base.partition("-")
            start = _parse_int(a, field)
            end = _parse_int(b, field)
            if start > end:
                raise ValueError(
                    f"campo {field}: intervallo invertito {base!r} (a > b)"
                )
        else:
            start = _parse_int(base, field)
            if "/" in element:
                # 'N/n': da N fino al massimo del campo con step n.
                end = hi
            else:
                end = start

        if start < lo or end > hi:
            raise ValueError(
                f"campo {field}: valore fuori range {lo}-{hi} in {element!r}"
            )

        values.update(range(start, end + 1, step))

    return frozenset(values)


def parse_cron(expr: str) -> CronExpr:
    """Analizza un'espressione cron a 5 campi e restituisce un :class:`CronExpr`.

    Solleva :class:`ValueError` se l'espressione non è valida.
    """
    if not isinstance(expr, str):
        raise ValueError("l'espressione cron deve essere una stringa")

    fields = expr.split()
    if len(fields) != 5:
        raise ValueError(
            f"l'espressione cron deve avere esattamente 5 campi, "
            f"ne sono stati trovati {len(fields)}"
        )

    parsed = [
        _parse_field(name, text, lo, hi)
        for (name, lo, hi), text in zip(_FIELD_SPECS, fields)
    ]
    minutes, hours, days, months, weekdays = parsed

    # Normalizza il 7 (domenica) a 0.
    if 7 in weekdays:
        weekdays = frozenset((weekdays - {7}) | {0})

    days_restricted = fields[2] != "*"
    weekdays_restricted = fields[4] != "*"

    return CronExpr(
        minutes=minutes,
        hours=hours,
        days=days,
        months=months,
        weekdays=weekdays,
        days_restricted=days_restricted,
        weekdays_restricted=weekdays_restricted,
    )


def _to_utc(dt: datetime) -> datetime:
    """Converte ``dt`` in UTC: i naive sono interpretati come UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _next_month(year: int, month: int) -> Tuple[int, int]:
    """Restituisce (anno, mese) del mese successivo a (year, month)."""
    if month == 12:
        return year + 1, 1
    return year, month + 1


def iter_cron(expr, start_dt: datetime) -> Iterator[datetime]:
    """Generatore infinito di ``datetime`` UTC strettamente successivi a ``start_dt``.

    ``expr`` può essere una stringa cron o un :class:`CronExpr`. I valori
    restituiti hanno secondi e microsecondi a zero e sono in ordine
    crescente. Solleva :class:`ValueError` se l'espressione non è valida o
    se non è mai soddisfacibile entro 10 anni da ``start_dt``.
    """
    if isinstance(expr, CronExpr):
        cron = expr
    else:
        cron = parse_cron(expr)

    start = _to_utc(start_dt)
    # Primo istante candidato: il minuto successivo a start (strettamente
    # successivo), con secondi e microsecondi a zero.
    cur = (start + timedelta(minutes=1)).replace(second=0, microsecond=0)

    limit_year = start.year + _MAX_SEARCH_YEARS
    while True:
        if cur.year > limit_year:
            raise ValueError(
                "espressione cron mai soddisfacibile: nessun match entro "
                f"{_MAX_SEARCH_YEARS} anni da {start.isoformat()}"
            )

        if cur.month not in cron.months:
            # Salta al primo giorno del mese successivo.
            ny, nm = _next_month(cur.year, cur.month)
            cur = datetime(ny, nm, 1, 0, 0, tzinfo=timezone.utc)
            continue

        # Semantica Vixie per giorno_mese/giorno_settimana: la decisione
        # passa tutta da day_matches (OR se entrambi i campi sono ristretti).
        weekday = (cur.weekday() + 1) % 7  # 0 = domenica
        if not cron.day_matches(cur.day, weekday):
            # Salta al giorno successivo (gestisce il cambio di mese/anno).
            cur = (cur.replace(hour=0, minute=0) + timedelta(days=1))
            continue

        if cur.hour not in cron.hours:
            # Salta all'inizio dell'ora successiva.
            cur = (cur.replace(minute=0) + timedelta(hours=1))
            continue

        if cur.minute not in cron.minutes:
            # Salta al minuto successivo.
            cur = cur + timedelta(minutes=1)
            continue

        yield cur
        cur = cur + timedelta(minutes=1)


def next_runs(expr, start_dt: datetime, count: int = 5) -> List[datetime]:
    """Restituisce i primi ``count`` ``datetime`` UTC successivi a ``start_dt``.

    ``expr`` può essere una stringa cron o un :class:`CronExpr`.
    ``count`` deve essere un intero non negativo.
    """
    if not isinstance(count, int) or isinstance(count, bool):
        raise ValueError("count deve essere un intero")
    if count < 0:
        raise ValueError("count deve essere non negativo")

    if count == 0:
        return []

    results: List[datetime] = []
    for dt in iter_cron(expr, start_dt):
        results.append(dt)
        if len(results) == count:
            break
    return results
