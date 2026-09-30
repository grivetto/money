# Registro degli esperimenti — append-only

**Regola (dal 2026-09-30, review esterna + audit dsh):** nessuna misura senza voce qui,
**prima del primo numero**. Ogni voce dichiara: id · data · ipotesi e meccanismo · dati ·
griglia dichiarata · **numero di varianti provate** · esito (verbatim del cancello) · stato ·
artefatti · hash di dati+codice (quando disponibile).

Le voci non si modificano: correzioni e nuovi tentativi sono **voci nuove** che le supersedono.
Il *conteggio delle varianti* è la materia prima della correzione per selezione multipla (vedi
`coda_catena/M1_release_validazione.md`): va dichiarato onestamente, anche quando fa comodo
non farlo. Un laboratorio che non conta i tentativi non può stimare la probabilità che il
"vincitore" sia un artefatto del caso.

**Avvertenza sulle voci storiche:** tutto ciò che precede il 2026-09-30 è **ricostruito a
posteriori** dagli artefatti in `prove/` e dalla coda. Dove un campo è ignoto: `n/d` — non è
una scusa per ometterlo nelle voci nuove.

**Contatore varianti dichiarate (cumulativo):** storico `n/d` (ricostruzione parziale);
dal 2026-09-30 in poi: **26** (P2: 6 misurate; P6: 6 misurate; P10: 8 dichiarate; P11: 6 misurate — tutte dichiarate prima dei numeri).

---

## Voci storiche (pre-registro, ricostruite)

- **H — RSI mean-reversion** → archiviata. Artefatti: `prove/H_rsi_mean_reversion.*`. Griglia/varianti: n/d.
- **I — Donchian breakout** → archiviata. Con perp: exp +2,47%/anno 180 EUR — sotto le soglie. Artefatti: `prove/I_donchian_breakout.*`. Varianti: n/d.
- **J — Rotazione forza** → **insufficiente** (campione piccolo: mancanza di dati, non merito). Artefatti: `prove/J_rotazione_forza.*`.
- **K — Effetto weekend** → archiviata. Artefatti: `prove/K_effetto_weekend.*`.
- **L — Momentum assoluto 60g** → archiviata (exp netta +2,61%, DD 57% — è la base di P2). Artefatti: `prove/L_momentum_assoluto.*`.
- **M — Capitolazione volume** → archiviata (exp -2,97% con_perp). Artefatti: `prove/M_capitolazione_volume.*`.
- **N — Breakout paniere** → archiviata. Artefatti: `prove/N_breakout_paniere.*`.
- **O — Reversal 2 giorni** → archiviata. Artefatti: `prove/O_reversal_2giorni.*`.
- **trend_lungo** → archiviata (misura principale; dipende dalla cache di alpha-omega-trading: vedi §riproducibilità / P9). Artefatti: `prove/trend_lungo_misura.txt`, `prove/trend_lungo_confronto_evidenza.txt`.
- **griglia_adattiva** → archiviata — **28 prove dichiarate** (misura di soglia, NON una strategia).
- **momento_4h** → esplorativa a 4h; esito n/d. Artefatti: `prove/momento_4h.*`.
- **portafoglio_2026-09-29** → esplorazione del DD di portafoglio (serializzato vs mark-to-market); tutti i rami archiviati. Artefatti: `prove/portafoglio_2026-09-29.*`.

## Voci con spec (`coda_catena/`)

