# 26 — Risposta all'"Analisi tecnica e proposta di trasformazione" (2026-10-09)

Documento ricevuto: `~/Analisi tecnica e proposta di trasformazione.docx` (snapshot `819bb14`).
Verificato contro il repo e **applicato in ordine di rischio/valore**: prima ciò che è
verificabile e non tocca capitale, poi il resto con revisione.

## Applicato — Sprint 0 «qualità e blocchi immediati» (commit `e5e06260`)

Criterio del docx: *qualità verde e un solo punto di invio ordini*. Fatto:

- **Ruff**: corretti i 2 `F541` (`scripts/tabellone.py:191`, `ops/zabbix/dev_platform.py:251-253`).
  Ora `ruff check .` → **All checks passed**.
- **Assert fuori dal percorso live**: `esecutore.costruisci()` usava 5 `assert` per invarianti
  economiche (prezzo/step/nozionale/tariffa/arrotondamento). Sostituiti con **eccezioni
  applicative** (`Rifiutato`): con `python -O` gli assert spariscono e un controllo di capitale
  non può dipendere da questo. Test aggiornato (`test_input_rotti_sono_rifiutati`).
- **CI** (`.github/workflows/ci.yml`): ruff + compileall + pytest + **pytest con `-O`**.
- **clOrdId idempotenti nel canary**: `scripts/canary_carry.py` costruiva i `clOrdId` con
  `time.time()` → un retry dopo timeout generava un id NUOVO (rischio di ordine/posizione
  doppia). Introdotti `cid_stabile()` (hash deterministico) e `intento()` (token persistito in
  `canary_state.json`): stesso intento → stesso id, sempre.
- **Test guardia** `tests/esecuzione/test_canary_clordid.py`: fallisce se qualcuno reintroduce
  un clOrdId basato sull'orologio.
- **Verde**: 601 → **603 test**, e **603 anche con `python -O`**.

## Applicato — §P1 «tabellone.py non passa il lint / errori troppo permissivi» (commit `ef3e0759`)

- `bills()` e `flussi_eur()` ora tracciano la **completezza** della fonte.
- `main()` classifica ogni fonte (`ok`/`partial`/`error`) e applica il **fail-closed**: il
  `netto_vs_versato` viene calcolato **solo se tutte le fonti sono complete**, altrimenti
  `stato="INCOMPLETE"` con i motivi. Un totale «best effort» spacciato per verità è peggio di
  nessun totale.
- Verifica live su MARCODG1: `stato=RECONCILED`, fonti `{equity: ok, bills: ok, flussi: ok}`,
  netto +33,38 EUR.

## Rinviato — richiede revisione dedicata (NON applicato in fretta)

Il docx ha ragione su questi punti, ma sono refactor di percorso critico che vanno fatti
**uno alla volta, con test d'incidente**, non a raffica:

- **P0 — due percorsi di esecuzione** (`esecutore.py` generico vs `canary_carry.py` imperativo):
  va unificato dietro un unico `ExecutionCoordinator`; gli script diventano CLI/read-model.
  Tocca il percorso ordini → massima cautela. *Prossimo passo proposto.*
- **P0 — hedging non atomico**: macchina a stati PLANNED→…→FLAT con invarianti (nessun ordine
  se c'è una gamba non riconciliata, delta max, timeout con unwind, intent_id persistente).
- **P1 — RiskGovernor runtime esecutivo** (non solo lista di azioni): oggi `rischio.py`
  restituisce le azioni del kill-switch; l'esecuzione verificabile manca.
- **P1 — stato SQLite WAL + outbox** al posto di JSON+flock per il percorso live.
- **P1 — `PreTradeDecision` unico versionato** e **`PromotionArtifact` firmato/scadibile**.
- **P2 — verdetti separati** `research_promoted` / `live_eligible`.

## Non applicato (e va detto)

- **Riaprire la caccia a centinaia di migliaia di configurazioni**: il docx stesso lo sconsiglia
  (§«Cosa non fare») ed è coerente con la misura di oggi (5.170 papabili, DSR≈0,01 → rumore).
- **Abbassare il DSR** per far passare un candidato: vietato. È una decisione metodologica da
  prendere con il proprietario, esplicita, documentata.
- **Allocare capitale** a qualunque strategia: nessuna è `live_eligible`. Il capitale resta in
  attesa della decisione del proprietario (Earn).

## Prossimi passi (in ordine)

1. **P0 — ExecutionCoordinator unico** (unifica canary + esecutore, elimina il secondo percorso).
2. **P0 — macchina a stati dell'hedge** con delta limit e unwind verificato.
3. **P1 — RiskGovernor esecutivo** con test d'incidente su exchange simulato.
4. **P1 — ReconciliationRun continuo** su SQLite WAL, con stato RECONCILED/MISMATCH/INCOMPLETE.
5. **§P2 — PromotionArtifact** + verdetti `research_promoted`/`live_eligible`.
