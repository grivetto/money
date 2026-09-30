# C1 — Canary carry DOGE (spec PRE-DICHIARATA) — 2026-10-01

STATO: pre-registrata prima dell'esecuzione. Apertura prevista entro il 01/10/2026.
Autorizzazione owner: 01/10/2026 ("devi sempre procedere in autonomia — VAI").
Registro: voce C1 in `prove/REGISTRO_ESPERIMENTI.md` (sezione Infrastruttura).

## Obiettivo (dichiarato PRIMA di eseguire)
Validare l'ESECUZIONE del carry/funding, **non fare profitto**:
1. ordini reali LIMITE (mai market) e fill verificati;
2. slippage reale vs mid, misurato per ogni fill;
3. fee effettive vs schedule (spot USDC 0,08/0,10% · perp 0,02/0,05%);
4. funding incassato per evento (vs media storica del raccoglitore);
5. riconciliazione spot↔perp (delta quantità ≤ 1 contratto);
6. tenuta della toolchain (script, log, monitor, cron).

## Strumento e taglia
- **DOGE**: spot `DOGE/USDC` + X-Perp `DOGE-USD_UM_XPERP-310404` (ctVal 10 DOGE, minSz 1 ct).
- **Taglia**: **110 DOGE per gamba** (~10,4 USDC di nozionale per lato a DOGE≈0,095 — la più
  piccola taglia ~10 USDC che tiene entrambe le gambe sopra il minimo). **Leva 1×**, margine **isolated**.
- Perché DOGE (dati raccoglitore EEA, finestre full/45g/15g): media **+9,6% / +8,8% / +10,8%**
  annualizzati, **96%+ periodi positivi**, code contenute (peggiore −0,016%/8h). Esclusi:
  **BTC/ETH funding NEGATIVO su EEA** (−3,7% / −0,8%); DOT forte ma in decelerazione; LINK volatile.

## Regole di apertura (verificate dallo script, --execute obbligatorio)
1. **Preflight**: zero ordini/posizioni/algo residui; USDC trading ≥ 22,5; minimi e bande
   ok; spread ≤ 50 bps; fee lette dall'account; book con profondità ≥ 5× taglia.
2. **PRIMA la gamba spot, POI la gamba perp** (la copertura si costruisce dal lato lungo).
3. Entrambe le gambe a **LIMITE** (spot: ask+0,2%; perp: bid−0,2%); un solo reprice; mai market.
4. Fill parziale: il residuo si annulla; delta ≤ 1 ct registrato, oltre → completare o chiudere tutto.
5. `set-lever` 1× isolated (fallback cross, registrato); clOrdId idempotenti; ogni passo loggato
   in `data/canary_events.jsonl` + stato in `data/canary_state.json`.

## Costi e attese
- Andata+ritorno ≈ **0,30%** (0,15%/giro) + funding.
- Funding atteso: +0,008–0,011%/8h (~+9÷12%/anno sul nozionale). A questa taglia: **centesimi** —
  il valore del canary è la VALIDAZIONE, non il P&L.

## Monitoraggio (finestra 14 giorni — review il 15/10/2026)
- **Cron ogni 10'** su MARCODG1: `canary_carry.py status --quiet` → log + state JSON (alimenta anche dashboard/Zabbix).
- **Dati vivi**: dashboard `denaro.grivetto.eu` scheda «CANARY C1» (via `/api/infra.json`, staleness 40') · landing `web.grivetto.eu` riga canary · Zabbix: item `svc.canary`, `canary.age_s`, `canary.upl`, `canary.delta_qty` (MARCODG1) + `svc.raccolta`, `raccolta.rows`, `raccolta.age_s`, `svc.fabbrica`, `fabbrica.tick_age_s` (mc2), con trigger attivi.
- Riconciliazione: |spot_qty − |pos|×ctVal| ≤ **1 DOGE**; persistente > 15' → anomalia.
- Funding cumulato < **−0,10%** dal giorno 0 con ultimi 3 eventi negativi → chiusura.
- Mark > **+40%** sopra entry → azione (top-up margine o chiusura controllata).
- Fail ordini ripetuti / errori exchange / mismatch grave → **chiusura immediata + debug**.

## Chiusura
`close`: buy-back perp reduceOnly + sell spot, verifica zeri, riconciliazione finale con numeri
reali. Ogni decisione discrezionale (chiusura anticipata, tagli, reprice extra) si registra con motivo.

## Criteri di avanzamento (review 15/10)
PASS se: riconciliazione senza anomalie persistenti · slippage medio ≤ 10 bps/lato ·
fee effettive = schedule · funding incassato ≥ 90% dell'atteso · zero interventi non registrati.
FAIL → debug, fix, nuovo canary (voce nuova nel registro).

## Autonomia e kill-switch
Eseguito da Hermes (autorizzazione permanente owner, 01/10). Kill-switch: comando `close`
operabile in ogni momento da Hermes; l'owner può ordinare la chiusura sempre.
Artefatti: `prove/C1_canary_carry.*` (log/eventi/stato ai milestone).
