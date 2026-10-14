# Pulizia cache Bybit — audit di igiene dati

- Generato: **2026-10-14 22:40:27 UTC** da `scripts/igiene_cache.py` (sola lettura sulla cache)
- Ambito: `data/cache/bybit_*.json` — **177 file**
- Artefatto JSON: `data/cache_igiene.json` (sha256 `9c1514d0e2728f62`)
- Riproduzione:

```bash
cd /home/sergio/money
.venv/bin/python scripts/igiene_cache.py --report prove/pulizia_cache_2026-10-14.md
# solo regole letterali (senza estensioni H4/S5):
.venv/bin/python scripts/igiene_cache.py --senza-estensioni --out /tmp/igiene_letterale.json
```

## 1. Metodo

Un file e' **rotto** se contiene almeno una firma dura, **sospetto** se non ha firme dure ma ha
almeno un'anomalia di scala/buco/volume, **ok** altrimenti.

| regola | categoria | origine | definizione operativa |
|---|---|---|---|
| `H0_file_illeggibile` | rotto | letterale | JSON non leggibile o struttura non conforme (venue/simbolo/timeframe/barre[6]) |
| `H1_ritorno_close` | rotto | letterale | |ritorno close-to-close di 1 barra| > 300% |
| `H2_prezzo_non_positivo` | rotto | letterale | prezzo open/high/low/close <= 0 oppure NaN/inf |
| `H3_ts_non_monotoni` | rotto | letterale | timestamp non strettamente crescenti (duplicati o fuori ordine) |
| `H4_crollo_intrabarra` | rotto | estensione | high/low dello stesso bar > 100x (crollo/swap intra-barra invisibile al close-to-close) |
| `S1_scala` | sospetto | letterale | scala anomala: max(high)/min(low) > 1e5 |
| `S2_prezzo_min` | sospetto | letterale | prezzo minimo < 1e-5 |
| `S3_buco` | sospetto | letterale | buco: distanza tra barre consecutive > 5x il timeframe |
| `S4_volume_zero` | sospetto | letterale | oltre 24 barre consecutive con volume == 0 |
| `S5_picco_isolato` | sospetto | estensione | picco isolato: high/low > 3x i bar adiacenti con range intra-barra > 3x |
| `I_buco` | info | informativa | barra mancante (buco > 1.5x il timeframe) |
| `I_range` | info | informativa | barra con range intra-barra > 3x |
| `I_volume_zero` | info | informativa | run di volume zero >= 5 barre |
| `I_serie_troncata` | info | informativa | serie che finisce > 2x il timeframe prima della fine comune dello stesso timeframe |

Soglie: ritorno close-to-close > 300% · high/low intra-barra > 100x · max/min > 1e+05 · prezzo min < 1e-05 · buco > 5x tf · volume zero > 24 barre · picco > 3x i vicini.

Precisazioni: i ritorni sono calcolati **close-to-close**; `max/min` e `prezzo minimo` sono calcolati
su **tutti i prezzi OHLC** (max dei high, min dei low), che e' la lettura piu' inclusiva; un **buco** e'
la distanza tra due timestamp consecutivi divisa per la durata del timeframe.

### 1.1 Estensioni attive

Due regole aggiunte alle definizioni letterali, entrambe necessarie a coprire casi reali:

- **`H4_crollo_intrabarra`** — CTC-USDT ha subito un token swap il 2022-09-21: nella serie `1d` il
  crollo (0.30 → 8e-05 → 0.29) compare **solo come low di una singola candela**, quindi il ritorno
  close-to-close non lo vede e la serie `1d` passerebbe per `ok` pur contenendo un finto −99,97%.
  Soglia 100x con margine enorme: il massimo range intra-barra di tutto il resto della cache e' 10,8x.
- **`S5_picco_isolato`** — AVAX-USDT porta un tick spurio isolato (high 1000.2774 il 2021-11-18 mentre
  il prezzo di mercato era ~100): nessuna firma dura, ma e' un dato da rivedere prima dei backtest.

Con le sole regole letterali i conteggi sarebbero: rotto 3, sospetto 6.

## 2. Conteggi

| categoria | file | quota |
|---|---|---|
| **ok** | 164 | 92.7% |
| **sospetto** | 9 | 5.1% |
| **rotto** | 4 | 2.3% |
| **totale** | 177 | 100.0% |

