# Ricostruzione nodo MARCODG1 (trading/web) — procedura di ripristino

> Creato 2026-10-06, a seguito del fermo del nodo (non risalito al riavvio).
> Regola: **prima si recupera, poi si reinstalla** — mai formattare se il disco è montabile.

## 0 — Cosa NON si perde (rassicurazione e contesto)

- **I soldi stanno su OKX**, non sul nodo: posizioni C1 (spot DOGE + perp short), saldi,
  sub-account. Il fermo del nodo non tocca nulla sul lato exchange.
- **Tutto il codice e la configurazione operativa sono in GitHub** (`grivetto/money`,
  repo pubblico): unit systemd, banco, crontab versionato, ops/, script canary.
- Si perdono, se il disco muore: **storico log C1** (`canary.log`, `canary_state.json`,
  `canary_events.jsonl`), i **segreti locali** (rigenerabili), i dati health (rigenerabili).

## A — FASE RECUPERO (disco raggiungibile: rescue/console dell'hoster)

Se il pannello dell'hoster offre **rescue system / console KVM**, avviarlo e copiare
i file critici PRIMA di qualsiasi reinstallazione. Liste e comandi:

File prioritari (in ordine):

| # | Percorso | Perché |
|---|----------|--------|
| 1 | `/home/marco/denaro/secrets/` | chiavi OKX del canary (main_okx.env) |
| 2 | `/home/marco/canary/` (state, events, log) | storico C1 per la review del 15/10 |
| 3 | `/home/marco/money/config/.env_banco` | chiave read-only del banco |
| 4 | `/home/marco/alpha-omega-trading/config/` | `.env_marcodg1` e simili (paper) |
| 5 | `/etc/cloudflared/` + `/var/lib/tailscale/` + `/etc/zabbix/` | tunnel/identità/agent (ripristino veloce) |
| 6 | `/home/marco/denaro/health/` + `/home/marco/alpha-omega-trading/node_data/` | stato bot/paper (rigenerabili) |
| 7 | `/home/marco/.ssh/` | accessi |
| 8 | `/home/marco/.zbx_cred` | credenziali API Zabbix (push metriche) |

Dal nodo in rescue (vecchio root probabilmente montato su `/mnt`):

```bash
# tar di tutto /home/marco (esclusi venv e cache, pesanti e rigenerabili)
tar czf /tmp/marco-home.tgz -C /mnt/home marco \
  --exclude 'marco/money/.venv' --exclude 'marco/alpha-omega-trading/venv' \
  --exclude 'marco/.cache' --exclude 'marco/denaro2'

# segreti e configurazioni di sistema
tar czf /tmp/marco-etc.tgz -C /mnt etc/cloudflared etc/zabbix var/lib/tailscale 2>/dev/null || true

# spedizione verso mc2 (è il nodo di raccolta/backup)
scp /tmp/marco-home.tgz /tmp/marco-etc.tgz sergio@87.106.3.15:/home/sergio/backup-marco/
```

Su mc2, appena arrivano: `chmod 600 ~/backup-marco/*.tgz` e annotare in
`money/deploy/reinstall/` che il recupero è avvenuto.

Se il rescue non è disponibile ma il disco è montato altrove → stessi `tar`, qualsiasi via.

## B — FASE RICOSTRUZIONE (server fresco)

```bash
# sul nodo fresco, come root:
git clone https://github.com/grivetto/money.git /root/money-setup   # oppure via scp
cd /root/money-setup && bash deploy/reinstall/ricostruisci-marco.sh
```

Lo script fa: pacchetti → utente → clone repo → venv (ccxt/requests/pyyaml) → directory →
unit systemd (money-* + fabbrica) enabled → crontab (`deploy/cron/crontab-marcodg1.txt`) → lista dei passi manuali.

## C — SEGRETI (manuali, mai in git)

| File | Contenuto | Come ripristinare |
|------|-----------|-------------------|
| `~/denaro/secrets/main_okx.env` | chiave OKX **MAIN** (canary C1, read+trade) | dal backup rescue; oppure rigenerare su OKX (stessa passphrase) e depositare con `umask 077`, chmod 600 |
| `~/money/config/.env_banco` | chiave **read-only** banco (`banco-readonly-*`) | dal backup; oppure rigenerare su OKX: permessi solo Read, IP whitelist `87.106.222.123` + `87.106.3.15` |
| `~/alpha-omega-trading/config/*.env` | chiavi sub-account (paper/live) | dal backup rescue |
| tunnel cloudflared | token/credenziali del tunnel `denaro` | Cloudflare Zero Trust → Tunnels → token; `cloudflared service install <TOKEN>` |
| tailscale | identità del nodo | `tailscale up` (login); il nodo riprende il nome `marcodg1` |
| `~/.zbx_cred` | credenziali API Zabbix (utente Admin; push metriche) | dal backup; oppure rigenerare con reset password via DB su mc2 (procedura ops) — `chmod 600` |
| zabbix-agent | connessione al server su mc2 | installare `zabbix-agent`; conf (pattern nuvola): `Server=127.0.0.1,100.87.24.42` · `ServerActive=127.0.0.1:10051` · `ListenIP=127.0.0.1,<tailscale-del-nodo>`; in Zabbix l'interfaccia dell'host deve puntare al tailscale del nodo; `enable --now` |

Deposito sicuro di un segreto (modello):

```bash
umask 077
cat > ~/denaro/secrets/main_okx.env <<'EOF'
OKX_API_KEY=...
OKX_API_SECRET=...
OKX_PASSPHRASE=...
EOF
chmod 600 ~/denaro/secrets/main_okx.env
```

## D — CANARY C1, dopo il ripristino

1. Ripristinare `~/canary/` (script copia in repo: `money/scripts/canary_carry.py`).
2. Se lo stato è perso ma si ha UNA riga di log recente: si ricostruisce
   (`109.89 DOGE` spot avg `0.09473`, perp `11ct @ 0.09466`, contract `DOGE-USD_UM_XPERP-310404`).
3. Test: `~/money/.venv/bin/python3 canary_carry.py status` → deve riconciliare.
4. La review del 15/10 si fa comunque: le posizioni e lo storico funding vivono su OKX.

## E — VERIFICA FINALE

Da mc2:

```bash
bash ~/money/ops/tools/postboot_check.sh
```

Atteso: tutte le voci `OK` — stack money di MARCODG1, aggregatore :8912, dashboard :8913,
canary fresco, banco PASS, flotta ~24 bot. Poi: `denaro.grivetto.eu` / `web.grivetto.eu` 200.

## Note residue (fase 2, non bloccanti per il ripristino)

- Paper node (`denaro-node-*`) e feeder: erano su alpha-omega → decidere se riportarli
  (in money) o dismettere alla ricostruzione.
- Grafana/Prometheus: reinstallabili dai package; dashboard da ri-importare.
- Il file unit `cloudflared-denaro.service` non è in git: si rigenera con
  `cloudflared service install` (nome standard `cloudflared.service`).
