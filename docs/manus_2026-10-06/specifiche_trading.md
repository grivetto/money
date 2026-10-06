# Denaro — Specifiche di trading applicate

**Allegato tecnico per analisi esterna (Manus AI)** · 2026-10-06 · nessun segreto incluso
· stato verificato sugli impianti reali (non stimato).

Accompagna il diagramma `architettura_denaro.html` / `architettura_denaro.png`.
Descrive **le specifiche che il sistema applica oggi, concretamente, al percorso del denaro**:
rischio, costi, esecuzione, promozione delle strategie, stato corrente.

---

## 1. Principio fondante (il vincolo che domina tutto)

> Prima si misura se un edge esiste — **ai costi reali dell'account** — poi lo si automatizza.

Sotto il nome *denaro* si sono succedute quattro codebase; nessuna ha mai guadagnato un euro
perché si costruiva prima il sistema e si cercava dopo qualcosa da catturare. La rifondazione
(23–30/09/2026) inverte l'ordine: **la pipeline di ricerca e il suo cancello di promozione sono
il prodotto**; l'esecuzione automatica esiste già ed è tenuta a terra finché non arriva un edge.

Conseguenza diretta e dichiarata: **oggi nessuna strategia è «promossa»** e il capitale
(~1.100 EUR) lavora solo su un esperimento di taglia minima (canary). È l'headline onesta.

## 2. Mandato di rischio (applicato)

| Regola | Valore | Note |
| :--- | :--- | :--- |
| Rischio per trade | **2%** del capitale della strategia | il sizing lo impone, non lo suggerisce |
| Stop giornaliero | **−3%** | raggiunto → la giornata operativa finisce |
| Drawdown massimo | **−10%** | raggiunto → revisione e stop della strategia |
| Leva | **1×** | niente margine aggressivo; perp in *isolated* |
| Conti | **un bot per conto** | regola dura, niente collisioni di ordini |
| Perdite | di mercato accettate (costo del business); **operative/ingegneristiche vietate** | root-cause accountability su ogni anomalia |

Principio operativo: hard-stop automatici, sizing dinamico, capitale isolato per strategia/account.
Il risk manager e il kill-switch non si aggirano «nemmeno per un test».

## 3. Strumenti, conti, chiavi

- **Exchange**: OKX regione **EEA** (`eea.okx.com`). Spot + **X-Perps** (acctLv 2): è il conto su
  cui sono state verificate le fee reali (vedi §4) e su cui girano canary e piani del carry.
- **Conti**: account main + sub-account isolati per strategia. Fondi separati per finalità.
- **Chiavi API**: permessi minimi, **IP-whitelist** (solo IP dei nodi autorizzati).
  - Chiave **read-only** dedicata per banco a secco e riconciliazioni (strutturalmente incapace di inviare ordini).
  - Chiave con permesso di trade **solo** per l'esecuzione autorizzata (oggi: canary C1).
  - Regola: chiavi residenti sui nodi, **mai in git/log/chat**; mai chiavi morte o simboli disabilitati in produzione (incidenti passati, ora preflight obbligatorio).
- **Un bot per conto**: un solo processo con permesso di ordine per conto — per costruzione.

## 4. Costi applicati (misurati dall'account, non da listini)

| Tariffa (per lato) | maker | taker | round-trip misto | Fonte |
| :--- | ---: | ---: | ---: | :--- |
| spot OKX EEA | 0,20% | 0,35% | **0,550%** | letta dall'account (`privateGetAccountTradeFee`) |
| conto con X-Perps | 0,08% | 0,10% | **0,180%** | assunzione conservativa di progetto (default) |
| perp/swap | 0,02% | 0,05% | **0,070%** | dall'account (con derivati attivi) |

Regole economiche applicate:

- **Il pedaggio è il vero giudice**: ogni misura di edge include fee **e slippage**; niente risultati «lordi».
- **Soglia ordine sensato**: `min_notional` 1 €; *sotto ~4 € di capitale per operazione non esiste un ordine economicamente sensato* (il pedaggio mangia tutto).
- **Soglia del cancello**: expectancy netta **≥ 3× il costo di round-trip** (criterio 6, vedi §5). Sotto, la strategia non parte — per codice.
- **Funding EEA ≠ funding globale**: sui dati del venue, BTC/ETH hanno funding negativo → il carry si sceglie sui dati reali, non sulla letteratura.

## 5. La pipeline di promozione (come una strategia arriva al denaro)

```
IDEA → spec PRE-REGISTRATA (varianti dichiarate prima)
     → misura su dati reali (fee + slippage inclusi, walk-forward, fuori campione)
     → CANCELLO a 8 criteri (codice vincolante: if not giudica(esito): return)
     → banco a secco (dry-run live, chiave read-only)
     → canary di taglia minima (denaro vero)
     → scala (deploy gated sull'owner)
```

Il **cancello** (`src/money/cancello.py`), tutti e 8 obbligatori:

| # | Criterio | Soglia |
| :--- | :--- | :--- |
| 1 | Numerosità | ≥ 30 operazioni (sotto → «insufficiente», non archiviata) |
| 2 | Expectancy | IC bootstrap 90%, estremo inferiore > 0 |
| 3 | t-statistic | > 1,65 |
| 4 | Profit factor | > 1,20 |
| 5 | Drawdown | ≤ 25% |
| 6 | Pedaggio coperto | expectancy netta ≥ 3× costo round-trip |
| 7 | Rilevanza economica | ≥ 10 EUR/anno su 1.000 EUR di riferimento |
| 8 | Indipendenza dai blocchi | via il blocco migliore, expectancy ancora ≥ 0 |

