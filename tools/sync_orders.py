#!/usr/bin/env python3
"""
TOOL: sync_orders
Layer 3 — Sync open orders from exchange
Input:  symbol (str)
Output: dict with open_orders list, filled_orders list
"""
import sys
import json
import ccxt
from pathlib import Path

def main():
    symbol = sys.argv[1] if len(sys.argv) > 1 else "SOL/EUR"

    env_path = Path(__file__).parent.parent / ".env"
    from dotenv import load_dotenv
    load_dotenv(env_path)

    client = ccxt.binance({
        'apiKey': __import__('os').getenv('BINANCE_API_KEY'),
        'secret': __import__('os').getenv('BINANCE_API_SECRET'),
        'enableRateLimit': True,
        'options': {'defaultType': 'spot', 'defaultFeeCurrency': 'BNB'},
    })

    try:
        open_orders = client.fetch_open_orders(symbol)
        buy_orders = [o for o in open_orders if o['side'] == 'buy']
        sell_orders = [o for o in open_orders if o['side'] == 'sell']

        result = {
            "status": "ok",
            "total_open": len(open_orders),
            "buy_orders": [{"id": o['id'], "price": float(o['price']), "amount": float(o['amount']), "remaining": float(o.get('remaining', 0))} for o in buy_orders],
            "sell_orders": [{"id": o['id'], "price": float(o['price']), "amount": float(o['amount']), "remaining": float(o.get('remaining', 0))} for o in sell_orders],
        }
        print(json.dumps(result))
    except Exception as e:
        print(json.dumps({"error": str(e), "status": "error"}))

if __name__ == "__main__":
    main()
