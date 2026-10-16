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

## 2026-10-12 — Ricerca: chiusi microstruttura, on-chain e sentiment; carry misurato; canary nel cancello
- **Microstruttura chiusa** (spread reale Bybit+Bitvavo, order-flow multi-giorno, simulatore di market making su tick reali): esito negativo; i dati tick Bybit (5+ anni) restano riusabili.
- **On-chain e sentiment**: nuova classe di dati testata e bocciata dal walk-forward.
- **Multi-timeframe** (1d/4h/1h): 0 candidati su tutti i timeframe.
- **Carry funding delta-neutral misurato su 96 g (netto fee)**: non batte l'Earn a rischio comparabile → carry solo regime-dipendente (a soglie), mai always-on.
- **Canary C1 nel cancello**: gate unico fail-closed + stop ATR obbligatorio (su 1d) + kill switch — stesso percorso dell'Esecutore.
- Bilancio del filone esplorativo: **6 arene × 59 simboli su 5+ anni → 0 edge validato**; nessuna promozione forzata.

## 2026-10-13 — Audit senza pietà; sorveglianza funding; RDP di omarchy
- **Audit del progetto (13/10)**: 11 lacune + piano E1–E4 per chiuderle — doc in repo; prima di qualunque scala si sistemano le fondamenta.
- **funding_watch X-Perp**: sorveglianza read-only degli X-Perp (i 60 più liquidi) con soglia e alert Telegram (cooldown 6h; 8 test; cron orario su mc2) — dice QUANDO il carry torna conveniente. Verificata end-to-end.
- **omarchy**: RDP riparato end-to-end (xrdp + xorgxrdp 0.10.5 + Xfce4 → sessione X11 su :10) — procedura in skill `omarchy-rdp`.

