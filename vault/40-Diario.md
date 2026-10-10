# Diario del progetto

## 2026-09-27 — La coda e il primo "6/8"
- Costruita la coda `coda_catena/` (spec P1–P4) e riorganizzato il canale DSH.
- P1 (chandelier ATR) misurata e archiviata: lo stop in uscita **peggiora** tutto.
- Nell'A/B di P1 la scoperta: **Donchian su 10 majors USDT = 6/8 criteri** (IC90 positivo per la prima volta nel progetto).

## 2026-09-28 — P5, il ridimensionamento onesto
- P5 (Donchian su 61 coppie): l'edge **non regge** l'allargamento (t 1,44; DD 98,9%). Meglio saperlo ora.
- Agent Zero riparato e messo al lavoro su P3. P4 parcheggiata (funding: 96 giorni di storia).

## 2026-09-29 — P3 e la sala di controllo
- Consegna P3 di Agent Zero: non valida (bug bloccanti). Hermes riscrive il modulo → 10 test nuovi → suite **218/218** verde.
- P3 misurata: di nuovo **6/8**. Expectancy +9,01%/op (16,4×), IC90+, PF 2,01 — ma DD 45,5% e t 1,58. **Il filtro di regime non doma il DD.**
- Creata questa sala di controllo (vault Obsidian, mc2 + Windows).

## 2026-10-03 — La squadra al completo
- **DSH ora gira anche su mc2 come servizio** (`dsh-web` :3080, systemd; headless collaudato con PONG-MC2): esecutore in più, in casa.
- **Nodo agenti a 3 esecutori**: opencode ricollaudato (PONG-OC) + **agy/Antigravity** in squadra.
- Foto della squadra: `money/FOTO_SQUADRA_2026-10-03.png` (8 esecutori + regia, su 3 macchine).
- Contorno: canary C1 in validazione (review 15/10) · capitale ≈1.100 € · P10 "insufficiente" (23<30 op).
- Pomeriggio: **sistemati i nomi host** (il desktop si annunciava come `mc2` — collisione col server → ora **omarchy**) e **DSH su omarchy riconfigurato**: servizio stabile `dsh-web` (:3080, avvio automatico, accesso via tunnel ssh) al posto delle istanze manuali.

## 2026-10-03 sera — P14 chiude il filone momentum; la squadra consegna
- **P14 (momentum cross su universo ampio) MISURATA → archiviata**: 58 simboli, verifica exp −1,93%, DD 73,3%, t −0,47 → 7/8 criteri KO. Con P10 "insufficiente", il filone momentum cross si chiude **con potenza adeguata** (l'allargamento d'universo non salva l'edge — P5 docet).
- **C1REV** (pack review canary) consegnato da A0-win, integrato (`scripts/canary_review.py`, 5/5) e deployato su MARCODG1 — pronto per il checkpoint del **15/10**.
- **Incidente provider risolto**: credito Google degli A0 a secco (402) → preset spostati su `openrouter/deepseek-v4-flash`; un file troncato recuperato via snapshot `_time_travel`.
- Sistemato l'**A0 Launcher di omarchy** (crash all'avvio: sandbox su FUSE senza SUID → wrapper `~/.local/bin/a0-launcher` con `--no-sandbox` + voce di menu; docker abilitato al boot).
- **Porte DSH standardizzate** (direttiva proprietario): win `3080` · mc2 `dsh-web` **4080** · omarchy **5080** — unit aggiornati e riavviati con backup `.bak-20261003`; 3080 non più occupata da mc2/omarchy.

## 2026-10-04 — opencode su tutta la flotta
- **opencode su 4 nodi** (mc2, omarchy, nuvola, MARCODG1 — v2.0.22, PONG ovunque): flotta a **11 esecutori su 4 macchine + regia** (docs/21).
- Costi ricorrenti censiti (docs/22): 9 €/mese VPS + ~22 €/mese Google AI Pro.
- Regola di flotta: **modelli solo online** (niente inference locale).

