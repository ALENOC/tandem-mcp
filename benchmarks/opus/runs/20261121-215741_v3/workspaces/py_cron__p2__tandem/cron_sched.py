"""Parser e iteratore di espressioni cron a 5 campi.

Campi (in ordine): minuto, ora, giorno_mese, mese, giorno_settimana.

Range validi:
    minuto            0-59
    ora               0-23
    giorno_mese       1-31
    mese              1-12
    giorno_settimana  0-6 (0 = domenica), accettato anche 7 come domenica

Sintassi supportata in ogni campo:
    *                 tutti i valori
    n                 numero singolo
    a-b               intervallo
    a,b,c             lista (gli elementi possono essere numeri, intervalli o step)
    */n               step su tutto il range
    a-b/n             step su un intervallo

La funzione ``next_runs(expr, start_dt, count=5)`` restituisce una lista di
``count`` datetime timezone-aware in UTC, strettamente successivi a ``start_dt``,
in ordine crescente, con secondi e microsecondi a zero.
"""

from datetime import date, datetime, timedelta, timezone

# (nome, minimo, massimo) per ogni campo, nell'ordine dei 5 campi.
_FIELD_SPECS = (
    ("minuto", 0, 59),
    ("ora", 0, 23),
    ("giorno_mese", 1, 31),
    ("mese", 1, 12),
    # Il range di parsing e' 0-7: 7 e' accettato come domenica e poi
    # normalizzato a 0 (vedi parse_cron). 8 e' fuori range.
    ("giorno_settimana", 0, 7),
)

# Numero massimo di anni da scandagliare alla ricerca di date raggiungibili.
# Un limite ampio (100 anni) garantisce di trovare date raggiungibili anche
# lontane (es. 29 febbraio) mentre le date impossibili (es. 31 febbraio)
# sollevano ValueError.
_MAX_YEARS = 100


def _parse_int(text, name):
    text = text.strip()
    if not text:
        raise ValueError("token vuoto nel campo %s" % name)
    try:
        return int(text)
    except ValueError:
        raise ValueError("token non numerico %r nel campo %s" % (text, name))


def _parse_part(part, name, lo, hi):
    """Restituisce il set di interi descritti da un elemento (senza virgole)."""
    step = 1
    if "/" in part:
        base, _sep, step_text = part.partition("/")
        if step_text == "":
            raise ValueError("step mancante in %r" % part)
        try:
            step = int(step_text)
        except ValueError:
            raise ValueError("step non numerico in %r" % part)
        if step <= 0:
            raise ValueError("step <= 0 in %r" % part)
    else:
        base = part

    if base == "*":
        start, end = lo, hi
    elif "-" in base:
        a, _sep, b = base.partition("-")
        start = _parse_int(a, name)
        end = _parse_int(b, name)
        if start > end:
            raise ValueError("intervallo con a>b in %r" % part)
    else:
        start = end = _parse_int(base, name)

    if start < lo or end > hi:
        raise ValueError("valore fuori range in %r" % part)

    return set(range(start, end + 1, step))


def _parse_field(field, name, lo, hi):
    """Restituisce il set di interi descritti da un singolo campo cron."""
    if not isinstance(field, str):
        raise ValueError("campo non stringa: %r" % (field,))
    field = field.strip()
    if field == "":
        raise ValueError("campo vuoto per %s" % name)

    values = set()
    for part in field.split(","):
        part = part.strip()
        if part == "":
            raise ValueError("token vuoto nel campo %s" % name)
        values |= _parse_part(part, name, lo, hi)
    return values


def _validate_date(days, months):
    """Solleva ValueError se la combinazione giorno/mese non e' mai raggiungibile."""
    for m in sorted(months):
        if m in (1, 3, 5, 7, 8, 10, 12):
            max_day = 31
        elif m in (4, 6, 9, 11):
            max_day = 30
        else:  # febbraio
            max_day = 29
        if any(d <= max_day for d in days):
            return
    raise ValueError("combinazione giorno/mese non raggiungibile")


def parse_cron(expr):
    """Analizza ``expr`` e restituisce una tupla di 5 set di interi.

    L'ordine della tupla e': (minuti, ore, giorni_mese, mesi, giorni_settimana).
    Per il campo giorno_settimana il valore 7 viene normalizzato a 0 (domenica).
    """
    if not isinstance(expr, str):
        raise ValueError("expr non stringa: %r" % (expr,))
    fields = expr.split()
    if len(fields) != 5:
        raise ValueError("numero di campi diverso da 5: %r" % (expr,))

    sets = []
    for field, (name, lo, hi) in zip(fields, _FIELD_SPECS):
        sets.append(_parse_field(field, name, lo, hi))

    # Normalizza il giorno_settimana: 7 == 0 (domenica).
    dow = sets[4]
    if 7 in dow:
        dow.discard(7)
        dow.add(0)

    _validate_date(sets[2], sets[3])
    return tuple(sets)


def _day_matches(d, dom, dow, dom_restricted, dow_restricted):
    """Semantica cron classica per la corrispondenza del giorno.

    Se sia giorno_mese sia giorno_settimana sono ristretti (non '*') basta che
    uno dei due corrisponda (OR); se e' ristretto solo uno, conta solo quello.
    """
    # Converte il weekday di Python (Mon=0..Sun=6) al formato cron (Sun=0..Sat=6).
    cron_dow = (d.weekday() + 1) % 7
    if dom_restricted and dow_restricted:
        return d.day in dom or cron_dow in dow
    if dom_restricted:
        return d.day in dom
    if dow_restricted:
        return cron_dow in dow
    return True


def next_runs(expr, start_dt, count=5):
    """Restituisce i prossimi ``count`` istanti di esecuzione di ``expr``.

    I risultati sono datetime timezone-aware in UTC, strettamente successivi a
    ``start_dt``, in ordine crescente, con secondi e microsecondi a zero.
    """
    if isinstance(count, bool) or not isinstance(count, int):
        raise ValueError("count deve essere un int")
    if count < 0:
        raise ValueError("count deve essere >= 0")
    if count == 0:
        return []

    if not isinstance(start_dt, datetime):
        raise ValueError("start_dt deve essere un datetime")

    minutes, hours, dom, months, dow = parse_cron(expr)
    dom_restricted = dom != set(range(1, 32))
    dow_restricted = dow != set(range(0, 7))

    if start_dt.tzinfo is None:
        start = start_dt.replace(tzinfo=timezone.utc)
    else:
        start = start_dt.astimezone(timezone.utc)

    sorted_hours = sorted(hours)
    sorted_minutes = sorted(minutes)

    results = []
    limit = start + timedelta(days=366 * _MAX_YEARS)
    d = start.date()
    while len(results) < count:
        if d > limit.date():
            raise ValueError("nessuna data raggiungibile entro %d anni" % _MAX_YEARS)
        if d.month in months and _day_matches(d, dom, dow, dom_restricted, dow_restricted):
            for h in sorted_hours:
                for m in sorted_minutes:
                    dt = datetime(d.year, d.month, d.day, h, m, tzinfo=timezone.utc)
                    if dt > start:
                        results.append(dt)
        d += timedelta(days=1)
    return results[:count]
