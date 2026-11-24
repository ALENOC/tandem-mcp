"""Parser and iterator for 5-field cron expressions.

Fields (in order): minute, hour, day-of-month, month, day-of-week.

Supported syntax per field:
  *            any value
  n            a single value
  a-b          an inclusive range
  a,b,c        a list (elements may be ranges or steps)
  */n          step over the whole field
  a-b/n        step over a range

Only the Python standard library is used.
"""

from datetime import datetime, timedelta, timezone

__all__ = ["parse", "next_runs", "CronExpr"]

# (min, max) bounds for each of the five fields, in order.
_BOUNDS = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 7)]
_NAMES = ["minute", "hour", "day-of-month", "month", "day-of-week"]


class CronExpr:
    """A parsed cron expression.

    Attributes:
        minutes, hours, days, months, weekdays: sets of integers.
        weekdays is normalised to 0-6 (7 becomes 0).
        dom_restricted / dow_restricted: whether the corresponding field
            is anything other than '*'.
    """

    def __init__(self, minutes, hours, days, months, weekdays,
                 dom_restricted, dow_restricted):
        self.minutes = minutes
        self.hours = hours
        self.days = days
        self.months = months
        self.weekdays = weekdays
        self.dom_restricted = dom_restricted
        self.dow_restricted = dow_restricted

    def __repr__(self):
        return ("CronExpr(minutes=%r, hours=%r, days=%r, months=%r, "
                "weekdays=%r)" % (self.minutes, self.hours, self.days,
                                   self.months, self.weekdays))


def _parse_int(token, field):
    token = token.strip()
    if not token:
        raise ValueError("empty token in %s field" % field)
    if token[0] in "+-":
        body = token[1:]
    else:
        body = token
    if not body.isdigit():
        raise ValueError("non-numeric token %r in %s field" % (token, field))
    return int(token)


def _parse_field(spec, lo, hi, field):
    """Parse one cron field into a set of integers.

    Returns (values, restricted) where restricted is False only when the
    whole field is '*'.
    """
    spec = spec.strip()
    if spec == "":
        raise ValueError("empty %s field" % field)
    if spec == "*":
        return set(range(lo, hi + 1)), False

    values = set()
    for part in spec.split(","):
        part = part.strip()
        if part == "":
            raise ValueError("empty element in %s field" % field)
        values |= _parse_element(part, lo, hi, field)
    return values, True


def _parse_element(part, lo, hi, field):
    if "/" in part:
        base, sep, step = part.partition("/")
        step = _parse_int(step, field)
        if step <= 0:
            raise ValueError("step must be positive in %s field" % field)
    else:
        base = part
        step = 1

    if base == "*":
        start, end = lo, hi
    elif "-" in base:
        a, sep, b = base.partition("-")
        start = _parse_int(a, field)
        end = _parse_int(b, field)
        if start > end:
            raise ValueError("range start > end in %s field" % field)
    else:
        start = _parse_int(base, field)
        end = start

    if start < lo or end > hi:
        raise ValueError("value out of range in %s field" % field)
    return set(range(start, end + 1, step))


def parse(expr):
    """Parse a 5-field cron expression into a CronExpr.

    Raises ValueError for any malformed expression.
    """
    if not isinstance(expr, str):
        raise ValueError("cron expression must be a string")
    fields = expr.split()
    if len(fields) != 5:
        raise ValueError("cron expression must have exactly 5 fields")

    minutes, m_r = _parse_field(fields[0], *_BOUNDS[0], _NAMES[0])
    hours, h_r = _parse_field(fields[1], *_BOUNDS[1], _NAMES[1])
    days, d_r = _parse_field(fields[2], *_BOUNDS[2], _NAMES[2])
    months, mo_r = _parse_field(fields[3], *_BOUNDS[3], _NAMES[3])
    weekdays, w_r = _parse_field(fields[4], *_BOUNDS[4], _NAMES[4])

    # Normalise weekday 7 (Sunday) to 0.
    if 7 in weekdays:
        weekdays.discard(7)
        weekdays.add(0)

    return CronExpr(minutes, hours, days, months, weekdays,
                    d_r, w_r)


def _day_matches(expr, dt):
    """Vixie rule: if both day-of-month and day-of-week are restricted the
    date matches when at least one of them matches; otherwise the restricted
    one (or the single one) must match."""
    dom_ok = dt.day in expr.days
    dow_ok = ((dt.weekday() + 1) % 7) in expr.weekdays
    if expr.dom_restricted and expr.dow_restricted:
        return dom_ok or dow_ok
    if expr.dom_restricted:
        return dom_ok
    if expr.dow_restricted:
        return dow_ok
    return True


def _next_occurrence(expr, start):
    """Return the first matching datetime strictly after ``start`` (a naive
    UTC datetime), or None if none exists within the search horizon."""
    # Search horizon: at least 9 years so that e.g. '0 0 29 2 *' (every 4
    # years) is found, while impossible expressions such as '0 0 30 2 *'
    # terminate with a ValueError instead of looping forever.
    horizon = start + timedelta(days=366 * 9)

    cur = start.replace(second=0, microsecond=0) + timedelta(minutes=1)
    while cur <= horizon:
        if cur.month not in expr.months:
            if cur.month == 12:
                cur = datetime(cur.year + 1, 1, 1)
            else:
                cur = datetime(cur.year, cur.month + 1, 1)
            continue
        if not _day_matches(expr, cur):
            cur = datetime(cur.year, cur.month, cur.day) + timedelta(days=1)
            continue
        if cur.hour not in expr.hours:
            cur = cur.replace(minute=0) + timedelta(hours=1)
            continue
        if cur.minute not in expr.minutes:
            cur = cur + timedelta(minutes=1)
            continue
        return cur
    return None


def next_runs(expr, start_dt, count=5):
    """Return the next ``count`` occurrences of ``expr`` strictly after
    ``start_dt`` as timezone-aware UTC datetimes (seconds and microseconds
    zeroed), in increasing order.

    A naive ``start_dt`` is interpreted as UTC; an aware one is converted
    to UTC. Raises ValueError for a malformed expression, a non-string
    expression, ``count < 1``, or an expression that never occurs.
    """
    if not isinstance(count, int) or isinstance(count, bool) or count < 1:
        raise ValueError("count must be a positive integer")
    parsed = parse(expr)
    if not isinstance(start_dt, datetime):
        raise ValueError("start_dt must be a datetime")

    if start_dt.tzinfo is None:
        start = start_dt.replace(tzinfo=None)
    else:
        start = start_dt.astimezone(timezone.utc).replace(tzinfo=None)

    results = []
    cur = start
    for _ in range(count):
        nxt = _next_occurrence(parsed, cur)
        if nxt is None:
            raise ValueError("cron expression never occurs")
        results.append(nxt.replace(tzinfo=timezone.utc))
        cur = nxt
    return results
