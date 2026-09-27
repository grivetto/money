# P4 — Funding carry su swap (raccolta dati + misura)
STATO: LIBERA
DATI: funding pubblico OKX (endpoint fetch_funding_rate_history verificato 2026-09-27)

## Ipotesi
I perp su OKX pagano funding storicamente positivo (i long pagano gli short nei regimi toro).
Strategia delta-neutrale: short perp + long spot a pari nozionale = raccolta del funding
senza rischio direzionale. E' la sola famiglia del progetto con rendimento NON direzionale.
Costo: swap taker/maker 0,07% giro (7,9x meno dello spot) + costo di ribilanciamento.

## PRIMA FASE: solo dati
1. Scaricare la storia funding di BTC/USDT:USDT ed ETH/USDT:USDT (ogni 8h) dal 2024-01-01.
2. Misurare: funding medio annualizzato, % di periodi positivi, peggiori periodi negativi.
3. Solo SE la media annualizzata > 8% (dopo il giro di entrata/uscita) si passa alla
   seconda fase (simulazione con mark price e ribilanciamenti). Altrimenti archivio subito.

## Regole se si procede
- Entrata quando funding medio 3 periodi > soglia; uscita quando < 0 per 2 periodi.
- maxDD da funding negativo prolungato; margine: leva 1x, mai oltre.
- Rischio dichiarato: liquidazione (mitigata da leva 1x + margine isolato) e funding negativo.

## Nota
Questa famiglia richiede derivati: la promozione aprirebbe il conto swap (doc 05 gia'
scritto: cap 1x, sub-account separato). NON si tocca niente di live senza via libera.
