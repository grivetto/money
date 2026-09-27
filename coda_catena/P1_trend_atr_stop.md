# P1 — Trend giornaliero con trailing stop ATR
STATO: PRESA_DA hermes 2026-09-27
DATI: USDT-lungo (2019-01-01 -> oggi; confine 2024-06-01)

## Ipotesi
Il pattern trasversale dei 12 nodi: le famiglie trend hanno expectancy NETTA positiva a fee
spot (+2,1% Donchian, +2,6% momentum assoluto) ma DD 48-57% e edge concentrato nel blocco
toro. La domanda: un trailing stop ATR taglia il DD senza uccidere l'expectancy? Se si', e'
la prima promozione del progetto.

## Meccanica (precisa, niente ambiguita')
- Entrata: chiusura(i) > max(massimi[i-40 .. i-1])  -> compro all'apertura di i+1.
- Stop: trailing = max(massimo_storico_posizione - k * ATR14(i), stop_precedente)
  con k in griglia; ATR di Wilder su TR. Lo stop si valuta INTRADAY sul minimo della barra;
  se la barra APRE sotto lo stop si esce all'apertura (gap = caso peggiore, mai allo stop).
- Uscita unica: lo stop. Niente uscita a canale opposto (era lei a lasciare correre i DD).
- Una posizione alla volta per simbolo; rientro permesso subito dopo uno stop.
- Anti-look-ahead: canale e ATR fino a i, esecuzione a i+1.

## Griglia (dichiarata, 6 config)
k in {2.0, 2.5, 3.0} x canale in {20, 40}

## Universo
BTC/USDT, ETH/USDT + le major USDT con copertura >= 95% dal 2019-01-01
(ADA, DOGE, LTC, LINK se coprono; la verifica di copertura decide, non noi).

## Note
- Confronto obbligatorio contro il nodo I (Donchian puro) sulla STESSA finestra: la tesi e'
  "stesso edge, meta' DD". Se il DD non scende sotto 25% e l'expectancy resta >= 3x pedaggio,
  il nodo si archivia come gli altri.
- Il verdetto finale si rifa' sulle EUR prima di qualunque promozione.
