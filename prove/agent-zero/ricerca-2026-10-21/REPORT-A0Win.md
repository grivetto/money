# REPORT — Ricerca soluzioni (codice e tecniche) per il progetto Denaro

**Data di consultazione:** 2026-10-21 (CEST)
**Autore:** Agent Zero (ricerca solo-lettura, nessuna esecuzione di codice trovato)
**Contesto:** trading crypto sistematico Python 3.12 + ccxt; OKX, Bybit, Bitvavo; capitali ~1.100 EUR; costi RT misurati ~28-40 bp; niente HFT.

## Metodo e limiti di verifica
- **Repository:** verificati via GitHub REST API pubblica (senza chiave): `stargazers_count`, `pushed_at`, `license.spdx_id`, `archived`. Sono dati reali letti dal file JSON salvato in `raw/`.
- **Paper:** DOI/titoli verificati via Crossref API (senza chiave). Per i paper arXiv ho verificato solo i metadati via Semantic Scholar API o la pagina `arxiv.org/abs/`; **non ho letto i full-text**. Niente affermazioni sul contenuto oltre a quanto dichiarato nel titolo/abstract visto.
- **Documenti/API:** verifica HTTP HEAD/GET dello status code delle pagine.
- **Non verificato:** full-text dei paper, piani tariffari/limiti free di alcuni servizi (Tardis, CoinGecko), contenuto dei repo piccoli, storie operative di exchange (okx docs non raggiungibile dal container).

---

## 1. Strategie con evidenza out-of-sample pubblica e riproducibile

### Makarov & Schoar — *Trading and Arbitrage in Cryptocurrency Markets*
- **Tipo:** paper accademico (Journal of Financial Economics, 2020)
- **URL:** doi:10.1016/j.jfineco.2019.07.001 (SSRN: 3171204) — https://doi.org/10.1016/j.jfineco.2019.07.001
- **Cosa fa:** documenta grandi deviazioni dei prezzi crypto fra exchange e arbitraggi cross-exchange; quantifica costi/barriere (capitale, tempi di trasferimento) e mostra come le opportunità si riducono col tempo.
- **Perché ci serve / dove si innesta:** execution | data. Base di riferimento per capire dove vivono gli spread reali (CEX vs CEX, spot vs perp) e quale frequenza di riallineamento è sopravvivibile con 1.100 EUR e 28-40 bp RT. Usato come esterno per calibrare le nostre soglie di arbitraggio/carry.
- **Maturità:** pubblicato, peer-reviewed; licenza n/a (paper). Attività: paper del 2020, ancora riferimento.
- **Primo esperimento:** confrontare la nostra esperienza reale di slippage/costi sui 3 exchange (dai fill già registrati) con le deviazioni cross-exchange descritte; misuriamo se dopo costi resta margine su BTC/ETH vs altcoin.

### Moskowitz, Ooi & Pedersen — *Time Series Momentum*
- **Tipo:** paper accademico (Journal of Financial Economics, 2012)
- **URL:** doi:10.1016/j.jfineco.2011.11.003 (SSRN: 2089463) — https://doi.org/10.1016/j.jfineco.2011.11.003
- **Cosa fa:** definisce il momentum time-series su 58 futures (equity, valute, commodity, bond) con lookback 12 mesi e holding 1 mese, con robustezza su 100+ anni.
- **Perché ci serve:** strategy | validation. È la famiglia di riferimento per il trend: il progetto ha già bocciato momentum su estremi out-of-sample, ma qui si può confrontare la specifica TSMOM classica sui nostri dati con costi reali.
- **Maturità:** paper classico, molto citato; niente codice ufficiale (repliche pubbliche numerose ma non verificate qui).
- **Primo esperimento:** backtest TSMOM standard (lookback 12M/1M, long-only e long-short) su OHLCV BTC/ETH da ccxt con 35 bp RT; obiettivo: rapporto Sharpe netto > 0 e DSR > 0.95, altrimenti chiudiamo la famiglia con evidenza.

### Huang, Sangiorgi & Urquhart — *Cryptocurrency Volume-Weighted Time Series Momentum* (2024)
- **Tipo:** working paper (SSRN)
- **URL:** doi:10.2139/ssrn.4825389 — https://doi.org/10.2139/ssrn.4825389
- **Cosa fa:** variante del momentum time-series pesata per volume applicata a crypto.
- **Perché ci serve:** strategy | validation. Possibile miglioramento della specifica TSMOM con filtro volume; da testare OOS con i nostri costi.
- **Maturità:** SSRN, 2024; **non verificato**: full-text e dichiarazione esplicita di costi/OOS.
- **Primo esperimento:** replicare la versione pesata per volume e confrontarla con TSMOM plain sullo stesso dataset; misura: Sharpe netto OOS a costi 28-40 bp.

