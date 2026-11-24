"""Parser e iteratore di espressioni cron a 5 campi.

Le espressioni seguono la sintassi classica di Vixie cron con cinque campi
posizionali separati da uno o piu' caratteri di whitespace:

    minuto  ora  giorno_mese  mese  giorno_settimana

Ogni campo ammette: ``*``, numeri interi, intervalli ``a-b``, liste separate
da virgola ``a,b,c`` e passi ``*/n``, ``a-b/n``, ``N/n`` (da ``N`` fino al
massimo del campo con passo ``n``).

I giorni della settimana vanno da 0 a 7 dove sia 0 che 7 indicano domenica
(il 7 viene normalizzato a 0), 1 = lunedi' ... 6 = sabato.

La semantica dei giorni segue Vixie cron: se sia ``giorno_mese`` sia
``giorno_settimana`` sono ristretti (cioe' non sono ``*`` semplice), una data
corrisponde se soddisfa ALMENO UNO dei due; se uno dei due e' ``*`` semplice
vale solo l'altro.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

__all__ = ["CronExpr", "parse", "next_runs"]

# (nome_campo, minimo, massimo) nell'ordine dei cinque campi.
_FIELDS = (
    ("minuto", 0, 59),
    ("ora", 0, 23),
    ("giorno_mese", 1, 31),
    ("mese", 1, 12),
    ("giorno_settimana", 0, 7),
)

# Numero massimo di anni da scandagliare alla ricerca di un'occorrenza prima
# di dichiarare un'espressione impossibile.
_MAX_YEARS = 10


class CronExpr:
    """Espressione cron a 5 campi gia' analizzata.

    Attributi (ciascuno ``frozenset`` di ``int``):

    * ``minutes``   minuti validi (0-59)
    * ``hours``     ore valide (0-23)
    * ``days``      giorni del mese validi (1-31)
    * ``months``    mesi validi (1-12)
    * ``weekdays``  giorni della settimana validi (0-6, domenica = 0)

    I flag ``dom_restricted`` e ``dow_restricted`` indicano se i campi
    ``giorno_mese`` e ``giorno_settimana`` sono ristretti (non ``*``
    semplice) e servono per la semantica OR dei giorni.
    """

    def __init__(self, minutes, hours, days, months, weekdays,
                 dom_restricted, dow_restricted):
        self.minutes = frozenset(minutes)
        self.hours = frozenset(hours)
        self.days = frozenset(days)
        self.months = frozenset(months)
        self.weekdays = frozenset(weekdays)
        self.dom_restricted = dom_restricted
        self.dow_restricted = dow_restricted

    def _day_matches(self, dt):
        """Restituisce True se il giorno della data ``dt`` e' ammesso.

        Applica la semantica OR di Vixie cron tra ``giorno_mese`` e
        ``giorno_settimana``.
        """
        dom_ok = dt.day in self.days
        dow_ok = ((dt.weekday() + 1) % 7) in self.weekdays
        if self.dom_restricted and self.dow_restricted:
            return dom_ok or dow_ok
        if self.dom_restricted:
            return dom_ok
        if self.dow_restricted:
            return dow_ok
        return True

    def iter(self, start_dt):
        """Generatore infinito dei datetime UTC successivi a ``start_dt``.

        I datetime restituiti sono ``aware`` (``tzinfo=timezone.utc``), con
        secondi e microsecondi a zero, strettamente maggiori di ``start_dt``
        e in ordine crescente.
        """
        cur = _to_utc(start_dt)
        # Il primo candidato e' il minuto successivo a start_dt, con secondi
        # e microsecondi azzerati: e' sempre strettamente maggiore di start_dt.
        cur = cur.replace(second=0, microsecond=0) + timedelta(minutes=1)
        while True:
            if cur.month not in self.months:
                cur = _advance_month(cur)
                continue
            if not self._day_matches(cur):
                cur = _advance_day(cur)
                continue
            if cur.hour not in self.hours:
                cur = _advance_hour(cur)
                continue
            if cur.minute not in self.minutes:
                cur = _advance_minute(cur)
                continue
            yield cur
            cur += timedelta(minutes=1)


def parse(expr):
    """Analizza l'espressione cron ``expr`` e restituisce un ``CronExpr``.

    Solleva ``ValueError`` se ``expr`` non e' una stringa, se il numero di
    campi non e' 5, se un valore e' fuori range, se un intervallo ha ``a > b``,
    se un passo e' <= 0 o non numerico, se un token non e' numerico (i nomi
    JAN/MON non sono supportati) o se sono presenti elementi vuoti, segni o
    spazi interni.
    """
    if not isinstance(expr, str):
        raise ValueError("l'espressione cron deve essere una stringa")
    fields = expr.split()
    if len(fields) != 5:
        raise ValueError(
            "sono attesi 5 campi separati da whitespace, ne sono stati "
            "trovati %d" % len(fields))
    minutes, hours, days, months, weekdays = [], [], [], [], []
    for idx, (field, (name, lo, hi)) in enumerate(zip(fields, _FIELDS)):
        values = _parse_field(field, name, lo, hi)
        if name == "giorno_settimana":
            values = [0 if v == 7 else v for v in values]
        if name == "minuto":
            minutes = values
        elif name == "ora":
            hours = values
        elif name == "giorno_mese":
            days = values
        elif name == "mese":
            months = values
        elif name == "giorno_settimana":
            weekdays = values
    dom_restricted = fields[2] != "*"
    dow_restricted = fields[4] != "*"
    return CronExpr(minutes, hours, days, months, weekdays,
                    dom_restricted, dow_restricted)


def next_runs(expr, start_dt, count=5):
    """Restituisce i prossimi ``count`` datetime UTC successivi a ``start_dt``.

    ``expr`` e' un'espressione cron a 5 campi (stringa o ``CronExpr``).
    ``start_dt`` puo' essere naive (interpretato come UTC) o aware (convertito
    in UTC). ``count`` deve essere un intero non negativo.

    Solleva ``ValueError`` se ``count`` e' negativo o non intero, se
    l'espressione e' non valida o se un'espressione sintatticamente valida non
    produce alcuna occorrenza entro 10 anni da ``start_dt``.
    """
    if isinstance(count, bool) or not isinstance(count, int):
        raise ValueError("count deve essere un intero")
    if count < 0:
        raise ValueError("count non puo' essere negativo")
    if count == 0:
        return []
    if isinstance(expr, CronExpr):
        cron = expr
    else:
        cron = parse(expr)
    start = _to_utc(start_dt)
    results = []
    gen = cron.iter(start)
    deadline = start + timedelta(days=365 * _MAX_YEARS)
    for dt in gen:
        if dt > deadline:
            raise ValueError(
                "espressione cron senza occorrenze entro %d anni da "
                "start_dt" % _MAX_YEARS)
        results.append(dt)
        if len(results) == count:
            break
    return results


def _parse_field(field, name, lo, hi):
    """Analizza un singolo campo cron e restituisce la lista di valori.

    ``name`` e' il nome del campo (per i messaggi d'errore), ``lo`` e ``hi``
    i limiti del range. Solleva ``ValueError`` per ogni token non valido.
    """
    values = set()
    for element in field.split(","):
        if element == "":
            raise ValueError(
                "campo %s: elemento vuoto nella lista" % name)
        values.update(_parse_element(element, name, lo, hi))
    return sorted(values)


def _parse_element(element, name, lo, hi):
    """Analizza un elemento di lista (senza virgole) e restituisce i valori.

    Gestisce ``*``, ``N``, ``a-b``, ``*/n``, ``a-b/n`` e ``N/n``.
    """
    step = 1
    has_step = False
    if "/" in element:
        base, sep, step_text = element.partition("/")
        if not sep:
            raise ValueError(
                "campo %s: passo mancante nel token %r" % (name, element))
        if step_text == "":
            raise ValueError(
                "campo %s: passo vuoto nel token %r" % (name, element))
        step = _to_int(step_text, name, element)
        if step <= 0:
            raise ValueError(
                "campo %s: passo non valido %r (deve essere > 0)"
                % (name, element))
        has_step = True
    else:
        base = element
    if base == "*":
        start, end = lo, hi
    elif "-" in base:
        a, sep, b = base.partition("-")
        if not sep:
            raise ValueError(
                "campo %s: intervallo non valido %r" % (name, element))
        if a == "" or b == "":
            raise ValueError(
                "campo %s: intervallo vuoto %r" % (name, element))
        start = _to_int(a, name, element)
        end = _to_int(b, name, element)
        if start > end:
            raise ValueError(
                "campo %s: intervallo invertito %r (inizio > fine)"
                % (name, element))
    else:
        start = _to_int(base, name, element)
        # Un numero semplice vale solo se stesso; con passo (N/n) va da N
        # fino al massimo del campo.
        end = hi if has_step else start
    if start < lo or start > hi or end < lo or end > hi:
        raise ValueError(
            "campo %s: valore fuori range %d-%d nel token %r"
            % (name, lo, hi, element))
    return list(range(start, end + 1, step))


def _to_int(text, name, element):
    """Converte ``text`` in intero, sollevando ``ValueError`` se non valido."""
    try:
        return int(text)
    except ValueError:
        raise ValueError(
            "campo %s: token non numerico %r" % (name, element)) from None


def _to_utc(dt):
    """Converte ``dt`` in un datetime aware in UTC.

    Un datetime naive e' interpretato come UTC; un datetime aware viene
    convertito in UTC.
    """
    if not isinstance(dt, datetime):
        raise ValueError("start_dt deve essere un datetime")
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _advance_month(dt):
    """Restituisce il primo istante del mese successivo a ``dt``."""
    if dt.month == 12:
        return datetime(dt.year + 1, 1, 1, tzinfo=timezone.utc)
    return datetime(dt.year, dt.month + 1, 1, tzinfo=timezone.utc)


def _advance_day(dt):
    """Restituisce il primo istante del giorno successivo a ``dt``."""
    return (dt + timedelta(days=1)).replace(hour=0, minute=0)


def _advance_hour(dt):
    """Restituisce il primo istante dell'ora successiva a ``dt``."""
    return (dt + timedelta(hours=1)).replace(minute=0)


def _advance_minute(dt):
    """Restituisce il primo istante del minuto successivo a ``dt``."""
    return dt + timedelta(minutes=1)
