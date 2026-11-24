# Report test `test_inventory.py`

Comando: `python3 -m unittest -v test_inventory.py`

Risultato: **216 test eseguiti, 3 non passano** (2 FAIL + 1 ERROR), 213 OK.

| # | Test | Esito | Funzione |
|---|------|-------|----------|
| 1 | `test_bulk_discount_rounding` | FAIL | `unit_price` |
| 2 | `test_restock_negative` | FAIL | `restock` |
| 3 | `test_export_csv_header` | ERROR (`KeyError: 'sku'`) | `export_rows` |

## 1. `test_bulk_discount_rounding`: FAIL

- Il test si aspetta `unit_price(22.22, 10) == 21.11`, ma ottiene `21.1`.
- Causa (`inventory.py:7`): `return int(base * (1 - rate) * 100) / 100`.
  `22.22 * 0.95 = 21.108999…`; `int(2110.8999…)` tronca a `2110`, quindi il
  risultato è `21.10` invece di `21.11` arrotondato. La funzione **tronca**
  invece di **arrotondare** ai centesimi (servirebbe ad es. `round(base * (1 - rate), 2)`).

## 2. `test_restock_negative`: FAIL

- Il test si aspetta che `restock(10, -3)` sollevi `ValueError`, ma l'eccezione
  non viene sollevata (`AssertionError: ValueError not raised`).
- Causa (`inventory.py:12`): `return stock + amount` non controlla in alcun modo
  `amount`. La docstring dice "amount must be positive", ma una quantità negativa
  viene sommata in silenzio (restituisce `7`). Manca un controllo del tipo
  `if amount <= 0: raise ValueError(...)`.

## 3. `test_export_csv_header`: ERROR

- Il test legge `rows[0]["sku"]` e va in `KeyError: 'sku'`.
- Causa (`inventory.py:17`): il dizionario generato usa la chiave `"code"`
  invece di `"sku"`: `{"code": i["sku"], "name": ..., "qty": ...}`. La docstring
  dice che le chiavi devono essere `sku, name, qty`, quindi l'intestazione del
  CSV esportato è sbagliata.

## Test che passano

Tutti gli altri 213 test (`test_restock_*`, `test_total_value_*`,
`test_unit_price_small_*`, `test_unit_price_mid_*`, `test_unit_price_bulk_*`)
passano: i loro valori attesi non risentono del troncamento, e `total_value`
non ha difetti.
