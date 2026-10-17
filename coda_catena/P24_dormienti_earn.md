# P24 — Dormienti a rendita: trasferimento verso Simple Earn (D2) — SPEC DI IMPLEMENTAZIONE
STATO: PRESA_DA Merlino 2026-10-17 (implementazione harness) — pre-registrata 2026-10-17 (hermes/Artù). REQ-MERL-20261017-005.
Voce OPERATIVA (tesoreria — decisione D2 del proprietario, ROADMAP §7 risposte 17/10): **non è un esperimento di ricerca**; non entra nel conteggio dei tentativi né nel gate JEV. L'esecuzione reale è di Artù, in finestra mattutina, dopo preflight cifre — mai di Merlino.
Repo: `grivetto/money` · commit di registrazione: `2c7b9907` (file di questa voce: `coda_catena/P24_dormienti_earn.md`).

## Obiettivo (verificabile)
Implementare l'harness `earn_move.py` che sposta importi **ESPLICITI** da funding/trading verso **Simple Earn** su OKX EEA: dry-run di default, `--execute` per eseguire, con guardie dure, idempotenza e riconciliazione post. Sblocca la mossa D2 («ogni euro dormiente si sveglia») con **zero percorsi non testati sul capitale** (regola di statuto).

## Input / Output
- **Input**: CLI (`--ccy`, `--amt`, `--fonte {funding,trading}`, `--max-amt`, `--min-amt`, `--rate`, `--target`, `--execute`); client ccxt OKX EEA (chiave con permessi di transfer/purchase, fornita al momento dell'esecuzione da Artù — MAI in chiaro nel codice, MAI in log); saldi reali letti in preflight (funding, trading, savings).
- **Output**: piano stampato (passi + importi + saldi attesi), riga di log append-only `logs/earn_move.log` (`{ts, ccy, amt, fonte, esito, delta_savings}`), riconciliazione delta savings == amt, exit code 0/≠0; in dry-run: nessuna scrittura.

## Contesto
- ROADMAP §2 D2, risposta del proprietario 17/10: «SÌ, con preflight cifre alla mano» — funding ≈211 USDC ≈194,16 € a 0% → Simple Earn (instant); comparto trading: eccedenza (≈88 €, da confermare col dry-run carry) → Earn.
- Riferimento esistente per il transfer tra conti: `scripts/okx_ops.py` (subcomando `transfer`: funding(6) → trading(18); dry-run di default; MAI stampa chiavi).
- Endpoint OKX v5 (DA VERIFICARE sulla doc pubblica al momento dell'implementazione e DICHIARARE nel LEGGIMI):
  - `GET /api/v5/finance/savings/balance` — saldo savings (read);
  - `POST /api/v5/finance/savings/purchase-redempt` — purchase/redeem flessibile (`{ccy, amt, side:"purchase", rate?}`).
  - **Fonte del prelievo del purchase** (funding vs trading): da determinare dalla doc; se il purchase attinge al **trading account**, il percorso include il transfer funding→trading PRIMA del purchase. Il piano stampato deve elencare OGNI passo.

## Meccanica
- CLI: `--ccy <C>` `--amt <A>` `--fonte {funding,trading}` `--max-amt <M>` `--min-amt <m>` `--rate <R>` (solo se richiesto dalla doc) `--execute` (default = dry-run).
- Passi: (1) preflight read-only — saldi funding/trading/savings, piano completo con importi e saldi attesi; (2) guardie; (3) con `--execute`: transfer (se serve, pattern `okx_ops.py`) poi purchase; (4) **riconciliazione**: delta saldo savings == amt (tolleranza 0), altrimenti errore esplicito e log; (5) log append-only in `logs/earn_move.log` (`{ts, ccy, amt, fonte, esito, delta_savings}`).
- **Idempotenza**: `--target <T>` (saldo savings cumulativo atteso); se savings ≥ T → esce con «già a target», nessuna scrittura.

## Guardie dure
- `amt` SEMPRE esplicito: vietato «tutto il saldo», vietati default impliciti; una sola operazione per esecuzione.
- Dry-run: ZERO chiamate di scrittura — verificato da test con client mock che conta le chiamate.
- `amt > --max-amt` o `amt < --min-amt` o `ccy` fuori whitelist {USDC, EUR, USDT} → rifiuto con messaggio, exit≠0.
- Nessun ordine di trading, nessun prelievo verso l'esterno, nessuna chiave stampata o loggata.

## Criteri di accettazione
1. `earn_move.py` + `test_earn_move.py` (mock, offline): sequenza passi (transfer prima del purchase quando `--fonte trading`), guardie max/min/whitelist, idempotenza target, riconciliazione (delta≠amt → errore), dry-run senza scritture. Output `pytest -q` per esteso.
2. Smoke dry-run con client mock: stampa piano + saldi attesi; artefatto JSON allegato.
3. `LEGGIMI.md` con: comando dry-run reale e comando `--execute` (per Artù, che esegue SOLO dopo preflight e in finestra mattutina), nota sulla fonte del prelievo e su `rate` (verificati su doc OKX).
4. Handoff `merlino/handoff/P24/` con script, test, artefatto smoke, LEGGIMI.md, `MANIFEST.sha256`, `READY` (ultimo).
**Scadenza: ACK subito, DONE entro 18/10 08:00 UTC** (finestra mattutina), altrimenti FAILED con evidenze.
Zero ordini reali, zero chiavi in gioco, zero write su `~/money`.

## Anti-bias / invarianti
- L'harness non decide nulla: importi, valuta e target vengono dal preflight di Artù (numeri esatti), l'harness esegue e riconcilia.
- Nessuna prova a importo minimo «per vedere se funziona»: la prima esecuzione reale è la mossa D2 autorizzata, con importo dal preflight.

## Fuori scope
- Redeem dal savings; ordini di trading di qualunque tipo; prelievi verso l'esterno; spostamenti impliciti o «tutto il saldo»; modifiche a C1/carry in produzione; qualunque scrittura su `~/money` da parte di Merlino (consegna via handoff).

## Verifica (riproducibile)
1. Test offline nel venv di scratch: `python -m pytest test_earn_move.py -q` — poi rieseguiti da Artù nel venv canonico (`cd ~/money && .venv/bin/python -m pytest -q /tmp/p24_review/test_earn_move.py`).
2. Smoke dry-run con client mock: `python earn_move.py --ccy USDC --amt 10 --fonte funding --max-amt 300` → stampa piano completo, zero chiamate di scrittura (asserzione nel test).
3. Run reale (SOLO Artù, dopo preflight cifre): dry-run col client vero (read-only) → saldi e piano; poi `--execute` con importo dal preflight; riconciliazione `delta_savings == amt` nella riga di log.
