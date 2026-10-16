#!/usr/bin/env bash
# status_squadre.sh — stato SQUADRA TRADE + SQUADRA DEV, eseguibile da ogni macchina del progetto.
# Uso:  status-squadre [--boot]
#   --boot : pensato per il run automatico dopo il riavvio (stesso output, nessuna attesa extra).
# Exit: 0 tutto ok · 1 almeno un KO.
set -u
BOX=$(hostname -s 2>/dev/null || hostname)
SOPTS="-o BatchMode=yes -o ConnectTimeout=6"
KO=0; IGNOTI=0

ok()  { printf '  [ok]   %s\n' "$1"; }
bad() { printf '  [KO]   %s\n' "$1"; KO=$((KO+1)); }
unk() { printf '  [?]    %s\n' "$1"; IGNOTI=$((IGNOTI+1)); }
remoto() { ssh $SOPTS "$1" "$2" 2>/dev/null; }

REPO=""
for c in "$HOME/money" /home/sergio/money /home/marco/money; do
  [ -f "$c/README.md" ] && [ -d "$c/.git" ] && REPO="$c" && break
done

# su macchine non-money (omarchy/win) l'irraggiungibilita' dei nodi e' attesa: non e' un KO
fallito() { if [ -n "$REPO" ]; then bad "$1"; else unk "$1 (macchina non-money: atteso)"; fi; }

echo "==================================================================="
echo " STATUS SQUADRE — $BOX — $(date '+%F %T %Z')"
if [ -n "$REPO" ]; then
  echo " repo: $REPO · git: $(git -C "$REPO" log --oneline -1 2>/dev/null | head -c 90)"
else
  echo " repo: non presente su questa macchina"
fi
echo "==================================================================="

echo
echo "[SQUADRA TRADE]"

# --- nuvola (nodo paper + monitor) ---
r=$(remoto nuvola 'for u in denaro-node-nuvola-trade money-health-nuvola denaro-exporter; do printf "unit %s=%s\n" $u $(systemctl is-active $u 2>/dev/null); done; printf "health=%s\n" $(curl -s -o /dev/null -m 6 -w "%{http_code}" http://127.0.0.1:8911/health)')
if [ -z "$r" ]; then fallito "nuvola non raggiungibile via ssh"; else
  while IFS='=' read -r k v; do
    case "$k" in
      health) [ "$v" = "200" ] && ok "nuvola health :8911 ($v)" || bad "nuvola health :8911 ($v)";;
      unit*)  u=${k#unit }; [ "$v" = "active" ] && ok "nuvola $u" || bad "nuvola $u ($v)";;
    esac
  done <<< "$r"
fi

# --- MARCODG1 (trading + web) ---
r=$(remoto MARCODG1 'for u in money-aggregator-marcodg1 money-dashboard-marcodg1 money-health-marcodg1 money-landing-marcodg1 money-watchdog-marcodg1.timer money-banco-secco.timer money-ricerca-raccolta.timer money-ricerca-scansione.timer cloudflared; do printf "unit %s=%s\n" $u $(systemctl is-active $u 2>/dev/null); done; printf "agg=%s\n" $(curl -s -o /dev/null -m 60 -w "%{http_code}" http://127.0.0.1:8912/api/infra.json); now=$(date +%s); for f in /home/marco/denaro/health/infra_snapshot.json /home/marco/money/logs/banco_secco.jsonl /home/marco/canary/canary.log /home/marco/money/data/carry_stato.json; do printf "ago %s=%s\n" $(basename $f) $(( now - $(stat -c %Y $f 2>/dev/null || echo 0) )); done; printf "banco_esito=%s\n" $(tail -1 /home/marco/money/logs/banco_secco.jsonl 2>/dev/null | grep -o "PASS\|FAIL" | head -1)')
if [ -z "$r" ]; then fallito "MARCODG1 non raggiungibile via ssh"; else
  while IFS='=' read -r k v; do
    case "$k" in
      agg)    [ "$v" = "200" ] && ok "MARCODG1 aggregatore :8912 ($v)" || bad "MARCODG1 aggregatore ($v)";;
      banco_esito) [ "$v" = "PASS" ] && ok "MARCODG1 banco a secco: PASS" || bad "MARCODG1 banco a secco: $v";;
      ago\ *) n=${k#ago }; lim=300
        [ "$n" = "banco_secco.jsonl" ] && lim=900; [ "$n" = "canary.log" ] && lim=2400
        [ "$n" = "carry_stato.json" ] && lim=3600
        [ "$v" -le "$lim" ] 2>/dev/null && ok "MARCODG1 $n fresco (${v}s)" || bad "MARCODG1 $n fermo (${v}s > ${lim}s)";;
      unit*)  u=${k#unit }; [ "$v" = "active" ] && ok "MARCODG1 $u" || bad "MARCODG1 $u ($v)";;
    esac
  done <<< "$r"
fi

# --- mc2 (ops del denaro: nodo paper + alert) ---
case "$BOX" in mc2)
  for u in denaro-node-mc2 hermes-gateway; do
    XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}" systemctl --user is-active --quiet "$u" && ok "mc2 (user) $u" || bad "mc2 (user) $u"
  done
  crontab -l 2>/dev/null | grep -q "watch_alerts.py check" && ok "mc2 cron watch_alerts" || bad "mc2 cron watch_alerts ASSENTE"
  ;;
