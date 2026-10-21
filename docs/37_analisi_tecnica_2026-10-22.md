# 37 — Analisi tecnica e proposta di migliorie (nota esterna, Manus AI) — 2026-10-22

**Fonte**: `/home/sergio/Analisi tecnica e proposta di migliorie — 2026-10-22.docx`
(sha256 `28cdc409fd26af2b77d97a947ce7d9bce52b830322f3fbfda8787a2483e12f62`, 15 157 byte; ricevuta 22/10/2026 00:06).
**Analisi eseguita dall'autore**: branch `main`, commit `5eef5706`.
**Trascrizione**: integrale, ripulita dai numeri di nota orfani (`1 2`, `2`, `3`); contenuto invariato.

## Disposition — stato di adozione (verifica sul campo, 22/10)

| # | Punto | Stato | Evidenza |
|---|---|---|---|
| P0.1 | CI verde + lint deterministico | **FATTO** | `c93dde3c`: F541 in `scripts/e6_momentum_estremo.py`, escape docstring dei test; ruff/compileall/pytest/`-O` rc=0 |
| P0.2 | Deriva dipendenze | **FATTO** | `79853318`: `requirements-dev.lock` (universal, fork numpy <3.12 / ≥3.12) + CI a matrice 3.11/3.12/3.14 che installa dal lock |
| P0.3 | Fail-closed percorso capitale | Aperto (settimane 2–3) | assert già banditi da `src/` (guardia AST); restano 4 assert fuori (scripts×2, ops, fabbrica) e 16 `except Exception` in 7 file da classificare |
| P1.4 | Discrepanze numeriche docs | **FATTO** | `5fcc0a8d`: conteggi 726→1021 (README×4 + scheda) |
| P1.5 | Coverage | Aperto (backlog) | |
| P1.6 | Separazione offline/rete/live | Aperto (backlog) | |
| P1.7 | Provenienza artefatti | Parziale | manifest già in uso per consegne/prove; schema CI da definire |
| P2.8 | Legacy / retention | Aperto (backlog) | i 2 file non compilabili in `legacy/` sono noti e attesi |
| P2.9 | TODO mark/index | Aperto (backlog) | nota: `carry_delta_neutral` oggi è fail-closed (`NotImplementedError`), nessun fallback silenzioso |
| P2.10 | Controlli statici | Aperto (backlog) | |

Extra trovato in verifica (fuori nota): `media()` non deterministica su Python <3.12 (somma naive) → `math.fsum` (`b17c8f7a`).

---

## Trascrizione della nota

