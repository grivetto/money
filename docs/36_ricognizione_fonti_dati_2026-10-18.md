# REPORT — Ricognizione fonti dati pubbliche ON-CHAIN e SENTIMENT

**Data esecuzione:** 2026-10-18 01:47 CEST  
**Asset di riferimento:** BTC  
**Metodo:** Ogni endpoint testato con curl reale — nessuna chiave API, nessun account

---

## Tabella riassuntiva

| Fonte | Endpoint testato | HTTP | Estratto risposta | Campi disponibili | Granularità | Storia | Chiave? | Verdetto |
|---|---|---|---|---|---|---|---|---|
| **Fear & Greed Index** | `https://api.alternative.me/fng/?limit=5` | 200 | `{"value":"55","value_classification":"Greed","timestamp":"1792195200"}` | value, value_classification, timestamp, time_until_update | Giornaliera | ~10+ anni (limit=365 testato) | No | **USABILE SUBITO** |
| **Blockchain.info / stats** | `https://api.blockchain.info/stats` | 200 | `{"market_price_usd":80947.37,"hash_rate":9.43E11,"n_tx":663450,"difficulty":1.4E14}` | market_price_usd, hash_rate, total_fees_btc, n_tx, n_blocks_mined, minutes_between_blocks, totalbc, difficulty, trade_volume_btc/usd | Istantanea (real-time) | Singolo snapshot — uso storico via charts API | No | **USABILE SUBITO** |
| **Blockchain.info / charts (tx count)** | `https://api.blockchain.info/charts/n-transactions?format=json&timespan=30days` | 200 | `{"name":"Confirmed Transactions Per Day","values":[{"x":1789603200,"y":652518}]}` | x (timestamp unix), y (valore), name, unit, period | Giornaliera | Fino a 5+ anni | No | **USABILE SUBITO** |
| **Blockchain.info / charts (hashrate)** | `https://api.blockchain.info/charts/hash-rate?format=json&timespan=30days` | 200 | `{"name":"Hash Rate","unit":"Hash Rate TH/s","values":[{"x":1789603200,"y":9.059E8}]}` | Stessa struttura di tx count | Giornaliera | Fino a 5+ anni | No | **USABILE SUBITO** |
| **Mempool.space (fees raccomandate)** | `https://mempool.space/api/v1/fees/recommended` | 200 | `{"fastestFee":1,"halfHourFee":1,"hourFee":1,"economyFee":1,"minimumFee":1}` | fastestFee, halfHourFee, hourFee, economyFee, minimumFee | Real-time | Snapshot corrente — storico via v1/mining/hashrate | No | **USABILE SUBITO** |
| **Mempool.space (mempool stats)** | `https://mempool.space/api/mempool` | 200 | `{"count":75890,"vsize":39386994,"total_fee":6064329}` | count, vsize, total_fee, fee_histogram [] | Real-time | Snapshot corrente | No | **USABILE SUBITO** |
| **Mempool.space (blocks)** | `https://mempool.space/api/v1/blocks/5` | 200 | Array di blocchi con id, height, timestamp, difficulty | id, height, version, timestamp, bits, nonce, difficulty, merkle_root | Per blocco (~10 min) | Ultimi N blocchi | No | **USABILE SUBITO** |
| **Mempool.space (mining pools)** | `https://mempool.space/api/v1/mining/pools/1w` | 200 | `{"pools":[{"name":"Foundry USA","blockCount":258,"rank":1}]}` | pools[], blockCount, rank, avgMatchRate, avgFeeDelta | Settimanale | 1 settimana | No | **USABILE SUBITO** |
| **Mempool.space (hashrate 24h)** | `https://mempool.space/api/v1/mining/hashrate/24h` | 200 | `{"hashrates":[{"timestamp":1792195200,"avgHashrate":1.009E21}],"currentHashrate":1.027E21}` | hashrates[], currentHashrate, currentDifficulty | 24h / Blocchi | 24 ore | No | **USABILE SUBITO** |
| **DefiLlama (chains TVL)** | `https://api.llama.fi/v2/chains` | 200 | `[{"name":"Mantle","tvl":96840225,"tokenSymbol":"MNT"}]` | name, tvl, tokenSymbol, gecko_id, chainId | Istantanea | Ultimo snapshot per chain | No | **USABILE SUBITO** |
| **DefiLlama (overview fees)** | `https://api.llama.fi/overview/fees?excludeTotalDataChart=true` | 200 | Dati fee storici per progetto | totalDataChart, totalDataChartBreakdown | Giornaliera | Dal 2018 | No | **USABILE SUBITO** |
| **DefiLlama (yields)** | `https://yields.llama.fi/pools` | 200 | Pool di yield farming | Tutti i campi pool | Real-time | Snapshot | No | **USABILE SUBITO** |
| **DefiLlama (protocols)** | `https://api.llama.fi/protocols` | 200 | Elenco protocolli | id, name, symbol, url, description, tvl | Istantanea | Snapshot | No | **USABILE SUBITO** |
| **OKX (funding rate main)** | `https://www.okx.com/api/v5/public/funding-rate?instId=BTC-USDT-SWAP` | 200 | `{"code":"0","data":[{"fundingRate":"0.0000559","fundingTime":"1792281600000"}]}` | fundingRate, fundingTime, formulaType, impactValue, instId | 8 ore (ogni funding period) | Solo rata corrente | No | **USABILE SUBITO** |
| **OKX EEA (funding rate)** | `https://eea.okx.com/api/v5/public/funding-rate?instId=BTC-USDT-SWAP` | 200 | Stessa struttura OKX main | Stessi campi | 8 ore | Solo rata corrente | No | **USABILE SUBITO** |
| **OKX (funding rate history)** | `https://www.okx.com/api/v5/public/funding-rate-history?instId=BTC-USDT-SWAP&limit=5` | 200 | `{"fundingRate":"0.0000947","fundingTime":"1792252800000","realizedRate":"0.0000947"}` | fundingRate, fundingTime, realizedRate, method | 8 ore | Storico illimitato (paginate) | No | **USABILE SUBITO** |
| **OKX (open interest)** | `https://www.okx.com/api/v5/public/open-interest?instId=BTC-USDT-SWAP` | 200 | `{"oi":"3055834.02","oiCcy":"30558.34","oiUsd":"2485132570.09"}` | oi, oiCcy, oiUsd, ts | Real-time | Snapshot corrente | No | **USABILE SUBITO** |
| **OKX EEA (open interest)** | `https://eea.okx.com/api/v5/public/open-interest?instId=BTC-USDT-SWAP` | 200 | Stessa struttura | Stessi campi | Real-time | Snapshot | No | **USABILE SUBITO** |
| **OKX (mark price)** | `https://www.okx.com/api/v5/public/mark-price?instId=BTC-USDT-SWAP` | 200 | `{"markPx":"81324.8","instId":"BTC-USDT-SWAP"}` | markPx, instType, ts | Real-time | Snapshot | No | **USABILE SUBITO** |
| **OKX (index candles)** | `https://www.okx.com/api/v5/market/index-candles?instId=BTC-USDT&bar=1D&limit=3` | 200 | Candle OHLC: `["1792252800000","81351.4","81699.2","80815.3","81369.1"]` | open, high, low, close, volume (timestamp + OHLCV) | Da 1m a 1M (param bar) | Fino a 1000 candele per chiamata | No | **USABILE SUBITO** |
| **CoinGecko (global)** | `https://api.coingecko.com/api/v3/global` | 200 | `{"active_cryptocurrencies":22320,"total_market_cap":{"btc":33784911}}` | active_cryptocurrencies, total_market_cap (multi valuta), markets | Istantanea | Snapshot corrente | No | **USABILE SUBITO** |
| **CoinGecko (simple price)** | `https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd` | 200 | `{"bitcoin":{"usd":81282}}` | prezzo, 24h_change, market_cap | Istantanea | Snapshot | No | **USABILE SUBITO** |
| **CoinGecko (market chart)** | `https://api.coingecko.com/api/v3/coins/bitcoin/market_chart?vs_currency=usd&days=30` | 200 | `{"prices":[[1789689600000,76371.36],[1789693200000,76526.04]]}` | prices[], market_caps[], total_volumes[] | Giornaliera/Oraria (dipende da days) | Fino a max 1 anno | No | **USABILE SUBITO** |
| **CoinGecko (coin detail)** | `https://api.coingecko.com/api/v3/coins/bitcoin?localization=false` | 200 | Prezzo:81287, market_cap:1.63T, vol:14.29B, ATH:126080 | Dati di mercato completi | Istantanea | Snapshot | No | **USABILE SUBITO** |

