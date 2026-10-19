# P28 — Chiusura delta-neutral di una coppia carry multi (strumento operativo)

STATO: **INTEGRATA (2026-10-19, Artù)** — implementazione Merlino (REQ-MERL-20261019-012: MANIFEST 5/5, 24 test, suite 978). Review PASS + **dry-run reale da MARCODG1 PASS su DOT e ADA (zero ordini)**. Commit `cb542704`. Voce OPERATIVA (gestione del carry in produzione; fuori dal conteggio tentativi).
Repo: `grivetto/money` · file di questa voce: `coda_catena/P28_chiusura_carry_multi.md`.

## Obiettivo (verificabile)
`scripts/carry_chiudi.py` chiude UNA coppia carry aperta del multi-coppia (`data/carry_multi/`): gamba perp in **reduceOnly** + gamba spot sell, con **dry-run di default** e `--execute` esplicito, riconciliazione finale e log evento. Nessuna logica nuova di trading: stessi percorsi di invio del resto del carry (`money.esecuzione.invio.invia_gamba` — unico percorso di invio imposto dal guard-test), stessa convenzione di stato/eventi di `carry_multi`.

## Contesto
- Il carry multi (DOT, ADA; LTC/AVAX abilitate il 19/10) ha il gate di apertura (`scripts/carry_apri.py`) ma **nessuna via di chiusura**: la modalità `close` esiste solo in C1 (`scripts/canary_carry.py`, hardcoded su DOGE).
- Serve per: rotazione/step del piano D3, deterioramento del funding (decisione operativa di Artù), incidenti. La chiusura è **riduzione di rischio**: non passa dal gate di apertura e il kill switch NON la blocca (come C1).
- La chiusura è una scrittura sul percorso del capitale → testata offline PRIMA di qualunque uso reale; dry-run che mostra il piano a zero scritture.

## Meccanica
- Uso: `carry_chiudi.py --coppia NOME [--motivo "testo"] [--execute]`. Default = dry-run.
- Pre-check (anche in dry-run): coppia nota in `COPPIE`; stato in `data/carry_multi/stato.json` con la coppia aperta; posizioni REALI lette dall'exchange (pos perp via fetch_positions, balance spot). **Quantità da chiudere = posizioni reali, MAI i numeri dello stato.**
- Se entrambe le gambe sono già a zero: «già chiusa», no-op, exit 0 (idempotente).
- Piano (dry-run): stampa gambe, quantità, prezzi indicativi (bid per le vendite), stima fee; zero ordini, zero scritture.
- Esecuzione (`--execute`), in sequenza:
  1. **perp**: ordine **reduceOnly** di chiusura della posizione (limit con reprice come C1, o market — scelta dell'implementatore, DICHIARATA nel LEGGIMI); attesa fill.
  2. **spot**: sell della qty spot detenuta (limit con reprice); attesa fill.
  - Sequenza perp→spot: se la perp non si chiude, **NON si vende lo spot** (niente posizione nuda non voluta); se lo spot non si chiude dopo perp chiusa: retry/reprice e poi evento di errore con stato esplicito (spot residuo = long, da sistemare a mano).
  - Caso perp assente ma spot presente → chiude solo lo spot (fallback C1). Caso spot assente ma perp presente → chiude solo la perp con nota.
- Riconciliazione finale: pos perp == 0 e delta spot == −qty venduta, con **poll esteso** (lezione REQ-008: l'accredito può avere latenza); timeout → esito FAIL_CHIUSURA con nota esplicita, nessuna azione correttiva automatica oltre il retry già previsto.
- Stato: aggiorna `data/carry_multi/stato.json` (coppia → status closed, ts_chiudi, esiti, fee) + riga in `eventi.jsonl`. clOrdId stabili (pattern `cid_stabile`) per idempotenza.
- Guardie: qty mai > posizione reale; mai invertire il segno (niente long/short accidentali); check min order size; coppia non nota → rifiuto.

## Input / Output
- Input: stato carry_multi, posizioni/saldi reali (sola lettura) — il modulo è offline-testabile con mock.
- Output: piano stampato (dry-run) / chiusura eseguita + stato aggiornato + evento; exit code 0/≠0.

## Criteri di accettazione
1. `scripts/carry_chiudi.py` + `tests/test_carry_chiudi.py` (mock, pattern earn_move/canary): chiusura completa (entrambe le gambe), dry-run zero scritture, già-chiusa no-op, perp assente → solo spot, spot assente → solo perp, timeout riconciliazione → FAIL con nota, guardie (coppia ignota, qty > posizione). Output `pytest -q` per esteso; suite esistente verde.
2. `LEGGIMI.md` con i comandi dry-run che rieseguirà Artù da MARCODG1 (`carry_chiudi.py --coppia DOT`).
3. Handoff `merlino/handoff/P28/` con modulo, test, LEGGIMI, `MANIFEST.sha256`, `READY` (ultimo).
4. Zero ordini, zero chiavi, zero write su `~/money` (lavoro in `~/merlino-scratch/p28/`).

## Verifica (riproducibile)
```bash
cd ~/money && .venv/bin/python -m pytest tests/test_carry_chiudi.py -q
# dry-run reale (SOLO Artù, da MARCODG1): .venv/bin/python3 scripts/carry_chiudi.py --coppia DOT
```

## Fuori scope
- Decisioni di QUANDO chiudere (restano operative: rotazione D3, deterioramento, incidente — di Artù); modifiche al gate/calcolo dell'apertura; ordini reali; chiavi.

## Riferimenti
`scripts/canary_carry.py` (modalità close C1 — riferimento di meccanica) · `scripts/carry_multi.py` (stato/eventi/COPPIE) · `scripts/carry_apri.py` (gate unico di apertura) · `scripts/earn_move.py` (pattern test/mock) · ROADMAP §D3 · REQ-MERL-20261019-012.
