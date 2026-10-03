BRIEF-C1REV — Generatore del pacchetto di review del canary C1 (carry DOGE)
Repo di destinazione: grivetto/money @ ff3223f6 (file finale `tools/canary_review.py`). Non hai accesso al repo: costruisci da zero secondo questo brief; Hermes rivede e integra.

## Obiettivo
Tool di SOLA LETTURA `canary_review.py` (solo stdlib) che, dai file del canary C1 (stato JSON, eventi JSONL, log testuale), produce un pacchetto di review (JSON + Markdown) per il checkpoint del 15/10: metriche + checklist PASS/FAIL contro i criteri pre-registrati. Niente rete, niente chiavi, niente ordini: legge solo file locali.

## Input — schemi esatti (i file reali arriveranno dopo; tu costruisci fixtures tuoi)
### canary_state.json
{"status": "open", "ts_open": "<ISO>", "inst": "<str>", "symbols": {"perp": "<str>", "spot": "<str>"},
 "spot": {"qty": <float>, "avg_px": <float>, "fee": <float>, "order": "<str>", "esito": "<str>", "mid_pre": <float>},
 "perp": {"ct": <float>, "avg_px": <float>, "order": "<str>", "esito": "<str>", "mid_pre": <float>, "mgnMode": "<str>", "lever": "<str>"},
 "delta_qty": <float>, "updated": "<ISO>",
 "last_pos_ct": <float>, "last_mark": <float>, "last_upl": <float>, "last_funding": <float>,
 "last_delta": <float>, "last_check": "<ISO>",
 "ts_close": "<ISO>", "esiti": {...}   # solo dopo la chiusura}
### canary_events.jsonl — una riga JSON per evento: {"ts": "<ISO>", "event": "<tipo>", ...}
Tipi noti: convert; spot_fill (qty, avg, fee, fee_ccy, esito, mid_pre); open_complete (ct, avg_perp, qty_spot, delta); close_perp; close_spot; close_complete; unwind_spot; abort; perdita_hedge.
### canary.log — righe testuali, una per giro del cron (formato `status --quiet`). Riga tipica (tollerare spazi variabili):
`C1 DOGE: perp 11ct@ 0.09466 mark 0.09282 upl +0.2024 funding +0.0076 |    spot 109.89 DOGE (avg 0.09466) mid 0.09282 delta-qty 0.11 liq 0 |    net stimato (spotΔ+upl+funding) +0.0090 USDC`
Quando la posizione manca: `C1 DOGE: nessuna posizione perp | DOGE spot N`. Righe con `ANOMALIE: ...` segnalano anomalie di quel giro. Righe non riconoscibili: ignorale.

## Output atteso
CLI: `python canary_review.py --state <f> --events <f> --log <f> --start <ISO> [--days 14] [--notional-usdc 10.4] [--out <dir>]`
- Scrive `<out>/C1_review.json` e `<out>/C1_review.md` (default out = `.`) e stampa il markdown.
- Contenuto minimo:
  - finestra: giorni, primo/ultimo check, numero giri log riconosciuti;
  - funding: cumulato (prima→ultima riga log; fallback `state.last_funding`), atteso-basso = notional × 0,008% × 3 × giorni, rapporto % (criterio: ≥ 90% dell'atteso-basso);
  - slippage: per ogni fill disponibile (spot_fill dagli events; leg perp da `state.perp` con `mid_pre`) — bps = (avg−mid)/mid per buy, (mid−avg)/mid per sell; media per lato; criterio: media ≤ 10 bps/lato; "n/d" se mancano;
  - fee: fee osservate (events `spot_fill.fee`) vs schedule (spot USDC maker 0,08% / taker 0,10%; perp 0,02%/0,05%) — rapporto;
  - riconciliazione: max `delta-qty` dalle righe log (criterio ≤ 1 DOGE); conteggio righe con `ANOMALIE`;
  - eventi: conteggio per tipo; evidenza di abort/unwind/perdita_hedge (gli interventi registrati si contano, non sono omissioni);
  - checklist PASS/FAIL/N-D per i 5 criteri (riconciliazione, slippage, fee, funding, interventi).
- Robustezza: input mancanti o righe rotte → degrada con nota, MAI crash. UTF-8, tolleranza spazi.

## Test (devono fallire senza l'implementazione)
`test_canary_review.py` con fixtures costruiti a mano dentro il test:
- fixture log (6 righe) + state + events → assert funding cumulato atteso, avg slippage atteso (calcolato a mano), delta max, item di checklist;
- caso "nessuna posizione" e caso file vuoto/malformato → assert nessun crash e nota "dati insufficienti";
- assert che con funding sotto soglia la checklist dia FAIL sul criterio funding.

## Criteri di accettazione (checklist)
- [ ] canary_review.py + test_canary_review.py consegnati;
- [ ] test eseguiti, esito REALE incollato in NOTE.md (n/N passed);
- [ ] solo stdlib; nessuna rete/chiave/ordine; sola lettura sui file;
- [ ] output JSON+MD con i campi minimi sopra.

## Fuori scope (non toccare)
- NON eseguire su file reali di produzione (non ne hai accesso);
- NON usare ccxt/requests né altri pacchetti; NON modificare altri file;
- NON toccare exchange/servizi.

## Comando di verifica
```bash
python -B test_canary_review.py
```
Atteso: N passed, 0 failed (incollare l'output in NOTE.md).

## Consegna
Cartella `/a0/usr/workdir/ponte-dsh/C1REV/`: `canary_review.py`, `test_canary_review.py`, `NOTE.md` (elenco file + comando + output reale). Firma con esito. NO segreti.
