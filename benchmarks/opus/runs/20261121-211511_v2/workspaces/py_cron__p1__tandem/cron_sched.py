"""Parser and iterator for 5-field cron expressions.

Fields: minute hour day_of_month month day_of_week.
"""

import datetime

FIELD_NAMES = ('minute', 'hour', 'dom', 'month', 'dow')
FIELD_RANGES = {
    'minute': (0, 59),
    'hour': (0, 23),
    'dom': (1, 31),
    'month': (1, 12),
    'dow': (0, 6),
}

# How far ahead (in days) we search before giving up on an expression that
# can never match.
MAX_SEARCH_DAYS = 366 * 5


def _parse_field(field, name):
    lo, hi = FIELD_RANGES[name]
    values = set()
    for item in field.split(','):
        if item == '':
            raise ValueError('empty item in field %r' % name)
        step = 1
        if '/' in item:
            base, step_s = item.split('/', 1)
            step = _to_int(step_s, name)
            if step <= 0:
                raise ValueError('step must be positive in field %r' % name)
        else:
            base = item
        if base == '*':
            start, end = lo, hi
        elif '-' in base:
            a_s, b_s = base.split('-', 1)
            a = _to_int(a_s, name)
            b = _to_int(b_s, name)
            if a > b:
                raise ValueError('range start > end in field %r' % name)
            start, end = a, b
        else:
            v = _to_int(base, name)
            if '/' in item:
                start, end = v, hi
            else:
                start = end = v
        if start < lo or end > hi:
            raise ValueError('value out of range in field %r' % name)
        values.update(range(start, end + 1, step))
    return values


def _to_int(token, name):
    token = token.strip()
    if not token:
        raise ValueError('empty number in field %r' % name)
    if not token.isdigit():
        raise ValueError('non-numeric token %r in field %r' % (token, name))
    return int(token)


def parse(expr):
    if not isinstance(expr, str):
        raise ValueError('cron expression must be a string')
    fields = expr.split()
    if len(fields) != 5:
        raise ValueError('cron expression must have exactly 5 fields')
    spec = {name: _parse_field(field, name)
            for name, field in zip(FIELD_NAMES, fields)}
    spec['dom_restricted'] = fields[2] != '*'
    spec['dow_restricted'] = fields[4] != '*'
    return spec


def _day_matches(spec, dt):
    dom_ok = dt.day in spec['dom']
    dow_ok = ((dt.weekday() + 1) % 7) in spec['dow']
    if spec['dom_restricted'] and spec['dow_restricted']:
        return dom_ok or dow_ok
    return dom_ok and dow_ok


def next_runs(expr, start_dt, count=5):
    if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
        raise ValueError('count must be a positive integer')
    spec = parse(expr)
    if start_dt.tzinfo is None:
        start = start_dt.replace(tzinfo=datetime.timezone.utc)
    else:
        start = start_dt.astimezone(datetime.timezone.utc)
    start = start.replace(second=0, microsecond=0)

    minutes = sorted(spec['minute'])
    hours = sorted(spec['hour'])
    months = sorted(spec['month'])
    dom_star = '*' in spec['dom']
    dow_star = '*' in spec['dow']

    results = []
    # First candidate minute strictly after start_dt.
    cur = start + datetime.timedelta(minutes=1)
    limit = start + datetime.timedelta(days=MAX_SEARCH_DAYS)
    while len(results) < count:
        if cur > limit:
            raise ValueError('cron expression never matches')
        if cur.month not in months:
            cur = _next_month(cur)
            continue
        if not _day_matches(spec, cur):
            cur = _next_day(cur)
            continue
        if cur.hour not in hours:
            cur = _next_hour(cur)
            continue
        if cur.minute not in minutes:
            cur = _next_minute(cur)
            continue
        results.append(cur)
        cur = _next_minute(cur)
    return results


def _next_minute(dt):
    return dt + datetime.timedelta(minutes=1)


def _next_hour(dt):
    return (dt.replace(minute=0) + datetime.timedelta(hours=1))


def _next_day(dt):
    return (dt.replace(hour=0, minute=0) + datetime.timedelta(days=1))


def _next_month(dt):
    if dt.month == 12:
        return datetime.datetime(dt.year + 1, 1, 1, tzinfo=dt.tzinfo)
    return datetime.datetime(dt.year, dt.month + 1, 1, tzinfo=dt.tzinfo)
