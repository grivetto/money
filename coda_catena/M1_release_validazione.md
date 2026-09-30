# M1 — Release di validazione (milestone, non strategia)

**Origine:** review esterna (Manus, 2026-09-30) + audit dsh. **Obiettivo:** rendere il
protocollo di validazione più forte del "cancello v1" **prima di qualunque live**. La
prossima milestone è una release di validazione statistico-economica, non una nuova strategia.

**Regole di M1 (governance):**
- coda ammessa: P6 (in misura), P7, P10 (assegnata a dsh) + nuove famiglie SOLO pre-registrate;
- budget esperimenti: **max 2 famiglie nuove a settimana**, fino a 3 lane di lavoro in
  parallelo (direttiva proprietario 30/09: accelerare il ciclo crea→testa). Ogni famiglia
  registrata in `prove/REGISTRO_ESPERIMENTI.md` **prima** del primo numero; il maggiore
  throughput si compensa col DSR/PBO (item 4) sui criteri di promozione;
  `prove/REGISTRO_ESPERIMENTI.md` **prima** del primo numero (anti-overfitting da throughput);
- il miglior risultato non si mostra prima dell'aggregato completo dell'esperimento;
- ogni artefatto deve essere riproducibile: hash di dati+codice (abilitati da P9);
- nessun agente può cambiare insieme strategia, dati e cancello; un agente propone
  eccezioni, non le autorizza.

## Items

1. **Registro esperimenti** — `prove/REGISTRO_ESPERIMENTI.md` — ✅ fatto (2026-09-30,
   ricostruzione storica + regola). Acceptance: ogni misura futura cita la voce di registro
   con il N. di varianti dichiarato.
2. **Allineamento cancello ↔ mandato** — proposta: il mandato operativo (DD −10%, stop
   giornaliero −3%) resta **hard**; il DD del cancello (25%) è declassato a **diagnostica**;
   nuova condizione di promozione: **al sizing di deploy il DD di portafoglio storico ≤ 10%
   E l'economia (pedaggio + criterio €) ricalcolata a quel taglio**. ⏳ attende OK proprietario.
3. **Block bootstrap** — IC90 con moving/stationary bootstrap nel cancello (o modulo
   `statistica`): blocchi dimensionati sulla durata tipica della dipendenza + sensitivity;
   bootstrap anche sui rendimenti giornalieri di portafoglio, non solo sui trade. Il
   t-statistic resta descrittivo finché l'errore standard non è corretto per dipendenza.
   ⏳ da implementare (+ test).
4. **Correzione selezione multipla** — Deflated Sharpe Ratio (o equivalente) + PBO/CSCV
   alimentati dal registro. ⏳ da implementare (+ test); applicata alle misure future.
5. **Scenari costi standard** — 3 scenari in ogni misura: favorevole / centrale / stressato
   (spread+slippage ×2, fill maker peggiorati). Un sistema non passa se profittevole solo
   nello scenario favorevole. ⏳ da integrare negli script di misura.
6. **Stati gerarchici** — insufficiente (<30 op) → candidata (≥30, meccanismo plausibile,
   **nessun capitale reale**) → validazione (≥100-150 op o pluriregime) → promovibile
   (robustezza completa) → canary → produzione limitata. ⏳ modifica al protocollo (+ cancello).
7. **Holdout finale** — segmento mai letto fino al congelamento della strategia. Nota onesta:
   l'OOS 2024-06→oggi è già stato letto più volte (contaminato come holdout comune): la
   proposta è smettere di leggerlo da ora per il candidato che si congela. ⏳ da formalizzare.
8. **Risk engine aggregato** — visione aggregata sopra i conti (cap per asset/fattore, cap di
   correlazione **sui rendimenti**, non sulle etichette), max 1-2 strategie live nella prima
   fase. La separazione dei conti deve limitare il rischio, non nascondere una singola
   scommessa sullo stesso regime. ⏳ design.
9. **Checklist guardrail live** (5 punti Manus §6) come gate di deploy: permessi/segregazione ·
   riconciliazione autoritativa · idempotenza ordini (client ID deterministico) · risk engine
   + kill switch · circuit breaker con escalation. ⏳ checklist + priorità.
10. **Protocollo canary** — sizing minimo; criteri di promozione canary→capitale (slippage,
    mismatch simulato vs reale, latenza, errori, DD, rendimento netto); aumento capitale solo
    dopo un periodo minimo e mai su un singolo risultato positivo. ⏳ bozza.
11. **P2 addendum pre-numero** — secondarie dichiarate prima della misura (costi stressati,
    coerenza regimi, attrattività vs controllo). ✅ fatto (spec aggiornata).
12. **P9 verificatore di provenienza** — chiude il difetto di riproducibilità dell'audit dsh.
    ✅ integrato 30/09: `src/money/verifica_provenienza.py` + 10 test in suite. Prossimo uso: pin
    dell'hash della cache dichiarata — nota: la cache di `trend_lungo` vive su Windows (C:\dev\...) →
    il manifest va generato lì, o la misura rifatta sui dati mc2.

## Criteri di chiusura M1 (per dichiararla fatta)

- items 1-6, 9-10 completati e testati;
- ogni misura effettuata da M1 in poi: registrata, con varianti contate, IC dipendenza-aware,
  scenari costi, esito con numeri;
- il primo eventuale "promovibile" passa dall'intero protocollo prima del canary.
