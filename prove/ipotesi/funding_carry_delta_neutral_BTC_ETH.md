# Rapporto di ricerca: Funding/Carry Delta-Neutral BTC/ETH
**Data rapporto**: 2026-10-17T03:09:02.265644

## Ipotesi
Vedere `docs/ipotesi/funding_carry_delta_neutral.md`

## Piano dati
Vedere `docs/piano_dati.md`

## Configurazione utilizzata
{
  "nome": "funding_carry_delta_neutral_BTC_ETH",
  "basis_entry_bps": 5.0,
  "basis_exit_bps": 20.0,
  "delta_threshold_pct": 10.0,
  "slippage_per_side": 0.0004,
  "commission_taker": 0.0005,
  "commission_maker": 0.0002,
  "leverage_max": 2.0,
  "margin_init_pct": 0.05,
  "min_operazioni_train": 30,
  "capitale_riferimento_eur": 1000.0
}

## Stato della simulazione
Il modulo `money.ricerca.carry_delta_neutral` è stato creato ma la funzione di simulazione `simula_carry_delta_neutral` solleva `NotImplementedError` in attesa di integrazione dei dati mark/index (necessari per calcolare il basis).

## Prossimi passi
1. Estrarre mark e index price dallo stesso feed funding (o da ticker) e arricchire il file `data/funding_xperp.jsonl`.
2. Completare la funzione di simulazione con logica di apertura, chiusura, riequilibrio e calcolo PnL.
3. Eseguire il backtest sui periodi train/validation/OOS definiti.
4. Valutare le metriche di successo tramite `money.cancello`.
5. Se l'ipotesi passa il cancello, passare a paper trading; altrimenti archiviare.

## Raccomandazione provvisoria
Poiché non è stato ancora possibile eseguire la simulazione completa, l'ipotesi rimane in stato **INSUFFICIENTE** (dati non sufficienti). Nessun edge dimostrato.
