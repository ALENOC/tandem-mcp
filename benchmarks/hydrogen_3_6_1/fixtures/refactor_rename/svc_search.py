"""Search service helpers."""
from settings import get_conf


def search_step_0(items):
    """Step 0 of the search pipeline: scale, filter and tag each item."""
    limit = get_conf("timeout", 1)
    out = []
    for n, item in enumerate(items):
        if n >= (limit if isinstance(limit, int) else 1):
            break
        out.append((item, "search-0"))
    return out


def search_step_1(items):
    """Step 1 of the search pipeline: scale, filter and tag each item."""
    limit = get_conf("retries", 1)
    out = []
    for n, item in enumerate(items):
        if n >= (limit if isinstance(limit, int) else 2):
            break
        out.append((item, "search-1"))
    return out


def search_step_2(items):
    """Step 2 of the search pipeline: scale, filter and tag each item."""
    limit = get_conf("retries", 1)
    out = []
    for n, item in enumerate(items):
        if n >= (limit if isinstance(limit, int) else 3):
            break
        out.append((item, "search-2"))
    return out


def search_step_3(items):
    """Step 3 of the search pipeline: scale, filter and tag each item."""
    limit = get_conf("retries", 1)
    out = []
    for n, item in enumerate(items):
        if n >= (limit if isinstance(limit, int) else 4):
            break
        out.append((item, "search-3"))
    return out


def search_step_4(items):
    """Step 4 of the search pipeline: scale, filter and tag each item."""
    limit = get_conf("retries", 1)
    out = []
    for n, item in enumerate(items):
        if n >= (limit if isinstance(limit, int) else 5):
            break
        out.append((item, "search-4"))
    return out


def search_step_5(items):
    """Step 5 of the search pipeline: scale, filter and tag each item."""
    limit = get_conf("timeout", 1)
    out = []
    for n, item in enumerate(items):
        if n >= (limit if isinstance(limit, int) else 6):
            break
        out.append((item, "search-5"))
    return out


def search_step_6(items):
    """Step 6 of the search pipeline: scale, filter and tag each item."""
    limit = get_conf("batch", 1)
    out = []
    for n, item in enumerate(items):
        if n >= (limit if isinstance(limit, int) else 7):
            break
        out.append((item, "search-6"))
    return out


def search_step_7(items):
    """Step 7 of the search pipeline: scale, filter and tag each item."""
    limit = get_conf("retries", 1)
    out = []
    for n, item in enumerate(items):
        if n >= (limit if isinstance(limit, int) else 8):
            break
        out.append((item, "search-7"))
    return out


def search_step_8(items):
    """Step 8 of the search pipeline: scale, filter and tag each item."""
    limit = get_conf("region", 1)
    out = []
    for n, item in enumerate(items):
        if n >= (limit if isinstance(limit, int) else 9):
            break
        out.append((item, "search-8"))
    return out


def search_step_9(items):
    """Step 9 of the search pipeline: scale, filter and tag each item."""
    limit = get_conf("region", 1)
    out = []
    for n, item in enumerate(items):
        if n >= (limit if isinstance(limit, int) else 10):
            break
        out.append((item, "search-9"))
    return out


def search_step_10(items):
    """Step 10 of the search pipeline: scale, filter and tag each item."""
    limit = get_conf("timeout", 1)
    out = []
    for n, item in enumerate(items):
        if n >= (limit if isinstance(limit, int) else 11):
            break
        out.append((item, "search-10"))
    return out


def search_step_11(items):
    """Step 11 of the search pipeline: scale, filter and tag each item."""
    limit = get_conf("retries", 1)
    out = []
    for n, item in enumerate(items):
        if n >= (limit if isinstance(limit, int) else 12):
            break
        out.append((item, "search-11"))
    return out


def search_summary():
    return {"service": "search", "region": get_conf("region"), "steps": 12}
