# E1 — Carry DINAMICO delta-neutral: esiste un edge? (misura, 2026-10-14)

> Autore: agente Hermes (subagent su task delegato). Solo endpoint PUBBLICI, nessuna chiave,
> nessun ordine, nessuna scrittura fuori da `data/funding_bybit/`.
> Precedente: `prove/carry_funding_2026-10-12.md` (carry **sempre attivo**, OKX EEA, 96 giorni) →
> 5-8%/anno lordi sul nozionale, cioè **pari o sotto** il pavimento Simple Earn (~5%/anno).

## 1. La domanda (e perché è diversa dalla precedente)

Il carry continuo non paga: il funding medio delle major è ~5-8%/anno e il capitale richiesto è
`2 × nozionale` (1x su entrambe le gambe, entrambe finanziate) → ROC ~2,5-4%/anno, sotto l'Earn.

Il carry **dinamico** non chiede il funding medio, chiede il funding **episodico**: esistono
giorni/settimane in cui il funding sulle alt va al 20-60% annuo, e in quelle finestre lo switch
si ripaga in pochi giorni. La domanda misurabile è quindi:

> Con la regola della spec congelata MOSAICO4 §3.4 — entra solo se il funding atteso paga i costi
> di switch in ≤7 giorni e batte il pavimento 5%/anno; esci sotto il pavimento — il carry
> delta-neutral batte il pavimento su **storia lunga** e su dati **out-of-sample**, **dopo** i costi?

L'OKX EEA ha solo ~96 giorni di funding (insufficiente). Questa misura usa **Bybit**, che ha
storia dal 2020.

## 2. Regola dichiarata PRIMA di guardare i risultati (congelata)

Formula del segnale = quella della spec MOSAICO4 §3.1, presa dal modulo congelato
`src/money/mosaico/signal.py::funding_forecast` (nessuna reimplementazione):

```
forecast(i) = min( media_robusta(funding8h[i-2..i]) , quantile_25(funding8h[i-29..i]) )
ann(i)      = forecast(i) * 3 * 365               # "Annualizzato = rate_8h * 3 * 365"
payback(i)  = 0,0033 / (forecast(i) * 3)          # giorni necessari a ripagare lo switch
APRI   <=> ann(i) > 5%/anno  AND  payback(i) <= 7 giorni
CHIUDI <=> ann(i) < 5%/anno
```

| parametro | valore dichiarato | fonte |
|---|---|---|
| costo switch RT | **0,33% del nozionale** (spot 0,26% = 0,18% fee + 0,08% slippage; perp 0,07%) | CONTEXT del task |
| pavimento di entrata/uscita | **5%/anno** (Simple Earn) | CONTEXT del task |
| payback massimo | **7 giorni** | CONTEXT del task |
| capitale impegnato | `2 × nozionale` (1x su entrambe le gambe, entrambe finanziate) | CONTEXT del task |
| split | train ≤ 2024-06-01 < OOS | CONTEXT del task |
| annualizzazione | `funding8h × 3 × 365` | CONTEXT del task |

Soglia operativa equivalente: `payback ≤ 7 giorni` ⟺ `ann ≥ 0,0033 × 365 / 7 = 17,2044%/anno`,
quindi la condizione **vincolante** è il payback (17,2% > 5%); il pavimento 5% governa l'**uscita**
(isteresi: entri sopra 17,2%, esci sotto 5%, in mezzo resti fermo).

**No look-ahead (regola dura, verificata).** La decisione presa al tempo `t_i`, usando **solo** le
osservazioni `funding[0..i]` (il funding già pagato a `t_i`), governa il periodo `(t_i, t_{i+1}]`,
che incassa `funding[i+1]`. Le soglie e i costi sono costanti dichiarate, **non ottimizzate**.
Test empirico (ETHUSDT, 6554 osservazioni): perturbando *tutti* i funding successivi a `t_3000`
(valori 0,01 / -0,01 / 0,00001) i 868 eventi con `ts ≤ t_3000` restano **identici**. Un
simbolo rieseguito due volte dà risultati bit-identici.

