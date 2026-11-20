# Report Decisionale - Tandem MCP (`usa Tandem`)

> Il report descrive il checkout sperimentale usato nelle prove. I percorsi in testo semplice identificano file di quel checkout.

**Data**: 2026-11-20
**Modelli fissati nelle prove**: Orchestratore cloud (`agy`) · Esecutore locale da 27B con quantizzazione IQ3_S (LM Studio)

---

## Risposte rapide alle tre domande chiave

1. **Cosa conviene quando scrivo semplicemente «usa Tandem»?**
   Conviene **l'esecuzione diretta al primo turno** (già impostata come default). In chat `agy`, le prove con `tandem-mcp` attivo (`slugify` `27.89s`, `rate_limiter` `23.09s`, `py discount` `24.00s`, `web counter` `24.63s`) mostrano che l'orchestratore sceglie gli strumenti nativi al turno 1 senza chiamare `auto_route` o `delegate`, completando il lavoro con alta affidabilità. Nelle prove multi-replica su compiti più lunghi (`Boids`, `Cron`, `Pendolo`), il riferimento diretto è stato eseguito con **MCP disabilitato** (`51.70s-70.35s`, `9/9` successi in budget).
2. **Quando delegare al modello locale ha ridotto i token cloud per risultato corretto consegnato in tempo?**
   - **Nell'orchestrazione host esterna** (`Portal`, `n=3` modified vs `n=1` `direct_from_prompt`): sì, **`37,975`** vs `92,941` token cloud per successo `strict` (`-59.1%`), al costo di `37.1-58.5` minuti per singolo tentativo riuscito (`63.6` minuti totali per successo includendo il fallimento `r2`).
   - **Nella normale chat `agy`**: **nessuna attività testata ha mostrato un risparmio materiale e ripetibile di token cloud per risultato corretto in tempo**. Su `web_boids_paused` (`1,200s`, `n=3`) la differenza è stata marginale (**`33,214` vs `33,532`**, `-318` token/successo, `-0.95%`); su `py_cron_sched`, `web_pendulum` e sulle piccole modifiche (`discount.py`, `rate_limiter`, `web counter`), la delega in chat ha consumato più token cloud o è scaduta.
3. **Quanto tempo aggiuntivo ho pagato per quel risparmio?**
   - Su `web_boids_paused` (unico caso in chat `agy` con `3/3` successi in budget e `-0.95%` cloud): **`+518.6s` (`+8.6` minuti)** di mediana (`572.40s` contro `53.76s` del diretto con MCP disabilitato).
   - Su `Portal` (orchestrazione host esterna, `-59.1%` cloud/successo): `37.1` min (`r1`) e `58.5` min (`r3`) sui singoli tentativi riusciti, cioè **`63.6` minuti di tempo totale per successo `strict`** contro `110.28s` (`1.8` min) del riferimento diretto (`n=1`).

---

## 1-2. Confronto delle prove più informative (senza medie uniche tra compiti diversi)

> **Distinzione dei percorsi misurati**:
> - **Diretto (MCP disabilitato)**: `agy mcp disable tandem-mcp`, strumenti nativi `agy`.
> - **«usa Tandem» diretto (MCP attivo)**: `tandem-mcp` abilitato, `TANDEM_AUTO_POLICY=first_turn`, l'orchestratore sceglie gli strumenti nativi al turno 1.
> - **Delega in chat `agy`**: `tandem-mcp` abilitato, l'orchestratore chiama `delegate` e attende tramite `HOST_WATCHER_CMD` nello stesso thread `agy`.
> - **Orchestrazione host esterna**: `run_ab_portal.py` / `host_runner` esterno con planner `agy` singolo e attesa/review fuori dalla chat interattiva.

### A. Piccole modifiche e generazione piccola in chat (`n=1` per braccio, `tandem-mcp` attivo)

- **Prova della scelta al primo turno (`slugify.py`, dopo allineamento istruzioni `first_turn`)**: entrambi i prompt hanno scelto il percorso diretto al turno 1 (`first_action=run_command`, `0` chiamate locali, `unittest` `exit=0`):
  - `usa Tandem`: `27.89s`, `27,011` token cloud (`25,320` in, `1,691` out), `0` locali.
  - `usa Tandem, privilegia il risparmio cloud, posso aspettare`: `25.79s`, `27,418` token cloud (`25,599` in, `1,819` out), `0` locali.
