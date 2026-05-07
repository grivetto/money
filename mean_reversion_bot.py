#!/usr/bin/env python3
"""
DENARO MEAN REVERSION BOT v1
Uses Bollinger Bands (20, 2) to detect overbought/oversold conditions.
When price < lower band, increase exposure (long bias).
When price > upper band, decrease exposure (short bias or reduce long).
"""
import os, json, time, logging, ccxt
from dotenv import load_dotenv
from vault_utils import atomic_write, atomic_read

load_dotenv(os.path.join(os.path.dirname(__file__) or ".", ".env"))

SYMBOL = "ETH/EUR"
TIMEFRAME = "1h"
BB_LEN = 20
BB_STD = 2
STATE_FILE = os.path.join(os.path.dirname(__file__) or ".", "meanrev_state.json")
LOG_FILE = os.path.join(os.path.dirname(__file__) or ".", "meanrev.log")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - MEANREV - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler(LOG_FILE)])
logger = logging.getLogger("MeanReversion")

ex = ccxt.binance({
    'apiKey': os.getenv("BINANCE_API_KEY"),
    'secret': os.getenv("BINANCE_API_SECRET"),
    'enableRateLimit': True,
    'options': {'defaultType': 'spot', 'defaultFeeCurrency': 'BNB'},
)

def get_ohlcv(limit=50):
    return ex.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=limit)

def bollinger_bands(prices, length=20, num_std=2):
    if len(prices) < length:
        return None, None, None
    recent = prices[-length:]
    ma = sum(recent) / length
    variance = sum((p - ma) ** 2 for p in recent) / length
    std = variance ** 0.5
    upper = ma + num_std * std
    lower = ma - num_std * std
    return lower, ma, upper

def compute_signal():
    ohlcv = get_ohlcv(50)
    if not ohlcv:
        return 0.5
    close = [c[4] for c in ohlcv]
    lower, ma, upper = bollinger_bands(close, BB_LEN, BB_STD)
    if lower is None:
        return 0.5
    price = close[-1]
    # If price below lower band -> oversold -> increase exposure (max 1.5)
    # If price above upper band -> overbought -> decrease exposure (min 0.5)
    # Linear mapping between bands
    if price <= lower:
        exposure = 1.5
    elif price >= upper:
        exposure = 0.5
    else:
        # interpolate
        # range from lower to upper maps to 1.5 down to 0.5
        ratio = (price - lower) / (upper - lower)  # 0 at lower, 1 at upper
        exposure = 1.5 - ratio * 1.0  # 1.5 at lower, 0.5 at upper
    # clamp
    exposure = max(0.5, min(1.5, exposure))
    logger.info(f"MeanRev: price={price:.2f} lower={lower:.2f} upper={upper:.2f} ma={ma:.2f} -> exposure {exposure:.2f}")
    return exposure

def load_state():
    try: return json.load(open(STATE_FILE))
    except: return {"exposure": 0.5, "timestamp": 0}

def save_state(s):
    s["timestamp"] = int(time.time())
    tmp = STATE_FILE + ".tmp"
    json.dump(s, open(tmp, "w"))
    os.replace(tmp, STATE_FILE)

def main():
    state = load_state()
    exposure = compute_signal()
    state["exposure"] = exposure
    save_state(state)
    logger.info(f"Saved meanrev exposure {exposure:.2f}")

if __name__ == "__main__":
    logger.info("🟢 Mean Reversion Bot started")
    while True:
        try:
            main()
        except Exception as e:
            logger.error(f"Error: {e}")
        time.sleep(300)  # every 5 min