*) r=$(remoto mc2 'for u in denaro-node-mc2 hermes-gateway; do printf "unit %s=%s\n" $u $(XDG_RUNTIME_DIR=/run/user/1000 systemctl --user is-active $u 2>/dev/null); done; crontab -l 2>/dev/null | grep -q "watch_alerts.py check" && echo "cron=ok" || echo "cron=ASSENTE"')
   if [ -z "$r" ]; then unk "mc2 ops non raggiungibile via ssh"; else
     while IFS='=' read -r k v; do
       case "$k" in
         cron) [ "$v" = "ok" ] && ok "mc2 cron watch_alerts" || bad "mc2 cron watch_alerts $v";;
         unit*) u=${k#unit }; [ "$v" = "active" ] && ok "mc2 $u" || bad "mc2 $u ($v)";;
       esac
     done <<< "$r"
   fi;;
esac

# --- payload master (il polso del denaro: il MASTER vive su MARCODG1) ---
p=""; src=""
if [ "$BOX" = "marcodg1" ]; then
  p=$(curl -s -m 90 "http://127.0.0.1:8912/api/infra.json" 2>/dev/null || true); src="master locale"
elif [ "$BOX" = "mc2" ]; then
  p=$(curl -s -m 25 "http://[::1]:8912/api/infra.json" 2>/dev/null || true); src="master via tunnel"
else
  p=$(remoto mc2 'curl -s -m 25 "http://[::1]:8912/api/infra.json"'); src="master via ssh mc2"
fi
if [ -n "$p" ]; then
  SRC="$src" python3 -c "
import json,os,sys
try: d=json.load(sys.stdin)
except Exception: print('  [?]    payload master non leggibile'); raise SystemExit
b=d.get('bots') or {}
run=sum(1 for x in b.values() if isinstance(x,dict) and x.get('status')=='running')
c=d.get('carry') or {}
cn=d.get('canary') or {}
print(f\"  » master [{os.environ.get('SRC','?')}]: equity {d.get('total_equity')} EUR | carry {c.get('coppie_aperte') or 'n/d'} coppie ({c.get('nozionale_totale_eur') or 'n/d'} EUR) | canary {cn.get('status') or 'n/d'} | bot running {run}\")
" <<< "$p" || bad "payload master non leggibile"
else
  unk "payload master non raggiungibile da questa macchina"
fi

echo
echo "[SQUADRA DEV]"
if [ "$BOX" = "mc2" ] && [ -n "$REPO" ]; then
  py="$REPO/.venv/bin/python"; [ -x "$py" ] || py=python3
  (cd "$REPO" && timeout 200 "$py" ops/agents/agents_status.py --dry 2>/dev/null) | sed 's/^/  /' || unk "agents_status non eseguibile"
else
  r=$(remoto mc2 'cd ~/money && timeout 200 .venv/bin/python ops/agents/agents_status.py --dry 2>/dev/null')
  if [ -n "$r" ]; then echo "$r" | sed 's/^/  /'; else unk "sezione Dev completa eseguibile da mc2"; fi
fi

echo
echo "-------------------------------------------------------------------"
printf 'SQUADRA TRADE: %s KO certi | dev: vedi tabella | ignoti: %s\n' "$KO" "$IGNOTI"
if [ "$KO" = 0 ]; then echo "VERDETTO: OK"; exit 0; else echo "VERDETTO: $KO KO — GUARDARE"; exit 1; fi
