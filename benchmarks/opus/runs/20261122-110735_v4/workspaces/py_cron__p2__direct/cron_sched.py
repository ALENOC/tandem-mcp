"""Parser e iteratore di espressioni cron a 5 campi.

Campi: minuto, ora, giorno_mese, mese, giorno_settimana.
Sintassi supportata per ogni campo: ``*``, numeri, intervalli ``a-b``,
liste ``a,b,c``, step ``*/n`` e ``a-b/n`` (anche combinati in liste).

Giorno della settimana: 0-7, dove 0 e 7 indicano entrambi domenica.
Come nel cron classico, se sia giorno_mese sia giorno_settimana sono
ristretti (diversi da ``*``), un giorno corrisponde se soddisfa almeno uno
dei due (semantica OR).
"""

from datetime import datetime, timedelta, timezone

__all__ = ["CronExpr", "parse", "next_runs"]

# (nome, minimo, massimo)
_FIELDS = (
    ("minuto", 0, 59),
    ("ora", 0, 23),
    ("giorno_mese", 1, 31),
    ("mese", 1, 12),
    ("giorno_settimana", 0, 7),
)

# Limite di ricerca: oltre questo orizzonte l'espressione è considerata
# impossibile (es. "0 0 30 2 *"). 29 febbraio ricorre al massimo ogni 8 anni.
_MAX_SEARCH_DAYS = 366 * 30


def _parse_int(text, name):
    if not text or not text.isdigit():
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
            base, step_txt = part.split("/", 1)
            step = _parse_int(step_txt, name)
            if step <= 0:
                raise ValueError(f"step deve essere > 0 nel campo {name}")
            if base == "":
                raise ValueError(f"step senza base nel campo {name}")
        else:
            base, step = part, 1

        if base == "*":
            start, end = lo, hi
        elif "-" in base:
            a, b = base.split("-", 1)
            start, end = _parse_int(a, name), _parse_int(b, name)
            if start > end:
                raise ValueError(
                    f"intervallo {base!r} invertito nel campo {name}")
        else:
            start = _parse_int(base, name)
            # "a/n" non è nella sintassi richiesta: lo rifiutiamo.
            if "/" in part:
                raise ValueError(
                    f"step ammesso solo con '*' o 'a-b' nel campo {name}")
            end = start

        if start < lo or end > hi:
            raise ValueError(
                f"valore fuori intervallo [{lo}-{hi}] nel campo {name}: {part!r}")
        values.update(range(start, end + 1, step))
    return values, text == "*"


class CronExpr:
    """Espressione cron compilata."""

    def __init__(self, expr):
        if not isinstance(expr, str):
            raise ValueError("l'espressione cron deve essere una stringa")
        parts = expr.split()
        if len(parts) != 5:
            raise ValueError(
                f"attesi 5 campi, trovati {len(parts)}: {expr!r}")
        parsed = [
            _parse_field(p, name, lo, hi)
            for p, (name, lo, hi) in zip(parts, _FIELDS)
        ]
        self.expr = expr
        self.minutes = sorted(parsed[0][0])
        self.hours = sorted(parsed[1][0])
        self.days = parsed[2][0]
        self.months = parsed[3][0]
        dow = parsed[4][0]
        if 7 in dow:
            dow = (dow - {7}) | {0}
        self.weekdays = dow
        self._dom_star = parsed[2][1]
        self._dow_star = parsed[4][1]

    def __repr__(self):
        return f"CronExpr({self.expr!r})"

    def _day_matches(self, d):
        if d.month not in self.months:
            return False
        dom_ok = d.day in self.days
        # Python: lunedì=0 ... domenica=6; cron: domenica=0 ... sabato=6
        dow_ok = (d.weekday() + 1) % 7 in self.weekdays
        if self._dom_star and self._dow_star:
            return True
        if self._dom_star:
            return dow_ok
        if self._dow_star:
            return dom_ok
        return dom_ok or dow_ok

    def iter_after(self, start_dt):
        """Genera i datetime UTC (aware) strettamente successivi a start_dt.

        Un datetime naive è interpretato come UTC.
        """
        if not isinstance(start_dt, datetime):
            raise TypeError("start_dt deve essere un datetime")
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=timezone.utc)
        else:
            start_dt = start_dt.astimezone(timezone.utc)

        # Primo minuto candidato: il minuto intero successivo a start_dt.
        cur = start_dt.replace(second=0, microsecond=0) + timedelta(minutes=1)
        day = cur.date()
        first = True
        misses = 0
        while True:
            if self._day_matches(day):
                misses = 0
                for h in self.hours:
                    if first and h < cur.hour:
                        continue
                    for m in self.minutes:
                        if first and h == cur.hour and m < cur.minute:
                            continue
                        yield datetime(day.year, day.month, day.day, h, m,
                                       tzinfo=timezone.utc)
            else:
                misses += 1
                if misses > _MAX_SEARCH_DAYS:
                    raise ValueError(
                        f"l'espressione {self.expr!r} non produce mai esecuzioni")
            first = False
            try:
                day += timedelta(days=1)
            except OverflowError:
                return


def parse(expr):
    """Valida e compila un'espressione cron; solleva ValueError se non valida."""
    return CronExpr(expr)


def next_runs(expr, start_dt, count=5):
    """Restituisce i prossimi ``count`` datetime UTC successivi a start_dt.

    Solleva ValueError se l'espressione non è valida (o non produce mai
    esecuzioni) o se count è negativo.
    """
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ValueError("count deve essere un intero >= 0")
    cron = expr if isinstance(expr, CronExpr) else CronExpr(expr)
    result = []
    if count == 0:
        return result
    for dt in cron.iter_after(start_dt):
        result.append(dt)
        if len(result) == count:
            break
    return result
