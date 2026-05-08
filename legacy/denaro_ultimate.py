#!/usr/bin/env python3
import os, time, json, sqlite3, sys
from datetime import datetime
from binance.client import Client
from logging.handlers import RotatingFileHandler
import logging

# --- LOGGING ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler('/home/sergio/denaro/bot_ultimate.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("DENARO_ULTIMATE")

# --- SYMBOL MAPPING (Binance compatibility) ---
SYMBOL_MAP = {
    "SOLEUR": "SOLUSDT",
    "ETHEUR": "ETHUSDT",
    "BTCEUR": "BTCUSDT"
}

# --- CORE ---
class DenaroCore:
    def __init__(self):
        self.db_path = "/home/sergio/denaro/trades.db"
        self.config_path = "/home/sergio/denaro/liquidity_config.json"
        self._init_db()
        self.client = None
        self.logger = logging.getLogger("Core")

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS trades (
            timestamp TEXT, symbol TEXT, side TEXT, price REAL, amount REAL, 
            profit REAL, bot_name TEXT, order_id TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS heartbeats (
            bot_name TEXT PRIMARY KEY, last_seen TEXT, status TEXT, current_pnl REAL)""")
        conn.commit()
        conn.close()

    def get_client(self):
        if self.client is None:
            from dotenv import load_dotenv
            load_dotenv("/home/sergio/denaro/.env")
            api_key = os.getenv("BINANCE_API_KEY")
            api_secret = os.getenv("BINANCE_API_SECRET")
            if not api_key or not api_secret:
                self.logger.error("API keys missing!")
                return None
            self.client = Client(api_key, api_secret)
        return self.client

    def update_heartbeat(self, bot_name, status="ALIVE", pnl=0.0):
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            now = datetime.now().isoformat()
            c.execute("""INSERT OR REPLACE INTO heartbeats 
                         (bot_name, last_seen, status, current_pnl) 
                         VALUES (?, ?, ?, ?)""",
                      (bot_name, now, status, pnl))
            conn.commit()
            conn.close()
        except Exception as e:
            self.logger.error(f"Heartbeat failed: {e}")

# --- BOT GRID ---
class RealisticGridBot:
    def __init__(self, user_symbol):
        self.user_symbol = user_symbol.upper()
        self.pair = SYMBOL_MAP.get(self.user_symbol, self.user_symbol)
        self.core = DenaroCore()
        self.logger = logging.getLogger(f"BOT-{self.user_symbol}")
        self.logger.info(f"User Symbol: {self.user_symbol} → Pair: {self.pair}")
        self.strategy = self._load_strategy()

    def _load_strategy(self):
        fname = f"/home/sergio/denaro/strategy_{self.user_symbol.lower()}.json"
        if os.path.exists(fname):
            with open(fname) as f:
                return json.load(f)
        return {
            "pair": self.pair,
            "profit_target": 0.015,
            "grid_levels": 6,
            "order_size_eur": 50.0
        }

    def _get_price_range(self):
        cl = self.core.get_client()
        if not cl: 
            self.logger.error("No Binance client!")
            return None, None, None
        try:
            klines = cl.get_klines(symbol=self.pair, interval='1h', limit=24)
            prices = [float(k[4]) for k in klines]
            curr = prices[-1]
            high, low = max(prices), min(prices)
            span = max(0.01, ((high - low) / curr) * 1.2)
            lower = curr * (1 - span)
            upper = curr * (1 + span)
            return lower, upper, curr
        except Exception as e:
            self.logger.error(f"Price fetch error: {e}")
            return None, None, None

    def _place_grid(self, lower, upper, current):
        cl = self.core.get_client()
        if not cl: 
            return 0
        try:
            cl.cancel_all_orders(symbol=self.pair)
            step = (upper - lower) / self.strategy['grid_levels']
            budget = self.strategy['order_size_eur'] * 3
            count = 0
            
            # BUY orders (below current)
            for i in range(self.strategy['grid_levels'] // 2):
                price = current - (step * (i + 1))
                amount = (budget / self.strategy['grid_levels']) / price * 0.995
                try:
                    cl.create_order(
                        symbol=self.pair, side='BUY', type='LIMIT',
                        quantity=round(amount, 6), price=round(price, 2),
                        timeInForce='GTC'
                    )
                    count += 1
                except Exception as e:
                    self.logger.warning(f"Buy order failed: {e}")
            
            # SELL orders (above current)
            for i in range(self.strategy['grid_levels'] // 2):
                price = current + (step * (i + 1))
                amount = (budget / self.strategy['grid_levels']) / current * 0.995
                try:
                    cl.create_order(
                        symbol=self.pair, side='SELL', type='LIMIT',
                        quantity=round(amount, 6), price=round(price, 2),
                        timeInForce='GTC'
                    )
                    count += 1
                except Exception as e:
                    self.logger.warning(f"Sell order failed: {e}")
            
            self.logger.info(f"Grid placed: {count} orders on {self.pair}")
            return count
        except Exception as e:
            self.logger.error(f"Grid placement error: {e}")
            return 0

    def run(self):
        self.logger.info(f"🚀 DENARO ULTIMATE started for {self.user_symbol}")
        self.core.update_heartbeat(self.user_symbol, "ALIVE", 0.0)
        
        while True:
            try:
                # 1. Calcola range e piazza ordini
                lower, upper, current = self._get_price_range()
                if lower:
                    self._place_grid(lower, upper, current)
                
                # 2. Heartbeat
                self.core.update_heartbeat(self.user_symbol, "ALIVE", 0.0)
                self.logger.info(f"Cycle complete. Heartbeat sent.")
                
                # 3. Sleep 5 min
                time.sleep(300)
            except Exception as e:
                self.logger.error(f"Main loop error: {e}")
                time.sleep(30)

if __name__ == "__main__":
    symbol = sys.argv[1] if len(sys.argv) > 1 else "SOLEUR"
    bot = RealisticGridBot(symbol)
    bot.run()
