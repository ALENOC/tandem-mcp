"""Parser e iteratore di espressioni cron a 5 campi.

Campi: minuto, ora, giorno_mese, mese, giorno_settimana.
Sintassi supportata per ogni campo: ``*``, numeri, intervalli ``a-b``,
liste ``a,b,c``, step ``*/n`` e ``a-b/n`` (anche combinati in liste).

Giorno della settimana: 0-7, dove 0 e 7 indicano entrambi la domenica.
Come nel cron classico, se sia giorno_mese sia giorno_settimana sono
ristretti (diversi da ``*``), basta che uno dei due corrisponda.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

__all__ = ["CronExpr", "parse", "iter_runs", "next_runs"]

# (nome, minimo, massimo)
_FIELDS = (
    ("minuto", 0, 59),
    ("ora", 0, 23),
    ("giorno_mese", 1, 31),
    ("mese", 1, 12),
    ("giorno_settimana", 0, 7),
)

# Giorni massimi per mese (febbraio 29 per includere gli anni bisestili).
_MAX_DAYS = {1: 31, 2: 29, 3: 31, 4: 30, 5: 31, 6: 30,
             7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31}

# Limite di ricerca: 28 anni coprono ogni combinazione calendario/giorno.
_SEARCH_DAYS = 366 * 29


@dataclass(frozen=True)
class CronExpr:
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
        # date.weekday(): lunedì=0 ... domenica=6 -> convertito a cron (dom=0)
        dow_ok = (d.weekday() + 1) % 7 in self.weekdays
        if self.dom_restricted and self.dow_restricted:
            return dom_ok or dow_ok
        return dom_ok and dow_ok

    def matches(self, dt: datetime) -> bool:
        return (dt.minute in self.minutes and dt.hour in self.hours
                and self.matches_day(dt.date()))


def _parse_int(text: str, name: str) -> int:
    if not (text.isascii() and text.isdigit()):  # rifiuta segni, spazi, vuoti, non-ASCII
        raise ValueError(f"valore non numerico nel campo {name}: {text!r}")
    try:
        return int(text)
    except ValueError:
        raise ValueError(f"valore non numerico nel campo {name}: {text!r}") from None


def _parse_field(text: str, name: str, lo: int, hi: int) -> frozenset:
    if not text:
        raise ValueError(f"campo {name} vuoto")
    values: set[int] = set()
    for part in text.split(","):
        if not part:
            raise ValueError(f"elemento vuoto nella lista del campo {name}")
        if "/" in part:
            base, step_text = part.split("/", 1)
            step = _parse_int(step_text, name)
            if step <= 0:
                raise ValueError(f"step non valido nel campo {name}: {step}")
        else:
            base, step = part, 1
            step_text = None

        if base == "*":
            start, end = lo, hi
        elif "-" in base:
            a, b = base.split("-", 1)
            start, end = _parse_int(a, name), _parse_int(b, name)
            if start > end:
                raise ValueError(f"intervallo invertito nel campo {name}: {base}")
        else:
            if step_text is not None:
                raise ValueError(
                    f"step ammesso solo dopo '*' o un intervallo nel campo {name}: {part}")
            start = end = _parse_int(base, name)

        if start < lo or end > hi:
            raise ValueError(
                f"valore fuori range [{lo}-{hi}] nel campo {name}: {base}")
        values.update(range(start, end + 1, step))
    return frozenset(values)


def parse(expr: str) -> CronExpr:
    """Analizza un'espressione cron a 5 campi; solleva ValueError se non valida."""
    if not isinstance(expr, str):
        raise ValueError("l'espressione cron deve essere una stringa")
    parts = expr.split()
    if len(parts) != 5:
        raise ValueError(f"attesi 5 campi, trovati {len(parts)}: {expr!r}")
    sets = [_parse_field(p, name, lo, hi)
            for p, (name, lo, hi) in zip(parts, _FIELDS)]
    minutes, hours, days, months, weekdays = sets
    weekdays = frozenset(w % 7 for w in weekdays)  # 7 -> 0 (domenica)
    cron = CronExpr(
        minutes=minutes, hours=hours, days=days, months=months,
        weekdays=weekdays,
        dom_restricted=parts[2] != "*",
        dow_restricted=parts[4] != "*",
    )
    # Rileva combinazioni impossibili (es. "0 0 30 2 *"): solo se il giorno
    # della settimana non offre un'alternativa (regola OR).
    if not (cron.dom_restricted and cron.dow_restricted):
        if not any(d <= _MAX_DAYS[m] for m in months for d in days):
            raise ValueError(f"l'espressione non corrisponde mai a una data: {expr!r}")
    return cron


def _to_utc(dt: datetime) -> datetime:
    if not isinstance(dt, datetime):
        raise TypeError("start_dt deve essere un datetime")
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)  # naive = UTC
    return dt.astimezone(timezone.utc)


def iter_runs(expr, start_dt: datetime):
    """Genera all'infinito i datetime UTC strettamente successivi a start_dt."""
    cron = expr if isinstance(expr, CronExpr) else parse(expr)
    start = _to_utc(start_dt)
    # Primo minuto candidato: il minuto intero successivo a start.
    first = start.replace(second=0, microsecond=0) + timedelta(minutes=1)
    hours = sorted(cron.hours)
    minutes = sorted(cron.minutes)

    day = first.date()
    misses = 0
    first_day = True
    while True:
        if cron.matches_day(day):
            misses = 0
            for h in hours:
                if first_day and h < first.hour:
                    continue
                for m in minutes:
                    if first_day and h == first.hour and m < first.minute:
                        continue
                    yield datetime(day.year, day.month, day.day, h, m,
                                   tzinfo=timezone.utc)
        else:
            misses += 1
            if misses > _SEARCH_DAYS:
                raise ValueError("nessuna esecuzione trovata per l'espressione")
        first_day = False
        if day == date.max:
            return
        day += timedelta(days=1)


def next_runs(expr, start_dt: datetime, count: int = 5) -> list[datetime]:
    """Restituisce i prossimi ``count`` datetime UTC successivi a ``start_dt``.

    ``start_dt`` naive è interpretato come UTC; se aware viene convertito.
    Solleva ValueError per espressioni non valide o ``count`` negativo.
    """
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        raise ValueError("count deve essere un intero >= 0")
    cron = expr if isinstance(expr, CronExpr) else parse(expr)
    result: list[datetime] = []
    if count == 0:
        return result
    for run in iter_runs(cron, start_dt):
        result.append(run)
        if len(result) >= count:
            break
    return result
