# P34 — Gate funding conservativo + chiusura economica + riconciliazione su saldi reali

**STATO: PRE-REGISTRATA** (Artù, 2026-10-26) — dispatch: Merlino (omarchy)

## Perché (evidenze, non opinioni)

1. **Finestra del gate di apertura troppo corta** (`scripts/carry_apri.py::funding_atteso`):
   oggi usa `min` degli ultimi **3 periodi** (24h) di funding. La lezione P19b (16/10)
   dice che l'istantaneo non è base di decisione e serve ≥100 periodi; un minimo su 24h
   è una stima conservativa ma **non robusta**: un regime di funding transitorio alto
   apre il carry e il payback poi si allunga (rischio misurato in P22: uscita frequente
   mascherata costa fino a −6,37%/anno su DOT).
2. **X-Perp EEA: tasso di listino, non di mercato.** Misurato su 33/33 epoche (16/10→26/10):
   fundingRate = **+0,010000%/8h esatte** (fisso). Il rischio non è il campione: è che
   **OKX cambi la tariffa**. Il gate deve verificare "tariffa corrente == tariffa dichiarata
   alla pre-registrazione" e allarmare al primo scostamento (watchdog, non solo al gate).
3. **Ciclo ADA chiuso 26/10 (primo ciclo completo)**: netto MTM alla chiusura +0,093 USDC,
   realizzato **−0,157 USDC** = funding +0,277 − fee_in 0,135 − fee_out 0,121 − basis gambe
   0,179. **La condizione "netto stimato ≥ 0" chiude PRIMA del pareggio reale**: mancano
   fee di uscita + basis di chiusura (~0,25 USDC su nozionale ~90, ≈0,28%). Payback reale
   misurato del ciclo completo: ~47 epoche (15,6 giorni).
4. **Riconciliazione su stato stantio**: `recon_giornaliero.py` (Lancillotto) usa
   `data/carry_multi/stato.json` (fermo all'apertura) → dopo lo scaling DOT del 23/10
   (78→253 ct) il delta spot è sottostimato di 3,2× e il netto pubblicato sul canale è
   errato. La riconciliazione DEVE leggere il saldo spot reale dall'exchange.

## Cosa si implementa (perimetro)

### F1 — stima funding per il gate di apertura
- Se strumento = X-Perp EEA (tariffa fissa): funding_atteso = tariffa corrente **solo se
  identica alla tariffa dichiarata** (0,0001). Altrimenti `ok=False` con motivo.
- Se strumento = USDT-SWAP (variabile): funding_atteso = **p10** della serie rolling
  (finestra ≥30 periodi da funding-rate-history; se n<30 → gate rifiuta con motivo
  "campione insufficiente", mai default permissivo).
- Il SEGNO si conserva (lezione fix audit 19/10): negativo → rifiuto.

### F2 — chiusura economica
- Nuova condizione di chiusura (per carry_chiudi e per i criteri operativi):
  `netto_stimato >= fee_uscita_stimata + basis_uscita_stimato + margine`
  con default margine = 0 e stime dalle tariffe reali (costi.py) e dallo spread corrente
  del book (bid/ask). Il vecchio criterio "netto ≥ 0" resta valido SOLO per le chiusure
  di emergenza/riduzione di rischio (kill switch), mai per la chiusura economica.
- Test: su una curva di riconciliazione sintetica il gate rifiuta di chiudere quando
  netto < fee_uscita+basis (caso ADA 26/10 riprodotto come fixture).

### F3 — riconciliazione su saldi reali
- Il calcolo del delta spot e del netto usa `fetch_balance` (saldo spot reale) e
  `account/positions` (uPnl reale), MAI `carry_stato.json` per quantità o prezzi.
- `recon_giornaliero.py` aggiornato di conseguenza (o sostituito dal modulo condiviso).

### F4 — watchdog tariffa X-Perp
- Controllo periodico (cron, stesso giro di carry_watch): tariffa X-Perp corrente vs
  dichiarata; scostamento → ALERT su canale (stessa via di carry_watch, alerts.log).

## Vincoli
- Nessun ordine reale; il gate si prova con i test + dry-run (`carry_apri --dry-run`,
  `carry_chiudi --dry-run`).
- Riusare `money.costi`, `money.rischio`, `money.esecuzione.cancello_carry`.
- Fee/slippage: tariffe reali da `costi.py` (verificate P23); nessun numero inventato.
- Test in `tests/ricerca/` o `tests/esecuzione/` secondo convenzione esistente.

## Criteri di accettazione
1. `python -m pytest -q tests/.../test_<nuovi>` verde nel venv canonico (suite completa verde).
2. Dry-run `carry_apri --coppia LTC` su MARCODG1: il gate stampa la stima funding usata
   e la sua fonte (tariffa fissa X-Perp / p10 rolling), rc coerente.
3. Fixture caso ADA 26/10: con netto 0,093 < fee_uscita+basis 0,25 → la chiusura economica
   rifiuta (mentre la chiusura di emergenza accetta).
4. `recon_giornaliero.py` post-fix: i numeri del delta spot combaciano col saldo reale
   (confronto con `fetch_balance` su una corsa reale).

## Fuori scope
- Apertura di nuove coppie (D3 resta sospeso: criterio N cicli chiusi, vedi piano).
- Ottimizzazione del basis d'ingresso (entry optimizer) — il delta residuo misurato
  (0,1%) è già sotto soglia; si riapre solo con evidenza contraria.

## Registro
- Pre-registrata 2026-10-26 da Artù. Numeri di riferimento: `prove/carry_recon_2026-10-22/`,
  ledger 26/10 (chiusura ADA), sessioni del 23/10 (scaling DOT).
