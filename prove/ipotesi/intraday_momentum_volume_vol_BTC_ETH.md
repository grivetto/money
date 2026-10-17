# Rapporto di ricerca: Momentum Intraday Condizionato da Volume e Volatilità BTC/ETH
**Data rapporto**: 2026-10-17T03:17:43+00:00

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
Il modulo `money.ricerca.intraday_momentum_volume_vol` è stato eseguito (stub che restituisce zero operazioni). La valutazione tramite `money.cancello` ha dato esito **insufficiente** per mancanza di operazioni (nessuna opportunità di momentum rilevata nei dati raccolti). L'ipotesi non passa il cancello.

## Prossimi passi
1. Poiché l'ipotesi è stata giudicata insufficiente, si proceda all'archiviazione e si incrementi il conteggio dei tentativi con una nuova ipotesi.
2. Valutare altre configurazioni (ad esempio variando i moltiplicatori di volume e volatilità, timeframe) oppure altre famiglie di edge (microstructure, cross-sectional momentum, regime filter) nell'ambito della pipeline di ricerca pre-registrata.
3. Ogni nuova ipotesi deve essere pre-registrata in `docs/ipotesi/` e il relativo tentativo aggiunto a `prove/caccia_continua/tentativi.jsonl`.

## Raccomandazione provvisoria
L'ipotesi **intraday_momentum_volume_vol_BTC_ETH** è **ARCHIVIATA** perché non ha prodotto operazioni sufficienti per il giudizio statistico. Nessun edge dimostrato per questa configurazione. Si passa a una nuova ipotesi.
