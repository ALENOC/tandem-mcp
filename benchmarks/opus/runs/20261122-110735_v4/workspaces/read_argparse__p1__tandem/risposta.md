# argparse: risposte in breve

## 1) Quale metodo fa davvero il parsing
`parse_args(args=None, namespace=None)` chiama `parse_known_args`, che passa a `_parse_known_args2`. Questo prepara gli argomenti (di default `sys.argv[1:]`) e il `Namespace` con i valori predefiniti, poi chiama **`_parse_known_args(arg_strings, namespace, intermixed)`**: è questo il metodo che fa davvero il parsing. Restituisce la coppia `(namespace, argomenti_non_riconosciuti)`. `parse_args` restituisce solo il **`Namespace`**. Se restano argomenti non riconosciuti, chiama `self.error('unrecognized arguments: ...')`.

## 2) Codice di uscita per un argomento non valido
Il codice di uscita è **2**. Il metodo **`error(message)`** stampa l'uso su stderr e chiama `self.exit(2, '%(prog)s: error: %(message)s\n')`. **`exit(status, message)`** chiama poi `_sys.exit(status)`. In `_parse_known_args2` una `ArgumentError` viene convertita in `self.error(...)` solo se `exit_on_error=True` (il default). Altrimenti l'eccezione viene propagata.

## 3) Abbreviazioni delle opzioni lunghe
`_parse_optional` cerca prima la corrispondenza esatta, anche nella forma `--opt=valore`. Se non la trova, chiama `_get_option_tuples`, che raccoglie tutte le opzioni registrate che **iniziano con** il prefisso scritto. Con una sola corrispondenza l'abbreviazione viene accettata. Con più corrispondenze viene sollevato l'errore `ambiguous option: %(option)s could match %(matches)s`. Il parametro del costruttore che disattiva le abbreviazioni è **`allow_abbrev`** (default `True`). Con `allow_abbrev=False` il confronto per prefisso viene saltato.

## 4) Due opzioni con lo stesso nome
`add_argument` passa per `_check_conflict`, che cerca le stringhe di opzione già presenti in `_option_string_actions`. Se ne trova, chiama il gestore scelto da **`conflict_handler`** tramite `_get_handler`, che costruisce il nome `'_handle_conflict_%s'`:
- `conflict_handler='error'` (default) usa **`_handle_conflict_error`**, che solleva `ArgumentError` con il messaggio `conflicting option string(s): ...`.
- `conflict_handler='resolve'` usa **`_handle_conflict_resolve`**: toglie la stringa in conflitto alla vecchia azione e vince la nuova. Se alla vecchia azione non resta nessuna stringa di opzione, viene rimossa del tutto.

Un valore diverso da questi due genera `ValueError('invalid conflict_resolution value: ...')`.