**Normalizzazione a 8 ore (necessaria per non falsare i numeri).** Il periodo di funding di Bybit
non è sempre 8h e **cambia nel tempo**: 13 dei 58 simboli (AXS, CTC, EGLD, FLOW, GAS, LRC, MASK,
MINA, RVN, STX, UMA, XTZ, ZRX) passano a 1h/2h/4h in certi anni. Ogni rate è quindi riscritto come
equivalente a 8h con il gap **reale che lo precede** (`rate × 8h / gap`, gap limitato a [1h, 24h]):
segnale e annualizzazione usano l'equivalente 8h; il **PnL** usa il rate reale pagato (cash flow
vero). Il fattore usa solo il passato → nessun look-ahead.

**Varianti provate — contate tutte** (servono per la deflazione multiple-testing / DSR):

| # | variante | differenza rispetto alla regola |
|---|---|---|
| v0 | `v0_sempre_attivo` | baseline del lavoro precedente: apre subito e resta dentro (1 switch) |
| v1 | `v1_regola_dichiarata` | **la regola dichiarata** (primaria) |
| v2 | `v2_payback_14g` | payback massimo 14 giorni invece di 7 |
| v3 | `v3_uscita_a_zero` | come v1 ma esce dopo 2 funding negativi (toglie il pavimento in uscita) |

Totale: **4 varianti di regola** provate (`n_varianti = 4`). Non è stata fatta selezione del
simbolo migliore: **tutti** i 58 simboli sono riportati nella tabella E. Se in futuro qualcuno
selezionasse il migliore a posteriori, la molteplicità da deflazionare sarebbe 4 × 58.

## 3. Dati

- **Fonte**: `GET https://api.bybit.com/v5/market/funding/history?category=linear&symbol=<SYM>&limit=200`,
  paginazione all'indietro con `endTime = (più vecchio visto) − 1 ms`. Endpoint **pubblico**, nessuna
  chiave; `fundingRate` + `fundingRateTimestamp` (ms UTC).
- **Nota sull'host**: il task indicava `api.bybit.eu`. Verificato il 2026-10-14: su quell'host
  `instruments-info?category=linear` torna **lista vuota** e `funding/history` torna
  `retCode 10001 "params error: Symbol Invalid"` per qualunque simbolo → l'entità EEA non espone i
  perp lineari via API pubblica. Si usa `api.bybit.com` (stesso schema v5, stesso endpoint, pubblico).
- **Copertura**: 58 simboli su 59 della cache `data/cache/bybit_*_1d.json`.
  Escluso **CSPR** (nessun perp lineare su Bybit). **SHIB** è coperto dal perp `SHIB1000USDT`
  (namespacing Bybit, stesso sottostante). **USDCUSDT** è incluso (funding ~0: utile come controllo).
- **Orari/periodo**: 370.314 osservazioni, dal **2020-03-25** (BTCUSDT) al **2026-10-14** (tutti);
  4 simboli hanno storia che parte nel 2026 (BNT, CFG, GAS, e simili) → per loro il train è nullo.
- File grezzi: `data/funding_bybit/<SIMBOLO>.json` (58 file, formato
  `{"simbolo","periodo_ore","primo_ts","ultimo_ts","n","osservazioni":[[ts_ms, rate], ...]}`).
- Download completo in ~3 minuti con 8 richieste concorrenti (log in `$TMPDIR/carry_dl.log`).

### A — aggregato, le 4 varianti (58 simboli, 2020-03-25 → 2026-10-14)

| variante | ROC cal. medio | ROC cal. mediano | ROC in posizione | quota tempo in pos. | ROC+Earn sul tempo libero | netto/capitale agg. | simboli ROC>0 | simboli ROC>5% | switch tot |
|---|---|---|---|---|---|---|---|---|---|
| `v0_sempre_attivo` | 1.7312% | 3.2751% | 1.7313% | 1.000 | 1.7301% | 2.4465% | 47/58 | 14 | 58 |
| `v1_regola_dichiarata` | 1.7193% | 1.2766% | 15.7712% | 0.090 | 6.2696% | 1.8756% | 56/58 | 3 | 207 |
| `v2_payback_14g` | 0.9854% | 1.4802% | 2.5117% | 0.521 | 3.3794% | 1.3486% | 42/58 | 4 | 5289 |
| `v3_uscita_a_zero` | 1.8502% | 1.4466% | 14.2962% | 0.111 | 6.2956% | 2.0185% | 55/58 | 4 | 184 |

