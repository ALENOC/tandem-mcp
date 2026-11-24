# Report test `test_inventory.py`

Comando: `python3 -m unittest -v test_inventory.py`

Esito: **216 test eseguiti, 3 non passano** (2 failure, 1 error). Gli altri 213 passano.

| # | Test | Tipo | Funzione coinvolta |
|---|------|------|--------------------|
| 1 | `test_bulk_discount_rounding` | FAIL | `unit_price` (inventory.py:7) |
| 2 | `test_restock_negative` | FAIL | `restock` (inventory.py:12) |
| 3 | `test_export_csv_header` | ERROR | `export_rows` (inventory.py:17) |

## 1. `test_bulk_discount_rounding` — FAIL

```
AssertionError: 21.1 != 21.11
```

Il test si aspetta `unit_price(22.22, 10) == 21.11`.

**Causa** (`inventory.py:7`): il prezzo viene troncato con
`int(base * (1 - rate) * 100) / 100` invece di essere arrotondato.
22.22 × 0.95 = 21.109 (in floating point `21.108999999999998`). Troncato
a due decimali dà 21.10, mentre arrotondato darebbe 21.11. La correzione
è usare `round(base * (1 - rate), 2)`.

## 2. `test_restock_negative` — FAIL

```
AssertionError: ValueError not raised
```

Il test si aspetta che `restock(10, -3)` sollevi `ValueError`.

**Causa** (`inventory.py:12`): `restock` restituisce direttamente
`stock + amount` senza controllare `amount`. La docstring dice che
"amount must be positive", ma la funzione accetta un valore negativo e
restituisce 7. Serve un controllo prima della somma, per esempio
`if amount <= 0: raise ValueError(...)`.

## 3. `test_export_csv_header` — ERROR

```
KeyError: 'sku'
```

Il test legge `rows[0]["sku"]` e si aspetta `"X1"`.

**Causa** (`inventory.py:17`): `export_rows` mette lo SKU sotto la
chiave `"code"` invece che `"sku"`. Le chiavi prodotte sono
`code, name, qty`, mentre la docstring indica `sku, name, qty`. Quando il
test accede a `"sku"` scatta un `KeyError`, quindi l'esito è ERROR e non
FAIL. La correzione è rinominare la chiave da `"code"` a `"sku"`.
