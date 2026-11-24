"""Parser e iteratore per espressioni cron a 5 campi.

Campi: minuto, ora, giorno_mese, mese, giorno_settimana.
Sintassi supportata per ciascun campo: ``*``, numeri, intervalli ``a-b``,
liste ``a,b,c``, step ``*/n`` e ``a-b/n`` (anche ``a/n`` = da a al massimo).

Semantica (come Vixie cron):
- giorno_settimana: 0-7, dove sia 0 che 7 indicano la domenica.
- se sia giorno_mese sia giorno_settimana sono ristretti (non iniziano con
  ``*``), un giorno corrisponde se soddisfa ALMENO UNO dei due (OR);
  altrimenti devono valere entrambi.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
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

# Un'espressione che non produce occorrenze entro questo orizzonte non ne
# produrrà mai (il calendario gregoriano si ripete ogni 400 anni, ma 8 anni
# coprono sempre almeno un 29 febbraio e tutte le combinazioni giorno/mese).
_MAX_SEARCH_DAYS = 366 * 8 + 1


def _parse_int(token: str, name: str, lo: int, hi: int) -> int:
    if not token.isdigit():  # rifiuta segni, spazi, stringhe vuote, unicode
        raise ValueError(f"valore non numerico {token!r} nel campo {name}")
    if not token.isascii():
        raise ValueError(f"valore non numerico {token!r} nel campo {name}")
    value = int(token)
    if not lo <= value <= hi:
        raise ValueError(
            f"valore {value} fuori intervallo [{lo}-{hi}] nel campo {name}"
        )
    return value


def _parse_field(text: str, name: str, lo: int, hi: int) -> FrozenSet[int]:
    if text == "":
        raise ValueError(f"campo {name} vuoto")
    values = set()
    for part in text.split(","):
        if part == "":
            raise ValueError(f"elemento vuoto nella lista del campo {name}")
        if part.count("/") > 1:
            raise ValueError(f"step multiplo non valido {part!r} nel campo {name}")
        base, sep, step_txt = part.partition("/")
        step = 1
        if sep:
            step = _parse_int(step_txt, name, 1, 10**6) if step_txt else 0
            if step < 1:
                raise ValueError(f"step non valido {part!r} nel campo {name}")
        if base == "*":
            start, end = lo, hi
        elif "-" in base:
            a, _, b = base.partition("-")
            start = _parse_int(a, name, lo, hi)
            end = _parse_int(b, name, lo, hi)
            if start > end:
                raise ValueError(
                    f"intervallo decrescente {base!r} nel campo {name}"
                )
        else:
            start = _parse_int(base, name, lo, hi)
            end = hi if sep else start
        values.update(range(start, end + 1, step))
    return frozenset(values)


@dataclass(frozen=True)
class CronExpr:
    minutes: FrozenSet[int]
    hours: FrozenSet[int]
    days_of_month: FrozenSet[int]
    months: FrozenSet[int]
    days_of_week: FrozenSet[int]  # 0=domenica ... 6=sabato (7 normalizzato a 0)
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
        return (
            dt.minute in self.minutes
            and dt.hour in self.hours
            and self.matches_day(dt.date())
        )


def parse(expr: str) -> CronExpr:
    """Analizza un'espressione cron a 5 campi; solleva ValueError se non valida."""
    if not isinstance(expr, str):
        raise ValueError("l'espressione cron deve essere una stringa")
    parts = expr.split()
    if len(parts) != 5:
        raise ValueError(
            f"attesi 5 campi nell'espressione cron, trovati {len(parts)}"
        )
    sets = [
        _parse_field(text, name, lo, hi)
        for text, (name, lo, hi) in zip(parts, _FIELDS)
    ]
    minutes, hours, dom, months, dow = sets
    dow = frozenset(v % 7 for v in dow)

    cron = CronExpr(
        minutes=minutes,
        hours=hours,
        days_of_month=dom,
        months=months,
        days_of_week=dow,
        dom_restricted=not parts[2].startswith("*"),
        dow_restricted=not parts[4].startswith("*"),
    )
    # Rifiuta combinazioni che non possono mai verificarsi (es. 30 febbraio).
    if not (cron.dom_restricted and cron.dow_restricted):
        max_day = max(calendar.monthrange(2000, m)[1] for m in months)  # anno bisestile
        if min(dom) > max_day:
            raise ValueError(
                f"l'espressione {expr!r} non produce mai occorrenze"
            )
    return cron


def _to_utc(start_dt: datetime) -> datetime:
    if not isinstance(start_dt, datetime):
        raise TypeError("start_dt deve essere un datetime")
    if start_dt.tzinfo is None or start_dt.utcoffset() is None:
        return start_dt.replace(tzinfo=timezone.utc)  # naive => interpretato come UTC
    return start_dt.astimezone(timezone.utc)


def iter_runs(expr, start_dt: datetime) -> Iterator[datetime]:
    """Genera all'infinito le occorrenze UTC strettamente successive a start_dt."""
    cron = expr if isinstance(expr, CronExpr) else parse(expr)
    start = _to_utc(start_dt)
    # Primo minuto candidato: il minuto intero successivo a start.
    try:
        first = start.replace(second=0, microsecond=0) + timedelta(minutes=1)
    except OverflowError:
        return  # start_dt è già l'ultimo minuto rappresentabile
    hours = sorted(cron.hours)
    minutes = sorted(cron.minutes)

    day = first.date()
    days_without_match = 0
    while True:
        if cron.matches_day(day):
            days_without_match = 0
            for h in hours:
                for m in minutes:
                    candidate = datetime.combine(day, time(h, m), tzinfo=timezone.utc)
                    if candidate >= first:
                        yield candidate
        else:
            days_without_match += 1
            if days_without_match > _MAX_SEARCH_DAYS:
                raise ValueError("l'espressione cron non produce mai occorrenze")
        try:
            day += timedelta(days=1)
        except OverflowError:
            return  # oltre datetime.max: nessuna ulteriore occorrenza


def next_runs(expr: str, start_dt: datetime, count: int = 5) -> List[datetime]:
    """Restituisce i prossimi ``count`` datetime UTC successivi a ``start_dt``.

    ``start_dt`` naive è interpretato come UTC; se aware viene convertito in UTC.
    Solleva ValueError per espressioni non valide o ``count`` negativo.
    """
    cron = parse(expr)
    if isinstance(count, bool) or not isinstance(count, int):
        raise TypeError("count deve essere un intero")
    if count < 0:
        raise ValueError("count non può essere negativo")
    result: List[datetime] = []
    if count == 0:
        return result
    for run in iter_runs(cron, start_dt):
        result.append(run)
        if len(result) == count:
            break
    return result
