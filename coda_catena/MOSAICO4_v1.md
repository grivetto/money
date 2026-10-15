# MOSAICO4_v1 — spec congelata (2026-10-09)

Fonte: «MOSAICO-4 — sistema di trading event-driven per quattro macchine» (§11–12).
Stato: **congelata**. Ogni modifica richiede una nuova spec (v2), non un edit.

## Cosa è MOSAICO-4 (in una riga)

Carry dinamico **market-neutral**: long spot + short perp, si opera **solo** quando
`funding_forecast` e `basis_edge` conservativi superano i costi p95 e i buffer; altrimenti
si resta fermi. «Un sistema che non opera quando non c'è margine è più vicino a
diventare redditizio di uno che opera continuamente per dimostrare attività» (§419).

## Parametri congelati (§5) — proposte di progetto, non verità ottimali

| Limite | Valore |
|---|---|
| Rischio massimo per hedge group | 0,25% equity |
| Calore massimo totale | 1,00% equity |
| Nozionale massimo per strumento | 10% equity (shadow/canary) |
| Nozionale massimo complessivo | 25% equity |
| Leva | 1x |
| Delta massimo normale | 0,25% del nozionale |
| Delta massimo duro | 0,75% del nozionale |
| Timeout di hedge | 30–60 s (da misurare) |
| Perdita giornaliera massima | 1% equity |
| Drawdown di arresto | 5% equity |
| Drawdown di revisione | 8% equity |

Sotto 1000 EUR il sistema risponde **NOT_ECONOMICALLY_FEASIBLE**: non aumenta size o leva (§203).

## Regola di ingresso (§3.4) — implementata in `economics.valuta`

```
beneficio_lordo = funding_atteso + basis_edge
costi           = fee_entry + fee_exit + slippage_entry + slippage_exit
                + spread_entry + spread_exit + conversione + buffer_hedge + buffer_avversi
apri  <=>  margine_netto >= max(3 * costi, soglia_minima_eur)
           e funding_atteso > 0
           e scenario avverso entro il budget di perdita
```

`funding_atteso` = **min**(media robusta ultimi 3, quantile 25 ultimi 30) — mai l'ultimo
valore osservato (§3.1). Nessun modello ML nel percorso live.

## Anti-overfitting (§10) — vincoli duri

- massimo **3 varianti** dichiarate: always-on, threshold, threshold+exit;
- massimo **3 strumenti** iniziali (BTC, ETH, un'altcoin solo se passa i test di capacità);
- **nessun tuning giornaliero**;
- **una sola** metrica primaria: netto riconciliato per unità di capitale a rischio;
- **una sola** finestra OOS congelata;
- costi e parametri salvati nello spec **prima** della misura;
- nessuna selezione retroattiva del "migliore" senza correzione multiple testing.

## Ordine di messa in produzione (§410) — NON negoziabile

```
spec congelata → simulatore fault-injected → shadow indipendente
→ canary minimo → riconciliazione netta → scala lenta
```

## Stato dell'implementazione (2026-10-09)

| §11 backlog | Stato |
|---|---|
| `src/money/mosaico/model.py` | **fatto** (HedgeGroup, Leg, EconomicsSnapshot) |
| `src/money/mosaico/economics.py` | **fatto** (break-even, 3 scenari) |
| `src/money/mosaico/signal.py` | **fatto** (funding_forecast, basis, qualità esecuzione) |
| `src/money/mosaico/state_machine.py` | **fatto** (§7 + invarianti §302-309) |
| `tests/mosaico/` (simulatore + fault injection) | **da fare** (Fase 1) |
| `src/money/mosaico/execution.py` (adapter → coordinator) | **da fare** |
| `src/money/mosaico/reconcile.py` | **da fare** |
| `scripts/mosaico_shadow.py` / `mosaico_status.py` | **da fare** |
| distribuzione su 4 macchine | **RINVIATA** (traguardo, non primo deliverable) |

## Perché la distribuzione a 4 macchine è rinviata

P0 (docs/27) ha appena unificato i percorsi di esecuzione in **uno** (`invio.py` +
`coordinatore.py`). Un event-bus su 4 nodi moltiplica i modi di divergere (latenza,
split-brain, replay) su un sistema da ~1.100 EUR e zero contributi live. I ruoli del §6
restano validi come **obiettivo architetturale**; si realizzano **dopo** shadow e canary
verdi, su una sola macchina prima, e sempre passando dall'unico punto di invio.

## Regola di quorum (§267) — implementata come concetto, non come consenso tra bot

```
artifact valido + preflight OK + reconciliation fresh + governor GREEN + break-even > 0
= ordine ammissibile ;  altrimenti NO_TRADE
```
La decisione è **deterministica**, non un voto. Nessun LLM decide un ordine (§11 doc Suggerimenti).

## Formato-contratto (retrofit 2026-10-15; contenuto scientifico sopra invariato)

- **Obiettivo**: portare il nucleo già implementato (`model`, `economics`, `signal`,
  `state_machine`) al **simulatore fault-injected** (Fase 1 di §410) e da lì a shadow e canary
  minimo, con la severità di prova del resto del progetto: fail-closed, nessun percorso live.
- **Repo/commit**: repo `grivetto/money`, nucleo e spec al commit `5aa92ccf` (09/10/2026);
  l'avanzamento (simulatore, adapter, reconcile) avanza commit per commit su `main`.
- **Input**: snapshot economics per hedge group (funding atteso, basis, costi, buffer — §3.4) e
  serie funding/basis dai dati già in repo; al simulatore si iniettano i guasti. **Output**: esito
  delle transizioni (§7) + verdetto `apri`/`no-trade` di `economics.valuta` + report dei test in
  `prove/`.
- **Test falsificabile**: `tests/mosaico/` — per ogni regola critica un test che DEVE fallire se
  l'implementazione è assente o sbagliata: con margine netto <= 0 il verdetto atteso e' NO_TRADE
  (assert); con delta oltre la soglia dura lo stato atteso e' di unwind, mai di hedge; il kill
  switch porta a `KILL_SWITCHED` da qualunque stato (§7–§8).
- **Criteri di accettazione**:
  - [ ] simulatore fault-injected: tutti i casi di guasto di docs/28 coperti, invarianti §302-309
        verificate a ogni transizione (0 violazioni);
  - [ ] nessun modulo `mosaico/` tocca la catena di esecuzione live (`esecuzione/invio.py` intatto);
  - [ ] test verdi anche con `python -O`; ruff pulito.
- **Fuori scope**: nessun ordine live, nessuna chiave API, nessuna modifica ai moduli della catena
  di esecuzione; non modificare i parametri §5 (si cambiano solo con una spec v2).
- **Procedura di verifica**:
```bash
.venv/bin/python -m pytest tests/mosaico -q     # ROSSO prima dell'implementazione, VERDE dopo
.venv/bin/python -m pytest -q                   # suite intera
.venv/bin/ruff check src/money/mosaico tests/mosaico
```
