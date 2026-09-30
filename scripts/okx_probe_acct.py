#!/usr/bin/env python3
"""Probe SOLA LETTURA del conto OKX EEA (main key): acctLv, permessi, saldi, tariffe, mercati.

Uso: python hermes_acct_probe.py [--env /path/main_okx.env]
Nessun ordine. Nessun movimento. Nessun valore di chiave stampato.
"""
import argparse
import json
import time
from pathlib import Path

import ccxt


def leggi_env(path):
    d = {}
    for ln in Path(path).read_text().splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#") or "=" not in ln:
            continue
        k, v = ln.split("=", 1)
        d[k.strip()] = v.strip().strip('"').strip("'")
    return d


ap = argparse.ArgumentParser()
ap.add_argument("--env", default="/home/marco/denaro/secrets/main_okx.env")
a = ap.parse_args()
env = leggi_env(a.env)

ex = ccxt.okx({
    "apiKey": env["OKX_API_KEY"], "secret": env["OKX_API_SECRET"],
    "password": env["OKX_PASSPHRASE"], "hostname": "eea.okx.com",
    "enableRateLimit": True, "options": {"defaultType": "spot"},
})

print("== account/config ==")
try:
    cfg = ex.privateGetAccountConfig()["data"][0]
    for campo in ("acctLv", "perm", "posMode", "acctStpMode", "mgnIsoMode",
                  "roleType", "kycLv"):
        if campo in cfg:
            print(f"  {campo}: {cfg[campo]}")
    print(f"  uid: [masked len={len(str(cfg.get('uid', '')))}]")
except Exception as e:
    print("  ERR", type(e).__name__, str(e)[:200])

print("== saldi funding (asset/balances) ==")
try:
    d = ex.privateGetAssetBalances({"ccy": "EUR,USDC,USDT"})["data"]
    if d:
        for row in d:
            print("  ", {k: row.get(k) for k in ("ccy", "availBal", "frozenBal")})
    else:
        print("  (nessun saldo nei ccy richiesti)")
except Exception as e:
    print("  ERR", type(e).__name__, str(e)[:200])

print("== saldi trading (account/balance) ==")
try:
    b = ex.privateGetAccountBalance()["data"][0]
    print("  totalEq:", b.get("totalEq"), "| isoEq:", b.get("isoEq"))
    for row in b.get("details", []):
        if row.get("ccy") in ("EUR", "USDC", "USDT"):
            print("  ", {k: row.get(k) for k in ("ccy", "availEq", "eq", "cashBal")})
except Exception as e:
    print("  ERR", type(e).__name__, str(e)[:200])

print("== tariffe (account/trade-fee) ==")
for it in ("SPOT", "SWAP"):
    try:
        d = ex.privateGetAccountTradeFee({"instType": it})["data"][0]
        rows = d.get("feeGroup") or d
        print(" ", it, "->", json.dumps(rows)[:420])
    except Exception as e:
        print(" ", it, "ERR", type(e).__name__, str(e)[:200])

print("== mercati EEA (pubblico) ==")
try:
    mk = ex.load_markets()
    tipi = {}
    for m in mk.values():
        tipi[m.get("type")] = tipi.get(m.get("type"), 0) + 1
    print("  tipi:", tipi)
    xperp = [m["symbol"] for m in mk.values() if "XPERP" in str(m.get("id", "")).upper()]
    print(f"  XPERP trovati: {len(xperp)}", xperp[:12])
    for s in ("DOT/USDT:USDT", "UNI/USDT:USDT", "AVAX/USDT:USDT", "BTC/USDT:USDT"):
        m = mk.get(s)
        if m:
            print(f"  {s} id={m['id']} contractSize={m.get('contractSize')} "
                  f"min={m['limits']['amount']['min']} mincost={m['limits']['cost']['min']} "
                  f"maker={m.get('maker')} taker={m.get('taker')}")
        else:
            print(f"  {s}: ASSENTE")
except Exception as e:
    print("  ERR", type(e).__name__, str(e)[:300])
print("timestamp", int(time.time()))
