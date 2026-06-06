#!/usr/bin/env python3
"""Collector v14 - esegue CCXT su ogni nodo remoto"""
import json, time, subprocess, sys
from pathlib import Path

DASHBOARD = Path("/var/www/html/denaro")

QUERY_SCRIPT = '''
import ccxt, json, os
home = "HOMEPLACEHOLDER"
key = ""
secret = ""
with open(home + "/.env") as f:
    for line in f:
        line = line.strip()
        if "BINANCE_API_KEY" in line and "SECRET" not in line:
            parts = line.split("=", 1)
            if len(parts) == 2:
                key = parts[1].strip().strip(chr(39)).strip(chr(34))
        if "BINANCE_API_SECRET" in line:
            parts = line.split("=", 1)
            if len(parts) == 2:
                secret = parts[1].strip().strip(chr(39)).strip(chr(34))
ex = ccxt.binance({"apiKey": key, "secret": secret, "enableRateLimit": True})
bal = ex.fetch_balance()
free = {}
for k, v in bal.get("free", {}).items():
    if v and v > 0.00000001:
        free[k] = round(v, 8)
prices = {}
for sym in ["SOL/USDT","ADA/USDT","DOGE/USDT","BTC/USDT","ETH/USDT","BNB/USDT"]:
    try:
        prices[sym] = ex.fetch_ticker(sym)["last"]
    except:
        pass
print(json.dumps({"free": free, "prices": prices}))
'''

def query_remote(host, home, venv):
    """Esegue lo script CCXT sul nodo remoto"""
    script = QUERY_SCRIPT.replace("HOMEPLACEHOLDER", home)
    cmd = venv + " -c '" + script + "'"
    try:
        r = subprocess.run(
            ["ssh","-o","ConnectTimeout=5",host,cmd],
            capture_output=True, text=True, timeout=30
        )
        if r.returncode == 0 and r.stdout.strip():
            return json.loads(r.stdout.strip())
        if r.stderr:
            print("  stderr: " + r.stderr[:200], file=sys.stderr)
    except Exception as e:
        print("  SSH error: " + str(e), file=sys.stderr)
    return {"free": {}, "prices": {}}

nodes = [
    ("MC2",      "sergio@mc2",      "/home/sergio/denaro",      "/home/sergio/denaro/venv/bin/python3"),
    ("Nuvola",   "sergio@nuvola",   "/home/sergio/denaro",      "/home/sergio/denaro/venv/bin/python3"),
    ("MARCODG1", "marco@MARCODG1",  "/home/marco/denaro",       "/home/marco/denaro/venv/bin/python3"),
]

all_free = {}
all_prices = {}
node_values = {}

for name, host, home, venv in nodes:
    print("[" + name + "] querying...")
    data = query_remote(host, home, venv)
    free = data.get("free", {})
    prices = data.get("prices", {})
    
    for a, q in free.items():
        all_free[a] = all_free.get(a, 0) + q
    all_prices.update(prices)
    
    val = 0
    for a, q in free.items():
        if a in ("USDT", "USDC"):
            val += q
        elif a == "EUR":
            val += q * 1.15
        else:
            val += q * prices.get(a + "/USDT", 0)
    node_values[name] = round(val, 2)
    assets_str = ", ".join(free.keys()) if free else "NONE"
    print("  $" + str(val) + " | " + assets_str)

total = sum(node_values.values())

output = {
    "ts": time.strftime("%H:%M"),
    "total_usd": round(total, 2),
    "total_eur": round(total / 1.15, 2),
    "nodes": node_values,
    "assets": {k: round(v, 8) for k, v in sorted(all_free.items()) if v > 0.00000001},
    "prices": all_prices,
    "btc_total": round(all_free.get("BTC", 0), 8),
}

with open(DASHBOARD / "portfolio.json", "w") as f:
    json.dump(output, f, indent=2)

print("\n=== TOTALE: $" + str(total) + " (EUR " + str(round(total/1.15, 2)) + ") ===")
for n, v in node_values.items():
    print("  " + n + ": $" + str(v))
if "BTC" in all_free:
    print("  BTC totale: " + str(all_free["BTC"]))
