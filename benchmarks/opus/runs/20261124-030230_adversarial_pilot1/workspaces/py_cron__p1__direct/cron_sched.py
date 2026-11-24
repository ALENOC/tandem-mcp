"""Parser e iteratore per espressioni cron a 5 campi.

Campi: minuto, ora, giorno_mese, mese, giorno_settimana.
Sintassi supportata per ogni campo: ``*``, numeri, intervalli ``a-b``,
liste ``a,b,c``, step ``*/n`` e ``a-b/n`` (anche combinati in lista).

Giorno della settimana: 0-6 con 0 = domenica; 7 è accettato come alias di
domenica. Come in Vixie cron, se sia giorno_mese sia giorno_settimana sono
ristretti (non iniziano con ``*``) basta che uno dei due corrisponda.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

__all__ = ["CronExpr", "parse", "iter_runs", "next_runs"]

# (nome, minimo, massimo)
_FIELDS = (
    ("minute", 0, 59),
    ("hour", 0, 23),
    ("day_of_month", 1, 31),
    ("month", 1, 12),
    ("day_of_week", 0, 7),
)

# Limite di sicurezza: un'espressione valida ma impossibile (es. "0 0 31 2 *")
# non deve far girare l'iteratore all'infinito. 400 anni sono il ciclo
# completo del calendario gregoriano: se nessuna occorrenza cade in questo
# periodo, non ne cadrà mai nessuna.
_MAX_YEARS = 400


def _parse_int(text: str, field: str) -> int:
    if not text.isdigit():  # rifiuta segni, spazi, stringhe vuote
        raise ValueError(f"valore non numerico {text!r} nel campo {field}")
    return int(text)


def _parse_field(text: str, name: str, lo: int, hi: int) -> frozenset[int]:
    if not text:
        raise ValueError(f"campo {name} vuoto")
    values: set[int] = set()
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
                    f"intervallo invertito {base!r} nel campo {name}"
                )
        else:
            if step != 1 or "/" in part:
                # "5/10" non è nella sintassi richiesta
                raise ValueError(
                    f"step ammesso solo dopo '*' o 'a-b' nel campo {name}"
                )
            start = end = _parse_int(base, name)

        if start < lo or end > hi:
            raise ValueError(
                f"valore fuori intervallo {lo}-{hi} in {part!r} (campo {name})"
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

    def _day_matches(self, dt: datetime) -> bool:
        dom_ok = dt.day in self.days_of_month
        dow_ok = (dt.isoweekday() % 7) in self.days_of_week
        if self.dom_restricted and self.dow_restricted:
            return dom_ok or dow_ok
        return dom_ok and dow_ok

    def matches(self, dt: datetime) -> bool:
        return (
            dt.minute in self.minutes
            and dt.hour in self.hours
            and dt.month in self.months
            and self._day_matches(dt)
        )


def parse(expr: str) -> CronExpr:
    """Analizza un'espressione cron a 5 campi; ValueError se non valida."""
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
    dow = frozenset(d % 7 for d in sets[4])  # 7 -> 0 (domenica)
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
        return dt.replace(tzinfo=timezone.utc)  # naive = UTC
    return dt.astimezone(timezone.utc)


def iter_runs(expr: str | CronExpr, start_dt: datetime):
    """Genera i datetime UTC (aware) strettamente successivi a start_dt."""
    cron = parse(expr) if isinstance(expr, str) else expr
    start = _to_utc(start_dt)
    try:
        # primo minuto intero strettamente successivo a start
        dt = start.replace(second=0, microsecond=0) + timedelta(minutes=1)
    except OverflowError:
        return
    if start.year + _MAX_YEARS <= 9999:
        limit = start.replace(year=start.year + _MAX_YEARS)
    else:
        limit = datetime.max.replace(tzinfo=timezone.utc)
    hours = sorted(cron.hours)
    minutes = sorted(cron.minutes)
    try:
        yield from _scan(cron, dt, limit, hours, minutes)
    except OverflowError:  # oltre datetime.max: nessuna altra occorrenza
        return


def _scan(cron: CronExpr, dt: datetime, limit: datetime, hours, minutes):
    while dt < limit:
        if dt.month not in cron.months:
            # salta al primo giorno del mese successivo
            y, m = (dt.year + 1, 1) if dt.month == 12 else (dt.year, dt.month + 1)
            dt = dt.replace(year=y, month=m, day=1, hour=0, minute=0)
            continue
        if not cron._day_matches(dt):
            dt = (dt + timedelta(days=1)).replace(hour=0, minute=0)
            continue
        next_h = next((h for h in hours if h >= dt.hour), None)
        if next_h is None:
            dt = (dt + timedelta(days=1)).replace(hour=0, minute=0)
            continue
        if next_h != dt.hour:
            dt = dt.replace(hour=next_h, minute=0)
        next_m = next((m for m in minutes if m >= dt.minute), None)
        if next_m is None:
            dt = dt.replace(minute=0) + timedelta(hours=1)
            continue
        dt = dt.replace(minute=next_m)
        yield dt
        dt += timedelta(minutes=1)


def next_runs(expr: str, start_dt: datetime, count: int = 5) -> list[datetime]:
    """Restituisce i prossimi ``count`` datetime UTC successivi a start_dt.

    start_dt naive è interpretato come UTC; se aware viene convertito in UTC.
    Solleva ValueError per espressioni non valide, count non valido o
    espressioni che non producono mai (o abbastanza) occorrenze.
    """
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ValueError("count deve essere un intero >= 0")
    cron = parse(expr)
    if count == 0:
        _to_utc(start_dt)
        return []
    out: list[datetime] = []
    for dt in iter_runs(cron, start_dt):
        out.append(dt)
        if len(out) == count:
            return out
    raise ValueError(f"l'espressione {expr!r} non produce {count} occorrenze")
