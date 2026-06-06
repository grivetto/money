#!/usr/bin/env python3
"""Quick collector — scrive portfolio.json con dati aggregati + Binance total"""
import json, time, subprocess
from pathlib import Path

DASHBOARD = Path("/var/www/html/denaro")

# Valori noti da Binance (Master + sergio@grivetto.eu che il collector non vede)
KNOWN_BTC = {
    "master": 0.00086053,
    "sergio_grivetto": 0.00081351,
}

def get_btc_price():
    try:
        import ccxt
        return ccxt.binance().fetch_ticker("BTC/USDT")["last"]
    except:
        return 60000

def collect_node(host, home, venv):
    """Esegue query CCXT sul nodo remoto"""
    script = '''import ccxt,json,os
home="''' + home + '''"
k=s=""
with open(home+"/.env") as f:
 for l in f:
  l=l.strip()
  if "BINANCE_API_KEY" in l and "SECRET" not in l:
   p=l.split("=",1)
   if len(p)==2:k=p[1].strip().strip(chr(39)).strip(chr(34))
  if "BINANCE_API_SECRET" in l:
   p=l.split("=",1)
   if len(p)==2:s=p[1].strip().strip(chr(39)).strip(chr(34))
ex=ccxt.binance({"apiKey":k,"secret":s,"enableRateLimit":True})
b=ex.fetch_balance()
fr={a:round(v,8) for a,v in b.get("free",{}).items() if v and v>1e-8}
tot={a:round(v,8) for a,v in b.get("total",{}).items() if v and v>1e-8}
pr={}
for sy in ["SOL/USDT","ADA/USDT","DOGE/USDT","BTC/USDT","ETH/USDT","BNB/USDT"]:
 try:pr[sy]=ex.fetch_ticker(sy)["last"]
 except:pass
print(json.dumps({"free":fr,"total":tot,"prices":pr}))
'''
    try:
        r = subprocess.run(
            ["ssh","-o","ConnectTimeout=5",host, venv+" -c '"+script+"'"],
            capture_output=True, text=True, timeout=30
        )
        if r.returncode == 0 and r.stdout.strip():
            return json.loads(r.stdout.strip())
    except:
        pass
    return {"free": {}, "total": {}, "prices": {}}

def node_value(total, prices):
    val = 0
    for a, q in total.items():
        if a in ("USDT","USDC"):
            val += q
        elif a == "EUR":
            val += q * 1.15
        else:
            val += q * prices.get(a+"/USDT", 0)
    return round(val, 2)

# === COLLECT ===
nodes = [
    ("MC2",      "sergio@mc2",      "/home/sergio/denaro",      "/home/sergio/denaro/venv/bin/python3"),
    ("Nuvola",   "sergio@nuvola",   "/home/sergio/denaro",      "/home/sergio/denaro/venv/bin/python3"),
    ("MARCODG1", "marco@MARCODG1",  "/home/marco/denaro",       "/home/marco/denaro/venv/bin/python3"),
]

btc_price = get_btc_price()
all_assets = {}
node_vals = {}
prices_all = {}

# Nuvola local
print("[Nuvola] local query...")
import ccxt as _ccxt
_home = "/home/sergio/denaro"
_k = _s = ""
with open(_home+"/.env") as f:
    for l in f:
        l = l.strip()
        if "BINANCE_API_KEY" in l and "SECRET" not in l:
            p = l.split("=",1)
            if len(p)==2: _k = p[1].strip().strip("'").strip('"')
        if "BINANCE_API_SECRET" in l:
            p = l.split("=",1)
            if len(p)==2: _s = p[1].strip().strip("'").strip('"')
_ex = _ccxt.binance({"apiKey":_k,"secret":_s,"enableRateLimit":True})
_b = _ex.fetch_balance()
_nuvola_total = {a:round(v,8) for a,v in _b.get("total",{}).items() if v and v>1e-8}
_nuvola_prices = {}
for sy in ["SOL/USDT","ADA/USDT","DOGE/USDT","BTC/USDT","ETH/USDT","BNB/USDT"]:
    try: _nuvola_prices[sy] = _ex.fetch_ticker(sy)["last"]
    except: pass
nv = node_value(_nuvola_total, _nuvola_prices)
node_vals["Nuvola"] = nv
prices_all.update(_nuvola_prices)
for a,q in _nuvola_total.items():
    all_assets[a] = all_assets.get(a,0) + q
print(f"  ${nv}")

# Remote nodes
for name, host, home, venv in [("MC2","sergio@mc2","/home/sergio/denaro","/home/sergio/denaro/venv/bin/python3"),("MARCODG1","marco@MARCODG1","/home/marco/denaro","/home/marco/denaro/venv/bin/python3")]:
    print(f"[{name}] remote query...")
    data = collect_node(host, home, venv)
    tot = data.get("total", {})
    pr = data.get("prices", {})
    nv = node_value(tot, pr)
    node_vals[name] = nv
    prices_all.update(pr)
    for a,q in tot.items():
        all_assets[a] = all_assets.get(a,0) + q
    print(f"  ${nv}")

# Add Master + sergio BTC
extra_btc = KNOWN_BTC["master"] + KNOWN_BTC["sergio_grivetto"]
extra_val = extra_btc * btc_price
all_assets["BTC"] = all_assets.get("BTC", 0) + extra_btc

trading_total = sum(node_vals.values())
grand_total = trading_total + extra_val

output = {
    "ts": time.strftime("%H:%M"),
    "trading_usd": round(trading_total, 2),
    "binance_total_usd": round(grand_total, 2),
    "binance_total_eur": round(grand_total / 1.15, 2),
    "btc_price": round(btc_price, 2),
    "extra_btc": round(extra_btc, 8),
    "extra_usd": round(extra_val, 2),
    "nodes": node_vals,
    "prices": {k: round(v,2) for k,v in prices_all.items()},
}

with open(DASHBOARD / "portfolio.json", "w") as f:
    json.dump(output, f, indent=2)

print(f"\nTrading: ${trading_total}")
print(f"Master+sergio: ${extra_val} ({extra_btc:.8f} BTC)")
print(f"GRAND TOTAL: ${grand_total} (EUR {grand_total/1.15:.0f})")
