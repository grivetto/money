# DONE — P26 Preflight dati (cointegrazione v2)

## Cosa è stato fatto
Preflight di salute dell'archivio candele giornaliere USDT su mc2
(`~/money/data/cache/okx_eea_<SYM>-USDT_1d.json`) per la spec P26.

- **File usati:** 90 file `okx_eea_*-USDT_1d.json` (esclusi 9 file `*-EUR_1d.json` presenti nella stessa cartella, non pertinenti).
- **Lettura dati:** solo `ssh BatchMode` da mc2, copia in `./data/`. **Nessuna scrittura su mc2.**
- **Strumento:** python3 3.14.7 + stdlib (`json`, `datetime`). **pandas NON era disponibile** → nessun venv necessario, analisi in stdlib pura.
- **Output in questo scratch:** `p26_preflight.json`, `p26_preflight.md`, `DONE.md` (+ script `analyze.py`, `make_md.py`, copie in `data/`).

## Comandi esatti eseguiti
```bash
# 1. inventario (conteggio: 90 file USDT, ~11 MB)
ssh -o BatchMode=yes mc2 'ls ~/money/data/cache/okx_eea_*-USDT_1d.json' | wc -l

# 2. copia in sola lettura dei 90 file nello scratch (nessuna scrittura su mc2)
mkdir -p ~/opencode-scratch/p26-preflight/data
ssh -o BatchMode=yes mc2 \
  'tar -cf - -C ~/money/data/cache $(ls ~/money/data/cache/okx_eea_*-USDT_1d.json | xargs -n1 basename)' \
  | tar -xf - -C ~/opencode-scratch/p26-preflight/data

# 3. analisi
cd ~/opencode-scratch/p26-preflight
python3 analyze.py      # -> p26_preflight.json
python3 make_md.py      # -> p26_preflight.md
```

## Finestre usate
- Addestramento: `[2020-01-01, 2024-06-01)` → 1613 giorni attesi.
- Verifica: `[2024-06-01, 2026-10-17]` dove **2026-10-17 = ultima barra presente nell'archivio** (data "oggi" dichiarata).
- Soglia copertura: 95% su entrambe + prima barra ≤ 2020-01-01.

## Output sintetico
- **File analizzati:** 90/90. **Illeggibili:** 0.
- **IDONEE:** **2 / 90** → `ETH/USDT`, `BTC/USDT`.
- **NON IDONEE:** 88 (tutte per la stessa causa: prima barra dopo il 2020-01-01).
- **Candidate top 30:** solo **2** coppie idonee (ne dichiaro l'insufficienza; elencate tutte).
  - Per volume nativo (addestramento): 1) ETH/USDT 200,349.77 · 2) BTC/USDT 20,541.74
  - Per controvalore (volume × close, USDT): 1) BTC/USDT ~490.2 M · 2) ETH/USDT ~253.5 M
- **Qualità archivio:** 90/90 file con **0 buchi interni** (serie contigue tra prima e ultima barra); 0 file con varianza degenere (close min < close max ovunque).

## Anomalie principali (dettaglio in `p26_preflight.md` §Anomalie)
1. **Nessun buco interno in nessuno dei 90 file.** La copertura bassa in addestramento NON è dovuta a buchi, ma all'assenza di storia antecedente alla prima barra.
2. **Prima barra quasi uniforme (59/90 = 2020-10-01).** LTC, XRP, ADA, LINK, etc. "partono" tutte lo stesso giorno → probabile **artefatto di raccolta** (confine di paginazione OKX), non data di listing reale. Solo BTC ed ETH risalgono al 2019-01-01; 24 file partono nel 2021.
   - **Conseguenza:** con la regola `prima barra ≤ 2020-01-01`, praticamente tutto l'universo esteso è escluso. Va deciso con lo spec owner se il vincolo è voluto o se è una proxy troppo severa.
3. **Confine di raccolta in coda.** 71 file si fermano al 2026-10-06, 15 al 2026-10-17, 3 al 2026-09-25, 1 (BTC) al 2026-10-16. Usare la fine globale 2026-10-17 abbassa la copertura di verifica dei file non aggiornati a ~98.7% (comunque ≥ 95%). Non è delisting, è un batch di raccolta parziale.
4. **Unità del volume.** Il campo `v` è in **valuta base** (BTC ~2×10⁴, DOGE ~9.8×10⁸), quindi il ranking "per volume" richiesto dalla spec **non è un ranking di liquidità confrontabile** tra simboli. Ho fornito anche un ranking **per controvalore (v × close)** come diagnostica aggiuntiva.

## Verifiche di correttezza
- Cross-check indipendente di copertura e volume medio su ETH/USDT, 1INCH/USDT, DOGE/USDT: valori coincidono al decimale con il report.
- Audit formattazione: tutte le barre allineate a mezzanotte UTC, nessun duplicato, nessun file fuori ordine, tutte con 6 campi, metadata coerenti (`venue=okx_eea`, `hostname=eea.okx.com`, `timeframe=1d`).

## Note di scoping
- Letti solo i 90 file **USDT**; i 9 file **EUR** della cartella sono stati ignorati perché fuori dalla spec.
- Nessuna chiave, nessun accesso di rete oltre ssh verso mc2.
