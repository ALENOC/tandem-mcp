"""Parser and iterator for standard 5-field cron expressions.

Fields, in order: minute (0-59), hour (0-23), day-of-month (1-31),
month (1-12), day-of-week (0-6, 0=Sunday, 7 also accepted as Sunday).

Each field supports: ``*``, a single number, a range ``a-b``, a list
``a,b,c`` (elements may be ranges or steps), a step ``*/n`` and a ranged
step ``a-b/n``.

Public API:
    parse(expr) -> tuple of 5 sets of allowed values
    next_runs(expr, start_dt, count=5) -> list of UTC datetimes
"""

from datetime import datetime, timedelta, timezone

# (name, low, high) for each of the five fields, in order.
_FIELDS = (
    ("minute", 0, 59),
    ("hour", 0, 23),
    ("day_of_month", 1, 31),
    ("month", 1, 12),
    ("day_of_week", 0, 7),
)

# Safety bound for the search: never look further than 10 years ahead.
_MAX_SEARCH_YEARS = 10
_MAX_YEAR = 9999


def _parse_int(token, field):
    token = token.strip()
    if not token:
        raise ValueError("empty token in field %s" % field)
    if token.startswith("+"):
        token = token[1:]
    if not token.isdigit():
        raise ValueError("non numeric token %r in field %s" % (token, field))
    return int(token)


def _parse_value(token, field, low, high):
    value = _parse_int(token, field)
    if value < low or value > high:
        raise ValueError(
            "value %d out of range [%d, %d] in field %s" % (value, low, high, field)
        )
    return value


def _parse_field(field, low, high, raw):
    """Return the set of allowed integer values for one cron field."""
    raw = raw.strip()
    if not raw:
        raise ValueError("empty field %s" % field)
    values = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            raise ValueError("empty element in field %s" % field)
        step = 1
        if "/" in part:
            base, sep, step_text = part.partition("/")
            step = _parse_int(step_text, field)
            if step == 0:
                raise ValueError("step 0 in field %s" % field)
        else:
            base = part
        if base == "*":
            start, end = low, high
        elif "-" in base:
            a, sep, b = base.partition("-")
            start = _parse_value(a, field, low, high)
            end = _parse_value(b, field, low, high)
            if start > end:
                raise ValueError("interval a>b in field %s" % field)
        else:
            start = _parse_value(base, field, low, high)
            if "/" in part:
                end = high
            else:
                end = start
        values.update(range(start, end + 1, step))
    return values


def parse(expr):
    """Parse a 5-field cron expression.

    Returns a tuple of 5 sets (minute, hour, day_of_month, month,
    day_of_week) holding the allowed integer values for each field.
    """
    if not isinstance(expr, str):
        raise ValueError("cron expression must be a string")
    fields = expr.split()
    if len(fields) != 5:
        raise ValueError("cron expression must have exactly 5 fields")
    sets = []
    for (name, low, high), raw in zip(_FIELDS, fields):
        sets.append(_parse_field(name, low, high, raw))
    # day_of_week: 7 is accepted as Sunday (0).
    if 7 in sets[4]:
        sets[4].discard(7)
        sets[4].add(0)
    return tuple(sets)


def _restricted(expr):
    """Return (dom_restricted, dow_restricted) for a 5-field cron expression.

    A field is restricted when its raw text is not exactly '*'.
    """
    fields = expr.split()
    return fields[2].strip() != "*", fields[4].strip() != "*"


def _normalize_start(start_dt):
    """Return start_dt as an aware UTC datetime (naive is treated as UTC)."""
    if not isinstance(start_dt, datetime):
        raise ValueError("start_dt must be a datetime")
    if start_dt.tzinfo is None:
        return start_dt.replace(tzinfo=timezone.utc)
    return start_dt.astimezone(timezone.utc)


def _day_matches(dom_set, dow_set, date, dom_restricted, dow_restricted):
    """Day matching for this scheduler.

    When both day-of-month and day-of-week are restricted (not '*'), a date
    matches if it satisfies at least one of them (standard cron OR rule). Otherwise only the restricted
    field applies (an unrestricted field is the full set).
    """
    dom_ok = date.day in dom_set
    # Convert Python weekday (Mon=0..Sun=6) to cron dow (Sun=0..Sat=6).
    cron_dow = (date.weekday() + 1) % 7
    dow_ok = cron_dow in dow_set
    if dom_restricted and dow_restricted:
        return dom_ok or dow_ok
    if dom_restricted:
        return dom_ok
    if dow_restricted:
        return dow_ok
    return True


def next_runs(expr, start_dt, count=5):
    """Return the next ``count`` matching UTC datetimes, strictly after start_dt."""
    if not isinstance(count, int) or isinstance(count, bool) or count < 1:
        raise ValueError("count must be a positive integer")
    minutes, hours, dom_set, months, dow_set = parse(expr)
    dom_restricted, dow_restricted = _restricted(expr)
    start = _normalize_start(start_dt)
    results = []
    cursor = start.replace(hour=0, minute=0, second=0, microsecond=0)
    # Search limit: a few years beyond the start date.
    if start.year + _MAX_SEARCH_YEARS > _MAX_YEAR:
        max_year = _MAX_YEAR
    else:
        max_year = start.year + _MAX_SEARCH_YEARS
    while cursor.year <= max_year and len(results) < count:
        if cursor.month not in months:
            # Jump to the first day of the next month.
            if cursor.month == 12:
                cursor = datetime(cursor.year + 1, 1, 1, tzinfo=timezone.utc)
            else:
                cursor = datetime(cursor.year, cursor.month + 1, 1, tzinfo=timezone.utc)
            continue
        if not _day_matches(dom_set, dow_set, cursor, dom_restricted, dow_restricted):
            cursor = (cursor + timedelta(days=1)).replace(hour=0, minute=0)
            continue
        for hour in sorted(hours):
            for minute in sorted(minutes):
                candidate = datetime(
                    cursor.year, cursor.month, cursor.day,
                    hour, minute, tzinfo=timezone.utc,
                )
                if candidate > start:
                    results.append(candidate)
                    if len(results) >= count:
                        break
            if len(results) >= count:
                break
        cursor = (cursor + timedelta(days=1)).replace(hour=0, minute=0)
    if len(results) < count:
        raise ValueError("no valid dates found within search limit")
    return results
