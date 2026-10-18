# TASK — Preflight dei dati tick (salute della raccolta)

Sei un operaio di analisi del progetto "money". Produci un REPORT DI PREFLIGHT dei dati tick raccolti. Lavora SOLO dentro ~/agy-scratch/preflight-tick/ (crea la directory).

## Dati
In ~/money/data/tick/ ci sono file `DOGEUSDT_YYYY-MM-DD.csv.gz` — tick trade-level (raccolta su MARCODG1). Schema CSV:
`timestamp,symbol,side,size,price,tickDirection,trdMatchID,grossValue,homeNotional,foreignNotional,RPI`
(timestamp = secondi epoch come float; side = Buy/Sell)

## Cosa produrre
Per OGNI file .csv.gz nella directory:
1. n_righe
2. primo e ultimo timestamp convertiti in ISO UTC
3. copertura in ore (ultimo - primo)
4. size: min, p50, max, media
5. price: min, p50, max
6. conteggio valori vuoti/null per colonna
7. duplicati su trdMatchID (conteggio)
8. n gap > 60 secondi tra timestamp consecutivi + gap massimo (secondi)

Riepilogo complessivo: n file, giorni coperti, n trade totali, anomalie rilevate.

## Output (in ~/agy-scratch/preflight-tick/)
- `preflight_tick.json` — tutti i numeri sopra (per file + riepilogo)
- `preflight_tick.md` — tabella leggibile

## Regole
- SOLO lettura dei dati; NON modificare nulla in ~/money.
- Scrivi SOLO in ~/agy-scratch/preflight-tick/.
- Niente rete, niente chiavi.
- Usa python3; se pandas manca, usa gzip+csv della stdlib (dichiaralo nel report).
- Numeri ESATTI, mai stimati. Se un file è illeggibile, scrivilo nel report, non inventare.

## Al termine
Scrivi `DONE.md` con: comando esatto eseguito, output sintetico (una riga per file: nome, righe, copertura), anomalie trovate.
