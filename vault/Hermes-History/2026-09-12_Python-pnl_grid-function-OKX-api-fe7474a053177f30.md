---
session_id: "api-fe7474a053177f30"
title: "Python pnl_grid function OKX"
source: api_server
model: prod
started: 2026-09-12 23:43
message_count: 8
estimated_cost_usd: 0.0021
tags: [hermes-history]
---

# Python pnl_grid function OKX
> `api-fe7474a053177f30` · 2026-09-12 23:43 →  · source=api_server · model=prod

## 🧑 User · 23:43
Python: scrivi pnl_grid(trades, fee) per un grid bot OKX con fee taker. Solo codice, max 8 righe.

## 🤖 Hermes · 23:43
def pnl_grid(trades, fee=0.001):
    pos, cash = 0.0, 0.0
    for t in trades:
        if t['side'] == 'buy':
            pos += t['size']
            cash -= t['size'] * t['price'] * (1 + fee)
        else:
            pos -= t['size']
            cash += t['size'] * t['price'] * (1 - fee)
    return cash + pos * trades[-1]['price']

## 🧑 User · 23:43
Python: scrivi pnl_grid(trades, fee) per un grid bot OKX con fee taker. Solo codice, max 8 righe.

## 🤖 Hermes · 23:43
def pnl_grid(trades, fee):
    buys = [t for t in trades if t['side'] == 'buy']
    sells = [t for t in trades if t['side'] == 'sell']
    cost = sum(t['price'] * t['qty'] * (1 + fee) for t in buys)
    rev = sum(t['price'] * t['qty'] * (1 - fee) for t in sells)
    return rev - cost

## 🧑 User · 23:54
Python: scrivi pnl_grid(trades, fee) per un grid bot OKX con fee taker. Solo codice, max 8 righe.

## 🤖 Hermes · 23:54
```python
def pnl_grid(trades, fee):
    buys = [t for t in trades if t["side"] == "buy"]
    sells = [t for t in trades if t["side"] == "sell"]
    qty = min(sum(t["qty"] for t in buys), sum(t["qty"] for t in sells))
    avg_buy = sum(t["price"] * t["qty"] for t in buys) / sum(t["qty"] for t in buys)
    avg_sell = sum(t["price"] * t["qty"] for t in sells) / sum(t["qty"] for t in sells)
    return qty * (avg_sell * (1 - fee) - avg_buy * (1 + fee))
```

## 🧑 User · 23:54
Python: scrivi pnl_grid(trades, fee) per un grid bot OKX con fee taker. Solo codice, max 8 righe.

## 🤖 Hermes · 23:54
def pnl_grid(trades, fee):
    spent = sum(t['price'] * t['size'] for t in trades if t['side'] == 'buy')
    received = sum(t['price'] * t['size'] for t in trades if t['side'] == 'sell')
    fees = sum(t['price'] * t['size'] * fee for t in trades)
    return received - spent - fees

