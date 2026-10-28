# Report — Edge di microstruttura/orderflow su OKX EEA (sola lettura, nessun ordine)

**Data**: 2026-10-26 · **Macchina**: mc2 · **Cartella artefatti**: `/home/sergio/money/prove/micro_edge/`

## 1. Dati disponibili e usati

| Dataset | Simboli | Periodo | Granularità | Venue | Righe |
|---|---|---|---|---|---|
| ohlcv_xperp.jsonl | BTC/USDT, ETH/USDT | 2024-06-01 → 2026-08-31 | 5 min OHLCV | OKX | 631.2k (315.6k/simbolo; dedup 25% slot duplicati → 236.7k slot puliti/simbolo) |
| tick/*.csv.gz | DOGEUSDT, SOLUSDT | 2026-09-13 → 2026-10-11 (29 gg) | tick singoli con lato aggressore | Bybit (non OKX) | ~15.6M trade (DOGE 6.8M, SOL 8.9M) |
| l2/*.jsonl | BTC-EUR | 2026-10-23 13:27 → 2026-10-24 21:29 | snapshot book ~1-2s con depth 1-100bp e imbalance precalcolati | OKX (raccolti da MARCODG1) | 114.9k |
| spread/spread.csv | BTC, ETH, SOL, XRP, DOGE, ADA, AVAX, LINK | 2026-10-12 → 2026-10-26 | bid/ask 5 min | Bybit + Bitvavo (non OKX EEA) | 64.1k |

**Costi usati (reali, confermati dal progetto)**: fee taker 0.10%/lato, fee maker 0.08%/lato (spot OKX EEA), + slippage 0.04%/lato → **round-trip 0.28% taker / 0.24% maker**. Su DOGE/SOL testato anche stress 0.30%/lato.

**Cancello**: walk-forward "train fino 2024-06-01" non applicabile letteralmente (i dati iniziano esattamente il 2024-06-01). Applicato l'equivalente: walk-forward con blocchi di verifica trimestrali e train expanding (7 blocchi, 2025-01→2026-09 su OHLCV; train 20gg/verify 9gg su tick; train 1gg/verify 1gg su L2; train 1 sett./verify 1 sett. su spread). Requisiti: positivo in (N-1)/N blocchi, sopravvive a fee+50%, Monte Carlo p5 non catastrofico.

## 2. Ipotesi testate e metriche nette

### H1 — Mean reversion post-move estremo (z-score 5-min su EWMA vol)
OHLCV OKX BTC+ETH, entry open successiva, hold 15-30 min. Params scelti per fold su train (consenso: z>1.5, H=3).
- BTC OOS (7 blocchi): n=22.058 trade, net −6067% (log, dominato dai costi), **gross +110% in 2.2 anni = +0.5 bp/trade**, win rate 16.7%, t-stat −95.6, Sharpe giorn. −33.1, maxDD 6066%, **MC p5 = −6501%**, fee×1.5 = −9154%. **Blocchi positivi: 0/7.**
- ETH: identico (n=22.043, gross +0.5bp/trade, 0/7 blocchi). **MORTA: bordo lordo 0.5bp vs costo 28bp (56x).**

### H2 — Autocorrelazione ritorni 1-5 min (contrarian sign(r) e variante momentum)
OHLCV BTC+ETH, hold 5-30 min.
- Contrarian: BTC n=97.751, gross +195.7% su 2.2 anni = **+0.2 bp/trade**, net −27.175%, t-stat −403, Sharpe −52.7, MC p5 −28.924%, 0/7 blocchi. Autocorr misurata: lag1 −0.008, lag2 −0.011 (BTC, significativa ma minuscola). **MORTA (140x).**
- Momentum: gross NEGATIVO (−358%). **MORTA.**

### H3 — Orderflow proxy da OHLCV (CLV × volume z-score)
BTC: n=14.394, gross −99.5% (perde anche lordo), net −4130%, t-stat −72.9, 0/7 blocchi. **MORTA.**

### H4 — Stagionalità oraria (drift per ora UTC, hold 5 min)
BTC k=2: n=8.134, net −2230%, gross ≈ 0, t-stat −105, 0/7 blocchi. **MORTA.**

### H5 — Sbilancio tick aggressivo 5-min → ritorno 5/15/30 min
Tick Bybit DOGE/SOL (29 gg), walk-forward 20+9 giorni, soglia scelta su train.
- IC: |IC| ≤ 0.03 ovunque, segno instabile (DOGE h5: +0.016 train → −0.027 verify; SOL h30: −0.026 → −0.009). Decili piatti e rumorosi in train E verify.
- Migliori strategie su verify: gross +0.7…+1.8 bp/trade, net taker 0.14% = **−26…−29 bp/trade** (n=272…1847). **MORTA: nessuna predittività dell'imbalance a orizzonti 5-30 min.**

### H6 — Predittività dello spread (z-score spread 5-min) → ritorno 5-120 min
Spread Bybit+Bitvavo 8 monete, 2 settimane, split 1w/1w.
- **Unico segnale con struttura reale e stabile OOS**: IC(z_spread, ritorno 30m) negativa e persistente: SOL −0.21→−0.31, XRP −0.19→−0.28, BTC −0.15→−0.17, DOGE −0.06→−0.08, ETH −0.12→+0.01 (unica eccezione).
- Strategia short con z>2-3, hold 30-120 min: **gross +4…+12 bp/trade** (pooled verify 120m: +11.6 bp/trade, t-stat +1.6), ma **net maker −12.5…−20 bp/trade, net taker −16.5…−24 bp/trade** (RT 24-28bp). **MORTA netto: il bordo lordo è reale ma 2-3x sotto il costo round-trip retail.**

### H7 — Sbilancio profondità L2 BTC-EUR → ritorno 5-30 min
2 giorni OKX (10-23 train / 10-24 verify).
- IC instabili: imb50_30m +0.07→+0.20 (t=+3.2, unico interessante ma n≈250 slot), imb100_15m +0.17→+0.004; segni che si invertono tra train e verify.
- Strategie net: **−24…−29 bp/trade in verify** (tutte negative). Vol 5-min mid 8-12bp, spread 0.2-0.4bp: a orizzonte secondi la fee (8-10bp/lato) è 25-50x lo spread → morto per costruzione.

## 3. Verdetto

**Nessuna ipotesi sopravvive al cancello.** Numeri chiave:
- Tutte le famiglie OHLCV: **0/7 blocchi positivi** (richiesto 6/7); fee+50% peggiora ovunque; **MC p5 catastrofico** (−6501% per H1 BTC, −28.924% H2, ecc.).
- Il bordo lordo massimo trovato a qualsiasi granularità è **+0.5 bp/trade (OHLCV), +1.8 bp/trade (tick), +11.6 bp/trade (spread-z 120m)** contro un costo round-trip di 24-28bp. Il migliore (spread-z) è sotto di un fattore 2-3; gli altri di 15-140x.
- Conferma quantitativa della misura nota del progetto (fee > spread, MM chiuso): su BTC-EUR lo spread mediano è 0.2-0.4bp vs fee maker 8bp.

L'unico segnale microstruttura **reale** (IC stabile OOS su 8 monete × 2 venue, orizzonti 15-120 min) è lo **z-score dello spread → ritorno negativo futuro** (spread largo dopo run-up → ritracciamento). Non è commerciabile standalone con fee retail, ma è riutilizzabile come **overlay a costo zero** su strategie già attive (carry/funding: evitare aperture long con z-spread estremo; timing degli ingressi).

## 4. Latenza / rate-limit del setup (API da MARCODG1, OKX EEA)

- **RTT misurato ora da mc2**: eea.okx.com = **11.8 ms** (min 11.5, max 12.1, 0% loss). Ottimo.
- Rate limit OKX spot (public): ~20 req/2s per endpoint (ccxt rateLimit 110ms). **Poll 5-60s ampiamente dentro i limiti** (12-720 richieste/ora vs ~36k/ora consentite). Il cron `campiona_spread.py` già fa questo a 5 min.
- L2 a 1s via REST è al limite (1 req/s per book a 400 livelli = 7200 req/ora: fattibile ma scomodo); la via corretta è **WebSocket books5/book_l2_tbt push** (fino a 240 canali, no poll). La raccolta L2 di MARCODG1 funziona già così.
- Con 12ms RTT + esecuzione REST (~50-150ms end-to-end) i segnali eseguibili in pratica hanno orizzonte ≥ 1-5 min; i segnali a secondi non sono eseguibili con affidabilità da questo setup.

## 5. Raccomandazioni di raccolta dati (i dati attuali NON bastano)

1. **Tick trades OKX EEA** (BTC-EUR, ETH-EUR): oggi i tick sono solo Bybit (DOGE/SOL, USDT). Serve la stessa serie sul venue eseguibile per validare imbalance/VPIN su EEA (1-3 mesi).
2. **L2 BTC-EUR per mesi, non 2 giorni**: il test imb50_30m (IC +0.20, t=+3.2 in verify) è l'unico segnale L2 non morto ma ha n≈250 slot: indecidibile. Con 2-4 mesi si fa walk-forward serio del depth imbalance a 30-60 min.
3. **Quote top-of-book 5-min OKX EEA per mesi** (BTC-EUR + top 10): lo spread-z è l'unico segnale robusto trovato; oggi è misurato solo su Bybit/Bitvavo per 2 settimane. Serve la stessa serie su EEA per conferma e per usarlo come overlay sul canary/carry.
4. **Per rendere lo spread-z commerciabile standalone** servirebbe fee round-trip ≤ ~4-6bp: fuori portata retail (Lv1), raggiungibile solo con tier VIP alti/rebate MM — da valutare ma fuori dai costi attuali.
5. Non serve raccogliere più OHLCV 5-min: l'analisi su 2.25 anni è conclusiva (bordo lordo 0.2-0.5bp/trade su tutti i segnali bar-level).

## 6. File di output

- `report_finale.md` — questo report
- `risultati_ohlcv.json` — H1-H4 per fold: param scelti, net/gross, t-stat, wr, maxDD, Sharpe giorn., MC p5, fee×1.5
- `risultati_tick.json` — IC e decili per orizzonte, strategie nette DOGE/SOL
- `risultati_l2.json` — IC L2 train/verify, strategie nette maker/taker
- `risultati_spread_pred.json`, `risultati_spread_z.json` — IC spread→ritorno, bin condizionati, strategie pooled
- `trades_*.npy` — PnL e timestamp dei trade OOS per ispezione
- Script riproducibili: `loaders.py`, `engine.py`, `esplora_ohlcv.py`, `esperimento_ohlcv.py`, `esperimento_tick.py`, `esperimento_l2.py`, `esperimento_spread_pred.py`, `esperimento_spread_z.py`

**Conclusione**: nessun edge di microstruttura/orderflow sfruttabile netto-fee con API retail su OKX EEA ai dati attuali. Il segnale spread-z (IC −0.1/−0.35, stabile OOS) è l'unico utilizzabile, come overlay o con fee non-retail. Raccolta prioritaria: tick e quote OKX EEA a lungo termine.
