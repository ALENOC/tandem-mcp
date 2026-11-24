"""Parser e iteratore di espressioni cron a 5 campi.

Campi (in ordine): minuto, ora, giorno_mese, mese, giorno_settimana.

Sintassi supportata per ogni campo:
    *            tutti i valori del range
    n            un singolo numero
    a-b          intervallo incluso
    a,b,c        lista di valori
    */n          step su tutto il range
    a-b/n        step su un intervallo

La funzione pubblica e' next_runs(expr, start_dt, count=5).
"""

import calendar
from datetime import datetime, timedelta, timezone

# (min, max) per ogni campo, nell'ordine dei campi.
# Per il giorno_settimana il range di validazione e' 0-7 (7 = domenica).
_RANGES = {
    "minute": (0, 59),
    "hour": (0, 23),
    "day": (1, 31),
    "month": (1, 12),
    "weekday": (0, 7),
}

_FIELD_NAMES = ("minute", "hour", "day", "month", "weekday")


def _parse_field(field, name):
    """Restituisce (set_valori, e_star) per un singolo campo cron.

    ``e_star`` e' True solo se il campo e' esattamente "*".
    """
    lo, hi = _RANGES[name]
    values = set()
    is_star = (field == "*")

    for part in field.split(","):
        if part == "":
            raise ValueError("token vuoto nel campo %s" % name)

        step = 1
        if "/" in part:
            base, sep, step_s = part.partition("/")
            if step_s == "":
                raise ValueError("step mancante nel campo %s" % name)
            try:
                step = int(step_s)
            except ValueError:
                raise ValueError("step non numerico nel campo %s" % name)
            if step == 0:
                raise ValueError("step zero nel campo %s" % name)
        else:
            base = part

        if base == "*":
            start, end = lo, hi
        elif "-" in base:
            a, sep, b = base.partition("-")
            try:
                start = int(a)
                end = int(b)
            except ValueError:
                raise ValueError("intervallo non numerico nel campo %s" % name)
            if start > end:
                raise ValueError("intervallo a>b nel campo %s" % name)
        else:
            try:
                start = int(base)
            except ValueError:
                raise ValueError("valore non numerico nel campo %s" % name)
            end = start

        if start < lo or end > hi:
            raise ValueError("valore fuori range nel campo %s" % name)

        values.update(range(start, end + 1, step))

    if name == "weekday" and 7 in values:
        values.discard(7)
        values.add(0)

    return values, is_star


def _parse(expr):
    """Valida l'espressione e restituisce i 5 campi (values, is_star)."""
    if not isinstance(expr, str):
        raise ValueError("espressione cron non stringa")
    fields = expr.split()
    if len(fields) != 5:
        raise ValueError("espressione cron deve avere esattamente 5 campi")
    parsed = []
    for field, name in zip(fields, _FIELD_NAMES):
        parsed.append(_parse_field(field, name))
    return parsed


def _day_matches(day_values, month_values, weekday_values, dow_star, dom_star,
                 date):
    """Verifica se una data corrisponde ai campi giorno/mese/settimana.

    Semantica standard cron: se sia giorno_mese sia giorno_settimana sono
    ristretti (non "*"), la data corrisponde se soddisfa ALMENO uno dei due.
    """
    if date.month not in month_values:
        return False
    dom_ok = date.day in day_values
    dow_ok = (date.weekday() + 1) % 7 in weekday_values
    if dow_star and dom_star:
        return True
    if dow_star:
        return dom_ok
    if dom_star:
        return dow_ok
    return dom_ok or dow_ok


def _next_valid_from(from_dt, minutes, hours, day_values, month_values,
                     weekday_values, dow_star, dom_star):
    """Restituisce il piu' piccolo datetime valido (UTC, secondi/microsecondi a
    zero) maggiore o uguale a ``from_dt``.

    L'iterazione salta interi mesi e giorni non validi invece di avanzare
    minuto per minuto, quindi e' efficiente anche su intervalli di anni.
    """
    year, month, day = from_dt.year, from_dt.month, from_dt.day
    # Limite di ricerca: circa 5 anni di mesi.
    for _ in range(5 * 12 + 1):
        if month in month_values:
            days_in_month = calendar.monthrange(year, month)[1]
            for d in range(day, days_in_month + 1):
                date = datetime(year, month, d)
                if not _day_matches(day_values, month_values, weekday_values,
                                   dow_star, dom_star, date):
                    continue
                for h in hours:
                    for m in minutes:
                        cand = datetime(year, month, d, h, m, tzinfo=timezone.utc)
                        if cand >= from_dt:
                            return cand
        month += 1
        if month > 12:
            month = 1
            year += 1
        day = 1
    raise ValueError("espressione cron impossibile")


def next_runs(expr, start_dt, count=5):
    """Restituisce i prossimi ``count`` datetime UTC strettamente successivi a
    ``start_dt`` che soddisfano l'espressione cron ``expr``.

    ``start_dt`` naive e' interpretato come UTC; se e' aware viene convertito
    in UTC. I datetime restituiti sono timezone-aware in UTC con secondi e
    microsecondi a zero.

    Solleva ValueError per espressioni non valide o impossibili.
    """
    if not isinstance(count, int) or isinstance(count, bool) or count < 1:
        raise ValueError("count deve essere un intero >= 1")
    if not isinstance(start_dt, datetime):
        raise ValueError("start_dt deve essere un datetime")

    (minute_values, _), (hour_values, _), (day_values, dom_star), \
        (month_values, _), (weekday_values, dow_star) = _parse(expr)

    minutes = sorted(minute_values)
    hours = sorted(hour_values)

    if start_dt.tzinfo is None:
        start = start_dt.replace(tzinfo=timezone.utc)
    else:
        start = start_dt.astimezone(timezone.utc)

    results = []
    cur = start.replace(second=0, microsecond=0)
    for _ in range(count):
        cur = _next_valid_from(cur + timedelta(minutes=1), minutes, hours,
                               day_values, month_values, weekday_values,
                               dow_star, dom_star)
        results.append(cur)

    return results
