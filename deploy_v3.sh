#!/usr/bin/env bash
# =============================================================================
# DENARO DEPLOY SCRIPT — v4.0
# Deploy completo su nuvola, mc2, MARCODG1
# Eseguire DA LOCALE (unica macchina da cui lanciare)
# =============================================================================
# CHANGES v4.0:
#   + auto_adaptive_engine.py (self-learning engine)
#   + event_gateway.py (heartbeat + Telegram alerts)
#   + Nuove dipendenze: pandas-ta (optional)
#   + Verifica WAL mode SQLite
#   + Avvio event_gateway in background
#   + Backup anche dei nuovi file
# =============================================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

declare -A HOSTS
HOSTS["nuvola"]="sergio:/home/sergio/denaro"
HOSTS["mc2"]="sergio:/home/sergio/denaro"
HOSTS["MARCODG1"]="marco:/home/marco/denaro"

RSYNC_EXCLUDES=(
    "--exclude=archive/"
    "--exclude=.git/"
    "--exclude=*.log"
    "--exclude=trades.db"
    "--exclude=.env"
    "--exclude=venv/"
    "--exclude=__pycache__/"
    "--exclude=*.pyc"
    "--exclude=*.template"
    "--exclude=backup_pre_deploy_*"
)

PIP_PACKAGES="ccxt pandas websockets python-dotenv requests beautifulsoup4 lxml aiohttp numpy"

echo "============================================================"
echo "  DENARO DEPLOY v4.0"
echo "============================================================"
echo ""

# ---------------------------------------------------------------------------
# FASE 0: Connettività
# ---------------------------------------------------------------------------
echo "▶ FASE 0: Verifica connettività..."
REACHABLE=()
for host in "${!HOSTS[@]}"; do
    ud="${HOSTS[$host]}"
    u="${ud%%:*}"
    if ssh -o ConnectTimeout=5 -o BatchMode=yes "${u}@${host}" "echo ok" &>/dev/null; then
        echo "  ✅ $host ($u): raggiungibile"
        REACHABLE+=("$host")
    else
        echo "  ❌ $host: NON RAGGIUNGIBILE"
    fi
