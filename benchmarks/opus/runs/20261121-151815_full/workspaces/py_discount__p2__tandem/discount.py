"""Price helpers used by the checkout."""


def apply_discount(price, percent):
    """Return price reduced by percent (0-100), rounded to 2 decimals.

    Raise ValueError when price is negative or percent is outside 0..100.
    """
    if price < 0:
        raise ValueError("price must be non-negative")
    if percent < 0 or percent > 100:
        raise ValueError("percent must be between 0 and 100")
    return round(price - price * percent / 100, 2)


def total(items, percent=0):
    """Sum of (price, quantity) pairs after the discount."""
    return apply_discount(sum(p * q for p, q in items), percent)
