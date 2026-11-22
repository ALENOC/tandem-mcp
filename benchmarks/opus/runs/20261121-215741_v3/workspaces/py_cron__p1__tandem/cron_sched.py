"""Parser e iteratore di espressioni cron a 5 campi.

Campi (in ordine): minuto, ora, giorno_mese, mese, giorno_settimana.

API pubblica:
    parse_cron(expr) -> tupla di 5 frozenset di interi
    next_runs(expr, start_dt, count=5) -> lista di datetime (tzinfo=UTC)
"""

from datetime import datetime, timedelta, timezone

# (min, max) per campo, nell'ordine dei campi.
_RANGES = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 6))

# Limite di ricerca per espressioni che non producono mai date.
_SEARCH_LIMIT = timedelta(days=366 * 5)


def _parse_field(field, lo, hi, is_dow):
    """Restituisce il frozenset di interi descritti da un singolo campo."""
    values = set()
    for part in field.split(','):
        if part == '':
            raise ValueError('token vuoto nel campo: %r' % field)
        step = 1
        if '/' in part:
            base, _sep, step_s = part.partition('/')
            if step_s == '' or not step_s.isdigit():
                raise ValueError('step non numerico: %r' % part)
            step = int(step_s)
            if step == 0:
                raise ValueError('step zero: %r' % part)
        else:
            base = part
        if base == '*':
            start, end = lo, hi
        elif '-' in base:
            a, _sep, b = base.partition('-')
            if not a.isdigit() or not b.isdigit():
                raise ValueError('intervallo non numerico: %r' % base)
            start, end = int(a), int(b)
            if start > end:
                raise ValueError('intervallo a>b: %r' % base)
        elif base.isdigit():
            start = end = int(base)
        else:
            raise ValueError('token non valido: %r' % base)
        hi_eff = 7 if is_dow else hi
        if start < lo or end > hi_eff:
            raise ValueError('valore fuori intervallo: %r' % base)
        if step == 1:
            values.update(range(start, end + 1))
        else:
            values.update(range(start, end + 1, step))
    if is_dow and 7 in values:
        values.discard(7)
        values.add(0)
    return frozenset(values)


def parse_cron(expr):
    """Analizza un'espressione cron a 5 campi.

    Restituisce una tupla di 5 frozenset di interi:
    (minuti, ore, giorni_mese, mesi, giorni_settimana).
    """
    if not isinstance(expr, str):
        raise ValueError('espressione non stringa: %r' % (expr,))
    fields = expr.split()
    if len(fields) != 5:
        raise ValueError('attesi 5 campi, trovati %d' % len(fields))
    parsed = []
    for i, (field, (lo, hi)) in enumerate(zip(fields, _RANGES)):
        parsed.append(_parse_field(field, lo, hi, is_dow=(i == 4)))
    return tuple(parsed)


def _day_ok(day, weekday, dom_set, dow_set, dom_star, dow_star):
    """Semantica giorno_mese / giorno_settimana.

    Se entrambi i campi sono ristretti (non '*') una data corrisponde se
    soddisfa UNO dei due (OR); se uno dei due e' '*', vale solo l'altro.
    """
    # Convert Python weekday (0=Mon..6=Sun) to cron dow (0=Sun,1=Mon..6=Sat)
    cron_dow = (weekday + 1) % 7
    if dom_star and dow_star:
        return True
    if dom_star:
        return cron_dow in dow_set
    if dow_star:
        return day in dom_set
    return (day in dom_set) or (cron_dow in dow_set)


def next_runs(expr, start_dt, count=5):
    """Restituisce i primi ``count`` run strettamente successivi a ``start_dt``.

    I datetime restituiti hanno tzinfo=UTC, secondi e microsecondi a zero.
    """
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise ValueError('count deve essere un intero >= 1')
    minutes, hours, dom_set, months, dow_set = parse_cron(expr)
    fields = expr.split()
    dom_star = fields[2] == '*'
    dow_star = fields[4] == '*'

    if not isinstance(start_dt, datetime):
        raise ValueError('start_dt deve essere un datetime')
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=timezone.utc)
    else:
        start_dt = start_dt.astimezone(timezone.utc)

    cur = start_dt.replace(second=0, microsecond=0) + timedelta(minutes=1)
    limit = start_dt + _SEARCH_LIMIT
    results = []
    while len(results) < count:
        if cur > limit:
            raise ValueError('espressione che non produce mai date: %r' % expr)
        if (cur.month in months and cur.hour in hours and cur.minute in minutes
                and _day_ok(cur.day, cur.weekday(), dom_set, dow_set,
                            dom_star, dow_star)):
            results.append(cur)
        cur += timedelta(minutes=1)
    return results
