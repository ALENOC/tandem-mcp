"""Parser e iteratore per espressioni cron a 5 campi.

Campi: minuto, ora, giorno_mese, mese, giorno_settimana.
Sintassi supportata per ogni campo: ``*``, numeri, intervalli ``a-b``,
liste ``a,b,c``, step ``*/n`` e ``a-b/n`` (anche combinati in liste).

Semantica (come Vixie cron):
- giorno_settimana: 0-7, dove sia 0 sia 7 indicano domenica.
- Se sia giorno_mese sia giorno_settimana sono ristretti (non ``*``),
  un giorno corrisponde se soddisfa ALMENO UNO dei due.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

__all__ = ["CronExpr", "parse", "next_runs", "iter_runs"]

# (nome, minimo, massimo)
_FIELDS = (
    ("minute", 0, 59),
    ("hour", 0, 23),
    ("day_of_month", 1, 31),
    ("month", 1, 12),
    ("day_of_week", 0, 7),
)

# Limite di ricerca: oltre questo orizzonte l'espressione non scatta mai
# (es. "0 0 30 2 *"). 28 anni coprono l'intero ciclo del calendario gregoriano
# per quanto riguarda combinazioni giorno/settimana, bisestili inclusi.
_MAX_SEARCH_DAYS = 366 * 28 + 7


@dataclass(frozen=True)
class CronExpr:
    minutes: frozenset[int]
    hours: frozenset[int]
    days_of_month: frozenset[int]
    months: frozenset[int]
    days_of_week: frozenset[int]  # 0=domenica ... 6=sabato
    dom_restricted: bool
    dow_restricted: bool

    def matches_day(self, d: datetime) -> bool:
        if d.month not in self.months:
            return False
        dom_ok = d.day in self.days_of_month
        # Python: lunedì=0 ... domenica=6  ->  cron: domenica=0 ... sabato=6
        dow_ok = (d.weekday() + 1) % 7 in self.days_of_week
        if self.dom_restricted and self.dow_restricted:
            return dom_ok or dow_ok
        return dom_ok and dow_ok

    def matches(self, d: datetime) -> bool:
        return (
            d.minute in self.minutes
            and d.hour in self.hours
            and self.matches_day(d)
        )


def _parse_int(text: str, name: str) -> int:
    if not text or not (text.isascii() and text.isdigit()):  # rifiuta segni, spazi, vuoti, non-ASCII
        raise ValueError(f"valore non valido {text!r} nel campo {name}")
    try:
        return int(text)
    except ValueError:
        raise ValueError(f"valore non valido {text!r} nel campo {name}") from None


def _parse_field(text: str, name: str, lo: int, hi: int) -> tuple[frozenset[int], bool]:
    """Restituisce (insieme di valori, ristretto?)."""
    if text == "":
        raise ValueError(f"campo {name} vuoto")
    values: set[int] = set()
    restricted = True
    for part in text.split(","):
        if part == "":
            raise ValueError(f"elemento vuoto nella lista del campo {name}: {text!r}")
        if part.count("/") > 1:
            raise ValueError(f"step multipli non ammessi nel campo {name}: {part!r}")
        base, sep, step_txt = part.partition("/")
        step = 1
        if sep:
            step = _parse_int(step_txt, name)
            if step == 0:
                raise ValueError(f"step zero non ammesso nel campo {name}: {part!r}")

        if base == "*":
            start, end = lo, hi
            if not sep and text == "*":
                restricted = False
        elif "-" in base:
            a_txt, _, b_txt = base.partition("-")
            start, end = _parse_int(a_txt, name), _parse_int(b_txt, name)
            if start > end:
                raise ValueError(f"intervallo invertito nel campo {name}: {part!r}")
        else:
            start = _parse_int(base, name)
            if sep:
                # "a/n" non fa parte della sintassi richiesta: è ambiguo, lo rifiutiamo.
                raise ValueError(
                    f"step ammesso solo dopo '*' o un intervallo nel campo {name}: {part!r}"
                )
            end = start

        if start < lo or end > hi:
            raise ValueError(
                f"valore fuori range [{lo}-{hi}] nel campo {name}: {part!r}"
            )
        values.update(range(start, end + 1, step))
    return frozenset(values), restricted


def parse(expr: str) -> CronExpr:
    """Analizza un'espressione cron a 5 campi. Solleva ValueError se non valida."""
    if not isinstance(expr, str):
        raise ValueError(f"l'espressione deve essere una stringa, non {type(expr).__name__}")
    parts = expr.split()
    if len(parts) != 5:
        raise ValueError(f"attesi 5 campi, trovati {len(parts)}: {expr!r}")

    parsed = [
        _parse_field(text, name, lo, hi)
        for text, (name, lo, hi) in zip(parts, _FIELDS)
    ]
    (mins, _), (hours, _), (dom, dom_r), (months, _), (dow, dow_r) = parsed
    dow = frozenset(d % 7 for d in dow)  # 7 -> 0 (domenica)
    return CronExpr(mins, hours, dom, months, dow, dom_r, dow_r)


def _to_utc(dt: datetime) -> datetime:
    if not isinstance(dt, datetime):
        raise TypeError(f"start_dt deve essere datetime, non {type(dt).__name__}")
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)  # naive: interpretato come UTC
    return dt.astimezone(timezone.utc)


def iter_runs(expr: str | CronExpr, start_dt: datetime):
    """Generatore (potenzialmente infinito) delle esecuzioni strettamente dopo start_dt.

    Solleva ValueError se l'espressione non è valida o non scatta mai.
    """
    cron = expr if isinstance(expr, CronExpr) else parse(expr)
    hours = sorted(cron.hours)
    minutes = sorted(cron.minutes)

    # Primo istante candidato: minuto successivo a start_dt (troncato al minuto).
    cur = _to_utc(start_dt).replace(second=0, microsecond=0) + timedelta(minutes=1)
    day = cur.replace(hour=0, minute=0)
    first_day = True
    days_without_match = 0

    while True:
        if cron.matches_day(day):
            days_without_match = 0
            for h in hours:
                for m in minutes:
                    candidate = day.replace(hour=h, minute=m)
                    if first_day and candidate < cur:
                        continue
                    yield candidate
        else:
            days_without_match += 1
            if days_without_match > _MAX_SEARCH_DAYS:
                raise ValueError(f"l'espressione non produce mai esecuzioni: {expr!r}")
        first_day = False
        try:
            day += timedelta(days=1)
        except OverflowError:
            return  # oltre datetime.max: nessuna ulteriore esecuzione


def next_runs(expr: str, start_dt: datetime, count: int = 5) -> list[datetime]:
    """Restituisce i prossimi ``count`` datetime UTC (aware) successivi a start_dt.

    start_dt naive è interpretato come UTC; se aware viene convertito in UTC.
    Solleva ValueError per espressioni non valide o count negativo.
    """
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ValueError(f"count deve essere un intero >= 0, non {count!r}")
    cron = parse(expr)  # valida subito anche quando count == 0
    result: list[datetime] = []
    if count == 0:
        return result
    for run in iter_runs(cron, start_dt):
        result.append(run)
        if len(result) == count:
            break
    return result