### Cheng, Deng & Wang — *Liquidation, Leverage and Optimal Margin in Bitcoin Futures Markets* (2021)
- **Tipo:** working paper (SSRN)
- **URL:** doi:10.2139/ssrn.3781646 — https://doi.org/10.2139/ssrn.3781646
- **Cosa fa:** studia liquidazioni, leva ottima e margine nei futures/perpetual Bitcoin.
- **Perché ci serve:** strategy | risk. Base per usare i dati di liquidazioni/OI come segnale o come vincolo di risk (evitare di essere noi la liquidazione).
- **Maturità:** SSRN, 2021; **non verificato** il full-text.
- **Primo esperimento:** correlazione fra picchi di liquidazioni e movimenti di prezzo su OKX (dati pubblici liquidations) su 90 giorni; se il segnale sopravvive ai costi, testarlo come overlay del trend.

### Moreira & Muir — *Volatility Managed Portfolios*
- **Tipo:** paper accademico (NBER w22208; poi Journal of Finance)
- **URL:** doi:10.3386/w22208 — https://doi.org/10.3386/w22208
- **Cosa fa:** mostra che scalare l'esposizione con l'inverso della volatilità realizzata migliora Sharpe e riduce drawdown per molte asset class.
- **Perché ci serve:** risk | strategy. È il metodo di vol-targeting di riferimento: si innesta come strato di sizing sopra qualunque segnale (anche i carry attuali).
- **Maturità:** paper consolidato; niente codice ufficiale verificato. Implementazioni semplici in Riskfolio-Lib/skfolio.
- **Primo esperimento:** applicare vol targeting (inverso di RV 20d, cap al 2x) al portafoglio carry esistente; misura: Sharpe netto e max drawdown prima/dopo.

### Nota hard sulla categoria
- **Evidenza pubblica riproducibile con costi dichiarati:** molto rara. I paper accademici crypto spesso coprono periodi rialzisti (2017-2020) e non dichiarano costi/regime post-2021. Qualunque repo che mostra solo equity curve senza periodo/costi/OOS è etichettato "non verificabile".
- Il progetto ha già bocciato 4 famiglie con walk-forward + DSR/PBO: il riflesso è giusto. Le risorse sopra servono a creare baseline confrontabili, non a promuovere segnali.

---

## 2. Architetture di bot riusabili

### freqtrade/freqtrade
- **Tipo:** repo
- **URL:** https://github.com/freqtrade/freqtrade — docs: https://docs.freqtrade.io/en/stable/ (HTTP 200 verificato)
- **Cosa fa:** bot crypto completo in Python: motore di strategie, backtesting, dry-run/paper/live con lo stesso codice, gestione persistenza SQLite, web UI, systemd/telegram, ~migliaia di test.
- **Perché ci serve / dove si innesta:** architettura/execution | risk (stoploss, max_open_trades, position sizing). È il candidato principale per risolvere il problema "13 bot paper con zero trade": il dry-run engine di freqtrade esegue davvero ordini simulati con min_notional/limiti ed è molto scrutinato.
- **Maturità:** GPL-3.0, stars 55.708, ultimo push 2026-10-21, attivissimo.
- **Primo esperimento:** non eseguire codice: confrontare la logica paper del progetto con il dry-run freqtrade su stessi parametri (min_notional, fees), su 1 simbolo BTC/USDT per 7 giorni; metrica: n. trade simulati e motivo di scarto (sizing vs soglia).

### jesse-ai/jesse
- **Tipo:** repo
- **URL:** https://github.com/jesse-ai/jesse
- **Cosa fa:** framework Python completo per strategie crypto: indicatori, backtest, live, paper, ottimizzazione, API.
- **Perché ci serve:** architettura | validation. Alternativa più "ricerca-first" a freqtrade; modello a eventi.
- **Maturità:** MIT, stars 8.682, ultimo push 2026-10-19, attivo.
- **Primo esperimento:** valutare se il suo modello di data feeding (candele+fees) spiega meglio il nostro zero-trade; confronto di configurazione, senza installare nulla.

### Drakkar-Software/OctoBot
- **Tipo:** repo
- **URL:** https://github.com/Drakkar-Software/OctoBot
- **Cosa fa:** bot con UI visuale, tentacles (strategie, exchanges), trading modes (grid, DCA, ecc.).
- **Perché ci serve:** architettura di riferimento per separazione valutatori/strategie/execution; meno adatto a integrarsi nel nostro codice Python custom.
- **Maturità:** GPL-3.0, stars 6.837, ultimo push 2026-10-21, attivo.
- **Primo esperimento:** leggere la struttura dei "tentacles" per estrarre pattern di separazione signal/execution (solo lettura della documentazione).

### hummingbot/hummingbot
- **Tipo:** repo
- **URL:** https://github.com/hummingbot/hummingbot
- **Cosa fa:** framework per bot market making/arbitrage, con connettori CEX/DEX, backtest e paper mode.
- **Perché ci serve:** execution | architettura. Riferimento per connettori e per strategie market-making (anche se noi non faremo HFT); utile per pattern di reconnect/riconciliazione.
- **Maturità:** Apache-2.0, stars 20.620, ultimo push 2026-10-20, attivo.
- **Primo esperimento:** estrarre il pattern di gestione fill/reconcile usato da hummingbot e confrontarlo col nostro storage SQLite/JSONL (sola lettura del codice).

