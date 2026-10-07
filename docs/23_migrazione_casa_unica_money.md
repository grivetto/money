# 23 — Migrazione «casa unica = money» (alpha-omega → money)

**Direttiva del proprietario (2026-10-06):** «alpha-omega non lo usiamo più: tutto quello che ci serve è money. Fai funzionare quello. MANDATORIO.»

Questo documento è il verbale operativo della migrazione: cosa è stato spostato, come si
verifica, e cosa resta. Regola di fondo: **un cutover per volta, con backup e verifica**;
C1 (canary carry) e banco a secco mai interrotti.

## Principi

- **Codice e servizi → money**: moduli in `ops/` (aggregator, dashboard, health, alerts,
  tools, zabbix, watchdog), unit systemd **versionate** in `deploy/systemd/`.
- **Dati dove stanno i produttori**: gli health file, `node_data/`, i log runtime restano
  nelle dir attuali finché non migrano anche le sorgenti (paper node); spostarli prima
  romperebbe chi li legge.
- **Backup delle unit dismesse** in `deploy/systemd/legacy_aot/` (con i crontab di backup).
- **Niente roture**: ogni servizio nuovo è stato avviato e verificato (payload/health)
  prima di dichiarare il cutover chiuso.

## Fatto (fase 1 — servizi e telemetria, 2026-10-06)

| Nodo | Migrato a money | Verifica |
| :--- | :--- | :--- |
| mc2 | aggregator (:8912), dashboard (:8913), health (:8911) — unit `money-*-mc2` | payload 24 bot / equity 1100,23 · healthy · http 200 |
| mc2 | cron: watch_alerts ×5, gen_dashboard, infra_snapshot, scommessa, cruscotto, raccolta funding, watchdog | test manuali rc=0; backup `legacy_aot/crontab-mc2.backup-*` |
| MARCODG1 | aggregator, dashboard, health, landing — unit `money-*-marcodg1` | payload 24 bot / equity 1100,22 · healthy · landing 200 |
| MARCODG1 | watchdog v3 (`money-watchdog-marcodg1.timer`, nomi unit money) | run pulito |
| MARCODG1 | banco a secco (`deploy/banco` + `deploy/scripts` in money; `.env_banco` in `money/config/`) | PASS, `fonte=money.costi`, ExecMainStatus=0 |
| MARCODG1 | venv `money/.venv` (ccxt 4.5.85, requests, pyyaml) | canary test run rc=0 |
| MARCODG1 | cron: push_metrics, infra_snapshot, canary, zabbix_bots → money (backup `.backup-20261006.txt` in `legacy_aot/`) | applicato 06/10 con approvazione; verifica al primo tick |
| nuvola | health (:8911) — unit `money-health-nuvola` | healthy, 6 bot paper |

Dashboard pubblica (verificata dalla catena nuova): **equity 1100,24 EUR · 24 bot · canary ✓**.

Difetti trovati e corretti lungo la strada (utili per il futuro):

1. bit `+x` perso sugli script in git → systemd 203/EXEC sul banco (fix: chmod + mode git);
2. l'aggregator valorizza i saldi via ccxt → sul nodo serve il venv con ccxt (non `python3` di sistema);
3. PyYAML mancante nel venv money di MARCODG1 (il banco legge `node_banco.yaml`);
4. default `MONEY_SRC` del banco puntava a un path morto → ora `PROJECT_ROOT/src` dinamico;
5. liste bot dei health server ancora pre-officina su nuvola → `*_paper`.

## Pendente (in ordine di priorità)

1. ~~Crontab di MARCODG1~~ ✅ fatto (con approvazione del proprietario): le 4 righe
   ripuntate a money; resta la sola riga `quality_shadow` (denaro2) per la fase 2.
2. **Paper node engine** (`denaro-node-*`, `engine_paper`, config per-nodo) + **feeder
   ZeroMQ**: migrazione congiunta — dipendono dal package `denaro/` di alpha-omega.
   Decisione contestuale: portare l'engine in money o dismettere i paper node.
3. **Exporter (denaro2) e quality_shadow**: da rifare in money sulle metriche del
   progetto (fabbrica/job-store/canary) o dismettere. Oggi girano da denaro2.
4. **Chiavi/config**: i `.env` di produzione restano in `alpha-omega/config` finché non
   si spostano in `money/config` (fase dedicata ai segreti, con inventario e permessi).
5. **Fase 3 — spegnimento**: fermare i servizi alpha-omega residui, archiviare in
   `legacy/`, togliere le ultime dipendenze (venv AOT).

## Riferimenti

- Backup e unit dismesse: `deploy/systemd/legacy_aot/`.
- Guardie: `ops/aggregator/port_guard.sh` (copie estranee), watchdog v3, health server.
- Regola invariata: nessuna unit toccata senza verifica successiva; ogni cutover ha il
  suo backup.

## Incidente 06/10 sera — MARCODG1 non risale al riavvio

