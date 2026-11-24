# argparse: risposte brevi

**1) Chi fa davvero il parsing.**
`parse_args(args=None, namespace=None)` chiama `parse_known_args`. Questo passa a `_parse_known_args2`, che a sua volta chiama `_parse_known_args(arg_strings, namespace, intermixed)`: è questo metodo a fare il lavoro vero. `_parse_known_args` restituisce la tupla `(namespace, extras)`, e `parse_known_args` passa al chiamante la stessa tupla `(namespace, args)`. `parse_args` invece restituisce solo il `Namespace`. Se restano argomenti non riconosciuti, chiama `self.error('unrecognized arguments: ...')`, oppure solleva `ArgumentError` quando `exit_on_error=False`.

**2) Uscita su argomento non valido.**
L'uscita la fa il metodo `error(message)`. Stampa l'uso su stderr e chiama `self.exit(2, '%(prog)s: error: %(message)s\n')`. `exit()` poi esegue `_sys.exit(status)`, quindi il codice di uscita è **2**. Durante il parsing le `ArgumentError` vengono catturate in `_parse_known_args2` e passate a `self.error(str(err))`, ma solo se `exit_on_error=True` (il default).

**3) Abbreviazioni delle opzioni lunghe.**
Se una stringa non corrisponde esattamente a un'opzione nota, `_parse_optional` chiama `_get_option_tuples`. Per le opzioni con due caratteri di prefisso (es. `--`), questo metodo cerca tutte le opzioni registrate che iniziano con il prefisso dato (prima dell'eventuale `=`). Se c'è una sola corrispondenza, l'abbreviazione viene accettata. Se ce ne sono più di una, il parser segnala l'errore `ambiguous option: %(option)s could match %(matches)s`. Le abbreviazioni si disattivano con il parametro del costruttore **`allow_abbrev=False`** (il default è `True`).

**4) Due opzioni con lo stesso nome.**
In `add_argument`, `_check_conflict` cerca le stringhe di opzione già registrate in `_option_string_actions`. Se le trova, chiama il gestore scelto dal parametro **`conflict_handler`** (tramite `_get_handler`, che cerca `'_handle_conflict_%s'`):
- `'error'` (default): `_handle_conflict_error` solleva `ArgumentError` con il messaggio `conflicting option string(s): ...`.
- `'resolve'`: `_handle_conflict_resolve` toglie la stringa in conflitto dalla vecchia azione. Se all'azione non resta nessuna stringa, la rimuove del tutto. Vince quindi l'ultima opzione definita.

Qualsiasi altro valore provoca `ValueError('invalid conflict_resolution value: ...')`.
