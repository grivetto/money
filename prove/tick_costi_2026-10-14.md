# Costi reali di esecuzione nelle cascate — tick Bybit (DOGE, SOL)

Generato da `scripts/tick_costi_cascata.py` il 2026-10-14 22:47:58 UTC.

## Perimetro e limiti (dichiarati)

Dati: tick *trade* Bybit (`public.bybit.com/trading`, gratuiti), colonne timestamp /
lato AGGRESSORE / size / prezzo. **Non c'e' l'order book storico**: lo spread quotato
best bid/ask non e' misurabile da qui. Tutti i numeri sotto sono PROXY da trade,
dichiarati come tali: VWAP su finestre, spread efficace buy-vs-sell su bucket da 10s,
stimatore di Roll. Per il dettaglio metodologico vedi l'intestazione dello script.

Costi assunti dal backtest cascate (`scripts/sonda_cascate.py`):
**0.26% round-trip** = 0.18% giro misto OKX + 2x0.04% slippage. Variante Bybit perp taker: 0.11% RT di sole fee.

- **DOGEUSDT**: 29 giorni (2026-09-13 -> 2026-10-11), 13,080,860 trade, 41,745 minuti con attivita', 624 ore contigue. Prezzo mediano 0.09271; passo di prezzo minimo osservato 9.999999999996123e-06 = **1.08 bps** (un attraversamento round-trip non puo' costare meno di 1 passo).
- **SOLUSDT**: 29 giorni (2026-09-13 -> 2026-10-11), 17,018,557 trade, 41,760 minuti con attivita', 624 ore contigue. Prezzo mediano 116.66; passo di prezzo minimo osservato 0.009999999999990905 = **0.86 bps** (un attraversamento round-trip non puo' costare meno di 1 passo).

## 1. Le ore piu' violente e i 10 minuti successivi

Segnale = chiusura dell'ora (t0). Tutte le misure partono dal **primo prezzo
disponibile dopo t0** (`px0`). Colonna `vol x72h` = volume dell'ora / media 72h
precedenti: `qualifica E2 = si` significa che l'ora soddisferebbe anche il filtro
del backtest cascate (drop <= -5% e volume >= 3x).

### Top 10 ore per |ritorno| — DOGEUSDT

| # | giorno (UTC) | ora | r_ora | drop 3h | USD ora | n trade | imb.ora | vol x72h | E2 (drop3<=-5% & vol>=3x) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 2026-10-08 | 15:00 | -5.14% | -4.91% | 48.59 M$ | 131,393 | -0.147 | 10.02 | no |
| 2 | 2026-09-23 | 14:00 | -4.58% | -4.55% | 82.48 M$ | 260,676 | -0.054 | 5.88 | no |
| 3 | 2026-10-02 | 18:00 | -3.63% | -4.27% | 31.66 M$ | 78,949 | -0.169 | 5.74 | no |
| 4 | 2026-09-22 | 03:00 | +3.06% | +2.52% | 22.25 M$ | 87,518 | +0.110 | 2.12 | no |
| 5 | 2026-09-21 | 15:00 | +2.48% | +4.11% | 56.91 M$ | 181,474 | +0.015 | 7.40 | no |
| 6 | 2026-09-21 | 08:00 | +2.39% | +3.97% | 27.40 M$ | 84,935 | +0.002 | 4.09 | no |
| 7 | 2026-09-21 | 18:00 | +2.37% | +2.44% | 22.38 M$ | 91,155 | +0.115 | 2.53 | no |
| 8 | 2026-09-23 | 15:00 | -2.25% | -6.79% | 25.56 M$ | 71,764 | -0.129 | 1.69 | no |
| 9 | 2026-10-07 | 01:00 | -2.19% | -1.66% | 9.06 M$ | 20,736 | -0.329 | 2.43 | no |
| 10 | 2026-09-18 | 13:00 | +2.14% | +1.74% | 12.23 M$ | 40,784 | +0.148 | 2.38 | no |

### Top 10 ore per CADUTA (ritorno piu' negativo) — DOGEUSDT

| # | giorno (UTC) | ora | r_ora | drop 3h | USD ora | n trade | imb.ora | vol x72h | E2 (drop3<=-5% & vol>=3x) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 2026-10-08 | 15:00 | -5.14% | -4.91% | 48.59 M$ | 131,393 | -0.147 | 10.02 | no |
| 2 | 2026-09-23 | 14:00 | -4.58% | -4.55% | 82.48 M$ | 260,676 | -0.054 | 5.88 | no |
| 3 | 2026-10-02 | 18:00 | -3.63% | -4.27% | 31.66 M$ | 78,949 | -0.169 | 5.74 | no |
| 4 | 2026-09-23 | 15:00 | -2.25% | -6.79% | 25.56 M$ | 71,764 | -0.129 | 1.69 | no |
| 5 | 2026-10-07 | 01:00 | -2.19% | -1.66% | 9.06 M$ | 20,736 | -0.329 | 2.43 | no |
| 6 | 2026-09-23 | 05:00 | -2.08% | -1.95% | 11.52 M$ | 36,191 | -0.216 | 0.87 | no |
| 7 | 2026-09-20 | 02:00 | -2.06% | -2.62% | 14.37 M$ | 35,071 | -0.275 | 2.49 | no |
| 8 | 2026-09-22 | 04:00 | -1.95% | +0.18% | 62.94 M$ | 223,074 | -0.030 | 5.86 | no |
| 9 | 2026-09-29 | 15:00 | -1.93% | -2.30% | 16.17 M$ | 52,406 | +0.025 | 3.01 | no |
| 10 | 2026-10-07 | 02:00 | -1.86% | -3.89% | 34.55 M$ | 104,438 | -0.101 | 9.02 | no |

