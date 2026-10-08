#!/bin/bash
# Deploy monitoring "money" su MARCODG1: prometheus + grafana + exporter (denaro2)
# Idempotente. Richiede: /home/marco/mon_deploy/ con i file, codice denaro2 già copiato.
set -euo pipefail
BASE=/home/marco/denaro
DEPLOY=/home/marco/mon_deploy

echo "[1/9] directory"
mkdir -p "$BASE/prometheus/rules" "$BASE/prometheus-data" "$BASE/grafana-data/dashboards" \
         "$BASE/grafana/provisioning/datasources" "$BASE/grafana/provisioning/dashboards" \
         /home/marco/denaro2/data

echo "[2/9] pyproject denaro2"
cat > /home/marco/denaro2/pyproject.toml <<'EOF'
[project]
name = "denaro2"
version = "0.0.1"
description = "denaro2 — fase 2 nodo (metrics)"
requires-python = ">=3.12"
dependencies = ["ccxt>=4.4,<5", "pyyaml>=6,<7"]

[tool.setuptools]
packages = ["denaro2"]
EOF

echo "[3/9] venv + dipendenze"
if [ ! -x "$BASE/venv/bin/python" ]; then python3 -m venv "$BASE/venv"; fi
"$BASE/venv/bin/pip" install -q --upgrade pip
"$BASE/venv/bin/pip" install -q "ccxt>=4.4,<5" "pyyaml>=6,<7"
"$BASE/venv/bin/pip" install -q -e /home/marco/denaro2
"$BASE/venv/bin/python" -c "import denaro2, ccxt, yaml; print('venv ok')"

echo "[4/9] prometheus 2.54.1"
if [ ! -x "$BASE/prometheus/prometheus" ]; then
  cd /tmp
  curl -sSL -o prom.tgz https://github.com/prometheus/prometheus/releases/download/v2.54.1/prometheus-2.54.1.linux-amd64.tar.gz
  tar xzf prom.tgz
  cp prometheus-2.54.1.linux-amd64/prometheus prometheus-2.54.1.linux-amd64/promtool "$BASE/prometheus/"
  rm -rf prometheus-2.54.1.linux-amd64 prom.tgz
fi
chmod +x "$BASE/prometheus/prometheus" "$BASE/prometheus/promtool"

echo "[5/9] grafana 11.1.4"
if [ ! -x "$BASE/grafana/bin/grafana" ]; then
  cd /tmp
  curl -sSL -o graf.tgz https://dl.grafana.com/oss/release/grafana-11.1.4.linux-amd64.tar.gz
  tar xzf graf.tgz
  cp -a grafana-v11.1.4/. "$BASE/grafana/"
  rm -rf grafana-v11.1.4 graf.tgz
fi
chmod +x "$BASE/grafana/bin/"* || true

echo "[6/9] configurazioni"
cp "$DEPLOY/prometheus.yml" "$BASE/prometheus.yml"
cp "$DEPLOY/denaro.risk.yml" "$BASE/prometheus/rules/denaro.risk.yml"
cp "$DEPLOY/datasources.yml" "$BASE/grafana/provisioning/datasources/datasources.yml"
cp "$DEPLOY/dashboards.yml" "$BASE/grafana/provisioning/dashboards/dashboards.yml"
cp "$DEPLOY/denaro-dashboard.json" "$BASE/grafana-data/dashboards/denaro-dashboard.json"

echo "[7/9] password admin grafana"
if [ ! -f "$BASE/secrets/grafana_admin.txt" ]; then
  PASS=$(head -c 32 /dev/urandom | base64 | tr -d '/+=' | cut -c1-20)
  (umask 077; echo "admin:$PASS" > "$BASE/secrets/grafana_admin.txt")
fi
PASS=$(cut -d: -f2 "$BASE/secrets/grafana_admin.txt")

echo "[8/9] unit systemd"
sed "s|__GRAFANA_ADMIN_PASS__|$PASS|" "$DEPLOY/money-grafana.service" > /tmp/money-grafana.unit
sudo -n cp /tmp/money-grafana.unit /etc/systemd/system/money-grafana.service
rm -f /tmp/money-grafana.unit
sudo -n cp "$DEPLOY/money-prometheus.service" /etc/systemd/system/money-prometheus.service
sudo -n cp "$DEPLOY/money-exporter.service" /etc/systemd/system/money-exporter.service
sudo -n systemctl daemon-reload

echo "[9/9] avvio"
sudo -n systemctl enable --now money-exporter money-prometheus money-grafana
sleep 6
echo "-- attivi:"; systemctl is-active money-exporter money-prometheus money-grafana
echo "-- exporter (righe denaro):"; curl -s -m 6 http://127.0.0.1:9100/metrics | grep -c '^denaro' || true
echo "-- prometheus ready:"; curl -s -m 6 http://127.0.0.1:9090/-/ready; echo
echo "-- grafana health:"; curl -s -m 8 http://127.0.0.1:3000/api/health; echo
echo "-- firewall (informativo):"; sudo -n ufw status 2>/dev/null | head -3 || true
echo
echo "=== DEPLOY MONITORING COMPLETATO ==="
