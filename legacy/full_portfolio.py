#!/usr/bin/env python3
"""Full portfolio reconciliation"""
import json, sys
sys.path.insert(0, '/home/sergio/denaro/venv/lib/python3.12/site-packages')
from binance.client import Client

with open('/home/sergio/denaro/.env') as f:
    env = {}
    for line in f:
        line = line.strip()
        if '=' in line and not line.startswith('#'):
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip()

c = Client(env['BINANCE_API_KEY'], env['BINANCE_API_SECRET'])
tickers = {p['symbol']: float(p['price']) for p in c.get_symbol_ticker()}
eurusdt = tickers.get('EURUSDT', 0)
usdteur = 1.0/eurusdt if eurusdt > 0 else 0.85

acc = c.get_account()
non_zero = []
for b in acc['balances']:
    free = float(b['free'])
    locked = float(b['locked'])
    if free + locked == 0:
        continue
    asset = b['asset']
    val = 0.0
    if asset == 'EUR':
        val = free + locked
    elif asset + 'EUR' in tickers:
        val = (free + locked) * tickers[asset + 'EUR']
    elif asset + 'USDT' in tickers:
        val = (free + locked) * tickers[asset + 'USDT'] * usdteur
    else:
        val = (free + locked) * usdteur  # fallback
    non_zero.append({'asset': asset, 'free': free, 'locked': locked, 'value_eur': round(val, 2)})
    if val > 0.5:
        print(f"  {asset:6s} free={free:10.4f} locked={locked:10.4f}  EUR={val:8.2f}€")

total = sum(a['value_eur'] for a in non_zero)
print(f"  {'TOTAL':6s} {'':>24s} {total:8.2f}€")
print(f"  Assets: {[a['asset'] for a in non_zero if a['value_eur'] > 0.5]}")
