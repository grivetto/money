#!/bin/bash
LOG="$HOME/denaro/grid.log"
WDOG_LOG="$HOME/denaro/monitor/monitor.log"
INTERVAL=60
START_CMD="cd $HOME/denaro && $HOME/denaro/venv/bin/python3 -u $HOME/denaro/grid_bot_v3.py >> $LOG 2>&1"

mkdir -p $(dirname "$WDOG_LOG")

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$WDOG_LOG"; }

kill_procs() {
    local pat pid
    for pat in "[g]rid_bot_v3.py" "[w]atchdog.sh"; do
        for pid in $(pgrep -f "$pat" 2>/dev/null); do
            [ -n "$pid" ] && [ "$pid" != "$$" ] && kill -9 "$pid" 2>/dev/null
        done
    done
    sleep 2
}

start_bot() {
    kill_procs
    log "Starting bot"
    eval "$START_CMD" &
    BOTPID=$!
    log "Bot started PID=$BOTPID"
}

log "=== Watchdog STARTED (PID=$$) ==="
start_bot

while true; do
    sleep $INTERVAL
    count=$(pgrep -f "[g]rid_bot_v3.py" 2>/dev/null | wc -l)
    [ "$count" -eq 0 ] 2>/dev/null && log "Bot dead. Restart." && start_bot && continue
    [ "$count" -gt 1 ] 2>/dev/null && log "Multi bots ($count). Restart." && start_bot && continue
    [ -f "$LOG" ] && {
        age=$(($(date +%s) - $(stat -c %Y "$LOG" 2>/dev/null)))
        [ "$age" -gt 300 ] 2>/dev/null && log "LOG stale (${age}s). Restart." && start_bot
    }
done
