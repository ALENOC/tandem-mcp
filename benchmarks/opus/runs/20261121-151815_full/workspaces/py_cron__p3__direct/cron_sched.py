"""Parser e iteratore per espressioni cron a 5 campi.

Campi: minuto ora giorno_mese mese giorno_settimana

Sintassi supportata per ogni campo:
    *        tutti i valori
    n        singolo numero
    a-b      intervallo inclusivo
    a,b,c    lista (ogni elemento può essere uno qualsiasi degli altri forme)
    */n      step sull'intero intervallo
    a-b/n    step su un intervallo

Giorno della settimana: 0-7, dove sia 0 sia 7 indicano domenica.
Come nel cron classico, se sia giorno_mese sia giorno_settimana sono
ristretti (diversi da '*'), un giorno corrisponde se soddisfa almeno uno dei due.
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

# Limite di ricerca: 400 anni coprono l'intero ciclo del calendario gregoriano,
# quindi se non c'è una corrispondenza entro questo orizzonte non ci sarà mai.
_MAX_YEARS = 400


def _parse_int(text: str, name: str) -> int:
    if not text or not text.isdigit():
        raise ValueError(f"valore non numerico {text!r} nel campo {name}")
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
            if "/" in step_txt:
                raise ValueError(f"step multiplo non valido nel campo {name}")
        else:
            base, step = part, 1

        if base == "*":
            start, end = lo, hi
        elif "-" in base:
            a, _, b = base.partition("-")
            start, end = _parse_int(a, name), _parse_int(b, name)
            if start > end:
                raise ValueError(
                    f"intervallo invertito {base!r} nel campo {name}"
                )
        else:
            if step != 1 or "/" in part:
                # "n/m" non è tra le forme supportate
                raise ValueError(
                    f"step ammesso solo con '*' o intervallo nel campo {name}"
                )
            start = end = _parse_int(base, name)

        if start < lo or end > hi:
            raise ValueError(
                f"valore fuori intervallo [{lo}-{hi}] in {part!r} nel campo {name}"
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
    dom_any: bool
    dow_any: bool

    def day_matches(self, year: int, month: int, day: int) -> bool:
        # datetime.weekday(): lunedì=0 ... domenica=6 -> convertiamo a cron
        cron_dow = (calendar.weekday(year, month, day) + 1) % 7
        dom_ok = day in self.days
        dow_ok = cron_dow in self.weekdays
        if self.dom_any and self.dow_any:
            return True
        if self.dom_any:
            return dow_ok
        if self.dow_any:
            return dom_ok
        return dom_ok or dow_ok


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
        raise TypeError("start_dt deve essere un datetime")
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def iter_runs(expr: str | CronExpr, start_dt: datetime) -> Iterator[datetime]:
    """Itera (senza fine) sugli istanti UTC strettamente successivi a start_dt."""
    cron = expr if isinstance(expr, CronExpr) else parse(expr)
    start = _to_utc(start_dt).replace(second=0, microsecond=0) + timedelta(
        minutes=1
    )
    # ora/minuto ordinati una volta sola
    hours = sorted(cron.hours)
    minutes = sorted(cron.minutes)

    year, month = start.year, start.month
    first = True
    last_match_year = None
    while True:
        if last_match_year is None and year - start.year > _MAX_YEARS:
            raise ValueError("l'espressione cron non produce mai esecuzioni")
        if last_match_year is not None and year - last_match_year > _MAX_YEARS:
            return
        if month in cron.months:
            ndays = calendar.monthrange(year, month)[1]
            first_day = start.day if first else 1
            for day in range(first_day, ndays + 1):
                if not cron.day_matches(year, month, day):
                    continue
                same_day = first and day == start.day
                for h in hours:
                    if same_day and h < start.hour:
                        continue
                    for m in minutes:
                        if same_day and h == start.hour and m < start.minute:
                            continue
                        last_match_year = year
                        yield datetime(year, month, day, h, m, tzinfo=timezone.utc)
        first = False
        month += 1
        if month > 12:
            month = 1
            year += 1
        if year > 9999:
            return


def next_runs(expr: str, start_dt: datetime, count: int = 5) -> List[datetime]:
    """Restituisce i prossimi `count` datetime UTC strettamente successivi a start_dt.

    Un start_dt naive viene interpretato come UTC; uno aware viene convertito in UTC.
    Solleva ValueError se l'espressione non è valida o non produce mai esecuzioni.
    """
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        raise ValueError("count deve essere un intero >= 0")
    cron = parse(expr)
    _to_utc(start_dt)  # valida il tipo subito
    result: List[datetime] = []
    if count == 0:
        return result
    for dt in iter_runs(cron, start_dt):
        result.append(dt)
        if len(result) >= count:
            break
    return result
