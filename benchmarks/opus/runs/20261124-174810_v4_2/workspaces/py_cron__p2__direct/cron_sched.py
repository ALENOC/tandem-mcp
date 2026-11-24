"""Parser e iteratore di espressioni cron a 5 campi.

Campi: minuto, ora, giorno_mese, mese, giorno_settimana.
Sintassi supportata per ogni campo: ``*``, numeri, intervalli ``a-b``,
liste ``a,b,c``, step ``*/n`` e ``a-b/n`` (anche combinati in liste).

Semantica giorno_mese / giorno_settimana come in Vixie cron: se entrambi
sono ristretti (nessuno dei due è ``*``) basta che uno dei due corrisponda.
Il giorno della settimana va da 0 (domenica) a 6; 7 è accettato come alias
della domenica.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import FrozenSet, List

__all__ = ["CronExpr", "parse", "next_runs"]

# (nome, minimo, massimo)
_FIELDS = (
    ("minute", 0, 59),
    ("hour", 0, 23),
    ("day_of_month", 1, 31),
    ("month", 1, 12),
    ("day_of_week", 0, 7),
)

# Limite di ricerca: 400 anni coprono l'intero ciclo del calendario gregoriano,
# quindi se nessuna data corrisponde entro questo intervallo non ne esiste alcuna.
_MAX_SEARCH_DAYS = 366 * 400


@dataclass(frozen=True)
class CronExpr:
    minutes: FrozenSet[int]
    hours: FrozenSet[int]
    days_of_month: FrozenSet[int]
    months: FrozenSet[int]
    days_of_week: FrozenSet[int]  # 0 = domenica ... 6 = sabato
    dom_any: bool
    dow_any: bool

    def matches_day(self, year: int, month: int, day: int) -> bool:
        if month not in self.months:
            return False
        # Python: lunedì=0 ... domenica=6  ->  cron: domenica=0 ... sabato=6
        dow = (calendar.weekday(year, month, day) + 1) % 7
        dom_ok = day in self.days_of_month
        dow_ok = dow in self.days_of_week
        if self.dom_any and self.dow_any:
            return True
        if self.dom_any:
            return dow_ok
        if self.dow_any:
            return dom_ok
        return dom_ok or dow_ok


def _parse_int(text: str, name: str, lo: int, hi: int) -> int:
    if not text.isdigit():  # rifiuta segni, spazi, stringhe vuote
        raise ValueError(f"valore non numerico {text!r} nel campo {name}")
    value = int(text)
    if not lo <= value <= hi:
        raise ValueError(f"valore {value} fuori intervallo [{lo}-{hi}] nel campo {name}")
    return value


def _parse_field(text: str, name: str, lo: int, hi: int) -> FrozenSet[int]:
    if not text:
        raise ValueError(f"campo {name} vuoto")
    values = set()
    for part in text.split(","):
        if not part:
            raise ValueError(f"elemento vuoto nella lista del campo {name}")
        if part.count("/") > 1:
            raise ValueError(f"step multipli in {part!r} nel campo {name}")
        base, sep, step_txt = part.partition("/")
        step = 1
        if sep:
            if not step_txt.isdigit() or int(step_txt) == 0:
                raise ValueError(f"step non valido {step_txt!r} nel campo {name}")
            step = int(step_txt)

        if base == "*":
            start, end = lo, hi
        elif "-" in base:
            if base.count("-") != 1:
                raise ValueError(f"intervallo non valido {base!r} nel campo {name}")
            a, b = base.split("-")
            start = _parse_int(a, name, lo, hi)
            end = _parse_int(b, name, lo, hi)
            if start > end:
                raise ValueError(f"intervallo decrescente {base!r} nel campo {name}")
        else:
            if sep:
                # "a/n" non è tra le forme richieste: accettiamo solo */n e a-b/n
                raise ValueError(f"step su valore singolo {part!r} nel campo {name}")
            start = end = _parse_int(base, name, lo, hi)

        values.update(range(start, end + 1, step))
    return frozenset(values)


def parse(expr: str) -> CronExpr:
    """Analizza un'espressione cron a 5 campi. Solleva ValueError se non valida."""
    if not isinstance(expr, str):
        raise ValueError("l'espressione cron deve essere una stringa")
    parts = expr.split()
    if len(parts) != 5:
        raise ValueError(f"attesi 5 campi, trovati {len(parts)}")

    sets = [_parse_field(p, n, lo, hi) for p, (n, lo, hi) in zip(parts, _FIELDS)]
    minutes, hours, dom, months, dow = sets
    dow = frozenset(d % 7 for d in dow)  # 7 -> 0 (domenica)

    cron = CronExpr(
        minutes=minutes,
        hours=hours,
        days_of_month=dom,
        months=months,
        days_of_week=dow,
        dom_any=parts[2] == "*",
        dow_any=parts[4] == "*",
    )

    # Rileva subito combinazioni impossibili (es. "0 0 30 2 *"): se conta solo
    # il giorno del mese, almeno un mese selezionato deve poterlo contenere.
    if cron.dow_any and not cron.dom_any:
        if not any(d <= _max_days(m) for m in months for d in dom):
            raise ValueError(f"nessuna data possibile per {expr!r}")
    return cron


def _max_days(month: int) -> int:
    return calendar.monthrange(2000, month)[1]  # 2000 è bisestile: febbraio = 29


def _to_utc(dt: datetime) -> datetime:
    if not isinstance(dt, datetime):
        raise TypeError("start_dt deve essere un datetime")
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)  # naive -> interpretato come UTC
    return dt.astimezone(timezone.utc)


def next_runs(expr: str, start_dt: datetime, count: int = 5) -> List[datetime]:
    """Restituisce i prossimi ``count`` datetime UTC strettamente successivi a start_dt.

    start_dt naive viene interpretato come UTC; se aware viene convertito in UTC.
    Solleva ValueError per espressioni non valide o count negativo.
    """
    cron = parse(expr)
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ValueError("count deve essere un intero >= 0")

    start = _to_utc(start_dt)
    # Primo istante candidato: il minuto successivo a start_dt (troncato al minuto).
    current = start.replace(second=0, microsecond=0) + timedelta(minutes=1)

    minutes = sorted(cron.minutes)
    hours = sorted(cron.hours)
    results: List[datetime] = []
    day = current.date()
    first_day = True

    for _ in range(_MAX_SEARCH_DAYS):
        if len(results) >= count:
            break
        if cron.matches_day(day.year, day.month, day.day):
            for h in hours:
                if first_day and h < current.hour:
                    continue
                for m in minutes:
                    if first_day and h == current.hour and m < current.minute:
                        continue
                    results.append(
                        datetime(day.year, day.month, day.day, h, m, tzinfo=timezone.utc)
                    )
                    if len(results) >= count:
                        return results
        first_day = False
        try:
            day += timedelta(days=1)
        except OverflowError:
            break

    if len(results) < count:
        raise ValueError(f"nessuna esecuzione trovata per {expr!r}")
    return results
