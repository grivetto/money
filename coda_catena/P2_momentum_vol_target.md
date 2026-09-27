# P2 — Momentum assoluto con position sizing a volatilita' (vol targeting)
STATO: LIBERA
DATI: USDT-lungo (2019-01-01 -> oggi; confine 2024-06-01)

## Ipotesi
Il nodo L (momentum assoluto 60g) ha +2,61% netto e DD 57%: la scommessa e' che il DD veniva
dai tratti ad alta volatilita' in cui la posizione era sempre piena. Regola: dentro/fuori
come L (long se ritorno 60g > 0), ma l'esposizione di OGNI operazione e'
`min(1, vol_target / vol_realizzata_20g)`, vol_target = 60% annualizzata. Nei backtest il
ritorno per operazione si scala per il fattore di esposizione.

## Meccanica
- Segnale: ritorno 60g > 0 alla chiusura di i -> lungo all'apertura di i+1 (come L).
- Sizing per operazione: f = min(1.0, 0.60 / (sigma20 * sqrt(365))), sigma20 = dev std dei
  rendimenti giornalieri FINO a i (solo passato).
- Ritorno lordo dell'operazione = f * (prezzo_uscita/prezzo_ingresso - 1). Il pedaggio si
  paga sul nozionale IMPEGNATO (f * posizione): attenzione a scalare anche quello.
- Una posizione alla volta per simbolo.

## Griglia (dichiarata, 4 config)
lookback in {60, 90} x vol_target in {0.50, 0.60}

## Universo: come P1.

## Note
- La metrica che conta: maxDD del nodo vs quello di L sulla stessa finestra. Se non scende
  sotto il 25% la famiglia si archivia.
