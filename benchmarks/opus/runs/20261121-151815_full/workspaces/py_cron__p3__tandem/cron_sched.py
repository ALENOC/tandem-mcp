"""Parser and iterator for 5-field cron expressions.

A cron expression has five whitespace separated fields:

    minute hour day_of_month month day_of_week

Each field may be ``*``, a number, a range ``a-b``, a list ``a,b,c`` whose
items may themselves be any of the other forms, a step ``*/n`` or a range
step ``a-b/n``.
"""

from datetime import datetime, timedelta, timezone

# (min, max) bounds for each of the five fields, in order.
_FIELD_BOUNDS = (
    (0, 59),   # minute
    (0, 23),   # hour
    (1, 31),   # day of month
    (1, 12),   # month
    (0, 7),    # day of week (0 and 7 are both Sunday)
)

# How far ahead (in years) to search before giving up on an expression that
# can never match.  Eight years covers every leap-year alignment.
_MAX_YEARS = 8


class CronSpec:
    """Parsed cron expression: the five allowed sets plus the raw fields."""

    __slots__ = ("minutes", "hours", "dom", "months", "dow", "dom_star", "dow_star")

    def __init__(self, minutes, hours, dom, months, dow, dom_star, dow_star):
        self.minutes = minutes
        self.hours = hours
        self.dom = dom
        self.months = months
        self.dow = dow
        self.dom_star = dom_star
        self.dow_star = dow_star

    def __eq__(self, other):
        if not isinstance(other, CronSpec):
            return NotImplemented
        return (
            self.minutes == other.minutes
            and self.hours == other.hours
            and self.dom == other.dom
            and self.months == other.months
            and self.dow == other.dow
            and self.dom_star == other.dom_star
            and self.dow_star == other.dow_star
        )

    def __repr__(self):
        return (
            "CronSpec(minutes=%r, hours=%r, dom=%r, months=%r, dow=%r, "
            "dom_star=%r, dow_star=%r)"
            % (
                self.minutes,
                self.hours,
                self.dom,
                self.months,
                self.dow,
                self.dom_star,
                self.dow_star,
            )
        )


def _parse_field(field, lo, hi, name):
    """Parse one cron field into a set of allowed integers.

    ``lo``/``hi`` are the inclusive bounds.  ``name`` is only used to build
    readable error messages.
    """
    if field == "":
        raise ValueError("empty %s field" % name)
    values = set()
    for item in field.split(","):
        if item == "":
            raise ValueError("empty item in %s field" % name)
        values |= _parse_item(item, lo, hi, name)
    return values


def _parse_item(item, lo, hi, name):
    """Parse a single list item (no commas) into a set of integers."""
    step = 1
    base = item
    if "/" in item:
        base, sep, step_text = item.partition("/")
        if sep == "":
            raise ValueError("empty step in %s field" % name)
        step = _parse_int(step_text, name)
        if step <= 0:
            raise ValueError("step must be positive in %s field" % name)
    if base == "*":
        start, end = lo, hi
    elif "-" in base:
        a, sep, b = base.partition("-")
        if sep == "":
            raise ValueError("malformed range in %s field" % name)
        start = _parse_int(a, name)
        end = _parse_int(b, name)
        if start > end:
            raise ValueError("range start greater than end in %s field" % name)
    else:
        start = _parse_int(base, name)
        end = start
    if start < lo or end > hi:
        raise ValueError("value out of range in %s field" % name)
    return set(range(start, end + 1, step))


def _parse_int(text, name):
    """Parse a non-negative integer, rejecting anything non numeric."""
    if text == "":
        raise ValueError("empty value in %s field" % name)
    if not all(c in "0123456789" for c in text):
        raise ValueError("non numeric value in %s field" % name)
    return int(text)


def parse(expr):
    """Parse a 5-field cron expression into a :class:`CronSpec`.

    Returns a :class:`CronSpec` whose attributes ``minutes``, ``hours``,
    ``dom``, ``months`` and ``dow`` are the sets of allowed integers.  The
    day of week set is normalized so that ``7`` becomes ``0`` (Sunday).
    """
    if not isinstance(expr, str):
        raise ValueError("cron expression must be a string")
    fields = expr.split()
    if len(fields) != 5:
        raise ValueError("cron expression must have exactly 5 fields")
    sets = []
    for field, (lo, hi), name in zip(fields, _FIELD_BOUNDS,
                                     ("minute", "hour", "day_of_month",
                                      "month", "day_of_week")):
        sets.append(_parse_field(field, lo, hi, name))
    minutes, hours, dom, months, dow = sets
    dow = {0 if v == 7 else v for v in dow}
    dom_star = fields[2] == "*"
    dow_star = fields[4] == "*"
    return CronSpec(minutes, hours, dom, months, dow, dom_star, dow_star)


def _day_matches(spec, dt):
    """Return True when ``dt``'s day satisfies the dom/dow rule."""
    dom_ok = dt.day in spec.dom
    dow_ok = (dt.weekday() + 1) % 7 in spec.dow
    if spec.dom_star and spec.dow_star:
        return True
    if spec.dom_star:
        return dow_ok
    if spec.dow_star:
        return dom_ok
    return dom_ok or dow_ok


def next_runs(expr, start_dt, count=5):
    """Return the next ``count`` UTC datetimes matching ``expr``.

    The returned datetimes are timezone aware (UTC), have zero seconds and
    microseconds, are strictly after ``start_dt`` and in ascending order.
    """
    if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
        raise ValueError("count must be a positive integer")
    if not isinstance(start_dt, datetime):
        raise ValueError("start_dt must be a datetime")
    if start_dt.tzinfo is None:
        start = start_dt.replace(tzinfo=timezone.utc)
    else:
        start = start_dt.astimezone(timezone.utc)
    spec = parse(expr)

    # Begin at the first whole minute strictly after ``start``.
    cursor = start.replace(second=0, microsecond=0) + timedelta(minutes=1)
    results = []
    limit = start + timedelta(days=366 * _MAX_YEARS)
    while len(results) < count:
        if cursor > limit:
            raise ValueError("expression never matches within %d years" % _MAX_YEARS)
        if cursor.month not in spec.months:
            cursor = _advance_month(cursor)
            continue
        if not _day_matches(spec, cursor):
            cursor = _advance_day(cursor)
            continue
        if cursor.hour not in spec.hours:
            cursor = _advance_hour(cursor)
            continue
        if cursor.minute not in spec.minutes:
            cursor = _advance_minute(cursor)
            continue
        results.append(cursor)
        cursor += timedelta(minutes=1)
    return results


def _advance_month(dt):
    """First instant of the next month, zeroed to the minute."""
    if dt.month == 12:
        return datetime(dt.year + 1, 1, 1, tzinfo=dt.tzinfo)
    return datetime(dt.year, dt.month + 1, 1, tzinfo=dt.tzinfo)


def _advance_day(dt):
    """First instant of the next day, zeroed to the minute."""
    return (dt + timedelta(days=1)).replace(hour=0, minute=0)


def _advance_hour(dt):
    """First instant of the next hour, zeroed to the minute."""
    return (dt + timedelta(hours=1)).replace(minute=0)


def _advance_minute(dt):
    """The next whole minute."""
    return dt + timedelta(minutes=1)