### nautechsystems/nautilus_trader
- **Tipo:** repo
- **URL:** https://github.com/nautechsystems/nautilus_trader
- **Cosa fa:** trading engine Rust-native, event-driven, deterministico; backtest e live con lo stesso codice; forte enfasi su test e replicabilità.
- **Perché ci serve:** architettura | execution | validation. Candidato per una futura migrazione del motore di ricerca in un sistema deterministico e testato.
- **Maturità:** LGPL-3.0, stars 30.514, ultimo push 2026-10-21, molto attivo. Progetto più pesante: curva di apprendimento alta.
- **Primo esperimento:** solo lettura: esaminare i loro test di backtest con commissioni/slippage e il modello di cronologia deterministica.

### Superalgos/Superalgos (con caveat)
- **Tipo:** repo
- **URL:** https://github.com/Superalgos/Superalgos
- **Cosa fa:** piattaforma di trading visuale/data con community, in Node.js.
- **Perché ci serve:** data/lab per prototipare velocemente; **caveat**: monolitico, UI-centric, poco adatto a innestarsi nel nostro stack Python; usato solo come ispirazione.
- **Maturità:** Apache-2.0, stars 5.716, ultimo push 2026-10-15, attivo.

### vnpy/vnpy (con caveat)
- **Tipo:** repo
- **URL:** https://github.com/vnpy/vnpy
- **Cosa fa:** framework quant trading cinese, event engine, gateway multipli, UI Qt.
- **Perché ci serve:** pattern di event engine e gateway exchange; **caveat**: orientato a mercati cinesi/CTA, UI pesante.
- **Maturità:** MIT, stars 45.971, ultimo push 2026-10-06, attivo.

### freqtrade/freqtrade-strategies
- **Tipo:** repo (esempi di strategie)
- **URL:** https://github.com/freqtrade/freqtrade-strategies
- **Cosa fa:** collezione di strategie della community per freqtrade.
- **Perché ci serve:** ispirazione/patttern di strategie con setup di test; **non** come fonte di segnali validati.
- **Maturità:** GPL-3.0, stars 5.578, ultimo push 2026-09-08, attivo.

---

## 3. Execution

### ccxt/ccxt (già in uso)
- **Tipo:** repo
- **URL:** https://github.com/ccxt/ccxt — docs: https://docs.ccxt.com/ (HTTP 200)
- **Cosa fa:** libreria unificata per 100+ exchange: order, OHLCV, funding, rate limits, errori normalizzati.
- **Perché ci serve:** execution | data. Già colonna portante del progetto; per execution serve sfruttare `createLimitOrder`, reprice, `fetchOrder`, e gestione rate limit esplicita.
- **Maturità:** MIT, stars 44.500, ultimo push 2026-10-21.
- **Primo esperimento:** audit del nostro layer ccxt: quante chiamate per ordine, backoff, e come il rate limit di OKX/Bybit/Bitvavo influisce sul reprice (con i log già esistenti).

### tardis-dev/tardis-node
- **Tipo:** repo
- **URL:** https://github.com/tardis-dev/tardis-node — docs: https://docs.tardis.dev/ (HTTP 200)
- **Cosa fa:** accesso conveniente a dati tick-level (L2 book, trades) storici e real-time di molti exchange, in Node.js.
- **Perché ci serve:** execution/data | microstruttura. Per misurare slippage vs mid e order book imbalance serve tick/L2, non solo OHLCV.
- **Maturità:** MPL-2.0, stars 367, ultimo push 2026-10-21. **Limiti piano free non verificati** (probabile pagamento per download storici completi).
- **Primo esperimento:** scaricare un campione L2 per BTC/USDT su uno degli exchange supportati e misurare slippage teorico di ordini 50-200 EUR vs mid; metrica: bp di slippage atteso vs i 10 bp taker.

### urkmezakin41-gif/twap-engine
- **Tipo:** repo (piccolo)
- **URL:** https://github.com/urkmezakin41-gif/twap-engine
- **Cosa fa:** motore TWAP exchange-agnostic con slippage-abort e opzioni.
- **Perché ci serve:** execution. Con 1.100 EUR, ordini grandi rispetto al book richiedono TWAP; il pattern slippage-abort è riusabile.
- **Maturità:** MIT, stars 1, ultimo push 2026-08-08, recente ma a bassissima maturità; va trattato come riferimento di design, non come dipendenza.
- **Primo esperimento:** micro-campionare 3-5 ordini reali del progetto con/without TWAP; misurare slippage medio e varianza.

### DaanZunnenberg/Aletheia
- **Tipo:** repo (piccolo)
- **URL:** https://github.com/DaanZunnenberg/Aletheia
- **Cosa fa:** framework market-making per perp (Deribit, BTC/ETH) con backtest e live multi-exchange.
- **Perché ci serve:** execution/backtest di market making; **caveat**: noi non faremo market making di latenza, ma il motore di backtest con costi è interessante per capire il costo di fare il maker.
- **Maturità:** NOASSERTION (licenza non chiara), stars 5, ultimo push 2026-09-28; licenza da chiarire.
- **Primo esperimento:** confrontare la simulazione di fee maker vs taker sui nostri symbol; metrica: quante bp risparmiamo passando a limit+reprice.

