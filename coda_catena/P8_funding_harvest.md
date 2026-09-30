# P8 — Raccoglitore funding/basis (INFRASTRUTTURA, non strategia)

STATO: INTEGRATO (2026-09-29) — in raccolta dati; scheduling da fare.

## Cos'e'
Raccoglitore append-only idempotente dei tassi funding su OKX EEA, per la fase di accumulo
del filone carry/funding (la "Tesi 1" della revisione economica Manus del 30/09).
Include la guardia anti-ordini (nessun percorso di codice puo' inviare ordini).

## Fatto
- `src/money/raccoglitore_funding.py` integrato il 2026-09-29 (9 test nella suite).
- Append-only idempotente: rilancia senza duplicare.
- Tabella giornaliera in corso su A0-MC2 (task P8B); controllo previsto alla consegna.

## Resta da fare (operativo, non una spec di ricerca)
- Verificare la tabella consegnata da A0-MC2 e schedulare il raccoglitore
  (runner in `scripts/` + timer, dopo il controllo).
- Regola di maturita' dichiarata: P4 (funding carry) sara' misurabile quando la storia
  accumulata raggiunge ~30 osservazioni indipendenti (limite endpoint: ~96 giorni di
  storico funding — vedi `coda_catena/P4_funding_carry.md`).

## Riferimenti
- Registro: `prove/REGISTRO_ESPERIMENTI.md` (sezione Infrastruttura).
- P4: `coda_catena/P4_funding_carry.md`.
