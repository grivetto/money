# P25 — KPI settimanali nel digest (FASE 1) — SPEC DI IMPLEMENTAZIONE
STATO: PRESA_DA Merlino 2026-10-18 (implementazione) — pre-registrata 2026-10-17 (hermes/Artù). REQ-MERL-20261018-006.
Voce OPERATIVA (osservabilità — ROADMAP §3 FASE 1: «KPI settimanali nel digest: rendita netta (€) · fee · distanza dal break-even»). Non è un esperimento; fuori dal conteggio tentativi.
Repo: `grivetto/money` · commit di registrazione: `084bd5f1` (file di questa voce: `coda_catena/P25_kpi_settimanali.md`).

## Obiettivo (verificabile)
Il digest Telegram del **lunedì** include una sezione KPI settimanali:
1. **Rendita netta 7g (€)** scomposta cambio-vs-resto (stessa metodologia di `watch_alerts.py::_attribuzione`, dal banco a secco);
2. **Fee pagate 7g (€)** dal nuovo `logs/fee_ledger.jsonl` (collector sotto) — se il file manca o è vuoto: riga «fee: dati insufficienti», MAI numeri inventati;
3. **Distanza dal break-even**: rendita netta mensilizzata (resto × 30/7) meno costi mensili; capitale attuale vs capitale-break-even stimato (costi ÷ rendita% realizzata 30g, dichiarando la formula e i limiti del campione corto).
Tutto con periodo effettivo dichiarato. Il digest giornaliero resta invariato (la sezione si aggiunge solo con `--settimanale`, che il cron usa il lunedì).

## Meccanica
- `ops/kpi_settimanali.py`: legge banco (via ssh MARCODG1, come `watch_alerts._banco_rows`), `logs/fee_ledger.jsonl`, e compone il testo KPI; `--invia` usa `tools/alert_lib`/`watch_alerts._invia_o_spool` (riusare il pattern esistente, niente nuovo canale). Costanti dichiarate: `COSTI_MENSILI_TARGET_EUR = 16.0` (da ROADMAP D1: AI ≤10 + VPS ≤6; sovrascrivibile da `prove/report_costi.json` se presente con campo `totale_mese_eur`).
- `scripts/raccogli_fee_ledger.py`: fetch read-only `/api/v5/trade/fills-history` (SPOT+FUTURES, ultimi N giorni, default 8) → append idempotente su `logs/fee_ledger.jsonl` con schema `{ts, instId, ordId, clOrdId, side, fillPx, fillSz, fee, feeCcy, billId}`; dedupe su `(billId)`; stampa `nuove=N duplicate=M errori=K`. Gira su MARCODG1 con la chiave read-only del banco (`config/.env_banco`); MAI chiavi in codice/log.
- Il KPI settimanale su mc2 legge `fee_ledger.jsonl` via ssh da MARCODG1 (stesso pattern ssh del digest). Somma fee in €: fee in USDC/USD convertita col tasso EUR implicito del banco; fee in altra valuta → esclusa e contata in una riga «escluse N voci (valuta non convertibile)». Fee di conversione USDC-EUR a 0: incluse (sono 0).

## Input / Output
- **Input**: `banco_secco.jsonl` (MARCODG1, sola lettura via ssh), `logs/fee_ledger.jsonl` (MARCODG1), `prove/report_costi.json` (opzionale, su mc2), costanti dichiarate.
- **Output**: testo KPI (stdout; con `--invia` su Telegram via il canale esistente); con `--json` un dict per test/verifica. Nessuna scrittura su exchange, nessun ordine.

## Criteri di accettazione
1. `ops/kpi_settimanali.py` + `scripts/raccogli_fee_ledger.py` + test offline (`tests/test_kpi_settimanali.py`, `tests/test_raccogli_fee_ledger.py`): fixture 2 settimane sintetiche con numeri noti e **valori attesi calcolati a mano** (rendita scomposta, fee sommate, mensilizzazione 30/7, break-even) — ogni test asserisce il risultato: senza l'implementazione i test falliscono; dedupe collector su billId, fee-ledger mancante → «dati insufficienti» (nessuna riga inventata), valuta non convertibile → conteggiata a parte. Output `pytest -q` per esteso.
2. Run reale (di Artù): collector sul ledger vero (7-8g) + KPI composto sul banco vero — output allegato come `prove/P25_kpi_<data>.txt`.
3. `LEGGIMI.md` con: comando cron proposto per il collector (MARCODG1, lunedì 08:50) e per il KPI (mc2, lunedì 09:00, `--settimanale --invia`), comandi esatti di dry-run.
4. Handoff `merlino/handoff/P25/` con i due moduli, i due test, artefatto smoke, LEGGIMI.md, `MANIFEST.sha256`, `READY` (ultimo).
**Scadenza: ACK subito, DONE entro 48h**, altrimenti FAILED con evidenze. Zero ordini, zero chiavi in gioco (test mock), zero write su `~/money`.

## Verifica (riproducibile)
Comando di verifica (test offline, rieseguiti da Artù nel venv canonico):
```bash
python -m pytest tests/test_kpi_settimanali.py tests/test_raccogli_fee_ledger.py -q
```
Run reale (SOLO Artù): collector con `.env_banco` da MARCODG1; poi `ops/kpi_settimanali.py --settimanale` su mc2 con lettura via ssh.

## Fuori scope
- Modifiche al digest giornaliero esistente oltre l'aggiunta della sezione `--settimanale`; nuove chiavi API; scritture su exchange; il track record 60 giorni (voce a sé).
