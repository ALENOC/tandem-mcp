"""Parser e iteratore di espressioni cron a 5 campi.

Campi: minuto ora giorno_mese mese giorno_settimana

Sintassi supportata per ogni campo:
    *        tutti i valori
    n        valore singolo
    a-b      intervallo inclusivo
    a,b,c    lista (ogni elemento può essere uno qualsiasi degli altri form)
    */n      step su tutto l'intervallo
    a-b/n    step su un intervallo

Giorno della settimana: 0-7, dove 0 e 7 indicano entrambi la domenica.
Come in Vixie cron, se sia giorno_mese sia giorno_settimana sono ristretti
(cioè non iniziano con '*'), un giorno corrisponde se soddisfa UNO dei due.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

__all__ = ["CronExpr", "parse", "next_runs"]

# (nome, minimo, massimo)
_FIELDS = (
    ("minute", 0, 59),
    ("hour", 0, 23),
    ("day_of_month", 1, 31),
    ("month", 1, 12),
    ("day_of_week", 0, 7),
)

# Limite di ricerca: sufficiente per qualsiasi espressione soddisfacibile
# (es. 29 febbraio, anche attraverso anni secolari non bisestili).
_MAX_SEARCH_DAYS = 366 * 12


def _parse_int(text: str, field: str) -> int:
    if not text.isdigit():
        raise ValueError(f"valore non numerico {text!r} nel campo {field}")
    return int(text)


def _parse_field(text: str, field: str, lo: int, hi: int) -> frozenset[int]:
    if not text:
        raise ValueError(f"campo {field} vuoto")
    values: set[int] = set()
    for part in text.split(","):
        if not part:
            raise ValueError(f"elemento vuoto nella lista del campo {field}")
        if "/" in part:
            base, _, step_text = part.partition("/")
            step = _parse_int(step_text, field)
            if step <= 0:
                raise ValueError(f"step deve essere > 0 nel campo {field}")
            if base != "*" and "-" not in base:
                raise ValueError(
                    f"step ammesso solo dopo '*' o un intervallo nel campo {field}: {part!r}"
                )
        else:
            base, step = part, 1

        if base == "*":
            start, end = lo, hi
        elif "-" in base:
            a, _, b = base.partition("-")
            start, end = _parse_int(a, field), _parse_int(b, field)
            if start > end:
                raise ValueError(f"intervallo invertito {base!r} nel campo {field}")
        else:
            start = end = _parse_int(base, field)

        if start < lo or end > hi:
            raise ValueError(
                f"valore fuori range {base!r} nel campo {field} (ammessi {lo}-{hi})"
            )
        values.update(range(start, end + 1, step))
    return frozenset(values)


@dataclass(frozen=True)
class CronExpr:
    minutes: frozenset[int]
    hours: frozenset[int]
    days_of_month: frozenset[int]
    months: frozenset[int]
    days_of_week: frozenset[int]  # 0 = domenica ... 6 = sabato
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

    def iter_after(self, start_dt: datetime):
        """Genera indefinitamente i datetime UTC (aware) strettamente successivi a start_dt."""
        current = _to_utc(start_dt).replace(second=0, microsecond=0) + timedelta(minutes=1)
        hours = sorted(self.hours)
        minutes = sorted(self.minutes)
        day = current.date()
        first_day = True
        misses = 0
        while True:
            if self.matches_day(day):
                misses = 0
                for h in hours:
                    if first_day and h < current.hour:
                        continue
                    for m in minutes:
                        if first_day and h == current.hour and m < current.minute:
                            continue
                        yield datetime.combine(day, time(h, m), tzinfo=timezone.utc)
            else:
                misses += 1
                if misses > _MAX_SEARCH_DAYS:
                    raise ValueError("l'espressione cron non produce mai alcuna occorrenza")
            first_day = False
            try:
                day += timedelta(days=1)
            except OverflowError:
                return


def _to_utc(dt: datetime) -> datetime:
    if not isinstance(dt, datetime):
        raise TypeError("start_dt deve essere un datetime")
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _is_satisfiable(dom: frozenset[int], months: frozenset[int]) -> bool:
    # 2000 è bisestile: febbraio ha 29 giorni (massimo possibile).
    return any(min(dom) <= calendar.monthrange(2000, m)[1] for m in months)


def parse(expr: str) -> CronExpr:
    """Analizza un'espressione cron a 5 campi. Solleva ValueError se non valida."""
    if not isinstance(expr, str):
        raise ValueError("l'espressione cron deve essere una stringa")
    parts = expr.split()
    if len(parts) != 5:
        raise ValueError(f"attesi 5 campi, trovati {len(parts)}: {expr!r}")
    sets = [
        _parse_field(text, name, lo, hi)
        for text, (name, lo, hi) in zip(parts, _FIELDS)
    ]
    minutes, hours, dom, months, dow = sets
    dow = frozenset(d % 7 for d in dow)
    dom_restricted = not parts[2].startswith("*")
    dow_restricted = not parts[4].startswith("*")
    if dom_restricted and not dow_restricted and not _is_satisfiable(dom, months):
        raise ValueError(f"l'espressione non corrisponde mai ad alcuna data: {expr!r}")
    return CronExpr(minutes, hours, dom, months, dow, dom_restricted, dow_restricted)


def next_runs(expr: str, start_dt: datetime, count: int = 5) -> list[datetime]:
    """Restituisce i prossimi `count` datetime UTC strettamente successivi a start_dt.

    start_dt naive è interpretato come UTC; se aware viene convertito in UTC.
    I risultati sono datetime aware con tzinfo=timezone.utc.
    """
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        raise ValueError("count deve essere un intero >= 0")
    cron = parse(expr)
    results: list[datetime] = []
    if count == 0:
        return results
    for dt in cron.iter_after(start_dt):
        results.append(dt)
        if len(results) >= count:
            break
    return results
