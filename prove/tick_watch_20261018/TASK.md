# TASK — Watchdog della raccolta tick: tick_watch.py (ripetibile) + report

Sei un operaio del progetto "money". Devi produrre uno script RIPETIBILE di sorveglianza della raccolta tick e il report del run di oggi. Lavora SOLO dentro ~/agy-scratch/tick-watch/ (crea la directory).

## Contesto
Su questo nodo, ~/money/data/tick/ contiene file `DOGEUSDT_YYYY-MM-DD.csv.gz` (tick trade-level, raccolta automatica). Un preflight del 17/10 ha verificato i file 13-16/10 (tutto sano, 12 gap >60s). Ora serve un CHECK RIPETIBILE, eseguibile ogni giorno da cron, che dica subito se la raccolta e' viva e sana: senza watchdog, una raccolta ferma resterebbe invisibile per settimane.

## Cosa produrre
1. `tick_watch.py` (in ~/agy-scratch/tick-watch/) — script che:
   a. trova TUTTI i file DOGEUSDT_*.csv.gz in ~/money/data/tick/ (oggi 5: dal 13/10 al 17/10), ordinati per data
   b. per ognuno calcola: n righe, copertura ore (ultimo-primo timestamp), primo/ultimo timestamp ISO UTC, totale valori null/vuoti, duplicati trdMatchID, n gap >60s e gap massimo
   c. controlli di FRESCHEZZA: (i) giorni mancanti tra il primo e l'ultimo giorno coperto; (ii) eta' dell'ultimo file in ore rispetto ad adesso; (iii) esiste il file del giorno precedente a oggi?
   d. VERDETTO con regole dichiarate nel codice:
      - FAIL se: ultimo file piu' vecchio di 36h OPPURE un giorno mancante nel mezzo OPPURE un file con copertura <20h OPPURE null>0 OPPURE duplicati>0
      - WARN se: gap>60s totali >20 OPPURE file del giorno precedente assente (ma ultimo <36h)
      - altrimenti OK
   e. scrive `tick_watch.json` + `tick_watch.md`; stampa il verdetto; exit code 0 (OK) / 1 (WARN) / 2 (FAIL)
2. Esegui lo script ORA e produci il report del run odierno.
3. `DONE.md` con: comando esatto, output, verdetto, anomalie.

## Regole
- SOLO lettura dei dati; NON modificare nulla in ~/money; scrivi SOLO in ~/agy-scratch/tick-watch/.
- python3 stdlib (gzip+csv+datetime+statistics); niente pandas se non c'e'; niente rete, niente chiavi.
- Numeri ESATTI. Lo script deve funzionare anche con 30+ file (usa glob, non liste fisse).
- Il campo timestamp e' secondi epoch come float; la prima riga di ogni csv e' header.
