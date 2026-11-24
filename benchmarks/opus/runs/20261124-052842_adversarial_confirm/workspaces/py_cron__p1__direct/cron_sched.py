"""Parser e iteratore per espressioni cron a 5 campi.

Campi: minuto, ora, giorno_mese, mese, giorno_settimana.

Sintassi supportata per ogni campo:
    *        tutti i valori
    n        un numero
    a-b      intervallo inclusivo
    a,b,c    lista (ogni elemento può essere una qualsiasi delle altre forme)
    */n      step su tutto l'intervallo
    a-b/n    step su un intervallo
    a/n      step da a fino al massimo del campo

Giorno della settimana: 0-6 con 0 = domenica; 7 è accettato come domenica.

Semantica (come Vixie cron): se sia giorno_mese sia giorno_settimana sono
ristretti (cioè non iniziano con '*'), una data corrisponde se soddisfa
almeno uno dei due; altrimenti devono essere soddisfatti entrambi.

Tutti i calcoli avvengono in UTC. Un ``start_dt`` naive è interpretato come
UTC; uno aware viene convertito in UTC. I risultati sono datetime aware UTC.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import FrozenSet, Iterator, List

__all__ = ["CronExpr", "parse", "iter_runs", "next_runs"]

# (nome, minimo, massimo)
_FIELDS = (
    ("minuto", 0, 59),
    ("ora", 0, 23),
    ("giorno_mese", 1, 31),
    ("mese", 1, 12),
    ("giorno_settimana", 0, 7),
)

# Giorni massimi per mese (febbraio con anno bisestile).
_MAX_DAYS = {1: 31, 2: 29, 3: 31, 4: 30, 5: 31, 6: 30,
             7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31}

# Limite di sicurezza per la ricerca: un'espressione valida e soddisfacibile
# trova sempre una corrispondenza entro 8 anni (29 febbraio di lunedì ecc.
# rientra in un ciclo di 28 anni, quindi usiamo un margine ampio).
_MAX_SEARCH_YEARS = 30


def _parse_int(text: str, name: str) -> int:
    if not text or not text.isascii() or not text.isdigit():
        raise ValueError(f"valore non numerico {text!r} nel campo {name}")
    return int(text)


def _parse_field(text: str, name: str, lo: int, hi: int) -> FrozenSet[int]:
    if not text:
        raise ValueError(f"campo {name} vuoto")
    values = set()
    for part in text.split(","):
        if not part:
            raise ValueError(f"elemento vuoto nella lista del campo {name}")
        if part.count("/") > 1:
            raise ValueError(f"step multipli in {part!r} (campo {name})")
        base, sep, step_txt = part.partition("/")
        if sep:
            step = _parse_int(step_txt, name)
            if step < 1:
                raise ValueError(f"step deve essere >= 1 in {part!r} (campo {name})")
        else:
            step = 1

        if base == "*":
            start, end = lo, hi
        elif "-" in base:
            a_txt, _, b_txt = base.partition("-")
            start = _parse_int(a_txt, name)
            end = _parse_int(b_txt, name)
            if start > end:
                raise ValueError(f"intervallo invertito {base!r} (campo {name})")
        else:
            start = _parse_int(base, name)
            # 'a/n' significa da a fino al massimo; 'a' da solo è un valore singolo.
            end = hi if sep else start

        if start < lo or end > hi:
            raise ValueError(
                f"valore fuori intervallo {lo}-{hi} in {part!r} (campo {name})"
            )
        values.update(range(start, end + 1, step))
    return frozenset(values)


@dataclass(frozen=True)
class CronExpr:
    minutes: FrozenSet[int]
    hours: FrozenSet[int]
    days: FrozenSet[int]
    months: FrozenSet[int]
    weekdays: FrozenSet[int]  # 0 = domenica ... 6 = sabato
    dom_restricted: bool
    dow_restricted: bool

    def matches_day(self, year: int, month: int, day: int) -> bool:
        if month not in self.months:
            return False
        # datetime.weekday(): lunedì=0 ... domenica=6 -> cron: domenica=0
        cron_dow = (calendar.weekday(year, month, day) + 1) % 7
        dom_ok = day in self.days
        dow_ok = cron_dow in self.weekdays
        if self.dom_restricted and self.dow_restricted:
            return dom_ok or dow_ok
        return dom_ok and dow_ok

    def matches(self, dt: datetime) -> bool:
        return (
            dt.minute in self.minutes
            and dt.hour in self.hours
            and self.matches_day(dt.year, dt.month, dt.day)
        )


def parse(expr: str) -> CronExpr:
    """Analizza un'espressione cron a 5 campi. Solleva ValueError se non valida."""
    if not isinstance(expr, str):
        raise ValueError("l'espressione cron deve essere una stringa")
    parts = expr.split()
    if len(parts) != 5:
        raise ValueError(
            f"attesi 5 campi, trovati {len(parts)} in {expr!r}"
        )
    sets = [
        _parse_field(text, name, lo, hi)
        for text, (name, lo, hi) in zip(parts, _FIELDS)
    ]
    weekdays = frozenset(d % 7 for d in sets[4])
    cron = CronExpr(
        minutes=sets[0],
        hours=sets[1],
        days=sets[2],
        months=sets[3],
        weekdays=weekdays,
        dom_restricted=not parts[2].startswith("*"),
        dow_restricted=not parts[4].startswith("*"),
    )
    _check_satisfiable(cron, expr)
    return cron


