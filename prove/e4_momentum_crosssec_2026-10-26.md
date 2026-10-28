# E4 — Momentum cross-sectional normalizzato per volatilità (1d + 4h)

*Generato il 2026-10-26 21:52Z da `scripts/crosssec_mom_vol.py`. Tutte le soglie e la griglia sono pre-registrate nello script prima delle misure.*

## 0. Verdetto

**No. Non c'è un edge di momentum cross-sectional promuovibile: 0 varianti su 96 (24 per
strategia × 2 pannelli × 2 strategie) è positiva in OOS, e tutte e quattro le configurazioni
promosse dal train falliscono il cancello.**

I numeri che lo dicono (walk-forward onesto: promozione SOLO sul train fino 2024-06-01, OOS mai toccato):

- **Long-short 1d** (promossa `ls-L21-V60-invol`, miglior train a +0,21%): **OOS −16,11%/anno**,
  Sharpe OOS −1,06, t(NW) −1,88, maxDD 39,2%; **2/5 blocchi positivi** (serve 4/5); fee+50% → −18,82%;
  Monte Carlo p5 CAGR −26,9% (terminale p5 0,47); senza i 3 asset migliori (CRV, ELF, XLM) → −19,62%.
  Turnover 38 capitali/anno → pedaggio 5,0%/anno: il problema NON è il pedaggio, il **lordo è negativo**.
- **Long-only 1d** (promossa `lo-L21-V30-invol`): train **+47,3%/anno** ma **OOS −30,3%/anno**
  (Sharpe −0,34, maxDD 82,7%, 3/5 blocchi, fee+50% → −32,6%, MC p5 terminale **0,09**, senza top-3 → −38,5%).
  Il train era tutto nel 2020-2023 (2020 +125%, 2021 +552%, 2023 +193%): non si trasferisce, OOS 0/24 varianti positive.
- **4h bybit** (verifica indipendente sull'altro timeframe): LS −1,64%/anno e LO −4,94%/anno in OOS,
  0/24 varianti positive ovunque, mediana griglia −3,2% (LS) / −7,6% (LO). Stesso segno negativo del 1d.
- **Griglia completa**: 1d LS 0/24 positive OOS (mediana −23,4%); 1d LO 24/24 positive in TRAIN ma 0/24 in OOS
  (mediana −41,8%); correlazione train-OOS +0,25/+0,44: il ranking di train non si trasferisce.
- **Verifica indipendente del segno** (`prove/e4_sanity_check.py`, implementazione numpy scritta da zero):
  spread quintile lordo OOS (L63/V60) −18,4%/anno (t −1,83), long-only lordo −22,7%/anno (t −1,77):
  il segnale momentum vol-normalizzato è **anti-predittivo** OOS su questo universo, non solo neutro.
- **Sensibilità congelate**: igiene_stretta (via anche i 24 sospetti |r|>100%): LS −16,96%, LO −21,16% OOS;
  LO ristretto ai soli nomi spot-live OKX EEA: −30,29%; LS con funding 5,6%/anno sul nozionale short: −18,39%.

**Implementabilità su OKX EEA con il nostro conto (la domanda del mandato):** la versione **long-only**
è quella implementabile: opera SOLO spot, su nomi quotati su eea.okx.com (84/87 dell'universo 1d sono
spot-live oggi; ELF/ICX/STORJ risultano delistati — le serie ferme al 25-09; 85/123 ribilanciamenti OOS
con l'intera gamba long live, e il pannello ristretto ai soli live dà comunque −30,29% OOS). La versione
**long-short** NON è implementabile spot (lo short non esiste): servirebbero X-Perps, e **23/87 simboli
dell'universo 1d non hanno nemmeno lo swap** (BETH, BNT, CELR, CFG, CSPR, CVC, DGB, ELF, ICX, KNC, LAT,
LEO, LRC, LSK, ORBS, PHA, SKL, SNT, STORJ, SWFTC, TRA, VELO, XCH) + funding medio 5,6%/anno sul nozionale
short (misurato sul carry). In ogni caso la domanda è accademica: **nessuna delle due supera il cancello,
quindi nessuna delle due è promuovibile**.

**Confronto con crosssec_v2 (E3):** E3 (momentum/reversal raw 3-14g, k 3/5/10, R 1-7, 1d Bybit) aveva già
verdetto negativo (0/108 positive in entrambe le finestre, mediana −17,1%/anno, miglior t 0,66). Questo E4
allarga l'universo (87+56 simboli, okx_eea 1d + bybit 4h), usa il segnale "da manuale" (momentum 21-90 giorni
normalizzato per volatilità 30-90 giorni), ribilanciamento settimanale e quintili: **il verdetto non cambia,
anzi peggiora**: non solo nessuna variante passa, ma il segnale ha segno sistematicamente NEGATIVO fuori
campione su entrambi i timeframe. La corsia cross-sectional momentum resta chiusa.

