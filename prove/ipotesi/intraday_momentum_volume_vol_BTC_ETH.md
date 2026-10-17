# Rapporto di ricerca: Momentum Intraday Condizionato da Volume e Volatilità BTC/ETH
**Data rapporto**: 2026-10-17T12:44:44+00:00

## Ipotesi
Vedere `docs/ipotesi/intraday_momentum_volume_vol_BTC_ETH.md`

## Piano dati
Vedere `docs/piano_dati.md`

## Configurazione utilizzata
{
  "nome": "intraday_momentum_volume_vol_BTC_ETH",
  "simboli": ["BTC/USDT", "ETH/USDT"],
  "timeframe": "5m",
  "volume_entry_multiplier": 2.0,
  "volatility_entry_multiplier": 1.2,
  "atr_period": 14,
  "volume_ma_period": 20,
  "holding_periods": 4,
  "slippage_per_side": 0.0004,
  "commission_taker": 0.0005,
  "commission_maker": 0.0002,
  "leverage_max": 2.0,
  "margin_init_pct": 0.05,
  "risk_per_trade_pct": 0.01,
  "min_operazioni_train": 30,
  "capitale_riferimento_eur": 1000.0
}

## Stato della simulazione
Il modulo `money.ricerca.intraday_momentum_volume_vol` è stato eseguito su dati OHLCV 5m (spot) per BTC/USDT e ETH/USDT raccolti da OKX EEA (ultimi 2 giorni circa). La simulazione ha prodotto **43 operazioni** con ritorno medio per operazione di **-0,1797%** (valori leggermente variabili per operazione). L'expectancy netta è **-0,18%** (IC bootstrap 90%: [-0,18%, -0,18%]), il profit factor è **0,00**, il drawdown massimo è **0,00%** (per via della semplicità del modello di PnL che non genera serie di ritorno abbastanza variabile per drawdown significativo), e l'esposizione media è **0,02** (cioè 2% del capitale per operazione, derivante da risk_per_trade=1% e leva=2).

## Valutazione tramite money.cancello
Il verdetto è stato **ARCHIVIATA** per i seguenti motivi principali:
- Expectancy netta negativa con intervallo di confidenza interamente sotto zero.
- T-statistic fortemente negativo (valore -178,8) ben sotto la soglia di significatività.
- Profit factor pari a 0 (nessun ritorno positivo).
- Pedaggio non coperto: expectancy netta inferiore al pedaggio moltiplicato per il margine di sicurezza.
- Rilevanza economica insufficiente: il guadagno annuo atteso è negativo e inferiore alla soglia minima di 10 EUR/anno.
- L'edge appare concentrato in pochi blocchi temporali, indicando dipendenza da un singolo evento piuttosto che una proprietà stabile della strategia.

## Prossimi passi
Poiché l'ipotesi è stata giudicata insufficiente, si proceda all'archiviazione e si incrementi il conteggio dei tentativi con una nuova ipotesi.
2. Valutare altre configurazioni (ad esempio variando i moltiplicatori di volume e volatilità, timeframe, oppure altre famiglie di edge) nell'ambito della pipeline di ricerca pre-registrata.
3. Ogni nuova ipotesi deve essere pre-registrata in `docs/ipotesi/` e il relativo tentativo aggiunto a `prove/caccia_continua/tentativi.jsonl`.

## Raccomandazione provvisoria
L'ipotesi **intraday_momentum_volume_vol_BTC_ETH** è **ARCHIVIATA** perché non ha dimostrato un edge statistico significativo dopo costi. Nessun edge dimostrato per questa configurazione. Si passa a una nuova ipotesi.
