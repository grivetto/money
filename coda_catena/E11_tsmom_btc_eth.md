# E11 — «TSMOM 12M/1M long-only BTC/ETH» (pre-registrazione)

**Data:** 2026-10-29 · **Autore:** Artù · **Stato:** PRE-REGISTRATA (universo, regola e finestre congelati PRIMA dei numeri) → **MISURATA 29/10: NON PROMOSSA (2/5 — T1/T2/DSR FAIL; T3/T4 PASS). Lane trend/TSMOM chiusa in questa forma. Artefatti `prove/e11_tsmom.{json,txt}`.**

## Come nasce (dichiarato)

Raccomandazione n.4 del report A0-Win (21/10) e «prossima lane pre-registrata» dichiarata dal verdetto E8
(chiusura della famiglia «estremi di prezzo»). È la baseline di time-series momentum più documentata
(12 mesi di lookback, ribilanciamento mensile), nella variante **long-only** — imposta dalla struttura del
progetto (spot-only sulle venue di produzione; il lato short delle famiglie precedenti è risultato negativo:
E6 −0,484% · E8 −1,122%). Il long-only non è una selezione post-hoc: è la forma dichiarata QUI, prima dei numeri.

## Ipotesi (congelata)

Il momentum a 12 mesi su BTC e ETH persiste a orizzonte mensile: se il rendimento degli ultimi 12 mesi di un
asset è positivo, l'asset rende positivamente anche nel mese successivo; se è negativo, stare flat.

## Dati

- **Prezzi**: OKX daily (bar=1D, endpoint pubblico con paginazione), BTC-USDT e ETH-USDT, 2019-01-01 → 2026-10-28.
  Stesso preflight prezzi della spec E10 (`~/hermes-scratch/e10/prezzi/` se già scaricato, altrimenti si scarica);
  validazione (monotonìa, gap, null, varianza) e finestra effettiva dichiarate negli artefatti.
- **Taglio**: serie a 2026-10-28.

## Regola operativa (zero gradi di libertà)

- `R12(t) = close(t) / close(t−365g) − 1` — rendimento 12 mesi su barre giornaliere (close UTC), calcolato SOLO
  con barre ≤ t.
