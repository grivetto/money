#!/usr/bin/env python3
"""
DENARO DCA BOT v1 — Dollar-Cost Averaging
Compra importi fissi a intervalli regolari.
Complementa il grid trading per accumulo a lungo termine.
"""
import os, json, time, logging, ccxt
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv(os.path.join(os.path.dirname(__file__) or ".", ".env"))

# === CONFIG ===
SYMBOL = "ETH/EUR"
AMOUNT_EUR = 10.0       # Quantita' fissa in EUR ad ogni esecuzione
INTERVAL_HOURS = 6       # Ogni 6 ore
STATE_FILE = os.path.join(os.path.dirname(__file__) or ".", "dca_state.json")

LOG_FILE = os.path.join(os.path.dirname(__file__) or ".", "dca.log")
logging.basicConfig(level=logging.INFO, format='%(asctime)s - DCA - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler(LOG_FILE)])
logger = logging.getLogger("DCA")

ex = ccxt.binance({
    'apiKey': os.getenv("BINANCE_API_KEY"),
    'secret': os.getenv("BINANCE_API_SECRET"),
    'enableRateLimit': True,
    'options': {'defaultType': 'spot', 'defaultFeeCurrency': 'BNB'},
})

def load_state():
    try: return json.load(open(STATE_FILE))
    except: return {"last_buy": 0, "total_invested": 0.0, "total_asset": 0.0, "trades": []}

def save_state(s):
    tmp = STATE_FILE + ".tmp"
    json.dump(s, open(tmp, "w"))
    os.replace(tmp, STATE_FILE)

def dca():
    state = load_state()
    now = time.time()
    
    # Check if enough time has passed
    if now - state.get("last_buy", 0) < INTERVAL_HOURS * 3600:
        next_buy = datetime.fromtimestamp(state["last_buy"] + INTERVAL_HOURS * 3600)
        logger.info(f"Prossimo acquisto: {next_buy.strftime('%Y-%m-%d %H:%M')}")
        return
    
    try:
        ticker = ex.fetch_ticker(SYMBOL)
        price = ticker['last']
        amount = AMOUNT_EUR / price
        
        # Check balance
        bal = ex.fetch_balance()
        eur_free = bal['free'].get('EUR', 0)
        
        if eur_free < AMOUNT_EUR * 1.01:  # 1% buffer for fees
            logger.warning(f"EUR insufficiente: {eur_free:.2f}€ (servono {AMOUNT_EUR:.2f}€)")
            return
        
        # Execute buy
        order = ex.create_market_buy_order(SYMBOL, round(amount, 5))
        actual_cost = float(order['cost']) if order.get('cost') else AMOUNT_EUR
        actual_amount = float(order['filled']) if order.get('filled') else amount
        
        state["last_buy"] = now
        state["total_invested"] += actual_cost
        state["total_asset"] += actual_amount
        state["trades"].append({
            "time": datetime.now().isoformat(),
            "price": price,
            "cost": round(actual_cost, 2),
            "amount": round(actual_amount, 5),
            "symbol": SYMBOL
        })
        # Keep last 50 trades
        state["trades"] = state["trades"][-50:]
        
        save_state(state)
        
        current_value = state["total_asset"] * price
        pnl = current_value - state["total_invested"]
        
        logger.info(f"✅ DCA: comprato {actual_amount:.5f} {SYMBOL.split('/')[0]} @ {price:.2f}€")
        logger.info(f"   Investito: {state['total_invested']:.2f}€ | Valore: {current_value:.2f}€ | PnL: {pnl:.2f}€")
        
    except Exception as e:
        logger.error(f"Errore DCA: {e}")

if __name__ == "__main__":
    logger.info(f"🟢 DCA Bot avviato: {SYMBOL} {AMOUNT_EUR}€ ogni {INTERVAL_HOURS}h")
    while True:
        dca()
        time.sleep(3600)  # Check every hour
