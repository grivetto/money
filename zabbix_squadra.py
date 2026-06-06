#!/usr/bin/env python3
"""Zabbix metric collector v2 — per-bot dettaglio da DB + log + bot_lock.json.
Si adatta automaticamente al path in cui si trova (HERMES home o /home/*/denaro)."""
import json, os, sys, time, re

# Auto-detect Denaro directory: script is at DENARO_DIR/zabbix_squadra.py
script_dir = os.path.dirname(os.path.abspath(__file__))
# If we're in squadra/ subdir, parent is DENARO_DIR
if script_dir.endswith("/squadra"):
    DENARO_DIR = os.path.dirname(script_dir)
else:
    DENARO_DIR = script_dir

LOG = os.path.join(DENARO_DIR, "squadra", "squadra.log")
DB = os.path.join(DENARO_DIR, "trades.db")
LOCK = os.path.join(DENARO_DIR, "bot_lock.json")
CONFIG = os.path.join(DENARO_DIR, "squadra", "squadra.json")

data = {
    "hostname": os.uname().nodename,
    "ts": int(time.time()),
    "denaro_dir": DENARO_DIR,
    "eur": 0.0, "peak": 0.0, "drawdown_pct": 0.0, "drawdown_eur": 0.0,
    "exposure": 0.0,
    "killswitch": "OFF",
    "killswitch_state": 0,
    "bots_total": 0, "bots_alive": 0,
    "errors": 0,
    "bots": {},
}

# 0. Config
try:
    if os.path.exists(CONFIG):
        cfg = json.load(open(CONFIG))
        data["drawdown_limit_pct"] = cfg.get("drawdown_limit_pct", 0)
        data["max_total_eur"] = cfg.get("max_total_eur", 0)
        data["test_mode"] = cfg.get("test_mode", False)
except Exception:
    pass

# 1. Kill-switch state
try:
    if os.path.exists(LOCK):
        with open(LOCK) as f:
            lock = json.load(f)
        data["killswitch_state"] = lock.get("global_state", 0)
        data["killswitch"] = {0: "OFF", 1: "BOT_STOPPED", 2: "LOCKED"}.get(data["killswitch_state"], "UNKNOWN")
        data["bots_locked_count"] = len(lock.get("bot_locks", {}))
        data["consecutive_losses"] = sum(lock.get("consecutive_losses", {}).values())
except Exception:
    pass

# 2. DB state per bot
try:
    import sqlite3
    conn = sqlite3.connect(DB, timeout=3)
    conn.row_factory = sqlite3.Row
    bot_rows = conn.execute("SELECT bot_name, state FROM bot_state").fetchall()
    for row in bot_rows:
        name = row["bot_name"]
        state = json.loads(row["state"])
        data["bots"][name] = {
            "alive": True,
            "in_position": bool(state.get("is_in_position", False)),
            "entry_price": float(state.get("entry_price", 0) or 0),
            "quantity": float(state.get("quantity", 0) or 0),
            "tp": float(state.get("tp", 0) or 0),
            "sl": float(state.get("sl", 0) or 0),
            "entry_time": float(state.get("entry_time", 0) or 0),
            "exchange": state.get("exchange_name", "binance"),
            "symbol": "?",
            "price": 0.0,
            "eur": 0.0,
            "pnl_daily_pct": 0.0,
            "pnl_daily_eur": 0.0,
            "action": "UNKNOWN",
            "drawdown_pct": 0.0,
            "drawdown_eur": 0.0,
        }
    conn.close()
    data["bots_total"] = len(bot_rows)
except Exception as e:
    data["db_error"] = str(e)

# 3. Log parsing for latest live metrics
try:
    if os.path.exists(LOG):
        out = os.popen(f"tail -200 {LOG}").read()
        lines = out.strip().split("\n")
        for line in reversed(lines):
            # Portfolio line
            m = re.search(r"EUR=([\d.]+)\s*\|\s*Peak=([\d.]+)\s*\|\s*Drawdown=([\d.]+)%", line)
            if m and data["eur"] == 0:
                data["eur"] = float(m.group(1))
                data["peak"] = float(m.group(2))
                data["drawdown_pct"] = float(m.group(3))
                data["drawdown_eur"] = data["peak"] - data["eur"] if data["peak"] > 0 else 0
            # Exposure
            m = re.search(r"Exposure=([\d.]+)€", line)
            if m and data["exposure"] == 0:
                data["exposure"] = float(m.group(1))
            # Per-bot report line: "  • Name: Symbol | status | order=eur | PnL=eur (N cicli)"
            m = re.search(r"•\s*(\w+):\s*(\S+)\s*\|\s*([✅❌🟢⚪🔴✖️\s\w-]+)\s*\|\s*order=([\d.]+)€", line)
            if m:
                bname = m.group(1)
                sym = m.group(2)
                status_text = m.group(3).strip()
                order_eur = float(m.group(4))
                if bname in data["bots"]:
                    data["bots"][bname]["symbol"] = sym
                    data["bots"][bname]["action"] = status_text
                    data["bots"][bname]["eur"] = order_eur
                # PnL
                pnl = re.search(r"PnL=([-.\d]+)€", line)
                if pnl and bname in data["bots"]:
                    data["bots"][bname]["pnl_daily_eur"] = float(pnl.group(1))
            # Error count
            if "Strategy error" in line or "Traceback" in line:
                data["errors"] += 1
except Exception as e:
    data["log_error"] = str(e)

data["bots_alive"] = sum(1 for b in data["bots"].values() if b.get("alive"))
print(json.dumps(data))