- **Confronto diretto vs delega sullo stesso file esistente (`discount.py`, `py discount` con `tests/check_discount.py`)**:
  - `usa Tandem` (MCP attivo, diretto al turno 1): **`24.00s`**, **`26,953`** cloud (`25,333` in, `1,620` out), `0` locali, `Pass`.
  - `usa Tandem, privilegia il risparmio di token cloud, posso aspettare` (delega in chat prima della correzione istruzioni): **`105.42s`** (`+81.42s`), **`33,479`** cloud (`30,845` in, `2,634` out; **`+6,526` cloud**), `11,888` locali (`5` inf.), `Pass`.
- **Altri casi `n=1` in chat con MCP attivo**:
  - `rate_limiter` (da zero): `usa Tandem` diretto `23.09s` / `20,645` cloud (`17,649` in, `2,996` out) vs delega in chat `165.64s` / `39,102` cloud (`36,002` in, `3,100` out), `15,712` locali (`5` inf.).
  - `web counter` (edit su `index.html` + `verify_ui.mjs`): `usa Tandem` diretto `24.63s` / `25,974` cloud (`24,865` in, `1,109` out) vs delega in chat scaduta a `480.30s` (`usage` cloud mancante `0/1`, `58,285` locali in `12` inf.; `index.html` corretto su disco ma bloccato in jail su `ms-playwright`).

### B. Confronti multi-replica (`n=3` coppie controbilanciate)

1. **`web_boids_paused`** (web start-paused, budget `1,200s`, valutatore `benchmarks/auto_suite/check_boids_behavioral.mjs`, risultati `benchmarks/auto_suite/runs/20261120-141727_value_ab/results.json`):
   - **Diretto (MCP disabilitato, `n=3`)**: **`3/3`** successi in budget, copertura cloud `3/3`, **`33,532`** cloud/successo (`100,595` tot), `0` locali, mediana **`53.76s`** (`48.85s-55.17s`).
   - **Delega in chat `agy` (MCP attivo, `n=3`)**: **`3/3`** successi in budget, copertura cloud `3/3`, **`33,214`** cloud/successo (`99,643` tot), `128,753` locali, mediana **`572.40s`** (`286.45s-702.36s`).

2. **`py_cron_sched`** (modulo Python, budget `900s`, `unittest` + check indipendente, risultati `benchmarks/auto_suite/runs/20261120-141727_value_ab/results.json`):
   - **Diretto (MCP disabilitato, `n=3`)**: **`3/3`** successi in budget, copertura cloud `3/3`, **`36,890`** cloud/successo (`110,671` tot), `0` locali, mediana **`62.21s`** (`52.80s-70.35s`).
   - **Delega in chat `agy` (MCP attivo, `n=3`)**: **`1/3`** successi in budget (`p1` `880.69s`; `p2` timeout `900.35s`; `p3` timeout `900.40s` con loop `unittest`), copertura cloud `1/3` (`52,913` su `p1`; **limite inferiore `>= 52,913` cloud per 1 successo**), `275,014` locali, mediana `900.35s`.

3. **`web_pendulum`** (web start-paused, budget `1,200s`, ultima rivalutazione `benchmarks/auto_suite/runs/20261120-154823_receipt_ab/reeval_pendulum_report.json` con `benchmarks/auto_suite/check_pendulum_v2.mjs`, originali in `benchmarks/auto_suite/runs/20261120-154823_receipt_ab/results.json`):
   - **Diretto (MCP disabilitato, `n=3`)**: **`3/3`** successi in budget, copertura cloud `3/3`, **`36,356`** cloud/successo (`109,068` tot: `80,119` in + `28,949` out), `0` locali, mediana **`61.98s`** (`51.70s-63.58s`).
   - **Delega in chat `B_cur` (MCP attivo, ricevuta verbosa, `n=3`)**: **`0/3`** successi in budget (`art=1/3`, `in_budget=1/3`; `p2` e `p3` timeout a `1200.27s` e `1200.37s`), copertura cloud `1/3` (limite inferiore `> 50,946` cloud tot su `0` successi), `230,758` locali, mediana `1200.27s`.
   - **Delega in chat `B_mod` (MCP attivo, ricevuta compatta v1, `n=3`)**: **`1/3`** successi in budget (`art=2/3`, `in_budget=2/3`; `p1` ok in `1078.85s`; `p2` `step` rotto; `p3` ok su disco ma timeout `1200.28s`), copertura cloud `2/3` (`75,591` su `p1+p2`; **limite inferiore `>= 75,591` cloud per 1 successo**), `262,074` locali, mediana `1078.85s`.

