"""Parser e iteratore di espressioni cron a 5 campi.

Campi: minuto, ora, giorno_mese, mese, giorno_settimana.
Sintassi supportata per ogni campo: ``*``, numeri, intervalli ``a-b``,
liste ``a,b,c``, step ``*/n`` e ``a-b/n`` (anche combinati in liste).

Semantica (come il cron classico di Vixie):
- giorno_settimana: 0-7, dove sia 0 sia 7 indicano domenica.
- Se sia giorno_mese sia giorno_settimana sono ristretti (non ``*``),
  un giorno corrisponde se soddisfa almeno UNO dei due.
"""

from datetime import date, datetime, timedelta, timezone

__all__ = ["CronExpr", "parse", "next_runs"]

# (nome, minimo, massimo)
_FIELDS = (
    ("minuto", 0, 59),
    ("ora", 0, 23),
    ("giorno_mese", 1, 31),
    ("mese", 1, 12),
    ("giorno_settimana", 0, 7),
)

# Limite di ricerca: 400 anni coprono l'intero ciclo del calendario
# gregoriano, quindi se nessun giorno corrisponde l'espressione è impossibile.
_MAX_SEARCH_DAYS = 400 * 366


def _parse_int(text, name):
    if not text.isdigit():  # rifiuta segni, spazi, stringhe vuote, decimali
        raise ValueError(f"valore non numerico {text!r} nel campo {name}")
    return int(text)


def _parse_field(text, name, lo, hi):
    """Restituisce (insieme_valori, è_asterisco)."""
    if not isinstance(text, str) or text == "":
        raise ValueError(f"campo {name} vuoto")
    values = set()
    for part in text.split(","):
        if part == "":
            raise ValueError(f"elemento vuoto nella lista del campo {name}")
        if "/" in part:
            base, _, step_txt = part.partition("/")
            step = _parse_int(step_txt, name)
            if step <= 0:
                raise ValueError(f"step non valido {step} nel campo {name}")
        else:
            base, step = part, 1

        if base == "*":
            start, end = lo, hi
        elif "-" in base:
            a_txt, _, b_txt = base.partition("-")
            start, end = _parse_int(a_txt, name), _parse_int(b_txt, name)
            if start > end:
                raise ValueError(
                    f"intervallo invertito {start}-{end} nel campo {name}")
        else:
            start = _parse_int(base, name)
            if "/" in part:
                # "a/n" non è richiesto dalla specifica: lo rifiutiamo.
                raise ValueError(
                    f"step ammesso solo su '*' o intervalli nel campo {name}")
            end = start

        if start < lo or end > hi:
            raise ValueError(
                f"valore fuori intervallo [{lo}-{hi}] nel campo {name}: {part!r}")
        values.update(range(start, end + 1, step))
    return frozenset(values), text == "*"


class CronExpr:
    """Espressione cron analizzata."""

    def __init__(self, expr):
        if not isinstance(expr, str):
            raise ValueError("l'espressione cron deve essere una stringa")
        parts = expr.split()
        if len(parts) != 5:
            raise ValueError(
                f"l'espressione cron deve avere 5 campi, trovati {len(parts)}")
        parsed = [_parse_field(p, n, lo, hi)
                  for p, (n, lo, hi) in zip(parts, _FIELDS)]
        self.expr = expr
        self.minutes = parsed[0][0]
        self.hours = parsed[1][0]
        self.days = parsed[2][0]
        self.months = parsed[3][0]
        dow = set(parsed[4][0])
        if 7 in dow:
            dow.discard(7)
            dow.add(0)
        self.weekdays = frozenset(dow)  # 0=domenica ... 6=sabato
        self._dom_star = parsed[2][1]
        self._dow_star = parsed[4][1]
        self._sorted_hours = sorted(self.hours)
        self._sorted_minutes = sorted(self.minutes)

    def __repr__(self):
        return f"CronExpr({self.expr!r})"

    def matches_day(self, d):
        if d.month not in self.months:
            return False
        dom_ok = d.day in self.days
        dow_ok = (d.isoweekday() % 7) in self.weekdays  # lun=1..dom=0
        if self._dom_star or self._dow_star:
            return dom_ok and dow_ok
        return dom_ok or dow_ok

    def matches(self, dt):
        return (dt.minute in self.minutes and dt.hour in self.hours
                and self.matches_day(dt.date()))

    def iter_after(self, start_dt):
        """Genera i datetime UTC (aware) strettamente successivi a start_dt."""
        cur = _to_utc(start_dt).replace(second=0, microsecond=0)
        cur += timedelta(minutes=1)
        day = cur.date()
        first = True
        searched = 0
        while True:
            if self.matches_day(day):
                searched = 0
                for h in self._sorted_hours:
                    if first and h < cur.hour:
                        continue
                    for m in self._sorted_minutes:
                        if first and h == cur.hour and m < cur.minute:
                            continue
                        yield datetime(day.year, day.month, day.day, h, m,
                                       tzinfo=timezone.utc)
            else:
                searched += 1
                if searched > _MAX_SEARCH_DAYS:
                    raise ValueError(
                        f"l'espressione {self.expr!r} non corrisponde mai")
            first = False
            if day == date.max:
                return
            day += timedelta(days=1)


def _to_utc(dt):
    if not isinstance(dt, datetime):
        raise TypeError("start_dt deve essere un datetime")
    if dt.tzinfo is None or dt.utcoffset() is None:
        return dt.replace(tzinfo=timezone.utc)  # naive = UTC
    return dt.astimezone(timezone.utc)


def parse(expr):
    """Analizza un'espressione cron; solleva ValueError se non valida."""
    return CronExpr(expr)


def next_runs(expr, start_dt, count=5):
    """Restituisce i prossimi ``count`` datetime UTC successivi a start_dt.

    ``start_dt`` naive è interpretato come UTC; se aware viene convertito.
    I risultati sono datetime aware con tzinfo=timezone.utc.
    Solleva ValueError per espressioni non valide o mai soddisfacibili.
    """
    cron = expr if isinstance(expr, CronExpr) else CronExpr(expr)
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ValueError("count deve essere un intero >= 0")
    result = []
    if count == 0:
        return result
    for dt in cron.iter_after(start_dt):
        result.append(dt)
        if len(result) == count:
            break
    return result
