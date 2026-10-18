# Report di Preflight — Dati Tick (`DOGEUSDT`)

> **Nota metodologica**: Analisi eseguita con `python3` stdlib (`gzip`, `csv`, `statistics`, `datetime`) poiché il pacchetto `pandas` non è installato nell'ambiente. Tutti i calcoli sono esatti al 100% su tutte le righe.

## 1. Riepilogo Complessivo

- **Directory dati**: `/home/marco/money/data/tick`
- **Numero file analizzati**: `4`
- **Giorni coperti**: `2026-10-13, 2026-10-14, 2026-10-15, 2026-10-16` (dal `2026-10-13T00:00:00.645600Z` al `2026-10-16T23:59:57.942900Z`)
- **Trade totali (`n_righe` complessive)**: `1307065`
- **Valori vuoti/null totali**: `0`
- **Duplicati `trdMatchID` (intra-file / cross-file)**: `0` / `0`
- **Gap > 60s totali**: `12` (gap massimo assoluto: `111.3704 s`)

### Anomalie Rilevate
- DOGEUSDT_2026-10-13.csv.gz: 10 gap > 60s (gap massimo: 111.3704s tra 2026-10-13T23:47:59.875300Z e 2026-10-13T23:49:51.245700Z)
- DOGEUSDT_2026-10-15.csv.gz: 1 gap > 60s (gap massimo: 72.7388s tra 2026-10-15T23:57:41.335300Z e 2026-10-15T23:58:54.074100Z)
- DOGEUSDT_2026-10-16.csv.gz: 1 gap > 60s (gap massimo: 61.0146s tra 2026-10-16T23:34:17.628300Z e 2026-10-16T23:35:18.642900Z)

---

## 2. Tabella Sintetica per File (Copertura, Volumi, Prezzi, Integrità)

| File | Leggibile | N. Righe | Primo Timestamp (ISO UTC) | Ultimo Timestamp (ISO UTC) | Copertura (ore) | Duplicati `trdMatchID` | Null Totali | N. Gap > 60s | Gap Max (s) |
| :--- | :---: | ---: | :--- | :--- | ---: | ---: | ---: | ---: | ---: |
| `DOGEUSDT_2026-10-13.csv.gz` | Sì | 274967 | `2026-10-13T00:00:00.645600Z` | `2026-10-13T23:59:58.784900Z` | 23.999483 | 0 | 0 | 10 | 111.3704 |
| `DOGEUSDT_2026-10-14.csv.gz` | Sì | 301376 | `2026-10-14T00:00:00.548600Z` | `2026-10-14T23:59:54.057900Z` | 23.998197 | 0 | 0 | 0 | 54.9996 |
| `DOGEUSDT_2026-10-15.csv.gz` | Sì | 471687 | `2026-10-15T00:00:00.172600Z` | `2026-10-15T23:59:58.841400Z` | 23.999630 | 0 | 0 | 1 | 72.7388 |
| `DOGEUSDT_2026-10-16.csv.gz` | Sì | 259035 | `2026-10-16T00:00:00.180000Z` | `2026-10-16T23:59:57.942900Z` | 23.999379 | 0 | 0 | 1 | 61.0146 |

---

## 3. Statistiche `size` e `price` per File

| File | `size` min | `size` p50 | `size` max | `size` media | `price` min | `price` p50 | `price` max |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `DOGEUSDT_2026-10-13.csv.gz` | 1 | 66.0 | 1881688 | 3411.806566 | 0.07996 | 0.08403 | 0.08521 |
| `DOGEUSDT_2026-10-14.csv.gz` | 1 | 67.0 | 1251131 | 4031.870335 | 0.08125 | 0.08326 | 0.08565 |
| `DOGEUSDT_2026-10-15.csv.gz` | 1 | 70.0 | 3382885 | 3518.659357 | 0.07752 | 0.07998 | 0.08203 |
| `DOGEUSDT_2026-10-16.csv.gz` | 1 | 69.0 | 3166765 | 3339.218492 | 0.07928 | 0.08130 | 0.08285 |

---

## 4. Conteggio Valori Vuoti/Null per Colonna

| File | `timestamp` | `symbol` | `side` | `size` | `price` | `tickDirection` | `trdMatchID` | `grossValue` | `homeNotional` | `foreignNotional` | `RPI` |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `DOGEUSDT_2026-10-13.csv.gz` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `DOGEUSDT_2026-10-14.csv.gz` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `DOGEUSDT_2026-10-15.csv.gz` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `DOGEUSDT_2026-10-16.csv.gz` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

---

## 5. Dettaglio Gap > 60 Secondi

| File | Riga | Da (ISO UTC) | A (ISO UTC) | Durata Gap (s) |
| :--- | ---: | :--- | :--- | ---: |
| `DOGEUSDT_2026-10-13.csv.gz` | 265173 | `2026-10-13T20:58:52.181300Z` | `2026-10-13T21:00:05.110800Z` | 72.9295 |
| `DOGEUSDT_2026-10-13.csv.gz` | 265870 | `2026-10-13T21:17:12.804100Z` | `2026-10-13T21:18:14.202800Z` | 61.3987 |
| `DOGEUSDT_2026-10-13.csv.gz` | 266725 | `2026-10-13T21:36:13.280000Z` | `2026-10-13T21:37:17.775000Z` | 64.4950 |
| `DOGEUSDT_2026-10-13.csv.gz` | 267620 | `2026-10-13T21:55:36.778700Z` | `2026-10-13T21:56:37.336000Z` | 60.5573 |
| `DOGEUSDT_2026-10-13.csv.gz` | 271132 | `2026-10-13T22:55:39.071200Z` | `2026-10-13T22:57:00.513200Z` | 81.4420 |
| `DOGEUSDT_2026-10-13.csv.gz` | 274248 | `2026-10-13T23:36:48.938000Z` | `2026-10-13T23:37:54.499000Z` | 65.5610 |
| `DOGEUSDT_2026-10-13.csv.gz` | 274505 | `2026-10-13T23:44:22.039100Z` | `2026-10-13T23:45:23.138800Z` | 61.0997 |
| `DOGEUSDT_2026-10-13.csv.gz` | 274606 | `2026-10-13T23:47:59.875300Z` | `2026-10-13T23:49:51.245700Z` | 111.3704 |
| `DOGEUSDT_2026-10-13.csv.gz` | 274779 | `2026-10-13T23:52:41.192700Z` | `2026-10-13T23:53:44.657400Z` | 63.4647 |
| `DOGEUSDT_2026-10-13.csv.gz` | 274909 | `2026-10-13T23:56:31.356600Z` | `2026-10-13T23:57:35.504700Z` | 64.1481 |
| `DOGEUSDT_2026-10-15.csv.gz` | 471642 | `2026-10-15T23:57:41.335300Z` | `2026-10-15T23:58:54.074100Z` | 72.7388 |
| `DOGEUSDT_2026-10-16.csv.gz` | 257936 | `2026-10-16T23:34:17.628300Z` | `2026-10-16T23:35:18.642900Z` | 61.0146 |
