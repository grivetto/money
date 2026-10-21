# P33 — canary: lock a prenotazione (status e close non devono MAI essere rifiutati da un open/close in corso)

**Origine:** finding non bloccante della review P30 (commit `9d3c72d4`), confermato leggendo il codice attuale.
**Priorità:** alta per rischio — oggi una RIDUZIONE di rischio (close) può essere rifiutata.

## Il problema (verificato sul codice)
`src/money/esecuzione/stato.py:115-138`: `lock_esclusivo` è un `flock(LOCK_EX|LOCK_NB)` su `<stato>.lock`; chi non lo prende riceve `LockOccupato`.
In `scripts/canary_carry.py` il lock avvolge l'INTERO flusso ordini:
- `open` (riga 424): dalla lettura dello stato fino al salvataggio finale, incluse le attese fill (60s + 45s, righe 451/465/489/503) → fino a ~2,5 minuti di lock trattenuto;
- `close` (riga 604): attese fill 60s+60s (righe 616/636) → fino a ~2 minuti;
- `status` (riga 554): lock esclusivo anche solo per leggere+aggiornare `last_*`.

Conseguenze con `LOCK_NB` (righe 547-549, 595-597, 664-666):
1. il cron `status --quiet` (ogni 10') durante un open/close **esce in errore** con LOCK OCCUPATO;
2. un `close` durante un open/close viene **RIFIUTATO**: per una riduzione di rischio è il comportamento sbagliato;
3. un secondo `close` concorrente viene rifiutato (questo è CORRETTO e va mantenuto).

## Obiettivo
Sostituire il lock «per tutto il flusso» con il **pattern di prenotazione (claim)**:
1. lock breve: leggi stato → verifica claim → scrivi claim (`opening`/`closing` con ts+pid) → **rilascia**;
2. lavoro lungo (ordini, attese fill, riconciliazioni) **senza lock**;
3. lock breve: scrivi lo stato finale → rilascia.

Il lock diventa una sezione critica di **millisecondi**, mai di minuti.

## Design richiesto (da implementare in canary_carry.py, non in stato.py)

### Stato (compatibile: campi nuovi solo in aggiunta)
- Nuovo campo `claim`: `{"tipo": "opening"|"closing", "ts": "<iso>", "pid": <int>}`, scritto SOTTO lock.
- Stato senza `claim` = libero (retro-compatibile con lo stato esistente del canary).
- Costante `CLAIM_TIMEOUT_S = 900` (15 min; un open reale resta sotto ~3 min): oltre questa soglia il claim è **stantio**.

### `open`
- Sezione 1 (lock breve): se `status == open` → exit come oggi («stato già open»). Se `claim` fresco (`opening` o `closing`) → **exit 2 con messaggio esplicito**: «operazione in corso (TIPO, pid N, da Xs) — apertura rifiutata». Se `claim` stantio → scrivere evento `claim_stantio` (con tipo/pid/età) e procedere. Se libero → scrivere `claim=opening` → release.
- Flusso ordini come oggi (P30: reprice, unwind ecc.), **senza lock**.
- Sezione 2 (lock breve): salva stato finale (`status=open` con i dati, oppure stato di errore/unwind come oggi) e **rimuovi il claim**.

### `close`
- Sezione 1 (lock breve): se `claim == opening` fresco → **exit 2 esplicito**: «apertura in corso (pid N, da Xs): nessuna posizione completa da chiudere — attendere» (NON è LOCK OCCUPATO: è la condizione reale). Se `claim == closing` fresco → exit 2 «chiusura già in corso (pid N)». Se stantio → evento `claim_stantio` e procedi. Altrimenti scrivi `claim=closing` → release.
- Flusso di chiusura come oggi (P30: close atomica, spot solo a perp chiusa, ecc.), **senza lock**.
- Sezione 2 (lock breve): salva stato finale (closed / close_incompleta / esiti) e **rimuovi il claim**.

### `status`
- Deve uscire **sempre 0** quando l'API risponde — mai LOCK OCCUPATO.
- Lettura senza lock accettata (le scritture sono atomiche: `salva()` = tmp+fsync+os.replace, quindi un lettore vede sempre il file vecchio o nuovo, mai a metà).
- L'aggiornamento dei campi `last_*`: tentare con lock breve; se occupato → **non scrivere** e continuare (oppure riprovare una volta); MAI uscire in errore per questo.
- Il claim attivo (se presente) va mostrato nella riga di stato («claim: opening pid 123 da 42s»).

## Test richiesti (ognuno PRIMA rosso, poi verde — documentare nel LEGGIMI)
Mock offline con latenza iniettata (pattern P30) + lock reale su tmp_path:
1. `status` mentre un `open` è in flusso (lock NON trattenuto a lungo) → legge, rc=0 (pre-fix: LOCK OCCUPATO).
2. `close` mentre `opening` fresco → exit 2 con motivo «apertura in corso» (pre-fix: LOCK OCCUPATO/exit diverso).
3. secondo `close` mentre `closing` fresco → exit 2 «chiusura già in corso».
4. doppio `open` concorrente → secondo rifiutato dal claim, primo completa; nessun lost update (il claim non lascia stato incoerente).
5. claim stantio (ts oltre timeout) → il successivo procede e registra evento `claim_stantio`.
6. `open` completo → alla fine claim rimosso, stato `open` (regressione P30).
7. `close` completo → claim rimosso, stato `closed` (regressione P30).
8. Tutti i 13 test di `tests/test_canary_carry_p30.py` restano verdi.

## Criteri di accettazione (per Merlino)
1. Fix + test 1-8 con output `pytest -q` per esteso e rosso pre-fix documentato (`LEGGIMI.md` con mappa test→scenario→esito).
2. Tabella scenari nel LEGGIMI: open/close/status × (libero | opening fresco | closing fresco | claim stantio) → comportamento atteso.
3. `status --quiet` NON deve mai produrre LOCK OCCUPATO (verifica esplicita nel LEGGIMI con il comando read-only che Artù rieseguirà).
4. Stato compatibile: `data/canary/…/stato.json` esistente resta leggibile; `claim` assente = libero.
5. Handoff `merlino/handoff/P33/` con `MANIFEST.sha256` + `READY` (ultimo file).
6. Zero ordini, zero chiavi, zero write su `~/money` (lavoro in `~/merlino-scratch/p33/`).

## Fuori perimetro
- P32 (M3/M4/M6/M9/M10/B1-B8 di carry_chiudi) resta dopo questa.
- Nessuna modifica a stato.py (il lock resta com'è; cambia solo l'uso nel canary).
- Nessuna modifica alla logica ordini/attese/verifiche di P30.