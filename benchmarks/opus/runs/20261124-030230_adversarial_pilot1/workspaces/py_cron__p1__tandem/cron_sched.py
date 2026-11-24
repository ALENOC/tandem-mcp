"""Parser and iterator for 5-field cron expressions.

Fields: minute, hour, day-of-month, month, day-of-week.
"""

from datetime import datetime, timedelta, timezone

__all__ = ["parse", "next_runs", "CronExpr"]

# (min, max) bounds per field, in field order.
_BOUNDS = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 7)]
_NAMES = ["minute", "hour", "day-of-month", "month", "day-of-week"]


class CronExpr:
    """Parsed cron expression holding the allowed value sets per field."""

    def __init__(self, minutes, hours, days, months, weekdays, dom_restricted, dow_restricted):
        self.minutes = minutes
        self.hours = hours
        self.days = days
        self.months = months
        self.weekdays = weekdays
        self.dom_restricted = dom_restricted
        self.dow_restricted = dow_restricted

    def __repr__(self):
        return ("CronExpr(minutes=%r, hours=%r, days=%r, months=%r, weekdays=%r)"
                % (self.minutes, self.hours, self.days, self.months, self.weekdays))


def _parse_field(field, lo, hi, name):
    """Parse one cron field into a set of ints. Raises ValueError on bad input."""
    values = set()
    for part in field.split(","):
        if part == "":
            raise ValueError("empty element in %s field" % name)
        step = 1
        if "/" in part:
            base, sep, step_s = part.partition("/")
            if step_s == "":
                raise ValueError("missing step in %s field" % name)
            if not step_s.isdigit():
                raise ValueError("non-numeric step in %s field" % name)
            step = int(step_s)
            if step == 0:
                raise ValueError("step must be positive in %s field" % name)
        else:
            base = part
        if base == "*":
            start, end = lo, hi
        elif "-" in base:
            a, sep, b = base.partition("-")
            if not a.isdigit() or not b.isdigit():
                raise ValueError("bad range in %s field" % name)
            start, end = int(a), int(b)
            if start > end:
                raise ValueError("range start > end in %s field" % name)
        else:
            if not base.isdigit():
                raise ValueError("non-numeric value in %s field" % name)
            start = end = int(base)
        if start < lo or end > hi:
            raise ValueError("value out of range in %s field" % name)
        values.update(range(start, end + 1, step))
    return values


def parse(expr):
    """Parse a 5-field cron expression into a CronExpr. Raises ValueError on bad input."""
    if not isinstance(expr, str):
        raise ValueError("cron expression must be a string")
    fields = expr.split()
    if len(fields) != 5:
        raise ValueError("cron expression must have 5 fields")
    minutes = _parse_field(fields[0], *_BOUNDS[0], _NAMES[0])
    hours = _parse_field(fields[1], *_BOUNDS[1], _NAMES[1])
    days = _parse_field(fields[2], *_BOUNDS[2], _NAMES[2])
    months = _parse_field(fields[3], *_BOUNDS[3], _NAMES[3])
    weekdays = _parse_field(fields[4], *_BOUNDS[4], _NAMES[4])
    # Normalize weekday 7 (Sunday) to 0.
    if 7 in weekdays:
        weekdays.discard(7)
        weekdays.add(0)
    dom_restricted = fields[2] != "*"
    dow_restricted = fields[4] != "*"
    return CronExpr(minutes, hours, days, months, weekdays, dom_restricted, dow_restricted)


def _day_matches(spec, day):
    """Vixie day matching: if both dom and dow are restricted, match either one."""
    dom_ok = day.day in spec.days
    dow_ok = (day.weekday() + 1) % 7 in spec.weekdays
    if spec.dom_restricted and spec.dow_restricted:
        return dom_ok or dow_ok
    if spec.dom_restricted:
        return dom_ok
    if spec.dow_restricted:
        return dow_ok
    return True


def _all_hm(spec):
    """All (hour, minute) pairs allowed by the spec, in ascending order."""
    return [(h, m) for h in sorted(spec.hours) for m in sorted(spec.minutes)]


def next_runs(expr, start_dt, count=5):
    """Return the next `count` UTC datetimes strictly after start_dt matching expr."""
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        raise ValueError("count must be a non-negative integer")
    spec = parse(expr)
    if not isinstance(start_dt, datetime):
        raise ValueError("start_dt must be a datetime")
    if start_dt.tzinfo is None:
        start = start_dt.replace(tzinfo=timezone.utc)
    else:
        start = start_dt.astimezone(timezone.utc)
    # Truncate to whole minutes; results are strictly after start.
    start = start.replace(second=0, microsecond=0)

    results = []
    if count == 0:
        return results

    pairs = _all_hm(spec)
    # Search limit: 5 years ahead, checked per day to avoid infinite loops.
    limit = start + timedelta(days=5 * 366)
    day = start.date()
    while len(results) < count:
        if day > limit.date():
            raise ValueError("cron expression never matches (no run within 5 years)")
        if day.month in spec.months and _day_matches(spec, day):
            if day == start.date():
                floor = (start.hour, start.minute)
                for h, m in pairs:
                    if (h, m) > floor:
                        results.append(datetime(day.year, day.month, day.day, h, m, tzinfo=timezone.utc))
                        if len(results) >= count:
                            break
            else:
                for h, m in pairs:
                    results.append(datetime(day.year, day.month, day.day, h, m, tzinfo=timezone.utc))
                    if len(results) >= count:
                        break
        day = day + timedelta(days=1)
    return results