# Analisi tecnica e proposta di migliorie — 2026-10-22
## Stato osservato
L’analisi è stata eseguita sul branch main, commit 5eef5706dd1d58a9cf1b898b095a9707b9355d35, dopo un clone pulito del repository. Il progetto ha una base migliore della media per un sistema di ricerca quantitativa: separa codice attivo, prove, documentazione e legacy/; concentra il dominio in src/money/; usa funzioni pure per costi e cancello; protegge il percorso di esecuzione con preflight, stato persistente atomico, lock e ledger append-only; mantiene una CI con test normali e test con python -O.
La verifica locale ha prodotto questi risultati:
python -m pip install -e ".[dev]": riuscito.
python -m pytest -q: 1.021 test superati, con 2 SyntaxWarning nelle docstring di tests/test_contabilita.py e tests/test_rischio.py.
python -O -m pytest -q: 1.021 test superati, ma con il warning di pytest che segnala l’uso di assert nei test quando gli assert vengono rimossi dall’ottimizzatore.
python -m compileall -q src scripts ops: riuscito.
ruff check .: fallito per F541 in scripts/e6_momentum_estremo.py:94.
python -m compileall -q .: fallito in due file congelati sotto legacy/, che contengono sintassi non compilabile. La CI attuale compila correttamente solo lo scope mantenuto.
Quindi il progetto non è completamente verde al momento: il problema più immediato è il lint rosso, mentre la suite funzionale e la compilazione dello scope CI sono verdi.
## P0 — da correggere prima di aggiungere nuove strategie
### 1. Ripristinare una CI realmente verde e rendere il lint deterministico
Evidenza. La CI esegue ruff check ., ma sul commit analizzato il comando fallisce per una f-string senza placeholder in scripts/e6_momentum_estremo.py:94. La correzione è minima: rimuovere il prefisso f oppure aggiungere un controllo CI che impedisca il merge quando il lint è rosso.
Miglioria proposta. Correggere il warning F541 e aggiungere un job o uno step ruff format --check solo se il progetto decide di adottare anche la formattazione automatica. In caso contrario, non introdurre un secondo standard: l’obiettivo immediato è mantenere ruff check . verde e affidabile.
Criterio di accettazione. ruff check ., python -m compileall -q src scripts ops, python -m pytest -q e python -O -m pytest -q devono terminare con codice zero in un checkout pulito.
### 2. Bloccare la deriva delle dipendenze
Evidenza. pyproject.toml dichiara solo vincoli inferiori, per esempio ccxt>=4.0, pytest>=8.0 e ruff>=0.5, mentre la CI usa un singolo interprete Python 3.12. Il pacchetto dichiara invece requires-python = ">=3.11". Questo lascia aperta la possibilità che due run installino versioni diverse o che Python 3.11 smetta di funzionare senza che la CI lo segnali.
Miglioria proposta. Scegliere una strategia esplicita:
mantenere vincoli larghi ma committare un lockfile di sviluppo, con aggiornamento periodico controllato; oppure
fissare almeno le dipendenze critiche e aggiornare tramite PR automatizzate.
In entrambi i casi, estendere la matrice CI a Python 3.11 e 3.12. Se Python 3.11 non è più supportato, correggere requires-python e la documentazione invece di lasciare una promessa non verificata.
Criterio di accettazione. La CI deve eseguire la suite su ogni versione Python dichiarata supportata e deve rendere riproducibile l’ambiente di sviluppo da un clone pulito.
### 3. Rendere fail-closed gli errori nel percorso capitale/ordini
Evidenza. Nel codice attivo esistono numerosi except Exception, inclusi moduli di esecuzione, raccolta funding e money.jev.py; quest’ultimo documenta esplicitamente un comportamento “fail-open”. Inoltre gli script operativi contengono assert che non sono coperti dal test AST attuale, che protegge soprattutto src/.
Miglioria proposta. Fare una revisione mirata soltanto del percorso che può influire su capitale, ordini, stato e riconciliazione:
sostituire gli except Exception con eccezioni specifiche dove l’errore deve bloccare l’azione;
classificare ogni fallback come fail_closed, degraded_read_only o best_effort_notification;
eliminare gli assert dagli entrypoint operativi e trasformarli in eccezioni applicative esplicite;
estendere tests/test_no_runtime_assert.py a scripts/, ops/ e fabbrica/, oppure dichiarare formalmente quali percorsi sono esclusi;
aggiungere un test per ogni errore di rete, stato corrotto, risposta incompleta e riconciliazione non conclusiva.
Criterio di accettazione. Con python -O, un controllo economico o di sicurezza non può sparire; ogni eccezione catturata nel percorso capitale deve produrre un evento nel ledger o un arresto osservabile.
## P1 — affidabilità, sicurezza e osservabilità
### 4. Eliminare le discrepanze numeriche nella documentazione
Evidenza. Il README riporta ancora 726 passed nella sezione di testing, mentre la stessa verifica sul commit corrente produce 1.021 test superati. La documentazione contiene anche più snapshot temporali e descrive versioni diverse dello stato del sistema.
Miglioria proposta. Non mantenere conteggi di test scritti a mano nel README. Sostituirli con un badge o con un comando riproducibile; se serve uno snapshot operativo, dichiarare sempre data, commit e comando che lo ha prodotto. Aggiungere un controllo CI che confronti le statistiche documentate solo se il formato resta semplice e non fragile.
Criterio di accettazione. Ogni numero operativo nel README deve avere una data e un commit, oppure deve essere generato automaticamente.
### 5. Aggiungere coverage utile al dominio finanziario
Evidenza. La suite è ampia, ma nel workflow non è presente un report di coverage. Il documento precedente aveva già identificato questa lacuna come miglioramento successivo. Senza coverage è difficile distinguere la quantità di test dalla copertura effettiva dei rami fail-closed, della riconciliazione e dei casi degeneri.
Miglioria proposta. Aggiungere pytest-cov con report XML/HTML per src/money, senza imporre subito una soglia globale artificiale. Dopo due o tre run, introdurre soglie separate per:
contabilità e riconciliazione;
costi, rischio e cancello;
esecuzione e stato;
ricerca e script di sola analisi.
Criterio di accettazione. Ogni PR pubblica il report di coverage e include test per i rami critici: dati corrotti, fee scadute, stato live illeggibile, lock occupato, fill duplicato e ordine fuori sequenza.
### 6. Separare in modo più netto offline, rete pubblica e credenziali
Evidenza. La suite corrente passa offline, ma il repository contiene numerosi script operativi, accessi a OKX, SSH, Docker, systemd e notifiche. Nei moduli ops/ compaiono comandi costruiti per bash -c e invocazioni SSH; questo è coerente con un pannello operativo, ma amplia la superficie d’attacco e rende importante distinguere ciò che è sicuro eseguire in CI da ciò che richiede una macchina autorizzata.
Miglioria proposta. Organizzare tre categorie di test e comandi:
offline: sempre eseguibili in CI, senza rete né segreti;
network: eseguibili manualmente o in un job isolato, con endpoint espliciti e timeout;
live: mai eseguiti dalla CI standard, con credenziali assenti per default e doppio controllo del flag di produzione.
Per gli script operativi, preferire argv strutturati a shell concatenate; quando bash -c è inevitabile, usare allowlist di comandi e parametri, logging dell’azione e utente di servizio con privilegi minimi.
Criterio di accettazione. Un checkout CI non deve poter leggere chiavi, inviare ordini o eseguire un comando remoto; i test devono dimostrare che l’assenza di credenziali produce un arresto esplicito e non un fallback ambiguo.
### 7. Rendere verificabile la provenienza degli artefatti di ricerca
Evidenza. prove/ contiene numerosi JSON e JSONL versionati, inclusi file di grandi dimensioni, ma non esiste nel workflow un controllo generale che leghi ogni artefatto a commit, configurazione, versione dipendenze e fonte dati. Il cancello documenta bene i limiti statistici, ma la riproducibilità della selezione dipende anche dalla provenienza dell’input.
Miglioria proposta. Definire un manifest per ogni run di ricerca con:
commit Git;
Python e versioni delle dipendenze;
exchange, endpoint e timeframe;
intervallo temporale e hash dei dati;
parametri pre-registrati;
seme casuale;
risultato e verdetto;
timestamp UTC e modalità offline/network/live.
Validare il manifest in CI con uno schema versionato. Non alterare gli artefatti storici: aggiungere una migrazione o una versione di formato per i nuovi run.
Criterio di accettazione. Un risultato senza manifest completo deve essere marcato come non riproducibile e non può essere promosso automaticamente.
## P2 — manutenzione e scalabilità del repository
### 8. Isolare meglio legacy/ e ridurre l’attrito del repository
Evidenza. legacy/ è correttamente escluso dal lint e dalla compilazione CI, ma due file storici non compilano. Nel repository sono inoltre presenti artefatti JSON/JSONL molto grandi; il clone supera circa 100 MB e diversi file di evidenza superano 1 MB.
Miglioria proposta. Formalizzare legacy/ come archivio non eseguibile:
aggiungere un README con stato “read-only / non supportato”;
impedire che venga importato dal codice attivo;
fornire un comando separato verify-legacy che riporti i file non compilabili senza far fallire la CI principale;
valutare Git LFS o un archivio esterno per scansioni grezze ripetitive, mantenendo nel Git gli hash, i manifest e gli artefatti curati.
Criterio di accettazione. Il percorso attivo deve essere verificabile senza leggere legacy/; l’archivio deve essere dichiaratamente non eseguibile e gli artefatti pesanti devono avere una politica di retention.
### 9. Chiudere i TODO che possono cambiare il risultato di una misura
Evidenza. src/money/ricerca/carry_delta_neutral.py contiene un TODO per sostituire un valore con il caricamento reale di mark/index. Un fallback di questo tipo può alterare PnL, neutralità delta o costi senza essere evidente nel risultato finale.
Miglioria proposta. Trasformare il TODO in una decisione esplicita:
implementare il caricamento reale e aggiungere fixture;
oppure bloccare la misura quando mark/index non è disponibile;
in nessun caso usare un valore sostitutivo silenzioso nel percorso che produce un verdetto.
Criterio di accettazione. Una misura deve registrare la fonte di mark/index e fallire con un motivo leggibile quando la fonte manca o non è coerente.
### 10. Introdurre controlli statici leggeri e mirati
Miglioria proposta. Dopo aver stabilizzato lint e dipendenze, aggiungere senza appesantire il progetto:
pip check già presente, mantenuto come gate;
pip-audit o equivalente in un job non bloccante iniziale, poi bloccante per vulnerabilità rilevanti;
controllo di segreti sui commit e sugli artefatti;
type checking almeno su src/money/esecuzione, contabilita, dati, costi e cancello;
pre-commit soltanto se il team accetta il relativo costo operativo.
L’ordine è importante: prima correggere il lint attuale e rendere riproducibile l’ambiente, poi introdurre nuovi gate. Una CI rumorosa verrebbe ignorata e contraddirebbe l’obiettivo del progetto.
## Roadmap consigliata
### Prima settimana
Correggere F541 e ripristinare ruff check . verde.
Aggiornare i conteggi e gli snapshot del README.
Estendere la CI a Python 3.11 e 3.12, oppure correggere la versione minima dichiarata.
Aggiungere un lockfile o una policy di pinning documentata.
### Settimane 2–3
Audit fail-closed dei moduli di esecuzione, stato, riconciliazione e jev.
Estendere il controllo anti-assert ai veri entrypoint operativi.
Aggiungere coverage per il dominio finanziario e casi di errore mancanti.
Separare job offline, network e live.
### Settimane 4–6
Introdurre manifest e schema per gli artefatti di ricerca.
Formalizzare la quarantena di legacy/ e la retention degli artefatti pesanti.
Chiudere il TODO mark/index con test e provenienza registrata.
Attivare audit dipendenze, secret scanning e type checking mirato.
## Decisione sintetica
Il progetto non ha bisogno, come prima mossa, di altre strategie o di più automazione. La priorità è rendere affidabile il sistema che già esiste: CI verde, ambiente riproducibile, documentazione coerente, percorsi live sempre fail-closed e artefatti con provenienza verificabile. Solo dopo questi interventi ha senso aumentare la superficie di ricerca o il grado di automazione operativa.

_«References»: sezione vuota nel docx originale (nessun riferimento esplicito)._

