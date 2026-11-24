# argparse: risposte in breve

## 1) Quale metodo esegue il parsing e cosa restituisce
Il lavoro vero lo fa `_parse_known_args(arg_strings, namespace, intermixed)`. La catena di chiamate è questa:
- `parse_args()` chiama `parse_known_args()`;
- `parse_known_args()` chiama `_parse_known_args2()`;
- `_parse_known_args2()` chiama `_parse_known_args()`.

`_parse_known_args2()` prepara il terreno. Se `args` è `None` usa `sys.argv[1:]`, crea il `Namespace` e imposta i valori di default.

`_parse_known_args()` restituisce la tupla `(namespace, args)`, dove `args` sono gli argomenti non riconosciuti. Anche `parse_known_args()` restituisce questa tupla. `parse_args()` invece restituisce solo il `Namespace`. Se restano argomenti non riconosciuti, chiama `error()` con il messaggio "unrecognized arguments: ...". Se `exit_on_error=False`, solleva invece `ArgumentError`.

## 2) Codice di uscita per un argomento non valido
Il codice di uscita è **2**. Il metodo `error(message)` stampa l'uso con `print_usage(sys.stderr)` e poi chiama `self.exit(2, '%(prog)s: error: %(message)s\n')`. A sua volta `exit(status=0, message=None)` stampa il messaggio su stderr e chiama `_sys.exit(status)`.

Le `ArgumentError` sollevate durante il parsing vengono catturate in `_parse_known_args2()` e girate a `error()`, ma solo se `exit_on_error=True`, che è il valore di default.

## 3) Abbreviazioni delle opzioni lunghe
Se un argomento non corrisponde esattamente a un'opzione, `_parse_optional()` chiama `_get_option_tuples()`. Questo metodo cerca tutte le opzioni registrate che iniziano con quel prefisso (`option_string.startswith(option_prefix)`), considerando solo la parte prima di un eventuale `=`.
- Con una sola corrispondenza, l'abbreviazione viene accettata.
- Con più corrispondenze, `_parse_known_args` dà l'errore "ambiguous option: %(option)s could match %(matches)s".

Il parametro del costruttore che disattiva le abbreviazioni è **`allow_abbrev`** (default `True`). Con `allow_abbrev=False` viene accettato solo il nome esatto.

## 4) Due opzioni con lo stesso nome
Lo decide il parametro del costruttore **`conflict_handler`** (default `'error'`). Il controllo avviene quando si aggiunge l'opzione: `_check_conflict()` trova le stringhe già presenti in `_option_string_actions`. Poi `_get_handler()` sceglie il metodo `_handle_conflict_<valore>`:
- `'error'` → `_handle_conflict_error()` solleva `ArgumentError` con il messaggio "conflicting option string(s): ...";
- `'resolve'` → `_handle_conflict_resolve()` toglie le stringhe in conflitto dalla vecchia opzione. Se alla vecchia opzione non resta più nessuna stringa, viene rimossa del tutto con `_remove_action()`, e vince la nuova opzione.

Con un valore diverso da questi, `_get_handler()` solleva `ValueError` ("invalid conflict_resolution value").
