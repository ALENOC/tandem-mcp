"""Parser e iteratore di espressioni cron a 5 campi.

Campi: minuto, ora, giorno_mese, mese, giorno_settimana.
"""

from datetime import datetime, timedelta, timezone

# (nome, minimo, massimo) per ogni campo, nell'ordine dei 5 campi.
_FIELDS = (
    ("minute", 0, 59),
    ("hour", 0, 23),
    ("day_of_month", 1, 31),
    ("month", 1, 12),
    ("day_of_week", 0, 7),
)

# Numero di giorni per mese (non bisestile) e per anno (non bisestile).
_DAYS_IN_MONTH = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_DAYS_IN_MONTH_LEAP = (31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_DAYS_IN_YEAR = 365


def _parse_field(spec, lo, hi, name):
    """Restituisce il set dei valori interi validi per un singolo campo."""
    if not isinstance(spec, str):
        raise ValueError("campo non stringa: %r" % (spec,))
    values = set()
    for part in spec.split(","):
        if part == "":
            raise ValueError("token vuoto nel campo %s" % name)
        step = 1
        if "/" in part:
            base, sep, step_s = part.partition("/")
            if step_s == "" or not step_s.isdigit():
                raise ValueError("step non numerico nel campo %s: %r" % (name, part))
            step = int(step_s)
            if step <= 0:
                raise ValueError("step <= 0 nel campo %s: %r" % (name, part))
        else:
            base = part
        if base == "*":
            start, end = lo, hi
        elif "-" in base:
            a, sep, b = base.partition("-")
            if not a.isdigit() or not b.isdigit():
                raise ValueError("intervallo non valido nel campo %s: %r" % (name, base))
            start, end = int(a), int(b)
            if start > end:
                raise ValueError("intervallo a > b nel campo %s: %r" % (name, base))
        elif base.isdigit():
            start = end = int(base)
        else:
            raise ValueError("token non numerico nel campo %s: %r" % (name, base))
        if start < lo or end > hi:
            raise ValueError("valore fuori range nel campo %s: %r" % (name, base))
        values.update(range(start, end + 1, step))
    return values


def _parse(expr):
    """Valida l'espressione e restituisce i 5 set di valori."""
    if not isinstance(expr, str):
        raise ValueError("espressione non stringa: %r" % (expr,))
    parts = expr.split()
    if len(parts) != 5:
        raise ValueError("numero di campi diverso da 5: %r" % (expr,))
    sets = []
    for spec, (name, lo, hi) in zip(parts, _FIELDS):
        sets.append(_parse_field(spec, lo, hi, name))
    # giorno_settimana: 7 = domenica = 0
    sets[4] = {v % 7 for v in sets[4]}
    return sets


def _dom_dow_restricted(expr):
    """Restituisce (dom_restricted, dow_restricted): True se il campo non inizia con '*'."""
    parts = expr.split()
    return not parts[2].startswith("*"), not parts[4].startswith("*")


def _day_matches(dom_set, dow_set, day, month, year, dom_restricted, dow_restricted):
    """Semantica Vixie cron per la corrispondenza del giorno."""
    dom_ok = day in dom_set
    dow_ok = (datetime(year, month, day).weekday() + 1) % 7 in dow_set
    if dom_restricted and dow_restricted:
        return dom_ok or dow_ok
    if dom_restricted:
        return dom_ok
    if dow_restricted:
        return dow_ok
    return dom_ok and dow_ok


def _impossible(sets, dom_restricted, dow_restricted):
    """True se l'espressione non puo mai corrispondere (nessun giorno valido)."""
    dom_set, dow_set = sets[2], sets[4]
    for month in sets[3]:
        for day in range(1, _DAYS_IN_MONTH_LEAP[month - 1] + 1):
            if _day_matches(dom_set, dow_set, day, month, 2000, dom_restricted, dow_restricted):
                return False
    return True


def next_runs(expr, start_dt, count=5):
    """Restituisce i prossimi ``count`` datetime UTC strettamente successivi a start_dt."""
    if not isinstance(count, int) or isinstance(count, bool) or count < 1:
        raise ValueError("count deve essere un intero >= 1")
    sets = _parse(expr)
    minute_set, hour_set, dom_set, month_set, dow_set = sets
    dom_restricted, dow_restricted = _dom_dow_restricted(expr)
    if _impossible(sets, dom_restricted, dow_restricted):
        raise ValueError("espressione che non puo mai corrispondere: %r" % (expr,))

    if start_dt.tzinfo is None:
        start = start_dt.replace(tzinfo=timezone.utc)
    else:
        start = start_dt.astimezone(timezone.utc)

    results = []
    # Limite di ricerca: alcuni anni oltre la data di partenza.
    limit = start + timedelta(days=_DAYS_IN_YEAR * 8)
    cur = start.replace(second=0, microsecond=0) + timedelta(minutes=1)
    while len(results) < count:
        if cur > limit:
            raise ValueError("espressione che non puo mai corrispondere: %r" % (expr,))
        if cur.month not in month_set or not _day_matches(
            dom_set, dow_set, cur.day, cur.month, cur.year, dom_restricted, dow_restricted
        ):
            # Salta al primo giorno corrispondente (mese e giorno).
            cur = (cur + timedelta(days=1)).replace(hour=0, minute=0)
            continue
        if cur.hour not in hour_set:
            later = [h for h in hour_set if h > cur.hour]
            if later:
                cur = cur.replace(hour=min(later), minute=min(minute_set))
            else:
                cur = (cur + timedelta(days=1)).replace(
                    hour=min(hour_set), minute=min(minute_set)
                )
            continue
        if cur.minute not in minute_set:
            later = [m for m in minute_set if m > cur.minute]
            if later:
                cur = cur.replace(minute=min(later))
            elif cur.hour < 23:
                cur = (cur.replace(minute=0) + timedelta(hours=1)).replace(
                    minute=min(minute_set)
                )
            else:
                cur = (cur + timedelta(days=1)).replace(
                    hour=min(hour_set), minute=min(minute_set)
                )
            continue
        # Tutti i campi corrispondono.
        results.append(cur)
        cur += timedelta(minutes=1)
    return results
