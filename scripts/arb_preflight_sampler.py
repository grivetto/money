#!/usr/bin/env python3
"""Campionatore spread cross-venue (OKX vs Bybit) — sola lettura, endpoint pubblici.

REQ-MERL-20261102-036: la raccolta 48-72h non e' mai stata consegnata. Questo
campionatore fa la pre-schermo onesta con tick simultanei pubblici: se lo spread
LORDO (caso piu' favorevole possibile: liquidita' globale, zero costi, zero latenza)
sta sotto il costo di giro, la lane si chiude senza la raccolta lunga.

Uso: python scripts/arb_preflight_sampler.py [out.jsonl] [round] [intervallo_s]
"""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import ccxt

SYM = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "DOGE/USDT",
       "ADA/USDT", "DOT/USDT", "LTC/USDT", "LINK/USDT", "AVAX/USDT"]
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("prove/arb_ticks.jsonl")
ROUNDS = int(sys.argv[2]) if len(sys.argv) > 2 else 35
INTERVAL = float(sys.argv[3]) if len(sys.argv) > 3 else 15.0

ex = {"okx": getattr(ccxt, "okx")(), "bybit": getattr(ccxt, "bybit")()}
for e in ex.values():
    e.enableRateLimit = True

OUT.parent.mkdir(parents=True, exist_ok=True)
n = 0
with OUT.open("a", encoding="utf-8") as f:
    for i in range(ROUNDS):
        row = {"ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
               "q": {}}
        for name, e in ex.items():
            try:
                t = e.fetch_tickers(SYM)
                row["q"][name] = {s: {"bid": t[s]["bid"], "ask": t[s]["ask"]}
                                  for s in SYM if t[s].get("bid") and t[s].get("ask")}
            except Exception as err:  # noqa: BLE001
                row["q"][name] = {"err": type(err).__name__}
        f.write(json.dumps(row) + "\n")
        f.flush()
        n += 1
        print(f"[{n}/{ROUNDS}] {row['ts']} "
              f"okx={len(row['q'].get('okx', {}))} bybit={len(row['q'].get('bybit', {}))}",
              flush=True)
        if i < ROUNDS - 1:
            time.sleep(INTERVAL)
print("FINE", n, "round in", OUT)
