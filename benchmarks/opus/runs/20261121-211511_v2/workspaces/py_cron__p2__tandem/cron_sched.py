"""Parser and iterator for 5-field cron expressions.

Fields: minute hour day_of_month month day_of_week
"""

import calendar
from datetime import datetime, timedelta, timezone

UTC = timezone.utc

# (min, max) bounds for each of the five fields, in order.
_BOUNDS = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 6)]
_NAMES = ["minute", "hour", "day_of_month", "month", "day_of_week"]

# How far ahead (in days) we are willing to search for a match.
_MAX_DAYS = 366 * 5 + 1


def _parse_int(token, field):
    token = token.strip()
    if not token:
        raise ValueError("empty value in %s field" % field)
    if token[0] in "+-":
        body = token[1:]
    else:
        body = token
    if not body.isdigit():
        raise ValueError("non-numeric value %r in %s field" % (token, field))
    return int(token)


def _parse_field(spec, lo, hi, name):
    """Parse one cron field into a sorted list of matching integers."""
    values = set()
    for item in spec.split(","):
        if item == "":
            raise ValueError("empty list item in %s field" % name)
        base = item
        step = 1
        if "/" in item:
            base, step_s = item.split("/", 1)
            step = _parse_int(step_s, name)
            if step <= 0:
                raise ValueError("step must be positive in %s field" % name)
        if base == "*":
            start, end = lo, hi
        elif "-" in base:
            a, b = base.split("-", 1)
            start = _parse_int(a, name)
            end = _parse_int(b, name)
            if start > end:
                raise ValueError("range start > end in %s field" % name)
        else:
            start = end = _parse_int(base, name)
        if start < lo or end > hi:
            raise ValueError("value out of range in %s field" % name)
        values.update(range(start, end + 1, step))
    return sorted(values)


class CronExpr:
    def __init__(self, expr):
        if not isinstance(expr, str):
            raise ValueError("expression must be a string")
        if expr.strip() == "":
            raise ValueError("empty cron expression")
        fields = expr.split()
        if len(fields) != 5:
            raise ValueError("expected 5 fields, got %d" % len(fields))
        self.minutes = _parse_field(fields[0], *_BOUNDS[0], name=_NAMES[0])
        self.hours = _parse_field(fields[1], *_BOUNDS[1], name=_NAMES[1])
        self.days = _parse_field(fields[2], *_BOUNDS[2], name=_NAMES[2])
        self.months = _parse_field(fields[3], *_BOUNDS[3], name=_NAMES[3])
        self.dows = _parse_field(fields[4], *_BOUNDS[4], name=_NAMES[4])
        self.dom_restricted = fields[2] != "*"
        self.dow_restricted = fields[4] != "*"

    def day_matches(self, dt):
        if self.dom_restricted and self.dow_restricted:
            return dt.day in self.days or dt.weekday() in self.dows
        if dt.day not in self.days:
            return False
        if dt.weekday() not in self.dows:
            return False
        return True


def _to_utc(dt):
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _next_month_first(year, month):
    if month == 12:
        return datetime(year + 1, 1, 1, tzinfo=UTC)
    return datetime(year, month + 1, 1, tzinfo=UTC)


def next_runs(expr, start_dt, count=5):
    if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
        raise ValueError("count must be a positive integer")
    ce = CronExpr(expr)
    start = _to_utc(start_dt)
    # First minute-aligned instant strictly after start_dt.
    if start.second == 0 and start.microsecond == 0:
        cursor = start + timedelta(minutes=1)
    else:
        cursor = start.replace(second=0, microsecond=0) + timedelta(minutes=1)
    results = []
    for _ in range(_MAX_DAYS):
        if cursor.month not in ce.months:
            cursor = _next_month_first(cursor.year, cursor.month)
            continue
        if not ce.day_matches(cursor):
            cursor = datetime(cursor.year, cursor.month, cursor.day, tzinfo=UTC) + timedelta(days=1)
            continue
        if cursor.hour not in ce.hours:
            cursor = datetime(cursor.year, cursor.month, cursor.day, 0, tzinfo=UTC) + timedelta(hours=1)
            continue
        if cursor.minute not in ce.minutes:
            cursor = cursor.replace(minute=0) + timedelta(minutes=1)
            continue
        results.append(cursor)
        if len(results) == count:
            return results
        cursor = cursor + timedelta(minutes=1)
    raise ValueError("no matching run found within %d days" % _MAX_DAYS)