**Lettura di A.** Il ROC è *del capitale* (= netto / 2 × nozionale), annualizzato sul tempo di
calendario: è la metrica da confrontare col 5% dell'Earn. `ROC in posizione` è la stessa cosa ma
diviso solo per il tempo effettivamente in posizione (misura la qualità del filtro, non il
rendimento che ottieni). `ROC+Earn sul tempo libero` = ROC calendario + 5% × (quota di tempo
fuori posizione): l'unico modo onesto di includere il fatto che il capitale fermo può stare in Earn.

### B — ROC medio del capitale per anno (media equal-weight sui simboli con dati)

| variante | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|
| `v0_sempre_attivo` | 26.535 | 15.1627 | -2.2568 | 2.5934 | 6.1054 | -0.1662 | -3.5611 |
| `v1_regola_dichiarata` | 20.488 | 12.8697 | 0.1075 | 0.4659 | 3.1629 | 0.3327 | 0.0 |
| `v2_payback_14g` | 25.2918 | 15.0934 | -1.5287 | 2.3889 | 4.0243 | -2.9564 | -2.2695 |
| `v3_uscita_a_zero` | 20.5008 | 13.5593 | 0.2101 | 0.4774 | 3.5594 | 0.257 | 0.0 |


### C — train (≤2024-06-01) vs OOS (>2024-06-01), ROC medio del capitale per simbolo

| variante | train n | train medio | train mediano | train t(H0:0) | OOS n | OOS medio | OOS mediano | OOS t(H0:0) | OOS t(H0:5%) | OOS simboli >5% |
|---|---|---|---|---|---|---|---|---|---|---|
| `v0_sempre_attivo` | 57 | 3.824% | 4.985% | 4.55 | 58 | -0.085% | 1.888% | -0.13 | -7.48 | 2 |
| `v1_regola_dichiarata` | 56 | 3.143% | 2.403% | 9.01 | 58 | 0.184% | 0.174% | 7.54 | -196.91 | 0 |
| `v2_payback_14g` | 57 | 3.773% | 3.639% | 7.60 | 58 | -1.605% | -0.615% | -3.06 | -12.58 | 1 |
| `v3_uscita_a_zero` | 56 | 3.352% | 2.600% | 9.29 | 58 | 0.231% | 0.251% | 7.93 | -163.89 | 0 |


### D — t-test complessivo (per-simbolo ROC calendario, tutta la storia)

| variante | media | sd | t(H0:0) | t(H0:5%) |
|---|---|---|---|---|
| `v0_sempre_attivo` | 1.731% | 6.080 | 2.17 | -4.09 |
| `v1_regola_dichiarata` | 1.719% | 1.525 | 8.59 | -16.38 |
| `v2_payback_14g` | 0.985% | 3.288 | 2.28 | -9.30 |
| `v3_uscita_a_zero` | 1.850% | 1.586 | 8.88 | -15.13 |


### E — per simbolo (v1 = regola dichiarata; v0 = sempre attivo, confronto)