### Docs exchange (execution)
- **Bybit V5:** https://bybit-exchange.github.io/docs/v5/intro (HTTP 200) — rate limit, order types.
- **Bitvavo:** https://docs.bitvavo.com/ (HTTP 200) — rest/websocket, fee.
- **OKX:** https://docs.okx.com/ (HTTP 000 dal container: non raggiungibile/errato; **non verificato**).
- **Perché ci servono:** definire parametri esatti di rate limit, min_notional, tick size per il reprice.

### Modelli di costo/impact
- **Cheng/Deng/Wang (2021) e Makarov/Schoar (2020)** già citati: contengono misure di impatto e cross-pricing.
- **Nota:** nessun modello di impact pronto e verificato trovato per i nostri exchange con 1.100 EUR: la raccomandazione è misurare dai nostri fill (già facciamo: 10 bp spot, 5 bp perp) e aggiungere slippage relativo al book locale.

---

## 4. Risk

### dcajasn/Riskfolio-Lib
- **Tipo:** repo
- **URL:** https://github.com/dcajasn/Riskfolio-Lib
- **Cosa fa:** ottimizzazione di portafoglio in Python: mean-variance, CVaR, Black-Litterman, vincoli, HRP, vol targeting.
- **Perché ci serve:** risk. Pronto all'uso per gestire il portafoglio multi-strategia (carry + canary + eventuali direzionali) con correlazioni e vol targeting.
- **Maturità:** BSD-3-Clause, stars 4.553, ultimo push 2026-10-04, attivo.
- **Primo esperimento:** calcolare allocazione vol-target su 3 strategie esistenti con rendimenti settimanali stimati; metrica: Sharpe netto di portafoglio vs singole strategie.

### skfolio/skfolio
- **Tipo:** repo
- **URL:** https://github.com/skfolio/skfolio
- **Cosa fa:** ottimizzazione portafoglio costruita su scikit-learn: API familiare, cross-validation, model selection.
- **Perché ci serve:** risk | validation. Alternativa più moderna a Riskfolio-Lib con integrazione sklearn.
- **Maturità:** BSD-3-Clause, stars 2.526, ultimo push 2026-10-21, attivo.
- **Primo esperimento:** stessi test di Riskfolio-Lib per confrontare API/stabilità; metrica: tempo di calcolo e robustezza dei pesi.

### ranaroussi/quantstats
- **Tipo:** repo
- **URL:** https://github.com/ranaroussi/quantstats
- **Cosa fa:** report di performance e rischio (Sharpe, Sortino, drawdown, VaR, heatmaps) in HTML.
- **Perché ci serve:** risk | reporting. Report standardizzati per ogni strategia e per l'audit OOS.
- **Maturità:** Apache-2.0, stars 7.732, ultimo push 2026-09-27, attivo.
- **Primo esperimento:** generare report quantstats per il carry esistente dai rendimenti giornalieri; metrica: max drawdown, calmar, VaR 95%.

### stefan-jansen/pyfolio-reloaded
- **Tipo:** repo
- **URL:** https://github.com/stefan-jansen/pyfolio-reloaded
- **Cosa fa:** analisi di portafoglio e tear-sheet (successore mantenuto di quantopian/pyfolio).
- **Perché ci serve:** risk | validation. Tear-sheet per i backtest OOS.
- **Maturità:** Apache-2.0, stars 616, ultimo push 2026-10-19, attivo.

### Kelly criterion, daily limits, kill switch, risk of ruin
- **Non ho trovato repo maturi e mantenuti specifici per Kelly/risk-of-ruin con licenza chiara.** I repo trovati via search GitHub (es. prediction-market bot con Kelly) sono piccoli, non focalizzati o con licenza assente.
- **Perché ci serve:** risk. La raccomandazione è implementare internamente (formule standard: Kelly frazionale, vol targeting, max DD giornaliero, kill switch) con test pytest già nel nostro framework; pattern già presenti nei nostri `test_risk_p2.py`.
- **Primo esperimento:** calcolare Kelly frazionario (f=1/4) sul carry storico e confrontare con l'attuale sizing; misura: crescita geometrica netta simulata Monte Carlo.

---

## 5. Validazione statistica

### Bailey, Borwein & López de Prado — *The Probability of Backtest Overfitting* (PBO)
- **Tipo:** paper (SSRN)
- **URL:** doi:10.2139/ssrn.2326253 — https://doi.org/10.2139/ssrn.2326253
- **Cosa fa:** introduce la probabilità di overfitting del backtest tramite CSCV, discriminando strategie robuste da quelle selezionate per caso.
- **Perché ci serve:** validation. Il progetto già usa PBO; questa è la fonte primaria da citare per ri-calibrare la procedura.
- **Maturità:** SSRN, 2013, molto citato; **non verificato** full-text.

