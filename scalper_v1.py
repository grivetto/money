#!/usr/bin/env python3
"""
DENARO MICRO SCALPER v1 — High-frequency tactical scalper
Uses RSI(14) + MACD + EMA(9/21) crossovers on 1min candles.
Aggressive small trades for quick profits on MC2.
"""
import os, json, time, logging, ccxt, pandas as pd
import numpy as np
from datetime import datetime

# === CONFIG ===
SYMBOL = "ETH/EUR"
CAPITAL = 70.0          # Max capital to use
POSITION_SIZE = 12.0    # € per trade
MAX_POSITIONS = 2
TAKE_PROFIT_PCT = 0.005 # 0.5%
STOP_LOSS_PCT = 0.008   # 0.8%
MAX_DAILY_LOSS = 5.0    # Stop trading if daily loss exceeds this
TRAILING_ACTIVATION = 0.003  # Start trailing at 0.3% profit
TRAILING_DISTANCE = 0.002   # Trail by 0.2%
RSI_OVERSOLD = 35       # Buy when RSI below this
RSI_OVERBOUGHT = 65     # Sell when RSI above this
CHECK_INTERVAL = 30     # Seconds between checks

LOG_FILE = "/home/sergio/denaro/scalper.log"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - SCALPER - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler(LOG_FILE)])
logger = logging.getLogger("Scalper")

# === EXCHANGE ===
from dotenv import load_dotenv
load_dotenv("/home/sergio/denaro/.env")

api_key = os.getenv("BINANCE_API_KEY")
api_secret = os.getenv("BINANCE_API_SECRET")

ex = ccxt.binance({
    'apiKey': api_key,
    'secret': api_secret,
    'enableRateLimit': True,
    'options': {'defaultType': 'spot', 'defaultFeeCurrency': 'BNB'},
})

