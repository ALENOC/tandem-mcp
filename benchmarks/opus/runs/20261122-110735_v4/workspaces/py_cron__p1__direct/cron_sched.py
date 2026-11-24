"""Parser e iteratore per espressioni cron a 5 campi.

Campi: minuto, ora, giorno_mese, mese, giorno_settimana.
Sintassi supportata per ogni campo: ``*``, numeri, intervalli ``a-b``,
liste ``a,b,c``, step ``*/n`` e ``a-b/n`` (combinabili nelle liste).

Semantica (come cron classico):
- giorno_settimana: 0-7, dove 0 e 7 indicano entrambi la domenica.
- Se sia giorno_mese sia giorno_settimana sono ristretti (non ``*``), un giorno
  corrisponde se soddisfa ALMENO UNO dei due (OR). Altrimenti vale l'AND.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Iterator, List, NamedTuple, Optional, Set

__all__ = ["CronExpr", "parse", "iter_runs", "next_runs"]

# (nome, minimo, massimo)
_FIELDS = (
    ("minuto", 0, 59),
    ("ora", 0, 23),
    ("giorno_mese", 1, 31),
    ("mese", 1, 12),
    ("giorno_settimana", 0, 7),
)

# Limite di ricerca: qualsiasi espressione soddisfacibile trova un'occorrenza
# entro 28 anni (ciclo del calendario gregoriano per 29 febbraio + weekday);
# 400 anni coprono l'intero ciclo gregoriano con ampio margine.
_MAX_SEARCH_DAYS = 366 * 400


class CronExpr(NamedTuple):
    minutes: frozenset
    hours: frozenset
    days: frozenset
    months: frozenset
    weekdays: frozenset  # 0=domenica ... 6=sabato
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


def _parse_int(text: str, name: str) -> int:
    if not text or not text.isdigit():
        raise ValueError(f"valore non valido nel campo {name}: {text!r}")
    return int(text)


def _parse_field(text: str, name: str, lo: int, hi: int) -> Set[int]:
    if not isinstance(text, str) or text == "":
        raise ValueError(f"campo {name} vuoto")
    values: Set[int] = set()
    for part in text.split(","):
        if part == "":
            raise ValueError(f"elemento vuoto nella lista del campo {name}")
        step = 1
        if "/" in part:
            base, _, step_text = part.partition("/")
            step = _parse_int(step_text, name)
            if step <= 0:
                raise ValueError(f"step non valido nel campo {name}: {step}")
        else:
            base = part

        if base == "*":
            start, end = lo, hi
        elif "-" in base:
            a_text, _, b_text = base.partition("-")
            start = _parse_int(a_text, name)
            end = _parse_int(b_text, name)
            if start > end:
                raise ValueError(
                    f"intervallo invertito nel campo {name}: {start}-{end}"
                )
        else:
            if "/" in part:
                # "a/n" non fa parte della sintassi richiesta
                raise ValueError(
                    f"step ammesso solo su '*' o 'a-b' nel campo {name}: {part!r}"
                )
            start = end = _parse_int(base, name)

        if start < lo or end > hi:
            raise ValueError(
                f"valore fuori intervallo [{lo}-{hi}] nel campo {name}: {part!r}"
            )
        values.update(range(start, end + 1, step))
    return values


def parse(expr: str) -> CronExpr:
    """Analizza un'espressione cron a 5 campi. Solleva ValueError se non valida."""
    if not isinstance(expr, str):
        raise ValueError("l'espressione cron deve essere una stringa")
    parts = expr.split()
    if len(parts) != 5:
        raise ValueError(
            f"l'espressione cron deve avere 5 campi, trovati {len(parts)}: {expr!r}"
        )
    sets = [
        _parse_field(p, name, lo, hi) for p, (name, lo, hi) in zip(parts, _FIELDS)
    ]
    weekdays = {d % 7 for d in sets[4]}  # 7 -> 0 (domenica)
    cron = CronExpr(
        minutes=frozenset(sets[0]),
        hours=frozenset(sets[1]),
        days=frozenset(sets[2]),
        months=frozenset(sets[3]),
        weekdays=frozenset(weekdays),
        dom_restricted=not parts[2].startswith("*"),
        dow_restricted=not parts[4].startswith("*"),
    )
    if not _satisfiable(cron):
        raise ValueError(f"l'espressione cron non corrisponde mai ad alcuna data: {expr!r}")
    return cron


_MAX_DAYS_IN_MONTH = {1: 31, 2: 29, 3: 31, 4: 30, 5: 31, 6: 30,
                      7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31}


def _satisfiable(cron: CronExpr) -> bool:
    # Con OR (entrambi ristretti) basta un qualsiasi weekday: sempre possibile.
    # Altrimenti serve almeno un giorno del mese esistente in un mese ammesso
    # (i vincoli di weekday da soli sono sempre soddisfacibili nel lungo periodo).
    if cron.dom_restricted and cron.dow_restricted:
        return True
    return any(
        d <= _MAX_DAYS_IN_MONTH[m] for m in cron.months for d in cron.days
    )


def _to_utc(dt: datetime) -> datetime:
    if not isinstance(dt, datetime):
        raise TypeError("start_dt deve essere un datetime")
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        return dt.replace(tzinfo=timezone.utc)  # naive: interpretato come UTC
    return dt.astimezone(timezone.utc)


def iter_runs(expr, start_dt: datetime) -> Iterator[datetime]:
    """Genera all'infinito i datetime UTC (aware) strettamente successivi a start_dt."""
    cron = expr if isinstance(expr, CronExpr) else parse(expr)
    start = _to_utc(start_dt)
    # Primo istante candidato: minuto intero successivo a start.
    first = start.replace(second=0, microsecond=0) + timedelta(minutes=1)

    hours = sorted(cron.hours)
    minutes = sorted(cron.minutes)
    day = first.date()
    first_day = day
    for _ in range(_MAX_SEARCH_DAYS):
        if cron.matches_day(day):
            for h in hours:
                if day == first_day and h < first.hour:
                    continue
                for m in minutes:
                    if day == first_day and h == first.hour and m < first.minute:
                        continue
                    yield datetime.combine(day, time(h, m), tzinfo=timezone.utc)
        try:
            day += timedelta(days=1)
        except OverflowError:
            return
    return


def next_runs(expr: str, start_dt: datetime, count: int = 5) -> List[datetime]:
    """Restituisce i prossimi ``count`` datetime UTC successivi a ``start_dt``.

    I datetime naive sono interpretati come UTC; quelli aware sono convertiti.
    Solleva ValueError se l'espressione non è valida o ``count`` è negativo.
    """
    cron = parse(expr)
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ValueError(f"count deve essere un intero >= 0, ricevuto {count!r}")
    result: List[datetime] = []
    if count == 0:
        return result
    for dt in iter_runs(cron, start_dt):
        result.append(dt)
        if len(result) >= count:
            break
    return result