---

## Top 3 consigliate per partire

### 1. OKX API (pubblica) — ON-CHAIN SENTIMENT (funding + open interest)

Copre: funding rate, funding rate history, open interest, mark price, index candles — tutto senza chiave.

```bash
# Funding rate BTC corrente
curl -s 'https://www.okx.com/api/v5/public/funding-rate?instId=BTC-USDT-SWAP'

# Funding rate history (ultimi 5 periodi)
curl -s 'https://www.okx.com/api/v5/public/funding-rate-history?instId=BTC-USDT-SWAP&limit=5'

# Open interest BTC
curl -s 'https://www.okx.com/api/v5/public/open-interest?instId=BTC-USDT-SWAP'

# Index candles giornalieri (per calcolare basis)
curl -s 'https://www.okx.com/api/v5/market/index-candles?instId=BTC-USDT&bar=1D&limit=30'
```

**Cosa copre:** Funding rate (8h cadenza), open interest (real-time), mark price, basis via index vs mark — tutto per il sentiment trading.

**Nota:** Il progetto usa OKX EEA — anche `eea.okx.com` funziona identico.

---

### 2. CoinGecko API (pubblica) — PREZZO + SENTIMENT DI MERCATO

Copre: prezzo, market cap, volume, 24h change, dati globali, storico prezzi.