| simbolo | primo funding | n oss. | periodo attuale | switch | quota in pos. | ROC cal. | ROC in posizione | ROC train | ROC OOS | ROC cal. v0 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1INCHUSDT | 2021-12-06 | 5320 | 8h | 3 | 0.100 | 1.16% | 11.59% | 2.013 | 0.2602 | 3.13% |
| AAVEUSDT | 2021-05-13 | 5941 | 8h | 7 | 0.106 | 1.47% | 13.94% | 2.4631 | 0.1952 | 4.98% |
| ADAUSDT | 2021-03-18 | 6110 | 8h | 6 | 0.124 | 3.92% | 31.70% | 6.6379 | 0.2511 | 6.78% |
| ALGOUSDT | 2021-09-23 | 5543 | 8h | 4 | 0.056 | 1.45% | 25.93% | 2.6879 | 0.0369 | 5.14% |
| ATOMUSDT | 2021-10-11 | 5489 | 8h | 5 | 0.074 | 1.46% | 19.60% | 2.6977 | 0.076 | 1.76% |
| AVAXUSDT | 2021-09-15 | 5566 | 8h | 3 | 0.097 | 1.60% | 16.57% | 2.9553 | 0.0481 | 3.24% |
| AXSUSDT | 2021-08-31 | 6605 | 8h | 4 | 0.036 | 0.55% | 15.30% | 1.07 | -0.0574 | -18.74% |
| BATUSDT | 2021-11-24 | 5357 | 8h | 3 | 0.044 | 0.63% | 14.18% | 1.0372 | 0.1918 | 4.10% |
| BCHUSDT | 2020-12-14 | 6392 | 8h | 5 | 0.125 | 4.98% | 39.74% | 8.3538 | 0.052 | 5.30% |
| BNTUSDT | 2023-08-07 | 3495 | 8h | 1 | 0.029 | 0.19% | 6.53% | 0.7426 | 0.0 | 0.88% |
| BTCUSDT | 2020-03-25 | 7183 | 8h | 7 | 0.114 | 2.73% | 23.96% | 4.1625 | 0.2083 | 6.33% |
| CELOUSDT | 2022-01-05 | 5230 | 8h | 3 | 0.086 | 1.18% | 13.77% | 2.2557 | 0.0996 | 2.03% |
| CFGUSDT | 2026-03-17 | 1271 | 4h | 0 | 0.000 | 0.00% | 0.00% | None | 0.0 | -25.22% |
| CHZUSDT | 2021-10-12 | 5486 | 8h | 3 | 0.096 | 1.76% | 18.31% | 3.1197 | 0.2528 | 2.67% |
| COMPUSDT | 2021-08-31 | 5611 | 8h | 3 | 0.090 | 1.69% | 18.67% | 3.1413 | 0.0 | 1.03% |
| CRVUSDT | 2021-10-25 | 5447 | 8h | 4 | 0.067 | 0.89% | 13.30% | 1.6163 | 0.1007 | 2.68% |
| CTCUSDT | 2022-05-17 | 8224 | 4h | 4 | 0.039 | 0.04% | 1.10% | 0.1995 | -0.0916 | -11.79% |
| DGBUSDT | 2022-03-28 | 4296 | 8h | 1 | 0.089 | 1.31% | 14.68% | 2.3619 | 0.0 | 3.31% |
| DOGEUSDT | 2021-06-02 | 5881 | 8h | 4 | 0.119 | 2.22% | 18.67% | 3.7202 | 0.3211 | 5.81% |
| DOTUSDT | 2021-03-18 | 6110 | 8h | 5 | 0.112 | 2.81% | 25.23% | 4.8388 | 0.073 | 4.35% |
| EGLDUSDT | 2021-11-23 | 12583 | 1h | 3 | 0.080 | 1.03% | 12.97% | 1.6984 | 0.3212 | 1.77% |
| ETCUSDT | 2021-06-29 | 5801 | 8h | 4 | 0.115 | 2.36% | 20.46% | 4.0878 | 0.2295 | 3.95% |
| ETHUSDT | 2020-10-21 | 6554 | 8h | 5 | 0.178 | 4.25% | 23.78% | 6.8106 | 0.3373 | 6.92% |
| FILUSDT | 2021-06-29 | 5801 | 8h | 3 | 0.134 | 2.80% | 20.90% | 4.7471 | 0.3985 | 5.72% |
| FLOWUSDT | 2021-11-26 | 13549 | 1h | 5 | 0.101 | 1.08% | 10.70% | 1.8574 | 0.2561 | -2.62% |
| GASUSDT | 2023-10-23 | 7175 | 2h | 3 | 0.150 | 1.98% | 13.19% | 8.9849 | 0.1836 | -11.43% |
| GRTUSDT | 2021-12-06 | 5320 | 8h | 2 | 0.072 | 0.81% | 11.36% | 1.3512 | 0.2497 | 4.29% |
| HBARUSDT | 2021-10-25 | 5447 | 8h | 4 | 0.079 | 1.60% | 20.31% | 2.7942 | 0.289 | 4.54% |
| ICPUSDT | 2021-09-15 | 5566 | 8h | 4 | 0.083 | 1.60% | 19.27% | 2.69 | 0.3536 | 4.63% |
| ICXUSDT | 2022-04-13 | 4872 | 8h | 2 | 0.191 | 1.72% | 9.01% | 2.4441 | 1.0483 | 6.20% |
| KSMUSDT | 2021-10-12 | 5486 | 8h | 3 | 0.054 | 0.89% | 16.55% | 1.6309 | 0.0597 | 1.83% |
| LINKUSDT | 2020-10-21 | 6554 | 8h | 5 | 0.188 | 6.56% | 34.88% | 10.6898 | 0.2747 | 10.14% |
| LRCUSDT | 2021-11-11 | 7061 | 8h | 3 | 0.063 | 0.59% | 9.42% | 1.0806 | 0.0657 | -2.60% |
| LTCUSDT | 2020-10-21 | 6554 | 8h | 5 | 0.190 | 6.60% | 34.68% | 10.9307 | 0.0126 | 9.63% |
| MANAUSDT | 2021-11-08 | 5433 | 8h | 3 | 0.082 | 0.93% | 11.37% | 1.6783 | 0.1175 | 3.50% |
| MASKUSDT | 2021-12-03 | 11639 | 1h | 2 | 0.064 | 0.62% | 9.59% | 1.2104 | -0.0106 | 0.50% |
| MINAUSDT | 2022-04-07 | 8214 | 4h | 4 | 0.072 | 1.21% | 16.77% | 2.2389 | 0.2739 | 0.50% |
| NEARUSDT | 2021-10-11 | 5489 | 8h | 3 | 0.099 | 1.92% | 19.39% | 3.4031 | 0.2666 | 4.55% |
| QTUMUSDT | 2021-12-13 | 5299 | 8h | 2 | 0.085 | 1.07% | 12.61% | 1.6044 | 0.5172 | 2.41% |
| RVNUSDT | 2022-01-06 | 11566 | 1h | 2 | 0.098 | 0.97% | 9.98% | 1.4202 | 0.5225 | 0.86% |
| SANDUSDT | 2021-11-01 | 5516 | 8h | 3 | 0.084 | 1.24% | 14.76% | 2.2335 | 0.1608 | 2.12% |
| SHIB1000USDT | 2021-10-20 | 5462 | 8h | 6 | 0.047 | 1.23% | 26.04% | 2.2743 | 0.0786 | 3.76% |
| SNXUSDT | 2021-12-13 | 5299 | 8h | 2 | 0.091 | 0.98% | 10.75% | 1.669 | 0.2632 | 0.60% |
| SOLUSDT | 2021-06-29 | 6161 | 8h | 4 | 0.118 | 2.11% | 17.83% | 3.5689 | 0.3157 | 0.23% |
| STXUSDT | 2021-12-03 | 13604 | 1h | 7 | 0.074 | 0.82% | 11.02% | 1.3334 | 0.2775 | -4.76% |
| SUSHIUSDT | 2021-05-13 | 5941 | 8h | 4 | 0.104 | 1.66% | 15.90% | 2.8735 | 0.1021 | 4.87% |
| THETAUSDT | 2021-08-31 | 5611 | 8h | 4 | 0.121 | 2.20% | 18.13% | 3.907 | 0.2225 | 5.63% |
| TRXUSDT | 2021-08-31 | 5611 | 8h | 5 | 0.046 | 0.65% | 14.03% | 1.0892 | 0.1301 | -0.52% |
| UMAUSDT | 2023-06-08 | 6340 | 4h | 2 | 0.096 | 0.74% | 7.66% | 1.8075 | 0.2947 | -2.67% |
| UNIUSDT | 2021-03-18 | 6110 | 8h | 3 | 0.094 | 2.24% | 23.83% | 3.7675 | 0.1638 | 5.57% |
| USDCUSDT | 2022-06-28 | 4827 | 8h | 1 | 0.001 | -0.04% | -60.23% | -0.0856 | 0.0 | 0.78% |
| VELOUSDT | 2024-05-20 | 2633 | 8h | 1 | 0.019 | 0.50% | 25.86% | None | 0.5079 | 5.53% |
| XLMUSDT | 2021-08-31 | 5611 | 8h | 3 | 0.103 | 2.06% | 20.01% | 3.8272 | 0.0205 | 3.92% |
| XRPUSDT | 2021-05-13 | 5941 | 8h | 4 | 0.131 | 2.34% | 17.80% | 3.9536 | 0.257 | 4.97% |
| XTZUSDT | 2020-10-21 | 11953 | 4h | 7 | 0.158 | 6.79% | 43.02% | 11.2593 | -0.0055 | 7.68% |
| YFIUSDT | 2021-12-10 | 5309 | 8h | 2 | 0.029 | 0.13% | 4.31% | 0.1908 | 0.0598 | 3.33% |
| ZILUSDT | 2022-01-30 | 5648 | 8h | 3 | 0.038 | 0.44% | 11.52% | 0.8124 | 0.0781 | -1.65% |
| ZRXUSDT | 2022-03-28 | 6217 | 8h | 4 | 0.079 | 0.99% | 12.55% | 2.0834 | -0.0151 | -1.99% |


