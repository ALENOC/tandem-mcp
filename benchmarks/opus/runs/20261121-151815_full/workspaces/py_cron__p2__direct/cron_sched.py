"""Parser e iteratore per espressioni cron a 5 campi.

Campi: minuto, ora, giorno_mese, mese, giorno_settimana.
Sintassi supportata per ogni campo: ``*``, numeri, intervalli ``a-b``,
liste ``a,b,c``, step ``*/n`` e ``a-b/n`` (anche combinati in liste).

Il giorno della settimana accetta 0-7 (0 e 7 = domenica). Come in cron
classico, se sia giorno_mese sia giorno_settimana sono ristretti (non ``*``),
una data corrisponde quando soddisfa almeno uno dei due.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import FrozenSet, Iterator, List

__all__ = ["CronExpression", "parse", "iter_runs", "next_runs"]

# (nome, minimo, massimo)
_FIELDS = (
    ("minuto", 0, 59),
    ("ora", 0, 23),
    ("giorno_mese", 1, 31),
    ("mese", 1, 12),
    ("giorno_settimana", 0, 7),
)

# Limite di ricerca: oltre questo orizzonte l'espressione è considerata
# impossibile (es. "0 0 31 2 *"). 29 febbraio ricorre al più ogni 8 anni.
_MAX_YEARS = 12


def _parse_int(text: str, name: str) -> int:
    if not text or not text.isdigit():
        raise ValueError(f"valore non valido {text!r} nel campo {name}")
    return int(text)


def _parse_field(text: str, name: str, lo: int, hi: int) -> FrozenSet[int]:
    if not isinstance(text, str) or text == "":
        raise ValueError(f"campo {name} vuoto")
    values = set()
    for part in text.split(","):
        if part == "":
            raise ValueError(f"elemento vuoto nella lista del campo {name}")
        if "/" in part:
            base, _, step_txt = part.partition("/")
            step = _parse_int(step_txt, name)
            if step <= 0:
                raise ValueError(f"step deve essere > 0 nel campo {name}")
            if base == "*":
                start, end = lo, hi
            elif "-" in base:
                start, end = _parse_range(base, name)
            else:
                raise ValueError(
                    f"step ammesso solo dopo '*' o 'a-b' nel campo {name}: {part!r}"
                )
        elif part == "*":
            start, end, step = lo, hi, 1
        elif "-" in part:
            start, end = _parse_range(part, name)
            step = 1
        else:
            start = end = _parse_int(part, name)
            step = 1
        if start < lo or end > hi:
            raise ValueError(
                f"valore fuori intervallo {lo}-{hi} nel campo {name}: {part!r}"
            )
        if start > end:
            raise ValueError(f"intervallo invertito nel campo {name}: {part!r}")
        values.update(range(start, end + 1, step))
    return frozenset(values)


def _parse_range(text: str, name: str):
    a, sep, b = text.partition("-")
    if not sep:
        raise ValueError(f"intervallo non valido nel campo {name}: {text!r}")
    return _parse_int(a, name), _parse_int(b, name)


@dataclass(frozen=True)
class CronExpression:
    minutes: FrozenSet[int]
    hours: FrozenSet[int]
    days: FrozenSet[int]
    months: FrozenSet[int]
    weekdays: FrozenSet[int]  # 0 = domenica ... 6 = sabato
    dom_restricted: bool
    dow_restricted: bool

    def matches_day(self, d: date) -> bool:
        if d.month not in self.months:
            return False
        dom_ok = d.day in self.days
        dow_ok = (d.isoweekday() % 7) in self.weekdays
        if self.dom_restricted and self.dow_restricted:
            return dom_ok or dow_ok
        return dom_ok and dow_ok

    def matches(self, dt: datetime) -> bool:
        return (
            dt.minute in self.minutes
            and dt.hour in self.hours
            and self.matches_day(dt.date())
        )


def parse(expr: str) -> CronExpression:
    """Analizza un'espressione cron a 5 campi; solleva ValueError se non valida."""
    if not isinstance(expr, str):
        raise ValueError("l'espressione cron deve essere una stringa")
    parts = expr.split()
    if len(parts) != 5:
        raise ValueError(
            f"l'espressione cron deve avere 5 campi, trovati {len(parts)}: {expr!r}"
        )
    sets = [
        _parse_field(text, name, lo, hi)
        for text, (name, lo, hi) in zip(parts, _FIELDS)
    ]
    weekdays = frozenset(v % 7 for v in sets[4])
    return CronExpression(
        minutes=sets[0],
        hours=sets[1],
        days=sets[2],
        months=sets[3],
        weekdays=weekdays,
        dom_restricted=parts[2] != "*",
        dow_restricted=parts[4] != "*",
    )


def _to_utc(dt: datetime) -> datetime:
    if not isinstance(dt, datetime):
        raise TypeError("start_dt deve essere un datetime")
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def iter_runs(expr, start_dt: datetime) -> Iterator[datetime]:
    """Genera all'infinito i datetime UTC (aware) strettamente successivi a start_dt.

    ``start_dt`` naive è interpretato come UTC. Solleva ValueError se
    l'espressione non produce occorrenze entro l'orizzonte di ricerca.
    """
    cron = expr if isinstance(expr, CronExpression) else parse(expr)
    minutes = sorted(cron.minutes)
    hours = sorted(cron.hours)

    current = _to_utc(start_dt).replace(second=0, microsecond=0) + timedelta(minutes=1)
    day = current.date()
    first_day = True
    days_without_match = 0
    max_days = _MAX_YEARS * 366

    while True:
        if cron.matches_day(day):
            days_without_match = 0
            for h in hours:
                if first_day and h < current.hour:
                    continue
                for m in minutes:
                    if first_day and h == current.hour and m < current.minute:
                        continue
                    yield datetime(day.year, day.month, day.day, h, m,
                                   tzinfo=timezone.utc)
        else:
            days_without_match += 1
            if days_without_match > max_days:
                raise ValueError(
                    "l'espressione cron non produce occorrenze "
                    f"entro {_MAX_YEARS} anni"
                )
        first_day = False
        if day == date.max:
            return
        day += timedelta(days=1)


def next_runs(expr: str, start_dt: datetime, count: int = 5) -> List[datetime]:
    """Restituisce i prossimi ``count`` datetime UTC successivi a ``start_dt``."""
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ValueError("count deve essere un intero >= 0")
    cron = parse(expr)  # valida subito, anche con count == 0
    result: List[datetime] = []
    if count == 0:
        return result
    for run in iter_runs(cron, start_dt):
        result.append(run)
        if len(result) >= count:
            break
    return result

