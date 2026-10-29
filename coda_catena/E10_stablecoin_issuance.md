# E10 — «stablecoin net issuance → rendimenti crypto (giornaliero)» (pre-registrazione)

**Data:** 2026-10-29 · **Autore:** Artù · **Stato:** PRE-REGISTRATA (universo, regola e finestre congelati PRIMA dei numeri)

## Come nasce (dichiarato)

Missione ricerca di Morgana (28/10), RANK 2: «on-chain netflows → ritorni intraday» (paper arXiv:2411.06327).
Preflight dati 29/10 (REQ-NUV-20261029-005; handoff verificato: outer 15/15, inner 11/11): **il paper non è
replicabile gratis** — exchange netflows free = solo BTC/ETH daily (2/5 asset), niente USDT, granularità 1d
contro 1–6h del paper, fonti multi-asset a pagamento (CoinGlass/Flipside 401/403, Etherscan richiede chiave).

**Sostituzione di proxy DICHIARATA** (decisione di spec, Artù): la famiglia on-chain che i dati pubblici
reggono è la supply/flussi stablecoin (DefiLlama, 1d, varianza verificata, storia 2017→). Ipotesi riformulata:
la **creazione netta di stablecoin** — proxy di liquidità in ingresso al crypto; il paper usa i netflow USDT
come predittore di liquidità buy-side — precede rendimenti positivi del mercato. È un proxy, non il netflow
exchange: limite dichiarato, non nascosto.

## Ipotesi (congelata)

La net issuance a 30 giorni del **nucleo storico** stablecoin (USDT+USDC+DAI) ha potere predittivo positivo
sui rendimenti giornalieri di BTC e ETH (long-only).

## Dati

- **Segnale**: serie DefiLlama consegnate in REQ-NUV-20261029-005 — SOLO `usdt`, `usdc`, `dai` (le tre con
  storia piena ≥ 2019). Gli altri 5 (PYUSD, USDe, USDS, USD1, USDG) restano FUORI: includerli introdurrebbe
  salti di composizione dell'aggregato (scelta congelata).
- **Prezzi**: OKX daily (bar=1D, endpoint pubblico con paginazione), BTC-USDT e ETH-USDT, 2019-01-01 → 2026-10-28.
  Da scaricare nel **preflight prezzi** del motore (regola della coda: prima i dati, poi i numeri); finestra
  effettiva confermata lì e dichiarata negli artefatti.
- **Taglio**: tutte le serie (stablecoin incluse) si tagliano a **2026-10-28** — l'ultimo punto DefiLlama
  (giorno corrente) è parziale e si esclude.

## Regola operativa (zero gradi di libertà)

- `I_t = Σ_nucleo (Supply_t − Supply_{t−1})` — net issuance giornaliera in USD (somma dei 3 supply).
- `S_t = Σ_{k=0..29} I_{t−k}` — net issuance su 30 giorni (usa SOLO giorni ≤ t).
- `z_t = (S_t − media(S[t−365:t])) / stdev(S[t−365:t])` — statistiche trailing **escluse da t in poi** (causali).
- Posizione (long-only, spot, no leva; BTC e ETH a peso UGUALE, entrambi sempre presenti):
  - `z_t ≥ +1,0` → LONG dall'apertura di t+1;
  - `z_t ≤ 0,0` → FLAT dall'apertura di t+1;
  - `0 < z_t < +1,0` → si MANTIENE lo stato precedente (isteresi dichiarata).
- **Costi**: ogni switch (entrata o uscita, per asset) = RT 0,20% (taker OKX spot 8–10 bp/lato, conservativo);
  stress ×2 = 0,40% RT.
- Warmup: z richiede 395 giorni di storia → i primi segnali sono ~2020-02.

## Finestre (congelate)

- **TRAIN 2020-02-15 → 2024-06-01** · **OOS 2024-06-01 → 2026-10-28**. La soglia (+1,0 / 0,0) è CONGELATA,
  non tarata: nessuna ri-ottimizzazione, nessuna variante di finestra.

## Criteri (3/3 + DSR)

- **T1 OOS**: media del rendimento giornaliero netto della strategia > 0, t ≥ 2,0, n ≥ 500 giorni OOS.
- **T2 costi ×2** (0,40% RT): media > 0.
- **T3 TRAIN**: media > 0 e t ≥ 2,0 (coerenza di segno su train).
- **DSR ≥ 0,95 con N = 2** (prima voce della famiglia on-chain/liquidity: la regola dichiarata = 1 look;
  +1 di margine prudenziale dichiarato per la sostituzione di proxy — nessun look non dichiarato).
  var SR stimata dai due SR per-asset (BTC, ETH) sul TRAIN (`money.statistica.varianza_da_tentativi`).
- **Report descrittivo obbligatorio**: confronto vs buy&hold 50/50 BTC/ETH (media, Sharpe, max DD) — trasparenza,
  non è una soglia.

## Contratto di verifica

- **Repo**: grivetto/money. **Implementazione**: Morgana (nuvola) — REQ-NUV-20261029-006.
- **Motore**: `scripts/e10_stablecoin.py` (stdlib+json; legge le serie stablecoin consegnate + i prezzi scaricati).
- **Test anti-look-ahead OBBLIGATORIO prima dei numeri**: `tests/ricerca/test_e10_antilookahead.py` — la decisione
  presa alla chiusura di t usa SOLO dati ≤ t e nessun dato ≥ t+1 (z_t può includere il giorno t, che è chiuso);
  la posizione entra all'open di t+1; il test DEVE fallire se z_t include giorni > t o se l'ingresso non è
  all'open di t+1.
- **Output**: per asset e aggregato — giorni in posizione, media giornaliera netta, t, CI90 bootstrap, stress,
  max DD, Sharpe, confronto buy&hold. Artefatti `prove/e10_stablecoin.{json,txt}`.
- **Misura ufficiale**: Artù (riesecuzione dal repo canonico). Smoke di validazione: Morgana.
- **Fuori scope**: varianti di soglia/finestra, lato short, leva, altri stablecoin, estensioni post-hoc.
- **Procedura**: `cd ~/money && .venv/bin/python scripts/e10_stablecoin.py` e
  `.venv/bin/python -m pytest tests/ricerca/ -q -k e10`.

## Se passa

Non è un'autorizzazione: canary 14 giorni a taglia minima con riconciliazione esatta (come C1), sizing 0,25% di
rischio per trade (mandato), e solo dopo go esplicito dell'owner.

## Se fallisce

Famiglia on-chain/liquidity CHIUSA: nessuna variante ulteriore. Il fronte ricerca prosegue sulle lane in
apertura (TSMOM 12M/1M long-only BTC/ETH).
