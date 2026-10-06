#!/usr/bin/env bash
# ricostruisci-marco.sh — ricostruzione del nodo MARCODG1 (trading/Web) dopo reinstallazione OS.
# Repo canonico: https://github.com/grivetto/money (pubblico; il pull non richiede credenziali).
#
# Uso:   sudo bash deploy/reinstall/ricostruisci-marco.sh
# Prereq: OS Debian/Ubuntu fresco, rete attiva, accesso sudo.
# Nota: gli ultimi passi (segreti, cloudflared, tailscale, zabbix) sono guidati e restano
#       manuali perché coinvolgono credenziali: vedi README-MARCODG1.md nella stessa cartella.
set -euo pipefail

UTENTE="${MARCO_UTENTE:-marco}"
H="/home/$UTENTE"
REPO="https://github.com/grivetto/money.git"

echo "=========================================================="
echo " Ricostruzione MARCODG1 — utente=$UTENTE home=$H"
echo "=========================================================="

echo "== 1/8 Pacchetti base =="
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git curl python3 python3-venv python3-pip jq ca-certificates rsync

echo "== 2/8 Utente $UTENTE =="
if ! id "$UTENTE" >/dev/null 2>&1; then
  adduser --disabled-password --gecos "" "$UTENTE"
fi
usermod -aG sudo "$UTENTE" || true

echo "== 3/8 Repo money =="
if [ ! -d "$H/money/.git" ]; then
  sudo -u "$UTENTE" git clone --depth 50 "$REPO" "$H/money"
else
  sudo -u "$UTENTE" git -C "$H/money" fetch origin && sudo -u "$UTENTE" git -C "$H/money" pull --ff-only
fi
sudo -u "$UTENTE" git -C "$H/money" log --oneline -1

echo "== 4/8 venv money (ccxt, requests, pyyaml) =="
sudo -u "$UTENTE" bash -lc "cd $H/money && [ -d .venv ] || python3 -m venv .venv"
sudo -u "$UTENTE" bash -lc "cd $H/money && .venv/bin/pip install -q -U pip && .venv/bin/pip install -q ccxt requests pyyaml"
sudo -u "$UTENTE" bash -lc "cd $H/money && .venv/bin/python3 -c 'import ccxt, yaml; print(\"venv OK\", ccxt.__version__)'"

echo "== 5/8 Directory runtime =="
sudo -u "$UTENTE" mkdir -p "$H/money/logs" "$H/denaro/health" "$H/denaro/logs" "$H/denaro/secrets" "$H/canary"
chmod 700 "$H/denaro/secrets"
echo "   (i SEGRETI vanno depositati a mano: vedi README-MARCODG1.md, sezione 'Segreti')"

echo "== 6/8 Unit systemd (money-* + fabbrica) =="
cd "$H/money/deploy/systemd"
for u in \
  money-aggregator-marcodg1.service money-dashboard-marcodg1.service money-health-marcodg1.service \
  money-landing-marcodg1.service money-watchdog-marcodg1.service money-watchdog-marcodg1.timer \
  money-banco-secco.service money-banco-secco.timer \
  fabbrica-worker.timer ; do
  install -m 644 "$u" "/etc/systemd/system/$u"
done
# fabbrica-worker.service e' un TEMPLATE con placeholder: istanza per-nodo
sed -e "s/__USER__/$UTENTE/" -e "s|__HOME__|$H|" -e "s/__NODE__/marcodg1/" \
  "$H/money/deploy/systemd/fabbrica-worker.service" > /etc/systemd/system/fabbrica-worker.service
systemctl daemon-reload
for u in \
  money-aggregator-marcodg1 money-dashboard-marcodg1 money-health-marcodg1 money-landing-marcodg1 \
  money-watchdog-marcodg1.timer money-banco-secco.timer fabbrica-worker.timer ; do
  systemctl enable --now "$u"
done
systemctl list-timers 'money-*' 'fabbrica-*' --no-pager | head -6 || true

echo "== 7/8 crontab (backup versionato del nodo) =="
sudo -u "$UTENTE" bash -lc "crontab $H/money/deploy/systemd/legacy_aot/crontab-marcodg1.backup-20261006.txt"
sudo -u "$UTENTE" bash -lc "crontab -l | grep -vE '^#|^$' | wc -l"

echo "== 8/8 Servizi esterni — MANUALI (vedi README) =="
cat <<'EOF'
  [ ] Segreti:    ~/denaro/secrets/main_okx.env  +  ~/money/config/.env_banco   (chmod 600)
  [ ] cloudflared: installare e collegare il tunnel 'denaro' (token dalla dashboard Cloudflare)
  [ ] tailscale:   curl -fsSL https://tailscale.com/install.sh | sh  &&  tailscale up
  [ ] zabbix-agent: installare, server = nodo mc2 (vedi README)  + enable --now
  [ ] canary:      ripristinare canary_state.json / canary_events.jsonl / canary.log in ~/canary (se recuperati)
  [ ] grafana/prometheus: opzionali (fase 2)

 Verifica finale:
   locale:  curl -s http://127.0.0.1:8912/api/infra.json | head -c 200 ; curl -s http://127.0.0.1:8911/health
   da mc2:  bash ~/money/ops/tools/postboot_check.sh
EOF

echo "=========================================================="
echo " Base installata. Completa i passi manuali (8/8) e lancia la verifica."
echo "=========================================================="
