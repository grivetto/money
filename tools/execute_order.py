#!/usr/bin/env python3
"""
TOOL: execute_order
Layer 3 — Atomic order executor (limit only)
Input:  side (buy/sell), price (float), amount (float), symbol (str)
Output: dict with order details or error
"""
import sys
import json
import asyncio
import ccxt
from pathlib import Path

def main():
    side = sys.argv[1] if len(sys.argv) > 1 else "buy"
    price = float(sys.argv[2]) if len(sys.argv) > 2 else 0
    amount = float(sys.argv[3]) if len(sys.argv) > 3 else 0
    symbol = sys.argv[4] if len(sys.argv) > 4 else "SOL/EUR"

    if price <= 0 or amount <= 0:
        print(json.dumps({"error": "Invalid price or amount", "status": "rejected"}))
        return

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
        if side == "buy":
            order = client.create_limit_buy_order(symbol, round(amount, 5), round(price, 2))
        elif side == "sell":
            order = client.create_limit_sell_order(symbol, round(amount, 5), round(price, 2))
        else:
            print(json.dumps({"error": f"Unknown side: {side}", "status": "rejected"}))
            return

        result = {
            "status": "filled",
            "order_id": order['id'],
            "symbol": order['symbol'],
            "side": order['side'],
            "price": float(order['price']),
            "amount": float(order['amount']),
            "filled": float(order.get('filled', 0)),
            "remaining": float(order.get('remaining', 0)),
            "timestamp": order['timestamp'],
        }
        print(json.dumps(result))
    except ccxt.InsufficientFunds:
        print(json.dumps({"error": "Insufficient funds", "status": "rejected"}))
    except ccxt.InvalidOrder:
        print(json.dumps({"error": "Invalid order", "status": "rejected"}))
    except Exception as e:
        print(json.dumps({"error": str(e), "status": "error"}))

if __name__ == "__main__":
    main()
