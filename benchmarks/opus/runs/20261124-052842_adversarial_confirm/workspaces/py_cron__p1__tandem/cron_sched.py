"""Parser e iteratore di espressioni cron a 5 campi.

Campi (in ordine): minuto, ora, giorno_mese, mese, giorno_settimana.

Range:
    minuto            0-59
    ora               0-23
    giorno_mese       1-31
    mese              1-12
    giorno_settimana  0-6  (0 = domenica)

Sintassi supportata per ogni campo:
    *            tutti i valori
    n            un singolo numero
    a-b          intervallo
    a,b,c        lista (gli elementi possono essere numeri, intervalli o step)
    */n          step su tutto il range
    a-b/n        step su un intervallo

Semantica cron standard: se sia giorno_mese che giorno_settimana sono
diversi da '*', un giorno corrisponde se corrisponde ALMENO UNO dei due.
"""

from datetime import datetime, timedelta, timezone

__all__ = ["parse", "next_runs", "CronExpr", "CronError"]


class CronError(ValueError):
    """Errore di sintassi o di semantica di un'espressione cron."""


# (nome, minimo, massimo) per ogni campo, in ordine.
_FIELDS = (
    ("minute", 0, 59),
    ("hour", 0, 23),
    ("day_of_month", 1, 31),
    ("month", 1, 12),
    ("day_of_week", 0, 6),
)

# Numero massimo di anni da scandire prima di dichiarare un'espressione
# mai soddisfacibile (es. '0 0 31 2 *').
_MAX_YEARS = 400


def _parse_field(spec, lo, hi, name):
    """Restituisce il set dei valori ammessi per un singolo campo."""
    if not isinstance(spec, str):
        raise CronError("campo %s: valore non stringa" % name)
    spec = spec.strip()
    if spec == "":
        raise CronError("campo %s: token vuoto" % name)

    values = set()
    for part in spec.split(","):
        part = part.strip()
        if part == "":
            raise CronError("campo %s: token vuoto nella lista" % name)
        values |= _parse_part(part, lo, hi, name)
    return values


def _parse_part(part, lo, hi, name):
    """Restituisce il set dei valori ammessi per una parte (senza virgole)."""
    step = 1
    if "/" in part:
        base, sep, step_s = part.partition("/")
        if step_s == "":
            raise CronError("campo %s: step vuoto" % name)
        try:
            step = int(step_s)
        except ValueError:
            raise CronError("campo %s: step non numerico" % name)
        if step <= 0:
            raise CronError("campo %s: step deve essere > 0" % name)
    else:
        base = part

    if base == "*":
        start, end = lo, hi
    elif "-" in base:
        a, sep, b = base.partition("-")
        start = _to_int(a, name)
        end = _to_int(b, name)
        if start > end:
            raise CronError("campo %s: intervallo a>b" % name)
    else:
        start = end = _to_int(base, name)

    if start < lo or end > hi:
        raise CronError("campo %s: valore fuori range" % name)

    return set(range(start, end + 1, step))


def _to_int(token, name):
    token = token.strip()
    if token == "":
        raise CronError("campo %s: token vuoto" % name)
    try:
        return int(token)
    except ValueError:
        raise CronError("campo %s: token non numerico" % name)


def parse(expr):
    """Analizza un'espressione cron a 5 campi.

    Restituisce un oggetto CronExpr che espone i 5 insiemi di valori
    ammessi (attributi minute, hour, day_of_month, month, day_of_week)
    e un metodo iter() che produce i datetime successivi all'infinito.
    """
    if not isinstance(expr, str):
        raise CronError("espressione cron non stringa")
    fields = expr.split()
    if len(fields) != 5:
        raise CronError("numero di campi diverso da 5")

    minutes = _parse_field(fields[0], 0, 59, "minute")
    hours = _parse_field(fields[1], 0, 23, "hour")
    doms = _parse_field(fields[2], 1, 31, "day_of_month")
    months = _parse_field(fields[3], 1, 12, "month")
    dows = _parse_field(fields[4], 0, 6, "day_of_week")

    return CronExpr(minutes, hours, doms, months, dows,
                    fields[2] != "*", fields[4] != "*")


class CronExpr:
    """Espressione cron analizzata: 5 insiemi di valori + iteratore."""

    __slots__ = ("minute", "hour", "day_of_month", "month", "day_of_week",
                 "_dom_restricted", "_dow_restricted")

    def __init__(self, minutes, hours, doms, months, dows,
                 dom_restricted, dow_restricted):
        self.minute = minutes
        self.hour = hours
        self.day_of_month = doms
        self.month = months
        self.day_of_week = dows
        self._dom_restricted = dom_restricted
        self._dow_restricted = dow_restricted

    def day_matches(self, dt):
        """Verifica la corrispondenza del giorno (semantica cron OR)."""
        dom_ok = dt.day in self.day_of_month
        dow_ok = ((dt.weekday() + 1) % 7) in self.day_of_week
        if self._dom_restricted and self._dow_restricted:
            return dom_ok or dow_ok
        if self._dom_restricted:
            return dom_ok
        if self._dow_restricted:
            return dow_ok
        return True

    def matches(self, dt):
        return (dt.minute in self.minute and dt.hour in self.hour
                and dt.month in self.month and self.day_matches(dt))

    def iter(self, start_dt):
        """Generatore che produce i datetime successivi a start_dt."""
        cur = _to_utc(start_dt)
        cur = cur.replace(second=0, microsecond=0) + timedelta(minutes=1)
        while True:
            if self.matches(cur):
                yield cur
            cur += timedelta(minutes=1)


def _to_utc(dt):
    if not isinstance(dt, datetime):
        raise CronError("start_dt non datetime")
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def next_runs(expr, start_dt, count=5):
    """Restituisce i prossimi ``count`` datetime UTC strettamente successivi
    a ``start_dt`` per l'espressione cron ``expr``."""
    if not isinstance(count, int) or isinstance(count, bool) or count < 1:
        raise CronError("count deve essere un intero >= 1")

    cron = parse(expr)
    start = _to_utc(start_dt)
    start = start.replace(second=0, microsecond=0)

    results = []
    cur = start + timedelta(minutes=1)
    limit_year = start.year + _MAX_YEARS
    while len(results) < count:
        if cur.year > limit_year:
            raise CronError("espressione cron mai soddisfacibile")
        if cron.matches(cur):
            results.append(cur)
        cur += timedelta(minutes=1)
    return results