### Eventi della definizione del backtest cascate — DOGEUSDT

**Nessun evento** nel periodo coperto dai tick (drop 3h <= -5% con volume >= 3x).

### Top 10 ore per |ritorno| — SOLUSDT

| # | giorno (UTC) | ora | r_ora | drop 3h | USD ora | n trade | imb.ora | vol x72h | E2 (drop3<=-5% & vol>=3x) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 2026-10-08 | 15:00 | -3.51% | -3.52% | 213.07 M$ | 137,248 | -0.157 | 7.31 | no |
| 2 | 2026-09-21 | 08:00 | +2.87% | +3.20% | 171.12 M$ | 117,160 | +0.096 | 5.04 | no |
| 3 | 2026-09-18 | 13:00 | +2.63% | +2.16% | 131.92 M$ | 109,446 | +0.065 | 3.92 | no |
| 4 | 2026-09-27 | 07:00 | +2.33% | +3.35% | 74.03 M$ | 54,105 | +0.201 | 2.02 | no |
| 5 | 2026-09-20 | 02:00 | -2.27% | -3.04% | 80.82 M$ | 58,095 | -0.170 | 2.34 | no |
| 6 | 2026-09-18 | 14:00 | +2.04% | +4.75% | 125.28 M$ | 110,587 | +0.064 | 3.60 | no |
| 7 | 2026-10-11 | 15:00 | +2.01% | +2.24% | 75.01 M$ | 35,245 | +0.335 | 3.61 | no |
| 8 | 2026-09-30 | 12:00 | +2.00% | +2.17% | 126.97 M$ | 89,279 | +0.076 | 3.48 | no |
| 9 | 2026-09-30 | 14:00 | -1.87% | -0.64% | 121.42 M$ | 112,347 | +0.032 | 3.12 | no |
| 10 | 2026-10-02 | 04:00 | +1.86% | +3.37% | 113.04 M$ | 85,156 | -0.015 | 3.01 | no |

### Top 10 ore per CADUTA (ritorno piu' negativo) — SOLUSDT

| # | giorno (UTC) | ora | r_ora | drop 3h | USD ora | n trade | imb.ora | vol x72h | E2 (drop3<=-5% & vol>=3x) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 2026-10-08 | 15:00 | -3.51% | -3.52% | 213.07 M$ | 137,248 | -0.157 | 7.31 | no |
| 2 | 2026-09-20 | 02:00 | -2.27% | -3.04% | 80.82 M$ | 58,095 | -0.170 | 2.34 | no |
| 3 | 2026-09-30 | 14:00 | -1.87% | -0.64% | 121.42 M$ | 112,347 | +0.032 | 3.12 | no |
| 4 | 2026-09-29 | 15:00 | -1.67% | -2.21% | 91.10 M$ | 68,964 | +0.049 | 2.59 | no |
| 5 | 2026-10-01 | 07:00 | -1.50% | -1.39% | 74.52 M$ | 40,133 | -0.100 | 1.95 | no |
| 6 | 2026-09-28 | 14:00 | -1.48% | -0.56% | 86.07 M$ | 73,674 | -0.187 | 2.59 | no |
| 7 | 2026-09-23 | 14:00 | -1.43% | -1.66% | 191.91 M$ | 150,224 | -0.012 | 4.43 | no |
| 8 | 2026-09-28 | 19:00 | -1.37% | -0.78% | 43.77 M$ | 30,106 | -0.285 | 1.40 | no |
| 9 | 2026-10-07 | 01:00 | -1.34% | -1.53% | 38.90 M$ | 20,614 | -0.033 | 1.64 | no |
| 10 | 2026-10-02 | 18:00 | -1.32% | -1.55% | 104.78 M$ | 70,994 | -0.157 | 2.78 | no |

### Eventi della definizione del backtest cascate — SOLUSDT

**Nessun evento** nel periodo coperto dai tick (drop 3h <= -5% con volume >= 3x).


## 2. Cosa succede nei 10 minuti dopo il segnale (misure sui tick)

