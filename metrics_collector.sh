#!/bin/bash
BASE="/home/sergio/denaro/dashboard/public"
mkdir -p "$BASE"
TS=$(date +%H:%M)

# NUVOLA
ssh nuvola "cat <<EOF
{\"ts\":\"$TS\",\"b\":$(pgrep -c -f grid_bot_v3.py 2>/dev/null||echo 0),\"w\":$(pgrep -c -f watchdog.sh 2>/dev/null||echo 0),\"i\":$(grep -oP 'Invested: \K[0-9.]+' /home/sergio/denaro/grid.log 2>/dev/null|tail -1||echo 0),\"p\":$(grep -oP 'Profit: \K[0-9.]+' /home/sergio/denaro/grid.log 2>/dev/null|tail -1||echo 0),\"pr\":$(grep -oP 'Price: \K[0-9.]+' /home/sergio/denaro/grid.log 2>/dev/null|tail -1||echo 0),\"t\":\"$(grep -oP 'Trend: \K[A-Z_]+' /home/sergio/denaro/grid.log 2>/dev/null|tail -1||echo UNKNOWN)\",\"r\":$(grep -oP 'RSI: \K[0-9.]+' /home/sergio/denaro/grid.log 2>/dev/null|tail -1||echo 0),\"tr\":$(grep -c 'SELL filled' /home/sergio/denaro/grid.log 2>/dev/null||echo 0),\"a\":\"$(zabbix_agentd -t denaro.service.active 2>/dev/null|grep -o 'active\|inactive'||echo unknown)\",\"d\":$(df -h /|tail -1|awk '{print \$5}'|tr -d '%'),\"m\":$(free -m|grep Mem|awk '{printf \"%.0f\", \$3/\$2*100}'),\"v4\":1}
EOF" > "$BASE/nuvola.json"

# MARCODG1
ssh MARCODG1 "cat <<EOF
{\"ts\":\"$TS\",\"b\":$(pgrep -c -f grid_bot_v3.py 2>/dev/null||echo 0),\"w\":$(pgrep -c -f watchdog.sh 2>/dev/null||echo 0),\"i\":$(grep -oP 'Invested: \K[0-9.]+' /home/marco/denaro/grid.log 2>/dev/null|tail -1||echo 0),\"p\":$(grep -oP 'Profit: \K[0-9.]+' /home/marco/denaro/grid.log 2>/dev/null|tail -1||echo 0),\"pr\":$(grep -oP 'Price: \K[0-9.]+' /home/marco/denaro/grid.log 2>/dev/null|tail -1||echo 0),\"t\":\"$(grep -oP 'Trend: \K[A-Z_]+' /home/marco/denaro/grid.log 2>/dev/null|tail -1||echo UNKNOWN)\",\"tr\":$(grep -c 'SELL filled' /home/marco/denaro/grid.log 2>/dev/null||echo 0),\"a\":\"$(zabbix_agentd -t denaro.service.active 2>/dev/null|grep -o 'active\|inactive'||echo unknown)\",\"d\":$(df -h /|tail -1|awk '{print \$5}'|tr -d '%'),\"m\":$(free -m|grep Mem|awk '{printf \"%.0f\", \$3/\$2*100}'),\"v4\":1}
EOF" > "$BASE/marcodg1.json"

if [ -f /home/sergio/denaro/scalper.log ]; then
  SCP=$(pgrep -c -f scalper_v1.py 2>/dev/null||echo 0)
  SPP=$(grep -oP 'PnL: [-0-9.]+' /home/sergio/denaro/scalper.log 2>/dev/null|tail -1|grep -oP '[-0-9.]+'||echo 0)
  SPPR=$(grep -oP 'ETH/EUR @ [0-9.]+' /home/sergio/denaro/scalper.log 2>/dev/null|tail -1|grep -oP '[0-9.]+'||echo 0)
  SR=$(grep -oP 'RSI=[0-9.]+' /home/sergio/denaro/scalper.log 2>/dev/null|tail -1|grep -oP '[0-9.]+'||echo 0)
  SB=$(grep -c 'BUY\|SELL' /home/sergio/denaro/scalper.log 2>/dev/null||echo 0)
  SE=$(grep -oP 'EUR=[0-9.]+' /home/sergio/denaro/scalper.log 2>/dev/null|tail -1|grep -oP '[0-9.]+'||echo 0)
  echo "{\"ts\":\"$TS\",\"sc\":$SCP,\"sp\":$SPP,\"spr\":$SPPR,\"sr\":$SR,\"sb\":$SB,\"se\":$SE,\"d\":$(df -h /|tail -1|awk '{print $5}'|tr -d '%'),\"m\":$(free -m|grep Mem|awk '{printf "%.0f", $3/$2*100}'),\"z\":1}" > "$BASE/mc2.json"
fi
