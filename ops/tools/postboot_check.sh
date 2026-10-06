#!/usr/bin/env bash
# postboot_check.sh v2 (2026-10-06) — verifica di risalita dell'ambiente dopo un riavvio.
# Gira SU mc2 (dove vive Hermes). Uso:  bash ops/tools/postboot_check.sh
# v2: unit rinominate money-* dopo la migrazione "casa unica"; aggiunti i controlli
#     MARCODG1 (unit money-*, banco a secco con path nuovo).
# Output: OK/PROBLEMA per ogni controllo + riepilogo finale. Nessun segreto stampato.
set -u
FAIL=0; OKN=0
ok()  { printf '%-58s OK\n' "$1"; OKN=$((OKN+1)); }
bad() { printf '%-58s PROBLEMA\n' "$1"; FAIL=$((FAIL+1)); }
chk_unit()  { systemctl is-active --quiet "$1" && ok "mc2 unit $1" || bad "mc2 unit $1"; }
chk_uunit() { systemctl --user is-active --quiet "$1" && ok "mc2 user $1" || bad "mc2 user $1"; }

echo "===== POST-BOOT CHECK — $(date '+%F %T %Z') ====="
echo
echo "-- mc2: servizi di sistema"
for u in ponte_ai dsh-pump stella-bridge-pump dsh-web money-aggregator-mc2 denaro-feeder-mc2 money-health-mc2 money-dashboard-mc2 denaro-exporter-mc2 cloudflared-home mc2-hardening zabbix-agent zabbix-tunnel-reverse docker ssh; do chk_unit "$u"; done
systemctl is-active --quiet tailscaled && ok "mc2 unit tailscaled" || bad "mc2 unit tailscaled"
echo
echo "-- mc2: servizi utente (linger) e timer"
for u in denaro-node-mc2 hermes-gateway fabbrica-tick.timer; do chk_uunit "$u"; done
echo
echo "-- mc2: porte chiave"
c=$(curl -s -o /dev/null -m 5 -w '%{http_code}' http://127.0.0.1:4080/ || true)
[ "$c" = "401" ] && ok "dsh-web :4080 (401 = atteso)" || bad "dsh-web :4080 (HTTP $c)"
c=$(curl -s -o /dev/null -m 5 -w '%{http_code}' http://127.0.0.1:8642/ || true)
[ -n "$c" ] && [ "$c" != "000" ] && ok "hermes-gateway :8642 (HTTP $c)" || bad "hermes-gateway :8642 (HTTP $c)"
c=$(curl -s -o /dev/null -m 5 -w '%{http_code}' http://127.0.0.1:8912/api/infra.json || true)
[ "$c" = "200" ] && ok "mc2 aggregatore :8912" || bad "mc2 aggregatore :8912 (HTTP $c)"
echo
echo "-- mc2: docker"
for n in agent-zero zabbix-server zabbix-web zabbix-db freellmapi-freellmapi-1; do
  docker inspect -f '{{.State.Running}}' "$n" 2>/dev/null | grep -q true && ok "container $n" || bad "container $n"
done
echo
echo "-- mc2: cron"
systemctl is-active --quiet cron && ok "cron attivo" || bad "cron NON attivo"
crontab -l 2>/dev/null | grep -q "watch_alerts.py check" && ok "cron watch_alerts presente" || bad "cron watch_alerts MANCANTE"
echo
echo "-- A0 (operai)"
c=$(curl -s -o /dev/null -m 6 -w '%{http_code}' -H 'Origin: http://127.0.0.1:50080' http://127.0.0.1:50080/ || true)
[ "$c" = "200" ] && ok "A0-mc2 :50080" || bad "A0-mc2 :50080 (HTTP $c)"
c=$(curl -s -o /dev/null -m 8 -w '%{http_code}' -H 'Origin: http://100.76.22.119:50080' http://100.76.22.119:50080/ 2>/dev/null || true)
[ "$c" = "200" ] && ok "A0-win (tailnet)" || bad "A0-win non raggiungibile (HTTP $c) -> su Windows: avvia Docker Desktop / container Agent Zero"
echo
echo "-- omarchy (nodo agenti)"
if ssh -o BatchMode=yes -o ConnectTimeout=8 omarchy 'systemctl is-active --quiet dsh-web' 2>/dev/null; then
  ok "omarchy: ssh + dsh-web attivi"
  c=$(ssh -o BatchMode=yes -o ConnectTimeout=8 omarchy 'curl -s -o /dev/null -m 5 -w "%{http_code}" http://127.0.0.1:5080/' 2>/dev/null || true)
  [ "$c" = "401" ] && ok "omarchy dsh-web :5080 (401 = atteso)" || bad "omarchy dsh-web :5080 (HTTP $c)"
else
  bad "omarchy non raggiungibile o dsh-web giu"
fi
echo
echo "-- MARCODG1 (trading/web — unit money-*)"
for u in money-aggregator-marcodg1 money-dashboard-marcodg1 money-health-marcodg1 money-landing-marcodg1 money-watchdog-marcodg1.timer money-banco-secco.timer fabbrica-worker.timer cloudflared-denaro zabbix-agent; do
  st=$(ssh -o BatchMode=yes -o ConnectTimeout=8 MARCODG1 "systemctl is-active $u" 2>/dev/null || true)
  [ "$st" = "active" ] && ok "MARCODG1 $u" || bad "MARCODG1 $u ($st)"
done
c=$(ssh -o BatchMode=yes -o ConnectTimeout=8 MARCODG1 'curl -s -o /dev/null -m 8 -w "%{http_code}" http://127.0.0.1:8912/api/infra.json' 2>/dev/null || true)
[ "$c" = "200" ] && ok "MARCODG1 aggregatore :8912" || bad "MARCODG1 aggregatore (HTTP $c)"
c=$(ssh -o BatchMode=yes -o ConnectTimeout=8 MARCODG1 'curl -s -o /dev/null -m 8 -w "%{http_code}" http://127.0.0.1:8913/' 2>/dev/null || true)
[ "$c" = "200" ] && ok "MARCODG1 dashboard :8913" || bad "MARCODG1 dashboard (HTTP $c)"
epoch=$(ssh -o BatchMode=yes -o ConnectTimeout=8 MARCODG1 'stat -c %Y /home/marco/canary/canary.log 2>/dev/null' 2>/dev/null || echo "")
if [ -n "$epoch" ]; then
  age=$(( $(date +%s) - epoch ))
  [ "$age" -lt 1500 ] && ok "canary C1: monitor fresco (${age}s)" || bad "canary C1: monitor fermo (${age}s)"
else
  bad "canary C1: log non leggibile"
fi
last=$(ssh -o BatchMode=yes -o ConnectTimeout=8 MARCODG1 'tail -1 /home/marco/money/logs/banco_secco.jsonl 2>/dev/null' || true)
echo "$last" | grep -q '"esito": "PASS"' && ok "banco a secco: ultimo run PASS" || bad "banco a secco: ultimo run NON PASS"
bepoch=$(ssh -o BatchMode=yes -o ConnectTimeout=8 MARCODG1 'stat -c %Y /home/marco/money/logs/banco_secco.jsonl 2>/dev/null' 2>/dev/null || echo "")
if [ -n "$bepoch" ]; then
  bage=$(( $(date +%s) - bepoch ))
  [ "$bage" -lt 700 ] && ok "banco a secco: fresco (${bage}s)" || bad "banco a secco: fermo (${bage}s)"
fi
echo
echo "-- FLOTTA (payload master)"
running=$(ssh -o BatchMode=yes -o ConnectTimeout=8 MARCODG1 'curl -s -m 12 http://127.0.0.1:8912/api/infra.json' 2>/dev/null | python3 -c "import json,sys;d=json.load(sys.stdin);b=d.get('bots') or {};print(sum(1 for x in b.values() if isinstance(x,dict) and x.get('status')=='running'))" 2>/dev/null || echo 0)
[ "$running" -ge 20 ] 2>/dev/null && ok "bot running: $running (attesi ~24)" || bad "bot running: $running (attesi ~24)"
echo
echo "===== RIEPILOGO: $OKN OK · $FAIL problemi ====="
[ "$FAIL" = 0 ] && echo "AMBIENTE OK" || echo "DA SISTEMARE: vedi le righe PROBLEMA qui sopra"