`imp_H` = (VWAP di tutti i trade entro H secondi)/px0 - 1, in bps: e' il prezzo medio
pagato da chi esegue al mercato spalmando l'ordine su quella finestra.
`impbuy_H` = lo stesso usando **solo i trade con aggressore Buy** (piu' severo:
e' il prezzo medio di chi compra davvero). `impsell_H` = costo simmetrico per chi vende.
`min600/max600` = escursione peggiore/migliore entro 10 minuti rispetto a px0.
`spread10s` = spread efficace mediano su bucket da 10s con entrambi i lati
(proxy del pedaggio round-trip di attraversamento, senza fee). ATTENZIONE: e' un
**limite inferiore**, non lo spread quotato — su un bucket affollato i due VWAP
convergono e il proxy tende a 0, mentre lo spread vero non puo' scendere sotto 1 passo
di prezzo (colonna 'passo' nella tabella dei simboli). Il 'Roll' e' un secondo
stimatore indipendente, anch'esso un limite inferiore in presenza di deriva.

### DOGEUSDT

#### eventi: top 10 per |ritorno| (i piu' violenti in assoluto)

`vsrif` = prezzo eseguito rispetto alla **chiusura dell'ora del segnale** (il prezzo che il
backtest assume di pagare): negativo = si paga meno di quanto assume il backtest.

| giorno | ora | r_ora | attesa s | n60 | n600 | M$ 60s | M$ 600s | imb 60s | imb 600s | imp 60s | impbuy 60s | imp 120s | impbuy 120s | impsell 120s | vsrif px0 | vsrif vwap60 | min600 | max600 | close600 | spread10s(med) | Roll |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-10-08 | 15:00 | -5.14% | 0.1 | 1,599 | 12,838 | 0.387 | 3.49 | +0.37 | -0.15 | +15.6 | +16.1 | +9.4 | +11.1 | -7.1 | +0.0 | +15.6 | -65.4 | +47.2 | +47.2 | 0.6 | 0.1 |
| 2026-09-23 | 14:00 | -4.58% | 0.5 | 1,412 | 10,894 | 0.436 | 3.13 | +0.59 | +0.23 | -19.7 | -20.6 | -6.6 | -7.3 | +3.8 | -1.1 | -20.8 | -25.3 | +39.0 | +1.1 | -0.2 | 0.1 |
| 2026-10-02 | 18:00 | -3.63% | 0.2 | 1,216 | 6,214 | 0.745 | 2.32 | -0.32 | +0.01 | +5.7 | +1.0 | +9.2 | +9.4 | -9.1 | +0.0 | +5.7 | -8.8 | +33.0 | -1.1 | 0.2 | 0.2 |
| 2026-09-22 | 03:00 | +3.06% | 0.0 | 6,175 | 105,114 | 1.576 | 30.53 | +0.48 | +0.02 | +20.8 | +22.9 | +31.1 | +32.6 | -28.4 | +0.0 | +20.8 | -6.9 | +393.4 | +255.1 | 2.0 | 0.4 |
| 2026-09-21 | 15:00 | +2.48% | 0.3 | 2,326 | 22,393 | 0.679 | 5.51 | +0.27 | +0.04 | +6.0 | +5.4 | +18.3 | +20.2 | -13.8 | +0.0 | +6.0 | -46.3 | +61.7 | -22.6 | -0.3 | 0.2 |
| 2026-09-21 | 08:00 | +2.39% | 0.1 | 2,048 | 8,076 | 0.445 | 1.95 | -0.45 | -0.05 | -25.2 | -27.5 | -22.0 | -19.1 | +24.0 | -1.1 | -26.3 | -44.6 | +20.7 | -6.5 | 0.9 | 0.2 |
| 2026-09-21 | 18:00 | +2.37% | 0.2 | 1,396 | 16,761 | 0.319 | 5.04 | +0.30 | -0.19 | +3.8 | +3.9 | +0.5 | +1.0 | +0.3 | +1.0 | +4.8 | -121.4 | +33.1 | -112.4 | -0.1 | 0.5 |
| 2026-09-23 | 15:00 | -2.25% | 0.0 | 1,371 | 35,632 | 0.619 | 12.27 | +0.06 | -0.10 | +3.6 | +5.1 | -54.6 | -51.9 | +56.2 | +1.1 | +4.7 | -181.2 | +50.7 | +47.5 | 0.5 | 0.4 |
| 2026-10-07 | 01:00 | -2.19% | 0.1 | 8,752 | 83,531 | 3.239 | 25.96 | -0.22 | -0.15 | -41.7 | -39.4 | -220.8 | -230.2 | +214.6 | +0.0 | -41.7 | -405.6 | +14.2 | -160.3 | 0.7 | 1.2 |
| 2026-09-18 | 13:00 | +2.14% | 0.4 | 1,112 | 8,620 | 0.309 | 2.89 | -0.40 | -0.31 | +13.5 | +15.6 | +14.9 | +19.1 | -12.0 | -1.1 | +12.4 | -44.7 | +32.1 | -30.9 | 1.2 | 0.1 |

