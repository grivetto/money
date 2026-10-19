# ERROR_MEMORY — registro delle lezioni apprese

Ogni voce: data, sintomo, causa radice, fix, regola permanente. Solo eventi
verificati sui sistemi reali (mai ipotesi). Chi tocca il codice legge questo
file PRIMA di modificare percorsi che muovono capitale.

## 2026-09 — Chiavi OKX EU: 50119 non significa "chiave morta"
- Sintomo: tutte le chiavi OKX fallivano con 50119 "API key doesn't exist".
- Causa radice: hostname sbagliato (`www.okx.com`); le chiavi EEA vivono solo su `eea.okx.com`.
- Fix: corretto hostname in verify_access e config; 3/3 sub-account GREEN.
- Regola: una chiave EU che fallisce altrove con 50119 NON è morta: è sul host sbagliato. Testare sempre via ccxt (probe stdlib homemade davano falsi "Invalid key").

## 2026-09 — Bug sizing: `int(step)` azzera la quantità
- Sintomo: ordini con quantità 0 nonostante nozionale valido.
- Causa radice: `int(0.001)` vale 0. Arrotondamento allo step fatto con cast a intero.
- Fix: `floor(q/step)*step` con decimali di step calcolati sul testo, mai cast.
- Regola: sul percorso del capitale zero eccezioni non gestite e zero cast silenziosi: assertion runtime + unit test PRIMA del live. (Incidente da $200+ del 19/09: stessa famiglia.)

## 2026-09 — Equity che ignora gli ordini aperti
- Sintomo: criterio di drawdown con equity sottostimata.
- Causa radice: uso di `free` invece di `total` (free+used) per valuta.
- Fix: `saldi_nonzero()` usa `total`; dashboard passata a `equity_detail` riconciliato.
- Regola: ogni equity/PnL dichiarato deve essere riconciliato con l'exchange (saldi, ordini aperti, fill). Mai dichiarare guadagni non riconciliati.

## 2026-09-19 — Incidente miner (docs/60 in alpha-omega-trading)
- Sintomo: miner su mc2 e MARCODG1, crontab zabbix svuotato via `/dev/shm/.cron_clean_*`, residui in `/var/tmp/.bin` e `/var/tmp/.X11-unix-socket`.
- Fix: contenimento, quarantena forense (md5 verificati), zabbix-agent hardened (`EnableRemoteCommands=0`, `ListenIP=127.0.0.1`).
- Regola: un componente critico giù senza alert È un incidente. Heartbeat + auto-recovery + panic alert su ogni daemon. PAT in `.bash_history` = segreto esposto: revocare subito (escalation proprietario ancora aperta al 27/09).

## 2026-09-27 — Falsi positivi fleet_integrity
- Sintomo: fleet-integrity.service in fail ogni 15 minuti (4 allarmi).
- Causa radice: lock `flock` in /tmp scambiati per eseguibili sospetti; porta 10050 LISTEN allarmata anche con `system.run` disattivo; regex PAT non matchava il pattern reale `@github.com`.
- Fix: patch P1-P6 + 47 test verdi (commit `294a7c9`).
- Regola: un check di sicurezza che urla sempre lupo viene ignorato: ogni allarme deve avere allowlist documentata e test che lo riproducono.

