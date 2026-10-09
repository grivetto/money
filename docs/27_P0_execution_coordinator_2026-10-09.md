# 27 — P0 ExecutionCoordinator: punto unico di invio (2026-10-09)

Chiusura del P0 di `docs/26` (§5 della proposta) e del §5 di
«Suggerimenti per Hermes — come aumentare la probabilità di rendimento netto».

## Il problema che è stato eliminato

Prima esistevano **due percorsi** che inviavano ordini:

- `src/money/esecuzione/esecutore.py` — generico, con journal/recovery/idempotenza;
- `scripts/canary_carry.py` — imperativo, macchina a stati propria, `clOrdId` a orologio;
- `scripts/okx_ops.py` — terzo percorso, `create_order` diretto senza idempotenza.

Due (tre) percorsi = due gestioni di fill parziali, retry, gambe orfane e posizioni
residue dopo un riavvio. Esattamente il rischio descritto dalla proposta.

## Cosa è stato fatto

**1. `src/money/esecuzione/invio.py` — punto unico di invio.**
Contiene `Gamba` (dataclass) e `invia_gamba(ex, gamba)`: **l'unica** chiamata a
`create_order` di tutto il repository. Non importa nulla dal package (livello più basso):
questo evita il ciclo che si creerebbe se `esecutore.py` importasse da `coordinatore.py`.

**2. `src/money/esecuzione/coordinatore.py` — macchina a stati dell'hedge.**
Stati: `PIANIFICATO → GAMBA_A_INVIATA → GAMBA_A_ESEGUITA → GAMBA_B_INVIATA → COPERTA`
(+ `CHIUSURA`, `PIATTO`, `FALLITO`). Exchange **iniettato**: testabile senza rete.
Invarianti codificate come **eccezioni applicative** (mai `assert`):

1. la gamba B (perp) non parte mai se la gamba A (spot) non è riconciliata;
2. se B non si copre entro il timeout → **unwind automatico** della gamba A (mai gambe orfane);
3. stesso intento → stesso `clOrdId` (idempotenza del retry);
4. delta di copertura misurato **sull'exchange** (posizioni), non dedotto dagli invii;
5. journal scritto **prima** di ogni invio (riusa `money.esecuzione.stato`, un solo writer).

**3. Migrazione dei tre percorsi** al punto unico: `esecutore.py`, `canary_carry.py`,
`okx_ops.py` ora chiamano `invia_gamba`. Il canary **continua a esistere** con gli stessi
sottocomandi (preflight/convert/open/status/close): cambia solo *come* invia.

**4. Test (10 nuovi + 1 guard):**
- `tests/esecuzione/test_coordinatore.py` (8): dry-run non invia; apertura completa
  coperta; **spot parziale ⇒ il perp non parte mai**; **perp non coperto ⇒ unwind**;
  chiusura che verifica il piatto; idempotenza `clOrdId`; journal su disco; nessun assert
  nel coordinatore.
- `tests/esecuzione/test_punto_unico_invio.py` (2, guard): fallisce se un file fuori da
  `invio.py` chiama `.create_order(`.

## Definizione di "fatto" — verificata

```
$ grep -rn "\.create_order(" src/ scripts/ ops/ --include=*.py | grep -v __pycache__
src/money/esecuzione/invio.py:49:    return ex.create_order(...)
```
- **Un solo punto** di invio ✅
- `canary_carry.py` / `esecutore.py` / `okx_ops.py` senza `create_order` diretto ✅
- **613 test verdi** (da 603) e **613 verdi anche con `python -O`** ✅
- `ruff check .` pulito ✅
- Nessun arming del live (`MONEY_LIVE_ARMED` non toccato) ✅

Commit: `567e7e87` (coordinatore+punto unico+test) e `4b6a346f` (migrazione dei percorsi).

## Cosa NON è stato fatto (e perché)

- **SQLite WAL + outbox**: è il P1 successivo. Non nello stesso commit del refactor —
  due cambiamenti grossi insieme sono un incidente. Prima unificare, poi migrare lo storage.
- **RiskGovernor esecutivo**: P1, prossimo.
- **Nessuna allocazione di capitale**, nessun ordine reale, nessuna riapertura della caccia.

## Prossimi passi (ordine)

1. **P1 — RiskGovernor esecutivo**: oggi `rischio.py` restituisce le *azioni* del
   kill-switch; manca l'esecuzione verificabile (stop dispatcher, cancella ordini del bot,
   chiudi e **verifica** flat, alert se non flat), con test d'incidente su exchange simulato.
2. **P1 — ReconciliationRun continuo** (SQLite WAL): stato `RECONCILED/MISMATCH/INCOMPLETE`,
   cursori persistenti.
3. **§P2 — `PromotionArtifact`** + verdetti `research_promoted` / `live_eligible`.
4. **§3/§6 — break-even pre-apertura** (3 scenari: favorevole/base/**avverso**) e capacità.
5. **§7 — scala lenta** (shadow → canary 25-50 € → 100 € → 250 € → 500 €) con capitale
   massimo deciso *prima* della misura e incluso nell'artifact.