done
[ ${#REACHABLE[@]} -eq 0 ] && { echo "Nessun host raggiungibile. Abort."; exit 1; }

# ---------------------------------------------------------------------------
# FASE 1: Backup
# ---------------------------------------------------------------------------
echo ""
echo "▶ FASE 1: Backup stato attuale..."
for host in "${REACHABLE[@]}"; do
    ud="${HOSTS[$host]}"
    u="${ud%%:*}"
    rd="${ud#*:}"
    ts=$(date +%Y%m%d_%H%M%S)
    echo "  → $host (dir=$rd ts=$ts)"
    ssh -o ConnectTimeout=5 -o BatchMode=yes "${u}@${host}" bash -c "
mkdir -p '${rd}/backup_${ts}'
for f in legion_manager_production.py trade_db.py exchange_multi.py auto_adaptive_engine.py event_gateway.py; do
    cp -v '${rd}/\$f' '${rd}/backup_${ts}/' 2>/dev/null || true
done
cp -v '${rd}/trades.db' '${rd}/backup_${ts}/' 2>/dev/null || true
echo 'Backup: ${rd}/backup_${ts}'
"
    echo "  ✅ $host: backup OK"
done

# ---------------------------------------------------------------------------
# FASE 2: Sync
# ---------------------------------------------------------------------------
echo ""
echo "▶ FASE 2: Sincronizzazione file..."
LOCAL_SOURCE="${SCRIPT_DIR}"
[ ! -d "$LOCAL_SOURCE" ] && LOCAL_SOURCE="$HOME/.openclaw/workspace/denaro"

for host in "${REACHABLE[@]}"; do
    ud="${HOSTS[$host]}"
    u="${ud%%:*}"
    rd="${ud#*:}"
    echo "  → $host ..."
    rsync -avz --delete "${RSYNC_EXCLUDES[@]}" "${LOCAL_SOURCE}/" "${u}@${host}:${rd}/"
    echo "  ✅ $host: sync OK"
done

# ---------------------------------------------------------------------------
# FASE 3: Dipendenze Python
# ---------------------------------------------------------------------------
echo ""
echo "▶ FASE 3: Installazione dipendenze Python..."
for host in "${REACHABLE[@]}"; do
    ud="${HOSTS[$host]}"
    u="${ud%%:*}"
    rd="${ud#*:}"
    echo "  → $host ..."
    ssh -o ConnectTimeout=5 -o BatchMode=yes "${u}@${host}" bash -c "
source '${rd}/venv/bin/activate' 2>/dev/null || {
    python3 -m venv '${rd}/venv'
    source '${rd}/venv/bin/activate'
    pip install --quiet --upgrade pip
}
pip install --quiet $PIP_PACKAGES
PYVER_NUM=\$(python3 -c 'import sys; print(sys.version_info.major * 100 + sys.version_info.minor)')
if [ \"\$PYVER_NUM\" -ge 314 ]; then
    echo '  ⏭️  pandas-ta: saltato (Python >= 3.14)'
else
    pip install --quiet pandas-ta 2>/dev/null || true
fi
python3 -c \"import ccxt, pandas, websockets, dotenv, numpy; print('Dipendenze: ✅')\"
"
    echo "  ✅ $host: deps OK"
done

# ---------------------------------------------------------------------------
# FASE 4: Database (WAL mode + nuove tabelle)
# ---------------------------------------------------------------------------
echo ""
echo "▶ FASE 4: Verifica database (WAL mode)..."
for host in "${REACHABLE[@]}"; do
    ud="${HOSTS[$host]}"
    u="${ud%%:*}"
    rd="${ud#*:}"
    echo "  → $host ..."
    ssh -o ConnectTimeout=5 -o BatchMode=yes "${u}@${host}" bash -c "
source '${rd}/venv/bin/activate' 2>/dev/null
cd '${rd}'
export PYTHONPATH=\"${rd}:\$PYTHONPATH\"
python3 << 'PYEOF'
import sqlite3, os, sys
db_path = os.path.join(os.getcwd(), 'trades.db')
print(f'DB path: {db_path}')
conn = sqlite3.connect(db_path)

# Enable WAL mode (crash-safe)
conn.execute('PRAGMA journal_mode=WAL')
conn.execute('PRAGMA synchronous=NORMAL')

# Create tables if missing
conn.execute('''CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_name TEXT, symbol TEXT, side TEXT,
    entry_price REAL, exit_price REAL, quantity REAL,
    entry_time TEXT, exit_time TEXT,
    gross_pnl REAL, fees REAL, net_pnl REAL,
    reason TEXT
)''')
conn.execute('''CREATE TABLE IF NOT EXISTS bot_state (
    bot_name TEXT PRIMARY KEY,
    is_in_position INTEGER DEFAULT 0,
    entry_price REAL, quantity REAL,
    tp REAL, sl REAL,
    entry_time REAL,
    last_heartbeat REAL,
    exchange_name TEXT DEFAULT 'binance'
)''')
conn.execute('''CREATE TABLE IF NOT EXISTS bot_exposure (
    symbol TEXT PRIMARY KEY,
    amount REAL,
    last_updated REAL
)''')
conn.execute('''CREATE TABLE IF NOT EXISTS vault_balance (
    key TEXT PRIMARY KEY,
    value REAL DEFAULT 0.0
)''')
conn.execute('''CREATE TABLE IF NOT EXISTS auto_disabled (
    symbol TEXT PRIMARY KEY,
    reason TEXT,
    disabled_at REAL
)''')

# Ensure vault row exists
conn.execute('INSERT OR IGNORE INTO vault_balance (key, value) VALUES (\"EUR\", 0.0)')

conn.commit()
cur = conn.execute(\"SELECT name FROM sqlite_master WHERE type='table'\")
tables = [r[0] for r in cur.fetchall()]
print(f'Tabelle: {tables}')
print('DB ✅ (WAL mode)')
conn.close()
PYEOF
"
    echo "  ✅ $host: DB OK"
done

# ---------------------------------------------------------------------------
# FASE 5: Cleanup legacy
# ---------------------------------------------------------------------------
echo ""
echo "▶ FASE 5: Cleanup legacy..."
for host in "${REACHABLE[@]}"; do
    ud="${HOSTS[$host]}"
    u="${ud%%:*}"
    rd="${ud#*:}"
    echo "  → $host ..."
    ssh -o ConnectTimeout=5 -o BatchMode=no "${u}@${host}" bash <<'CLEANEOF'
echo "Killing legacy python processes..."
pkill -9 -f "scalper_eth.py" 2>/dev/null || true
pkill -9 -f "grid_bot" 2>/dev/null || true
pkill -9 -f "alpha_strike" 2>/dev/null || true
pkill -9 -f "sniper_squad" 2>/dev/null || true
pkill -9 -f "AI_RISK" 2>/dev/null || true
pkill -9 -f "collect_dashboard" 2>/dev/null || true
pkill -9 -f "momentum_scalper" 2>/dev/null || true
pkill -9 -f "bnb_scalper" 2>/dev/null || true
pkill -9 -f "sololegion" 2>/dev/null || true

# Kill TUTTI i processi python dell'utente (trashati in sicurezza)
sudo pkill -9 -u "$USER" python3 2>/dev/null || pkill -9 python3 2>/dev/null || true
sleep 2

# Pulisci file di stato legacy
rm -f ~/denaro/AI_RISK.log ~/denaro/AI_RISK.py 2>/dev/null || true
rm -f ~/denaro/positions/*.json 2>/dev/null || true
rm -f /app/positions /app/vault.json /app/global_exposure.json 2>/dev/null || true
systemctl --user disable bnb_scalper.service 2>/dev/null || true

# Rimuovi stray trade_db.py (fuori dalla dir denaro)
if [ -f "/home/sergio/trade_db.py" ]; then
    if ! readlink -f "/home/sergio/trade_db.py" | grep -q "denaro"; then
        echo "  Rimosso stray: /home/sergio/trade_db.py"
        rm -f "/home/sergio/trade_db.py"
    fi
fi

echo "  ✅ $(hostname) pulito"
CLEANEOF
done

# ---------------------------------------------------------------------------
# FASE 6: Avvio (con CWD esplicito e path assoluti)
# ---------------------------------------------------------------------------
echo ""
echo "▶ FASE 6: Avvio LegionManager + EventGateway..."
for host in "${REACHABLE[@]}"; do
    ud="${HOSTS[$host]}"
    u="${ud%%:*}"
    rd="${ud#*:}"
    echo "  → $host (dir=$rd) ..."
    ssh -o ConnectTimeout=5 -o BatchMode=yes "${u}@${host}" bash -c "
# Assicura directory
mkdir -p '${rd}/positions'
mkdir -p '${rd}/logs'

# Ripulisci lock DB residui
rm -f '${rd}/trades.db-journal' '${rd}/trades.db-wal' 2>/dev/null || true
sleep 1

# Avvia con CWD esplicito e PYTHONPATH
cd '${rd}'
export PYTHONPATH='${rd}':\$PYTHONPATH

# Kill any existing instance
pkill -f 'legion_manager_production.py' 2>/dev/null || true
pkill -f 'event_gateway.py' 2>/dev/null || true
sleep 2

# Avvia LegionManager
nohup python3 -u '${rd}/legion_manager_production.py' >> '${rd}/legion_production.log' 2>&1 &
NEW_PID=\$!
sleep 5

if kill -0 \$NEW_PID 2>/dev/null; then
    echo \"  ✅ LegionManager: PID=\$NEW_PID\"
else
    echo \"  ❌ LegionManager: avvio fallito\"
    tail -20 '${rd}/legion_production.log'
fi

# Avvia EventGateway (heartbeat)
nohup python3 -u '${rd}/event_gateway.py' >> '${rd}/event_gateway.log' 2>&1 &
GW_PID=\$!
sleep 2
if kill -0 \$GW_PID 2>/dev/null; then
    echo \"  ✅ EventGateway: PID=\$GW_PID\"
else
    echo \"  ⚠️  EventGateway: non avviato (no Telegram config?)\"
fi
"
done

echo ""
echo "============================================================"
echo "  DEPLOY v4.0 COMPLETATO"
echo "============================================================"
echo "Log LegionManager:  tail -f ~/denaro/legion_production.log"
echo "Log EventGateway:   tail -f ~/denaro/event_gateway.log"
echo "DB:                 sqlite3 ~/denaro/trades.db '.tables'"
echo "============================================================"