| minuto | USD medi | n trade | min bps (med) | close bps (med) | imb (med) |
|---|---|---|---|---|---|
| +1' | 0.532 M$ | 1,506 | -10.4 | +4.0 | +0.16 |
| +2' | 0.496 M$ | 2,046 | -10.2 | +8.7 | +0.09 |
| +3' | 0.449 M$ | 1,636 | -7.5 | +8.8 | -0.05 |
| +4' | 0.379 M$ | 1,606 | -8.8 | +4.0 | +0.09 |
| +5' | 0.311 M$ | 964 | -13.0 | -4.7 | -0.17 |
| +6' | 0.337 M$ | 836 | -17.2 | -1.1 | +0.10 |
| +7' | 0.269 M$ | 1,278 | -13.8 | -8.4 | -0.14 |
| +8' | 0.391 M$ | 1,414 | -17.6 | -4.8 | -0.20 |
| +9' | 0.363 M$ | 1,309 | -14.2 | +5.5 | +0.03 |
| +10' | 0.341 M$ | 902 | -7.7 | -3.8 | +0.06 |


#### eventi: top 10 per CADUTA (il caso del backtest cascate)

`vsrif` = prezzo eseguito rispetto alla **chiusura dell'ora del segnale** (il prezzo che il
backtest assume di pagare): negativo = si paga meno di quanto assume il backtest.

| giorno | ora | r_ora | attesa s | n60 | n600 | M$ 60s | M$ 600s | imb 60s | imb 600s | imp 60s | impbuy 60s | imp 120s | impbuy 120s | impsell 120s | vsrif px0 | vsrif vwap60 | min600 | max600 | close600 | spread10s(med) | Roll |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-10-08 | 15:00 | -5.14% | 0.1 | 1,599 | 12,838 | 0.387 | 3.49 | +0.37 | -0.15 | +15.6 | +16.1 | +9.4 | +11.1 | -7.1 | +0.0 | +15.6 | -65.4 | +47.2 | +47.2 | 0.6 | 0.1 |
| 2026-09-23 | 14:00 | -4.58% | 0.5 | 1,412 | 10,894 | 0.436 | 3.13 | +0.59 | +0.23 | -19.7 | -20.6 | -6.6 | -7.3 | +3.8 | -1.1 | -20.8 | -25.3 | +39.0 | +1.1 | -0.2 | 0.1 |
| 2026-10-02 | 18:00 | -3.63% | 0.2 | 1,216 | 6,214 | 0.745 | 2.32 | -0.32 | +0.01 | +5.7 | +1.0 | +9.2 | +9.4 | -9.1 | +0.0 | +5.7 | -8.8 | +33.0 | -1.1 | 0.2 | 0.2 |
| 2026-09-23 | 15:00 | -2.25% | 0.0 | 1,371 | 35,632 | 0.619 | 12.27 | +0.06 | -0.10 | +3.6 | +5.1 | -54.6 | -51.9 | +56.2 | +1.1 | +4.7 | -181.2 | +50.7 | +47.5 | 0.5 | 0.4 |
| 2026-10-07 | 01:00 | -2.19% | 0.1 | 8,752 | 83,531 | 3.239 | 25.96 | -0.22 | -0.15 | -41.7 | -39.4 | -220.8 | -230.2 | +214.6 | +0.0 | -41.7 | -405.6 | +14.2 | -160.3 | 0.7 | 1.2 |
| 2026-09-23 | 05:00 | -2.08% | 0.6 | 578 | 4,978 | 0.091 | 1.58 | -0.05 | +0.18 | +0.3 | +0.4 | -2.9 | -1.8 | +3.7 | -1.0 | -0.7 | -18.7 | +29.6 | +7.9 | 0.0 | 0.3 |
| 2026-09-20 | 02:00 | -2.06% | 0.2 | 1,157 | 8,466 | 0.359 | 2.73 | +0.02 | -0.07 | +5.3 | +9.4 | +0.6 | +4.7 | +4.5 | -1.2 | +4.1 | -43.3 | +69.1 | +32.8 | -0.1 | 0.2 |
| 2026-09-22 | 04:00 | -1.95% | 0.2 | 3,320 | 15,821 | 0.664 | 4.13 | +0.20 | +0.20 | -15.2 | -9.8 | -20.0 | -15.2 | +24.0 | -1.0 | -16.2 | -45.0 | +31.0 | -17.0 | 0.5 | 0.2 |
| 2026-09-29 | 15:00 | -1.93% | 0.4 | 883 | 4,620 | 0.148 | 1.02 | +0.68 | +0.22 | +2.0 | +2.2 | +8.4 | +8.8 | -6.1 | +0.0 | +2.0 | -7.5 | +29.9 | +21.4 | 0.4 | 0.1 |
| 2026-10-07 | 02:00 | -1.86% | 0.1 | 251 | 1,781 | 0.060 | 0.60 | +0.75 | +0.54 | +7.0 | +7.4 | +11.6 | +11.8 | -9.1 | +0.0 | +7.0 | +0.0 | +37.8 | +28.9 | 0.9 | 0.2 |