### Bailey & López de Prado — *The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting and Non-Normality* (DSR)
- **Tipo:** paper (SSRN)
- **URL:** doi:10.2139/ssrn.2460551 — https://doi.org/10.2139/ssrn.2460551
- **Cosa fa:** corregge lo Sharpe per numero di trial, non-normalità e varianza di stima: Sharpe "deflazionato".
- **Perché ci serve:** validation. Base della regola progetto "nessuna promozione senza evidenza OOS".
- **Maturità:** SSRN, 2019; **non verificato** full-text.

### Yosri-Ben-Halima/cpcv-train-test-data-split-module
- **Tipo:** repo
- **URL:** https://github.com/Yosri-Ben-Halima/cpcv-train-test-data-split-module
- **Cosa fa:** implementazione MIT di Combinatorial Purged Cross-Validation (CPCV) per serie temporali.
- **Perché ci serve:** validation. Riusabile per la walk-forward combinatoria.
- **Maturità:** MIT, stars 2, ultimo push 2025-09-04 (10 mesi, borderline); repo piccolo, va testato.
- **Primo esperimento:** verificare che i suoi split rispettino embargo/purge sui nostri dati (30m/1h); metrica: assenza di leakage sul lag test.

### Furkan-rgb/PurgeEmbargoKFoldCV
- **Tipo:** repo
- **URL:** https://github.com/Furkan-rgb/PurgeEmbargoKFoldCV
- **Cosa fa:** K-fold purged con embargo per serie temporali.
- **Perché ci serve:** validation. Alternativa leggera.
- **Maturità:** MIT, stars 1, ultimo push 2026-03-02, recente ma immaturo.

### RafaelPupio/purged-walkforward
- **Tipo:** repo
- **URL:** https://github.com/RafaelPupio/purged-walkforward
- **Cosa fa:** walk-forward purged/embargoed per serie con overlap.
- **Perché ci serve:** validation.
- **Maturità:** MIT, stars 0, ultimo push 2026-09-29, molto immaturo.

### TonyMa1/walk-forward-backtester
- **Tipo:** repo
- **URL:** https://github.com/TonyMa1/walk-forward-backtester
- **Cosa fa:** implementazione Python di Walk-Forward Optimization (WFO) con OOS per segmenti.
- **Perché ci serve:** validation. Confronto diretto con la nostra procedura walk-forward.
- **Maturità:** MIT, stars 12, ultimo push 2025-03-24 (18 mesi, poco attivo).

### Altri backtester con costi (strumenti di validazione)
- **kernc/backtesting.py** — AGPL-3.0, stars 9.096, ultimo push 2026-08-05, attivo; https://github.com/kernc/backtesting.py
- **pmorissette/bt** — MIT, stars 2.999, ultimo push 2026-10-20; https://github.com/pmorissette/bt
- **stefan-jansen/zipline-reloaded** — Apache-2.0, stars 1.969, ultimo push 2026-10-19; https://github.com/stefan-jansen/zipline-reloaded
- **stefan-jansen/alphalens-reloaded** — Apache-2.0, stars 672, ultimo push 2026-10-17; https://github.com/stefan-jansen/alphalens-reloaded
- **microsoft/qlib** — MIT, stars 49.587, ultimo push 2026-10-14; AI quant platform, ma orientata a equities asiatiche; https://github.com/microsoft/qlib
- **optuna/optuna** — MIT, stars 14.947, ultimo push 2026-10-21; ottimizzazione iperparametri con pruning; https://github.com/optuna/optuna

---

## 6. Dati

### ccxt (OHLCV, funding, OI)
- **URL:** https://docs.ccxt.com/ (HTTP 200)
- **Cosa fa:** OHLCV, funding rate history, open interest su OKX/Bybit (e parzialmente Bitvavo) con la stessa API.
- **Perché ci serve:** data. Strato già esistente; da estendere con funding/OI/liquidations dove supportati.
- **Maturità:** MIT, attivo (vedi sopra).

### binance/binance-public-data
- **Tipo:** repo (dataset/istruzioni)
- **URL:** https://github.com/binance/binance-public-data
- **Cosa fa:** istruzioni e script per scaricare dati storici pubblici Binance (spot, futures, funding, trades, aggTrades).
- **Perché ci serve:** data. Fonte gratuita di OHLCV/funding storici per ricerca fuori dai nostri exchange (utile per test di robustezza cross-exchange); licenza non dichiarata nello snippet verificato → **da chiarire**.
- **Maturità:** stars 2.545, ultimo push 2026-10-16, attivo.
- **Primo esperimento:** usare i downloader per un dataset di 1-2 anni BTC/ETH futures, con funding, e replicare i test che facciamo su OKX/Bybit.

### StonkyLab/crypto-data-downloader
- **Tipo:** repo (piccolo)
- **URL:** https://github.com/StonkyLab/crypto-data-downloader
- **Cosa fa:** utilità Python per scaricare OHLCV e funding rates da exchange maggiori.
- **Perché ci serve:** data. Potenziale raccoglitore leggero per i nostri nodi.
- **Maturità:** MIT, stars 3, ultimo push 2026-10-18, recente ma immaturo.

