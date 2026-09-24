#!/usr/bin/env python3
"""
DENARO CORE — Base class for trading bots (ASYNC version).
Provides: config management, Binance client, balance, ATR, order sync, trade logging.
"""
import os, json, time, logging, asyncio, ccxt
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__) or ".", ".env"))
logger = logging.getLogger("DenaroCore")

class DenaroCore:
    """Base class for Denaro trading bots. Provides shared infrastructure."""
    
    def __init__(self, bot_name="DenaroBot"):
        self.bot_name = bot_name
        self.config = self.load_config()
        self.client = self._create_client()
    
    def _create_client(self):
        return ccxt.binance({
            'apiKey': os.getenv("BINANCE_API_KEY"),
            'secret': os.getenv("BINANCE_API_SECRET"),
            'enableRateLimit': True,
            'options': {
                'defaultType': 'spot',
                'defaultFeeCurrency': 'BNB',
            }
        })
    
    def load_config(self):
        config_path = os.path.join(os.path.dirname(__file__) or ".", "grid_config.json")
        try:
            with open(config_path) as f:
                cfg = json.load(f)
            logger.info(f"[{self.bot_name}] Config loaded successfully: "
                       f"symbol={cfg.get('symbol', '?')}, symbol_ws={cfg.get('symbol_ws', '?')}")
            return cfg
        except Exception as e:
            logger.error(f"Config load error: {e}")
            return {
                "symbol": "SOL/EUR", "symbol_ws": "soleur",
                "grid_levels": 4, "base_order_eur": 20.0,
                "max_total_invested": 100.0, "grid_range_pct": 0.01,
                "profit_per_grid": 0.0025, "config_reload_sec": 60,
            }
    
    async def get_balance(self, currency='EUR'):
        try:
            bal = await asyncio.to_thread(self.client.fetch_balance)
            return bal['free'].get(currency, 0)
        except:
            return 0
    
    async def sync_orders(self, symbol):
        try:
            orders = await asyncio.to_thread(self.client.fetch_open_orders, symbol)
            return orders
        except:
            return []
    
    async def get_atr(self, symbol, timeframe='1h', lookback=14):
        try:
            ohlcv = await asyncio.to_thread(
                self.client.fetch_ohlcv, symbol, timeframe=timeframe, limit=lookback + 1
            )
            if len(ohlcv) < lookback + 1:
                return 0
            trs = []
            for i in range(1, len(ohlcv)):
                h, l, pc = ohlcv[i][2], ohlcv[i][3], ohlcv[i-1][4]
                trs.append(max(h - l, abs(h - pc), abs(l - pc)))
            return sum(trs[-lookback:]) / lookback
        except:
            return 0
    
    async def log_trade(self, symbol, side, price, amount, cost, fee, profit):
        logger.info(f"[TRADE] {side} {symbol}: {amount:.4f} @ {price:.2f}€ | "
                   f"Cost: {cost:.2f}€ Fee: {fee:.4f}€ Profit: {profit:.4f}€")
