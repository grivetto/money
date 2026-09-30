# P10 — Momentum cross-sectional long/flat (rotazione top-k)
STATO: DA PRENDERE — assegnata a dsh via canale (2026-09-30)
DATI: USDT-lungo (2020-10-01 -> 2026-09-25; confine addestramento 2024-06-01)

## Ipotesi
Il momentum **relativo** (ranking tra i 10 majors) riduce la dipendenza da un singolo asset
e cattura i cicli di forza relativa, restando long/flat (mai short) e con turnover
controllato. È un taglio DIVERSO dal trend a canale (selezione tra strumenti, non timing del
singolo): nessuna delle 13+ famiglie archiviate misura questo meccanismo.
(Review esterna Manus 30/09: "più interessante del momentum su singolo asset", a patto di
tenere poche posizioni e cap di correlazione a capitale piccolo.)

## Meccanica (anti-lookahead per costruzione)
- Ranking: alla chiusura della barra `i`, per ogni simbolo `r = chiusura(i)/chiusura(i-L) - 1`
  (solo passato). Selezione dei migliori `k`.
- Ribilanciamento ogni `R` barre (alla chiusura): composizione target = top-`k` per `r`.
- Esecuzione: SOLO i cambi di composizione all'apertura della barra successiva (vendita
  degli usciti, acquisto degli entrati). Chi è già in paniere e resta NON viene toccato
  (niente churn artificiale).
- Allocazione: equity / k per posizione (equipesate, dichiarato) — **richiede l'hook
  `esposizione_per_op` del motore di portafoglio** (già presente, commit e6ff1c7f).
- Costi: `money.costi` — okx_eea_spot misto + slippage 4 bp per lato (come donchian);
  scenario secondario okx_eea_con_perp. Nessuna leva, cassa vincolante, mai short.
- Con meno di k candidati validi si tengono i disponibili; con 0 candidati si è flat.

## Griglia (dichiarata, 8 varianti) — PRIMA dei numeri
`{k: 2, 3}` × `{L: 60, 120}` × `{R: 7, 14}` = **8 configurazioni**, tutte provate SULL'ADDESTRAMENTO
(2020-10-01 -> 2024-06-01) sul motore di portafoglio (DD mark-to-market).
Selezione: miglior rapporto `expectancy_netta / dd_portafoglio` in addestramento; si riportano
TUTTE le 8 righe. Poi UNA verifica sola sul periodo 2024-06-01 -> 2026-09-25 con la config
scelta (la verifica NON si usa per scegliere).

## Criterio di successo / verdetto
- Verdetto col cancello (8 criteri) sulla finestra di verifica + confronto tariffe.
- Metriche secondarie fisse: DD di portafoglio mark-to-market, eseguiti/saltati (cassa),
  esposizione aggregata massima.
- Se archivia: si archivia, niente "quasi". Artefatti: `prove/P10_*.{txt,json}`.

## Deliverable (handoff dsh → hermes, come P2)
- `src/money/ricerca/momentum_cross.py` (motore) + `tests/ricerca/test_momentum_cross.py`
  (anti-lookahead, timing di ribilanciamento, applicazione costi, mai short, tenuta dei
  simboli già in paniere, caso 0 candidati).
- `scripts/misura_p10.py` (griglia dichiarata + selezione su addestramento + verifica +
  cancello + artefatti).
- `MANIFEST` sha256 dei file + nota metodologica nel file di canale.

## Nota
L'handoff va in `hermes_bridge/dsh/handoff/P10/`; Hermes verifica (manifest), integra e
misura — stesso flusso di P2, che ha funzionato.