## 2026-10-14 — Fix audit atterrati; pannello agenti; KDE di omarchy; Kaggle TPU in coda
- **Fix della notte 13→14**: banco a secco legge anche Simple Earn; cancello (via la doppia sottrazione del pedaggio); giudice statistico (DSR sulla finestra di selezione); fix #4 audit (rischio misurato sullo STOP) + doc di stato fix.
- **Pannello agenti** read-only (Hermes/A0/opencode/agy/DSH su 5 nodi) → `/agenti` in dashboard + `/api/agenti.json`; **dev_platform** estesa (Hermes ×2, 16 operai) + trigger Zabbix «Operaio giù».
- **omarchy / KDE**: sistemati Welcome Center e il ripristino-sessione che riapriva le Impostazioni a ogni login (`ksmserverrc` → `loginMode=emptySession`).
- **Kaggle free AI (account sgrivett)**: abilitato (telefono + Persona) — TPU v5e-8 20 h/sett + GPU 30 h/sett; kernel `qwen38-tpu-serve` (kaggle-tpu-lab; Qwen3.8-27B bf16; endpoint OpenAI-compatibile) **in coda per uno slot TPU** (carenza piattaforma; l'attesa non consuma quota). Quando parte: URL+key su mc2 (`~/kaggle-tpu-lab`) — skill `kaggle-free-ai-server`.
- **JEV**: gate verificato live (ping 14/10 → jev-1.13.0); in attesa di spec attive in coda (ultimo giro reale 08/10).

## 2026-10-15 — Siti: la squadra assorbita in /squadra; doppioni in 301; Grafana dietro Access
- **Vetrina riorganizzata** (direttiva owner: brand **Denaro**, zero storytelling): la pagina della squadra è ora **denaro.grivetto.eu/squadra** (route in `serve_dashboard.py`, pagina brandizzata, sfondo `squadra-dev-2026-10-11.jpg`); landing e footer linkano `/squadra`.
- **web.grivetto.eu ritirato**: 301 Cloudflare → denaro.grivetto.eu/squadra (origin: stub di fallback su MARCODG1, backup `index.bak-20261015.html`).
- **Doppioni legacy**: home.grivetto.eu → 301 denaro.grivetto.eu/ · dashboard.grivetto.eu → 301 denaro.grivetto.eu/dashboard (vhost nginx su mc2 + tunnel cloudflared-home ripuntato).
- **Grafana dietro Cloudflare Access** (come Zabbix): app Access «grafana» con policy email (sergio.grivetto@gmail.com + sergio@grivetto.eu); verificata pubblica (302 → login Access).
- **Kitchen Lab**: link aggiornato a denaro.grivetto.eu/squadra.
- Note operative: il pubblico è servito da **MARCODG1** (`money-dashboard-marcodg1` :8913, `money-landing-marcodg1` :8914); mc2 ha le copie speculari — dopo un commit, `git pull` + restart del servizio su MARCODG1. Doc completa: `docs/30_siti_e_domini_2026-10-15.md`.

## 2026-10-15 (2) — Fix 5: S4 fermata, MOSAICO4 sbloccata, tree ripulito
- **S4 «caccia continua» fermata**: esaurita dal 12/10 (run 1070; 156k viste; 0 candidati); il tick */5 scriveva solo «spazio esaurito — niente da fare» e il cron è stato **commentato** su mc2 (canonico `deploy/cron/crontab-mc2.txt` riallineato al live). Riattivare SOLO con una nuova dichiarazione dello spazio (S5). Il watchdog liveness resta: `esaurito` = fine corsa, non allarma.
- **MOSAICO4_v1 sbloccata**: retrofit formato-contratto (contenuto scientifico invariato) — repo/commit, input/output, criteri, fuori scope, verifica → lint **7/7**; il job `spec_fix` fermo da 4 giorni in fabbrica si è chiuso da solo al tick successivo (job-store: coda 0).
- **Tree git ripuliti**: `ops/dashboard/scommessa.json` fuori dal versionamento su tutti i nodi (churn rigenerato ogni 10' — stesso trattamento di `agenti.json`); su MARCODG1 archiviati i residui (`C1_review.json/md` simulati del 06/10, `.bak` del dashboard dell'11/10, `canary_state.json` orfano in `scripts/`).
- Verifiche: spec_lint 7/7 · suite completa verde · `crontab -l` live ≡ canonico · fabbrica job chiuso · `git status` pulito su mc2/MARCODG1/nuvola.

## 2026-10-16 (2) — Verifica post-riavvio mc2 (owner): tutto OK; stato trading a 1.097 €
- **mc2 riavviata ~18:39–18:44** (uptime precedente 1g18h; probabile riavvio manuale). Risalita completa: `postboot_check.sh` **49 OK · 0 problemi**; sshd/tailscale/docker/zabbix/money-*/denaro-node-mc2 all up; hardening MC2HARD applicato al boot (3389 inclusa → solo LAN/Tailscale); xrdp attivo.
- **Equity riconciliata: ≈1.097,4 €** (OKX main 1.097,25 + dust subs 0,09; source=balances, `unpriced` vuoto). Comparti: trading 368,7 · funding 194,5 · Simple Earn 534,6. Banco a secco: ultimo run **PASS** (`riconciliazione_quadra: si`, `ordini_aperti: 0`, chiave read_only).
- **Trading: tutto paper** — 13 bot running (7 mc2 + 6 nuvola), 0 live, 0 trade oggi. Uniche posizioni reali: canary C1 DOGE (delta-neutral, net ~+0,05 USDC, funding cumulato 117,9% del minimo atteso) e carry DOT+ADA (nozionale 179,8 €, UPL +0,36 €, aperti 15/10 23:00Z).
- **Alert**: `~/.denaro_alerts/sent.log` — ⚠️ hermes-gateway inactive 18:40 + ✅ rientro 18:45 (transitorio del riavvio, comportamento atteso); state/spool puliti. Digest giornaliero regolare.
- **Siti**: denaro.grivetto.eu 200 (+`/agenti` ok); web.grivetto.eu 301 (atteso). Zabbix web/server/db attivi.
- **Nota tecnica per la prossima sessione**: le card `mc2:okx:*` nel payload master sono legittime (blocco di completamento che le riempie dai file paper quando il path legacy manca — stesso ts delle card `*:paper:*`). Sul master ci sono **+62 righe NON committate** in `infra_aggregator.py` (alias BETH→ETH per l'equity: +4,95 USDC non contati prima; sezioni `ricerca`/`carry`): committare e riallineare le copie. Residui minori: `node_stale_bots: [mc2:unknown]` (glob generico cattura file non-bot), unit utente `app-pulseaudio@autostart` failed (cosmetico, PipeWire).

## 2026-10-16 (3) — Decisione owner: si resta in $; visibilità sul cambio attivata
- **Decisione**: capitale in USD (USDC/Earn), niente conversione EUR. Il calo dal picco (1.108,3 → ~1.097) è ~95% cambio $→€ (tasso 0,8997→0,8910 in 2 gg) — fee totali di sempre €1,51, PnL realizzato 0,00, tabellone +28,75 vs versato.
- **Attivato** (`ops/alerts/watch_alerts.py`): (1) digest 9:00 con **Δ24h/Δ7g scomposti "cambio vs resto"** (serie banco 5' via ssh, `_attribuzione`); (2) **soglia-campanello 1.090 €** nel check equity (ogni 10'), messaggio col motivo; attiva solo fuori dal regime di crollo; anti-spam 12h. Test: `tests/test_watch_alerts_delta.py` + suite 726/726 verde.
- Nota: Δ7g compare quando la finestra a 7 giorni non copre più il periodo pre-riordino (tasso leggibile solo dal 14/10) — self-heal ~21/10.

## 2026-10-16 (4) — Pulizia del repo (owner): una foto per famiglia, aggiornate a oggi
- **Restano nel root (nuovi, dati live di stasera)**: `FOTO_SISTEMA_2026-10-16.png` · `FOTO_SQUADRA_2026-10-16.png` · `ARCHITETTURA_2026-10-16.md` (equity ≈1.096 € · 13 bot paper / 0 live · 16/16 operai · postboot 49/49).
- **Rimosse 24 voci datate/duplicate**: FOTO_SISTEMA 01–03/10 ×6 · FOTO_SQUADRA 03–07/10 ×4 · ARCHITETTURA 30/09–01/10 ×4 · dash_*.png ×4 · TRADING_2026-10-08 ×2 · landing_v2.png · BRIEF_MANUS ×2 · copia orfana `squadra-2026-10-07.png` nel kit landing. Recuperabili in git history (commit `2530aad2`) e nel backup `/tmp/denaro_pulizia_backup/` su mc2.
- **Riferimenti aggiornati**: README ×4 (it/en/es/th), `docs/17`, `SCHEDA_PROGETTO`, `vault/20-Squadra` (+ `.gitignore`: `*.egg-info/`). Regola d'ora: **una sola versione corrente per famiglia nel root**; le storiche si consultano in git.
- Committati anche gli artefatti di ricerca di stanotte (scansioni S1/S3 + registro, commit `ecafd7ce`). Lasciati apposta: `docs/manus_2026-10-06/` (bundle analisi esterna), `legacy/`, e i non-registrati P20 (market-making Bitvavo — tutti `passa:false`).
- Follow-up (stessa sera): sezione «Status» dei 4 README riallineata a oggi (726 test · capitale ≈1.096 € · C1 review PASS + carry DOT+ADA · S4 esaurita · 16/16 operai · postboot 49/49) e conteggi suite 558→726 aggiornati (tabella strumenti, blocchi testing/quickstart, albero); tabella riproduzione 2 ambienti datata (2026-09-25). Fix lint F541 in `scripts/misura_p20.py` (file lasciato non registrato).

## 2026-10-16 (5) — Roadmap guadagni + potatura finale + allineamento infra a dfbe88f5
- **Roadmap** (`ROADMAP.md`, root): dai 1.096 € ai guadagni reali. Aritmetica nuda: rendita ≈3,4 €/mese vs costi ≈31 €/mese = **−28 €/mese**; Fase 0 = 3 decisioni owner (taglio costi ≤16 €/mese; sveglia dormienti: funding 194 € + eccesso trading → Earn; carry 180→400 € a gate). Fase 1 = report mensile automatico + 60gg track record; Fase 2 = scala capitale a gate (prima review ≈15/12; proiezioni: 10k→+30–36 €/mese, 25k→≈+100); Fase 3 = ricerca continua; kill-check 31/01.
- **Potatura repo**: rimosso bundle `docs/manus_2026-10-06/` (superseded; backup in /tmp + git history) e residui P20 non registrati (market-making: bocciato dalle fee; backup in /tmp). Commit `d117b3a5`.
- **Allineamento infra a git**: MARCODG1 aveva 37 voci sparse nel working tree → committate le necessarie (aggregator BETH+sezioni ricerca/carry, dashboard carry, zabbix, review C1, unit+script ricerca, artefatti P15/P16/E/funding_scan; commit `dfbe88f5`); .bak spostati in /tmp; identità repo-locale impostata; **push da MARCODG1 impossibile** (nessuna credenziale https; chiave ssh non su GitHub) → push via mc2 (procedura da ricordare). Ora **mc2 + MARCODG1 + nuvola tutti su `dfbe88f5`** (omarchy: nessun artefatto money; win: non raggiungibile da qui).

## 2026-10-16 (6) — Veglia flotta (auto-heal) + status squadre + radar OKX + scheda progetto
- **Veglia** (`ops/fleet/veglia.py`, timer 2'): check meticolosi (unit system+user, HTTP, docker, freschezza file vitali) con **auto-riparazione** (restart/start, cooldown 15', riverifica, log in `~/.veglia/`, notifica TG sui rossi persistenti). Smoke mc2: **24/24 ok**.
- **Status squadre** (`deploy/riavvio/status_squadre.sh|.ps1`): Trade+Dev in un colpo da ogni macchina; unit di boot sui 3 nodi money → `~/status_squadre_boot.txt` al riavvio; ps1 provato su win (OK). **Prima run ha già trovato un guasto vero**: `carry_stato.json` fermo da 20h — mancava lo scheduler di `genera_carry.py` → aggiunto cron `*/5` su MARCODG1 (+ canonico in `deploy/cron/`); ora l'uPL reale del carry è +1,56 € (il +0,36 mostrato era congelato).
- **Radar OKX** (`ops/radar/radar_okx.py`, timer 45' su mc2): annunci ufficiali EEA → TG su Learn&Earn/campagne/airdrop; dedup con baseline silenziosa. Doc onesto: `docs/27_airdrop_e_opportunita_2026-10-16.md` (+ proposta pilota on-chain cappato 50–100 €, in attesa di decisione owner).
- **Scheda progetto** (`SCHEDA_PROGETTO.md`) riscritta sullo stato reale: squadre Trade/Dev, macchine, servizi, motore economico, metodo, verdetti, vigilanza, runbook. Suite **737 test** verdi (11 nuovi), ruff pulito.
- Follow-up: unit di boot con `XDG_RUNTIME_DIR` (niente falsi KO delle unit utente al riavvio); ps1 win → tailscale via servizio; status-squadre installato anche su omarchy; tutto deployato e provato (mc2 VERDETTO OK).

## 2026-10-16 (7) — Test chiavi API OKX (owner): tutti i sub funzionano da nuvola e MARCODG1
- **Eseguito** `ops/tools/prova_chiavi.py` (nuovo, sola lettura, mai valori stampati; stdin per test remoti).
- **Esito**: `main_okx.env` OK da nuvola e MARCODG1 (uid main 822983321310515677). **Sub `mc2sub1` / `nuvolasub1` / `marcosub1`: TUTTI OK da entrambi gli IP** (uid sub distinti, mainUid = main, saldi trading vuoti). Mappa chiave↔nodo: nuvola → `nuvolasub1` (`.env_nuvola`); mc2 → `mc2sub1` (`.env_mc2`, stessa chiave, verificato); MARCODG1 → main. `marcosub1` valida ma non usata da servizi.
- **Da mc2 tutto KO per design**: CGNAT → IP non whitelisted (50119 / "IP not in whitelist"). Nota nel tool.
- **Igiene trovata**: la copia `~/denaro/secrets/main_okx.env` su mc2 è una chiave VECCHIA/morta (50119 anche da IP buono); le copie vive sono su nuvola≡MARCODG1 (identiche, hash verificato). Il vecchio vault `~/.denaro_vault/keys_master.env` (ago) = archivio, tutte morte. Pulizia suggerita, in attesa dell'owner.

## 2026-10-16 (8) — Onda S5: nuovo fronte di ricerca (P21/P22/P23) + dispatch agli aiutanti
- **Perché**: la caccia su OHLCV è chiusa PER EVIDENZA (~600k configurazioni, 0 candidati al DSR); l'unico motore con netto positivo è il funding/carry; il pedaggio è il giudice di ogni edge (cancello, criterio 6). Il fronte S5 = funding + esecuzione + dati nuovi, non altre candele.
- **Pre-registrate 3 voci** in `coda_catena/` (lint 7/7): **P21** paniere carry con regola di selezione/pesi (6 configurazioni vs 3 baseline, netto costi); **P22** gate di regime RARO giudicato netto (chiude l'ultima variante aperta dall'addendum P12); **P23** pedaggio REALIZZATO sui fill reali C1+carry + studio maker-first. Piano: `docs/28_fronte_ricerca_2026-10-16.md`; registro aggiornato (voci PRIMA dei numeri).
- **Dispatch agli aiutanti**: P21 assegnata a **DSH-omarchy** (REQ su canale `dsh-mc2/` + turno headless pilotato da mc2; consegna via handoff `dsh-mc2/handoff/P21/`); P22 = prossimo libero (fabbrica/DSH/opencode); P23 = hermes. Dati: funding via ccxt pubblico + archivio (scan n≥60g ~metà novembre); tick/orderflow a ≥30g (~15/11).
- **Watcher consegne** (`ops/alerts/watch_handoff.py` + cron 5' su mc2): notifica TG all'arrivo di un `READY` negli handoff DSH (`hermes_bridge/*/handoff/*/READY`, dedup in `~/.handoff_watch/seen.json`) — mai piu' consegne silenziose; READY storici seedati senza notifica. 3 test nuovi (scansione/dedup/root assente).

## 2026-10-16 (9) — Audit Manus integrato: CI fail-fast + assert runtime eliminati
- Branch `improvement/ci-and-runtime-hardening` (account grivetto) revisionato e mergiato (**4db0846d**, nessun conflitto): CI non più cieca (`pip install -e ".[dev]"` + `pip check` al posto del fallback `|| true`); **4 assert nel codice vivo** (trend_lungo, scansione, scansione3, p13_cointegrazione) -> `RuntimeError` fail-closed (restano attivi anche con `python -O`); guardia AST `tests/test_no_runtime_assert.py` anti-reintroduzione (src/ ora a zero assert).
- **Verifica completa PRIMA del push**: pip install rc=0 · pip check pulito · ruff OK · compileall OK · **741 test verdi** (normale) e **741 con `-O`**. Doc integrata: `docs/31_proposta_miglioramenti_2026-10-16.md` (5 miglioramenti futuri: CI 3.11+3.12, coverage, flag produzione script live, provenienza tariffa negli artefatti, separazione test rete/credenziali).
