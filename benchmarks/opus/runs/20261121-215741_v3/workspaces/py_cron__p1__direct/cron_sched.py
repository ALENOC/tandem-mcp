"""Parser e iteratore di espressioni cron a 5 campi.

Campi: minuto, ora, giorno_mese, mese, giorno_settimana.
Sintassi supportata per ogni campo: ``*``, numeri, intervalli ``a-b``,
liste ``a,b,c``, step ``*/n`` e ``a-b/n`` (anche ``a/n`` = da a al massimo).

Giorno della settimana: 0-6 con 0 = domenica; 7 è accettato come domenica.
Come in cron standard, se sia giorno_mese sia giorno_settimana sono
ristretti (non ``*``), basta che uno dei due corrisponda.
"""

from __future__ import annotations

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

# Limite di ricerca: oltre questo orizzonte l'espressione è considerata
# impossibile (es. "0 0 30 2 *"). 29 febbraio + vincoli copre <= 28 anni.
_MAX_SEARCH_DAYS = 366 * 30


@dataclass(frozen=True)
class CronExpr:
    minutes: FrozenSet[int]
    hours: FrozenSet[int]
    days: FrozenSet[int]
    months: FrozenSet[int]
    weekdays: FrozenSet[int]  # 0 = domenica
    dom_any: bool
    dow_any: bool

    def matches_day(self, d: datetime) -> bool:
        if d.month not in self.months:
            return False
        dom_ok = d.day in self.days
        cron_wd = (d.weekday() + 1) % 7  # Python: lunedì=0 -> cron: domenica=0
        dow_ok = cron_wd in self.weekdays
        if self.dom_any and self.dow_any:
            return True
        if self.dom_any:
            return dow_ok
        if self.dow_any:
            return dom_ok
        return dom_ok or dow_ok

    def matches(self, dt: datetime) -> bool:
        return (
            dt.minute in self.minutes
            and dt.hour in self.hours
            and self.matches_day(dt)
        )


def _parse_int(text: str, name: str) -> int:
    if not text or not text.isdigit():
        raise ValueError(f"valore non valido nel campo {name}: {text!r}")
    return int(text)


def _parse_field(text: str, name: str, lo: int, hi: int) -> FrozenSet[int]:
    if not text:
        raise ValueError(f"campo {name} vuoto")
    values = set()
    for part in text.split(","):
        if not part:
            raise ValueError(f"elemento vuoto nella lista del campo {name}")
        if "/" in part:
            base, _, step_txt = part.partition("/")
            step = _parse_int(step_txt, name)
            if step <= 0:
                raise ValueError(f"step deve essere > 0 nel campo {name}")
        else:
            base, step = part, 1

        if base == "*":
            start, end = lo, hi
        elif "-" in base:
            a, _, b = base.partition("-")
            start, end = _parse_int(a, name), _parse_int(b, name)
            if start > end:
                raise ValueError(
                    f"intervallo invertito nel campo {name}: {base!r}"
                )
        else:
            start = _parse_int(base, name)
            # "a/n" significa da a fino al massimo
            end = hi if "/" in part else start

        if start < lo or end > hi:
            raise ValueError(
                f"valore fuori range [{lo}-{hi}] nel campo {name}: {part!r}"
            )
        values.update(range(start, end + 1, step))
    return frozenset(values)


def parse(expr: str) -> CronExpr:
    """Analizza un'espressione cron a 5 campi. Solleva ValueError se non valida."""
    if not isinstance(expr, str):
        raise ValueError("l'espressione cron deve essere una stringa")
    parts = expr.split()
    if len(parts) != 5:
        raise ValueError(
            f"attesi 5 campi, trovati {len(parts)}: {expr!r}"
        )
    sets = [
        _parse_field(p, name, lo, hi)
        for p, (name, lo, hi) in zip(parts, _FIELDS)
    ]
    weekdays = frozenset(d % 7 for d in sets[4])
    return CronExpr(
        minutes=sets[0],
        hours=sets[1],
        days=sets[2],
        months=sets[3],
        weekdays=weekdays,
        dom_any=parts[2] == "*",
        dow_any=parts[4] == "*",
    )


def _to_utc(dt: datetime) -> datetime:
    if not isinstance(dt, datetime):
        raise ValueError("start_dt deve essere un datetime")
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)  # naive = UTC
    return dt.astimezone(timezone.utc)


def iter_runs(expr, start_dt: datetime) -> Iterator[datetime]:
    """Itera all'infinito i datetime UTC (aware) strettamente successivi a start_dt."""
    cron = expr if isinstance(expr, CronExpr) else parse(expr)
    start = _to_utc(start_dt).replace(second=0, microsecond=0) + timedelta(minutes=1)
    hours = sorted(cron.hours)
    minutes = sorted(cron.minutes)

    day = start.replace(hour=0, minute=0)
    first = True
    misses = 0
    while True:
        if cron.matches_day(day):
            misses = 0
            for h in hours:
                for m in minutes:
                    cand = day.replace(hour=h, minute=m)
                    if first and cand < start:
                        continue
                    yield cand
        else:
            misses += 1
            if misses > _MAX_SEARCH_DAYS:
                raise ValueError(f"l'espressione non produce mai esecuzioni: {expr!r}")
        first = False
        day += timedelta(days=1)


def next_runs(expr: str, start_dt: datetime, count: int = 5) -> List[datetime]:
    """Restituisce i prossimi ``count`` datetime UTC successivi a ``start_dt``."""
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        raise ValueError("count deve essere un intero >= 0")
    cron = parse(expr)  # valida subito anche con count == 0
    it = iter_runs(cron, start_dt)
    return [next(it) for _ in range(count)]
