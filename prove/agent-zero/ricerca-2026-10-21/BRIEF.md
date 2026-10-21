# BRIEF — Ricerca soluzioni (codice e tecniche) per il progetto Denaro

## Obiettivo
Cerca in rete — GitHub, paper, blog tecnici, documentazione — le **migliori soluzioni riusabili o adattabili** al progetto. Per ciascuna: cosa fa, perché ci serve, dove si innesta, e un primo esperimento concreto. **Non implementare e non eseguire nulla**: solo raccogliere, valutare, riportare.

## Contesto (dove ci innestiamo)
- Trading crypto sistematico, Python 3.12, ccxt; exchange: OKX, Bybit, Bitvavo. Nodi Linux (mc2, MARCODG1, nuvola), systemd, pytest (~1000 test), ruff, SQLite/JSONL.
- Capitale piccolo (~1.100 EUR). **Niente HFT, niente market making di latenza.**
- Costi reali misurati dai fill: spot 10 bp, perp 5 bp (taker) → ~28-40 bp per ciclo round-trip. min_notional e rate limit contano.
- Attivi oggi: carry delta-neutral su funding (spot+perp, aperte/chiudibili, riconciliate), canary.
- Ricerca direzionale: 4 famiglie già bocciate out-of-sample (cascate, mean-reversion 7g, momentum su estremi, cointegrazione) con walk-forward, DSR, PBO. Regola del progetto: pre-registrazione, nessuna promozione senza evidenza OOS con costi inclusi.
- Paper trading: 13 bot, praticamente zero trade — problema aperto (sizing/min_notional/segnale: da capire).
- Sotto-progetto "scommessa asimmetrica": farming airdrop su Base con wallet dedicato (fase fondazione).

## Categorie da coprire (in ordine di priorità)
1. **Strategie con evidenza out-of-sample pubblica e riproducibile**: cash-and-carry/funding basis, market-neutral, trend/momentum con filtri di regime, mean-reversion su crypto, segnali da funding/open interest/liquidazioni, vol carry. Per ognuna: dati, periodo, costi, frequenza, e perché (non) dovrebbe sopravvivere al cambio exchange/regime.
2. **Architetture di bot riusabili**: separazione signal/execution/risk, idempotenza e riconciliazione ordini, dry-run/paper/live dallo stesso codice, gestione stato e crash-recovery; repo con test.
3. **Execution**: limit+reprice vs market, maker-first, TWAP/iceberg, misura dello slippage vs mid, modelli di costo/impact, gestione rate limit sui nostri exchange. Cosa vale riusare da progetti esistenti.
4. **Risk**: sizing (Kelly frazionato, vol targeting, ATR), limiti giornalieri e drawdown, kill switch, risk of ruin, portafoglio multi-strategia + correlazioni; implementazioni pronte all'uso.
5. **Validazione statistica**: DSR, PBO, purged K-fold + embargo, bootstrap, Monte Carlo, walk-forward onesto; librerie e paper di riferimento.
6. **Dati**: fonti gratuite/affidabili (OHLCV, funding, OI, liquidazioni, on-chain), API senza chiave o a basso attrito; raccoglitori robusti e loro trabocchetti (look-ahead, survivorship, cache stantie).
7. **Microstruttura crypto**: order book, imbalance, spread, sessioni; paper accessibili e riproducibili.
8. **On-chain/DeFi** (subordinato, per la scommessa): firma locale → invio → verifica, idempotenza, nonce/gas, bridge CEX→DEX, pattern di farming/claim; librerie (viem, ethers, web3.py).
9. **Tool per la ricerca quant** (screener, backtester, optimizer open source): solo se maturi e testati.

## Filtri di qualità (duri)
- Repo mantenuti (attività < 12 mesi), licenza chiara, test e documentazione.
- Niente "segnali magici", niente risultati solo in-sample, niente corsi/guru/piattaforme a pagamento.
- Ogni claim di rendimento deve dichiarare: dati, periodo, costi, OOS. In mancanza → etichetta "non verificabile" o scarto.
- Preferenza Python; altri linguaggi solo per tecniche/architetture.

## Formato di consegna (in /a0/usr/workdir/ricerca-soluzioni/)
- `REPORT.md` in italiano: per categoria, le migliori risorse. Per ciascuna: nome + URL, tipo (repo/paper/blog/doc), 2-3 righe su cosa fa, "perché ci serve / dove si innesta" (strategy | execution | risk | validation | data | infra), maturità + licenza + ultima attività, e un **primo esperimento concreto** (cosa testeremmo e come misurarlo con i nostri costi ~28-40 bp RT).
- Sezione "TOP 5 da provare subito" con motivazione.
- Sezione "scartati": una riga sul perché.
- Fonti con URL e data di consultazione; dichiarare ciò che non si è potuto verificare. Zero contenuti inventati: solo ciò che hai effettivamente visto.

## Vincoli operativi
- Solo ricerca e lettura. **Niente esecuzione di codice trovato, niente installazioni, niente chiavi/API/account, niente registrazioni o acquisti, nessuna interazione con exchange o wallet.**
- Nessun segreto nei file.
- Scrivere solo dentro `/a0/usr/workdir/ricerca-soluzioni/`.

## Chiusura
In fondo al report: "cosa consiglio di fare per primo e perché" (max 20 righe), con l'esperimento n.1 pronto da girare.