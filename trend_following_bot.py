#!/usr/bin/env python3
"""
DENARO TREND FOLLOWING BOT v1
Long-only trend following using EMA-200 and ADX.
When trend is strong up, increase exposure; when trend weak or down, reduce to cash.
"""
import os, json, time, logging, ccxt
from dotenv import load_dotenv
from vault_utils import atomic_write, atomic_read

load_dotenv(os.path.join(os.path.dirname(__file__) or ".", ".env"))

# CONFIG
SYMBOL = "ETH/EUR"
TIMEFRAME = "4h"
EMA_LEN = 200
ADX_LEN = 14
ADX_THRESH = 20
EXPOSURE_PCT = [0.0, 0.3, 0.6, 1.0]  # cash, low, medium, full
STATE_FILE = os.path.join(os.path.dirname(__file__) or ".", "trend_state.json")
LOG_FILE = os.path.join(os.path.dirname(__file__) or ".", "trend.log")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - TREND - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler(LOG_FILE)])
logger = logging.getLogger("TrendFollow")

ex = ccxt.binance({
    'apiKey': os.getenv("BINANCE_API_KEY"),
    'secret': os.getenv("BINANCE_API_SECRET"),
    'enableRateLimit': True,
    'options': {'defaultType': 'spot', 'defaultFeeCurrency': 'BNB'},
})

def get_ohlcv(limit=250):
    return ex.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=limit)

def ema(series, period):
    # simple EMA
    k = 2 / (period + 1)
    ema_val = series[0]
    for price in series[1:]:
        ema_val = price * k + ema_val * (1 - k)
    return ema_val

def adx(high, low, close, period=14):
    # simplified ADX calculation
    plus_dm = [max(high[i] - high[i-1], 0) for i in range(1, len(high))]
    minus_dm = [max(low[i-1] - low[i], 0) for i in range(1, len(low))]
    tr = [max(high[i] - low[i], abs(high[i] - close[i-1]), abs(low[i] - close[i-1])) for i in range(1, len(high))]
    # smth like Wilder smoothing; we'll approximate using EMA of length period
    def ema_wilder(arr, p):
        k = 1 / p
        res = [arr[0]]
        for a in arr[1:]:
            res.append(a * k + res[-1] * (1 - k))
        return res[-1]
    plus_di = 100 * ema_wilder(plus_dm, period) / ema_wilder(tr, period)
    minus_di = 100 * ema_wilder(minus_dm, period) / ema_wilder(tr, period)
    dx = (abs(plus_di - minus_di) / (plus_di + minus_di + 1e-9)) * 100
    adx_val = ema_wilder([dx] * period, period)  # not accurate but okay
    return adx_val

def compute_signal():
    ohlcv = get_ohlcv(500)
    if not ohlcv:
        return 0.0
    close = [c[4] for c in ohlcv]
    high = [c[2] for c in ohlcv]
    low = [c[3] for c in ohlcv]
    ema_val = ema(close, EMA_LEN)
    adx_val = adx(high, low, close, ADX_LEN)
    price = close[-1]
    # Determine trend strength
    if price > ema_val and adx_val > ADX_THRESH:
        trend = "strong_up"
    elif price < ema_val and adx_val > ADX_THRESH:
        trend = "strong_down"
    else:
        trend = "weak"
    # Map to exposure
    if trend == "strong_up":
        idx = 3
    elif trend == "strong_down":
        idx = 0
    elif trend == "weak" and price > ema_val:
        idx = 2
    else:
        idx = 1
    exposure = EXPOSURE_PCT[idx]
    logger.info(f"Trend: {trend} price={price:.2f} EMA{EMA_LEN}={ema_val:.2f} ADX={adx_val:.1f} -> exposure {exposure*100:.0f}%")
    return exposure

def load_state():
    try: return json.load(open(STATE_FILE))
    except: return {"exposure": 0.0, "last_asset": 0.0, "last_cash": 0.0}

def save_state(s):
    tmp = STATE_FILE + ".tmp"
    json.dump(s, open(tmp, "w"))
    os.replace(tmp, STATE_FILE)

def main():
    state = load_state()
    exposure = compute_signal()
    # For now just log; in future could adjust base order of grid bot via config file
    state["exposure"] = exposure
    save_state(state)
    logger.info(f"Saved exposure {exposure:.2f}")

if __name__ == "__main__":
    logger.info("🟢 Trend Following Bot started")
    while True:
        try:
            main()
        except Exception as e:
            logger.error(f"Error: {e}")
        time.sleep(3600)  # hourly
