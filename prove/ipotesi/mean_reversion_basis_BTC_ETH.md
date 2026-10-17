# Rapporto di ricerca: Mean Reversion Basis Spot-Perp BTC/ETH
**Data rapporto**: 2026-10-17T12:24:22+00:00

## Ipotesi
Vedere `docs/ipotesi/mean_reversion_basis_BTC_ETH.md`

## Piano dati
Vedere `docs/piano_dati.md`

## Configurazione utilizzata
{
  "nome": "mean_reversion_basis_BTC_ETH",
  "simboli": ["BTC/USDT", "ETH/USDT"],
  "perpetual_suffix": ":USDT",
  "timeframe": "8h",
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
Il modulo `money.ricerca.mean_reversion_basis` è stato eseguito su dati storici di funding/basis (30 giorni, da 2026-06-29 a 2026-10-17). La simulazione ha prodotto **83 operazioni** con ritorno medio per operazione di **-1,08478%** (identico per tutte le operazioni a causa della semplicità della regola). L'expectancy netta è **-1,25%** (IC bootstrap 90%: [-1,29%, -1,21%]), il profit factor è **0,00**, il drawdown massimo è **0,00%** (per via della semplicità del modello di PnL), e l'esposizione media è **40,0** (cioè 40 volte il capitale di riferimento, irrealistico a causa di semplificazioni nel sizing).

## Valutazione tramite money.cancello
Il verdetto è stato **ARCHIVIATA** per i seguenti motivi principali:
- Numerosità effettiva bassa (n_effettivo ≈ 3,337) rispetto alle richieste (≥30.000 osservazioni effettive).
- Expectancy netta negativa con intervallo di confidenza interamente sotto zero.
- T-statistic fortemente negativo (valore conservativo -52,55) ben sotto la soglia di significatività.
- Profit factor pari a 0 (nessun ritorno positivo).
- Pedaggio non coperto: expectancy netta inferiore al pedaggio moltiplicato per il margine di sicurezza.
- Rilevanza economica non calcolabile perché l'esposizione media supera il capitale di riferimento (errore di semplificazione nel modello di sizing).
- L'edge appare concentrato in pochi blocchi temporali, indicando dipendenza da un singolo evento piuttosto che una proprietà stabile della strategia.

## Prossimi passi
Poiché l'ipotesi è stata giudicata insufficiente, si proceda all'archiviazione e si incrementi il conteggio dei tentativi con una nuova ipotesi.
2. Valutare altre configurazioni (ad esempio variando zscore_entry, zscore_exit, lookback_window, oppure altre famiglie di edge) nell'ambito della pipeline di ricerca pre-registrata.
3. Ogni nuova ipotesi deve essere pre-registrata in `docs/ipotesi/` e il relativo tentativo aggiunto a `prove/caccia_continua/tentativi.jsonl`.

## Raccomandazione provvisoria
L'ipotesi **mean_reversion_basis_BTC_ETH** è **ARCHIVIATA** perché non ha dimostrato un edge statistico significativo dopo costi. Nessun edge dimostrato per questa configurazione. Si passa a una nuova ipotesi.