Il protocollo «referee ostile» (docs/18) blocca per costruzione: look-ahead, survivorship,
data snooping, overfitting, selezione multipla (correzione DSR per le scansioni massive).
Ogni misura nasce da una voce nel registro **prima** del primo numero.

## 6. Protezioni operative (percorso del denaro)

- **Idempotenza**: nessun ordine senza chiave di idempotenza (un retry non duplica un ordine).
- **Preflight obbligatorio**: saldo, `min_notional`, simbolo abilitato, chiave valida — prima di ogni sessione/ordine.
- **Banco a secco**: ogni 5 minuti il sistema legge i saldi reali con chiave read-only, calcola cosa farebbe, e logga `PASS/FAIL` + riconciliazione (ordini aperti, posizioni). È la prova generale permanente del layer live.
- **Zero silenzi**: ogni componente critico ha heartbeat + watchdog; un componente giù senza alert è trattato come incidente. Alert su un canale Telegram unico (rate-limited).
- **Fail-closed** su test e integrazione; **fail-open solo** per il gate di advisoring JEV (non tocca il denaro).
- **Nessun LLM nel percorso caldo**: gli agenti AI lavorano in ombra (ricerca, review, dispatching); a decidere size/ordini è codice deterministico.
- **Deploy versionato**: systemd e cron vivono nel repo (`deploy/`); niente «path drift».

## 7. L'esecuzione corrente: canary C1 (l'unico denaro a rischio)

- **Cosa**: carry funding su DOGE — **spot long + X-Perp short** (delta-neutrale, 1×, isolated).
- **Quando**: aperto il 01/10/2026 — **prima esecuzione reale del progetto**, intenzionalmente a **taglia minima**.
- **Monitor**: riconciliazione periodica con l'exchange (posizioni, ordini, fill, funding incassato); alert Telegram.
- **Review: 15/10/2026** con **criteri pre-dichiarati** (docs/16) — esito verde → si discute la scala multi-pair (piano in docs/20, gated sull'owner); esito rosso → si chiude e si archivia con evidenza.
- **Rischi dichiarati**: funding che gira negativo, liquidazione del perp (mitigata: 1×, isolated, margine monitorato), rischio operativo di *esecuzione spot+perp paralleli*.

## 8. Forward-test paper (nessun denaro)

- **17 bot paper** su 3 nodi (mc2 7 · nuvola 6 · MARCODG1 4): stesse regole dei bot reali, **fill simulati** con fee e slippage reali (`PaperExchange`), candele da OKX pubblica.
- Serve a validare l'operatività e le uscite dei bot trend in condizioni live **senza rischio**: la flotta reale è spenta finché un edge non passa il cancello.

## 9. Stato al 06/10/2026 (numeri verificati)

| Voce | Stato |
| :--- | :--- |
| Capitale | ~1.100 EUR (deposito 03/10), riconciliato read-only |
| Strategie promosse | **0** — tutte le famiglie testate archiviate o insufficienti (P1–P14) |
| Esperimento vivo | canary C1 (carry DOGE), giorno ~6/14 |
| Ricerca | ultima scansione sistematica a 512 tentativi con correzione per selezione multipla: **0 candidati** |
| Paper | 17 bot, forward-test attivo |
| Infra | fabbrica ≈140.000 tiri (tick 3 s), job-store, gate JEV, 533 test offline, ruff pulito |
| Guardrail | banco dry-run PASS ogni 5' · health dei nodi verde · alert Telegram attivi |

## 10. Invarianti non negoziabili

1. Nessuna esecuzione prima di un edge promosso (canary = esperimento firmato, non promozione).
2. Nessuna affermazione di performance senza **riconciliazione con l'exchange**.
3. Nessun capitale configurato che l'account non ha.
4. Nessun ordine senza chiave di idempotenza.
5. Nessuna telemetria che legge come un fossile.
6. Nessun LLM nel percorso caldo.
7. Nessun path drift: systemd e cron versionati.
8. Nessuna soglia abbassata per far passare qualcosa.

## 11. Dove un aiuto esterno serve (domande per Manus)

1. **Metodo**: il cancello (8 criteri) + pre-registrazione + correzione per selezione multipla sono abbastanza forti? Buchi metodologici?
2. **Ricerca**: con pedaggio spot ~0,55% round-trip (0,07% via perp), dati daily/4h e capitale ~1k EUR — quale classe di edge ha più probabilità di passare il cancello? Suggerimenti concreti e testabili.
3. **Infrastruttura**: orchestrazione eventi vs polling 3 s; rilevare deviazioni silenziose; formato dei brief per agenti senza contesto.
4. **Codice**: review libera del repository (pubblico: `github.com/grivetto/money`).

---

*Riferimenti interni: `SCHEDA_PROGETTO.md` (quadro d'insieme) · `docs/02` (banco a secco) ·
`docs/16` (canary) · `docs/18` (protocollo ricerca) · `docs/20` (scala carry) ·
`prove/REGISTRO_ESPERIMENTI.md` (evidenze congelate).*
