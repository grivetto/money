#!/usr/bin/env python3
"""Denaro Health Monitor - run every hour for status and auto-healing"""
import subprocess, time, json, os
from datetime import datetime

HOME = os.path.expanduser("~")
LOG = f"{HOME}/denaro/health_monitor.log"

def log_msg(msg):
    t = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG, "a") as f:
        f.write(f"[{t}] {msg}\n")
    print(f"[{t}] {msg}")

def ssh(host, cmd, timeout=15):
    try:
        r = subprocess.run(["ssh", "-o", "ConnectTimeout=5", host, cmd],
                          capture_output=True, text=True, timeout=timeout)
        return r.stdout, r.returncode
    except Exception as e:
        return str(e), -1

def check_node(name, host, service, pair):
    problems = []
    info = {"name": name, "host": host, "status": "OK"}
    
    # 1. SSH connectivity
    out, code = ssh(host, "echo PONG")
    if "PONG" not in out:
        info["status"] = "FAIL"
        return info, ["SSH UNREACHABLE"]
    info["ssh"] = "OK"
    
    # 2. Service status
    out, code = ssh(host, f"systemctl --user is-active {service} 2>&1")
    if "active" not in out:
        problems.append(f"SERVICE_{service}_DEAD")
        info["service"] = "DEAD"
        # attempt restart
        ssh(host, f"systemctl --user restart {service} 2>&1", timeout=20)
        time.sleep(5)
        out2, _ = ssh(host, f"systemctl --user is-active {service} 2>&1")
        if "active" in out2:
            problems.append(f"SERVICE_RESTARTED")
            info["service"] = "RESTARTED"
        else:
            info["service"] = "FAIL"
    else:
        info["service"] = "active"
    
    # 3. Bot process
    out, code = ssh(host, "pgrep -c -f grid_bot_v3.py 2>/dev/null")
    bot_count = int(out.strip() or 0)
    info["bot"] = bot_count
    if bot_count == 0:
        problems.append("BOT_DEAD")
        info["status"] = "WARN"
        # restart through watchdog
        ssh(host, f"systemctl --user restart {service} 2>&1", timeout=20)
        time.sleep(8)
        out2, _ = ssh(host, "pgrep -c -f grid_bot_v3.py 2>/dev/null")
        if int(out2.strip() or 0) > 0:
            problems.append("BOT_RESTARTED")
            info["bot"] = int(out2.strip())
    
    # 4. Watchdog process
    out, code = ssh(host, "pgrep -c -f watchdog.sh 2>/dev/null")
    wdg_count = int(out.strip() or 0)
    info["wdg"] = wdg_count
    if wdg_count < 2:
        problems.append(f"WATCHDOG_LOW({wdg_count})")
        info["status"] = "WARN"
    
    # 5. Last trade log entry (staleness check)
    out, code = ssh(host, "stat -c %Y /home/$(whoami)/denaro/grid.log 2>/dev/null")
    if out.strip() and out.strip().isdigit():
        last_ts = int(out.strip())
        age = time.time() - last_ts
        info["log_age_s"] = int(age)
        if age > 600:  # 10 min stale
            problems.append(f"LOG_STALE({int(age)}s)")
            info["status"] = "WARN"
    
    # 6. Get trade info
    out, code = ssh(host, "tail -1 /home/$(whoami)/denaro/grid.log 2>/dev/null")
    info["trade"] = out.strip()[:120]
    
    # 7. Zabbix
    out, code = ssh(host, f"zabbix_agentd -t denaro.gridproc 2>&1")
    info["zabbix_g"] = out.strip()
    out, code = ssh(host, f"zabbix_agentd -t denaro.watchdog 2>&1")
    info["zabbix_w"] = out.strip()
    
    if not problems:
        info["status"] = "OK"
    elif all("RESTARTED" in p for p in problems):
        info["status"] = "RECOVERED"
    
    return info, problems

results = []
all_ok = True

# Check nodes
info, probs = check_node("NUVOLA", "nuvola", "wdg-watchdog.service", "SOL/EUR")
results.append((info, probs))
if probs: all_ok = False

info, probs = check_node("MARCODG1", "MARCODG1", "denaro-watchdog.service", "ADA/EUR")
results.append((info, probs))
if probs: all_ok = False

# MC2 self-check
mc2_disk = subprocess.run(["df", "-h", "/"], capture_output=True, text=True).stdout.split("\n")[1]
mc2_load = open("/proc/loadavg").read().strip()
mc2_mem = subprocess.run(["free", "-h"], capture_output=True, text=True).stdout.split("\n")[1]
mc2_info = f"disk={mc2_disk.split()[-2]} load={mc2_load.split()[:3]} mem={mc2_mem.split()[2]}"
log_msg(f"MC2: {mc2_info}")

# Log results
for info, probs in results:
    n = info["name"]
    s = info["status"]
    bot = info.get("bot", "?")
    wdg = info.get("wdg", "?")
    trade = info.get("trade", "")[:80]
    
    if s == "OK":
        log_msg(f"OK  {n}: bot={bot} wdg={wdg} serv={info['service']} trade={trade}")
    elif s == "RECOVERED":
        log_msg(f"REC {n}: {' '.join(probs)} -> trade={trade}")
    else:
        log_msg(f"ERR {n}: {' '.join(probs)}")
        for p in probs:
            print(f"ALERT: {n} - {p}")

# Summary line for Telegram
summary_parts = []
for info, probs in results:
    n = info["name"]
    s = info["status"]
    bot = info.get("bot", 0)
    trade = info.get("trade", "")
    if "Invested" in trade:
        inv = trade.split("Invested:")[1].split("|")[0].strip() if "|" in trade else "?"
    else:
        inv = "?"
    summary_parts.append(f"{n}={s}({inv}€)")

print(f"\n{'='*50}")
log_msg(f"SUMMARY: {' | '.join(summary_parts)}")

if not all_ok:
    exit(1)
