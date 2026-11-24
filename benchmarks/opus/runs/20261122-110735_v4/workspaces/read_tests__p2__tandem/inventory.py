"""Small inventory module used by the test-report benchmark task."""


def unit_price(base, qty):
    """Price per unit after the bulk discount: 5% off from 10 units, 10% off from 100."""
    rate = 0.10 if qty >= 100 else 0.05 if qty >= 10 else 0.0
    return int(base * (1 - rate) * 100) / 100      # truncates instead of rounding


def restock(stock, amount):
    """Add amount to stock; amount must be positive."""
    return stock + amount                          # never rejects a negative amount


def export_rows(items):
    """Rows for the CSV export: one dict per item with keys sku, name, qty."""
    return [{"code": i["sku"], "name": i["name"], "qty": i["qty"]} for i in items]


def total_value(items, prices):
    return round(sum(i["qty"] * prices[i["sku"]] for i in items), 2)
