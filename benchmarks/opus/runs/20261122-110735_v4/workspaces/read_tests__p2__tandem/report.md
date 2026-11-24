# Report test: `python3 -m unittest -v test_inventory.py`

**Esito:** 216 test eseguiti, **3 non superati** (`FAILED (failures=2, errors=1)`); 213 superati.

| # | Test | Esito | Messaggio |
|---|------|-------|-----------|
| 1 | `test_bulk_discount_rounding` | FAIL | `AssertionError: 21.1 != 21.11` |
| 2 | `test_restock_negative` | FAIL | `AssertionError: ValueError not raised` |
| 3 | `test_export_csv_header` | ERROR | `KeyError: 'sku'` |

## 1. `test_bulk_discount_rounding` (FAIL)

Il test verifica `unit_price(22.22, 10) == 21.11`.

**Causa — `inventory.py:7`:**
```python
return int(base * (1 - rate) * 100) / 100
```
Con 10 unità lo sconto è del 5%: 22.22 × 0.95 = 21.109, che va arrotondato a 21.11.
`int()` invece **tronca** i decimali e restituisce 21.10, quindi 21.1.
Correzione possibile: `round(base * (1 - rate), 2)`.

## 2. `test_restock_negative` (FAIL)

Il test si aspetta che `restock(10, -3)` sollevi `ValueError`.

**Causa — `inventory.py:12`:**
```python
return stock + amount
```
La docstring dice che `amount` deve essere positivo, ma la funzione non lo controlla mai:
somma anche una quantità negativa e restituisce 7 senza errore.
Correzione possibile: `if amount <= 0: raise ValueError(...)` prima della somma.

## 3. `test_export_csv_header` (ERROR)

Il test legge `rows[0]["sku"]` dal risultato di `export_rows(...)`.

**Causa — `inventory.py:17`:**
```python
return [{"code": i["sku"], "name": i["name"], "qty": i["qty"]} for i in items]
```
La docstring dice che le chiavi sono `sku, name, qty`, ma il codice salva lo SKU sotto la chiave
**`"code"`**. La chiave `"sku"` non esiste nella riga esportata, quindi il test va in `KeyError`
(per questo è un ERROR e non un FAIL).
Correzione possibile: usare la chiave `"sku"` al posto di `"code"`.
