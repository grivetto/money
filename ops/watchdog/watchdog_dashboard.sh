#!/bin/bash
# Watchdog Money su MARCODG1 — v3 2026-10-06 (casa unica = money)
# Copre: stack dashboard (:8913/:8912/:8911) + landing pubblica (:8914).
# v2 (2026-09-23): incidente stack fermato il 22/09 per ~27h senza alert.
# v3: unit rinominate money-* dopo la migrazione da alpha-omega; log invariato.
# Gli override WATCHDOG_PORT_* esistono per testare il percorso KO senza toccare i servizi veri.
LOG=/home/marco/denaro/logs/watchdog_dashboard.log
PORT_DASH=${WATCHDOG_PORT_DASH:-8913}
PORT_AGG=${WATCHDOG_PORT_AGG:-8912}
PORT_LAND=${WATCHDOG_PORT_LAND:-8914}

c1=$(curl -s -o /dev/null -w '%{http_code}' --max-time 8 "http://127.0.0.1:${PORT_DASH}/" || true)
c2=$(curl -s -o /dev/null -w '%{http_code}' --max-time 8 "http://127.0.0.1:${PORT_AGG}/api/infra.json" || true)
c3=$(curl -s -o /dev/null -w '%{http_code}' --max-time 8 "http://127.0.0.1:${PORT_LAND}/" || true)

if [ "$c1" != "200" ] || [ "$c2" != "200" ]; then
  echo "$(date -Is) KO dashboard=$c1 aggregator=$c2 — riavvio stack" >> "$LOG"
  sudo -n /usr/bin/systemctl start money-aggregator-marcodg1 money-dashboard-marcodg1 money-health-marcodg1
  sleep 5
  c1b=$(curl -s -o /dev/null -w '%{http_code}' --max-time 8 "http://127.0.0.1:${PORT_DASH}/" || true)
  c2b=$(curl -s -o /dev/null -w '%{http_code}' --max-time 8 "http://127.0.0.1:${PORT_AGG}/api/infra.json" || true)
  echo "$(date -Is) dopo restart stack: dashboard=$c1b aggregator=$c2b" >> "$LOG"
  if [ "$c1b" != "200" ] || [ "$c2b" != "200" ]; then
    echo "$(date -Is) ATTENZIONE: recovery stack non riuscito" >> "$LOG"
  fi
fi

if [ "$c3" != "200" ]; then
  echo "$(date -Is) KO landing=$c3 — riavvio money-landing-marcodg1" >> "$LOG"
  sudo -n /usr/bin/systemctl start money-landing-marcodg1
  sleep 4
  c3b=$(curl -s -o /dev/null -w '%{http_code}' --max-time 8 "http://127.0.0.1:${PORT_LAND}/" || true)
  echo "$(date -Is) dopo restart landing: $c3b" >> "$LOG"
  if [ "$c3b" != "200" ]; then
    echo "$(date -Is) ATTENZIONE: recovery landing non riuscito" >> "$LOG"
  fi
fi
exit 0
