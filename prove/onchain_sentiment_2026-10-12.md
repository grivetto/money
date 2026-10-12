# On-chain e sentiment: dataset, segnali apparenti e verdetto (2026-10-12)

Ordine dell'utente: ampliare la ricerca ad altre classi di dato (on-chain, sentiment),
usando tutte le metodologie e l'infra multi-nodo. Questo documento registra cosa e'
stato fatto e **perche' nessun segnale e' stato promosso**.

## 1. Cosa c'e' di nuovo (dati)

| Fonte | Copertura | Costo |
|---|---|---|
| CoinMetrics community | 11 asset, BTC **5.763 giorni** (15,8 anni), ETH 4.092 | 0 |
| metriche | MVRV, FlowInEx/OutEx, SplyEx, AdrActCnt, HashRate, TxCnt, PriceUSD, ... | 0 |
| Fear & Greed (alternative.me) | **3.172 giorni** (dal 2018-02-01) | 0 |
| DefiLlama TVL | 3.303 giorni | 0 |

Script: `scripts/scarica_esterni.py`. Dati in `data/esterni/` (26 MB, fuori da git).

## 2. Segnali APPARENTEMENTE forti (perche' non bastava fermarsi qui)

Setaccio (`scripts/setaccia_onchain.py`, 290 coppie metrica x asset x orizzonte):
- MVRV grezzo BTC -> rendimento 30g: corr **+0.267, t=+20.9** (n=5733)
- F&G -> rendimento 30g: DOGE corr +0.210 t=+12.0; BTC +0.131 t=+7.4
- 131/290 coppie con |t| > 2.5

Backtest long/flat (`scripts/backtest_onchain.py`), "OOS dal 2021-01-01":
- **MVRV momentum** (> media 180g): BTC **+713%** (sharpe 1.19, DD -26%) vs B&H +185%;
  ETH +686% (sharpe 0.96) vs B&H +247%
- **F&G > 50**: ETH +821% (sharpe 1.03); DOGE +9672%

Sembrava un edge. **Non lo era.** Tre difetti strutturali:

1. **Il t-stat e' gonfiato**: rendimenti a 30 giorni su dati giornalieri si sovrappongono
   -> il t reale e' ~sqrt(30) volte piu' piccolo (~3.8, non 20.9).
2. **Il periodo "OOS dal 2021" e' contaminato** dal bull 2021 (DOGE +10.325% in un anno).
3. **BTC 2011-2026 e' un bull market secolare**: qualunque variabile crescente correla
   col prezzo (trend mascherato). Alcune "metriche" erano perfino metadata
   (AssetCompletionTime), cioe' artefatti.

## 3. Il test che decide: walk-forward genuino, per anno e per parametro

`scripts/walkforward_sentiment.py` e `scripts/walkforward_mvrv.py`.

**F&G > 50, split temporali genuini:**

| Split | BTC | ETH | DOGE |
|---|---|---|---|
| train 2018-2020 | perde | vince | perde |
| OOS-1 2021-2022 | VINCE | VINCE | VINCE |
| **OOS-2 2023-2026** | **-42.5% vs +403.6%** | **-39.5% vs +111.1%** | **-59.6% vs +23.7%** |
| OOS 2021-2026 | -39.1% vs +184.7% | +112.5% vs +246.6% | +2154% vs +1457% |

**Sensibilita' alla soglia (BTC, 2021-2026)**: 20:-93% | 30:-69% | 40:-42% | 50:-39% |
**60:+45%** | 70:-2%. Il segno che cambia con la soglia e' la firma del curve-fit.

**Totale dal 2018**: meta' degli asset in perdita (LTC -60%, XLM -47%, BCH -29%, ADA -23%).

**MVRV momentum, split genuini:**

| Split | BTC | ETH | DOGE | ADA |
|---|---|---|---|---|
| train 2018-2020 | VINCE | VINCE | perde | VINCE |
| OOS-1 2021-2022 | VINCE | VINCE | VINCE | VINCE |
| **OOS-2 2023-2026** | **+9% vs +404%** | **-22% vs +111%** | **+4% vs +24%** | **-31% vs +1%** |
| OOS 2021-2026 | perde | perde | vince | vince |

**Sensibilita' alla finestra (BTC, 2021-2026)**: 60:+27% | 90:+4% | 120:+52% | 180:+65% |
250:-12% | 365:-29%. Instabile.

**Lettura**: entrambi i segnali vincono nel bull 2021 e perdono nel 2023-2026; nessuno
protegge nel bear 2022 (BTC -7% nel 2018, ETH -17% nel 2022 = long durante il crollo).
Chi "vince" lo fa per il regime, non per informazione.

## 4. Il trend puro non e' la spiegazione, ma non basta

`scripts/confronto_trend.py`: SMA200 batte B&H solo **3/11** asset; MVRV-mom batte SMA200
**9/11**. Quindi l'on-chain non e' un semplice trend travestito... ma **quello che aggiunge
non sopravvive all'out-of-sample genuino** (sezione 3). Un'informazione che funziona
solo in-sample/in-regime non e' negoziabile.

## 5. Verdetto

**Nessun edge promosso.** La pista on-chain/sentiment e' chiusa con la stessa evidenza
delle altre: walk-forward genuino, sensibilita' ai parametri, confronto con buy&hold.

Consuntivo delle arene testate (tutte con dati reali, tutte bocciate):
1. Candele, 20 famiglie, 5+ anni, 59 simboli, **tutti i timeframe**:
   - 1d -> 0 candidati (sr0 0.42)
   - 4h -> 0 candidati (sr0 1.08)
   - 1h -> 0 candidati (sr0 1.21)
   Su timeframe piu' fini la soglia DSR sale e la fee pesa di piu': il collo di
   bottiglia non e' la risoluzione temporale.
2. Order-flow a 1 minuto, 30M tick -> 85-350x sotto i costi
3. Market making simulato, 48k fill -> perdita sistematica (t fino a -94)
4. Basis cross-venue, 39 simboli -> rumore/sotto soglia
5. On-chain (MVRV, flussi exchange, indirizzi) -> bocciato da walk-forward
6. Sentiment (Fear & Greed) e TVL -> bocciati da walk-forward

**Il valore prodotto non e' un edge, e' un cancello che ha fermato sei strategie che
sembravano buone prima di toccare capitale reale.** Il capitale resta in Earn (~5%/anno),
il canary resta live, l'infra e i dati restano a terra per il giorno in cui un edge
dovesse presentarsi.