```bash
# Prezzo BTC + 24h change
curl -s 'https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd&include_24hr_change=true'

# Storico 30 giorni (orario/giornaliero)
curl -s 'https://api.coingecko.com/api/v3/coins/bitcoin/market_chart?vs_currency=usd&days=30'

# Dati globali mercato
curl -s 'https://api.coingecko.com/api/v3/global'
```

**Cosa copre:** Prezzo attuale, variazioni, total market cap, volume, storico fino a 90 giorni gratis.

---

### 3. Fear & Greed Index + Mempool.space — SENTIMENT + ON-CHAIN BASE

Copre: indice fear/greed (sentiment aggregato), fee di rete (traffico blockchain), mempool stats, mining hashrate.

```bash
# Fear & Greed (ultimi 7 giorni)
curl -s 'https://api.alternative.me/fng/?limit=7'

# Fee raccomandate (real-time)
curl -s 'https://mempool.space/api/v1/fees/recommended'

# Hashrate 24h
curl -s 'https://mempool.space/api/v1/mining/hashrate/24h'

# Mempool stats (traffico pending tx)
curl -s 'https://mempool.space/api/mempool'
```

**Cosa copre:** Sentiment fear/greed (daily), fee di rete (real-time), attività mining, congestione mempool.

---

## Fonti scartate

| Fonte | Endpoint testato | Motivo |
|---|---|---|
| **Blockchain.info MVRV chart** | `https://api.blockchain.info/charts/mvrv?format=json` | HTTP 400 — chart "mvrv" non esiste. Blockchain.info non espone MVRV via API pubblica. |
| **Blockchain.info realized-cap** | `https://api.blockchain.info/charts/realized-cap` | HTTP 400 — stesso limite. |
| **Blockchain.info market-price** | `https://api.blockchain.info/charts/market-price` | HTTP 400 — stesso limite. |
| **Coinglass (tutti gli endpoint)** | `https://fapi.coinglass.com/api/fundingRate/BTC`, `https://www.coinglass.com/api/fundingRate/BTC`, `https://open-api.coinglass.com/api/v1/funding/rate?symbol=BTC` | Tutti HTTP 404. Richiede API key + account. |
| **OKX index price** | `https://www.okx.com/api/v5/public/index-price?instId=BTC-USD` | HTTP 404 — endpoint inesistente (index via index-candles funziona). |
| **DefiLlama /tvl/ethereum (direct)** | `https://api.llama.fi/tvl/ethereum` | Risposta vuota. Forse deprecato. Usare `/v2/chains`. |
| **Mempool /mining/difficulty/7d** | `https://mempool.space/api/v1/mining/difficulty/7d` | HTTP 404 — endpoint non supportato. |

---

## Note aggiuntive

- **Blockchain.com charts API** è limitata: i parametri `timespan` funzionano solo se l'URL è compilato correttamente (usare `&` non `&` nell'URL crudo). Alcuni chart popolari (market-price, realized-cap, mvrv) NON sono accessibili — solo `n-transactions`, `hash-rate`, `difficulty` e pochi altri.
- **Coinglass** è completamente bloccato senza API key (richiede piano a pagamento). Da evitare per now.
- **CoinGecko** ha rate limit (10-30 req/min) senza chiave, sufficiente per polling non intensivo.
- **OKX** non richiede chiave per endpoint pubblici read-only (funding, open interest, mark price, index candles). Rate limit generoso (~20 req/s).
- **MVRV ratio** non è disponibile da nessuna fonte pubblica gratuita (né blockchain.info, né Coingecko, né DefiLlama). Necessita LookIntoBitcoin (solo web UI) o Glassnode (a pagamento). Workaround: calcolare approssimazione da `market_price_usd` (blockchain.info stats) e `realized cap` stimato, ma non è preciso.
- **DefiLlama** è la migliore fonte pubblica per TVL cross-chain.
- **Mempool.space** è eccellente per metriche on-chain Bitcoin real-time.
