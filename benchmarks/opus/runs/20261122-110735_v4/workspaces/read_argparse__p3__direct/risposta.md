# argparse: risposte in breve

## 1) Quale metodo esegue il parsing
Il metodo pubblico è `parse_args(args=None, namespace=None)`. Chiama `parse_known_args`, che passa a `_parse_known_args2`. Il parsing vero e proprio lo fa `_parse_known_args(arg_strings, namespace, intermixed)`.
- Se `args` è `None`, usa `sys.argv[1:]`.
- `parse_known_args` restituisce una tupla `(namespace, argomenti_non_riconosciuti)`.
- `parse_args` restituisce solo l'oggetto `Namespace` con gli attributi valorizzati. Se restano argomenti non riconosciuti, segnala l'errore `unrecognized arguments: ...`.

## 2) Codice di uscita con un argomento non valido
Il programma termina con codice **2**. Lo fa il metodo `error(message)`: stampa l'usage su stderr e chiama `self.exit(2, '%(prog)s: error: %(message)s\n')`. A sua volta `exit(status=0, message=None)` chiama `sys.exit(status)`.
- Questo succede solo se il parametro del costruttore `exit_on_error=True` (il default).
- Con `exit_on_error=False` viene invece sollevata un'eccezione `ArgumentError`.

## 3) Abbreviazioni delle opzioni lunghe
Le gestisce `_get_option_tuples`, chiamato da `_parse_optional` quando la stringa non corrisponde esattamente a nessuna opzione. Raccoglie tutte le opzioni che iniziano con il prefisso dato, considerando solo la parte prima di un eventuale `=`. Quindi `--verb` corrisponde a `--verbose`.
- Se c'è una sola corrispondenza, viene usata quella.
- Se ce ne sono più di una, viene sollevato l'errore `ambiguous option: ... could match ...`, cioè uscita con codice 2 tramite `error`.

Le abbreviazioni si disattivano con il parametro del costruttore `allow_abbrev=False` (il default è `True`).

## 4) Due opzioni con lo stesso nome
Lo decide il parametro del costruttore `conflict_handler`, che di default vale `'error'`. Quando si aggiunge un'azione, `_check_conflict` cerca le stringhe di opzione già registrate. Poi `_get_handler` sceglie il metodo `_handle_conflict_<valore>`:
- **`'error'`** → `_handle_conflict_error`: solleva `ArgumentError` con il messaggio `conflicting option string(s): ...`.
- **`'resolve'`** → `_handle_conflict_resolve`: toglie le stringhe in conflitto dalla vecchia opzione, che viene rimossa del tutto se non le resta alcuna stringa. Vince la nuova opzione.
- **Qualsiasi altro valore** → `ValueError('invalid conflict_resolution value: ...')`.
