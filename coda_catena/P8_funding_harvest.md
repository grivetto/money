# P8 — Raccoglitore funding/basis (INFRASTRUTTURA, non strategia)

STATO: ATTIVO (01/10) — P8 integrato (29/09) + P8B tabella (certificato `prove/agent-zero/P8B/`); **raccolta SCHEDULATA**: runner `scripts/raccogli_funding.py` + cron mc2 ogni 4h (`13 */4 * * *`, log `logs/raccolta_funding.log`); backfill iniziale 2692 righe (10 X-Perp major, storia dal 03/07).

## Cos'e'
Raccoglitore append-only idempotente dei tassi funding su OKX EEA, per la fase di accumulo
del filone carry/funding (la "Tesi 1" della revisione economica Manus del 30/09).
Include la guardia anti-ordini (nessun percorso di codice puo' inviare ordini).

## Fatto
- `src/money/raccoglitore_funding.py` integrato il 2026-09-29 (9 test nella suite).
- Append-only idempotente: rilancia senza duplicare.
- Tabella giornaliera in corso su A0-MC2 (task P8B); controllo previsto alla consegna.

## Resta da fare (operativo, non una spec di ricerca)
- [fatto 30/09] Tabella P8B verificata e integrata.
- [fatto 01/10] Raccoglitore schedulato: backfill 2692 righe + cron ogni 4h.
- [aperto] Arricchimento `basis_pp`: l'endpoint funding non fornisce mark/index price → campo 0.0; valutare un punto di raccolta basis separato (mark vs index live) se servira' al canary.
- Regola di maturita' dichiarata: P4 (funding carry) sara' misurabile quando la storia
  accumulata raggiunge ~30 osservazioni indipendenti.

## Riferimenti
- Registro: `prove/REGISTRO_ESPERIMENTI.md` (sezione Infrastruttura).
- P4: `coda_catena/P4_funding_carry.md`.

## Formato-contratto (retrofit 2026-10-06; contenuto sopra invariato)
- **Obiettivo**: mantenere la raccolta funding append-only e idempotente per il filone carry,
  con guardia anti-ordini; strumento di misura, non una strategia.
- **Repo/commit**: `grivetto/money`, retrofit al commit `e996d336` (06/10/2026); integrazione
  del 29/09 con certificato P8B in `prove/agent-zero/P8B/`.
- **Input**: endpoint pubblici OKX EEA (funding history degli X-Perp major) — nessuna chiave,
  nessun ordine. **Output**: `data/funding_xperp.jsonl` (append-only) + tabella giornaliera da
  `src/money/report_funding.py`.
- **Test falsificabile**: un test che fallisce senza l'implementazione — due esecuzioni sulla
  stessa finestra NON devono produrre righe duplicate (assert di idempotenza), e il modulo NON
  deve contenere percorsi che chiamano `create_order` (verifica statica).
- **Criteri di accettazione**:
  - [ ] append-only idempotente verificato dai test;
  - [ ] un errore di rete non corrompe il file (ripartenza pulita);
  - [ ] guardia anti-ordini presente e testata staticamente.
- **Fuori scope**: nessun trading, nessuna chiave privata, nessun ordine — solo endpoint
  pubblici; non toccare il modulo dei costi.
- **Procedura di verifica**:
```bash
python scripts/raccogli_funding.py --giorni 3      # atteso: errori=0, scritti/duplicati coerenti
python -m pytest tests/test_raccoglitore_funding.py tests/test_report_funding.py -q
```
