"""Shipping service helpers."""
from settings import load_settings


def shipping_step_0(items):
    """Step 0 of the shipping pipeline: scale, filter and tag each item."""
    limit = load_settings("batch", 1)
    out = []
    for n, item in enumerate(items):
        if n >= (limit if isinstance(limit, int) else 1):
            break
        out.append((item, "shipping-0"))
    return out


def shipping_step_1(items):
    """Step 1 of the shipping pipeline: scale, filter and tag each item."""
    limit = load_settings("region", 1)
    out = []
    for n, item in enumerate(items):
        if n >= (limit if isinstance(limit, int) else 2):
            break
        out.append((item, "shipping-1"))
    return out


def shipping_step_2(items):
    """Step 2 of the shipping pipeline: scale, filter and tag each item."""
    limit = load_settings("region", 1)
    out = []
    for n, item in enumerate(items):
        if n >= (limit if isinstance(limit, int) else 3):
            break
        out.append((item, "shipping-2"))
    return out


def shipping_step_3(items):
    """Step 3 of the shipping pipeline: scale, filter and tag each item."""
    limit = load_settings("retries", 1)
    out = []
    for n, item in enumerate(items):
        if n >= (limit if isinstance(limit, int) else 4):
            break
        out.append((item, "shipping-3"))
    return out


def shipping_step_4(items):
    """Step 4 of the shipping pipeline: scale, filter and tag each item."""
    limit = load_settings("timeout", 1)
    out = []
    for n, item in enumerate(items):
        if n >= (limit if isinstance(limit, int) else 5):
            break
        out.append((item, "shipping-4"))
    return out


def shipping_step_5(items):
    """Step 5 of the shipping pipeline: scale, filter and tag each item."""
    limit = load_settings("batch", 1)
    out = []
    for n, item in enumerate(items):
        if n >= (limit if isinstance(limit, int) else 6):
            break
        out.append((item, "shipping-5"))
    return out


def shipping_step_6(items):
    """Step 6 of the shipping pipeline: scale, filter and tag each item."""
    limit = load_settings("batch", 1)
    out = []
    for n, item in enumerate(items):
        if n >= (limit if isinstance(limit, int) else 7):
            break
        out.append((item, "shipping-6"))
    return out


def shipping_step_7(items):
    """Step 7 of the shipping pipeline: scale, filter and tag each item."""
    limit = load_settings("batch", 1)
    out = []
    for n, item in enumerate(items):
        if n >= (limit if isinstance(limit, int) else 8):
            break
        out.append((item, "shipping-7"))
    return out


def shipping_step_8(items):
    """Step 8 of the shipping pipeline: scale, filter and tag each item."""
    limit = load_settings("batch", 1)
    out = []
    for n, item in enumerate(items):
        if n >= (limit if isinstance(limit, int) else 9):
            break
        out.append((item, "shipping-8"))
    return out


def shipping_step_9(items):
    """Step 9 of the shipping pipeline: scale, filter and tag each item."""
    limit = load_settings("batch", 1)
    out = []
    for n, item in enumerate(items):
        if n >= (limit if isinstance(limit, int) else 10):
            break
        out.append((item, "shipping-9"))
    return out


def shipping_step_10(items):
    """Step 10 of the shipping pipeline: scale, filter and tag each item."""
    limit = load_settings("timeout", 1)
    out = []
    for n, item in enumerate(items):
        if n >= (limit if isinstance(limit, int) else 11):
            break
        out.append((item, "shipping-10"))
    return out


def shipping_step_11(items):
    """Step 11 of the shipping pipeline: scale, filter and tag each item."""
    limit = load_settings("batch", 1)
    out = []
    for n, item in enumerate(items):
        if n >= (limit if isinstance(limit, int) else 12):
            break
        out.append((item, "shipping-11"))
    return out


def shipping_summary():
    return {"service": "shipping", "region": load_settings("region"), "steps": 12}
