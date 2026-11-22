"""Parser and iterator for 5-field cron expressions.

Fields are: minute hour day_of_month month day_of_week.
Day of week uses 0-6 with 0 = Sunday.
"""

import calendar
from datetime import datetime, timedelta, timezone

# (min, max) inclusive bounds for each of the five fields, in order.
_FIELD_BOUNDS = [
    (0, 59),   # minute
    (0, 23),   # hour
    (1, 31),   # day of month
    (1, 12),   # month
    (0, 6),    # day of week (0 = Sunday)
]

# How far ahead (in days) to search before declaring an expression
# that can never match.  A little over five years.
_MAX_SEARCH_DAYS = 5 * 366 + 30


class CronExpr:
    """A parsed cron expression.

    Attributes ``minute``, ``hour``, ``dom``, ``month`` and ``dow`` hold the
    sets of allowed integer values for each field.  ``dom_star`` and
    ``dow_star`` record whether the raw field was a bare ``*`` (unrestricted),
    which drives the Vixie day-matching rule.
    """

    def __init__(self, minute, hour, dom, month, dow, dom_star, dow_star):
        self.minute = minute
        self.hour = hour
        self.dom = dom
        self.month = month
        self.dow = dow
        self.dom_star = dom_star
        self.dow_star = dow_star


def _parse_field(field, lo, hi, name):
    """Parse one cron field into a set of allowed integers.

    Supports ``*``, ``n``, ``a-b``, ``a,b,c`` (items may be any of the other
    forms), ``*/n`` and ``a-b/n``.  Raises ValueError on any malformed input.
    """
    values = set()
    for item in field.split(','):
        if item == '':
            raise ValueError('empty list item in %s field: %r' % (name, field))
        base = item
        step = 1
        if '/' in item:
            base, sep, step_s = item.partition('/')
            if step_s == '':
                raise ValueError('missing step value in %s field: %r' % (name, item))
            if not step_s.isdigit():
                raise ValueError('non-numeric step in %s field: %r' % (name, item))
            step = int(step_s)
            if step <= 0:
                raise ValueError('step must be positive in %s field: %r' % (name, item))
        if base == '*':
            start, end = lo, hi
        elif '-' in base:
            a, sep, b = base.partition('-')
            if not a.isdigit() or not b.isdigit():
                raise ValueError('non-numeric range in %s field: %r' % (name, item))
            start, end = int(a), int(b)
            if start > end:
                raise ValueError('range start > end in %s field: %r' % (name, item))
        elif base.isdigit():
            start = end = int(base)
        else:
            raise ValueError('non-numeric token in %s field: %r' % (name, item))
        if start < lo or end > hi:
            raise ValueError('value out of range %d-%d in %s field: %r' % (lo, hi, name, item))
        values.update(range(start, end + 1, step))
    return values


def parse(expr):
    """Parse a 5-field cron expression string into a :class:`CronExpr`.

    Raises ValueError for a non-string, the wrong number of fields, or any
    malformed field.
    """
    if not isinstance(expr, str):
        raise ValueError('cron expression must be a string')
    fields = expr.split()
    if len(fields) != 5:
        raise ValueError('cron expression must have exactly 5 fields, got %d' % len(fields))
    names = ['minute', 'hour', 'day_of_month', 'month', 'day_of_week']
    sets = []
    for field, (lo, hi), name in zip(fields, _FIELD_BOUNDS, names):
        sets.append(_parse_field(field, lo, hi, name))
    minute, hour, dom, month, dow = sets
    return CronExpr(minute, hour, dom, month, dow,
                    dom_star=(fields[2] == '*'), dow_star=(fields[4] == '*'))


def _day_matches(expr, dt):
    """Vixie day rule: if both DOM and DOW are restricted, either may match."""
    dom_ok = dt.day in expr.dom
    # Cron DOW uses 0=Sunday..6=Saturday; Python weekday() uses 0=Monday..6=Sunday.
    cron_dow = (dt.weekday() + 1) % 7
    dow_ok = cron_dow in expr.dow
    if expr.dom_star and expr.dow_star:
        return True
    if expr.dom_star:
        return dow_ok
    if expr.dow_star:
        return dom_ok
    return dom_ok or dow_ok


def next_runs(expr, start_dt, count=5):
    """Return the next ``count`` UTC datetimes strictly after ``start_dt``.

    ``expr`` may be a cron expression string or a :class:`CronExpr`.  A naive
    ``start_dt`` is treated as UTC; an aware one is converted to UTC first.
    Raises ValueError if ``count <= 0`` or the expression can never match.
    """
    if not isinstance(count, int) or isinstance(count, bool):
        raise ValueError('count must be an integer')
    if count <= 0:
        raise ValueError('count must be a positive integer')
    if isinstance(expr, CronExpr):
        ce = expr
    else:
        ce = parse(expr)
    if start_dt.tzinfo is None:
        start = start_dt.replace(tzinfo=timezone.utc)
    else:
        start = start_dt.astimezone(timezone.utc)
    start = start.replace(second=0, microsecond=0)

    hours = sorted(ce.hour)
    minutes = sorted(ce.minute)
    if not hours or not minutes:
        raise ValueError('cron expression can never match')

    # Candidate days: the first matching day at or after the start day, then
    # every following day.  We skip whole days that cannot match instead of
    # stepping minute by minute.
    day = start.date()
    skipped = 0
    while not (day.month in ce.month and _day_matches(ce, datetime(day.year, day.month, day.day))):
        day += timedelta(days=1)
        skipped += 1
        if skipped > _MAX_SEARCH_DAYS:
            raise ValueError('cron expression can never match (search bounded)')

    results = []
    searched = 0
    while len(results) < count:
        if searched > _MAX_SEARCH_DAYS:
            raise ValueError('cron expression can never match (search bounded)')
        if day.month in ce.month and _day_matches(ce, datetime(day.year, day.month, day.day)):
            for h in hours:
                for m in minutes:
                    cand = datetime(day.year, day.month, day.day, h, m, tzinfo=timezone.utc)
                    if cand > start:
                        results.append(cand)
                        if len(results) >= count:
                            break
                if len(results) >= count:
                    break
        day += timedelta(days=1)
        searched += 1
    return results
