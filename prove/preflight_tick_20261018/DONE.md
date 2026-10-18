# DONE — Preflight Dati Tick (`DOGEUSDT`)

## Comando esatto eseguito
```bash
python3 /home/marco/agy-scratch/preflight-tick/analyze_preflight.py
```
*(Nota: `pandas` non è installato nell'ambiente; l'analisi è stata effettuata con `python3` stdlib `gzip` + `csv` + `statistics` + `datetime`).*

## Output sintetico (per file)
- `DOGEUSDT_2026-10-13.csv.gz` | righe: `274967` | copertura: `23.999483 h` (`2026-10-13T00:00:00.645600Z` -> `2026-10-13T23:59:58.784900Z`)
- `DOGEUSDT_2026-10-14.csv.gz` | righe: `301376` | copertura: `23.998197 h` (`2026-10-14T00:00:00.548600Z` -> `2026-10-14T23:59:54.057900Z`)
- `DOGEUSDT_2026-10-15.csv.gz` | righe: `471687` | copertura: `23.999630 h` (`2026-10-15T00:00:00.172600Z` -> `2026-10-15T23:59:58.841400Z`)
- `DOGEUSDT_2026-10-16.csv.gz` | righe: `259035` | copertura: `23.999379 h` (`2026-10-16T00:00:00.180000Z` -> `2026-10-16T23:59:57.942900Z`)

**Totale**: `4` file (`2026-10-13` .. `2026-10-16`), `1307065` trade totali.

## Anomalie trovate
- **Valori null/vuoti**: `0` su tutte le 11 colonne di tutti i 4 file.
- **Duplicati `trdMatchID`**: `0` intra-file e `0` cross-file.
- **Timestamp fuori ordine (gap negativi)**: `0` in tutti i file.
- **Gap > 60 secondi tra trade consecutivi** (`12` totali):
  - `DOGEUSDT_2026-10-13.csv.gz`: `10` gap > 60s concentrati nella fascia 20:58–23:57 UTC (gap massimo: `111.3704 s` tra `2026-10-13T23:47:59.875300Z` e `2026-10-13T23:49:51.245700Z`).
  - `DOGEUSDT_2026-10-14.csv.gz`: `0` gap > 60s (gap massimo: `54.9996 s`).
  - `DOGEUSDT_2026-10-15.csv.gz`: `1` gap > 60s (gap massimo: `72.7388 s` tra `2026-10-15T23:57:41.335300Z` e `2026-10-15T23:58:54.074100Z`).
  - `DOGEUSDT_2026-10-16.csv.gz`: `1` gap > 60s (gap massimo: `61.0146 s` tra `2026-10-16T23:34:17.628300Z` e `2026-10-16T23:35:18.642900Z`).
