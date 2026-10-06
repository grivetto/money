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