| regola scattata | file |
|---|---|
| `H1_ritorno_close` (rotto) | 3 |
| `H4_crollo_intrabarra` (rotto) | 3 |
| `S2_prezzo_min` (sospetto) | 6 |
| `S5_picco_isolato` (sospetto) | 3 |

## 3. File ROTTI (4 file, 2 simboli)

| file | n barre | primo ts (UTC) | ultimo ts (UTC) | motivo |
|---|---|---|---|---|
| `bybit_CTC-USDT_1d.json` | 1613 | 2022-05-13 00:00 | 2026-10-12 00:00 | H4_crollo_intrabarra |
| `bybit_CTC-USDT_1h.json` | 38702 | 2022-05-13 10:00 | 2026-10-12 00:00 | H1_ritorno_close + H4_crollo_intrabarra |
| `bybit_CTC-USDT_4h.json` | 9676 | 2022-05-13 08:00 | 2026-10-12 00:00 | H1_ritorno_close + H4_crollo_intrabarra |
| `bybit_ICX-USDT_1h.json` | 41330 | 2022-01-06 07:00 | 2026-09-24 08:00 | H1_ritorno_close |

### 3.1 `bybit_CTC-USDT_1d.json` — H4_crollo_intrabarra

- **H4_crollo_intrabarra**: barre con high/low > 100x: 1
  - 2022-09-21 00:00 (UTC): O 0.30096 H 0.311135 L 8e-05 C 0.292734 — high/low = **3889x**

### 3.2 `bybit_CTC-USDT_1h.json` — H1_ritorno_close + H4_crollo_intrabarra

- **H1_ritorno_close**: barre con |ritorno close-to-close| > 300%: 1
  - 2022-09-21 12:00 (UTC): close 8e-05 → 0.306735 = **+383318.75%**
- **H4_crollo_intrabarra**: barre con high/low > 100x: 2
  - 2022-09-21 12:00 (UTC): O 8e-05 H 0.308909 L 8e-05 C 0.306735 — high/low = **3861x**
  - 2022-09-21 11:00 (UTC): O 0.303649 H 0.303649 L 8e-05 C 8e-05 — high/low = **3796x**

### 3.3 `bybit_CTC-USDT_4h.json` — H1_ritorno_close + H4_crollo_intrabarra

- **H1_ritorno_close**: barre con |ritorno close-to-close| > 300%: 1
  - 2022-09-21 12:00 (UTC): close 8e-05 → 0.30539 = **+381637.50%**
- **H4_crollo_intrabarra**: barre con high/low > 100x: 2
  - 2022-09-21 12:00 (UTC): O 8e-05 H 0.311135 L 8e-05 C 0.30539 — high/low = **3889x**
  - 2022-09-21 08:00 (UTC): O 0.303671 H 0.30579 L 8e-05 C 8e-05 — high/low = **3822x**

### 3.4 `bybit_ICX-USDT_1h.json` — H1_ritorno_close

- **H1_ritorno_close**: barre con |ritorno close-to-close| > 300%: 1
  - 2026-09-21 16:00 (UTC): close 0.01004 → 0.05804 = **+478.09%**

## 4. File SOSPETTI (9)

| file | n barre | primo ts (UTC) | ultimo ts (UTC) | motivo |
|---|---|---|---|---|
| `bybit_AVAX-USDT_1d.json` | 1795 | 2021-11-12 00:00 | 2026-10-12 00:00 | S5_picco_isolato |
| `bybit_AVAX-USDT_1h.json` | 43072 | 2021-11-12 08:00 | 2026-10-12 00:00 | S5_picco_isolato |
| `bybit_AVAX-USDT_4h.json` | 10768 | 2021-11-12 08:00 | 2026-10-12 00:00 | S5_picco_isolato |
| `bybit_GAS-USDT_1d.json` | 437 | 2021-12-29 00:00 | 2023-03-10 00:00 | S2_prezzo_min |
| `bybit_GAS-USDT_1h.json` | 10458 | 2021-12-29 13:00 | 2023-03-10 06:00 | S2_prezzo_min |
| `bybit_GAS-USDT_4h.json` | 2615 | 2021-12-29 12:00 | 2023-03-10 04:00 | S2_prezzo_min |
| `bybit_SHIB-USDT_1d.json` | 1771 | 2021-12-06 00:00 | 2026-10-12 00:00 | S2_prezzo_min |
| `bybit_SHIB-USDT_1h.json` | 42497 | 2021-12-06 07:00 | 2026-10-12 00:00 | S2_prezzo_min |
| `bybit_SHIB-USDT_4h.json` | 10625 | 2021-12-06 04:00 | 2026-10-12 00:00 | S2_prezzo_min |