## 4. Verdetto — **NO, l'edge non c'è** (almeno non sopra il pavimento)

1. **Agli aggregati la regola dichiarata sta decisamente sotto il pavimento.** v1 rende
   **1,72%/anno** sul capitale (mediana 1,28%), contro il 5% dell'Earn: t-test contro H0: μ=5%
   dà **−16,4** sui 58 simboli. Su tutta la storia **solo 3 simboli su 58** battono il 5%
   (XTZ 6,79%, LTC 6,60%, LINK 6,56%) e sono esattamente i simboli con la storia più favorevole
   (2021). La regola "sempre attivo" (v0) fa **1,73%/anno**: identica. Il filtro non sposta nulla
   al livello di portafoglio.
2. **L'unica parte informativa del segnale è reale ma viene diluita.** Quando è dentro, v1
   incassa funding per un equivalente di **15,77%/anno sul capitale** (contro 1,73% di v0 sempre
   dentro): il filtro seleziona davvero le finestre di funding alto, ~9× la media incondizionata.
   Ma ci sta dentro solo il **9% del tempo** → 0,09 × 15,8 ≈ 1,4%/anno di calendario, che è tutto
   ciò che il carry aggiunge: il resto del tempo il capitale deve stare fermo (o in Earn, e allora
   non è merito del carry).