## 2026-09-27 — Refuso nei segreti: `OKK_API_KEY`
- Sintomo: `money/.env` contiene `OKK_API_KEY` (doppia K) e `OKX_SECRET_KEY`; il banco si aspetta `OKX_API_KEY` / `OKX_API_SECRET`.
- Fix: mappatura esplicita in fase di installazione del banco (file sorgente lasciato com'è, chmod 600).
- Regola: i segreti si copiano con mappatura dichiarata e verifica di sola lettura (fetch balance), mai "corretti" a memoria. Permessi sempre 600.

## 2026-09-27 — Config drift tra nodi
- Sintomo: clone su MARCODG1 indietro di 6 giorni rispetto a origin/main; serviva il banco appena versionato.
- Regola: prima di qualsiasi deploy su un nodo: `git fetch`, verifica distanza da origin/main, backup branch dello stato locale, poi fast-forward. Mai deploy su codice non sincronizzato.

## 2026-09-27 — Criteri del cancello citati a memoria (sbagliati)
- Sintomo: in un task a DSH ho citato criteri del cancello (10k trade, Sharpe>=1.5, maxDD<=12%, PSR, K-S, turnover) che NON esistono nel repo.
- Causa radice: valori presi da un riassunto di sessione invece che dal codice (`src/money/cancello.py`: numerosita>=30, IC bootstrap 90% con estremo>0, t>1.65, PF>1.20, maxDD<=25%, expectancy>=3x pedaggio, rilevanza>=10 EUR/anno, indipendenza blocchi).
- Fix: DSH ha verificato il repo e obiettato; decisione DEC-20260927-HERMES-01: il cancello del codice e' vincolante, le altre metriche solo in aggiunta.
- Regola: qualsiasi parametro di governance (criteri, fee, limiti) si cita SOLO dal codice/config vigente, mai da memoria o riassunti. Stessa famiglia dell'errore fee: 0,070% e' il giro SWAP; una strategia spot si giudica a okx_eea_spot 0,550% (misurato 27/09: maker 0,200/taker 0,350, Lv1).

## 2026-09-27 — Servizio critico non supervisionato
- Sintomo: cloudflared su mc2 (PID 2531) girava senza systemd: un crash = web.grivetto.eu giù in silenzio.
- Regola: ogni processo che serve traffico o muove dati sta sotto systemd con Restart=always + watchdog + alert. Nessun demone "a mano".

## 2026-09-27 — Nodi legacy LIVE dimenticati sui sub-account
- Sintomo: denaro-node-marcodg1-xrp (marcosub1) e denaro-node-nuvola-trade (nuvolasub1) ancora active/running con chiavi trade, equity 0, tick a vuoto.
- Causa radice: la flotta legacy non era mai stata spenta davvero; un nodo live dimenticato su un conto e' una collisione di ordini in attesa (regola: MAI due bot sullo stesso conto).
- Fix: stop+disable su entrambi; verificato zero nodi live su 3 nodi (resta solo il paper su MARCODG1). denaro-node-mc2 resta fermo per scelta.
- Regola: prima che un conto entri nel perimetro money, il suo nodo legacy deve essere stop+disable. La flotta live riparte SOLO dalla catena cancello -> esecuzione, mai riaccendendo un legacy.

## 2026-10-17 — Cron raccolta funding rotto 8h da WIP non committato
- Sintomo: `raccogli_funding.py` falliva con `ImportError` (`report_copertura`) a ogni run (12:13, 16:13 CEST); marker `data/raccolta_last_run` fermo dalle 06:13 UTC → `svc.raccolta=0` (allarme "raccolta ferma").
- Causa radice: un WIP di ricerca non committato aveva riscritto `src/money/raccoglitore_funding.py` rimuovendo `report_copertura`; i cron eseguono il working tree di ~/money, non un commit.
- Fix: funzione ripristinata dalla HEAD; `basis_pp` corretto (spot X-Perp USD → coppia USDC, prima puntava a un mercato inesistente su OKX EEA); ticker caricati solo se ci sono record nuovi; test aggiornati (+4). Verifica live: scritti=20, errori=0, marker fresco.
- Regola: il working tree di ~/money su mc2 È la produzione dei cron: una sessione che lo modifica non si chiude finché `pytest tests/` non è verde e le modifiche non sono committate.

## 2026-10-19 — Raccolta esterni congelata 94h da un "salta se esiste" (trovata dall'audit agy)
- Sintomo: `data/esterni/*.json` (on-chain CoinMetrics, F&G, TVL) fermi al 2026-10-15 nonostante il timer orario `money-ricerca-raccolta` girasse verde (58/58 run SUCCESS). Nessun allarme: la raccolta sembrava viva.
- Causa radice: `scarica_esterni.py` saltava i file esistenti ("gia' presente, salto") e non li aggiornava MAI piu': il collector faceva la prima fotografia, non il flusso. Trovato dall'audit operai agy (ondata 19/10), non da un watchdog.
- Fix: aggiornamento incrementale (legge l'ultima data, scarica da lì con overlap 3g, merge idempotente; F&G/TVL riscaricati sempre; file esistente mai sovrascritto se il download fallisce). Verifica live: 11 asset aggiornati fino a 2026-10-19, mtime nuovi. Guardia aggiunta: check `raccolta:esterni` in watch_alerts modo carry (allarme se il file resta fermo > 48h).
- Regola: un collector che salta "se esiste" è una fotografia, non una raccolta: la freschezza si verifica con un check ripetibile (mtime/ultima data), mai dedotta dal verde del timer.
