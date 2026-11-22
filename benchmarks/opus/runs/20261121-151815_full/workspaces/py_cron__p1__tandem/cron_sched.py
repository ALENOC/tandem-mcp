"""Parser and iterator for 5-field cron expressions.

Fields: minute hour day_of_month month day_of_week.
"""

from datetime import datetime, timedelta, timezone

# (min, max) inclusive bounds for each of the five fields, in order.
_FIELD_BOUNDS = [
    (0, 59),   # minute
    (0, 23),   # hour
    (1, 31),   # day of month
    (1, 12),   # month
    (0, 7),    # day of week (0 and 7 both mean Sunday)
]

# How far ahead to search before declaring an expression impossible.
_MAX_SEARCH_DAYS = 366 * 5


def _parse_field(field, lo, hi, name):
    """Parse one cron field into a sorted list of matching integers."""
    if field == "":
        raise ValueError("empty field in %s" % name)
    values = set()
    for item in field.split(","):
        if item == "":
            raise ValueError("empty list item in %s" % name)
        step = 1
        if "/" in item:
            base, sep, step_s = item.partition("/")
            if step_s == "":
                raise ValueError("missing step value in %s" % name)
            try:
                step = int(step_s)
            except ValueError:
                raise ValueError("non-numeric step in %s" % name)
            if step < 1:
                raise ValueError("step must be >= 1 in %s" % name)
        else:
            base = item
        if "-" in base:
            a_s, sep, b_s = base.partition("-")
            if a_s == "" or b_s == "":
                raise ValueError("malformed range in %s" % name)
            try:
                a = int(a_s)
                b = int(b_s)
            except ValueError:
                raise ValueError("non-numeric range in %s" % name)
            if a > b:
                raise ValueError("range start > end in %s" % name)
            if a < lo or b > hi:
                raise ValueError("range out of bounds in %s" % name)
            values.update(range(a, b + 1, step))
        else:
            if base == "*":
                values.update(range(lo, hi + 1, step))
            else:
                try:
                    v = int(base)
                except ValueError:
                    raise ValueError("non-numeric value in %s" % name)
                if v < lo or v > hi:
                    raise ValueError("value out of bounds in %s" % name)
                values.add(v)
    return sorted(values)


class CronExpr:
    """A parsed 5-field cron expression."""

    def __init__(self, expr):
        if not isinstance(expr, str):
            raise ValueError("cron expression must be a string")
        parts = expr.split()
        if len(parts) != 5:
            raise ValueError("cron expression must have exactly 5 fields")
        self.minutes = _parse_field(parts[0], 0, 59, "minute")
        self.hours = _parse_field(parts[1], 0, 23, "hour")
        self.days_of_month = _parse_field(parts[2], 1, 31, "day_of_month")
        self.months = _parse_field(parts[3], 1, 12, "month")
        self.days_of_week = _parse_field(parts[4], 0, 7, "day_of_week")
        self._dom_restricted = parts[2] != "*"
        self._dow_restricted = parts[4] != "*"
        self._dow = set(self.days_of_week)
        if 7 in self._dow:
            self._dow.add(0)
        self._dow.discard(7)
        self._check_impossible()

    def _check_impossible(self):
        """Raise ValueError if the expression can never match a real date."""
        for year in range(2000, 2000 + 8):
            for month in self.months:
                for dom in self.days_of_month:
                    try:
                        datetime(year, month, dom)
                    except ValueError:
                        continue
                    if self._day_matches(datetime(year, month, dom)):
                        return
        raise ValueError("cron expression can never match a date")

    def _day_matches(self, dt):
        dom_ok = dt.day in self.days_of_month
        dow_ok = (dt.weekday() + 1) % 7 in self._dow
        if self._dom_restricted and self._dow_restricted:
            return dom_ok or dow_ok
        if self._dom_restricted:
            return dom_ok
        if self._dow_restricted:
            return dow_ok
        return True

    def next_runs(self, start_dt, count=5):
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            raise ValueError("count must be a positive integer")
        if start_dt.tzinfo is None:
            start = start_dt.replace(tzinfo=timezone.utc)
        else:
            start = start_dt.astimezone(timezone.utc)
        results = []
        # cur is the earliest candidate minute strictly after start.
        cur = start.replace(second=0, microsecond=0) + timedelta(minutes=1)
        limit = start + timedelta(days=_MAX_SEARCH_DAYS)
        while len(results) < count:
            if cur > limit:
                raise ValueError("cron expression can never match a date")
            if cur.month not in self.months or not self._day_matches(cur):
                cur = cur.replace(hour=0, minute=0) + timedelta(days=1)
                continue
            if cur.hour not in self.hours:
                cur = cur.replace(minute=0) + timedelta(hours=1)
                continue
            # cur.minute is the lower bound for this hour: start.minute+1 for
            # the start hour, 0 for every later hour.
            for m in self.minutes:
                if m >= cur.minute:
                    results.append(cur.replace(minute=m))
                    limit = results[-1] + timedelta(days=_MAX_SEARCH_DAYS)
                    if len(results) >= count:
                        return results
            cur = cur.replace(minute=0) + timedelta(hours=1)
        return results


def parse(expr):
    """Parse a 5-field cron expression string into a CronExpr."""
    return CronExpr(expr)


def next_runs(expr, start_dt, count=5):
    """Return the next `count` UTC datetimes strictly after start_dt."""
    if isinstance(expr, str):
        expr = CronExpr(expr)
    elif not isinstance(expr, CronExpr):
        raise ValueError("cron expression must be a string")
    return expr.next_runs(start_dt, count)
