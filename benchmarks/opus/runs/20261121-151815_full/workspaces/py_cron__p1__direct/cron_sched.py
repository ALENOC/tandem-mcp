"""Parser e iteratore per espressioni cron a 5 campi.

Campi: minuto, ora, giorno_mese, mese, giorno_settimana.
Sintassi supportata per ogni campo: ``*``, numeri, intervalli ``a-b``,
liste ``a,b,c``, step ``*/n`` e ``a-b/n`` (anche combinati in lista).

Semantica (come Vixie cron):
- giorno_settimana: 0-7, dove 0 e 7 indicano entrambi la domenica.
- se sia giorno_mese sia giorno_settimana sono ristretti (non ``*``),
  una data corrisponde se soddisfa almeno uno dei due (OR).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
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

# Limite di ricerca: oltre questo orizzonte l'espressione è considerata
# impossibile (es. "0 0 30 2 *"). 28 anni coprono il ciclo completo del
# calendario gregoriano rispetto a giorni della settimana e anni bisestili
# nella pratica.
_MAX_SEARCH_DAYS = 366 * 28


def _parse_int(token: str, field: str, lo: int, hi: int) -> int:
    if not token.isdigit():
        raise ValueError(f"valore non numerico {token!r} nel campo {field}")
    value = int(token)
    if not lo <= value <= hi:
        raise ValueError(
            f"valore {value} fuori intervallo [{lo}-{hi}] nel campo {field}"
        )
    return value


def _parse_field(text: str, field: str, lo: int, hi: int) -> FrozenSet[int]:
    if text == "":
        raise ValueError(f"campo {field} vuoto")
    values = set()
    for part in text.split(","):
        if part == "":
            raise ValueError(f"elemento di lista vuoto nel campo {field}")
        if "/" in part:
            base, _, step_txt = part.partition("/")
            if "/" in step_txt:
                raise ValueError(f"step multiplo in {part!r} nel campo {field}")
            if not step_txt.isdigit() or int(step_txt) == 0:
                raise ValueError(f"step non valido {step_txt!r} nel campo {field}")
            step = int(step_txt)
            if base == "*":
                start, end = lo, hi
            elif "-" in base:
                start, end = _parse_range(base, field, lo, hi)
            else:
                raise ValueError(
                    f"step ammesso solo dopo '*' o un intervallo: {part!r} "
                    f"nel campo {field}"
                )
        else:
            step = 1
            if part == "*":
                start, end = lo, hi
            elif "-" in part:
                start, end = _parse_range(part, field, lo, hi)
            else:
                start = end = _parse_int(part, field, lo, hi)
        values.update(range(start, end + 1, step))
    return frozenset(values)


def _parse_range(text: str, field: str, lo: int, hi: int):
    a, sep, b = text.partition("-")
    if not sep or "-" in b:
        raise ValueError(f"intervallo non valido {text!r} nel campo {field}")
    start = _parse_int(a, field, lo, hi)
    end = _parse_int(b, field, lo, hi)
    if start > end:
        raise ValueError(f"intervallo decrescente {text!r} nel campo {field}")
    return start, end


@dataclass(frozen=True)
class CronExpr:
    minutes: FrozenSet[int]
    hours: FrozenSet[int]
    days_of_month: FrozenSet[int]
    months: FrozenSet[int]
    days_of_week: FrozenSet[int]  # 0=domenica ... 6=sabato
    dom_restricted: bool
    dow_restricted: bool

    def matches_day(self, dt: datetime) -> bool:
        if dt.month not in self.months:
            return False
        dom_ok = dt.day in self.days_of_month
        # datetime.weekday(): lunedì=0 ... domenica=6 -> cron: domenica=0
        dow_ok = (dt.weekday() + 1) % 7 in self.days_of_week
        if self.dom_restricted and self.dow_restricted:
            return dom_ok or dow_ok
        return dom_ok and dow_ok

    def matches(self, dt: datetime) -> bool:
        return (
            dt.minute in self.minutes
            and dt.hour in self.hours
            and self.matches_day(dt)
        )


def parse(expr: str) -> CronExpr:
    """Analizza un'espressione cron a 5 campi; solleva ValueError se invalida."""
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
    dow = frozenset(d % 7 for d in sets[4])
    return CronExpr(
        minutes=sets[0],
        hours=sets[1],
        days_of_month=sets[2],
        months=sets[3],
        days_of_week=dow,
        dom_restricted=not parts[2].startswith("*"),
        dow_restricted=not parts[4].startswith("*"),
    )


def _to_utc(dt: datetime) -> datetime:
    if not isinstance(dt, datetime):
        raise ValueError("start_dt deve essere un datetime")
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def iter_runs(expr, start_dt: datetime) -> Iterator[datetime]:
    """Itera all'infinito sulle esecuzioni (UTC) strettamente successive a start_dt.

    ``expr`` può essere una stringa o un CronExpr già analizzato.
    Un datetime naive è interpretato come UTC.
    """
    cron = expr if isinstance(expr, CronExpr) else parse(expr)
    current = _to_utc(start_dt).replace(second=0, microsecond=0) + timedelta(minutes=1)
    minutes = sorted(cron.minutes)
    hours = sorted(cron.hours)

    while True:
        # Avanza giorno per giorno fino a un giorno valido.
        skipped = 0
        while not cron.matches_day(current):
            current = (current + timedelta(days=1)).replace(hour=0, minute=0)
            skipped += 1
            if skipped > _MAX_SEARCH_DAYS:
                raise ValueError(
                    "l'espressione cron non produce mai esecuzioni"
                )
        found = None
        for h in hours:
            if h < current.hour:
                continue
            for m in minutes:
                if h == current.hour and m < current.minute:
                    continue
                found = current.replace(hour=h, minute=m)
                break
            if found is not None:
                break
        if found is None:
            current = (current + timedelta(days=1)).replace(hour=0, minute=0)
            continue
        yield found
        current = found + timedelta(minutes=1)


def next_runs(expr: str, start_dt: datetime, count: int = 5) -> List[datetime]:
    """Restituisce i prossimi ``count`` datetime UTC successivi a ``start_dt``."""
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ValueError("count deve essere un intero >= 0")
    cron = parse(expr)  # valida subito anche con count == 0
    result: List[datetime] = []
    if count == 0:
        return result
    for dt in iter_runs(cron, start_dt):
        result.append(dt)
        if len(result) == count:
            break
    return result