class MicroScalper:
    def __init__(self):
        self.positions = []  # {symbol, side, entry, amount, stop, target, trail_high}
        self.daily_pnl = 0.0
        self.last_check = 0
        
    def get_indicators(self, symbol, limit=50):
        ohlcv = ex.fetch_ohlcv(symbol, timeframe='1m', limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp','open','high','low','close','volume'])
        df['rsi'] = self.rsi(df['close'], 14)
        df['ema9'] = df['close'].ewm(span=9).mean()
        df['ema21'] = df['close'].ewm(span=21).mean()
        df['macd'] = df['close'].ewm(span=12).mean() - df['close'].ewm(span=26).mean()
        df['macd_signal'] = df['macd'].ewm(span=9).mean()
        return df
    
    def rsi(self, series, period):
        delta = series.diff()
        gain = delta.where(delta > 0, 0).rolling(period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
        rs = gain / loss.replace(0, np.nan)
        return 100 - (100 / (1 + rs))
    
    def check_signals(self, df):
        last = df.iloc[-1]
        prev = df.iloc[-2]
        signals = []
        
        rsi_buy = last['rsi'] < RSI_OVERSOLD and prev['rsi'] > last['rsi']
        rsi_sell = last['rsi'] > RSI_OVERBOUGHT and prev['rsi'] < last['rsi']
        ema_buy = prev['ema9'] <= prev['ema21'] and last['ema9'] > last['ema21']
        ema_sell = prev['ema9'] >= prev['ema21'] and last['ema9'] < last['ema21']
        macd_buy = prev['macd'] <= prev['macd_signal'] and last['macd'] > last['macd_signal']
        macd_sell = prev['macd'] >= prev['macd_signal'] and last['macd'] < last['macd_signal']
        
        if rsi_buy or (ema_buy and macd_buy):
            signals.append("BUY")
        if rsi_sell or (ema_sell and macd_sell):
            signals.append("SELL")
        
        return signals, last['close'], last['rsi']
    
    def execute(self):
        global ex
        try:
            # Reconnect if needed
            if not ex.check_required_credentials():
                ex = ccxt.binance({'apiKey': os.getenv("BINANCE_API_KEY"),
                                   'secret': os.getenv("BINANCE_API_SECRET"),
                                   'enableRateLimit': True,
                                   'options': {'defaultType': 'spot'}})
            
            balance = ex.fetch_balance()
            eur_free = balance['free'].get('EUR', 0)
            asset = SYMBOL.split('/')[0]
            asset_free = balance['free'].get(asset, 0)
            current_price = ex.fetch_ticker(SYMBOL)['last']
            
            logger.info(f"📊 {SYMBOL} @ {current_price:.2f}€ | EUR={eur_free:.2f} | {asset}={asset_free:.4f} | PnL={self.daily_pnl:.2f}€")
            
            # Daily loss limit
            if self.daily_pnl <= -MAX_DAILY_LOSS:
                logger.warning(f"🚫 Daily loss limit reached ({self.daily_pnl:.2f}€). Stopping.")
                return
            
            # Get signals
            df = self.get_indicators(SYMBOL)
            signals, price, rsi = self.check_signals(df)
            
            logger.info(f"  RSI={rsi:.1f} | Signals: {signals}")
            
            # Manage positions: check stop/target
            for pos in self.positions[:]:
                if pos['side'] == 'BUY':
                    # Update trailing
                    if price > pos['trail_high']:
                        pos['trail_high'] = price
                    if price >= pos['entry'] * (1 + TRAILING_ACTIVATION):
                        stop = pos['trail_high'] * (1 - TRAILING_DISTANCE)
                        pos['stop'] = max(pos['stop'], stop)
                    
                    # Check exit
                    if price >= pos['target'] or price <= pos['stop']:
                        try:
                            sell_amount = pos['amount']
                            order = ex.create_market_sell_order(SYMBOL, sell_amount)
                            pnl = (price - pos['entry']) * pos['amount']
                            self.daily_pnl += pnl
                            fee = price * pos['amount'] * 0.001
                            logger.info(f"💰 CLOSE BUY @ {price:.2f}€ | PnL: {pnl:.2f}€ (fee: {fee:.4f}€)")
                            self.positions.remove(pos)
                        except Exception as e:
                            logger.error(f"Close error: {e}")
                elif pos['side'] == 'SELL' and asset_free > 0:
                    if price <= pos['target'] or price >= pos['stop']:
                        try:
                            order = ex.create_market_buy_order(SYMBOL, pos['amount'])
                            pnl = (pos['entry'] - price) * pos['amount']
                            self.daily_pnl += pnl
                            logger.info(f"💰 CLOSE SELL @ {price:.2f}€ | PnL: {pnl:.2f}€")
                            self.positions.remove(pos)
                        except Exception as e:
                            logger.error(f"Close error: {e}")
            
            # New signals
            if len(self.positions) < MAX_POSITIONS and eur_free > POSITION_SIZE:
                if "BUY" in signals:
                    amount = POSITION_SIZE / price
                    try:
                        order = ex.create_market_buy_order(SYMBOL, round(amount, 5))
                        self.positions.append({
                            'side': 'BUY', 'entry': price, 'amount': round(amount, 5),
                            'stop': price * (1 - STOP_LOSS_PCT),
                            'target': price * (1 + TAKE_PROFIT_PCT),
                            'trail_high': price
                        })
                        logger.info(f"🚀 BUY {amount:.4f} @ {price:.2f}€ | Stop: {price*(1-STOP_LOSS_PCT):.2f} | Target: {price*(1+TAKE_PROFIT_PCT):.2f}")
                    except Exception as e:
                        logger.error(f"Buy error: {e}")
                
                elif "SELL" in signals and asset_free > (POSITION_SIZE / price * 0.5):
                    amount = min(asset_free, POSITION_SIZE / price)
                    try:
                        order = ex.create_market_sell_order(SYMBOL, round(amount, 5))
                        self.positions.append({
                            'side': 'SELL', 'entry': price, 'amount': round(amount, 5),
                            'stop': price * (1 + STOP_LOSS_PCT),
                            'target': price * (1 - TAKE_PROFIT_PCT),
                            'trail_low': price
                        })
                        logger.info(f"🚀 SELL {amount:.4f} @ {price:.2f}€")
                    except Exception as e:
                        logger.error(f"Sell error: {e}")
        
        except Exception as e:
            logger.error(f"Error: {e}")
            time.sleep(30)

if __name__ == "__main__":
    logger.info("=" * 50)
    logger.info("🟢 MICRO SCALPER AVVIATO")
    logger.info(f"   Pair: {SYMBOL} | Size: {POSITION_SIZE}€ | TP: {TAKE_PROFIT_PCT*100:.1f}% | SL: {STOP_LOSS_PCT*100:.1f}%")
    logger.info(f"   RSI: {RSI_OVERSOLD}/{RSI_OVERBOUGHT} | Max Loss: {MAX_DAILY_LOSS}€/day | Max Pos: {MAX_POSITIONS}")
    logger.info("=" * 50)
    
    bot = MicroScalper()
    while True:
        bot.execute()
        time.sleep(CHECK_INTERVAL)
