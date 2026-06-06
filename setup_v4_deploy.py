#!/usr/bin/env python3
"""Setup DB tables for Denaro v4.0 and start processes (run on each host)"""
import sqlite3, os, subprocess, time, sys, json

def main():
    denaro = os.path.expanduser("~")
    if not os.path.exists(os.path.join(denaro, "denaro")):
        # try specific user paths
        for p in ["/home/sergio/denaro", "/home/marco/denaro"]:
            if os.path.exists(p):
                denaro = p
                break
    
    db_path = os.path.join(denaro, "trades.db")
    venv_python = os.path.join(denaro, "venv", "bin", "python3")
    lm_path = os.path.join(denaro, "legion_manager_production.py")
    gw_path = os.path.join(denaro, "event_gateway.py")
    
    if not os.path.exists(lm_path):
        print(f"ERROR: {lm_path} not found!")
        sys.exit(1)
    
    # --- DB Setup ---
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("PRAGMA journal_mode=WAL;")
    c.execute("CREATE TABLE IF NOT EXISTS trades ("
              "id INTEGER PRIMARY KEY AUTOINCREMENT, "
              "symbol TEXT NOT NULL, side TEXT NOT NULL, "
              "entry_price REAL NOT NULL, exit_price REAL DEFAULT NULL, "
              "quantity REAL NOT NULL, pnl REAL DEFAULT NULL, "
              "pnl_pct REAL DEFAULT NULL, fee REAL DEFAULT NULL, "
              "entry_time TEXT NOT NULL, exit_time TEXT DEFAULT NULL, "
              "status TEXT DEFAULT 'open', strategy TEXT DEFAULT 'legion', "
              "exchange TEXT DEFAULT 'binance');")
    c.execute("CREATE TABLE IF NOT EXISTS bot_state ("
              "bot_name TEXT PRIMARY KEY, is_in_position INTEGER DEFAULT 0, "
              "entry_price REAL DEFAULT NULL, quantity REAL DEFAULT NULL, "
              "tp REAL DEFAULT NULL, sl REAL DEFAULT NULL, "
              "entry_time REAL DEFAULT NULL, last_heartbeat REAL DEFAULT NULL);")
    c.execute("CREATE TABLE IF NOT EXISTS auto_disabled ("
              "symbol TEXT PRIMARY KEY, disabled_at REAL NOT NULL, "
              "reason TEXT NOT NULL, win_rate REAL DEFAULT NULL);")
    conn.commit()
    c.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in c.fetchall()]
    c.execute("SELECT COUNT(*) FROM trades")
    trades = c.fetchone()[0]
    conn.close()
    print(f"DB OK: tables={tables}, trades={trades}")
    
    # --- Check env file has v4 params ---
    env_path = os.path.join(denaro, ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            env_content = f.read()
        if "INITIAL_CAPITAL" not in env_content:
            print("WARNING: .env missing v4 params - need update")
        else:
            print("ENV: v4 params present")
    
    # --- Kill legacy processes ---
    for proc in ["grid_bot_v3.py", "orchestrator.py", 
                 "momentum_scalper"]:
        subprocess.run(["pkill", "-f", proc], capture_output=True)
    time.sleep(1)
    print("Legacy processes: killed")
    
    # --- Start LegionManager v4 ---
    lm_log = os.path.join(denaro, "legion_production.log")
    with open(lm_log, "a") as log:
        proc = subprocess.Popen(
            [venv_python, lm_path],
            stdout=log, stderr=subprocess.STDOUT,
            cwd=denaro
        )
    print(f"LegionManager PID: {proc.pid}")
    
    # --- Start EventGateway ---
    gw_log = os.path.join(denaro, "event_gateway.log")
    with open(gw_log, "a") as log:
        proc2 = subprocess.Popen(
            [venv_python, gw_path],
            stdout=log, stderr=subprocess.STDOUT,
            cwd=denaro
        )
    print(f"EventGateway PID: {proc2.pid}")
    
    # Save PIDs for later check
    with open(os.path.join(denaro, ".v4_pids.json"), "w") as f:
        json.dump({"legion_manager": proc.pid, "event_gateway": proc2.pid}, f)
    
    print("Denaro v4.0 setup COMPLETATO!")
    print(f"Log files:")
    print(f"  {lm_log}")
    print(f"  {gw_log}")

if __name__ == "__main__":
    main()
