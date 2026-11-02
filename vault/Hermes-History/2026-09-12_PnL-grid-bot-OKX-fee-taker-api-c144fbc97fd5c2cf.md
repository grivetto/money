---
session_id: "api-c144fbc97fd5c2cf"
title: "PnL grid bot OKX fee taker"
source: api_server
model: prod
started: 2026-09-12 23:23
message_count: 2
estimated_cost_usd: 0.0009
tags: [hermes-history]
---

# PnL grid bot OKX fee taker
> `api-c144fbc97fd5c2cf` · 2026-09-12 23:23 →  · source=api_server · model=prod

## 🧑 User · 23:23
Python: scrivi pnl_grid(trades, fee) per grid bot OKX con fee taker. Solo codice, max 8 righe.

## 🤖 Hermes · 23:24
<details><summary>🧠 Ragionamento</summary>

We need to output only code, max 8 lines. Provide a function pnl_grid(trades, fee) for grid bot OKX with taker fee. Should be correct. Let's pick a clear implementation. Use trades list of dicts with side, price, qty. Compute PnL including fee on each trade (taker). Fee applied to notional absolute value. Provide code within 8 lines.

We'll output just code.



</details>
def pnl_grid(trades, fee):
    pnl = 0.0
    for t in trades:
        notional = t["price"] * t["qty"]
        if t["side"] == "buy":
            pnl -= notional * (1 + fee)
        else:
            pnl += notional * (1 - fee)
    return pnl

