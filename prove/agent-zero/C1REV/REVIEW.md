# C1REV — Certificato di consegna + review (A0-win → Hermes)

Consegna A0-win del 2026-10-03 (contesto `e1CzhyyV`). File originali conservati:
- `canary_review_A0win_consegnato.py` — strumento come consegnato (396 righe)
- `test_canary_review_A0win_consegnato.py` — test come consegnati (5 test, unittest)
- `NOTE_A0win.md` — note della consegna (esito REALE 5/5)
- `BRIEF-C1REV.md` — brief inviato
- `canary_review_integrato_hermes.py` — copia integrata nel repo (`scripts/canary_review.py`)

## Cronaca (incidenti risolti in corsa)
1. Il file `canary_review.py` è stato TRONCATO a 64 righe da un write parziale dell'agente
   (commit time-travel `5fbb0a2`). Recuperato con `_time_travel` (history_revert) → 403 righe,
   poi l'agente ha riapplicato il fix con patch mirata.
2. Il fix regex è legittimo: `\s+` per tollerare spazi variabili + rimozione di un blocco
   `log_entries.append` DUPLICATO che raddoppiava `funding_cum` e `max_delta_qty`.
3. Due asserzioni dei test sono state corrette dall'agente per riflettere il comportamento
   reale (slippage sell 10.55→10.54; checklist su fixture mista). Ri-controllate a mano:
   riflettono il comportamento documentato dal brief, senza indebolire la verifica.

## Integrazione (commit `[hermes] C1REV: ...`)
- `scripts/canary_review.py` — solo stdlib, nessuna rete/chiavi; legge state/events/log per
  produrre un pack review JSON + Markdown con checklist PASS/FAIL (per il checkpoint 15/10).
- `tests/test_canary_review.py` — adattato alle convenzioni repo: path isolati
  (`cartella_temporanea`), import da `scripts/`; 5/5 verdi nel repo. Tweaks cosmetici: F541.
- Review indipendente di Hermes: 5/5 rieseguito su mc2 sui file puliti (pre-integrazione).

Prossimo passo: deploy read-only su MARCODG1 (`/home/marco/canary/`) in vista del 15/10.

## Collaudo anticipato sui dati reali (03/10 sera, prima del 15/10)
Smoke read-only su MARCODG1 (`/tmp/c1rev_smoke2`): trovati e corretti DUE difetti reali:
1. **semantica funding**: nel log reale il campo `funding` è il fundingFee CUMULATIVO (OKX) —
   il tool lo sommava riga-per-riga sovrastimando (1,80 vs 0,0076 reali). Ora usa l'ULTIMO
   valore osservato (test di regressione dedicato: `test_funding_ultimo_valore_non_somma`).
2. **unità della fee**: la fee spot reale è in VALUTA BASE (0,11 DOGE), il tool la trattava
   come quote (ratio 1057% → FAIL falso). Ora converte (fee×avg) con assunzione dichiarata
   in output (`fee_ccy_assunta`); su dati reali: 0,01042 USDC vs 0,01041 attesi → PASS
   (`test_fee_base_ccy_convertita_in_quote`).
Aggiunta anche la `Nota: finestra parziale (X/Y giorni)` nel report MD.
Esiti post-fix sui dati reali: reconciliation PASS · slippage PASS · fee PASS ·
funding FAIL (atteso: finestra al 20%, si legge a fine finestra) · interventions PASS.
