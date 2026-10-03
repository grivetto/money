# P14 — Momentum cross-sectional su universo ampio
STATO: **pre-registrata 2026-10-03** (voce nel REGISTRO PRIMA dei numeri). Seguito dichiarato di P10 («insufficiente»: 23 op < 30). Implementazione ad A0-MC2 (handoff); misura ufficiale Hermes.
DATI: USDT-lungo [2020-10-01 -> 2026-09-25], confine addestramento 2024-06-01 (identici a P10).

## Perché (dichiarato prima)
P10 (top-k su 10 major) è «insufficiente» per numerosità: l'OOS ha prodotto solo 23 operazioni.
La domanda di P14: **il momentum cross-sectional regge con più campioni?** Ampliando l'universo
(tutte le coppie con copertura >=95%, selettore `money.ricerca.universo` come in P5) il numero
di operazioni cresce e il campione acquista potenza. Se l'edge è dei soli major, si vedrà
(P5 docet: l'allargamento uccise il Donchian) — il verdetto è comunque vincolante.

## Meccanica
Identica a P10 (`src/money/ricerca/momentum_cross.py`, nessuna modifica al motore):
ranking alla chiusura di `i` su `r = c(i)/c(i-L)-1` (solo passato); ribilanciamento ogni `R`
barre alla chiusura; esecuzione dei SOLI cambi di composizione all'apertura successiva
(vendita usciti, acquisto entrati; chi resta in paniere non viene toccato); equipesate
`equity/k`; mai short; cassa vincolante. Con <k candidati validi si tengono i disponibili;
con 0 candidati si è flat.

## Griglia dichiarata (8 varianti) — PRIMA dei numeri
`{k: 3, 5} × {L: 60, 120} × {R: 7, 14}` — tutte provate SULL'ADDESTRAMENTO sul motore di
portafoglio (DD mark-to-market). Selezione: miglior rapporto `expectancy_netta / dd_portafoglio`
in addestramento (n >= 30 operazioni di training per la candidabilità).
**Riga di riferimento (NON selezionabile)**: la config scelta in P10 (k=2, L=120, R=14)
valutata sullo stesso universo ampio — solo confronto, fuori dalla selezione.
Poi UNA verifica sola OOS [2024-06-01 -> 2026-09-25] con la config scelta.

## Costi (dichiarati)
- Primari: `okx_eea_spot` misto + slippage 4 bp/lato (identici a P10).
- Secondari: scenario `okx_eea_con_perp`.
- Stress: slippage ×2 (l'universo ampio include coppie più sottili) — criterio aggiuntivo di
  robustezza dichiarato PRIMA: un candidato serio deve reggere anche lo scenario stressato.

## Criterio di successo / verdetto
- Cancello (8 criteri) sulla finestra di verifica + confronto tariffe.
- Metriche secondarie fisse: DD di portafoglio mark-to-market, eseguiti/saltati (cassa),
  esposizione aggregata massima, n. simboli effettivamente presenti nell'universo.
- Artefatti: `prove/P14_momentum_universo.*` (txt + json).

## Deliverable (handoff A0-MC2 → hermes)
- `scripts/misura_p14.py` — runner adattato da `scripts/misura_p10.py` (riferimenti nel workdir):
  universo via selettore (come `scripts/misura_p5.py`), griglia P14, riga di riferimento
  non selezionabile, artefatti `prove/P14_*`.
- `tests/test_misura_p14.py` — test OFFLINE delle funzioni pure del runner su dati sintetici
  (dichiarazione griglia, selezione, costruzione righe artefatto); niente rete nei test.
- `NOTE.md` con comando di verifica ed esito REALE; MANIFEST sha256 (protocollo di consegna).

## Nota
Il risultato NON modifica P10 (che resta «insufficiente» nel registro). Se P14 archivia, il
filone momentum cross si chiude con potenza adeguata; se promuove, si apre il percorso di
deploy (banco → canary) come da regole.
