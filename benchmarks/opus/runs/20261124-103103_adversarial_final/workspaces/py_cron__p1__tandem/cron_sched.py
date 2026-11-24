"""Parser e iteratore di espressioni cron a 5 campi.

Campi (in ordine): minuto, ora, giorno_mese, mese, giorno_settimana.

Range validi:
    minuto            0-59
    ora               0-23
    giorno_mese       1-31
    mese              1-12
    giorno_settimana  0-6 (0 = domenica, accettato anche 7 come domenica)

Sintassi supportata per ogni campo:
    '*'
    numero
    intervallo 'a-b'
    lista 'a,b,c' (gli elementi possono essere numeri, intervalli o step)
    step '*/n' e 'a-b/n'

Semantica giorno (regola OR di Vixie cron):
    se sia giorno_mese sia giorno_settimana sono ristretti (non '*'),
    una data corrisponde se corrisponde a uno dei due campi.
    se uno dei due e' '*', vale solo l'altro.
"""

from datetime import datetime, timedelta, timezone

__all__ = ["parse_cron", "next_runs"]

# (min, max, nome) per ogni campo, in ordine.
_FIELD_SPECS = (
    (0, 59, "minuto"),
    (0, 23, "ora"),
    (1, 31, "giorno_mese"),
    (1, 12, "mese"),
    (0, 6, "giorno_settimana"),
)

# Limite di ricerca per espressioni che non possono mai scattare.
_SEARCH_LIMIT_DAYS = 366 * 5


def _parse_field(field, lo, hi, name, dow=False):
    """Restituisce l'insieme dei valori validi per un singolo campo cron.

    Per il campo giorno_settimana (dow=True) e' accettato anche 7 come
    domenica; il valore 7 viene normalizzato a 0.
    """
    check_hi = 7 if dow else hi
    values = set()
    for part in field.split(","):
        if part == "":
            raise ValueError("token vuoto nel campo %s" % name)
        step = 1
        if "/" in part:
            base, sep, step_s = part.partition("/")
            if step_s == "":
                raise ValueError("step vuoto nel campo %s" % name)
            try:
                step = int(step_s)
            except ValueError:
                raise ValueError(
                    "step non numerico nel campo %s: %r" % (name, step_s)
                )
            if step <= 0:
                raise ValueError("step <= 0 nel campo %s" % name)
        else:
            base = part
        if base == "*":
            start, end = lo, hi
        elif "-" in base:
            a, sep, b = base.partition("-")
            if a == "" or b == "":
                raise ValueError("intervallo vuoto nel campo %s" % name)
            try:
                start = int(a)
                end = int(b)
            except ValueError:
                raise ValueError(
                    "intervallo non numerico nel campo %s: %r" % (name, base)
                )
            if start > end:
                raise ValueError(
                    "intervallo con a>b nel campo %s: %r" % (name, base)
                )
        else:
            try:
                start = int(base)
            except ValueError:
                raise ValueError(
                    "token non numerico nel campo %s: %r" % (name, base)
                )
            end = start
        if start < lo or end > check_hi:
            raise ValueError(
                "valore fuori range nel campo %s: %r" % (name, base)
            )
        for v in range(start, end + 1, step):
            values.add(0 if (dow and v == 7) else v)
    return values


def parse_cron(expr):
    """Restituisce i 5 insiemi di valori validi (minuto, ora, giorno_mese,
    mese, giorno_settimana) per l'espressione cron data.

    Solleva ValueError per espressioni non valide.
    """
    if not isinstance(expr, str):
        raise ValueError("expr non stringa")
    fields = expr.split()
    if len(fields) != 5:
        raise ValueError("numero di campi diverso da 5")
    sets = []
    for i, (field, (lo, hi, name)) in enumerate(zip(fields, _FIELD_SPECS)):
        sets.append(_parse_field(field, lo, hi, name, dow=(i == 4)))
    return sets


def _day_matches(sets, day):
    """Verifica la corrispondenza del giorno secondo la regola OR di Vixie.

    ``day`` e' un ``datetime.date``.
    """
    dom_ok = day.day in sets[2]
    dow_ok = ((day.weekday() + 1) % 7) in sets[4]
    dom_restricted = len(sets[2]) < 31
    dow_restricted = len(sets[4]) < 7
    if dom_restricted and dow_restricted:
        return dom_ok or dow_ok
    if dom_restricted:
        return dom_ok
    if dow_restricted:
        return dow_ok
    return True


def _impossible(sets):
    """True se l'espressione non puo' mai scattare (giorno mai soddisfabile)."""
    if len(sets[0]) == 0 or len(sets[1]) == 0 or len(sets[3]) == 0:
        return True
    dom = sets[2]
    dow = sets[4]
    dom_restricted = len(dom) < 31
    dow_restricted = len(dow) < 7
    if dom_restricted and dow_restricted:
        # regola OR: impossibile solo se entrambi i campi sono vuoti
        return len(dom) == 0 and len(dow) == 0
    if dom_restricted:
        return len(dom) == 0
    if dow_restricted:
        return len(dow) == 0
    return False


def next_runs(expr, start_dt, count=5):
    """Restituisce i prossimi ``count`` datetime UTC strettamente successivi
    a ``start_dt`` per l'espressione cron ``expr``.

    I datetime restituiti sono timezone-aware in UTC (tzinfo=timezone.utc),
    con secondi e microsecondi a 0, in ordine crescente.

    Se ``start_dt`` e' naive viene trattato come UTC; se e' aware viene
    convertito in UTC.

    ``count`` deve essere un intero >= 1, altrimenti ValueError.
    """
    if not isinstance(count, int) or isinstance(count, bool):
        raise ValueError("count deve essere un intero")
    if count < 1:
        raise ValueError("count deve essere >= 1")

    sets = parse_cron(expr)
    if _impossible(sets):
        raise ValueError("espressione cron che non puo' mai scattare")

    if start_dt.tzinfo is None:
        start = start_dt.replace(tzinfo=timezone.utc)
    else:
        start = start_dt.astimezone(timezone.utc)

    hours = sorted(sets[1])
    minutes = sorted(sets[0])

    results = []
    day = start.date()
    limit = _SEARCH_LIMIT_DAYS
    while len(results) < count:
        if (day - start.date()).days > limit:
            raise ValueError("espressione cron che non puo' mai scattare")
        if day.month in sets[3] and _day_matches(sets, day):
            for h in hours:
                for m in minutes:
                    dt = datetime(
                        day.year, day.month, day.day, h, m,
                        tzinfo=timezone.utc,
                    )
                    if dt > start:
                        results.append(dt)
                        if len(results) >= count:
                            break
                if len(results) >= count:
                    break
        day += timedelta(days=1)
    return results