- **P1 — Trend + stop chandelier** (2026-09-27) → archiviata: ipotesi smentita; A/B interno vs Donchian 6/8; exp -0,70% (con perp). Griglia: A/B 2 varianti dichiarate; storico n/d. Artefatti: `prove/P1_trend_atr_stop.*`, `prove/P1_pilota_btceth_2019.*`.
- **P2 — Momentum + vol targeting** (misurata 2026-09-30, dsh+Hermes) → **ARCHIVIATA per costruzione**: nessuna delle 6 configurazioni dichiarate porta il DDport ≤ 25% (controllo 42,8%; vt=0,50/0,60/0,75 → 46,8/47,5/41,7%). Il sizing riduce il DD *serializzato* (47,0% → 37,6% a vt=0,50) ma NON il DD di portafoglio mark-to-market: il DD è una proprietà di portafoglio (concorrenza + correlazione tra simboli), non del singolo trade. Il controllo riproduce il riferimento A/B (check OK). Artefatti: `prove/P2_vol_target.{txt,json}`; misura: `scripts/misura_p2.py`; test del gancio: `tests/ricerca/test_portafoglio_esp_variabile.py`.
- **P3 — Filtro SMA200** (2026-09-29) → archiviata: t 1,58 · DD 45,5% · exp +9,01%/op = 16,4× pedaggio · IC90 [+0,10%, +19,12%]; bocciata SOLO da t e DD. Varianti: A/B 6/8 dichiarate. Artefatti: `prove/P3_trend_filtro_200g.*`.
- **P4 — Funding carry** → parcheggiata: storia funding EEA ≈ 96 giorni, non misurabile; si accumula con P8. Spec: `coda_catena/P4_funding_carry.md`. **30/09 prima lettura triage (NON misura, regime singolo)**: +5,09%/anno lordo medio sui 5 major, 83-92% periodi positivi (BTC/DOGE/ETH), rientro costi 32-68 gg — artefatti `prove/P4_triage_carry_2026-09-30.*`.
- **P5 — Donchian universo esteso** (2026-09-28) → archiviata: 407 coppie scansionate → 61 misurate; l'allargamento diluisce (t 1,44; DD 98,9%; IC90 [−0,28%, +8,93%]). Varianti: 61 misurate (su 407 scan). Artefatti: `prove/P5_universo.json`, `prove/P5_donchian_esteso.*`.
- **P6 — Livello portafoglio (cap concorrenza/correlazione)** (misurata 2026-09-30, hermes) → **ARCHIVIATA per costruzione**: nessuna delle 6 configurazioni dichiarate porta il DDport ≤ 25% (migliore `mp=2 fifo` a 37,8%, con expectancy del campione eseguito NEGATIVA; `mincorr` riduce il DD serializzato fino a 19,6% ma non il DD di portafoglio: 38,4-42,3%). Controllo OK. Griglia: `{max_posizioni: 2,3,4} x {fifo, mincorr}` = **6 varianti**; segnale fisso Donchian 55/20; successo: DDport ≤ 25% E exp ≥ 3× pedaggio. Artefatti: `prove/P6_portafoglio.{txt,json}`; misura `scripts/misura_p6.py`; gancio motore `filtro_ingresso` (test `tests/ricerca/test_portafoglio_filtro_ingresso.py`).
- **P7 — Economia della soglia** → **chiusa** (2026-09-30): superata da P6 (famiglia trend archiviata per costruzione); le domande economiche confluiscono in E1. Spec mai materializzata.
- **P10 — Momentum cross-sectional long/flat** (registrata 2026-09-30) → assegnata a dsh (handoff). Griglia: `{k: 2,3} x {L: 60,120} x {R: 7,14}` = **8 varianti** dichiarate (selezione solo su addestramento; verifica unica). Artefatti attesi: `prove/P10_*`.
- **P11 — Volatility breakout ATR** (misurata 2026-09-30, hermes) → **ARCHIVIATA per costruzione**: la configurazione scelta in addestramento (k=2,0 / m=20; exp netta training +147,98%/op, n=68) in VERIFICA dà DDport **77,2%** ed expectancy (eseguita) **-4,60%** (copertura -8,4x; t -0,68; giudica: archiviato) → fallisce DDport ≤ 25% E exp ≥ 3x pedaggio. Finestra piena: DDport 77,2%, exp +25,24% (cop 45,9x) — fallisce comunque il DD. Griglia: `{k: 1.0,1.5,2.0} x {M: 10,20}` = **6 varianti** dichiarate prima dei numeri; selezione solo su addestramento (n ≥ 30). Nota di pipeline: dd_ser/dd_port identici fra le due finestre = spiegato e verificato (l'episodio peggiore è nella coda comune; pesi 0,25 → decisioni scala-invarianti; debug trade-by-trade OK). Artefatti: `prove/P11_vol_breakout.{txt,json}`; misura `scripts/misura_p11.py`. Integrazione: 2 fix in review + allineamento a `money.dati.Barra` (massimo/minimo) con test di regressione.

## Infrastruttura (non strategie — non consumano gradi di libertà di ricerca)

- **P8 — Raccoglitore funding/basis** → integrato 2026-09-29 (`src/money/raccoglitore_funding.py`, 9 test nella suite). Append-only idempotente, guardia anti-ordini. Tabella giornaliera (P8B) consegnata da A0-MC2 e integrata 30/09: `src/money/report_funding.py` + 9 test (review Hermes).
- **P9 — Verificatore di provenienza `prove/*`** → integrato 2026-09-30 (`src/money/verifica_provenienza.py`, 10 test). Primo uso previsto: pin dell'hash della cache dichiarata (la cache di `trend_lungo` è su Windows: il manifest va generato lì o la misura rifatta sui dati mc2).
- **E1 — Economia unitaria (scheda costi + cost-to-edge + benchmark)** → **integrato 2026-09-30** (`src/money/economia.py`, 7 test; consegna A0-PC, review Hermes). Non consuma gradi di libertà di ricerca. Prossima applicazione: misure P6/P10 (scheda economica accanto al verdetto).
- **C1 — Canary carry DOGE (esecuzione minima reale)** → **APERTO 2026-10-01 00:43**: spot 109,89 DOGE + short 11 ct X-Perp DOGE (leva 1× isolated); delta gambe 0,11 DOGE; fee reali = schedule (spot 0,10% in DOGE, perp 0,05% in USDC, conversione 0%); riconciliazione OK. Spec: `docs/16_canary_carry_2026-10-01.md`. Finestra 14g, review 15/10. Artefatti: `prove/C1_canary_carry_open.*`; ops: `scripts/canary_carry.py` + cron status 30' su MARCODG1.

## Registro variazioni

- 2026-09-30 — creato: ricostruzione storica + regola append-only + contatore varianti.
- 2026-09-30 — P9 integrato; verificatore di provenienza disponibile in `src/money/`.
- 2026-09-30 — P2 misurata e archiviata per costruzione (sizing: DD serializzato giù, DD portafoglio invariato/peggiore).
- 2026-09-30 — P6 misurata (6 varianti) e archiviata per costruzione: cap di concorrenza e filtro di correlazione riducono il DD *serializzato* ma non il DD di portafoglio sotto il 25% (migliore 37,8%, expectancy eseguita negativa). Controllo riproduce il riferimento P2.
- 2026-09-30 — P7 chiusa prima della materializzazione (superata da P6); lane attive: E1 (economia unitaria), P10 (dsh), P8/funding (raccolta).
- 2026-09-30 — P8B consegnato (A0-MC2) e integrato: `src/money/report_funding.py` + 9 test (review Hermes). Tabella giornaliera funding pronta per il controllo della raccolta.
- 2026-09-30 — P11 pre-registrata (volatility breakout ATR, 6 varianti): implementazione ad A0-PC, misura hermes. Direttiva proprietario: portare la produzione a x5 (fabbrica a 1', piu' lane parallele).
- 2026-09-30 — Fabbrica portata a x20 (direttiva proprietario): tick 15s via timer systemd (units versionate in `deploy/systemd/`), watchdog anti-silenzio (cron 1'), banco ogni 20 tiri.
- 2026-09-30 — Prima lettura TRIAGE del carry/funding (non misura): +5,09%/anno lordo medio sui 5 major, 83-92% periodi positivi sui major; costo di ciclo 0,62%; serve alla decisione (accumulo + X-Perps + capitale). Artefatti `prove/P4_triage_carry_2026-09-30.*`.
- 2026-09-30 — Incidente A0-MC2 risolto: contesti nuovi nascevano col preset Default su google/gemini con chiave vuota; chiave Gemini di `money/.env` VALIDA ma con credito prepagato ESAURITO (402) → Default riportato a OpenRouter; chiave installata per il futuro.
- 2026-09-30 — J1 job-store integrato: `fabbrica/jobs.py` (lease/dedup/retry, WAL) + `tests/test_fabbrica_jobs.py` (10/10, verificati da Hermes); wire nel tick prossimo.
- 2026-09-30 — P11 modulo integrato: `src/money/ricerca/vol_breakout_atr.py` + test 7/7 dopo 2 fix in review (frammento di log nel file consegnato; caso float del test soglia riscritto con valori binari esatti); misura hermes in corso.
- 2026-09-30 — P11 MISURATA e **ARCHIVIATA per costruzione** (verifica: DDport 77,2% > 25%; exp eseguita -4,60% < 3x pedaggio; selezione k=2,0 m=20). Numeri identici fra finestre = verificati genuini (episodio peggiore nella coda comune, decisioni scala-invarianti — debug dedicato). Integrazione chiusa: allineamento a `money.dati.Barra` (massimo/minimo) + test di regressione (8/8). Artefatti `prove/P11_vol_breakout.*`.
- 2026-09-30 — Lane aggiornate: P11 archiviata; hermes → dossier X-Perps (decisione owner) + sorveglianza P10; A0-MC2/A0-PC liberi (J1 e P11 integrati); prossimo della coda: P12 (4h + regime, coda dsh) o filone funding quando i dati maturano.
- 2026-10-01 — **X-Perps API SBLOCCATE**: chiave nuova creata sul contesto MAIN (read+trade, senza withdraw); chiavi vecchie/fuori-contesto = `50124`; il transfer funding→trading richiede il permesso Withdraw (chiave treasury separata). Raccoglitore P8 schedulato (cron 4h; backfill 2692 righe; prima rivelazione: funding EEA ≠ globale — BTC/ETH NEGATIVI su EEA).
- 2026-10-01 — **C1 canary carry DOGE pre-registrato e APERTO** (spot 109,89 + short 11 ct, 1× isolated; fee reali = schedule; delta 0,11): prima esecuzione reale spot+perp del progetto via API. Review 15/10.