4. **`Portal`** (`20261119_ab_portal_opt`, **orchestrazione host esterna**, `benchmarks/hydrogen_3_6_1/runs/20261119_ab_portal_opt/summary.json` + rivalutazione strict `benchmarks/hydrogen_3_6_1/runs/20261119_ab_portal_opt/reeval_strict.json`):
   - **`direct_from_prompt` (MCP disabilitato, `n=1`)**: **`1/1`** `strict`, `92,941` cloud, `0` locali, `110.28s`.
   - **`tandem_from_prompt modified` (`n=3`)**: **`2/3`** `strict` (`r1` pass `24,920` cloud / `2,224.42s` / `240,648` loc; `r2` fail `26,399` cloud / `1,895.25s` / `206,367` loc; `r3` pass `24,631` cloud / `3,508.10s` / `364,861` loc), copertura cloud `3/3` → **`37,975` cloud/successo** (`75,950 / 2`), `811,876` locali. Tempo dei singoli tentativi riusciti: `2,224.42s` (`37.1` min) e `3,508.10s` (`58.5` min); **tempo totale per successo includendo il fallimento `r2`: `3,813.89s` (`63.6` min)**.
   - **`tandem_from_prompt baseline` (`n=3`)**: **`0/3`** `strict` (`r1` `23,753` / `3,071.95s`; `r2` `23,026` / `3,727.75s`; `r3` timeout `4,210.0s` / `20,184` cloud), copertura cloud `3/3` (`66,963` su `0` successi), `1,155,396` locali.

---

## 3. Ottimizzazioni con risparmio misurato vs modifiche di affidabilità

- **Ottimizzazioni con risparmio misurato**:
  - **Compattazione `write_file`** (`TANDEM_COMPACT_WRITES=1` su `Portal`, `benchmarks/hydrogen_3_6_1/runs/20261119_ab_compaction/summary.json`, `n=3` coppie): **`-18.1%` token locali** (`693,349` vs `846,805`) e **`-21.6%` tempo** (`6,377.45s` vs `8,129.25s`), a parità di `state=verified` (`3/3` in entrambe, `e2e=0/3` su entrambe).
  - **Politica `first_turn` su edit esistenti** (`tandem_mcp/server.py`, `tandem_mcp/router.py`, configurazione globale utente di `agy` in nelle istruzioni personali del client): elimina il turno `auto_route` e mantiene il diretto su modifiche a codice esistente anche con richiesta di risparmio cloud (`slugify`: `25.79s`, `27,418` cloud, `0` locali).
- **Miglioramenti di affidabilità**:
  - **`not_evaluated` su prerequisito mancante** (`tandem_mcp/agent.py`, `tests/test_not_evaluated.py`): evita riparazioni inutili senza nascondere `exit=2` di comandi generici. Nel caso storico `web B_save` il timeout era **`480.30s`**; nella **riproduzione offline** su copia dello stesso scenario il job chiude in **`2.83s` con `repairs=0`**, preservando l'artefatto e `tandem:web_check`.
  - **`_web_probe.mjs` start-paused** (`tandem_mcp/_web_probe.mjs`): clicca `Play`/`Start`/`Resume` se la canvas è statica all'avvio (`tests/test_web_check.py`: `20 checks, 0 failures`).
  - **Ricevuta compatta (`TANDEM_COMPACT_RECEIPT=1`)**: la **v1** è stata provata in chat su `web_pendulum` `B_mod` (riletture post-watcher: **`0/2`** contro `1/1` di `B_cur`); le correzioni successive (canale `TANDEM_PROOF_FILE` + `TANDEM_VERIFY_NONCE`, `VERDICT:` prima di `WORKER_CLAIM`, perimetro esplicito e `outcome` su `exit=2`) sono state **verificate offline** (`tests/test_compact_receipt.py` `18/18`, `tests/test_e2e_receipt.py` `11/11`, `tests/test_not_evaluated.py` `18/18`).

---

## 4. Tabella operativa, distinzioni e limiti delle evidenze