| minuto | USD medi | n trade | min bps (med) | close bps (med) | imb (med) |
|---|---|---|---|---|---|
| +1' | 0.411 M$ | 1,294 | -10.1 | +4.2 | +0.13 |
| +2' | 0.270 M$ | 1,238 | -17.2 | +3.4 | +0.07 |
| +3' | 0.387 M$ | 1,372 | -11.4 | +8.2 | -0.19 |
| +4' | 0.198 M$ | 823 | -2.2 | +2.0 | +0.17 |
| +5' | 0.224 M$ | 811 | -10.9 | +6.8 | +0.09 |
| +6' | 0.288 M$ | 854 | -5.0 | +19.6 | +0.50 |
| +7' | 0.185 M$ | 730 | +14.0 | +16.3 | +0.07 |
| +8' | 0.181 M$ | 817 | +3.2 | +9.6 | +0.17 |
| +9' | 0.111 M$ | 582 | +5.1 | +19.3 | +0.48 |
| +10' | 0.142 M$ | 746 | +10.0 | +14.6 | +0.32 |

### SOLUSDT

#### eventi: top 10 per |ritorno| (i piu' violenti in assoluto)

`vsrif` = prezzo eseguito rispetto alla **chiusura dell'ora del segnale** (il prezzo che il
backtest assume di pagare): negativo = si paga meno di quanto assume il backtest.

| giorno | ora | r_ora | attesa s | n60 | n600 | M$ 60s | M$ 600s | imb 60s | imb 600s | imp 60s | impbuy 60s | imp 120s | impbuy 120s | impsell 120s | vsrif px0 | vsrif vwap60 | min600 | max600 | close600 | spread10s(med) | Roll |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-10-08 | 15:00 | -3.51% | 0.1 | 1,861 | 17,764 | 1.480 | 23.55 | +0.20 | -0.27 | +9.8 | +9.9 | +4.5 | +7.0 | -2.1 | +0.0 | +9.8 | -59.0 | +24.9 | +10.1 | 0.4 | 0.2 |
| 2026-09-21 | 08:00 | +2.87% | 0.0 | 2,059 | 9,549 | 1.635 | 9.48 | -0.37 | +0.17 | -10.4 | -8.7 | -10.6 | -8.7 | +11.7 | -0.9 | -11.2 | -22.5 | +23.4 | +1.7 | 0.6 | 0.2 |
| 2026-09-18 | 13:00 | +2.63% | 0.1 | 3,242 | 21,271 | 2.122 | 20.89 | +0.15 | -0.04 | +14.8 | +16.1 | +24.3 | +24.9 | -23.7 | +0.0 | +14.8 | -13.8 | +47.9 | +17.5 | 0.6 | 0.2 |
| 2026-09-27 | 07:00 | +2.33% | 0.1 | 6,578 | 19,940 | 7.615 | 27.36 | +0.03 | -0.03 | +16.0 | +16.3 | +11.3 | +12.8 | -9.8 | +0.0 | +16.0 | -16.9 | +37.9 | +12.1 | -0.0 | 0.2 |
| 2026-09-20 | 02:00 | -2.27% | 0.2 | 2,038 | 12,441 | 2.253 | 13.97 | -0.03 | +0.26 | -0.4 | -0.9 | -1.8 | -1.0 | +2.7 | -0.9 | -1.3 | -26.0 | +81.8 | +53.9 | 0.5 | 0.2 |
| 2026-09-18 | 14:00 | +2.04% | 0.1 | 1,588 | 21,918 | 1.521 | 26.71 | +0.02 | -0.25 | +2.4 | +3.8 | -0.6 | +1.6 | +1.4 | -0.9 | +1.5 | -116.5 | +15.3 | -115.6 | 0.5 | 0.2 |
| 2026-10-11 | 15:00 | +2.01% | 0.1 | 1,893 | 9,046 | 2.603 | 19.03 | -0.35 | +0.19 | -7.8 | -5.5 | -15.5 | -16.5 | +14.4 | +0.9 | -6.9 | -30.4 | +12.5 | -18.8 | 0.4 | 0.3 |
| 2026-09-30 | 12:00 | +2.00% | 0.0 | 1,844 | 13,770 | 2.290 | 17.88 | -0.00 | +0.05 | +3.8 | +5.6 | -5.3 | +0.2 | +7.7 | -0.8 | +3.0 | -22.2 | +68.1 | +60.7 | 0.1 | 0.2 |
| 2026-09-30 | 14:00 | -1.87% | 0.1 | 1,475 | 10,796 | 1.552 | 12.32 | +0.07 | -0.23 | +4.1 | +3.9 | +5.9 | +5.4 | -6.4 | +0.0 | +4.1 | -11.0 | +23.6 | +7.6 | 0.7 | 0.2 |
| 2026-10-02 | 04:00 | +1.86% | 0.2 | 2,605 | 11,555 | 2.953 | 14.08 | +0.29 | +0.04 | +7.5 | +7.5 | +8.7 | +8.6 | -8.9 | +0.0 | +7.5 | -30.8 | +25.9 | -13.0 | -0.1 | 0.2 |