def _check_satisfiable(cron: CronExpr, expr: str) -> None:
    """Rifiuta espressioni che non possono mai scattare (es. '0 0 30 2 *')."""
    if cron.dom_restricted and cron.dow_restricted:
        return  # basta il giorno della settimana: ogni mese ha tutti i giorni
    if any(d <= _MAX_DAYS[m] for m in cron.months for d in cron.days):
        return
    raise ValueError(f"l'espressione {expr!r} non corrisponde a nessuna data")


def _to_utc(dt: datetime) -> datetime:
    if not isinstance(dt, datetime):
        raise TypeError("start_dt deve essere un datetime")
    if dt.tzinfo is None or dt.utcoffset() is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def iter_runs(expr, start_dt: datetime) -> Iterator[datetime]:
    """Itera all'infinito sulle esecuzioni strettamente successive a start_dt."""
    cron = expr if isinstance(expr, CronExpr) else parse(expr)
    start = _to_utc(start_dt)
    # Primo minuto candidato: strettamente dopo start.
    cur = start.replace(second=0, microsecond=0) + timedelta(minutes=1)

    minutes = sorted(cron.minutes)
    hours = sorted(cron.hours)
    limit_year = cur.year + _MAX_SEARCH_YEARS

    year, month, day = cur.year, cur.month, cur.day
    first_hour, first_minute = cur.hour, cur.minute

    while year <= limit_year:
        if month not in cron.months:
            month, day = month + 1, 1
            first_hour = first_minute = 0
            if month > 12:
                year, month = year + 1, 1
            continue

        ndays = calendar.monthrange(year, month)[1]
        while day <= ndays:
            if cron.matches_day(year, month, day):
                for h in hours:
                    if h < first_hour:
                        continue
                    for m in minutes:
                        if h == first_hour and m < first_minute:
                            continue
                        yield datetime(year, month, day, h, m, tzinfo=timezone.utc)
            day += 1
            first_hour = first_minute = 0

        month, day = month + 1, 1
        if month > 12:
            year, month = year + 1, 1

    raise ValueError(  # pragma: no cover - protetto da _check_satisfiable
        f"nessuna esecuzione trovata entro {_MAX_SEARCH_YEARS} anni"
    )


def next_runs(expr: str, start_dt: datetime, count: int = 5) -> List[datetime]:
    """Restituisce i prossimi ``count`` datetime UTC strettamente dopo start_dt.

    Solleva ValueError per espressioni non valide o ``count`` negativo.
    """
    if isinstance(count, bool) or not isinstance(count, int):
        raise ValueError("count deve essere un intero")
    if count < 0:
        raise ValueError("count deve essere >= 0")
    cron = parse(expr)  # valida subito, anche con count == 0
    result: List[datetime] = []
    if count == 0:
        return result
    for run in iter_runs(cron, start_dt):
        result.append(run)
        if len(result) >= count:
            break
    return result
