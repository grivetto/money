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
- [aperto] Arricchimento `basis_pp`: l'endpoint funding non fornisce mark/index price → campo 0.0; valutare un punto di raccolta basis separato (mark vs index live) se servirà al canary.
- Regola di maturita' dichiarata: P4 (funding carry) sara' misurabile quando la storia
  accumulata raggiunge ~30 osservazioni indipendenti.

## Riferimenti
- Registro: `prove/REGISTRO_ESPERIMENTI.md` (sezione Infrastruttura).
- P4: `coda_catena/P4_funding_carry.md`.
