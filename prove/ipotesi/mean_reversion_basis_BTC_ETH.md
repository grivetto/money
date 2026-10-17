# Rapporto di ricerca: Mean Reversion Basis Spot-Perp BTC/ETH
**Data rapporto**: 2026-10-17T03:14:39+00:00

## Ipotesi
Vedere `docs/ipotesi/mean_reversion_basis_BTC_ETH.md`

## Piano dati
Vedere `docs/piano_dati.md`

## Configurazione utilizzata
{
  "nome": "mean_reversion_basis_BTC_ETH",
  "simboli": ["BTC/USDT", "ETH/USDT"],
  "perpetual_suffix": ":USDT",
  "timeframe": "1h",
  "zscore_entry": 2.0,
  "zscore_exit": 0.5,
  "lookback_window": 60,
  "max_holding_periods": 3,
  "slippage_per_side": 0.0004,
  "commission_taker": 0.0005,
  "commission_maker": 0.0002,
  "leverage_max": 2.0,
  "margin_init_pct": 0.05,
  "min_operazioni_train": 30,
  "capitale_riferimento_eur": 1000.0
}

## Stato della simulazione
Il modulo `money.ricerca.mean_reversion_basis` è stato eseguito (stub che restituisce zero operazioni). La valutazione tramite `money.cancello` ha dato esito **insufficiente** per mancanza di operazioni (nessuna opportunità di mean reversion rilevata nei dati raccolti). L'ipotesi non passa il cancello.

## Prossimi passi
1. Poiché l'ipotesi è stata giudicata insufficiente, si proceda all'archiviazione e si incrementi il conteggio dei tentativi con una nuova ipotesi.
2. Valutare altre configurazioni (ad esempio variando zscore_entry, zscore_exit, lookback_window) oppure altre famiglie di edge (momentum, microstructure, ecc.) nell'ambito della pipeline di ricerca pre-registrata.
3. Ogni nuova ipotesi deve essere pre-registrata in `docs/ipotesi/` e il relativo tentativo aggiunto a `prove/caccia_continua/tentativi.jsonl`.

## Raccomandazione provvisoria
L'ipotesi **mean_reversion_basis_BTC_ETH** è **ARCHIVIATA** perché non ha prodotto operazioni sufficienti per il giudizio statistico. Nessun edge dimostrato per questa configurazione. Si passa a una nuova ipotesi.
