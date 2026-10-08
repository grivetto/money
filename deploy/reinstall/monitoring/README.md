# Kit monitoring money — Prometheus + Grafana + exporter (MARCODG1)

Ripristina lo stack metriche su un MARCODG1 ricostruito. Riferimento: `docs/23` «Fase 2 — monitoring ripristinato (08/10/26)».

## Cosa contiene
- `deploy.sh` — script idempotente (dir, venv, download binari, config, unit, avvio).
- `prometheus.yml` — scrape: exporter `:9100` dei 3 nodi (mc2/nuvola via tailscale) + self.
- `denaro.risk.yml` — regole alert rischio (senza alertmanager: visibili in UI, non notificano).
- `datasources.yml`, `dashboards.yml` — provisioning Grafana (datasource uid `denaro-prometheus`, folder «Money»).
- `denaro-dashboard.json` — dashboard «Money — Flotta & Rischio» (uid `denaro-dashboard`).
- `money-prometheus.service`, `money-grafana.service`, `money-exporter.service` — unit systemd.
  NB: `money-grafana.service` contiene il placeholder `__GRAFANA_ADMIN_PASS__`, sostituito da `deploy.sh`
  con la password generata in `/home/marco/denaro/secrets/grafana_admin.txt` (600).

## Prerequisiti
- Codice denaro2 in `/home/marco/denaro2` (package `denaro2/` + `accounts.yaml`).
  Copia master: `mc2:/home/sergio/denaro2` — nel `pyproject.toml` serve
  `[tool.setuptools] packages = ["denaro2"]` (flat-layout con data/config/reports altrimenti fallisce).
- Segreti in `/home/marco/denaro/secrets/` con permessi **600** (il loader `denaro2.secrets` rifiuta permessi più larghi).
- Route Cloudflare `grafana.grivetto.eu` → `127.0.0.1:3000` presente nell'ingress del tunnel (remote-managed, dal dashboard CF Zero Trust).

## Deploy
```bash
rsync -a <questo kit> MARCODG1:/home/marco/mon_deploy/
rsync -a <denaro2/: denaro2/ accounts.yaml config> MARCODG1:/home/marco/denaro2/
ssh MARCODG1 'bash /home/marco/mon_deploy/deploy.sh'
```

## Verifica
```bash
systemctl is-active money-prometheus money-grafana money-exporter   # 3x active
curl -s 127.0.0.1:3000/api/health                                   # {"database":"ok"}
curl -s '127.0.0.1:9090/api/v1/targets?state=active'                # 4 target up
curl -sI https://grafana.grivetto.eu/ | head -1                     # 200 (anonimo → grafico)
```

## Note operative
- Grafana: **accesso anonimo Viewer** + home dashboard → la URL pubblica apre direttamente il grafico.
  L'administrador serve solo per modifiche (`/login`).
- L'exporter sul nodo è l'UNICO con il blocco flotta attivo (`DEN_AGG_URL=http://127.0.0.1:8912`);
  su mc2/nuvola `DEN_AGG_URL` è vuoto per non duplicare le serie.
- `node_totals.running/equity/pnl/trades` = solo bot **live**; i paper si leggono da `denaro_node_paper_running` e `denaro_bot_*`.
