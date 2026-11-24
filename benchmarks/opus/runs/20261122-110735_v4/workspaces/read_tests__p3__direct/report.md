# Report test `test_inventory.py`

Comando: `python3 -m unittest -v test_inventory.py`

Risultato: **216 test eseguiti, 3 non passano** (2 failure + 1 error), 213 passano.

## Test che falliscono

### 1. `test_bulk_discount_rounding` — FAIL
- Asserzione: `unit_price(22.22, 10) == 21.11`, ottenuto `21.1`.
- Causa: `inventory.py:7`, `unit_price` tronca invece di arrotondare:
  `int(base * (1 - rate) * 100) / 100`. `22.22 * 0.95 * 100` in floating point vale
  `2110.8999999999996`, e `int()` lo tronca a `2110`, quindi restituisce `21.10`
  invece di `21.11`.
- Correzione suggerita: `round(base * (1 - rate), 2)`.

### 2. `test_restock_negative` — FAIL
- Asserzione: `restock(10, -3)` deve sollevare `ValueError`, ma l'eccezione non viene sollevata.
- Causa: `inventory.py:12`, `restock` restituisce `stock + amount` senza controllare
  `amount`. La docstring dice che amount deve essere positivo, ma un valore negativo
  viene accettato (e restituisce 7).
- Correzione suggerita: `if amount <= 0: raise ValueError(...)` prima della somma.

### 3. `test_export_csv_header` — ERROR (`KeyError: 'sku'`)
- Asserzione: `rows[0]["sku"] == "X1"`.
- Causa: `inventory.py:17`, `export_rows` mette lo SKU sotto la chiave `"code"` invece
  di `"sku"` (`{"code": i["sku"], ...}`). Questo contraddice la docstring
  (chiavi `sku`, `name`, `qty`), quindi `rows[0]["sku"]` solleva `KeyError`.
- Correzione suggerita: rinominare la chiave in `"sku"`.

Nessun file sorgente o di test è stato modificato.