**Pre-registrazione suggerita (non misurata qui — sarebbe snooping su questo OOS):** il segno negativo
sistematico (spread lordo −18%/anno con t −1,8, coerente su 1d e 4h e sull'implementazione indipendente)
indica che la versione **reversal** dello stesso identico ranking merita una nuova voce nel registro con
questo stesso cancello, dichiarata PRIMA di vedere i suoi numeri.

## 1. Universo e igiene
- **1d_okx**: 87 simboli, 2855 barre dal 2019-01-01 al 2026-10-25.
- **4h_bybit**: 56 simboli, 11548 barre dal 2021-07-05 al 2026-10-12.
- Serie bybit 1d: **nessun simbolo aggiuntivo** rispetto a okx_eea (sottoinsieme): il pannello 1d usa una sola sede (okx_eea, quella del conto); il 4h usa bybit come verifica indipendente.
- Esclusioni pre-dichiarate: `CTC` (redenominazione/token swap (+195,7% il 2023-12-12; wick 3822x sui 4h il 2022-09-21)); `GAS` (serie rotta: scala prezzi incoerente con il mercato (skill cache-ohlcv-igiene)); `USDC` (stablecoin: nessuna dispersione cross-sezionale, occupa una gamba).
- Sospetti NON esclusi in base (|r| giornaliero > 100%): `BAND`, `CFX`, `CHZ`, `CSPR`, `CVC`, `DOGE`, `ICX`, `IOST`, `KSM`, `LAT`, `LPT`, `LSK`, `MANA`, `NMR`, `OKB`, `ORBS`, `PHA`, `RSR`, `SHIB`, `STORJ`, `STX`, `SWFTC`, `UMA`, `VELO`. Scenario `igiene_stretta` in §7.

## 2. Meccanica
- Segnale: `score = ret(L giorni) / (sigma(V giorni)·sqrt(L))` con L ∈ (21, 42, 63, 90) e V ∈ (30, 60, 90) → 12 segnali × 2 pesi (ew, inverso-vol) = **24 varianti per strategia**, misurate su train e OOS.
- Portafoglio: quintili (k = n//5 per gamba, si opera solo con n ≥ 30 asset); LS = +1/(2k) top / −1/(2k) bottom (lordo 1,0, netto 0); LO = +1/k top (lordo 1,0).
- Ribilanciamento settimanale (prima barra di ogni settimana ISO), esecuzione alla chiusura con 1 barra di ritardo: **zero look-ahead** (verificato per troncamento, G1).
- Costi: 0.130% per lato (RT 0,26% = giro misto 0,18% + 2×0,04% slippage) sul turnover effettivo; chiusura forzata su fine dati: un lato sul peso.
- Walk-forward: train fino 2024-06-01, variante promossa = argmax CAGR netto train (tie-break: turnover minore entro 0,5 pp); OOS con variante **congelata**.

## 3. Griglia su train e OOS (24 varianti per strategia per pannello)
### 1d_okx — LS

| L | V | pesi | CAGR train | CAGR OOS | CAGR full | Sharpe OOS | t OOS | tNW OOS | maxDD full | turn/ann | costo ann |
|---|---|---|---|---|---|---|---|---|---|---|
| 21 | 60 | invol | +0.21% | -16.11% | -5.11% | -1.06 | -1.64 | -1.88 | 56.2% | 38.31 | +4.99% |
| 21 | 30 | invol | -1.91% | -15.81% | -6.41% | -0.95 | -1.47 | -1.63 | 61.8% | 39.60 | +5.16% |
| 21 | 60 | ew | -3.18% | -18.38% | -8.13% | -1.20 | -1.85 | -2.21 | 61.0% | 36.44 | +4.75% |
| 42 | 30 | invol | -4.02% | -18.43% | -8.70% | -1.17 | -1.81 | -1.84 | 65.7% | 31.63 | +4.12% |
| 42 | 60 | invol | -5.79% | -30.82% | -14.31% | -2.11 | -3.26 | -3.46 | 78.4% | 28.68 | +3.74% |
| 42 | 30 | ew | -6.69% | -23.44% | -12.19% | -1.55 | -2.40 | -2.62 | 71.0% | 28.43 | +3.71% |
| 21 | 30 | ew | -7.62% | -17.85% | -10.89% | -1.18 | -1.83 | -2.11 | 68.0% | 36.85 | +4.81% |
| 21 | 90 | invol | -8.23% | -17.10% | -11.05% | -1.12 | -1.74 | -2.03 | 62.9% | 37.49 | +4.89% |
| 42 | 90 | invol | -8.43% | -31.71% | -16.31% | -2.07 | -3.21 | -3.32 | 79.6% | 28.05 | +3.66% |
| 42 | 60 | ew | -9.47% | -33.39% | -17.61% | -2.34 | -3.62 | -4.01 | 81.8% | 26.63 | +3.48% |
| 21 | 90 | ew | -9.93% | -19.91% | -13.12% | -1.31 | -2.02 | -2.48 | 66.7% | 35.84 | +4.67% |
| 42 | 90 | ew | -11.83% | -32.27% | -18.69% | -2.20 | -3.42 | -3.74 | 81.9% | 26.30 | +3.43% |
| 90 | 30 | invol | -12.53% | -20.64% | -15.10% | -1.31 | -2.03 | -1.95 | 72.7% | 23.09 | +3.01% |
| 90 | 60 | invol | -14.10% | -21.73% | -16.52% | -1.41 | -2.19 | -2.09 | 75.6% | 21.10 | +2.75% |
| 90 | 30 | ew | -14.19% | -28.31% | -18.80% | -1.93 | -2.98 | -2.98 | 80.6% | 20.28 | +2.65% |
| 63 | 30 | invol | -14.79% | -19.19% | -16.17% | -1.24 | -1.93 | -1.94 | 79.8% | 26.94 | +3.52% |
| 63 | 60 | invol | -16.07% | -23.40% | -18.39% | -1.52 | -2.35 | -2.40 | 83.2% | 24.65 | +3.22% |
| 63 | 90 | invol | -16.11% | -26.12% | -19.32% | -1.67 | -2.59 | -2.62 | 82.3% | 23.52 | +3.07% |
| 90 | 60 | ew | -16.16% | -26.42% | -19.45% | -1.76 | -2.72 | -2.69 | 81.6% | 19.22 | +2.51% |
| 63 | 30 | ew | -16.27% | -24.39% | -18.86% | -1.65 | -2.55 | -2.70 | 84.0% | 23.87 | +3.12% |
| 63 | 90 | ew | -17.76% | -28.65% | -21.27% | -1.96 | -3.04 | -3.23 | 84.7% | 22.03 | +2.88% |
| 90 | 90 | invol | -18.51% | -22.29% | -19.69% | -1.38 | -2.13 | -2.03 | 82.0% | 20.19 | +2.64% |
| 63 | 60 | ew | -19.14% | -28.86% | -22.26% | -1.93 | -2.98 | -3.25 | 87.9% | 22.95 | +3.00% |
| 90 | 90 | ew | -20.28% | -27.27% | -22.49% | -1.79 | -2.77 | -2.71 | 86.7% | 18.80 | +2.46% |

### 1d_okx — LO

| L | V | pesi | CAGR train | CAGR OOS | CAGR full | Sharpe OOS | t OOS | tNW OOS | maxDD full | turn/ann | costo ann |
|---|---|---|---|---|---|---|---|---|---|---|
| 21 | 30 | invol | +47.29% | -30.32% | +17.05% | -0.34 | -0.53 | -0.51 | 88.6% | 38.85 | +5.07% |
| 21 | 60 | invol | +44.34% | -33.95% | +13.54% | -0.43 | -0.66 | -0.65 | 87.2% | 36.45 | +4.75% |
| 21 | 60 | ew | +36.75% | -42.59% | +4.76% | -0.53 | -0.83 | -0.84 | 91.3% | 33.67 | +4.39% |
| 21 | 30 | ew | +36.46% | -40.21% | +5.92% | -0.47 | -0.73 | -0.74 | 92.7% | 34.86 | +4.55% |
| 42 | 30 | invol | +33.34% | -31.63% | +8.61% | -0.42 | -0.65 | -0.67 | 88.3% | 30.59 | +3.99% |
| 42 | 60 | invol | +30.85% | -43.16% | +1.29% | -0.74 | -1.14 | -1.22 | 92.6% | 27.40 | +3.57% |
| 21 | 90 | invol | +25.02% | -36.28% | +1.65% | -0.48 | -0.75 | -0.74 | 89.4% | 35.50 | +4.63% |
| 42 | 30 | ew | +24.86% | -43.15% | -1.94% | -0.56 | -0.86 | -0.93 | 93.3% | 25.81 | +3.37% |
| 21 | 90 | ew | +22.68% | -44.29% | -3.73% | -0.58 | -0.90 | -0.91 | 92.2% | 33.30 | +4.34% |
| 63 | 60 | invol | +20.72% | -27.61% | +3.18% | -0.34 | -0.52 | -0.54 | 87.0% | 22.67 | +2.96% |
| 42 | 90 | invol | +20.37% | -41.85% | -3.73% | -0.68 | -1.05 | -1.13 | 92.0% | 26.57 | +3.47% |
| 90 | 30 | invol | +19.74% | -32.37% | +0.47% | -0.47 | -0.74 | -0.77 | 85.9% | 21.19 | +2.77% |
| 63 | 30 | invol | +19.53% | -29.58% | +1.61% | -0.39 | -0.60 | -0.62 | 90.3% | 25.34 | +3.31% |
| 42 | 60 | ew | +19.15% | -52.25% | -10.02% | -0.83 | -1.29 | -1.40 | 96.5% | 24.48 | +3.20% |
| 90 | 60 | invol | +18.98% | -30.08% | +1.06% | -0.40 | -0.62 | -0.65 | 83.2% | 19.84 | +2.59% |
| 90 | 30 | ew | +15.38% | -46.21% | -8.72% | -0.68 | -1.05 | -1.12 | 93.0% | 17.40 | +2.27% |
| 63 | 30 | ew | +13.48% | -43.03% | -8.16% | -0.56 | -0.87 | -0.94 | 95.4% | 21.11 | +2.76% |
| 63 | 90 | invol | +12.39% | -31.28% | -3.37% | -0.42 | -0.65 | -0.69 | 87.3% | 21.56 | +2.81% |
| 42 | 90 | ew | +12.27% | -49.72% | -12.27% | -0.75 | -1.16 | -1.26 | 95.7% | 24.06 | +3.14% |
| 90 | 60 | ew | +11.37% | -42.47% | -9.08% | -0.56 | -0.86 | -0.92 | 91.9% | 17.09 | +2.23% |
| 90 | 90 | invol | +11.26% | -28.07% | -2.69% | -0.35 | -0.55 | -0.56 | 85.1% | 18.42 | +2.41% |
| 63 | 60 | ew | +10.80% | -43.29% | -9.80% | -0.57 | -0.89 | -0.94 | 94.5% | 20.30 | +2.65% |
| 63 | 90 | ew | +9.36% | -43.44% | -10.69% | -0.58 | -0.90 | -0.96 | 93.0% | 19.56 | +2.56% |
| 90 | 90 | ew | +6.33% | -42.56% | -11.99% | -0.56 | -0.87 | -0.92 | 93.1% | 16.54 | +2.16% |

### 4h_bybit — LS

| L | V | pesi | CAGR train | CAGR OOS | CAGR full | Sharpe OOS | t OOS | tNW OOS | maxDD full | turn/ann | costo ann |
|---|---|---|---|---|---|---|---|---|---|---|
| 90 | 90 | invol | -1.80% | -1.64% | -1.73% | -0.19 | -0.72 | -0.71 | 47.3% | 4.12 | +0.54% |
| 90 | 60 | invol | -2.16% | -2.06% | -2.12% | -0.25 | -0.96 | -0.93 | 51.9% | 4.30 | +0.56% |
| 90 | 30 | invol | -2.31% | -2.41% | -2.35% | -0.30 | -1.12 | -1.06 | 55.3% | 4.52 | +0.59% |
| 21 | 60 | ew | -2.35% | -2.93% | -2.61% | -0.35 | -1.31 | -1.35 | 58.2% | 7.41 | +0.97% |
| 21 | 90 | invol | -2.36% | -2.50% | -2.42% | -0.31 | -1.17 | -1.19 | 56.1% | 7.58 | +0.99% |
| 21 | 90 | ew | -2.39% | -2.82% | -2.59% | -0.33 | -1.25 | -1.29 | 58.0% | 7.28 | +0.95% |
| 21 | 60 | invol | -2.41% | -2.98% | -2.66% | -0.38 | -1.43 | -1.46 | 58.6% | 7.75 | +1.01% |
| 21 | 30 | invol | -2.48% | -2.73% | -2.59% | -0.35 | -1.30 | -1.32 | 59.5% | 7.95 | +1.04% |
| 21 | 30 | ew | -2.57% | -2.77% | -2.66% | -0.32 | -1.22 | -1.27 | 60.3% | 7.52 | +0.98% |
| 90 | 90 | ew | -2.76% | -2.62% | -2.69% | -0.31 | -1.16 | -1.15 | 61.7% | 3.91 | +0.51% |
| 42 | 90 | invol | -2.78% | -3.69% | -3.19% | -0.50 | -1.87 | -1.80 | 66.5% | 5.54 | +0.72% |
| 90 | 60 | ew | -2.95% | -2.83% | -2.90% | -0.34 | -1.27 | -1.25 | 63.1% | 4.02 | +0.53% |
| 90 | 30 | ew | -3.05% | -3.62% | -3.31% | -0.44 | -1.64 | -1.63 | 67.4% | 4.18 | +0.55% |
| 42 | 90 | ew | -3.06% | -3.44% | -3.23% | -0.44 | -1.65 | -1.63 | 66.8% | 5.26 | +0.69% |
| 63 | 90 | invol | -3.24% | -3.19% | -3.22% | -0.43 | -1.62 | -1.59 | 65.6% | 4.60 | +0.60% |
| 42 | 60 | invol | -3.42% | -3.72% | -3.55% | -0.51 | -1.93 | -1.85 | 69.4% | 5.74 | +0.75% |
| 42 | 60 | ew | -3.43% | -3.31% | -3.38% | -0.42 | -1.60 | -1.57 | 67.7% | 5.42 | +0.71% |
| 63 | 90 | ew | -3.75% | -3.66% | -3.71% | -0.48 | -1.80 | -1.79 | 71.0% | 4.39 | +0.58% |
| 63 | 30 | invol | -3.88% | -3.17% | -3.56% | -0.44 | -1.65 | -1.60 | 68.8% | 5.12 | +0.67% |
| 63 | 60 | invol | -3.93% | -3.20% | -3.61% | -0.44 | -1.65 | -1.59 | 69.3% | 4.83 | +0.63% |
| 42 | 30 | invol | -4.11% | -3.79% | -3.97% | -0.53 | -2.00 | -1.90 | 73.7% | 6.13 | +0.80% |
| 42 | 30 | ew | -4.30% | -3.45% | -3.92% | -0.45 | -1.70 | -1.66 | 73.2% | 5.65 | +0.74% |
| 63 | 60 | ew | -4.49% | -3.51% | -4.05% | -0.46 | -1.72 | -1.70 | 73.8% | 4.61 | +0.60% |
| 63 | 30 | ew | -4.54% | -3.32% | -3.99% | -0.44 | -1.64 | -1.63 | 73.1% | 4.75 | +0.62% |

### 4h_bybit — LO

| L | V | pesi | CAGR train | CAGR OOS | CAGR full | Sharpe OOS | t OOS | tNW OOS | maxDD full | turn/ann | costo ann |
|---|---|---|---|---|---|---|---|---|---|---|
| 90 | 90 | invol | -3.44% | -4.94% | -4.11% | -0.07 | -0.26 | -0.27 | 84.1% | 3.65 | +0.48% |
| 90 | 30 | invol | -4.69% | -5.78% | -5.18% | -0.11 | -0.41 | -0.43 | 89.1% | 4.08 | +0.53% |
| 90 | 90 | ew | -4.73% | -7.65% | -6.05% | -0.13 | -0.49 | -0.51 | 91.9% | 3.42 | +0.45% |
| 90 | 60 | invol | -4.85% | -4.97% | -4.90% | -0.07 | -0.28 | -0.29 | 87.6% | 3.92 | +0.51% |
| 63 | 90 | invol | -5.31% | -6.33% | -5.77% | -0.12 | -0.44 | -0.46 | 90.1% | 4.13 | +0.54% |
| 90 | 60 | ew | -5.87% | -7.60% | -6.65% | -0.13 | -0.48 | -0.50 | 93.3% | 3.60 | +0.47% |
| 90 | 30 | ew | -5.91% | -8.78% | -7.21% | -0.17 | -0.66 | -0.69 | 94.5% | 3.70 | +0.49% |
| 42 | 90 | invol | -6.07% | -8.07% | -6.97% | -0.18 | -0.68 | -0.71 | 93.5% | 5.04 | +0.66% |
| 63 | 90 | ew | -6.16% | -8.53% | -7.23% | -0.16 | -0.60 | -0.63 | 94.3% | 3.90 | +0.51% |
| 21 | 90 | invol | -6.75% | -5.89% | -6.37% | -0.08 | -0.31 | -0.32 | 92.0% | 7.18 | +0.94% |
| 42 | 90 | ew | -6.76% | -9.21% | -7.87% | -0.18 | -0.69 | -0.73 | 95.4% | 4.74 | +0.62% |
| 21 | 90 | ew | -7.32% | -7.51% | -7.41% | -0.11 | -0.43 | -0.44 | 94.6% | 6.83 | +0.89% |
| 21 | 60 | invol | -7.37% | -6.44% | -6.95% | -0.11 | -0.40 | -0.42 | 92.9% | 7.26 | +0.95% |
| 63 | 30 | invol | -7.40% | -6.83% | -7.15% | -0.15 | -0.58 | -0.60 | 93.1% | 4.65 | +0.61% |
| 63 | 60 | invol | -7.46% | -6.57% | -7.06% | -0.13 | -0.50 | -0.53 | 92.9% | 4.34 | +0.57% |
| 21 | 30 | invol | -7.74% | -5.42% | -6.71% | -0.07 | -0.27 | -0.27 | 94.0% | 7.59 | +0.99% |
| 21 | 60 | ew | -7.75% | -7.82% | -7.78% | -0.13 | -0.48 | -0.49 | 94.8% | 6.85 | +0.90% |
| 42 | 60 | invol | -8.05% | -7.98% | -8.02% | -0.18 | -0.68 | -0.72 | 95.1% | 5.23 | +0.68% |
| 21 | 30 | ew | -8.24% | -6.93% | -7.66% | -0.09 | -0.36 | -0.37 | 95.7% | 7.03 | +0.92% |
| 63 | 60 | ew | -8.39% | -8.17% | -8.29% | -0.15 | -0.56 | -0.58 | 95.6% | 4.07 | +0.53% |
| 63 | 30 | ew | -8.53% | -8.26% | -8.41% | -0.16 | -0.59 | -0.62 | 95.7% | 4.15 | +0.54% |
| 42 | 30 | invol | -8.77% | -8.04% | -8.44% | -0.19 | -0.73 | -0.76 | 95.8% | 5.74 | +0.75% |
| 42 | 60 | ew | -8.83% | -8.74% | -8.79% | -0.17 | -0.63 | -0.66 | 96.3% | 4.86 | +0.64% |
| 42 | 30 | ew | -9.60% | -8.92% | -9.30% | -0.18 | -0.67 | -0.70 | 97.0% | 5.07 | +0.66% |

## 4. Varianti promosse e cancello OOS

| pannello | strategia | variante | G1 | G2 blocchi | G3 fee+50% | G4 MC p5 | G5 senza top3 |
|---|---|---|---|---|---|---|---|
| 1d_okx | LS | ls-L21-V60-invol | OK | 2/5 | -18.82% (FAIL) | CAGR -26.91% / term 0.47 (FAIL) | -19.62% (FAIL) |
| 1d_okx | LO | lo-L21-V30-invol | OK | 3/5 | -32.55% (FAIL) | CAGR -63.59% / term 0.09 (FAIL) | -38.50% (FAIL) |
| 4h_bybit | LS | ls-L90-V90-invol | OK | 2/5 | -1.93% (FAIL) | CAGR -4.87% / term 0.49 (FAIL) | -3.83% (FAIL) |
| 4h_bybit | LO | lo-L90-V90-invol | OK | 2/5 | -5.17% (FAIL) | CAGR -15.11% / term 0.10 (FAIL) | -9.55% (FAIL) |

## 5. Dettaglio delle varianti promosse (OOS)

### 1d_okx — LS — ls-L21-V60-invol

- CAGR OOS **-16.11%** · Sharpe OOS **-1.06** · t **-1.64** · t NW(7) **-1.88** · maxDD OOS **39.2%**
- CAGR train +0.21% · CAGR full -5.11% · turnover annuo **38.31** capitali/anno · costo annuo +4.99% · 305 ribilanciamenti
- blocchi OOS: 2024-06-01→2024-11-22 +0.34% | 2024-11-23→2025-05-16 -19.48% | 2025-05-17→2025-11-07 +11.21% | 2025-11-08→2026-05-01 -20.14% | 2026-05-02→2026-10-24 -8.59%
- per anno (full): 2019:+0.0% 2020:+24.6% 2021:-1.0% 2022:-2.2% 2023:+3.5% 2024:-28.7% 2025:-3.5% 2026:-22.8%
- MC OOS (block-bootstrap 7g, 3000 percorsi): p5 CAGR -26.91%, p50 CAGR -16.11%, p5 terminale 0.471.
- senza i 3 asset migliori OOS (`CRV, ELF, XLM`): CAGR OOS -19.62%, blocchi positivi 1/5.
- copertura OKX EEA: 80/123 ribilanciamenti OOS con la gamba long interamente spot-live su eea.okx.com; gamba short swap-live 0/123.
- sensibilità funding 5.6%/anno sul nozionale short: CAGR OOS -18.39%, blocchi positivi 1/5.

### 1d_okx — LO — lo-L21-V30-invol

- CAGR OOS **-30.32%** · Sharpe OOS **-0.34** · t **-0.53** · t NW(7) **-0.51** · maxDD OOS **82.7%**
- CAGR train +47.29% · CAGR full +17.05% · turnover annuo **38.85** capitali/anno · costo annuo +5.07% · 310 ribilanciamenti
- blocchi OOS: 2024-06-01→2024-11-22 +14.57% | 2024-11-23→2025-05-16 -38.52% | 2025-05-17→2025-11-07 +7.64% | 2025-11-08→2026-05-01 -47.77% | 2026-05-02→2026-10-24 +6.12%
- per anno (full): 2019:+0.0% 2020:+125.5% 2021:+552.0% 2022:-76.5% 2023:+192.8% 2024:-6.7% 2025:-51.1% 2026:-25.7%
- MC OOS (block-bootstrap 7g, 3000 percorsi): p5 CAGR -63.59%, p50 CAGR -30.82%, p5 terminale 0.089.
- senza i 3 asset migliori OOS (`TRX, XRP, CRV`): CAGR OOS -38.50%, blocchi positivi 3/5.
- copertura OKX EEA: 85/123 ribilanciamenti OOS con la gamba long interamente spot-live su eea.okx.com; gamba short swap-live 123/123.

### 4h_bybit — LS — ls-L90-V90-invol

- CAGR OOS **-1.64%** · Sharpe OOS **-0.19** · t **-0.72** · t NW(7) **-0.71** · maxDD OOS **28.7%**
- CAGR train -1.80% · CAGR full -1.73% · turnover annuo **4.12** capitali/anno · costo annuo +0.54% · 243 ribilanciamenti
- blocchi OOS: 2024-06-01→2024-11-20 -10.32% | 2024-11-20→2025-05-12 -1.49% | 2025-05-12→2025-10-31 +6.27% | 2025-10-31→2026-04-22 -16.05% | 2026-04-22→2026-10-11 +0.31%
- per anno (full): 2021:+0.0% 2022:-4.2% 2023:-11.5% 2024:-28.4% 2025:-1.5% 2026:-3.7%
- MC OOS (block-bootstrap 7g, 3000 percorsi): p5 CAGR -4.87%, p50 CAGR -1.65%, p5 terminale 0.492.
- senza i 3 asset migliori OOS (`TRX, MINA, RVN`): CAGR OOS -3.83%, blocchi positivi 0/5.
- copertura OKX EEA: 116/123 ribilanciamenti OOS con la gamba long interamente spot-live su eea.okx.com; gamba short swap-live 18/123.
- sensibilità funding 5.6%/anno sul nozionale short: CAGR OOS -2.10%, blocchi positivi 1/5.

### 4h_bybit — LO — lo-L90-V90-invol

- CAGR OOS **-4.94%** · Sharpe OOS **-0.07** · t **-0.26** · t NW(7) **-0.27** · maxDD OOS **79.8%**
- CAGR train -3.44% · CAGR full -4.11% · turnover annuo **3.65** capitali/anno · costo annuo +0.48% · 243 ribilanciamenti
- blocchi OOS: 2024-06-01→2024-11-20 +2.23% | 2024-11-20→2025-05-12 -4.24% | 2025-05-12→2025-10-31 -21.21% | 2025-10-31→2026-04-22 -41.90% | 2026-04-22→2026-10-11 +8.79%
- per anno (full): 2021:+0.0% 2022:-70.9% 2023:+90.5% 2024:+20.8% 2025:-57.8% 2026:-6.1%
- MC OOS (block-bootstrap 7g, 3000 percorsi): p5 CAGR -15.11%, p50 CAGR -5.07%, p5 terminale 0.098.
- senza i 3 asset migliori OOS (`TRX, XRP, CFG`): CAGR OOS -9.55%, blocchi positivi 1/5.
- copertura OKX EEA: 116/123 ribilanciamenti OOS con la gamba long interamente spot-live su eea.okx.com; gamba short swap-live 123/123.

## 6. Confronto con crosssec_v2 (E3)

Il precedente E3 (crosssec_v2) testava momentum/reversal **raw** a 3-14 giorni su 1d Bybit con k=3/5/10 e ribilanciamento 1-7 giorni: verdetto **nessun edge** (0/108 varianti positive in train e OOS, mediana −17,1%/anno netta, miglior t 0,66). Questo E4 cambia tre cose, pre-registrate: (a) segnale **normalizzato per volatilità** su orizzonti 21-90 giorni (il momentum di medio termine, non il reversal breve); (b) ribilanciamento **settimanale** fisso e quintili larghi (turnover più basso → pedaggio 1/3 di R=3); (c) universo okx_eea 1d (90 simboli) + verifica 4h bybit. I numeri netti OOS vanno letti contro il −2,3% annuo OOS della migliore E3.

## 7. Sensibilità aggiuntive (report-only, varianti congelate)

**igiene_stretta (1d)**: tolte anche le serie con |r| giornaliero > 100% (`BAND`, `CFX`, `CHZ`, `CSPR`, `CVC`, `DOGE`, `ICX`, `IOST`, `KSM`, `LAT`, `LPT`, `LSK`, `MANA`, `NMR`, `OKB`, `ORBS`, `PHA`, `RSR`, `SHIB`, `STORJ`, `STX`, `SWFTC`, `UMA`, `VELO`), varianti congelate, solo OOS:
- LS ls-L21-V60-invol: CAGR OOS -16.96%, blocchi positivi 1/5.
- LO lo-L21-V30-invol: CAGR OOS -21.16%, blocchi positivi 3/5.
**long-only 1d ristretto ai 84 nomi spot-live OKX EEA**:
- LO lo-L21-V30-invol: CAGR OOS -30.29%, blocchi positivi 3/5.

## 8. Riproducibilità

- script: `scripts/crosssec_mom_vol.py`; numeri completi: `e4_momentum_crosssec_2026-10-26.json`
- dati: `data/cache/okx_eea_*-USDT_1d.json` (90 file) e `data/cache/bybit_*-USDT_4h.json` (59 file), nessuna scrittura in cache.
- listing OKX EEA: `prove/e4_okx_instruments.json` (public instruments, letti il giorno del run).
