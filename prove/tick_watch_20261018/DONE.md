# DONE — Watchdog raccolta tick (`tick_watch.py`)

## 1. Comando esatto
```bash
python3 /home/marco/agy-scratch/tick-watch/tick_watch.py
```

## 2. Output del run odierno
### Output standard (stdout + exit code)
```text
VERDETTO: OK | file=5 (2026-10-13..2026-10-17) | righe=1490386 | min_cov=23.9982h | null=0 | dup=0 | gap>60s=20 | max_gap=111.37s | age_mtime=12.36h | age_last_ts=13.91h | yesterday(2026-10-17)=OK
EXIT_CODE=0
```

### File prodotti in `/home/marco/agy-scratch/tick-watch/`
- `tick_watch.py` — script ripetibile (solo stdlib: `gzip`, `csv`, `datetime`, `statistics`, `glob`, `json`, `os`, `re`, `sys`)
- `tick_watch.json` — report strutturato JSON con metriche per file, freschezza, riepilogo e dettagli gap
- `tick_watch.md` — report leggibile in Markdown

### Tabella riepilogativa per file (run `2026-10-18T13:54:28.527444+00:00`)

| Data | File | Righe | Copertura (h) | Primo TS (ISO UTC) | Ultimo TS (ISO UTC) | Null/Vuoti | Dup `trdMatchID` | Gap >60s | Max Gap (s) |
|---|---|---:|---:|---|---|---:|---:|---:|---:|
| `2026-10-13` | `DOGEUSDT_2026-10-13.csv.gz` | 274967 | 23.9995 | `2026-10-13T00:00:00.645600+00:00` | `2026-10-13T23:59:58.784900+00:00` | 0 | 0 | 10 | 111.3704 |
| `2026-10-14` | `DOGEUSDT_2026-10-14.csv.gz` | 301376 | 23.9982 | `2026-10-14T00:00:00.548600+00:00` | `2026-10-14T23:59:54.057900+00:00` | 0 | 0 | 0 | 54.9996 |
| `2026-10-15` | `DOGEUSDT_2026-10-15.csv.gz` | 471687 | 23.9996 | `2026-10-15T00:00:00.172600+00:00` | `2026-10-15T23:59:58.841400+00:00` | 0 | 0 | 1 | 72.7388 |
| `2026-10-16` | `DOGEUSDT_2026-10-16.csv.gz` | 259035 | 23.9994 | `2026-10-16T00:00:00.180000+00:00` | `2026-10-16T23:59:57.942900+00:00` | 0 | 0 | 1 | 61.0146 |
| `2026-10-17` | `DOGEUSDT_2026-10-17.csv.gz` | 183321 | 23.9993 | `2026-10-17T00:00:00.937600+00:00` | `2026-10-17T23:59:58.525100+00:00` | 0 | 0 | 8 | 94.7981 |
| **Totale / Sintesi** | **5 file** | **1490386** | **min 23.9982** | `2026-10-13T00:00:00.645600+00:00` | `2026-10-17T23:59:58.525100+00:00` | **0** | **0** | **20** | **111.3704** |

### Controlli di freschezza
- **Giorni mancanti tra primo (`2026-10-13`) e ultimo (`2026-10-17`)**: `0` (nessuno)
- **Eta' ultimo file (`DOGEUSDT_2026-10-17.csv.gz`)**:
  - da `mtime` (`2026-10-18T01:32:53.392556+00:00`): `12.36 ore` (< 36h)
  - da `last_ts` (`2026-10-17T23:59:58.525100+00:00`): `13.91 ore` (< 36h)
- **Esiste il file del giorno precedente a oggi (`2026-10-17`)?**: **SI**

## 3. Verdetto
- **VERDETTO**: **OK** (`exit code 0`)
- Tutte le condizioni di `FAIL` sono false (eta' ultimo file < 36h, 0 giorni mancanti, copertura minima 23.9982h >= 20h, 0 valori null/vuoti, 0 duplicati `trdMatchID`).
- Tutte le condizioni di `WARN` sono false (gap >60s totali = 20, che non supera la soglia `>20`; file di ieri `2026-10-17` presente).

## 4. Anomalie e Osservazioni
1. **Gap >60s sulla soglia di attenzione (`20` su soglia `>20`)**:
   - Nei primi 4 file (`13-16/10`) erano presenti `12` gap >60s (10 il `13/10`, 0 il `14/10`, 1 il `15/10`, 1 il `16/10`).
   - Il file `DOGEUSDT_2026-10-17.csv.gz` aggiunge `8` nuovi gap >60s (con gap massimo giornaliero di `94.7981 s` alle `11:42:10 UTC`), portando il totale cumulato esattamente a `20`.
   - Con un solo ulteriore gap >60s nei prossimi file, la regola `gap>60s totali > 20` farebbe scattare `WARN` sul totale storico cumulato.
2. **Volume di trade inferiore il 17/10 (sabato)**:
   - `DOGEUSDT_2026-10-17.csv.gz` conta `183,321` righe (contro una media di `298,077.20` e mediana di `274,967`), fisiologico per la minore attivita' nel weekend, che contribuisce anche alla maggiore frequenza di intervalli >60s senza trade (8 gap tra 60.1s e 94.8s) pur con copertura oraria completa (`23.9993 h`).
3. **Integrita' dati perfetta**:
   - `0` valori null/vuoti su `1,490,386` righe (`16,394,246` celle totali).
   - `0` `trdMatchID` duplicati.