## 2026-10-06 — Ricostruzione MARCODG1, revisione Manus, scansioni S1/S2
- **MARCODG1 ricostruito** (kit `ricostruisci-marco.sh`): crontab → money, credenziali Zabbix ruotate, stack servizi money riallineato; post-ricostruzione verificata.
- **Revisione esterna Manus applicata** (Sprint 0/1/2): esecuzione fail-closed + clOrdId per intento + journal; fabbrica job-store atomico + shell=False; cancello con dipendenza temporale (IC a blocchi, t HAC). Suite 558.
- **Migrazione "casa unica = money", fase 1**: osservabilità e alerting portati in money su mc2/MARCODG1/nuvola (aggregator, dashboard, health, watch_alerts, banco); alpha-omega dismesso come casa.
- **S1 (scansione esplorativa)**: 7 famiglie × 32 config su 16 major → **0 candidati**; descrittivi mom_abs XLM/XRP/DOGE.
- **Contro-verifica indipendente S1 (DSH omarchy)**: numeri riprodotti al 7º decimale; `rsi2(3,15,65)` su XRP l'unico robusto → **watchlist**.
- **S2 (scansione funding carry X-Perp)**: 7 candidati descrittivi lato short (DOGE +6,50%, LINK +6,33%, ADA +6,33%, …); nessuna promozione — da pre-registrare come esperimenti.
- P4/P8 retrofit formato-contratto; canary funding check normalizzato; costi = verità del conto (`okx_eea_con_perp`).

## 2026-10-07 — S3 caccia adattiva; aiutanti tutti in auto-start
- **S3 "caccia adattiva"**: griglia estesa (10 famiglie, 61 config) + raffinamento locale (±1 passo), DSR sull'unione dei tentativi → **0 candidati** (1.760 tentativi su major; 6.902 su universo ampio/58 simboli). Il loop notturno ora esegue **S1+S3**.
- **Flotta in auto-start**: opencode → servizio systemd (`Restart=always`) su **tutti e 4 i nodi**; **agy** (remote-control) daemon su tutti e 4; win: DSH-Web sotto Task Scheduler con restart automatico; `dsh-bridge` su mc2 disabilitato (residuo storico).
- **Accesso win sistemato**: chiave SSH per utente admin va in `C:\ProgramData\ssh\administrators_authorized_keys` (per gli admin Windows ignora `~/.ssh/authorized_keys`).
- Test di resilienza kill→restart passati su tutti i nodi per opencode e agy.
- Hermes: installati plugin utili (ticker crypto desktop, fxmacrodata, echarts).

## 2026-10-08 — S4 «caccia continua» in cron; omarchy ricompletato; landing «trading»
- **S4 «caccia continua» attivata** (direttiva proprietario: «ricerca di un edge nuovo e funzionale ogni 10 minuti»): lotto di 96 configurazioni MAI testate dal vicinato dichiarato dei semi S1/S3 (156.005 config totali), best-first sull'addestramento, DSR cumulativa con ricontrollo/declassamento dei candidati; ~3 s a giro su mc2; evidenza `prove/caccia_continua/`; liveness nel watchdog (`watch_alerts check`, ferma >45′ = allarme).
- **omarchy post-ricostruzione, servizi ricostituiti**: `dsh-web.service` :5080 (fix della unit rimasta a :3080 nel repo), `opencode.service`, `antigravity-cli-daemon` (agy, linger on), docker + agent-zero `unless-stopped`; smoke: PONG su DSH headless, opencode, agy.
- **Trovato e corretto su omarchy**: un opencode stantio 1.18.35 (mise) mascherava il v2.0.24 ufficiale via PATH (errore sul db v2) → rimosso da mise, `~/.local/bin/opencode` → symlink al binario ufficiale.
- **Landing**: nuovo sfondo a tema trading (`TRADING_2026-10-08.html/.jpg`), overlay alleggerito a due strati — candele/curva/ticker visibili e testo leggibile; live su web.grivetto.eu.

