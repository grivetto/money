#!/usr/bin/env python3
"""
TOOL: fetch_market_data
Layer 3 — Atomic market data fetcher
Input:  symbol (str), timeframe (str), limit (int)
Output: dict with ticker + ohlcv + atr
"""
import sys
import json
import ccxt
from pathlib import Path

def main():
    symbol = sys.argv[1] if len(sys.argv) > 1 else "SOL/EUR"
    timeframe = sys.argv[2] if len(sys.argv) > 2 else "15m"
    limit = int(sys.argv[3]) if len(sys.argv) > 3 else 20

    # Load env
    env_path = Path(__file__).parent.parent / ".env"
    from dotenv import load_dotenv
    load_dotenv(env_path)

    client = ccxt.binance({
        'apiKey': __import__('os').getenv('BINANCE_API_KEY'),
        'secret': __import__('os').getenv('BINANCE_API_SECRET'),
        'enableRateLimit': True,
        'options': {'defaultType': 'spot', 'defaultFeeCurrency': 'BNB'},
    })

    # Ticker
    ticker = client.fetch_ticker(symbol)
    ohlcv = client.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit + 1)

    # ATR (14-period)
    trs = []
    for i in range(1, len(ohlcv)):
        high, low, prev_close = ohlcv[i][2], ohlcv[i][3], ohlcv[i-1][4]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
    atr = sum(trs) / len(trs) if trs else 0
    atr_pct = atr / ticker['last'] if ticker['last'] else 0

    result = {
        "symbol": symbol,
        "timeframe": timeframe,
        "last": ticker['last'],
        "bid": ticker['bid'],
        "ask": ticker['ask'],
        "volume": ticker['quoteVolume'],
        "atr": atr,
        "atr_pct": atr_pct,
        "high_24h": ticker['high'],
        "low_24h": ticker['low'],
        "timestamp": ticker['timestamp'],
    }
    print(json.dumps(result))

if __name__ == "__main__":
    main()
