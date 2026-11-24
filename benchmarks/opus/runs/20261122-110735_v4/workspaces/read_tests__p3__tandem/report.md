# Report test `test_inventory.py`

Comando: `python3 -m unittest -v test_inventory.py`

Risultato: **216 test eseguiti, 3 non passano** (2 failure, 1 error) — `FAILED (failures=2, errors=1)`.

## Test che falliscono

### 1. `test_bulk_discount_rounding` — FAIL
- Errore: `AssertionError: 21.1 != 21.11` (test_inventory.py:647, `unit_price(22.22, 10)`).
- Causa: `inventory.py:7`, in `unit_price`:
  `return int(base * (1 - rate) * 100) / 100`
  Il prezzo viene **troncato** invece che arrotondato. 22.22 × 0.95 = 21.109, che in virgola mobile è
  ~21.10899999…; `int(2110.899…)` dà 2110 → 21.1 invece di 21.11.
  Correzione suggerita: `round(base * (1 - rate), 2)`.

### 2. `test_restock_negative` — FAIL
- Errore: `AssertionError: ValueError not raised` (test_inventory.py:650, `restock(10, -3)`).
- Causa: `inventory.py:12`, in `restock`:
  `return stock + amount`
  La docstring dice che `amount` deve essere positivo, ma la funzione non lo valida e restituisce 7
  invece di sollevare `ValueError`.
  Correzione suggerita: `if amount <= 0: raise ValueError(...)` prima della somma.

### 3. `test_export_csv_header` — ERROR
- Errore: `KeyError: 'sku'` (test_inventory.py:655, `rows[0]["sku"]`).
- Causa: `inventory.py:17`, in `export_rows`:
  `return [{"code": i["sku"], "name": i["name"], "qty": i["qty"]} for i in items]`
  La riga esportata usa la chiave `"code"` invece di `"sku"`, contrariamente alla docstring
  ("keys sku, name, qty"); il test che legge `rows[0]["sku"]` va quindi in `KeyError`.
  Correzione suggerita: usare la chiave `"sku"`.

Gli altri 213 test (tra cui tutti i `test_total_value_*`) passano.
