# argparse: risposte brevi

## 1) Il metodo che esegue il parsing
Il metodo pubblico è `parse_args(args=None, namespace=None)`. Chiama `parse_known_args`, che passa a `_parse_known_args2`, e il lavoro vero lo fa `_parse_known_args(arg_strings, namespace, intermixed)`. `_parse_known_args2` usa `sys.argv[1:]` se `args` è `None` e crea un `Namespace` già riempito con i valori di default. `parse_args` restituisce un **oggetto `Namespace`** con gli attributi analizzati. Se restano argomenti che il parser non riconosce, li segnala con `error` ("unrecognized arguments"). `parse_known_args` invece restituisce la tupla `(namespace, lista_argomenti_rimanenti)`.

## 2) Codice di uscita con un argomento non valido
Il programma termina con **codice 2**. Se `exit_on_error` è vero (il default), l'`ArgumentError` viene intercettato e passato al metodo `error(message)`. `error` stampa l'usage su stderr e poi chiama `self.exit(2, "%(prog)s: error: %(message)s\n")`. `exit(status=0, message=None)` scrive il messaggio su stderr e chiama `sys.exit(status)`. Con `exit_on_error=False` il programma non termina e l'`ArgumentError` viene propagato al chiamante.

## 3) Abbreviazioni delle opzioni lunghe
Se una stringa non corrisponde esattamente a un'opzione, `_parse_optional` chiama `_get_option_tuples`. Questo metodo raccoglie tutte le opzioni registrate in `_option_string_actions` che **iniziano con il prefisso** scritto dall'utente, prendendo solo la parte prima di `=`.
- Se c'è **una sola** corrispondenza, l'abbreviazione viene accettata (es. `--verb` → `--verbose`).
- Se ce n'è **più di una**, si ottiene l'errore `ambiguous option: ... could match ...`.

Il parametro del costruttore `allow_abbrev` (default `True`) le disattiva: con `allow_abbrev=False` i prefissi non vengono cercati. Resta ammessa la forma corta concatenata, tipo `-xVALORE`.

## 4) Due opzioni con lo stesso nome
Quando si aggiunge un'azione, `_add_action` chiama `_check_conflict`. Questo cerca le stringhe di opzione già presenti e, se ne trova, chiama il gestore indicato dal parametro **`conflict_handler`** del costruttore. `_get_handler` cerca il metodo `_handle_conflict_<valore>`:
- `conflict_handler='error'` (default): `_handle_conflict_error` solleva `ArgumentError` ("conflicting option string(s): ...").
- `conflict_handler='resolve'`: `_handle_conflict_resolve` toglie la stringa in conflitto dalla vecchia opzione, che viene eliminata del tutto se non le restano altri nomi. Vince la nuova definizione.
- Un valore diverso causa `ValueError` ("invalid conflict_resolution value").