### bmoscon/cryptofeed
- **Tipo:** repo
- **URL:** https://github.com/bmoscon/cryptofeed
- **Cosa fa:** feed WebSocket per molti exchange, normale verso eventi di libro/trade/funding.
- **Perché ci serve:** data | execution. Per L2 e tick in tempo reale dove serve microstruttura.
- **Maturità:** licenza AGPL-3.0 (verificata da raw LICENSE: "GNU Affero General Public License... v3"), stars 2.927, ultimo push 2026-10-19, attivo. **Nota licenza:** AGPL ha vincoli per chi distribuisce/serve;
- **Primo esperimento:** solo valutazione della licenza e confronto con lo ZMQ market source già presente.

### API gratuite e dati on-chain
- **CoinGecko API:** https://api.coingecko.com/api/v3/ping (HTTP 200 verificato; pagina web https://www.coingecko.com/en/api risponde 403 al curl → documentazione non verificata da script).
- **Chainid:** https://chainid.network/ (HTTP 200) — IDs chain per network EVM/Base.
- **Tardis (dati storici tick):** docs HTTP 200; limiti free non verificati.
- **CoinCap:** https://api.coincap.io/v2/rates/bitcoin (HTTP 000 dal container → **non verificato**; possibile blocco rete).

### Trappole note (da includere nei nostri raccoglitori)
- **Look-ahead:** non riallineare funding/OI alla stessa chiusura della candela usata come segnale.
- **Survivorship:** i dataset Binance/Bybit attuali escludono i delisted; per OOS onesto servono snapshot o liste storiche.
- **Cache stantie:** timestamp delle candle (aperta/chiusura) e timezone: il server `nuvola` è in UTC? Da verificare nei nostri feeder.
- **Fonte non verificata:** file JSONL/SQLite già sul progetto non validati in questa ricerca.

---

## 7. Microstruttura crypto

### Paper (metadati verificati via Semantic Scholar API; full-text non letto)
- **When Does Order Flow Matter? State-Dependent L2 Liquidity-State Transitions in Crypto Futures** — arXiv:2607.09230 (2026)
  - Cosa fa (da titolo): transizioni di stato di liquidità L2 condizionate allo stato del mercato, in futures crypto.
  - Perché ci serve: execution | data. Per studiare imbalance e liquidità nei momenti chiave (es. funding settlement).
  - Maturità: preprint arXiv; **non verificato** il contenuto completo.
- **Optimal Signal Extraction from Order Flow: A Matched Filter Perspective on Normalization and Market Microstructure** — arXiv:2512.18648 (2025)
  - Cosa fa (da titolo): estrazione di segnale da order flow con matched filter.
  - Perché ci serve: execution | strategy. Tecnica di normalizzazione del flusso ordini.
- **Robust Market Making with Hawkes Order Flow and Price Impact via Adversarial Reinforcement Learning** — arXiv:2609.22785 (2026)
  - Cosa fa (da titolo): market making robusto con order flow Hawkes e impact via RL adversarial.
  - Perché ci serve: execution. Solo riferimento accademico (noi non faremo MM di latenza).

### Repo
- **mansoor-mamnoon/limit-order-book** — C++ core + Python SDK, motore order book ad alte prestazioni. Licenza assente nello snippet verificato, stars 92, ultimo push 2025-08-30. Riferimento di design per elaborare L2 se servirà; **caveat licenza**.
- **kostyafarber/crypto-lob-data-pipeline** — pipeline Kafka per L2 Deribit del 2022 (MIT, non recente: 2022-08-10): scartato per attività.
- **davelamtrader/Strategy-Backtest-Orderbook-Imbalance-Pattern-based-Cryptocurrencies-Screening-Trading-Strategy** — repo piccolo (stars 2, 2025-08-24, licenza assente): **non verificabile**, scartato.

---

## 8. On-chain/DeFi (scommessa asimmetrica)

### wevm/viem
- **Tipo:** repo
- **URL:** https://github.com/wevm/viem
- **Cosa fa:** interfaccia TypeScript per Ethereum: account locali, transazioni, smart contract, nonce management.
- **Perché ci serve:** on-chain | infra. Firma locale → invio → verifica, idempotenza (nonce), gas; ideale per il wallet Base dedicato.
- **Maturità:** licenza MIT (verificata da raw `src/LICENSE`: "MIT License"), stars 3.590, ultimo push 2026-10-21, attivissimo.
- **Primo esperimento:** non eseguire codice: redigere una checklist di firma locale/invio/verifica (nonce, gas, reorg) usando i pattern viem; solo documentazione.

### ethers-io/ethers.js
- **Tipo:** repo
- **URL:** https://github.com/ethers-io/ethers.js
- **Cosa fa:** libreria Ethereum in TypeScript/JavaScript, molto diffusa.
- **Perché ci serve:** on-chain. Alternativa a viem, più legacy; supporto Base L2.
- **Maturità:** MIT, stars 8.719, ultimo push 2026-06-18, attivo.