| minuto | USD medi | n trade | min bps (med) | close bps (med) | imb (med) |
|---|---|---|---|---|---|
| +1' | 2.188 M$ | 1,966 | -6.9 | +3.7 | +0.02 |
| +2' | 2.766 M$ | 1,864 | -16.1 | +1.6 | -0.16 |
| +3' | 1.617 M$ | 1,568 | -17.4 | -2.2 | -0.02 |
| +4' | 1.279 M$ | 1,106 | -9.7 | +0.1 | +0.06 |
| +5' | 1.737 M$ | 1,066 | -13.2 | +1.4 | +0.06 |
| +6' | 1.972 M$ | 1,252 | -4.1 | +9.4 | -0.02 |
| +7' | 1.076 M$ | 1,012 | -1.3 | +8.6 | -0.05 |
| +8' | 1.334 M$ | 1,080 | +0.2 | +3.9 | -0.18 |
| +9' | 1.156 M$ | 1,103 | -9.9 | +4.4 | +0.28 |
| +10' | 1.492 M$ | 956 | -5.8 | +8.9 | +0.04 |


#### eventi: top 10 per CADUTA (il caso del backtest cascate)

`vsrif` = prezzo eseguito rispetto alla **chiusura dell'ora del segnale** (il prezzo che il
backtest assume di pagare): negativo = si paga meno di quanto assume il backtest.

| giorno | ora | r_ora | attesa s | n60 | n600 | M$ 60s | M$ 600s | imb 60s | imb 600s | imp 60s | impbuy 60s | imp 120s | impbuy 120s | impsell 120s | vsrif px0 | vsrif vwap60 | min600 | max600 | close600 | spread10s(med) | Roll |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-10-08 | 15:00 | -3.51% | 0.1 | 1,861 | 17,764 | 1.480 | 23.55 | +0.20 | -0.27 | +9.8 | +9.9 | +4.5 | +7.0 | -2.1 | +0.0 | +9.8 | -59.0 | +24.9 | +10.1 | 0.4 | 0.2 |
| 2026-09-20 | 02:00 | -2.27% | 0.2 | 2,038 | 12,441 | 2.253 | 13.97 | -0.03 | +0.26 | -0.4 | -0.9 | -1.8 | -1.0 | +2.7 | -0.9 | -1.3 | -26.0 | +81.8 | +53.9 | 0.5 | 0.2 |
| 2026-09-30 | 14:00 | -1.87% | 0.1 | 1,475 | 10,796 | 1.552 | 12.32 | +0.07 | -0.23 | +4.1 | +3.9 | +5.9 | +5.4 | -6.4 | +0.0 | +4.1 | -11.0 | +23.6 | +7.6 | 0.7 | 0.2 |
| 2026-09-29 | 15:00 | -1.67% | 0.0 | 1,262 | 6,610 | 1.290 | 8.17 | +0.03 | +0.06 | +3.0 | +6.0 | +4.3 | +6.3 | -2.1 | +0.0 | +3.0 | -11.0 | +16.1 | +4.2 | 0.5 | 0.2 |
| 2026-10-01 | 07:00 | -1.50% | 0.1 | 537 | 5,157 | 0.446 | 6.28 | +0.63 | +0.20 | +5.2 | +5.2 | +4.2 | +4.8 | -3.2 | +0.0 | +5.2 | -18.7 | +13.6 | -8.5 | 0.4 | 0.2 |
| 2026-09-28 | 14:00 | -1.48% | 0.1 | 1,366 | 10,218 | 0.945 | 9.06 | +0.28 | +0.14 | +8.1 | +9.4 | +12.5 | +12.2 | -12.9 | +0.8 | +9.0 | -4.2 | +48.3 | +48.3 | -0.0 | 0.1 |
| 2026-09-23 | 14:00 | -1.43% | 0.3 | 1,070 | 9,482 | 1.203 | 10.62 | +0.31 | +0.13 | -3.4 | -2.3 | +7.5 | +8.0 | -6.5 | +0.0 | -3.4 | -12.2 | +31.3 | +10.4 | 0.7 | 0.2 |
| 2026-09-28 | 19:00 | -1.37% | 0.1 | 665 | 6,763 | 1.074 | 11.60 | +0.35 | +0.21 | +6.0 | +5.7 | -4.3 | +1.9 | +7.6 | +0.0 | +6.0 | -20.3 | +60.9 | +60.0 | 0.4 | 0.2 |
| 2026-10-07 | 01:00 | -1.34% | 0.1 | 9,443 | 54,620 | 19.301 | 79.25 | -0.50 | -0.09 | -37.3 | -26.3 | -77.2 | -83.1 | +73.7 | +0.0 | -37.3 | -167.4 | +7.6 | -100.9 | 1.4 | 0.4 |
| 2026-10-02 | 18:00 | -1.32% | 0.1 | 839 | 8,338 | 0.735 | 11.33 | +0.24 | +0.03 | +5.9 | +6.3 | +17.0 | +17.1 | -16.9 | +0.0 | +5.9 | -10.2 | +35.6 | -0.8 | 0.3 | 0.2 |

