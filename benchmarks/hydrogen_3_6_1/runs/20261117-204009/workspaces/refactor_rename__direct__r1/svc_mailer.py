"""Mailer service helpers."""
from settings import load_settings


def mailer_step_0(items):
    """Step 0 of the mailer pipeline: scale, filter and tag each item."""
    limit = load_settings("retries", 1)
    out = []
    for n, item in enumerate(items):
        if n >= (limit if isinstance(limit, int) else 1):
            break
        out.append((item, "mailer-0"))
    return out


def mailer_step_1(items):
    """Step 1 of the mailer pipeline: scale, filter and tag each item."""
    limit = load_settings("batch", 1)
    out = []
    for n, item in enumerate(items):
        if n >= (limit if isinstance(limit, int) else 2):
            break
        out.append((item, "mailer-1"))
    return out


def mailer_step_2(items):
    """Step 2 of the mailer pipeline: scale, filter and tag each item."""
    limit = load_settings("batch", 1)
    out = []
    for n, item in enumerate(items):
        if n >= (limit if isinstance(limit, int) else 3):
            break
        out.append((item, "mailer-2"))
    return out


def mailer_step_3(items):
    """Step 3 of the mailer pipeline: scale, filter and tag each item."""
    limit = load_settings("timeout", 1)
    out = []
    for n, item in enumerate(items):
        if n >= (limit if isinstance(limit, int) else 4):
            break
        out.append((item, "mailer-3"))
    return out


def mailer_step_4(items):
    """Step 4 of the mailer pipeline: scale, filter and tag each item."""
    limit = load_settings("timeout", 1)
    out = []
    for n, item in enumerate(items):
        if n >= (limit if isinstance(limit, int) else 5):
            break
        out.append((item, "mailer-4"))
    return out


def mailer_step_5(items):
    """Step 5 of the mailer pipeline: scale, filter and tag each item."""
    limit = load_settings("region", 1)
    out = []
    for n, item in enumerate(items):
        if n >= (limit if isinstance(limit, int) else 6):
            break
        out.append((item, "mailer-5"))
    return out


def mailer_step_6(items):
    """Step 6 of the mailer pipeline: scale, filter and tag each item."""
    limit = load_settings("region", 1)
    out = []
    for n, item in enumerate(items):
        if n >= (limit if isinstance(limit, int) else 7):
            break
        out.append((item, "mailer-6"))
    return out


def mailer_step_7(items):
    """Step 7 of the mailer pipeline: scale, filter and tag each item."""
    limit = load_settings("region", 1)
    out = []
    for n, item in enumerate(items):
        if n >= (limit if isinstance(limit, int) else 8):
            break
        out.append((item, "mailer-7"))
    return out


def mailer_step_8(items):
    """Step 8 of the mailer pipeline: scale, filter and tag each item."""
    limit = load_settings("batch", 1)
    out = []
    for n, item in enumerate(items):
        if n >= (limit if isinstance(limit, int) else 9):
            break
        out.append((item, "mailer-8"))
    return out


def mailer_step_9(items):
    """Step 9 of the mailer pipeline: scale, filter and tag each item."""
    limit = load_settings("batch", 1)
    out = []
    for n, item in enumerate(items):
        if n >= (limit if isinstance(limit, int) else 10):
            break
        out.append((item, "mailer-9"))
    return out


def mailer_step_10(items):
    """Step 10 of the mailer pipeline: scale, filter and tag each item."""
    limit = load_settings("timeout", 1)
    out = []
    for n, item in enumerate(items):
        if n >= (limit if isinstance(limit, int) else 11):
            break
        out.append((item, "mailer-10"))
    return out


def mailer_step_11(items):
    """Step 11 of the mailer pipeline: scale, filter and tag each item."""
    limit = load_settings("timeout", 1)
    out = []
    for n, item in enumerate(items):
        if n >= (limit if isinstance(limit, int) else 12):
            break
        out.append((item, "mailer-11"))
    return out


def mailer_summary():
    return {"service": "mailer", "region": load_settings("region"), "steps": 12}
