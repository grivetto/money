# Ipotesi di ricerca: Mean Reversion del Basis Spot-Perp

**Nome ipotesi**: mean_reversion_basis_BTC_ETH  
**Famiglia**: mean_reversion_basis  
**Data pre-registrazione**: 2026-10-17  

## Motivazione economica
Il basis (futures prezzo - spot prezzo) tende a tornare alla media a causa di arbitraggio e pressioni di mercato. Quando il basis si allontana significativamente dalla sua media storica, esiste un'opportunità di prendere una posizione delta-neutral (long spot / short perp se basis > media, oppure short spot / long perp se basis < media) e chiudere quando il basis returns to media. Questo edge è particolarmente rilevante nei mercati crypto dove i finanziamenti possono causare deviazioni temporanee.

## Dati richiesti
- Serie storica di basis spot-perp (calcolato come mark_price - index_price o tramite ticker) per BTC/USDT e ETH/USDT su OKX EEA.
- Prezzi spot e perpetual (mark price, index price) con timeframe adeguato (es. 1h o 5m).
- Dati point-in-time: nessun dato futuro o ricalcolato ex post.
- Per ogni osservazione registrare: timestamp, simbolo, exchange, timeframe, basis valore, mark price, index price, fonte.
- Dati mancanti: gestire tramite interpolazione o skip, ma documentare.

## Regole di ingresso/uscita
- **Ingresso**: quando |z-score(basis)| > soglia_entry (es. 2.0), dove z-score è calcolato su una finestra mobile di lookback (es. 60 osservazioni).
  - Se basis > media: apri posizione delta-neutral short basis (short perp, long spot).
  - Se basis < media: apri posizione delta-neutral long basis (long perp, short spot).
- **Uscita**: quando |z-score(basis)| < soglia_exit (es. 0.5) oppure dopo un massimo di holding period (es. 8 funding intervals).
- **Stop loss**: opzionale, basato su deviazione estrema (es. |z-score| > 4.0) per limitare perdite.

## Sizing e leva
- Capitale di riferimento: 1000 EUR.
- Leva massima: 2.0 (per entrambe le gambe).
- Margine iniziale richiesto: 5% del notional per la gamba perp.
- Size calcolato in modo da avere lo stesso notional in spot e perp (delta-neutral).
- Il notional massimo è dato da: N = (leverage_max / (1 + leverage_max)) * capitale_riferimento.

## Costi
- Commissioni: taker 0.05%, maker 0.02% (da money.costi, da confermare).
- Slippage: 0.04% per lato (da configurare).
- Funding: ricevuto/pagato ogni 8h, basato sul tasso di funding reale.
- Costi di apertura/chiusura: commissioni + slippage su entrambe le gambe.
- Costi di finanziamento: funding accrued durante il holding period.
- **Nota**: tutti i costi devono essere detratti dal PnL.

## Invalidazione
L'ipotesi è invalidata se:
- Il backtest out-of-sample mostra expectancy netta negativa dopo costi.
- Il profit factor è sotto 1.0.
- Il drawdown massimo supera il 30% del capitale di riferimento.
- Il numero di operazioni out-of-sample è inferiore a 30.
- Il t-statistic (HAC/Newey-West) è sotto 1.645 (livello di significatività 90% one-tailed).
- L'edge dipende da un singolo blocco temporale (testato con suddivisione in blocchi).

## Metriche e periodi
- **Periodi suggeriti** (da confermare con dati disponibili):
  - Train: 2024-06-01 a 2025-05-31
  - Validation: 2025-06-01 a 2025-08-31
  - OOS: 2025-09-01 a 2026-08-31
- **Benchmark obbligatori**:
  - Buy&hold BTC
  - Buy&hold ETH
  - Esposizione zero
  - Strategia casuale con stessi costi/turnover
  - Versione senza segnale principale (ingresso/uscita casuale)
  - Versione con costi raddoppiati
- **Cancello statistico**:
  - ≥30 operazioni OOS
  - Expectancy netta positiva
  - Limite inferiore CI > 0 (bootstrap o HAC)
  - t-statistic sufficiente (HAC/Newey-West quando serve)
  - Profit factor > soglia (da definire, es. 1.2)
  - Drawdown massimo < soglia (es. 0.25)
  - Costi coperti dall'edge
  - Indipendenza da singolo blocco temporale
  - Stabilità su più regimi (controllo via analisi di regime)
  - DSR, PBO/CSCV se calcolabile

## Note
- Questa ipotesi è pre-registrata prima di ogni analisi o backtest.
- Ogni modifica alle soglie dopo aver visto i risultati richiede una nuova ipotesi e incremento del conteggio dei tentativi.
- Il bot resterà in paper/dry-run finché non esiste edge OOS con fee e slippage.