- Confermato down su 4 canali (ping, ssh refused, tailscale offline, dashboard 530). I soldi
  e le posizioni C1 stanno su OKX e non sono toccati; il monitor canary è in pausa.
- Predisposto il **kit di ripristino**: `deploy/reinstall/` — `README-MARCODG1.md` (recupero
  disco → ricostruzione → segreti → verifica) e `ricostruisci-marco.sh` (server fresco).
- Creato in git il file mancante `deploy/systemd/money-banco-secco.timer`.
- Priorità al recupero: `~/denaro/secrets/`, `~/canary/` (storico C1), `.env_banco`, config.

### Esito ricostruzione (06/10 sera, completata)

MARCODG1 ricostruito con il kit (`deploy/reinstall/`) e riportato in servizio:
- base Ubuntu 26.04, utente marco (+sudo), repo money, venv, unit `money-*` enabled, crontab, timer;
- **banco a secco PASS** (chiave read-only nuova, `chiave_solo_lettura=si`), equity 1.100,13 EUR;
- **canary C1** ripartito con stato ricostruito dal monitor pre-incidente (11 ct @ 0,09466 / 109,89 DOGE @ 0,09473), riconciliazione OK;
- tunnel Cloudflare (denaro/web.grivetto.eu) su, dashboard 200; tailscale su (IP nuovo 100.89.26.52);
- zabbix-agent via tunnel (127.0.0.1:10051); fabbrica-worker shard: pubblica a mc2 via tunnel 2222;
- fix applicati: gruppo `marco` mancante (216/GROUP), template fabbrica-worker istanziato per nodo (217/USER),
  worker shard con unit `money-*`, known_hosts/chiave ssh marco→mc2, postboot_check v2.1.
- Restano (fase 2): flotta paper di marco (0 bot ricostruiti: decisione portare/dismettere),
  metriche grafana/prometheus, exporter.

Le chiavi di marco sono nuove (authorized_keys nuova): per l'accesso usare la chiave di mc2 già depositata;
ogni altro accesso storico va riautorizzato.

## Residui post-ricostruzione trovati e corretti (2026-10-07)

Dopo la ricostruzione del 06/10 il nodo era "su", ma una serie di residui teneva
ciechi i monitor — e nessun alert li segnalava, perché i check stessi erano rotti.

| # | Residuo | Effetto | Fix |
|---|---------|---------|-----|
| 1 | crontab reinstallato = copia PRE-migrazione (path alpha-omega morti) | monitor canary cieco, push Zabbix / snapshot / sync bot fermi da ~14h | riapplicata la versione money: `deploy/cron/crontab-marcodg1.txt` (kit aggiornato); riga quality_shadow sospesa (fase 2) |
| 2 | `~/.zbx_cred` non ripristinato (non era nel kit) | push_metrics / zabbix_bots senza login API | password Admin ruotata di nuovo (reset via DB, verificato); creds depositate su mc2 e sul nodo (600) |
| 3 | known_hosts e chiave ssh nodo→nuvola assenti | aggregatore: nuvola "non raggiungibile" | known_hosts aggiunto (fingerprint verificato) + chiave marco autorizzata su nuvola |
| 4 | interfaccia Zabbix host MARCODG1 = vecchio IP tailscale (100.70.254.121) | item passivi dell'agent stagnanti dal 06/10 | interfaccia → 100.89.26.52; agent allineato al pattern nuvola (`Server=127.0.0.1,100.87.24.42` · `ServerActive=127.0.0.1:10051` · `ListenIP=127.0.0.1,100.89.26.52`) — verificato: avail=1, item ripartiti |
| 5 | watch_alerts: venv canary morto + path fleet_integrity errato (mc2) | alert ripetuti "exit 127" e "check rotto" | path aggiornati a money (`money/.venv/bin/python3`, `ops/tools/fleet_integrity.py`) |
| 6 | push_metrics: crash heal su health file mancanti | rc=1 ogni minuto (dopo il push) | guard "unit presente sul nodo" + lettura JSON robusta |
| 7 | scommessa: scp verso path morto (`alpha-omega/denaro`) | scheda scommessa ferma al 06/10 | target → `money/ops/dashboard/scommessa.json` (crontab mc2 aggiornato, run verificato) |
| 8 | stato bot: 4 paper marcodg1 tra i "running" | allarme flotta perpetuo per bot non ricostruiti | rimossi dallo stato (fase 2: decisione portare/dismettere) |

Extra hardening (07/10): sul nodo anche `PermitRootLogin without-password` (drop-in
`/etc/ssh/sshd_config.d/99-denaro.conf`, allineato a mc2); resta da valutare col
proprietario `PasswordAuthentication no` + fail2ban (ci sono ~7k tentativi di forza
bruta al giorno sull'IP pubblico).

Regola confermata (zero-silenzi): i check che sorvegliano devono restare verdi LORO per primi —
un residuo di ricostruzione che spegne i check è un incidente, non un dettaglio.
