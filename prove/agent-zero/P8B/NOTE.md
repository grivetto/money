# Task P8B — Tabella giornaliera funding/basis (modulo + test)

## Cosa è stato fatto

1. **Creato `report_funding.py`** — modulo autonomo, solo stdlib:
   - `tabella_giornaliera(path_jsonl)`: legge file JSONL (da P8) con righe
     `{"simbolo","ts","funding","basis_pp","fonte"}` e aggrega per (simbolo, giorno UTC):
     n_funding (conteggio), funding_medio, funding_somma, basis_medio (solo basis_pp non nulli),
     primo_ts, ultimo_ts. Output = lista ordinata per (giorno, simbolo).
   - `copertura(tabella, giorni_attesi)`: per simbolo, giorni con dato vs attesi, copertura %.
   - `report_testo(tabella)` e `report_json(tabella)`: stringhe deterministiche.
   - Righe malformate nel JSONL: CONTATE (`righe_saltate`) e saltate, mai un crash.
   - Import solo stdlib: json, os, datetime, typing, collections.

2. **Creato `test_report_funding.py`** — 9 test con fixture in `_prove_test/`:
   - (a) `test_a_fixture_piccola`: 3 righe stesso giorno/simbolo -> conteggi/somme/medie corretti
   - (b) `test_b_multi_simbolo_giorno_ordine`: multi-simbolo, multi-giorno, ordine stabile (giorno, simbolo)
   - (c) `test_c_riga_malformata`: 2 righe malformate -> saltate e contate, resto intatto
   - (d) `test_d_file_vuoto`: file vuoto -> tabella vuota, non errore
   - (e) `test_e_file_inesistente`: file inesistente -> FileNotFoundError chiaro
   - (f) `test_f_determinismo`: due chiamate -> stesse stringhe (testo e JSON)
   - (g) `test_g_basis_nulli_assenti`: basis None/assenti -> media solo su valori presenti, N/A in testo
   - Extra: `test_extra_copertura`, `test_extra_report_json_struttura`

3. **Tutti i test PASS** eseguiti in `/a0/usr/workdir/p8b/`

## Comandi eseguiti
```bash
mkdir -p /a0/usr/workdir/p8b
cd /a0/usr/workdir/p8b
python3 test_report_funding.py
```

## Esito REALE dei test
```
✓ test_a_fixture_piccola PASS
✓ test_b_multi_simbolo_giorno_ordine PASS
✓ test_c_riga_malformata PASS
✓ test_d_file_vuoto PASS
✓ test_e_file_inesistente PASS
✓ test_f_determinismo PASS
✓ test_g_basis_nulli_assenti PASS
✓ test_extra_copertura PASS
✓ test_extra_report_json_struttura PASS

=== TUTTI I TEST PASSATI ===
Test eseguiti: 9 (7 richiesti + 2 extra)
```

## File creati in `/a0/usr/workdir/p8b/`
- `report_funding.py` (218 righe)
- `test_report_funding.py` (296 righe)
- `NOTE.md` (questo file)
- `_prove_test/` (directory di lavoro dei test, ricreata a ogni test)

## Note tecniche
- Timestamp convertiti a giorno UTC via `datetime.fromtimestamp(ts/1000, tz=timezone.utc)`
- Aggregazione con defaultdict per performance
- Basis medio calcolato solo su valori non-None/presenti
- Report JSON con `sort_keys=True` e `separators=('