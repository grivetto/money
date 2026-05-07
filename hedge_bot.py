#!/usr/bin/env python3
"""
DENARO DELTA NEUTRAL HEDGING BOT v1
Maintains a delta-neutral position by holding spot and a short perpetual future.
For simplicity, we simulate by adjusting an exposure factor that the grid bot can read.
"""
import os, json, time, logging
from dotenv import load_dotenv
from vault_utils import atomic_write, atomic_read

load_dotenv(os.path.join(os.path.dirname(__file__) or ".", ".env"))

SYMBOL = "ETH/EUR"
STATE_FILE = os.path.join(os.path.dirname(__file__) or ".", "hedge_state.json")
LOG_FILE = os.path.join(os.path.dirname(__file__) or ".", "hedge.log")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - HEDGE - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler(LOG_FILE)])
logger = logging.getLogger("DeltaHedge")

def get_funding_rate():
    # Placeholder: Binance funding rate for ETHUSDT perpetual
    # In reality, we would fetch from fapi/v1/fundingRate
    return 0.0001  # example 0.01% per 8h

def main():
    state = {}
    funding = get_funding_rate()
    # If funding positive, longs pay shorts -> we want to be short perpetual to earn funding
    # For spot + short perpetual, delta approx 0
    # We'll just log and store a flag that the grid bot could reduce exposure if funding > threshold
    hedge_active = funding > 0.00005
    state["hedge_active"] = hedge_active
    state["funding_rate"] = funding
    tmp = STATE_FILE + ".tmp"
    json.dump(state, open(tmp, "w"))
    os.replace(tmp, STATE_FILE)
    logger.info(f"Funding rate: {funding*100:.4f}% -> hedge active: {hedge_active}")

if __name__ == "__main__":
    logger.info("🟢 Delta Neutral Hedging Bot started")
    while True:
        try:
            main()
        except Exception as e:
            logger.error(f"Error: {e}")
        time.sleep(300)  # every 5 min