### ApeWorX/web3.py (già ethereum/web3.py)
- **Tipo:** repo
- **URL:** https://github.com/ApeWorX/web3.py (redirect ufficiale da ethereum/web3.py)
- **Cosa fa:** libreria Ethereum in Python, mantenuta ora da ApeWorX.
- **Perché ci serve:** on-chain. Siamo team Python: per i tooling di farming/claim può essere più comoda di viem.
- **Maturità:** MIT, stars 5.546, ultimo push 2026-09-29, attivo.

### ApeWorX/ape
- **Tipo:** repo
- **URL:** https://github.com/ApeWorX/ape
- **Cosa fa:** framework Python per sviluppo/automazione on-chain (account, transazioni, test).
- **Perché ci serve:** on-chain. Gestione wallet dedicato, script di farming/claim riusabili.
- **Maturità:** Apache-2.0, stars 1.054, ultimo push 2026-10-21, attivo.

### alloy-rs/alloy
- **Tipo:** repo
- **URL:** https://github.com/alloy-rs/alloy
- **Cosa fa:** toolkit Ethereum in Rust (trasporti, middleware, reti).
- **Perché ci serve:** on-chain | infra. Alternativa Rust se servirà performance; il progetto Denaro è Python, quindi secondario.
- **Maturità:** Apache-2.0, stars 1.342, ultimo push 2026-10-21, attivo.

### Nota su idempotenza/nonce/gas/bridge
- Nessun repo maturo e verificato trovato specifico per "farming airdrop idempotente con nonce/gas ottimale". I pattern sono ben documentati dalle librerie sopra (viem/web3.py) e nelle best practice dei bridge CEX→DEX. **Non verificato**: guide specifiche per Base airdrop farming.

---

## 9. Strumenti per la ricerca quant (screener, backtester, optimizer)

- **Optuna** (MIT, attivo): optimizer iperparametri con pruning; già citato in validation.
- **backtesting.py** (AGPL-3.0, attivo): backtester leggero; attenzione licenza.
- **bt** (MIT, attivo): backtest flessibile; buona manutenibilità.
- **Riskfolio-Lib / skfolio** (BSD-3-Clause, attivi): ottimizzazione portafoglio.
- **quantstats / pyfolio-reloaded** (Apache-2.0, attivi): analytics e report.
- **nautilus_trader** (LGPL-3.0, attivo): engine deterministico di ricerca/produzione.
- **qlib** (MIT, attivo): piattaforma AI quant; **scartato come scelta principale** perché orientata a equities e dataset complessi, non alla nostra scala retail crypto.
- **vectorbt** (Commons Clause, NOASSERTION): **scartato per licenza** (clausola che limita uso commerciale) nonostante popolarità e attività.

---

## TOP 5 da provare subito

1. **freqtrade (dry-run/paper)** — motivo: risolve il problema operativo più visibile (13 bot paper con zero trade) fornendo un benchmark di dry-run reale, con test consolidati e licenza chiara; costo di prova: basso, solo comparazione.
2. **Tardis / ccxt per dati L2 e funding** — motivo: senza dati di libro/funding non possiamo validare execution né carry; Tardis-node è attivo (MPL-2.0) e ccxt è già nello stack.
3. **Riskfolio-Lib o skfolio per il risk layer** — motivo: con 4+/strategie servono allocazione multi-strategia, vol targeting e correlazioni; sono pronte, MIT/BSD, attive.
4. **NautilusTrader come motore deterministico di ricerca** — motivo: unifica backtest/live con lo stesso codice, ha test seri e permette di replicare gli esperimenti OOS in modo affidabile; più pesante, da adottare per la ricerca successiva.
5. **godzilla-community (infrastruttura funding rate self-hosted)** — motivo: allineato al carry attivo, open source (Apache-2.0), attivo; consente di rendere la raccolta/calcolo funding esplicita e riconciliata.

## Scartati (motivo in una riga)
- **askmike/gekko** — archiviato dal 2020 (MIT, archived=True).
- **gakonst/ethers-rs** — archiviato nel 2024; sostituito da alloy-rs.
- **hudson-and-thames/mlfinlab** — ultimo push 2023, licenza non chiara (NOASSERTION); concetti utili ma non riusabili direttamente.
- **quantopian/pyfolio** — non mantenuto; usare pyfolio-reloaded.
- **aoki-h-jp/funding-rate-arbitrage** — inattivo dal 2023, Binance-centric.
- **vectorbt** — popolare e attivo ma licenza Commons Clause (non OSI) incompatibile con uso commerciale senza cautela.
- **microsoft/qlib** — orientato a equities/mercati Asia, eccessivo per scala retail crypto.
- **Superalgos** — monolitico e UI-centric, non si innesta nel nostro stack Python (resta fonte di ispirazione).
- **counterfactual5/funding-arb** — troppo giovane (stars 9) per essere base, ma da tenere d'occhio.
- **binance/binance-public-data** — utile, ma licenza non dichiarata nello snippet verificato; usare solo per dati propri.

