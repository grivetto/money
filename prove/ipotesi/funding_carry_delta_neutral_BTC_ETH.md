# Rapporto di ricerca: Funding/Carry Delta-Neutral BTC/ETH
**Data rapporto**: 2026-10-17T01:39:54+00:00

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
Il modulo `money.ricerca.carry_delta_neutral` è stato eseguito (stub che restituisce zero operazioni). La valutazione tramite `money.cancello` ha dato esito **insufficiente** per mancanza di operazioni (nessuna opportunità di carry rilevata nei dati raccolti). L'ipotesi non passa il cancello.

## Prossimi passi
1. Poiché l'ipotesi è stata giudicata insufficiente, si proceda all'archiviazione e si incrementi il conteggio dei tentativi con una nuova ipotesi.
2. Valutare altre configurazioni (ad esempio variando basis_entry_bps, basis_exit_bps, delta_threshold_pct) oppure altre famiglie di edge (mean reversion basis, momentum, ecc.) nell'ambito della pipeline di ricerca pre-registrata.
3. Ogni nuova ipotesi deve essere pre-registrata in `docs/ipotesi/` e il relativo tentativo aggiunto a `prove/caccia_continua/tentativi.jsonl`.

## Raccomandazione provvisoria
L'ipotesi **funding_carry_delta_neutral_BTC_ETH** è **ARCHIVIATA** perché non ha prodotto operazioni sufficienti per il giudizio statistico. Nessun edge dimostrato per questa configurazione. Si passa a una nuova ipotesi.