| minuto | USD medi | n trade | min bps (med) | close bps (med) | imb (med) |
|---|---|---|---|---|---|
| +1' | 1.246 M$ | 1,314 | -3.5 | +7.1 | +0.22 |
| +2' | 1.421 M$ | 1,186 | -3.0 | +9.7 | -0.06 |
| +3' | 1.137 M$ | 940 | -6.0 | +8.0 | -0.06 |
| +4' | 1.190 M$ | 886 | +1.7 | +7.2 | +0.27 |
| +5' | 0.850 M$ | 768 | -1.7 | +7.6 | -0.05 |
| +6' | 1.759 M$ | 924 | -0.9 | +11.0 | -0.06 |
| +7' | 0.967 M$ | 856 | -3.8 | +1.3 | -0.12 |
| +8' | 0.911 M$ | 838 | -6.9 | -0.0 | -0.12 |
| +9' | 0.729 M$ | 726 | -3.4 | +4.9 | +0.34 |
| +10' | 0.963 M$ | 853 | -2.5 | +8.9 | -0.00 |

## 3. Stima (conservativa) dello slippage di un market buy/sell

Proxy: differenza tra il **prezzo medio dei trade BUY nei primi 120s** e il primo
prezzo disponibile px0, in bps. E' conservativa in due sensi: (a) spalma l'ordine su
120 secondi, cosa che un'esecuzione reale non fa (ma il flusso viene tutto dal lato
che si muove contro di te), (b) ignora il consumo di liquidita' oltre il flusso
osservato. Per il sell e' speculare.

| simbolo | campione | n | slippage buy 120s (med) | p75 | slippage sell 120s (med) | p75 | RT stimato (buy+sell) | spread10s (med) |
|---|---|---|---|---|---|---|---|---|
| DOGEUSDT | top-|r| | 10 | +5.2 bps | +17.1 | -3.4 bps | +18.9 | **+1.8 bps** | 0.6 bps |
| DOGEUSDT | cadute | 10 | +1.4 bps | +9.3 | +3.8 bps | +19.1 | **+5.2 bps** | 0.4 bps |
| DOGEUSDT | controllo (ore normali) | 12 | +1.4 bps | +3.7 | -0.7 bps | +6.4 | **+0.8 bps** | 0.7 bps |
| SOLUSDT | top-|r| | 10 | +3.5 bps | +8.2 | -0.4 bps | +6.5 | **+3.2 bps** | 0.5 bps |
| SOLUSDT | cadute | 10 | +5.9 bps | +7.7 | -2.7 bps | +1.5 | **+3.2 bps** | 0.4 bps |
| SOLUSDT | controllo (ore normali) | 12 | -1.2 bps | +1.7 | +3.1 bps | +6.1 | **+1.9 bps** | 0.5 bps |

### 3b. Prezzo eseguito vs prezzo di riferimento del backtest (chiusura dell'ora)

Il backtest assume di comprare alla chiusura dell'ora con 4 bps di slippage per lato.
Qui si misura il prezzo *realmente disponibile* rispetto a quella chiusura, in bps.
Negativo = si paga MENO del prezzo assunto dal backtest, quindi lo slippage assunto non
serve (nella direzione sfavorevole); positivo = il mercato e' scappato.

| simbolo | campione | n | px0 vs rif | vwap 5s vs rif | vwap 60s vs rif | vwap buy 60s vs rif | vwap buy 120s vs rif |
|---|---|---|---|---|---|---|---|
| DOGEUSDT | top-|r| | 10 | +0.0 | +1.9 | +5.3 | +5.1 | +5.7 |
| DOGEUSDT | cadute | 10 | +0.0 | -0.4 | +3.0 | +1.6 | +0.3 |
| DOGEUSDT | controllo (ore normali) | 12 | +0.0 | +0.6 | +0.5 | +1.2 | +1.1 |
| SOLUSDT | top-|r| | 10 | +0.0 | -0.1 | +3.5 | +4.3 | +3.1 |
| SOLUSDT | cadute | 10 | +0.0 | +0.2 | +4.7 | +5.4 | +5.9 |
| SOLUSDT | controllo (ore normali) | 12 | +0.0 | -0.1 | -2.1 | -1.9 | -1.7 |

Slippage round-trip mediano — top-|r|: **+2.5 bps** vs controllo +1.3 bps (rapporto 1.9x).
Slippage round-trip mediano — cadute: **+4.2 bps** vs controllo +1.3 bps (rapporto 3.1x).

## 4. Confronto con il costo assunto (0,26% RT)

All-in = fee round-trip + slippage RT proxy misurato (mediana buy + mediana sell).