- `bybit_AVAX-USDT_1d.json`: **S5_picco_isolato** picchi isolati (> 3x i bar adiacenti): 1
- `bybit_AVAX-USDT_1h.json`: **S5_picco_isolato** picchi isolati (> 3x i bar adiacenti): 1
- `bybit_AVAX-USDT_4h.json`: **S5_picco_isolato** picchi isolati (> 3x i bar adiacenti): 1
- `bybit_GAS-USDT_1d.json`: **S2_prezzo_min** prezzo minimo 1.28e-06 < 1e-05 (barra 2022-11-13 00:00)
- `bybit_GAS-USDT_1h.json`: **S2_prezzo_min** prezzo minimo 1.28e-06 < 1e-05 (barra 2022-11-13 21:00)
- `bybit_GAS-USDT_4h.json`: **S2_prezzo_min** prezzo minimo 1.28e-06 < 1e-05 (barra 2022-11-13 20:00)
- `bybit_SHIB-USDT_1d.json`: **S2_prezzo_min** prezzo minimo 4.054e-06 < 1e-05 (barra 2026-06-25 00:00)
- `bybit_SHIB-USDT_1h.json`: **S2_prezzo_min** prezzo minimo 4.054e-06 < 1e-05 (barra 2026-06-25 13:00)
- `bybit_SHIB-USDT_4h.json`: **S2_prezzo_min** prezzo minimo 4.054e-06 < 1e-05 (barra 2026-06-25 12:00)

## 5. LISTA PROPOSTA — simboli da escludere dai backtest

Criterio: sono esclusi **solo i file `rotto` con firma dura** (regole H1/H2/H3/H4).

**A. Esclusione totale (rotto su tutti i timeframe disponibili):**

- **CTC-USDT**

**B. Esclusione per timeframe (serie parzialmente compromesse):**

| simbolo | escludere i tf | serie disponibili |
|---|---|---|
| **ICX-USDT** | 1h | 1d, 1h, 4h |

Da sapere: sugli altri timeframe dello stesso simbolo restano anomalie informative
(non firme dure), da valutare prima di usare quei file:

- **ICX-USDT** → 1d: I_range, I_serie_troncata; 1h: I_range, I_serie_troncata; 4h: I_range, I_serie_troncata


File da NON usare nei backtest:

```
data/cache/bybit_CTC-USDT_1d.json
data/cache/bybit_CTC-USDT_1h.json
data/cache/bybit_CTC-USDT_4h.json
data/cache/bybit_ICX-USDT_1h.json
```

## 6. Sospetti da valutare a parte (non in lista di esclusione)

| simbolo | timeframe | regole |
|---|---|---|
| AVAX-USDT | 1d, 1h, 4h | S5_picco_isolato |
| GAS-USDT | 1d, 1h, 4h | S2_prezzo_min |
| SHIB-USDT | 1d, 1h, 4h | S2_prezzo_min |

## 7. Anomalie informative (non cambiano la classificazione)

| regola | file |
|---|---|
| `I_buco` | 163 |
| `I_range` | 45 |
| `I_serie_troncata` | 12 |
| `I_volume_zero` | 9 |

