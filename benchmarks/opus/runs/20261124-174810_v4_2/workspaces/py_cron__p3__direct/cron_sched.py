"""Parser e iteratore per espressioni cron a 5 campi.

Formato: ``minuto ora giorno_mese mese giorno_settimana``

Sintassi supportata per ciascun campo:
  *        tutti i valori
  N        valore singolo
  a-b      intervallo inclusivo
  a,b,c    lista (ogni elemento puo' essere uno qualunque dei costrutti)
  */n      step sull'intero dominio
  a-b/n    step su un intervallo
  N/n      step da N fino al massimo del dominio (estensione Vixie cron)

Semantica (come Vixie cron):
  * giorno_settimana: 0-7, dove sia 0 che 7 indicano la domenica.
  * Se sia giorno_mese sia giorno_settimana sono ristretti (non ``*``), una
    data corrisponde se soddisfa ALMENO UNO dei due campi (OR).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import FrozenSet, List

__all__ = ["CronExpr", "parse", "next_runs"]

# (nome, minimo, massimo)
_FIELDS = (
    ("minuto", 0, 59),
    ("ora", 0, 23),
    ("giorno_mese", 1, 31),
    ("mese", 1, 12),
    ("giorno_settimana", 0, 7),
)

# Limite di ricerca: 28 anni coprono l'intero ciclo calendario gregoriano
# rilevante (giorni della settimana + anni bisestili), piu' un margine.
_MAX_SEARCH_DAYS = 366 * 30


def _parse_int(text: str, name: str, lo: int, hi: int) -> int:
    if not text or not text.isdigit():
        raise ValueError(f"valore non valido {text!r} nel campo {name}")
    value = int(text)
    if not lo <= value <= hi:
        raise ValueError(
            f"valore {value} fuori intervallo [{lo}-{hi}] nel campo {name}"
        )
    return value


def _parse_field(text: str, name: str, lo: int, hi: int) -> FrozenSet[int]:
    if not text:
        raise ValueError(f"campo {name} vuoto")
    values = set()
    for part in text.split(","):
        if not part:
            raise ValueError(f"elemento vuoto nella lista del campo {name}")

        if "/" in part:
            base, _, step_txt = part.partition("/")
            if "/" in step_txt:
                raise ValueError(f"step multiplo non valido {part!r} nel campo {name}")
            if not step_txt.isdigit() or int(step_txt) == 0:
                raise ValueError(f"step non valido {step_txt!r} nel campo {name}")
            step = int(step_txt)
        else:
            base, step = part, None

        if base == "*":
            start, end = lo, hi
        elif "-" in base:
            a_txt, _, b_txt = base.partition("-")
            start = _parse_int(a_txt, name, lo, hi)
            end = _parse_int(b_txt, name, lo, hi)
            if start > end:
                raise ValueError(f"intervallo invertito {base!r} nel campo {name}")
        else:
            start = _parse_int(base, name, lo, hi)
            # "N/n" significa da N fino al massimo; "N" e' un singolo valore.
            end = hi if step is not None else start

        values.update(range(start, end + 1, step or 1))
    return frozenset(values)


@dataclass(frozen=True)
class CronExpr:
    minutes: FrozenSet[int]
    hours: FrozenSet[int]
    days: FrozenSet[int]
    months: FrozenSet[int]
    weekdays: FrozenSet[int]  # 0=domenica ... 6=sabato (7 normalizzato a 0)
    dom_restricted: bool
    dow_restricted: bool

    def matches_day(self, d: date) -> bool:
        if d.month not in self.months:
            return False
        cron_dow = (d.weekday() + 1) % 7  # Python: lun=0 -> cron: dom=0
        dom_ok = d.day in self.days
        dow_ok = cron_dow in self.weekdays
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
    """Analizza un'espressione cron a 5 campi. Solleva ValueError se non valida."""
    if not isinstance(expr, str):
        raise ValueError("l'espressione cron deve essere una stringa")
    parts = expr.split()
    if len(parts) != 5:
        raise ValueError(
            f"l'espressione cron richiede 5 campi, trovati {len(parts)}: {expr!r}"
        )
    sets = [
        _parse_field(text, name, lo, hi)
        for text, (name, lo, hi) in zip(parts, _FIELDS)
    ]
    weekdays = frozenset(0 if v == 7 else v for v in sets[4])
    return CronExpr(
        minutes=sets[0],
        hours=sets[1],
        days=sets[2],
        months=sets[3],
        weekdays=weekdays,
        dom_restricted=parts[2] != "*",
        dow_restricted=parts[4] != "*",
    )


def _to_utc(dt: datetime) -> datetime:
    if not isinstance(dt, datetime):
        raise TypeError("start_dt deve essere un datetime")
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def next_runs(expr: str, start_dt: datetime, count: int = 5) -> List[datetime]:
    """Restituisce i prossimi ``count`` datetime UTC strettamente successivi a start_dt.

    Un ``start_dt`` naive viene interpretato come UTC; uno aware viene
    convertito in UTC. I risultati sono datetime aware in UTC con secondi e
    microsecondi a zero.

    Solleva ValueError se l'espressione non e' valida o non produce mai
    occorrenze (es. ``0 0 30 2 *``).
    """
    cron = parse(expr)
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ValueError("count deve essere un intero >= 0")

    start = _to_utc(start_dt).replace(second=0, microsecond=0) + timedelta(minutes=1)
    minutes = sorted(cron.minutes)
    hours = sorted(cron.hours)

    results: List[datetime] = []
    day = start.date()
    days_without_match = 0
    first_day = True

    while len(results) < count:
        if cron.matches_day(day):
            days_without_match = 0
            for h in hours:
                if first_day and h < start.hour:
                    continue
                for m in minutes:
                    if first_day and h == start.hour and m < start.minute:
                        continue
                    results.append(
                        datetime(day.year, day.month, day.day, h, m, tzinfo=timezone.utc)
                    )
                    if len(results) == count:
                        return results
        else:
            days_without_match += 1
            if days_without_match > _MAX_SEARCH_DAYS:
                raise ValueError(
                    f"l'espressione cron {expr!r} non produce mai occorrenze"
                )
        first_day = False
        try:
            day += timedelta(days=1)
        except OverflowError:
            raise ValueError("superato l'intervallo di date rappresentabile") from None

    return results