> **Implementazione attuale vs raccomandazione**: oggi il comportamento implementato in `tandem_mcp/server.py` e nelle istruzioni personali del client mantiene diretti gli edit su codice esistente anche quando chiedi di risparmiare cloud, ma consente ancora di delegare **generazione sostanziale da zero** con `privilegia il risparmio di token cloud`. Sulla base dei risultati in chat `agy`, la nostra **raccomandazione operativa** è invece usare il **diretto per tutte le attività quotidiane** (compresa la generazione da zero), riservando la delega locale al vincolo esplicito `solo locale`.
>
> **Significato di «solo locale» in chat `agy`**: il messaggio iniziale dell'utente raggiunge comunque l'orchestratore cloud (`agy`) al turno 1; `solo locale` impone che da quel momento il router (`tandem_mcp/router.py`) deleghi al modello locale **senza alcun fallback cloud**.

| Attività | Percorso consigliato | Evidenza | Compromesso |
| :--- | :--- | :--- | :--- |
| Richiesta ordinaria («usa Tandem») | **Diretto al turno 1** | Con MCP attivo su edit/piccoli moduli: `23.09s-27.89s`; su `Boids`/`Cron`/`Pendolo` (MCP disabilitato): `9/9` (`48.85s-70.35s`) | Usa token cloud (`~21K-37K`), ma massimizza velocità e tasso di successo |
| Modifica mirata a codice esistente (anche con «risparmia cloud») | **Diretto al turno 1** | `slugify` `25.79s` (`27.4K`) vs `discount.py` delegato `105.42s` (`33.5K`) | Evita `+6.5K-18.5K` token cloud di schema, watcher e riletture |
| Generazione da zero (`preferisco risparmiare token cloud`) | **Diretto** (raccomandato; oggi ancora delegabile se sostanziale) | In chat `agy`: `-0.95%` su `Boids`, peggiorativo su `Cron` e `Pendolo` | Risparmio cloud non ripetibile in chat vs `+8.6-19` min |
| Vincolo **`solo locale`** (niente fallback cloud dopo turno 1) | **Delegal modello locale** | Funzionante su file/test locali con `host_runner` | Attesa `3-60` min e rischio timeout su logica complessa |

- **Letture massive (`digest_*`)**: in `benchmarks/auto_suite/runs/20261120-080404_auto_eval_v2/results.json` (`eval2_explain_hooks`), `B_auto_mandatory` (`local_digest`) ha usato `38,501` cloud in `30.54s` contro `24,261` cloud in `23.71s` di `A_direct`; manca una prova controllata in cui `digest_*` riduca davvero i token cloud in chat `agy` (**aperto**).
- **Generazione complessa**: esiste un vantaggio cloud misurato (`-59.1%`) **solo** su `Portal` con orchestrazione host esterna (`63.6` min totali per successo `strict`), non replicato nella normale chat `agy`.
- **Confronto con Atomic Agent Fusion**: in [`COMPARISON.md`](./COMPARISON.md) il confronto è **solo qualitativo sui README pubblici**, senza benchmark empirici di token, qualità o tempi (**aperto**).

---

## Decisione finale ed esperimento futuro

Con i dati di oggi, **nella normale chat `agy` nessuna attività ha ancora mostrato un vantaggio materiale e ripetibile di token cloud delegando al modello locale**: anche quando l'utente chiede risparmio cloud, conviene mantenere il **diretto** come scelta pratica su tutte le attività quotidiane e riservare la delega al vincolo **`solo locale`**.

**Unico esperimento futuro (non avviato) che potrebbe cambiare la decisione**:
- **Riferimento e varianti**: confronto a **5 coppie controbilanciate su almeno 2 prompt nuovi** (`n=5` per prompt) nella stessa chat `agy`, tra **diretto con `tandem-mcp` attivo** (riferimento) e **delega con schema `delegate` caricato in anticipo (non-lazy)**, mantenendo identica la versione della ricevuta compatta v2 (`TANDEM_COMPACT_RECEIPT=1`) in tutte le varianti e conteggiando i token dello schema anche nei turni/run in cui `delegate` resta inutilizzato.
- **Criterio prefissato (budget `900s`)**: la delega deve ottenere **almeno `>= 30%` in meno di token cloud per successo entro `900s`**, includendo i costi dei fallimenti, con **qualità e tasso di successo almeno pari al riferimento** (`>= 80%`, cioè almeno **4 consegne corrette su 5** per prompt). Se in una replica manca `usage` cloud, il criterio **non è verificabile** (a meno che il limite inferiore calcolato sui soli run con `usage` violi già il risparmio del `30%`, nel qual caso l'ipotesi è comunque respinta).