## 2026-10-10 — S4 raddoppiata; priorità ricerca edge
- **S4 «caccia continua»: cadenza raddoppiata** (direttiva proprietario: «diamo priorità alla ricerca di edge buoni e validi, raddoppia il cron»): da `*/10` a `*/5` su mc2 (~288 giri/giorno, ~46.000 config/giorno a lotto 160); watchdog liveness 45'→25'; metodo/DSR/spazio invariati. Stato: 315 giri, 316k valutabili, 5.214 papabili, 0 candidati; saturazione stimata ~2–3 giorni.
- **Verifica post-avvio (10/10, 06:15–07:00Z)**: 10 tick consecutivi ogni 5' esatti (scarto max ~5 s), 0 buchi; il rallentamento del contatore `cumulativi` è fisiologico — la frontiera attraversa la coda dello spazio (fasce a finestre estreme quasi mai valutabili: `donchian n_in`≥100 → 0/2.689; `ema fast`≥20 → 0/6.440), non un guasto; coerenza `somma stat.n` ≡ contatore verificata (316.104). Lezione registrata in skill.

## 2026-10-11 — Landing: il trading su denaro.grivetto.eu, la squadra dev su web.grivetto.eu
- **Split delle vetrine** (direttiva proprietario): la pagina «il trading» passe da web.grivetto.eu a **denaro.grivetto.eu** (root = landing trading; la dashboard Neon Grid resta su **/dashboard**, verificato 200); su **web.grivetto.eu** va **la squadra dev** — nuova home con la **foto delle squadra** come sfondo (immagine generata, `squadra-dev-2026-10-11.jpg`) e il roster: HERMES, A0 ×2, DSH ×3, opencode ×4, agy ×4, FABBRICA.
- **serve_dashboard.py v2.1**: route `/` → landing (nuovo `DASH_LANDING_FILE`, default `landing.html`), `/dashboard` → Neon Grid; asset statici (`ASSET_ROUTES`) per lo sfondo; fix `_send` (header non più duplicati); `healthz` ora riporta `landing`/`landing_exists`. Test su :8999 prima del deploy; backup della versione precedente su MARCODG1.
- **Favicon trading su denaro.grivetto.eu**: nuova `favicon.svg` (candele neon + trend) — prima era 404. Live e verificata.
- **Grafana**: link «Dashboard Money» aggiornato → `denaro.grivetto.eu/dashboard` (la root è la landing).
- Verifiche post-deploy: `denaro.grivetto.eu/` = landing trading · `/dashboard` = Neon Grid · `/favicon.svg` 200 · `/api/infra.json` 200 · `web.grivetto.eu/` = squadra dev · sfondo squadra 200. Screenshot in `report/landing_2026-10-11/`.

## 2026-10-11 (notte) — «Il sito mostra solo 120 €»: buco di lettura (terzo comparto), guardie equity
- **Segnalazione proprietario** («denaro.grivetto.eu mostra solo 120€?»): NO, non era corretto. Dopo lo spostamento di ~1.061 € in Simple Earn, l'aggregator leggeva solo trading+funding: equity mostrata ~120 vs **~1.100 reali**; stesso buco nell'exporter (Grafana main=20,14) e quindi su Zabbix/trend. Fondi sempre al sicuro: buco di LETTURA (comparto savings), non di capitale.
- **Fix (3 nodi + sito, verificato)**: aggregator mc2+MARCODG1 e `denaro2/exporter.py` (mc2/MARCODG1/nuvola) sommano **trading+funding+savings** (`privateGetFinanceSavingsBalance`, retry, flag `savings_ok`; nuovo gauge `denaro_equity_real_partial`); `okx_ops.py saldi` allineato; trend ricostruito (36 punti interpolati, backup `.bak-20261011`); patch exporter versionata in `ops/tools/patch_exporter_equity_savings.py`.
- **Verifica**: `denaro.grivetto.eu/dashboard` = **1.100,30 €** (hero + breakdown per conto); Zabbix `project.equity` = 1.100,3; Prometheus `main` = 1.100,17; 0 problemi attivi su Zabbix/Prometheus.
- **Guardie anti-ricaduta**: trigger Zabbix «Money: equity crollo (>30% vs media 24h)» (id 26304) + modo `watch_alerts.py equity` (*/10 su mc2: crollo <70% del max 24h, letture per-conto incomplete, total assente; anti-spam 6h) + 6 test (`tests/test_watch_alerts_equity.py`). Lezione in skill: **i comparti OKX sono TRE**.
