"""Parser e iteratore di espressioni cron a 5 campi.

Campi: minuto, ora, giorno_mese, mese, giorno_settimana.
Semantica Vixie per giorno_mese / giorno_settimana.
"""

from datetime import datetime, timedelta, timezone

# (min, max) per ogni campo, nell'ordine dei campi.
_RANGES = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 6))

# Limite di ricerca per espressioni mai soddisfabili (circa 5 anni).
_MAX_SEARCH_DAYS = 5 * 366


def _parse_field(field, lo, hi):
    """Restituisce il set di interi di un singolo campo cron."""
    values = set()
    for part in field.split(','):
        if part == '':
            raise ValueError('token vuoto nel campo: %r' % field)
        step = 1
        if '/' in part:
            base, sep, step_s = part.partition('/')
            if step_s == '':
                raise ValueError('step mancante: %r' % part)
            try:
                step = int(step_s)
            except ValueError:
                raise ValueError('step non numerico: %r' % part)
            if step <= 0:
                raise ValueError('step <= 0: %r' % part)
        else:
            base = part
        if base == '*':
            start, end = lo, hi
        elif '-' in base:
            a, sep, b = base.partition('-')
            if a == '' or b == '':
                raise ValueError('intervallo non valido: %r' % base)
            try:
                start = int(a)
                end = int(b)
            except ValueError:
                raise ValueError('intervallo non numerico: %r' % base)
            if start > end:
                raise ValueError('intervallo a>b: %r' % base)
        else:
            try:
                start = int(base)
            except ValueError:
                raise ValueError('token non numerico: %r' % base)
            if '/' in part:
                end = hi
            else:
                end = start
        if start < lo or end > hi:
            raise ValueError('valore fuori range: %r' % base)
        values.update(range(start, end + 1, step))
    return values


def parse(expr):
    """Analizza un'espressione cron a 5 campi.

    Restituisce una tupla di 5 set di interi:
    (minuti, ore, giorni_mese, mesi, giorni_settimana).
    """
    if not isinstance(expr, str):
        raise ValueError('expr non stringa: %r' % (expr,))
    fields = expr.split()
    if len(fields) != 5:
        raise ValueError('numero di campi diverso da 5: %r' % expr)
    result = []
    for field, (lo, hi) in zip(fields, _RANGES):
        result.append(_parse_field(field, lo, hi))
    return tuple(result)


def _dom_dow_match(dom, dow, dom_set, dow_set, dom_star, dow_star):
    """Semantica Vixie per giorno_mese e giorno_settimana."""
    if dom_star and dow_star:
        return True
    if dom_star:
        return dow in dow_set
    if dow_star:
        return dom in dom_set
    return (dom in dom_set) or (dow in dow_set)


def next_runs(expr, start_dt, count=5):
    """Restituisce i prossimi ``count`` datetime UTC strettamente successivi a start_dt."""
    if not isinstance(count, int) or isinstance(count, bool):
        raise ValueError('count non intero: %r' % (count,))
    if count < 0:
        raise ValueError('count < 0: %r' % (count,))
    minutes, hours, dom_set, months, dow_set = parse(expr)

    if isinstance(start_dt, datetime):
        if start_dt.tzinfo is None:
            start = start_dt.replace(tzinfo=timezone.utc)
        else:
            start = start_dt.astimezone(timezone.utc)
    else:
        raise ValueError('start_dt non datetime: %r' % (start_dt,))

    dom_star = expr.split()[2] == '*'
    dow_star = expr.split()[4] == '*'

    results = []
    # Primo minuto strettamente successivo a start.
    cur = (start + timedelta(minutes=1)).replace(second=0, microsecond=0)
    # Limite di ricerca per espressioni mai soddisfabili.
    limit = start + timedelta(days=_MAX_SEARCH_DAYS)
    while len(results) < count:
        if cur > limit:
            raise ValueError('espressione mai soddisfabile: %r' % expr)
        if (cur.month in months
                and _dom_dow_match(cur.day, (cur.weekday() + 1) % 7,
                                   dom_set, dow_set, dom_star, dow_star)
                and cur.hour in hours
                and cur.minute in minutes):
            results.append(cur)
        cur += timedelta(minutes=1)
    return results
