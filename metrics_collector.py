#!/usr/bin/env python3
"""Denaro metrics collector - writes JSON for dashboard, runs every 30s"""
import json, subprocess, os, time
BASE = "/home/sergio/denaro/dashboard/public"
os.makedirs(BASE, exist_ok=True)

def ssh(host, cmd, timeout=10):
    try:
        if host in ("nuvola", "127.0.0.1", "localhost"):
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
            return r.stdout.strip()
        r = subprocess.run(["ssh", "-o", "ConnectTimeout=5", host, cmd], capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except: return ""

def gval(out, marker, default="0"):
    for line in out.split("\n"):
        if marker in line:
            return line.split(marker)[1].strip().split()[0] if marker in line else default
    return default

# NUVOLA
n = ssh("nuvola", "echo BOT=$(pgrep -c -f grid_bot_v3.py 2>/dev/null); echo WDG=$(pgrep -c -f watchdog.sh 2>/dev/null); echo INV=$(grep -oP 'Invested: \\K[0-9.]+' /home/sergio/denaro/grid.log 2>/dev/null | tail -1); echo PRF=$(grep -oP 'Profit: \\K[0-9.]+' /home/sergio/denaro/grid.log 2>/dev/null | tail -1); echo PRI=$(grep -oP 'Price: \\K[0-9.]+' /home/sergio/denaro/grid.log 2>/dev/null | tail -1); echo TREND=$(grep -oP 'Trend: \\K[A-Z_]+' /home/sergio/denaro/grid.log 2>/dev/null | tail -1); echo RSI=$(grep -oP 'RSI: \\K[0-9.]+' /home/sergio/denaro/grid.log 2>/dev/null | tail -1); echo TRADES=$(grep -c 'SELL filled' /home/sergio/denaro/grid.log 2>/dev/null); echo ACTIVE=$(zabbix_agentd -t denaro.service.active 2>/dev/null | grep -o 'active\\|inactive'); echo DISK=$(df -h / | tail -1 | awk '{print $5}' | tr -d '%'); echo MEM=$(free -m | grep Mem | awk '{printf \"%.0f\", $3/$2*100}')")

nuvola = {
    "ts": time.strftime("%H:%M"), "b": int(gval(n,"BOT=","0")), "w": int(gval(n,"WDG=","0")),
    "i": float(gval(n,"INV=","0")), "p": float(gval(n,"PRF=","0")),
    "pr": float(gval(n,"PRI=","0")), "t": gval(n,"TREND=","?"),
    "r": float(gval(n,"RSI=","0")), "tr": int(gval(n,"TRADES=","0")),
    "a": gval(n,"ACTIVE=","?"), "d": int(gval(n,"DISK=","0") or "0"),
    "m": int(gval(n,"MEM=","0") or "0"), "v4": 1
}
json.dump(nuvola, open(f"{BASE}/nuvola.json","w"))

# MARCODG1
m = ssh("MARCODG1", "echo BOT=$(pgrep -c -f grid_bot_v3.py 2>/dev/null); echo WDG=$(pgrep -c -f watchdog.sh 2>/dev/null); echo INV=$(grep -oP 'Invested: \\K[0-9.]+' /home/marco/denaro/grid.log 2>/dev/null | tail -1); echo PRF=$(grep -oP 'Profit: \\K[0-9.]+' /home/marco/denaro/grid.log 2>/dev/null | tail -1); echo PRI=$(grep -oP 'Price: \\K[0-9.]+' /home/marco/denaro/grid.log 2>/dev/null | tail -1); echo TREND=$(grep -oP 'Trend: \\K[A-Z_]+' /home/marco/denaro/grid.log 2>/dev/null | tail -1); echo TRADES=$(grep -c 'SELL filled' /home/marco/denaro/grid.log 2>/dev/null); echo ACTIVE=$(zabbix_agentd -t denaro.service.active 2>/dev/null | grep -o 'active\\|inactive'); echo DISK=$(df -h / | tail -1 | awk '{print $5}' | tr -d '%'); echo MEM=$(free -m | grep Mem | awk '{printf \"%.0f\", $3/$2*100}')")

marcodg1 = {
    "ts": time.strftime("%H:%M"), "b": int(gval(m,"BOT=","0")), "w": int(gval(m,"WDG=","0")),
    "i": float(gval(m,"INV=","0")), "p": float(gval(m,"PRF=","0")),
    "pr": float(gval(m,"PRI=","0")), "t": gval(m,"TREND=","?"),
    "tr": int(gval(m,"TRADES=","0")), "a": gval(m,"ACTIVE=","?"),
    "d": int(gval(m,"DISK=","0") or "0"), "m": int(gval(m,"MEM=","0") or "0"), "v4": 1
}
json.dump(marcodg1, open(f"{BASE}/marcodg1.json","w"))

# MC2 + Scalper
log_xrp = "/home/sergio/denaro/momentum_scalper.log"
log_sol = "/home/sergio/denaro/momentum_scalper_sol.log"
log = log_xrp  # Primary log for backward compat
scp = 0; spp = 0; sppr = 0; sr = 0; sb = 0; se = 0; sdisk = 0; smem = 0

# Count both scalper processes
scp_xrp = int(subprocess.run(["pgrep","-c","-f","momentum_scalper.py"], capture_output=True,text=True).stdout.strip() or "0")
scp_sol = int(subprocess.run(["pgrep","-c","-f","momentum_scalper_sol.py"], capture_output=True,text=True).stdout.strip() or "0")
scp = scp_xrp + scp_sol

# Read PnL from both logs (cumulative)
for lg in [log_xrp, log_sol]:
    if os.path.exists(lg):
        txt = open(lg).read()
        for line in txt.split("\n")[-100:]:
            if "PnL totale:" in line:
                try:
                    # "📊 PnL totale: 0.1234€ (5 trade)"
                    p_str = line.split("PnL totale:")[1].split("€")[0].strip()
                    spp += float(p_str)
                except: pass
            if "ENTRY:" in line and "@" in line:
                try:
                    # Last entry price
                    sppr = float(line.split("@")[1].strip().split("€")[0].strip())
                except: pass
            if "RSI=" in line:
                try:
                    sr = float(line.split("RSI=")[1].split("|")[0].strip())
                except: pass
            if "BUY" in line and "ENTRY" in line:
                sb += 1

# Also count SELLs
for lg in [log_xrp, log_sol]:
    if os.path.exists(lg):
        sb += int(subprocess.run(["grep","-c","SELL|TP|SL",lg], capture_output=True,text=True).stdout.strip() or "0")

sdisk = int(subprocess.run(["df","-h","/"], capture_output=True,text=True).stdout.split("\n")[1].split()[4].strip("%"))
smem = round(float(subprocess.run(["free","-m"], capture_output=True,text=True).stdout.split("\n")[1].split()[2]) / float(subprocess.run(["free","-m"], capture_output=True,text=True).stdout.split("\n")[1].split()[1]) * 100)

mc2 = {
    "ts": time.strftime("%H:%M"), "sc": scp, "sp": round(spp,4),
    "spr": sppr, "sr": round(sr,1), "sb": sb,
    "se": se, "d": sdisk, "m": smem, "z": 1 if scp > 0 else 0,
    "profit": round(spp, 4),  # Cumulative PnL for dashboard
    "sc_xrp": scp_xrp, "sc_sol": scp_sol,
}
json.dump(mc2, open(f"{BASE}/mc2.json","w"))

print(f"OK {nuvola['ts']} N={nuvola['i']}€ M={marcodg1['i']}€ S={mc2['sp']}€")
