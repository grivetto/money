# P6 — Livello PORTAFOGLIO: cap di concorrenza e correlazione
STATO: PRESA_DA hermes (2026-09-30)
DATI: USDT-lungo (2020-10-01 -> 2026-09-25; confine addestramento 2024-06-01)

## Ipotesi (evidenza da P2, 30/09)
P2 ha mostrato che il vol targeting riduce il DD *serializzato* (47,0% → 37,6%) ma NON il DD
di portafoglio mark-to-market (42,8% → 41,7-47,5%). Lettura: il DD nasce dalla **concorrenza
di posizioni correlate**, non dalla size del singolo trade. Attacco conseguente: limitare la
concorrenza (cap di posizioni) e la correlazione accettata contemporaneamente.

## Meccanica
- Segnale FISSO: Donchian 55/20 sui 10 majors (come P2; il segnale NON si tocca).
  Allocazione base 0.25 x equity per operazione; cassa vincolante; nessuna leva.
- Variante **fifo**: `max_posizioni` ∈ {2, 3, 4}; un segnale che arriva a slot pieni è
  SALTATO e contato (comportamento già nel motore `portafoglio.py`).
- Variante **mincorr**: come fifo, ma un nuovo ingresso è **rifiutato** se la correlazione
  a 60 barre dei rendimenti giornalieri con una qualunque posizione aperta supera
  **τ = 0,75** (dichiarato). Il check usa SOLO dati fino alla barra di decisione.
  Richiede un hook di filtro-ingresso nel motore (lo aggiunge la misura, con test).

## Griglia (dichiarata, 6 varianti) — PRIMA dei numeri
`{max_posizioni: 2, 3, 4}` × `{selezione: fifo, mincorr}` = **6 configurazioni**.
Controllo interno: la configurazione P2 "sizing no" (nessun cap) = DDport 42,84%.

## Metriche e criterio di successo
- Primaria: **DD di portafoglio mark-to-market** (motore `backtest_portafoglio`).
- Successo: DDport ≤ 25% E expectancy ≥ 3× pedaggio — stessa regola di P2, finestra VERIFICA.
- Secondarie obbligatorie: EUR/anno (i cap riducono le operazioni eseguite: va letto),
  conteggio eseguiti/saltati, esposizione aggregata massima, posizioni concorrenti massime,
  t-stat. Artefatti: `prove/P6_portafoglio.{txt,json}`.

## Nota dichiarata
Se anche P6 fallisce, il filone trend-cash-solo non è investibile a questo capitale e si
archivia **per costruzione** (regola P2). Si prosegue con le famiglie nuove (P10 in misura,
poi quelle su funding/basis quando i dati ci saranno).

---

## Esito (30/09/2026, POST-numeri — sola registrazione, niente sopra è stato toccato)
**ARCHIVIATA per costruzione.** Nessuna delle 6 configurazioni dichiarate soddisfa
DDport ≤ 25% E exp ≥ 3× pedaggio (finestra VERIFICA):
- migliore per DD: `mp=2 fifo` → dd_port 37,8% (controllo 42,8%), ma expectancy del
  campione eseguito **negativa** (-4,6%, t -1,03);
- `mincorr` riduce il DD *serializzato* (fino a 19,6%) ma il DD di portafoglio resta
  38,4-42,3%; con mp≥3 il cap non viene nemmeno raggiunto (il filtro rifiuta prima);
- controllo interno: OK (riproduce il riferimento P2).
Numeri completi: `prove/P6_portafoglio.{txt,json}`; registro: `prove/REGISTRO_ESPERIMENTI.md`.
