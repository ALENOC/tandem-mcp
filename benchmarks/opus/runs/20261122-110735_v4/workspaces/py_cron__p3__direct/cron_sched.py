"""Parser e iteratore di espressioni cron a 5 campi.

Campi: minuto ora giorno_mese mese giorno_settimana

Sintassi supportata per ogni campo:
    *        tutti i valori
    n        singolo valore
    a-b      intervallo inclusivo
    a,b,c    lista (ogni elemento può essere una qualsiasi delle altre forme)
    */n      step su tutto l'intervallo
    a-b/n    step su un intervallo

Giorno della settimana: 0-7, con 0 e 7 = domenica (1 = lunedì).
Semantica classica di cron: se sia giorno_mese sia giorno_settimana sono
ristretti (non "*"), un giorno corrisponde se soddisfa almeno uno dei due.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

__all__ = ["CronExpression", "parse", "next_runs"]

# (nome, minimo, massimo)
_FIELDS = (
    ("minuto", 0, 59),
    ("ora", 0, 23),
    ("giorno_mese", 1, 31),
    ("mese", 1, 12),
    ("giorno_settimana", 0, 7),
)

# Limite di ricerca: un ciclo gregoriano completo garantisce di trovare ogni
# combinazione possibile; oltre, l'espressione non corrisponde mai.
_MAX_SEARCH_YEARS = 400


def _parse_int(token: str, name: str, lo: int, hi: int) -> int:
    if not token or not token.isdigit():
        raise ValueError(f"valore non valido {token!r} nel campo {name}")
    value = int(token)
    if not lo <= value <= hi:
        raise ValueError(
            f"valore {value} fuori intervallo [{lo}-{hi}] nel campo {name}"
        )
    return value


def _parse_field(text: str, name: str, lo: int, hi: int) -> frozenset[int]:
    if not text:
        raise ValueError(f"campo {name} vuoto")
    values: set[int] = set()
    for part in text.split(","):
        if not part:
            raise ValueError(f"elemento vuoto nella lista del campo {name}")
        step = 1
        if "/" in part:
            base, _, step_text = part.partition("/")
            if "/" in step_text:
                raise ValueError(f"step multiplo non valido {part!r} nel campo {name}")
            if not step_text.isdigit() or int(step_text) == 0:
                raise ValueError(f"step non valido {step_text!r} nel campo {name}")
            step = int(step_text)
            if base != "*" and "-" not in base:
                raise ValueError(
                    f"lo step richiede '*' o un intervallo a-b: {part!r} nel campo {name}"
                )
        else:
            base = part

        if base == "*":
            start, end = lo, hi
        elif "-" in base:
            a, _, b = base.partition("-")
            start = _parse_int(a, name, lo, hi)
            end = _parse_int(b, name, lo, hi)
            if start > end:
                raise ValueError(f"intervallo invertito {base!r} nel campo {name}")
        else:
            start = end = _parse_int(base, name, lo, hi)

        values.update(range(start, end + 1, step))
    return frozenset(values)


@dataclass(frozen=True)
class CronExpression:
    minutes: frozenset[int]
    hours: frozenset[int]
    days: frozenset[int]
    months: frozenset[int]
    weekdays: frozenset[int]  # 0 = domenica ... 6 = sabato
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

    def iter_after(self, start_dt: datetime):
        """Genera i datetime UTC (aware) strettamente successivi a start_dt."""
        current = _to_utc(start_dt).replace(second=0, microsecond=0)
        current += timedelta(minutes=1)
        minutes = sorted(self.minutes)
        hours = sorted(self.hours)
        limit_year = current.year + _MAX_SEARCH_YEARS

        day = current.date()
        first_day = True
        while True:
            if day.year > limit_year:
                return
            if day.month not in self.months:
                # Salta al primo giorno del mese successivo.
                last = calendar.monthrange(day.year, day.month)[1]
                day = day.replace(day=last) + timedelta(days=1)
                first_day = False
                continue
            if self.matches_day(day):
                for h in hours:
                    if first_day and h < current.hour:
                        continue
                    for m in minutes:
                        if first_day and h == current.hour and m < current.minute:
                            continue
                        yield datetime(
                            day.year, day.month, day.day, h, m, tzinfo=timezone.utc
                        )
            day += timedelta(days=1)
            first_day = False


def _to_utc(dt: datetime) -> datetime:
    if not isinstance(dt, datetime):
        raise TypeError("start_dt deve essere un datetime")
    if dt.tzinfo is None or dt.utcoffset() is None:
        # I datetime naive sono interpretati come UTC.
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse(expr: str) -> CronExpression:
    """Analizza un'espressione cron a 5 campi; ValueError se non valida."""
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
    weekdays = frozenset(v % 7 for v in sets[4])  # 7 -> 0 (domenica)

    # Rifiuta combinazioni giorno/mese impossibili (es. "0 0 31 4 *")
    # quando il giorno della settimana non offre alternative.
    dom_restricted = parts[2] != "*"
    dow_restricted = parts[4] != "*"
    if not dow_restricted or not dom_restricted:
        max_days = max(
            29 if m == 2 else calendar.monthrange(2001, m)[1] for m in sets[3]
        )
        if min(sets[2]) > max_days:
            raise ValueError(
                f"l'espressione {expr!r} non corrisponde mai ad alcuna data"
            )

    return CronExpression(
        minutes=sets[0],
        hours=sets[1],
        days=sets[2],
        months=sets[3],
        weekdays=weekdays,
        dom_restricted=dom_restricted,
        dow_restricted=dow_restricted,
    )


def next_runs(expr: str, start_dt: datetime, count: int = 5) -> list[datetime]:
    """Restituisce i prossimi `count` datetime UTC strettamente successivi a start_dt.

    start_dt naive è interpretato come UTC; se aware viene convertito in UTC.
    I risultati sono datetime aware con tzinfo=timezone.utc.
    Solleva ValueError per espressioni non valide o count negativo.
    """
    cron = parse(expr)
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ValueError("count deve essere un intero >= 0")
    result: list[datetime] = []
    if count == 0:
        return result
    for dt in cron.iter_after(start_dt):
        result.append(dt)
        if len(result) == count:
            break
    if not result:
        raise ValueError(f"l'espressione {expr!r} non corrisponde mai ad alcuna data")
    return result
