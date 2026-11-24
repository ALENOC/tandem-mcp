# argparse: risposte in breve

1. **Parsing.** Chi fa davvero il lavoro è il metodo interno `_parse_known_args(arg_strings, namespace, intermixed)` (riga 1954). La catena di chiamate è `parse_args` → `parse_known_args` → `_parse_known_args2` → `_parse_known_args`. Restituisce la coppia `(namespace, args)`: il `Namespace` riempito e la lista degli argomenti non riconosciuti. `parse_known_args` restituisce la stessa coppia. `parse_args` restituisce solo il `Namespace` e, se restano argomenti non riconosciuti, chiama `error('unrecognized arguments: ...')`.

2. **Errore ed uscita.** Il metodo `error(message)` stampa l'usage su stderr e poi chiama `self.exit(2, '%(prog)s: error: %(message)s\n')`. `exit(status, message)` termina con `_sys.exit(status)`, quindi il **codice di uscita è 2**. Le `ArgumentError` arrivano a `error` solo se `exit_on_error=True` (il default). Con `exit_on_error=False` l'eccezione viene propagata e il programma non esce.

3. **Abbreviazioni.** `_parse_optional` cerca prima la corrispondenza esatta. Se non la trova, chiama `_get_option_tuples`, che raccoglie tutte le opzioni il cui nome inizia con il prefisso dato (`option_string.startswith(option_prefix)`). Se c'è un solo candidato, l'abbreviazione viene accettata. Se ce ne sono più di uno, si ha l'errore `ambiguous option: %(option)s could match %(matches)s`. Le abbreviazioni si disattivano con il parametro del costruttore **`allow_abbrev=False`** (il default è `True`).

4. **Nomi duplicati.** Quando si aggiunge un'azione, `_check_conflict` cerca le stringhe di opzione già registrate. Se ne trova, `_get_handler` chiama `_handle_conflict_<valore>`. Decide il parametro **`conflict_handler`**:
   - `'error'` (default): `_handle_conflict_error` solleva `ArgumentError` con il messaggio `conflicting option string(s): ...`.
   - `'resolve'`: `_handle_conflict_resolve` toglie la stringa in conflitto dalla vecchia opzione (e rimuove del tutto l'opzione se non le restano nomi), così vince la nuova.
   - Qualsiasi altro valore causa `ValueError('invalid conflict_resolution value: ...')`.
