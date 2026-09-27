# P1 — Trend giornaliero con trailing stop ATR
STATO: FATTA, ARCHIVIATA (hermes) 2026-09-27
ESITO: ipotesi SMENTITA. Il chandelier peggiora tutto: DD 55,6% (vs 47,0% del Donchian puro),
expectancy -1,07% (vs +7,99%). L'uscita per stop e' la leva sbagliata per domare il DD.
CONTROPROVA: Donchian puro sulla stessa finestra USDT -> 6/8 criteri PASSATI (IC90 positivo
per la prima volta, copertura 14,5x, PF 1,97, EUR/anno +474), bocciato solo da t=1,620<1,650
e DD 47%>25%. La strada e' il controllo dell'ESPOSIZIONE (P2/P3), non dell'uscita.
DATI: USDT-lungo (2020-10-01 -> oggi; confine 2024-06-01)
# Correzione 2026-09-27 (Hermes): l'EEA serve gli alt/USDT solo dal ~2020-06; a 2019-01
# risponde vuoto. Finestra spostata al primo istante in cui l'universo e' COMPLETO (10/10).
# Verifica INVARIATA (2024-06-01 -> 2026-09-25). Run-pilota BTC/ETH-2019 in prove/.

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
