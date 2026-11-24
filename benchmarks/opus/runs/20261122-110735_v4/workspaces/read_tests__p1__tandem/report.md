# Report test: `python3 -m unittest -v test_inventory.py`

**Esito:** 216 test eseguiti, **3 non passano** (`FAILED (failures=2, errors=1)`): 2 failure e 1 error.

## 1. `test_bulk_discount_rounding` (FAIL)

- **Test** (`test_inventory.py:646-647`): `self.assertEqual(unit_price(22.22, 10), 21.11)`
- **Errore:** `AssertionError: 21.1 != 21.11`
- **Causa** (`inventory.py:7`): `return int(base * (1 - rate) * 100) / 100` tronca invece di arrotondare.
  22.22 × 0.95 = 21.109 → ×100 = 2110.9 → `int()` = 2110 → 21.10, mentre il valore atteso
  arrotondato è 21.11. Dovrebbe usare `round(base * (1 - rate), 2)`.

## 2. `test_restock_negative` (FAIL)

- **Test** (`test_inventory.py:649-651`): si aspetta `ValueError` da `restock(10, -3)`.
- **Errore:** `AssertionError: ValueError not raised`
- **Causa** (`inventory.py:12`): `return stock + amount` non valida l'argomento. La docstring dice
  che amount deve essere positivo, ma un valore negativo viene accettato (restituisce 7).
  Manca un `if amount <= 0: raise ValueError(...)`.

## 3. `test_export_csv_header` (ERROR)

- **Test** (`test_inventory.py:653-655`): `self.assertEqual(rows[0]["sku"], "X1")`
- **Errore:** `KeyError: 'sku'`
- **Causa** (`inventory.py:17`): `export_rows` crea il dizionario con la chiave `"code"` invece di
  `"sku"` (`{"code": i["sku"], ...}`), il che contraddice la docstring ("keys sku, name, qty").
  Quindi `rows[0]["sku"]` non esiste.