- **Segnale**: il primo giorno di ogni mese `r`, per ciascun asset indipendentemente, il segnale è `R12(r−1)`
  (close dell'ULTIMO giorno del mese precedente): se `> 0` → LONG; se `≤ 0` → FLAT.
- **Esecuzione**: la posizione (o la sua conferma) è attiva dall'apertura del primo giorno utile ≥ `r`; tra un
  ribilanciamento e il successivo la posizione resta invariata.
- **Pesi**: BTC e ETH a peso UGUALE, ciascuno con la PROPRIA posizione (long-only, spot, no leva).
- **Costi**: ogni cambio di posizione (entrata o uscita, per asset) = RT 0,20% (taker OKX spot 8–10 bp/lato,
  conservativo); stress ×2 = 0,40% RT. Ribilanciamenti senza cambio di posizione = zero costi.
- Warmup: il primo segnale utile richiede 365 giorni di storia → primi ribilanciamenti ~2020-02.

## Finestre (congelate)

- **TRAIN 2020-02-01 → 2024-06-01** · **OOS 2024-06-01 → 2026-10-28**. Nessuna ri-ottimizzazione: lookback
  (12M), frequenza (mensile) e soglia (0) sono CONGELATI, non tarati.

## Criteri (4/4 + DSR)

- **T1 OOS**: media del rendimento giornaliero netto della strategia > 0, t ≥ 2,0, n ≥ 500 giorni OOS.
- **T2 costi ×2** (0,40% RT): media > 0.
- **T3 TRAIN**: media > 0 e t ≥ 2,0 (coerenza di segno su train).
- **T4 OOS — value-add sul passivo**: il max drawdown della strategia OOS ≤ max drawdown del buy&hold 50/50
  BTC/ETH OOS (una strategia long-only che non riduce il drawdown rispetto al tenere non ha valore aggiunto).
- **DSR ≥ 0,95 con N = 5** — look dichiarati: questa regola (1) + i 4 esperimenti storici della famiglia «trend
  direzionale su OHLCV» nel REGISTRO (P1 chandelier, P3 filtro 200g, P5 Donchian esteso, P11 vol breakout).
  var SR stimata dai due SR per-asset (BTC, ETH) sul TRAIN (`money.statistica.varianza_da_tentativi`).
- **Report descrittivo obbligatorio**: confronto vs buy&hold 50/50 (media, Sharpe, max DD) + % giorni in posizione.

## Contratto di verifica

- **Repo**: grivetto/money. **Implementazione**: Merlino (omarchy) — REQ-MERL-20261029-025.
- **Motore**: `scripts/e11_tsmom.py` (stdlib+json; riusa i prezzi del preflight).
- **Test anti-look-ahead OBBLIGATORIO prima dei numeri**: `tests/ricerca/test_e11_antilookahead.py` — il segnale
  del mese r usa SOLO barre ≤ r−1; l'ingresso è all'open del primo giorno utile ≥ r; il test DEVE fallire se
  R12(r) ingoia il close di r o giorni successivi, o se l'ingresso usa il close del giorno di ribilanciamento.
- **Output**: per asset e aggregato — % giorni in posizione, media giornaliera netta, t, CI90 bootstrap, stress,
  max DD (strategia vs buy&hold), Sharpe. Artefatti `prove/e11_tsmom.{json,txt}`.
- **Misura ufficiale**: Artù (riesecuzione dal repo canonico). Smoke di validazione: Merlino.
- **Fuori scope**: varianti di lookback (6M/3M), frequenza settimanale, lato short, altri asset, estensioni post-hoc.
- **Procedura**: `cd ~/money && .venv/bin/python scripts/e11_tsmom.py` e
  `.venv/bin/python -m pytest tests/ricerca/ -q -k e11`.

## Se passa

Non è un'autorizzazione: canary 14 giorni a taglia minima con riconciliazione esatta (come C1), sizing 0,25% di
rischio (mandato), e solo dopo go esplicito dell'owner.

## Se fallisce

La lane trend/TSMOM si chiude in questa forma. Nessuna variante: la ricerca si riorienta sulle lane in apertura
(E10 in misura; RANK 3 della missione: listing event-driven).

## Esito (misura ufficiale 29/10/2026, Artù)

**NON PROMOSSA (2/5) — lane chiusa in questa forma.** Misura dal repo canonico (mc2); smoke di Merlino
(omarchy) identico al bit; test anti-look-ahead 7/7 PRIMA dei numeri; dati OKX 1D 2019→2026-10-28
(2858 barre/asset, zero gap/duplicati/null; griglia 16:00 UTC dichiarata e verificata). **OOS (880 giorni):
aggregato −0,0192%/giorno, t −0,31, CI90 [−0,122%, +0,083%] → T1 FAIL; stress (costi ×2) −0,0199% → T2 FAIL.
TRAIN (2020-02→2024-06): +0,203%/giorno, t 2,57 → T3 PASS. T4 PASS (maxDD strategia 43,6% ≤ buy&hold 60,2%).
DSR 0,361 (N=5) → FAIL.** Switch: BTC 6 · ETH 12; ultimo ribilanciamento 2026-10: BTC FLAT, ETH FLAT.
Il momentum 12M ha reso nel train e si è spento nell'OOS recente; l'unico valore misurato è la riduzione
del drawdown rispetto al passivo. Artefatti `prove/e11_tsmom.{json,txt}`; motore `scripts/e11_tsmom.py`;
spot-check indipendente R12 ok. Fronti aperti: E10 (stablecoin) e RANK 3 (listing event-driven).
