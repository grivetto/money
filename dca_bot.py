#!/usr/bin/env python3
"""
DENARO DCA BOT v2 — Dollar-Cost Averaging Condizionale
Compra solo quando il prezzo scende >=2% sotto la media mobile.
Riduce le commissioni acquistando meno frequentemente ma a prezzi migliori.
"""
import os, json, time, logging, ccxt
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv(os.path.join(os.path.dirname(__file__) or ".", ".env"))

# === CONFIG ===
SYMBOL = "ETH/EUR"
AMOUNT_EUR = 5.0          # Acquisto base ridotto a 5€
INTERVAL_HOURS = 24        # Controlla ogni 24 ore
MIN_DIP_PCT = 3.0          # Acquista solo se prezzo >=3% sotto la media (più selettivo)
USE_PROFIT_ONLY = True     # Se True, usa solo i profitti del grid (non tocca il capitale EUR)
PROFIT_FILE = os.path.join(os.path.dirname(__file__) or ".", ".tmp/futures_state.json")
MAX_PRICE_HISTORY = 50      # Quanti prezzi giornalieri tenere in memoria
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
    except: return {"last_check": 0, "last_buy": 0, "total_invested": 0.0, 
                    "total_asset": 0.0, "price_history": [], "trades": []}

def save_state(s):
    tmp = STATE_FILE + ".tmp"
    json.dump(s, open(tmp, "w"))
    os.replace(tmp, STATE_FILE)

def dca():
    state = load_state()
    now = time.time()
    
    # Always check at INTERVAL_HOURS
    if now - state.get("last_check", 0) < INTERVAL_HOURS * 3600:
        next_check = datetime.fromtimestamp(state["last_check"] + INTERVAL_HOURS * 3600)
        logger.info(f"Prossimo controllo: {next_check.strftime('%Y-%m-%d %H:%M')}")
        return
    
    state["last_check"] = now
    
    try:
        ticker = ex.fetch_ticker(SYMBOL)
        price = ticker['last']
        
        # Update price history (1 entry per check, ~4 entries/day)
        state.setdefault("price_history", []).append({
            'time': now,
            'price': price
        })
        # Keep only last N entries
        if len(state['price_history']) > MAX_PRICE_HISTORY:
            state['price_history'] = state['price_history'][-MAX_PRICE_HISTORY:]
        save_state(state)
        
        # Calculate moving average from history
        prices = [p['price'] for p in state['price_history']]
        avg_price = sum(prices) / len(prices) if prices else price
        
        # Calculate dip percentage
        dip_pct = (avg_price - price) / avg_price * 100
        logger.info(f"ETH: {price:.2f}€ | Media {len(prices)} campioni: {avg_price:.2f}€ | Dip: {dip_pct:+.2f}%")
        
        # Check if price is low enough for a buy
        if dip_pct < MIN_DIP_PCT:
            logger.info(f"Dip {dip_pct:.1f}% < soglia {MIN_DIP_PCT}%, acquisto rimandato")
            return
        
        # Check minimum time since last buy (at least 24h)
        if now - state.get("last_buy", 0) < 86400:
            last_buy_time = datetime.fromtimestamp(state["last_buy"])
            logger.info(f"Ultimo acquisto: {last_buy_time.strftime('%Y-%m-%d %H:%M')} (<24h, aspetta)")
            return
        
        # Check balance
        bal = ex.fetch_balance()
        eur_free = bal['free'].get('EUR', 0)
        
        # Profit-only mode: use only grid profits, not capital
        if USE_PROFIT_ONLY:
            try:
                with open(PROFIT_FILE) as f:
                    pf = json.load(f)
                total_profit = pf.get('current_pnl', 0)
                if total_profit < AMOUNT_EUR:
                    logger.info(f"Profitto ({total_profit:.2f}€) < {AMOUNT_EUR}€, DCA rimandato (usa profitti)")
                    return
                available = min(eur_free, total_profit * 0.5)
                if available < AMOUNT_EUR:
                    logger.info(f"Disponibile {available:.2f}€ < {AMOUNT_EUR}€, aspetta")
                    return
                actual_amount_eur = min(AMOUNT_EUR, available)
                logger.info(f"Profit-only: {total_profit:.2f}€ profitti, usando {actual_amount_eur:.2f}€")
            except:
                logger.info("Profit file non disponibile, DCA rimandato")
                return
        else:
            actual_amount_eur = AMOUNT_EUR
        
        if eur_free < actual_amount_eur * 1.01:
            logger.warning(f"EUR insufficiente: {eur_free:.2f}€ (servono {actual_amount_eur:.2f}€)")
            return
        
        # Execute buy
        logger.info(f"✅ CONDIZIONE SODDISFATTA: dip {dip_pct:.1f}% >= {MIN_DIP_PCT}%")
        order = ex.create_market_buy_order(SYMBOL, round(actual_amount_eur / price, 5))
        actual_cost = float(order.get('cost', AMOUNT_EUR))
        actual_amount = float(order.get('filled', AMOUNT_EUR / price))
        
        state["last_buy"] = now
        state["total_invested"] += actual_cost
        state["total_asset"] += actual_amount
        state["trades"].append({
            "time": datetime.now().isoformat(),
            "price": price,
            "cost": round(actual_cost, 2),
            "amount": round(actual_amount, 5),
            "dip_pct": round(dip_pct, 2),
            "symbol": SYMBOL
        })
        state["trades"] = state["trades"][-50:]
        save_state(state)
        
        current_value = state["total_asset"] * price
        pnl = current_value - state["total_invested"]
        logger.info(f"✅ Comprato {actual_amount:.5f} ETH @ {price:.2f}€ (dip {dip_pct:.1f}%)")
        logger.info(f"   Investito: {state['total_invested']:.2f}€ | Valore: {current_value:.2f}€ | PnL: {pnl:.2f}€")
        
    except Exception as e:
        logger.error(f"Errore DCA: {e}")

if __name__ == "__main__":
    logger.info(f"🟢 DCA v2 avviato: {SYMBOL} {AMOUNT_EUR}€, minimo dip {MIN_DIP_PCT}%, check ogni {INTERVAL_HOURS}h")
    while True:
        dca()
        time.sleep(3600)
