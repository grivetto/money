# Ipotesi di ricerca: Momentum Intraday Condizionato da Volume e Volatilità

**Nome ipotesi**: intraday_momentum_volume_vol_BTC_ETH  
**Famiglia**: intraday_momentum_volume_vol  
**Data pre-registrazione**: 2026-10-17  

## Motivazione economica
Nei mercati crypto, gli spostamenti intraday spesso sono accompagnati da aumenti di volume e volatilità. Quando si osserva un aumento significativo del volume relativo alla media recente, seguito da un movimento di prezzo coerente, può indicare l'inizio di un trend intraday sostenibile. Allo stesso modo, un aumento di volume con movimento di prezzo debole o contrario può segnalare esaurimento e opportunità di reversal. Condizionare l'ingresso su entrambi volume e volatilità permette di filtrare falsi segnali e concentrarsi su movimenti con vera partecipazione di mercato.

## Dati richiesti
- OHLCV intraday (timeframe adeguato, es. 5m o 15m) per BTC/USDT e ETH/USDT su OKX EEA.
- Campi: timestamp, open, high, low, close, volume.
- Dati point-in-time: nessun dato futuro o ricalcolato ex post.
- Per ogni osservazione registrare: timestamp, simbolo, exchange, timeframe, OHLCV, fonte.
- Dati mancanti: gestire tramite skip o interpolazione, ma documentare.

## Regole di ingresso/uscita (esempio di configurazione da testare)
- **Indicatori**:
  - Media mobile del volume su 20 periodi (vol_ma20).
  - Range vero medio (ATR) su 14 periodi come misura di volatilità.
  - Cambiamento di prezzo percentuale sull'ultima chiusura (returns).
- **Ingresso long**:
  - volume > vol_ma20 * soglia_volume_entry (es. 2.0)
  - ATR > ATR_ma * soglia_vol_entry (es. 1.2)  [opzionale, per confermare volatilità]
  - returns > 0 (movimento rialzista nell'ultimo periodo)
- **Ingresso short** (simmetrico per ribassista):
  - volume > vol_ma20 * soglia_volume_entry
  - ATR > ATR_ma * soglia_vol_entry
  - returns < 0
- **Uscita**: dopo un numero fisso di periodi (es. 4 periodi di timeframe) oppure quando si verifica una condizione di逆转 (es. volume spike in direzione opposta).
- **Stop loss**: basato su ATR (es. 2 * ATR dall'ingresso) per limitare perdite.
- Nota: questa è solo una configurazione di esempio; la pre-registrazione deve specificare i parametri esatti da testare.

## Sizing e leva
- Capitale di riferimento: 1000 EUR.
- Leva massima: 2.0.
- Margine iniziale richiesto: 5% del notional.
- Size calcolato in base al capitale e alla leva, con rischio per trade limitato (es. 1% del capitale).

## Costi
- Commissioni: taker 0.05%, maker 0.02% (da money.costi).
- Slippage: 0.04% per lato (da configurare, potrebbe essere più alto per timeframe bassi).
- Costi di apertura/chiusura: commissioni + slippage.
- Costi di finanziamento: rilevanti se si tiene posizione overnight, ma per intraday generalmente trascurabili.
- **Nota**: tutti i costi devono essere detratti dal PnL.

## Invalidazione
L'ipotesi è invalidata se:
- Il backtest out-of-sample mostra expectancy netta negativa dopo costi.
- Il profit factor è sotto 1.0.
- Il drawdown massimo supera il 25% del capitale di riferimento.
- Il numero di operazioni out-of-sample è inferiore a 30.
- Il t-statistic (HAC/Newey-West) è sotto 1.645 (livello di significatività 90% one-tailed).
- L'edge dipende da un singolo blocco temporale (testato con suddivisione in blocchi).

## Metriche e periodi
- **Periodi suggeriti**:
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