Buchi sistemici (stessa barra mancante in piu' file — probabile buco del provider, non del file):

| barra mancante (inizio, UTC) | timeframe | file coinvolti |
|---|---|---|
| 2026-08-31 08:00 | 1h | 55 |
| 2026-04-28 08:00 | 4h | 55 |
| 2024-01-16 00:00 | 1d | 53 |

Barre con range intra-barra anomalo (wick estremi; es. flash-crash 2025-10-10):

| file | barra (UTC) | high | low | close | high/low |
|---|---|---|---|---|---|
| `bybit_AVAX-USDT_1d.json` | 2021-11-18 00:00 | 1000.2774 | 92.3607 | 101.1818 | 10.83x |
| `bybit_AVAX-USDT_4h.json` | 2021-11-18 12:00 | 1000.2774 | 97.0571 | 97.3803 | 10.31x |
| `bybit_AVAX-USDT_1h.json` | 2021-11-18 13:00 | 1000.2774 | 101.0 | 102.0001 | 9.9x |
| `bybit_ICX-USDT_1d.json` | 2026-09-21 00:00 | 0.07 | 0.00951 | 0.02528 | 7.36x |
| `bybit_ICX-USDT_4h.json` | 2026-09-21 16:00 | 0.07 | 0.01004 | 0.02246 | 6.97x |
| `bybit_GAS-USDT_1d.json` | 2022-04-03 00:00 | 6.847e-05 | 1e-05 | 3.773e-05 | 6.85x |
| `bybit_SUSHI-USDT_1d.json` | 2025-10-10 00:00 | 0.7195 | 0.1519 | 0.4796 | 4.74x |
| `bybit_MINA-USDT_1d.json` | 2025-10-10 00:00 | 0.1709 | 0.0379 | 0.1058 | 4.51x |
| `bybit_DOT-USDT_1d.json` | 2025-10-10 00:00 | 4.289 | 0.966 | 2.918 | 4.44x |
| `bybit_SUSHI-USDT_4h.json` | 2025-10-10 20:00 | 0.652 | 0.1519 | 0.4796 | 4.29x |
| `bybit_FIL-USDT_1d.json` | 2025-10-10 00:00 | 2.45 | 0.586 | 1.657 | 4.18x |
| `bybit_GAS-USDT_1d.json` | 2022-04-02 00:00 | 1.65e-05 | 3.97e-06 | 1.36e-05 | 4.16x |

## 8. Calibrazione delle soglie

Ritorni close-to-close massimi **sotto** la soglia del 300% (margine della soglia H1):

| file | max |ritorno| | quando (UTC) |
|---|---|---|
| `bybit_GAS-USDT_1d.json` | 235.80% | 2022-04-02 00:00 |
| `bybit_CFG-USDT_1h.json` | 167.99% | 2026-02-26 03:00 |
| `bybit_CFG-USDT_4h.json` | 163.50% | 2026-02-26 00:00 |
| `bybit_MANA-USDT_1d.json` | 157.26% | 2021-10-30 00:00 |
| `bybit_ICX-USDT_1d.json` | 156.91% | 2026-09-21 00:00 |

Range intra-barra massimi **sotto** la soglia 100x (margine della soglia H4):

| file | high/low | quando (UTC) |
|---|---|---|
| `bybit_AVAX-USDT_1d.json` | 10.83x | 2021-11-18 00:00 |
| `bybit_AVAX-USDT_4h.json` | 10.306x | 2021-11-18 12:00 |
| `bybit_AVAX-USDT_1h.json` | 9.904x | 2021-11-18 13:00 |
| `bybit_ICX-USDT_1d.json` | 7.361x | 2026-09-21 00:00 |
| `bybit_ICX-USDT_4h.json` | 6.972x | 2026-09-21 16:00 |

## 9. Copertura della cache

- File con copertura < 100% (barre mancanti dentro l'intervallo coperto): **163**
- Buco massimo osservato: **2.0x** il timeframe
- Finestra piu' ampia coperta: 2021-07-05 00:00 → 2026-10-12 00:00

**Serie troncate** (finiscono prima della fine comune dello stesso timeframe): 12 file — 4 simboli.

| simbolo | timeframe | ultimo bar (UTC) | fine comune (UTC) | ritardo |
|---|---|---|---|---|
| BNT-USDT | 1d | 2025-03-11 00:00 | 2026-10-12 00:00 | 580x tf |
| BNT-USDT | 1h | 2025-03-11 08:00 | 2026-10-12 00:00 | 13912x tf |
| BNT-USDT | 4h | 2025-03-11 08:00 | 2026-10-12 00:00 | 3478x tf |
| DGB-USDT | 1d | 2026-05-12 00:00 | 2026-10-12 00:00 | 153x tf |
| DGB-USDT | 1h | 2026-05-12 07:00 | 2026-10-12 00:00 | 3665x tf |
| DGB-USDT | 4h | 2026-05-12 04:00 | 2026-10-12 00:00 | 917x tf |
| GAS-USDT | 1d | 2023-03-10 00:00 | 2026-10-12 00:00 | 1312x tf |
| GAS-USDT | 1h | 2023-03-10 06:00 | 2026-10-12 00:00 | 31482x tf |
| GAS-USDT | 4h | 2023-03-10 04:00 | 2026-10-12 00:00 | 7871x tf |
| ICX-USDT | 1d | 2026-09-24 00:00 | 2026-10-12 00:00 | 18x tf |
| ICX-USDT | 1h | 2026-09-24 08:00 | 2026-10-12 00:00 | 424x tf |
| ICX-USDT | 4h | 2026-09-24 08:00 | 2026-10-12 00:00 | 106x tf |

Non e' una firma dura: sono serie che si fermano prima (delisting o buco di raccolta). Per i backtest
conta perche' un test che assume la finestra piena trattera' questi simboli come "senza dati" dopo la
fine della serie, con un campione piu' corto del previsto.

## 10. Casi noti — verifica

### 10.1 CTC-USDT — token swap del 2022-09-21 (caso noto, confermato)

- `bybit_CTC-USDT_1d.json` — regola `H4_crollo_intrabarra`, evento 2022-09-21 00:00 (UTC):

  | barra (UTC) | open | high | low | close | volume |
  |---|---|---|---|---|---|
  | 2022-09-19 00:00 | 0.299684 | 0.310959 | 0.276549 | 0.310876 | 18075.73 |
  | 2022-09-20 00:00 | 0.310876 | 0.310876 | 0.298509 | 0.30096 | 10746.93 |
  | 2022-09-21 00:00 **← evento** | 0.30096 | 0.311135 | 8e-05 | 0.292734 | 100280.08 |
  | 2022-09-22 00:00 | 0.292734 | 0.309942 | 0.284945 | 0.308626 | 45134.14 |
  | 2022-09-23 00:00 | 0.308626 | 0.312489 | 0.294631 | 0.2995 | 108352.6 |

- `bybit_CTC-USDT_1h.json` — regola `H1_ritorno_close`, evento 2022-09-21 12:00 (UTC):

  | barra (UTC) | open | high | low | close | volume |
  |---|---|---|---|---|---|
  | 2022-09-21 10:00 | 0.303649 | 0.303649 | 0.303649 | 0.303649 | 0.0 |
  | 2022-09-21 11:00 | 0.303649 | 0.303649 | 8e-05 | 8e-05 | 12415.58 |
  | 2022-09-21 12:00 **← evento** | 8e-05 | 0.308909 | 8e-05 | 0.306735 | 21328.88 |
  | 2022-09-21 13:00 | 0.306735 | 0.311135 | 0.306735 | 0.30869 | 4172.51 |
  | 2022-09-21 14:00 | 0.30869 | 0.308698 | 0.30864 | 0.308698 | 19.06 |

- `bybit_CTC-USDT_4h.json` — regola `H1_ritorno_close`, evento 2022-09-21 12:00 (UTC):

  | barra (UTC) | open | high | low | close | volume |
  |---|---|---|---|---|---|
  | 2022-09-21 04:00 | 0.302328 | 0.303671 | 0.302328 | 0.303671 | 785.0 |
  | 2022-09-21 08:00 | 0.303671 | 0.30579 | 8e-05 | 8e-05 | 17121.9 |
  | 2022-09-21 12:00 **← evento** | 8e-05 | 0.311135 | 8e-05 | 0.30539 | 26104.39 |
  | 2022-09-21 16:00 | 0.30539 | 0.307113 | 0.303711 | 0.306266 | 152.36 |
  | 2022-09-21 20:00 | 0.306266 | 0.306266 | 0.286315 | 0.292734 | 56097.82 |

Lettura: nello stesso giorno il prezzo passa da ~0.304 a 8e-05 e poi torna a ~0.305 (`4h`/`1h`).
E' l'artefatto del token swap, non un movimento di mercato: nella serie `1d` lo stesso evento
compare **solo come low** della candela del 2022-09-21 (O 0.30096 / H 0.311135 / L 8e-05 /
C 0.292734), quindi il solo ritorno close-to-close non lo vede.

### 10.2 GAS-USDT — scala sospetta (caso noto, confermato come `sospetto`)

| file | n barre | min prezzo | max prezzo | max/min | barra del minimo (UTC) | fine serie (UTC) |
|---|---|---|---|---|---|---|
| `bybit_GAS-USDT_1d.json` | 437 | 1.28e-06 | 0.0002117 | 165.3906 | 2022-11-13 00:00 | 2023-03-10 00:00 |
| `bybit_GAS-USDT_1h.json` | 10458 | 1.28e-06 | 0.0002117 | 165.3906 | 2022-11-13 21:00 | 2023-03-10 06:00 |
| `bybit_GAS-USDT_4h.json` | 2615 | 1.28e-06 | 0.0002117 | 165.3906 | 2022-11-13 20:00 | 2023-03-10 04:00 |

Lettura: tutta la storia sta a 1,28e-06 … 2,117e-04, cioe' 4-5 ordini di grandezza sotto la scala
degli altri simboli; il minimo (1,28e-06) viola la soglia 1e-5 → `S2_prezzo_min`. La serie si ferma
il 2023-03-10 su tutti i timeframe.

Verifica esterna (pagine pubbliche, non chiavi API): la storia pubblica di GAS/USD (ADVFN su dati
CEX.IO) segna 2,49 USD il 2022-12-02, con la fascia di quel periodo attorno a 2,2-2,5 USD, e la
pagina pubblica CoinGecko riporta per GAS un massimo storico di 91,94 USD e un minimo di 0,6213 USD.
Nella cache la stessa data vale 1,60e-06, cioe' un fattore implicito di circa **1,5e6** sui livelli,
e il turnover implicito (volume 7,3e8 x 1,6e-06) e' dell'ordine di 1e3 USD/giorno: incompatibile con
un mid-cap. Conclusione: la serie GAS della cache **non e' la serie GAS reale riscalata di una
costante**, quindi i LIVELLI non sono usabili e i rendimenti restano non verificati. Va chiarita la
fonte (o il simbolo) prima di qualunque backtest che la includa.

### 10.3 ICX-USDT — +478% in 1h il 2026-09-21 (serie troncata subito dopo)

- `bybit_ICX-USDT_1h.json` — regola `H1_ritorno_close`, evento 2026-09-21 16:00 (UTC):

  | barra (UTC) | open | high | low | close | volume |
  |---|---|---|---|---|---|
  | 2026-09-21 14:00 | 0.01001 | 0.01001 | 0.00997 | 0.00997 | 1627.78 |
  | 2026-09-21 15:00 | 0.00997 | 0.01004 | 0.00996 | 0.01004 | 15593.03 |
  | 2026-09-21 16:00 **← evento** | 0.01004 | 0.07 | 0.01004 | 0.05804 | 1291753.14 |
  | 2026-09-21 17:00 | 0.05804 | 0.05804 | 0.02989 | 0.03299 | 790967.89 |
  | 2026-09-21 18:00 | 0.03299 | 0.03518 | 0.02292 | 0.02292 | 285779.51 |

Lettura: il close passa 0.01004 → 0.05804 (+478%) e il massimo della barra e' 0.07; la serie `1h`
si ferma il 2026-09-24 08:00, ~18 giorni prima della fine comune (`I_serie_troncata` su tutti e tre
i timeframe). Non e' un errore di formato ma e' un evento da trattare con cautela: `1d` e `4h` non
hanno firma dura (il massimo giornaliero e' un range 7,4x, sotto la soglia) ma contengono la stessa
pompa. Valutare se escludere anche `1d`/`4h` se il backtest usa il periodo finale.

### 10.4 SHIB-USDT — regola `S2` scattata, probabile artefatto della definizione

| file | n barre | min prezzo | max prezzo | max/min | barra del minimo (UTC) |
|---|---|---|---|---|---|
| `bybit_SHIB-USDT_1d.json` | 1771 | 4.054e-06 | 4.56453e-05 | 11.2593 | 2026-06-25 00:00 |
| `bybit_SHIB-USDT_1h.json` | 42497 | 4.054e-06 | 4.56453e-05 | 11.2593 | 2026-06-25 13:00 |
| `bybit_SHIB-USDT_4h.json` | 10625 | 4.054e-06 | 4.56453e-05 | 11.2593 | 2026-06-25 12:00 |

Lettura: SHIB quota per costruzione nella fascia 1e-5 (minimo 4,05e-06, massimo 4,56e-05), quindi la
soglia "prezzo minimo < 1e-5" scatta su un dato plausibile e non su un errore: **falso positivo
della regola**, da NON escludere dai backtest. Un test che usa soglie assolute di prezzo (es. filtri
"prezzo > 0.01") va comunque adattato alla scala.

### 10.5 AVAX-USDT — tick spurio del 2021-11-18 (nessuna firma dura)

- `bybit_AVAX-USDT_1d.json` — regola `S5_picco_isolato`, evento 2021-11-18 00:00 (UTC):

  | barra (UTC) | open | high | low | close | volume |
  |---|---|---|---|---|---|
  | 2021-11-16 00:00 | 93.9548 | 102.6341 | 83.0001 | 98.4782 | 4020.082 |
  | 2021-11-17 00:00 | 98.4782 | 110.4628 | 91.3501 | 108.1662 | 5251.786 |
  | 2021-11-18 00:00 **← evento** | 108.1662 | 1000.2774 | 92.3607 | 101.1818 | 15701.316 |
  | 2021-11-19 00:00 | 101.1818 | 115.9436 | 96.6403 | 112.9771 | 8836.855 |
  | 2021-11-20 00:00 | 112.9771 | 132.3182 | 112.6061 | 127.1282 | 9417.93 |

Lettura: `high = 1000.2774` mentre i bar adiacenti stanno a 110-116 (e il close e' 101.18): e' un
tick spurio isolato, ripetuto identico su tutti e tre i timeframe. Non produce firme dure (il close
non salta) → il file resta `sospetto` per `S5`, non `rotto`. Un backtest che usa i massimi
(breakout, canali) va protetto; per il resto il file e' utilizzabile.

## 11. Limiti

- La classificazione e' di **forma**, non di merito: un file `ok` significa "nessuna firma dura o
  anomalia nota", non "prezzi verificati contro una seconda fonte".
- I ritorni sono close-to-close: un crollo intra-barra resta invisibile tranne che per `H4`.
- Le soglie sono quelle concordate; il margine e' ampio (sezione 8), quindi il conteggio e' stabile.

<!-- LOG-LAVORAZIONE:START -->
## Log di lavorazione

- 2026-10-15 00:25:49 CEST — avviato audit: 177 file bybit_*.json attesi (59 simboli x 3 tf: 1d/4h/1h); esplorazione struttura OK (chiavi uniformi, 0 file illeggibili).
- 2026-10-15 00:31:58 CEST — esplorazione completata: 177/177 file con struttura conforme (chiavi venue/hostname/simbolo/timeframe/categoria/barre, 6 campi per barra, ts in ms crescenti). Candidati già individuati: CTC (swap 2022-09-21 su 1d/4h/1h), ICX (+478% in 1h il 2026-09-21), AVAX (tick 1000.2774 il 2021-11-18), GAS e SHIB (prezzo minimo < 1e-5).
- 2026-10-15 00:31:58 CEST — scritto scripts/igiene_cache.py (sola lettura, stdlib). In corso: run completa + generazione di data/cache_igiene.json e del report.
- 2026-10-15 00:35:00 CEST — prima run completa OK: ok=164 sospetti=9 rotti=4. Aggiunte al report: sezione 10 'casi noti' con la finestra contesto delle barre, serie troncate (GAS/BNT/DGB/ICX), buchi sistemici del provider. Rilancio per la versione finale.
- 2026-10-15 00:38:50 CEST — verifica indipendente (seconda implementazione scritta da zero, non importa il modulo): conteggi identici 164/9/4, tutte le metriche per file coincidono, sha256 combacianti; unica differenza attesa: S5 non viene duplicato su CTC 1d perche' la stessa barra e' gia' coperta da H4. Verifica esterna GAS: pagina pubblica ADVFN/CEX.IO segna 2,49 USD il 2022-12-02 contro 1,60e-06 nella cache (fattore ~1,5e6): serie non riconciliabile, resta sospetto.
- 2026-10-15 00:41:48 CEST — CHIUSO. Artefatti: `scripts/igiene_cache.py` (sha256 a7296595804a9f1a…), `data/cache_igiene.json` (sha256 9c1514d0e2728f62…, 340289 byte), questo report. Cache di input mai modificata: 177 sha256 verificati identici prima/dopo tutte le run. Nessun commit git eseguito.
