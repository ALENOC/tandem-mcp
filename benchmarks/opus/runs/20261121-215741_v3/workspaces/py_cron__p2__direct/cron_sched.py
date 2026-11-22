"""Parser e iteratore di espressioni cron a 5 campi.

Campi: minuto ora giorno_mese mese giorno_settimana
Sintassi supportata per ogni campo: ``*``, numeri, intervalli ``a-b``,
liste ``a,b,c``, step ``*/n`` e ``a-b/n`` (anche ``a/n`` = da a fino al massimo).

Giorno della settimana: 0-6 con 0 = domenica (7 accettato come domenica).
Come nel cron classico, se sia giorno_mese sia giorno_settimana sono
ristretti (non ``*``), basta che ne corrisponda uno dei due.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import FrozenSet, Iterator, List

__all__ = ["CronExpr", "parse", "iter_runs", "next_runs"]

# (nome, minimo, massimo)
_FIELDS = (
    ("minute", 0, 59),
    ("hour", 0, 23),
    ("day_of_month", 1, 31),
    ("month", 1, 12),
    ("day_of_week", 0, 7),
)

# Oltre questo orizzonte un'espressione è considerata impossibile
# (28 anni coprono il ciclo completo bisestile/giorno della settimana).
_MAX_YEARS = 28 * 2


def _parse_int(text: str, field: str) -> int:
    if not text.isdigit():
        raise ValueError(f"valore non valido {text!r} nel campo {field}")
    return int(text)


def _parse_field(text: str, field: str, lo: int, hi: int) -> FrozenSet[int]:
    if not text:
        raise ValueError(f"campo {field} vuoto")
    values = set()
    for part in text.split(","):
        if not part:
            raise ValueError(f"elemento vuoto nella lista del campo {field}")
        if "/" in part:
            base, _, step_txt = part.partition("/")
            step = _parse_int(step_txt, field)
            if step <= 0:
                raise ValueError(f"step deve essere > 0 nel campo {field}")
        else:
            base, step = part, 1

        if base == "*":
            start, end = lo, hi
        elif "-" in base:
            a, _, b = base.partition("-")
            start, end = _parse_int(a, field), _parse_int(b, field)
            if start > end:
                raise ValueError(
                    f"intervallo {base!r} invertito nel campo {field}")
        else:
            start = _parse_int(base, field)
            # "a/n" significa da a fino al massimo con passo n
            end = hi if "/" in part else start

        if start < lo or end > hi:
            raise ValueError(
                f"{part!r} fuori dai limiti {lo}-{hi} nel campo {field}")
        values.update(range(start, end + 1, step))
    return frozenset(values)


@dataclass(frozen=True)
class CronExpr:
    minutes: FrozenSet[int]
    hours: FrozenSet[int]
    days_of_month: FrozenSet[int]
    months: FrozenSet[int]
    days_of_week: FrozenSet[int]  # 0 = domenica .. 6 = sabato
    dom_restricted: bool
    dow_restricted: bool

    def matches_day(self, d: date) -> bool:
        if d.month not in self.months:
            return False
        dom_ok = d.day in self.days_of_month
        dow_ok = (d.isoweekday() % 7) in self.days_of_week
        if self.dom_restricted and self.dow_restricted:
            return dom_ok or dow_ok
        return dom_ok and dow_ok

    def matches(self, dt: datetime) -> bool:
        return (dt.minute in self.minutes and dt.hour in self.hours
                and self.matches_day(dt.date()))


def parse(expr: str) -> CronExpr:
    """Analizza un'espressione cron a 5 campi; ValueError se non valida."""
    if not isinstance(expr, str):
        raise ValueError("l'espressione cron deve essere una stringa")
    parts = expr.split()
    if len(parts) != 5:
        raise ValueError(
            f"attesi 5 campi, trovati {len(parts)}: {expr!r}")
    sets = [_parse_field(p, name, lo, hi)
            for p, (name, lo, hi) in zip(parts, _FIELDS)]
    dow = frozenset(v % 7 for v in sets[4])
    return CronExpr(
        minutes=sets[0], hours=sets[1], days_of_month=sets[2],
        months=sets[3], days_of_week=dow,
        dom_restricted=not parts[2].startswith("*"),
        dow_restricted=not parts[4].startswith("*"),
    )


def _to_utc(dt: datetime) -> datetime:
    if not isinstance(dt, datetime):
        raise TypeError("start_dt deve essere un datetime")
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def iter_runs(expr, start_dt: datetime) -> Iterator[datetime]:
    """Genera all'infinito gli istanti UTC (strettamente) successivi a start_dt.

    ``expr`` può essere una stringa o un CronExpr già analizzato.
    Solleva ValueError se l'espressione non è valida o non può mai scattare.
    """
    cron = expr if isinstance(expr, CronExpr) else parse(expr)
    start = _to_utc(start_dt).replace(second=0, microsecond=0)
    start += timedelta(minutes=1)  # strettamente successivo

    hours = sorted(cron.hours)
    minutes = sorted(cron.minutes)
    day = start.date()
    first_day = True
    days_without_match = 0
    max_days = 366 * _MAX_YEARS
    while True:
        if cron.matches_day(day):
            days_without_match = 0
            for h in hours:
                if first_day and h < start.hour:
                    continue
                for m in minutes:
                    if first_day and h == start.hour and m < start.minute:
                        continue
                    yield datetime(day.year, day.month, day.day, h, m,
                                   tzinfo=timezone.utc)
        else:
            days_without_match += 1
            if days_without_match > max_days:
                raise ValueError(
                    "l'espressione cron non corrisponde mai ad alcuna data")
        first_day = False
        try:
            day += timedelta(days=1)
        except OverflowError:
            return


def next_runs(expr: str, start_dt: datetime, count: int = 5) -> List[datetime]:
    """Restituisce i prossimi ``count`` datetime UTC successivi a start_dt."""
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        raise ValueError("count deve essere un intero >= 0")
    cron = parse(expr)  # valida subito anche con count == 0
    result: List[datetime] = []
    if count == 0:
        return result
    for dt in iter_runs(cron, start_dt):
        result.append(dt)
        if len(result) >= count:
            break
    return result