3. **Out-of-sample il carry dinamico è zero.** Dal 2024-06-01 a oggi (2,4 anni):
   v1 rende **+0,18%/anno** (mediana 0,17%) e sta in posizione il **2,5%** del tempo;
   **0 simboli su 58** battono il 5%. Il "sempre attivo" rende **−0,09%/anno**. Il test sul
   sotto-periodo ha t=7,5 contro 0 (la dispersione cross-sezionale è minuscola e i simboli sono
   correlati: non è una prova di forza, è una prova che *non è negativo*) ma piazza il risultato
   a un ordine di grandezza dal pavimento: per la domanda posta, la risposta è la stessa di prima.
4. **La fotografia onesta del capitale**: se sul tempo libero metti il capitale in Earn, il
   pacchetto v1 rende **6,27%/anno** su tutta la storia (1,72% di carry + 5% × 91% di tempo libero)
   ma solo **5,06%/anno** nell'OOS (0,18% di carry + 5% × 97,5% di tempo libero), contro il 5,00%
   del **non fare nulla**: +0,06 pp/anno, cioè ~0,7 €/anno
   sul capitale della flotta (~1.100 €), in cambio di due gambe, margine, funding che può girare
   negativo, riconciliazione. Non è un edge, è arrotondamento.
5. **Dov'è l'edge, allora? Solo nel passato.** Il carry ha pagato in **2020-2021** (ROC medio
   20,5% e 12,9%/anno per v1) e in misura minore nel 2024 (3,2%); dal 2022 in poi è piatto o
   negativo e nel 2026 è esattamente **0,00%** (mai in posizione: la soglia di 17,2%/anno non è
   più stata superata). La tesi "spike episodici" era vera nel regime di funding del 2021: con
   funding strutturalmente più basso e più efficiente (2024-2026) non si ripresenta.