| simbolo | campione | fee RT | slippage RT proxy | costo all-in RT | vs assunto 0,26% |
|---|---|---|---|---|---|
| DOGEUSDT | cadute — OKX misto 0,18% | 0.18% | 5.2 bps (0.05%) | **0.232%** | -11% |
| DOGEUSDT | cadute — Bybit taker 0,11% | 0.11% | 5.2 bps (0.05%) | **0.162%** | -38% |
| DOGEUSDT | controllo (ore normali) — OKX misto 0,18% | 0.18% | 0.8 bps (0.01%) | **0.188%** | -28% |
| DOGEUSDT | controllo (ore normali) — Bybit taker 0,11% | 0.11% | 0.8 bps (0.01%) | **0.118%** | -55% |
| DOGEUSDT | top-|r| — OKX misto 0,18% | 0.18% | 1.8 bps (0.02%) | **0.198%** | -24% |
| DOGEUSDT | top-|r| — Bybit taker 0,11% | 0.11% | 1.8 bps (0.02%) | **0.128%** | -51% |
| SOLUSDT | cadute — OKX misto 0,18% | 0.18% | 3.2 bps (0.03%) | **0.212%** | -19% |
| SOLUSDT | cadute — Bybit taker 0,11% | 0.11% | 3.2 bps (0.03%) | **0.142%** | -45% |
| SOLUSDT | controllo (ore normali) — OKX misto 0,18% | 0.18% | 1.9 bps (0.02%) | **0.199%** | -23% |
| SOLUSDT | controllo (ore normali) — Bybit taker 0,11% | 0.11% | 1.9 bps (0.02%) | **0.129%** | -50% |
| SOLUSDT | top-|r| — OKX misto 0,18% | 0.18% | 3.2 bps (0.03%) | **0.212%** | -19% |
| SOLUSDT | top-|r| — Bybit taker 0,11% | 0.11% | 3.2 bps (0.03%) | **0.142%** | -46% |

Versione severa (p75 del buy + p75 del sell, non le mediane):

| simbolo | campione | slippage RT p75 | all-in (fee OKX 0,18%) |
|---|---|---|---|
| DOGEUSDT | cadute | 28.4 bps | **0.464%** |
| DOGEUSDT | controllo (ore normali) | 10.1 bps | **0.281%** |
| DOGEUSDT | top-|r| | 36.0 bps | **0.540%** |
| SOLUSDT | cadute | 9.2 bps | **0.272%** |
| SOLUSDT | controllo (ore normali) | 7.9 bps | **0.259%** |
| SOLUSDT | top-|r| | 14.6 bps | **0.326%** |

## 5. Impatto atteso per dimensione dell'ordine (proxy lineare, dichiarato)

Il costo sopra e' quello del *flusso*, cioe' di un ordine grande quanto l'intero
volume scambiato nella finestra. Per un ordine piu' piccolo il costo e' assunto
proporzionale alla quota di flusso che occupa (legge lineare di Kyle: approssimazione
- l'impatto reale e' sub-lineare, quindi questa stima e' prudenziale per ordini piccoli
e ottimistica per ordini grandi). Per lato: (proprio USD / USD taker nei primi 120s) x
slippage_buy_120s misurato. Eventi di caduta (il caso del backtest).

| simbolo | ordine | quota del flusso 120s (med) | slippage stimato per lato | all-in RT con fee 0,18% |
|---|---|---|---|---|
| DOGEUSDT | 10k$ | 1.39% | +0.02 bps | 0.181% |
| DOGEUSDT | 50k$ | 6.94% | +0.10 bps | 0.184% |
| DOGEUSDT | 100k$ | 13.88% | +0.20 bps | 0.187% |
| DOGEUSDT | 500k$ | 69.39% | +0.99 bps | 0.216% |
| DOGEUSDT | 1000k$ | 138.78% | +1.98 bps | 0.252% |
| SOLUSDT | 10k$ | 0.37% | +0.02 bps | 0.180% |
| SOLUSDT | 50k$ | 1.85% | +0.11 bps | 0.181% |
| SOLUSDT | 100k$ | 3.71% | +0.22 bps | 0.181% |
| SOLUSDT | 500k$ | 18.54% | +1.09 bps | 0.186% |
| SOLUSDT | 1000k$ | 37.08% | +2.17 bps | 0.192% |

## 6. Numeri chiave (generati) e verdetto

| simbolo | campione | slippage buy (med) | slippage sell (med) | spread10s (med) | all-in RT |
|---|---|---|---|---|---|
| DOGEUSDT | cadute | +1.4 bps | +3.8 bps | 0.4 bps | 0.232% |
| DOGEUSDT | top-|r| | +5.2 bps | -3.4 bps | 0.6 bps | 0.198% |
| SOLUSDT | cadute | +5.9 bps | -2.7 bps | 0.4 bps | 0.212% |
| SOLUSDT | top-|r| | +3.5 bps | -0.4 bps | 0.5 bps | 0.212% |

**Verdetto automatico**: il costo all-in piu' alto misurato e' 0.232%, sotto l'assunto di 0.26%. Il costo assunto regge.

Lettura a mano (dai numeri sopra) — vedi sezione successiva se presente.