## Fonti con URL e data di consultazione (2026-10-21)
Tutte le URL GitHub sono state lette via GitHub REST API pubblica; documenti/paper via Crossref/ArXiv/Semantic Scholar/HTTP status.
- Repo principali: freqtrade (GPL-3.0), jesse-ai/jesse (MIT), OctoBot (GPL-3.0), hummingbot (Apache-2.0), ccxt (MIT), cryptofeed (AGPL-3.0), nautilus_trader (LGPL-3.0), vnpy (MIT), Riskfolio-Lib (BSD-3-Clause), skfolio (BSD-3-Clause), quantstats (Apache-2.0), pyfolio-reloaded (Apache-2.0), alphalens-reloaded (Apache-2.0), backtesting.py (AGPL-3.0), bt (MIT), zipline-reloaded (Apache-2.0), optuna (MIT), qlib (MIT), PyPortfolioOpt (MIT), ApeWorX/ape (Apache-2.0), ApeWorX/web3.py (MIT), ethers.js (MIT), viem (MIT), alloy-rs (Apache-2.0), tardis-node (MPL-2.0), godzilla-community (Apache-2.0), Twap-engine (MIT), Aletheia (NOASSERTION), binance-public-data, StonkyLab/crypto-data-downloader (MIT), CPCV module (MIT), PurgeEmbargoKFoldCV (MIT), purged-walkforward (MIT), walk-forward-backtester (MIT).
- Paper: Makarov & Schoar JFE 2020 (doi:10.1016/j.jfineco.2019.07.001); Moskowitz, Ooi & Pedersen JFE 2012 (doi:10.1016/j.jfineco.2011.11.003); Huang, Sangiorgi & Urquhart 2024 (doi:10.2139/ssrn.4825389); Cheng, Deng & Wang 2021 (doi:10.2139/ssrn.3781646); Moreira & Muir NBER (doi:10.3386/w22208); Bailey, Borwein & López de Prado 2013 (doi:10.2139/ssrn.2326253); Bailey & López de Prado 2019 (doi:10.2139/ssrn.2460551).
- Preprint (metadati verificati): arXiv:2607.09230; arXiv:2512.18648; arXiv:2609.22785.
- Docs/API: docs.freqtrade.io (200), docs.ccxt.com (200), bybit-exchange.github.io (200), docs.bitvavo.com (200), docs.tardis.dev (200), api.coingecko.com/api/v3/ping (200), chainid.network (200), api.coincap.io (000 non verificato), docs.okx.com (000 non verificato).

## Non verificabile / non verificato in questa ricerca
- Full-text dei paper accademici e preprint: ho letto solo metadati (titolo, anno, DOI, venue) via Crossref/Semantic Scholar; nessuna conclusione sul contenuto empirico oltre il titolo.
- Limiti/piani free di Tardis, CoinGecko e CoinCap: non verificati da pagine complete.
- Licenze di alcuni repo piccoli (NOASSERTION o campo assente): non determinate in modo affidabile, segnalate come "da chiarire".
- OKX docs e CoinCap non raggiungibili dal container di ricerca (HTTP 000): possibile blocco di rete, non verifica della disponibilità del servizio.
- Contenuto interno dei repo del progetto (SQLite/JSONL, log dei 13 bot paper): non analizzato in questa ricerca (fuori scope, nessuna esecuzione).

## Cosa consiglio di fare per primo (max 20 righe)
1. La priorità non è trovare la strategia magica, ma chiudere il buco operativo del paper trading a zero trade e rendere i costi di execution misurabili. Senza questo, ogni esperimento OOS è sospetto.
2. Esperimento n.1 (pronto da girare, nessuna installazione): **audit di execution e di paper-trading** sui 3 exchange.
   - Input: log già esistenti dei 13 bot paper + fill storici del progetto (spot/perp).
   - Procedura: (a) per ogni bot paper, estrarre i motivi di non-esecuzione: segnale sotto soglia, sizing arrotondato a 0, min_notional non raggiunto, rate limit, prezzo non attraversato; (b) per i fill reali, calcolare slippage = (prezzo medio eseguito - mid all'invio) in bp, separando spot e perp; (c) confrontare con 10/5 bp taker e con il budget 28-40 bp RT.
   - Output atteso: tabella per bot/exchange di (n_segnali, n_trade, motivo_scarto, slippage_medio, slippage_p99, fee_pagate).
   - Criterio di successo: riusciamo a spiegare ≥90% dei casi zero-trade e abbiamo una stima slippage per simbolo.
3. In parallelo (lettura): scaricare e leggere la documentazione dry-run di freqtrade per confrontare la nostra logica paper con un benchmark di settore.
4. Solo dopo questi due passi, dedicare tempo alle strategie: il primo candidato da testare OOS con costi è la famiglia TSMOM classica (lookback 12M/1M, long-only) su BTC/ETH con 35 bp RT, usando DSR/PBO come già facciamo.
5. Nessuna promozione di strategia senza che l'esperimento n.1 e la baseline TSMOM siano chiusi con costi inclusi.