6. **Varianti: nessuna salva la baracca.** v2 (payback 14g) è peggio (0,99%/anno, OOS −1,6%);
   v3 (uscita a zero) è marginalmente meglio (1,85%/anno, OOS 0,23%), sempre sotto il pavimento.
   Le tre varianti "a soglia" percorrono tutte 0,99-1,85%/anno: nessuna combinazione di
   soglie-e-isteresi sposta il problema, perché il problema non è la soglia — è che i giorni di
   funding alto sono troppo pochi e troppo concentrati nel 2021.

**Conclusione.** Un 'no' netto: la regola di carry dinamico delta-neutral di MOSAICO4 §3.4, con i
costi e il pavimento dichiarati, **non batte il Simple Earn** su storia lunga Bybit (1,72%/anno
contro 5%), **non batte nulla out-of-sample** (0,18%/anno, 0/58 simboli sopra il pavimento) e il
suo contributo marginale su un portafoglio che tiene il resto in Earn è **+0,06 pp/anno**. Il
segnale di selezione funziona (in posizione il funding è ~16%/anno), ma la copertura temporale
(9% in-sample, 2,5% OOS) lo rende economicamente irrilevante. Se in futuro si volesse riprovare,
la domanda giusta non è "quale soglia" ma "esiste un modo di stare esposti al funding alto **senza
impegnare 2× il nozionale per tutto il tempo**" — e quella è una domanda diversa, non misurata qui.

## 5. Limiti dichiarati (cosa NON è stato provato)

- Una sola fonte (Bybit linear). Il funding OKX su ~96 giorni dà numeri coerenti (5-8%/anno lordi
  sempre-attivo) → nessun motivo di credere a un artefatto venue-specifico, ma non è verificato su
  Binance/OKX per la storia lunga.
- PnL di prezzo delle due gambe assunto nullo (delta-neutral) e **basis drift non modellato**:
  gli switch avvengono a funding-noto, il che in un mercato con basis ampio è un'idealizzazione.
- Slippage assunto 0,08% sullo spot e 0 nell'entry/exit del perp oltre la fee; su alt illiquide è
  probabilmente **peggiore** → i numeri sopra sono un limite superiore.
- Esecuzione istantanea alla rilevazione del funding (nessun ritardo operativo, nessun partial fill).
- Un simbolo = una "slot" di capitale da 2× nozionale; nessun vincolo di margine condiviso, nessuna
  gestione del rischio di liquidazione (a 1x è a ~99,5%, quindi non vincolante).
- Non testate: leva >1x (alza il ROC ma introduce liquidazione), selezione cross-sezionale
  top-K (è selezione a posteriori: da deflazionare), funding su altri venue.

## 6. Comandi riproducibili

```bash
cd /home/sergio/money
# 1) scarica la storia funding Bybit (endpoint pubblici, ~59 simboli, ~3 min)
.venv/bin/python scripts/backtest_carry_dinamico.py scarica --parallelo 8
# 2) backtest delle 4 varianti, tabella a video + JSON completo (~3 min)
.venv/bin/python scripts/backtest_carry_dinamico.py backtest --json "$TMPDIR/e1_carry_dinamico.json"
# 3) una sola variante
.venv/bin/python scripts/backtest_carry_dinamico.py backtest --variante v1_regola_dichiarata
```

Il modulo del segnale è quello congelato: `src/money/mosaico/signal.py::funding_forecast`
(importato, non ricopiato). Lo script inserisce `src/` nel `sys.path` da solo, quindi non serve
`PYTHONPATH=src`.

## 7. File prodotti

| file | contenuto |
|---|---|
| `data/funding_bybit/<SIMBOLO>.json` | 58 serie di funding Bybit (370.314 osservazioni, 2020-03-25 → 2026-10-14) |
| `scripts/backtest_carry_dinamico.py` | downloader + backtest delle 4 varianti (questo lavoro) |
| `prove/e1_carry_dinamico_2026-10-14.md` | questo report |
