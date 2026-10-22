# Riconciliazione Carry DOT / ADA (REQ-20261022-003 — T3)

- **Data/ora riconciliazione:** `2026-10-21T23:45:44Z`
- **Finestra analizzata:** da `2026-10-15T23:00:00Z` (apertura carry DOT `23:00:02Z`, ADA `23:00:12Z`) a `2026-10-21T23:45:02Z` (`carry_stato.json`)
- **Epoche di funding maturate nella finestra:** **18** per coppia (36 totali), da `2026-10-16T00:00:00Z` (`1792108800000`) a `2026-10-21T16:00:00Z` (`1792598400000`), cadenza 8h (`00:00`, `08:00`, `16:00` UTC).

---

## 1. Tabella di Riconciliazione Principale (DOT, ADA, TOTALE)

Tutti gli importi monetari di PnL/fee/funding sono espressi in **USDC / USD** (valuta di regolamento degli X-Perp EEA e delle coppie spot `DOT-USDC` / `ADA-USDC`; vedi §4 per l'assunzione sul campo `nozionale_eur` di `carry_stato.json`).
Poiché il Passo 1 della REQ indica gli endpoint `DOT-USDT-SWAP` / `ADA-USDT-SWAP` mentre le posizioni reali nel ledger `fee_ledger.jsonl` sono sugli X-Perp EEA `DOT-USD_UM_XPERP-310808` / `ADA-USD_UM_XPERP-310404`, la tabella riporta **entrambe** le serie di funding e di netto:
- **Serie A (`USDT-SWAP`):** tassi e mark price da `DOT-USDT-SWAP` e `ADA-USDT-SWAP` (endpoint letterali Passo 1), applicati alla quantità sottostante reale della gamba short (`78 DOT`, `390 ADA`).
- **Serie B (`X-Perp EEA`, reale):** tassi e mark price da `DOT-USD_UM_XPERP-310808` e `ADA-USD_UM_XPERP-310404` (strumenti effettivamente in portafoglio su OKX EEA).

Per ciascuna serie è indicato sia il funding calcolato col **nozionale mark puntuale** a ciascun timestamp di funding (`noz_mark(t) = qty_perp * mark_open_1H(t)`), sia col **nozionale fisso** da `carry_stato.json` (`89.895` per gamba).

| Voce | DOT | ADA | TOTALE |
|---|---:|---:|---:|
| **Apertura (`ts_apri`)** | `2026-10-15T23:00:02Z` | `2026-10-15T23:00:12Z` | `2026-10-15T23:00Z` |
| **Epoche funding (8h)** | 18 | 18 | 36 |
| **Qty spot lorda acquistata** | 78.0000 DOT | 390.0000 ADA | — |
| **Fee spot ingresso (in base ccy)** | -0.078000 DOT | -0.390000 ADA | — |
| **Qty spot netta (`carry_stato.json`)** | 77.9220 DOT | 389.6100 ADA | — |
| **Contratti perp short (`ct_perp`)** | 78.0 ct (`ctVal=1`) | 39.0 ct (`ctVal=10`) | 117.0 ct |
| **Sottostante perp short (`qty_perp`)** | 78.0000 DOT | 390.0000 ADA | — |
| **Delta residuo gambe (`ct*ctVal - qty_spot`)** | 0.0780 DOT | 0.3900 ADA | — |
| **Prezzo medio ingresso spot (`VWAP_spot_in`)** | 1.153981 USDC | 0.230400 USDC | — |
| **Prezzo medio ingresso perp (`VWAP_perp_in`)** | 1.152315 USDC | 0.230049 USDC | — |
| **Prezzo spot corrente (`prezzo_ora`)** | 1.146100 USDC | 0.225200 USDC | — |
| **Nozionale stato (`carry_stato.json`)** | 89.8950 | 89.8950 | 179.7900 |
| **Nozionale medio mark (`USDT-SWAP`, 18 epoche)** | 89.0270 USD | 86.6667 USD | 175.6937 USD |
| **Nozionale medio mark (`X-Perp EEA`, 18 epoche)** | 88.9430 USDC | 86.5670 USDC | 175.5100 USDC |
| **Somma `fundingRate` 18 epoche (`USDT-SWAP`)** | +0.076404% (`+0.00076404`) | +0.003162% (`+0.00003162`) | — |
| **Somma `fundingRate` 18 epoche (`X-Perp EEA`)** | +0.180000% (`+0.00180000`) | +0.180000% (`+0.00180000`) | — |
| **Funding incassato — Serie A `USDT-SWAP` (noz. mark)** | **+0.069576 USDC** | **+0.004107 USDC** | **+0.073683 USDC** |
| **Funding incassato — Serie A `USDT-SWAP` (noz. fisso 89.895)** | +0.068683 USDC | +0.002843 USDC | +0.071526 USDC |
| **Funding incassato — Serie B `X-Perp EEA` (noz. mark)** | **+0.160097 USDC** | **+0.155821 USDC** | **+0.315918 USDC** |
| **Funding incassato — Serie B `X-Perp EEA` (noz. fisso 89.895)** | +0.161811 USDC | +0.161811 USDC | +0.323622 USDC |
| **Fee spot ingresso (in USDC a `fillPx`)** | -0.090010 USDC | -0.089856 USDC | -0.179866 USDC |
| *(Fee spot ingresso valorizzata a `prezzo_ora`)* | *(-0.089396 USDC)* | *(-0.087828 USDC)* | *(-0.177224 USDC)* |
| **Fee perp ingresso (in USDC, da ledger)** | -0.044940 USDC | -0.044860 USDC | -0.089800 USDC |
| **Fee uscite (posizioni aperte → 0 fill uscita)** | 0.000000 USDC | 0.000000 USDC | 0.000000 USDC |
| **Fee totali pagate (ingresso + uscite, a `fillPx`)** | **-0.134951 USDC** | **-0.134716 USDC** | **-0.269666 USDC** |
| **uPL perp corrente (`carry_stato.json`)** | **+0.555000 USDC** | **+1.930000 USDC** | **+2.485000 USDC** |
| **Delta spot MTM (`qty_spot * (prezzo_ora - VWAP_spot_in)`)** | **-0.614067 USDC** | **-2.025972 USDC** | **-2.640039 USDC** |
| *(Delta spot cash-to-mark `qty_spot*prezzo_ora - costo_spot_in`, già incl. fee spot)* | *(-0.704077 USDC)* | *(-2.115828 USDC)* | *(-2.819905 USDC)* |
| **Sbilancio MTM gambe (`uPL_perp + Delta_spot_MTM`)** | -0.059067 USDC | -0.095972 USDC | -0.155039 USDC |
| **Netto stimato — Serie A `USDT-SWAP` (noz. mark)** | **-0.124442 USDC** | **-0.226580 USDC** | **-0.351022 USDC** |
| **Netto stimato — Serie A `USDT-SWAP` (noz. fisso)** | -0.125334 USDC | -0.227845 USDC | -0.353179 USDC |
| **Netto stimato — Serie B `X-Perp EEA` (noz. mark)** | **-0.033920 USDC** | **-0.074867 USDC** | **-0.108787 USDC** |
| **Netto stimato — Serie B `X-Perp EEA` (noz. fisso)** | -0.032206 USDC | -0.068876 USDC | -0.101083 USDC |

Formula del netto stimato (senza doppio conteggio della fee spot):
`Netto = Funding + uPL_perp + Delta_spot_MTM - (Fee_spot_USDC_entry + Fee_perp_USDC)`
che è algebricamente identica a:
`Netto = Funding + uPL_perp + (qty_spot_net * prezzo_ora - esborso_USDC_spot_in) - Fee_perp_USDC`.

---

## 2. Specifiche Strumenti e Verifica Endpoint Candele Mark (Passo 1)

### 2.1 Parametri strumento (`/api/v5/public/instruments`)
| `instId` | `instType` | `ctVal` | `ctValCcy` | `lotSz` | `minSz` | `settleCcy` | Note |
|---|---|---:|---|---:|---:|---|---|
| `DOT-USDT-SWAP` | `SWAP` | `1` | `DOT` | `1` | `1` | `USDT` | Endpoint richiesto Passo 1 (1 ct = 1 DOT) |
| `ADA-USDT-SWAP` | `SWAP` | `100` | `ADA` | `0.1` | `0.1` | `USDT` | Endpoint richiesto Passo 1 (1 ct = 100 ADA; 390 ADA = 3.9 ct) |
| `DOT-USD_UM_XPERP-310808` | `FUTURES` | `1` | `DOT` | `1` | `1` | `USD` | Strumento reale in `fee_ledger.jsonl` (78 ct = 78 DOT) |
| `ADA-USD_UM_XPERP-310404` | `FUTURES` | `10` | `ADA` | `1` | `1` | `USD` | Strumento reale in `fee_ledger.jsonl` (39 ct = 390 ADA) |

### 2.2 Endpoint candele mark
- **Endpoint verificato ed esistente:** `GET https://www.okx.com/api/v5/market/mark-price-candles?instId=<instId>&bar=1H&limit=200`
- **Risposta:** `code="0"`, 200 candele orarie `[ts, o, h, l, c, confirm]` da `2026-10-13T16:00:00Z` (`1791907200000`) a `2026-10-21T23:00:00Z` (`1792623600000`), coprendo **18/18** timestamp di funding (`missing_mark = 0`).
- **Prezzo usato al timestamp di funding `t`:** prezzo `open` (`candle[1]`) della candela 1H con `ts == fundingTime`.

---

## 3. Dettaglio Fill da `~/money/logs/fee_ledger.jsonl` (Passo 2)

Nel ledger locale (`23` righe totali) sono presenti **12 fill** con `instId` che inizia per `DOT` o `ADA` (tutti di ingresso del `2026-10-15T22:59:59Z` – `23:00:10Z`; **0 fill di uscita**):

| `ts` (ms) | Data/Ora UTC | `instId` | `side` | `fillSz` | `fillPx` | `fee` | `feeCcy` | `billId` |
|---|---|---|---:|---:|---:|---:|---|---|
| `1792105199351` | `2026-10-15T22:59:59.351Z` | `DOT-USDC` | `buy` | `62.8125` | `1.1540` | `-0.0628125` | `DOT` | `4013203997863874565` |
| `1792105199351` | `2026-10-15T22:59:59.351Z` | `DOT-USDC` | `buy` | `15.1875` | `1.1539` | `-0.0151875` | `DOT` | `4013203997863874562` |
| `1792105199641` | `2026-10-15T22:59:59.641Z` | `DOT-USD_UM_XPERP-310808` | `sell` | `2` | `1.1521` | `-0.0011521` | `USDC` | `4013204007594659846` |
| `1792105199641` | `2026-10-15T22:59:59.641Z` | `DOT-USD_UM_XPERP-310808` | `sell` | `30` | `1.1522` | `-0.0172830` | `USDC` | `4013204007594659845` |
| `1792105199641` | `2026-10-15T22:59:59.641Z` | `DOT-USD_UM_XPERP-310808` | `sell` | `11` | `1.1523` | `-0.00633765` | `USDC` | `4013204007594659844` |
| `1792105199641` | `2026-10-15T22:59:59.641Z` | `DOT-USD_UM_XPERP-310808` | `sell` | `24` | `1.1524` | `-0.0138288` | `USDC` | `4013204007594659843` |
| `1792105199641` | `2026-10-15T22:59:59.641Z` | `DOT-USD_UM_XPERP-310808` | `sell` | `11` | `1.1525` | `-0.00633875` | `USDC` | `4013204007594659842` |
| `1792105209745` | `2026-10-15T23:00:09.745Z` | `ADA-USDC` | `buy` | `390` | `0.2304` | `-0.39` | `ADA` | `4013204346628640769` |
| `1792105210040` | `2026-10-15T23:00:10.040Z` | `ADA-USD_UM_XPERP-310404` | `sell` | `20` | `0.2300` | `-0.023` | `USDC` | `4013204356527198213` |
| `1792105210040` | `2026-10-15T23:00:10.040Z` | `ADA-USD_UM_XPERP-310404` | `sell` | `1` | `0.2301` | `-0.0011505` | `USDC` | `4013204356527198212` |
| `1792105210040` | `2026-10-15T23:00:10.040Z` | `ADA-USD_UM_XPERP-310404` | `sell` | `13` | `0.2301` | `-0.0149565` | `USDC` | `4013204356527198211` |
| `1792105210040` | `2026-10-15T23:00:10.040Z` | `ADA-USD_UM_XPERP-310404` | `sell` | `5` | `0.2301` | `-0.0057525` | `USDC` | `4013204356527198210` |

---

## 4. Assunzioni Dichiarate e Limiti

1. **Doppio riferimento strumento (`USDT-SWAP` vs `X-Perp EEA`):**
   - Il Passo 1 richiede i dati pubblici di `DOT-USDT-SWAP` e `ADA-USDT-SWAP`. Tuttavia su OKX EEA i contratti effettivamente aperti dal conto (come attestato da `fee_ledger.jsonl` e `scripts/carry_multi.py`) sono gli X-Perp `DOT-USD_UM_XPERP-310808` (`ctVal=1 DOT`) e `ADA-USD_UM_XPERP-310404` (`ctVal=10 ADA`).
   - Sugli X-Perp EEA il `fundingRate` di tutte le 18 epoche dal 16/10 al 21/10 è stato pari al floor positivo standard di `+0.0001` (`+0.01%` per 8h = `+0.18%` cumulato in 6 giorni), mentre sui global `USDT-SWAP` il funding cumulato nelle stesse 18 epoche è stato `+0.076404%` su DOT e `+0.003162%` su ADA. Entrambe le serie sono riportate integralmente.
2. **Sottostante `ADA` e differenza `ctVal` (`10` vs `100`):**
   - Su `ADA-USD_UM_XPERP-310404` `ctVal = 10 ADA`, quindi `39 contratti = 390 ADA` (allineato ai `390 ADA` comprati sullo spot). Su `ADA-USDT-SWAP` `ctVal = 100 ADA` (`lotSz = 0.1`): per coerenza economica con la gamba spot reale, anche nella Serie A il nozionale mark è calcolato su **390 ADA** (`3.9 ct` equivalenti `ADA-USDT-SWAP`), non su `39 * 100 = 3900 ADA`.
3. **Unità di misura di `nozionale_eur` e `upl` in `carry_stato.json`:**
   - In `data/carry_multi/stato.json` e `data/carry_stato.json` il campo `nozionale_eur = 89.895` è stato registrato all'apertura moltiplicando la quantità perp per l'ultimo fillPx in USD/USDC (`78 * 1.1525 = 89.895` per DOT; `390 * 0.2305 = 89.895` per ADA), e `upl` proviene da `unrealizedPnl` OKX dell'X-Perp regolato in USDC/USD. Pertanto tutte le grandezze della tabella sono omogenee in **USDC/USD**. (Per eventuale conversione in EUR, i fill `USDC-EUR` nel ledger registrano `0.89329 EUR/USDC`).
4. **Fee di uscita e sbilancio delta residuo:**
   - Le posizioni sono aperte: le fee di uscita realizzate sono `0.000000 USDC` (una futura chiusura taker a parità di schedule `0.10%` spot + `0.05%` perp costerebbe ulteriori `~0.132 USDC` per gamba, ovvero `~0.264 USDC` totali).
   - Poiché la fee spot di acquisto (`0.10%`) è stata trattenuta da OKX in valuta base (`0.078 DOT` e `0.39 ADA`), la gamba spot detiene lo `0.10%` in meno di sottostante rispetto alla gamba short perp (`77.922 DOT` vs `78.0 DOT`; `389.61 ADA` vs `390.0 ADA`). Inoltre all'apertura lo spot è stato eseguito a un prezzo leggermente superiore al perp (`VWAP_spot_in - VWAP_perp_in = +0.001665 USDC` su DOT e `+0.000351 USDC` su ADA), generando uno spread d'ingresso iniziale di `-0.1299 USDC` (DOT) e `-0.1370 USDC` (ADA), che spiega perché `uPL_perp + Delta_spot_MTM` sia pari a `-0.0591 USDC` (DOT) e `-0.0960 USDC` (ADA).
5. **Dati mancanti:**
   - Non avendo interrogato endpoint privati (vincolo: solo dati pubblici + ledger locale), il funding effettivamente accreditato sul conto non è letto da `/api/v5/account/bills` ma ricostruito esattamente dalla serie pubblica `funding-rate-history` × nozionale mark; le fee dal `2026-10-19T10:50:02+02:00` a oggi non hanno avuto nuovi run di `raccogli_fee_ledger.py`, ma non vi sono stati ordini/chiusure sulle due coppie (contratti invariati `78` e `39` in `carry_stato.json`).

---

## 5. Artefatti Salvati e Impronte `sha256sum` (Passo 4)

Tutti i file JSON grezzi scaricati (fetch UTC `2026-10-21T23:45:41Z` – `23:45:44Z`) e gli artefatti generati si trovano in `/home/marco/hermes-scratch/carry_recon/`:

| File | Timestamp Fetch UTC | Byte | `sha256sum` |
|---|---|---:|---|
| `raw/funding_DOT-USDT-SWAP.json` | `2026-10-21T23:45:41+00:00` | 18452 | `b6de848e8a04e972ed92b7086ae82577ce94f769c9256894713359cbd5a0cce0` |
| `raw/funding_ADA-USDT-SWAP.json` | `2026-10-21T23:45:41+00:00` | 18482 | `fa8bee5825dff3f7213f517fe38e41179db2b439281d1dee9fc6edcb3cedbfef` |
| `raw/instruments_DOT-USDT-SWAP.json` | `2026-10-21T23:45:42+00:00` | 739 | `0c6bb65653766b8ba91dd422bc2706e980380c676b635e8645609eb5c75f8c41` |
| `raw/instruments_ADA-USDT-SWAP.json` | `2026-10-21T23:45:42+00:00` | 742 | `a1326f34e01eae371a87faea5ec5d7b65caab3038777d7e787c0e358c84272c8` |
| `raw/mark_candles_1H_DOT-USDT-SWAP.json` | `2026-10-21T23:45:42+00:00` | 10767 | `5dd4a5b71e40e325391def7228df658f074576e7df51655d383366ea2b74980a` |
| `raw/mark_candles_1H_ADA-USDT-SWAP.json` | `2026-10-21T23:45:43+00:00` | 10742 | `946e8151be17831a7428ba3842d24b83a1efd14b732cea01af979b7f1548a003` |
| `raw/funding_DOT-USD_UM_XPERP-310808.json` | `2026-10-21T23:45:43+00:00` | 18412 | `6782b089bb46e86bb30fdf883b2f707cec64748515aded816daf7693b76212ad` |
| `raw/funding_ADA-USD_UM_XPERP-310404.json` | `2026-10-21T23:45:43+00:00` | 18412 | `eba5580a035b714c0836b83b49a411f5e46ac9aa432ed9f531fafefc0e203d33` |
| `raw/instruments_FUTURES_DOT-USD_UM_XPERP-310808.json` | `2026-10-21T23:45:43+00:00` | 762 | `638a77815c20d7a59e61e6ac33b99045cfd01c5d63142fa5cc5af29c148713f1` |
| `raw/instruments_FUTURES_ADA-USD_UM_XPERP-310404.json` | `2026-10-21T23:45:44+00:00` | 765 | `2b821abd495174b3920e7cd55b2b06f47a7379b77f2a8eb907a3d2b521e080d3` |
| `raw/mark_candles_1H_DOT-USD_UM_XPERP-310808.json` | `2026-10-21T23:45:44+00:00` | 10742 | `557c0968ec81007cc76daff86148222e31ae3afe3c693a0e49444b4a8f1fa3ad` |
| `raw/mark_candles_1H_ADA-USD_UM_XPERP-310404.json` | `2026-10-21T23:45:44+00:00` | 10756 | `b52ab2facff78d6f5445eef5ccf5ae656a047790bfba234f5c991382ce2413d4` |
| `raw/carry_stato_snapshot.json` | `2026-10-21T23:45:02+00:00` | 853 | `956c7422a2fa3562a06e42df9b13e7935fab1b121838effbca7abcb2a15ace06` |
| `raw/manifest.json` | `2026-10-21T23:45:44+00:00` | 4852 | `1167301a657bb5d66dde4d2ba7e4229105092cd00123d77c5765828a9f07bef1` |
