# P4 — Funding carry su swap (raccolta dati + misura)
STATO: IN ACCUMULO (con P8) — storia funding in raccolta dal 03/07; misura formale quando la
storia raggiunge ~30 osservazioni indipendenti (regola di maturita' dichiarata). Nel frattempo
il canary C1 (docs/16, review 15/10) valida l'esecuzione reale spot+perp a taglia minima.
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

## Formato-contratto (retrofit 2026-10-06; contenuto scientifico sopra invariato)
- **Obiettivo**: decidere se il carry funding (short perp + long spot, delta-neutrale) merita
  capitale, con numeri netti ai costi reali del conto; oggi in accumulo dati con P8.
- **Repo/commit**: repo `grivetto/money`, retrofit al commit `e996d336` (06/10/2026); la
  misura e gli artefatti si registrano in `prove/REGISTRO_ESPERIMENTI.md`.
- **Input**: serie funding per simbolo da `data/funding_xperp.jsonl` (raccolta P8, cron 4h) +
  specifiche strumenti X-Perp (contract size, minimi, fee). **Output**: verdetto del cancello
  (promosso / archiviato / insufficiente) sul paniere carry, con payback per simbolo.
- **Test falsificabile**: un test che fallisce senza l'implementazione — con funding sintetico
  noto a zero per tutti i periodi il netto atteso del carry DEVE risultare <= 0 (assert: il
  criterio di uccisione scatta e il verdetto e' `archiviato`).
- **Criteri di accettazione**:
  - [ ] netto annualizzato per simbolo >= soglia dichiarata PRIMA della misura (costi di
        ciclo reali inclusi, addendum contabile P12);
  - [ ] regola di regime valutata al netto dei cicli per episodio (lezione P12);
  - [ ] verifica su finestra mai usata per la selezione.
- **Fuori scope**: nessun ordine live (il canary C1 e' gia' autorizzato e tracciato a parte);
  non modificare i moduli della catena spot; nessuna leva oltre 1x.
- **Procedura di verifica**:
```bash
# raccolta in corso (cron ogni 4h) — stato:
tail -5 logs/raccolta_funding.log
# rigenerare la tabella funding:
python -c "from money.report_funding import *"  # vedi tests/test_report_funding.py
python -m pytest tests/test_raccoglitore_funding.py tests/test_report_funding.py -q
```
