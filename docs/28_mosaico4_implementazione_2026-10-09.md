# 28 — MOSAICO-4: cosa è stato implementato e cosa è rinviato (2026-10-09)

Documento ricevuto: `~/MOSAICO-4 — sistema di trading event-driven per quattro macchine.docx`
(v0.1, «concept da validare»). Spec congelata: `coda_catena/MOSAICO4_v1.md`.

## Lettura critica (prima di scrivere codice)

Il documento è il **terzo** in due giorni. I primi due (`Analisi tecnica…`, `Suggerimenti
per Hermes…`) dicevano entrambi di **smettere di aggiungere complessità** e consolidare su
**un solo percorso di esecuzione** — cosa chiusa con P0 (`invio.py` + `coordinatore.py`).
Un «sistema event-driven per **quattro macchine**» va nella direzione opposta.

Il documento stesso risolve la tensione al §401 (*«nessun modulo live prima del simulatore
e dei test di recovery»*) e al §410 (ordine: spec → simulatore → shadow → canary → scala).
Quindi è stato implementato il **nucleo deterministico** (§11), **su una macchina**, dietro
i guardrail di P0. La distribuzione a quattro nodi resta **traguardo documentato**.

## Fatto — nucleo `src/money/mosaico/` (§11 del backlog)

| Modulo | Contenuto | Test |
|---|---|---|
| `model.py` | `Leg`, `HedgeGroup` (+`net_delta`, `delta_relativo`), `EconomicsSnapshot` | ✅ |
| `economics.py` | `valuta()` = regola §3.4; `scenari()` favorevole/base/**avverso**; `not_economicamente_fattibile()` (§5) | ✅ |
| `signal.py` | `funding_forecast` = min(media 3, q25 di 30) §3.1; `basis` §3.2; `esecuzione_ammissibile()` §3.3 | ✅ |
| `state_machine.py` | §7 completo (13 stati normali + 5 incidenti), `transizione()`, `puo_entrare()`, `verifica_invarianti()` (§302-309) | ✅ |

**28 test** (`tests/mosaico/test_nucleo.py`), con un test che fa **scattare** ogni regola:
funding positivo ma netto sotto soglia ⇒ niente apertura; spread/depth/slippage/TTL/latenza
⇒ rifiuto; transizione vietata; stato terminale; gamba B non coperta ⇒ `UNWIND_REQUIRED`;
kill da qualsiasi stato; delta oltre soglia dura ⇒ eccezione; saldo non riconciliato ⇒
eccezione; posizione non confermata ⇒ eccezione.

Suite totale: **603 → 641 test**, e **641 verdi anche con `python -O`**. `ruff check .` pulito.

### Un buco reale trovato mentre testavo

Lo scenario **avverso** con soli fattori (funding ×0,5, slippage ×2) **non andava mai
negativo** quando il base passava col margine 3×: il controllo sul budget avverso non
morderebbe **mai** — una condizione del §3.4 che sembrerebbe implementata e non lo sarebbe.
Corretto applicando il **buffer eventi avversi** = costi base nel solo scenario avverso
(previsto dal §4 del doc). Ora il controllo scatta davvero.

## Rinviato — e perché (non per pigrizia)

- **Distribuzione su 4 macchine (§6)**: P0 ha appena ridotto i percorsi di esecuzione a
  **uno**. Un event-bus su 4 nodi moltiplica i modi di divergere (latenza, split-brain,
  replay) su un sistema da ~1.100 EUR con **zero contributi live**. I ruoli del §6 restano
  validi come architettura-obiettivo, da realizzare **dopo** shadow e canary verdi, e sempre
  passando dall'unico punto di invio.
- **Simulatore fault-injected (§8 Fase 1)**: è il **prossimo** lavoro vero — fill parziali,
  timeout dopo accettazione, clOrdId duplicato, ordine cancellato ma con fill, funding
  mancante, restart tra journal e invio. I modelli sono pronti per riceverlo.
- **`execution.py`** (adapter verso `coordinatore`) e **`reconcile.py`**: dopo il simulatore.
- **`mosaico_shadow.py` / `mosaico_status.py`**: nessuna chiave, nessun ordine — fase shadow.
- **Capitale, size, leva, scala**: **non implementati**. Restano decisioni del proprietario,
  non codice.

## Guardrail verificati

- **Un solo punto di invio**: il guard-test `tests/esecuzione/test_punto_unico_invio.py`
  copre ora anche `src/money/mosaico/` (scansiona `src/`, `scripts/`, `ops/`). Nessun
  `create_order` fuori da `src/money/esecuzione/invio.py` ✅
- **Niente live**: `MONEY_LIVE_ARMED` non toccato, nessun file di promozione, nessuna chiave
  aggiunta, nessun ordine reale ✅
- **Test-first** con `python -O` e CI ✅
- Commit piccoli e tematici (un componente per commit) ✅

## Anti-overfitting (§10) — vincoli recepiti nella spec

massimo 3 varianti (always-on / threshold / threshold+exit), massimo 3 strumenti, nessun
tuning giornaliero, **una** metrica primaria (netto riconciliato per unità di capitale a
rischio), **una** finestra OOS congelata, costi e parametri nello spec **prima** della misura.

## La nota onesta

Nessuna architettura — a uno o a quattro nodi — produce da sola un rendimento. P0 ha reso il
sistema **onesto** (non può più chiamare «guadagno» ciò che è equity o ordine non
riconciliato). MOSAICO-4 ha senso **solo se** esegue bene un edge che **esiste**: oggi,
misurato, quell'edge non c'è (5.170 papabili, DSR≈0,01; carry funding 0,68% vs soglia 8%).
Il nucleo è pronto a misurare — non a guadagnare.

## Prossimo passo concreto

`tests/mosaico/` — **simulatore exchange con fault injection** (§8 Fase 1). Criterio di
completamento: *nessun test deve produrre una posizione orfana non rilevata*. Poi shadow.
