#!/usr/bin/env python3
"""
DENARO SCALPER v2 — Configurable tactical scalper
Usage: python3 scalper_v2.py <symbol> <invest_eur> <logfile>
Example: python3 scalper_v2.py ETH/EUR 12.0 /home/sergio/denaro/eth_scalper.log
"""
import os, sys, json, time, logging, ccxt, pandas as pd
import numpy as np
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__) or ".", ".env"))

SYMBOL = sys.argv[1] if len(sys.argv) > 1 else "ETH/EUR"
POSITION_SIZE = float(sys.argv[2]) if len(sys.argv) > 2 else 12.0
LOG_FILE = sys.argv[3] if len(sys.argv) > 3 else f"/home/{os.getenv('USER','sergio')}/denaro/{SYMBOL.split('/')[0]}_scalper.log"
MAX_POSITIONS = 2
TAKE_PROFIT_PCT = 0.005
STOP_LOSS_PCT = 0.008
MAX_DAILY_LOSS = 5.0
RSI_OVERSOLD = 35
RSI_OVERBOUGHT = 65
CHECK_INTERVAL = 45

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler(LOG_FILE)])
logger = logging.getLogger(f"Scalper.{SYMBOL.split('/')[0]}")

ex = ccxt.binance({
    'apiKey': os.getenv("BINANCE_API_KEY"),
    'secret': os.getenv("BINANCE_API_SECRET"),
    'enableRateLimit': True,
    'options': {'defaultType': 'spot', 'defaultFeeCurrency': 'BNB'},
})

class Scalper:
    def __init__(self):
        self.positions = []
        self.daily_pnl = 0.0
        
    def indicators(self, limit=50):
        ohlcv = ex.fetch_ohlcv(SYMBOL, timeframe='1m', limit=limit)
        df = pd.DataFrame(ohlcv, columns=['t','o','h','l','c','v'])
        delta = df['c'].diff()
        gain = delta.where(delta>0,0).rolling(14).mean()
        loss = (-delta.where(delta<0,0)).rolling(14).mean()
        rs = gain / loss.replace(0, np.nan)
        df['rsi'] = 100 - (100/(1+rs))
        df['ema9'] = df['c'].ewm(span=9).mean()
        df['ema21'] = df['c'].ewm(span=21).mean()
        macd = df['c'].ewm(span=12).mean() - df['c'].ewm(span=26).mean()
        df['macd_s'] = macd.ewm(span=9).mean()
        df['macd'] = macd
        return df
    
    def run(self):
        logger.info(f"🚀 AVVIATO {SYMBOL} size={POSITION_SIZE}€ TP={TAKE_PROFIT_PCT*100:.1f}% SL={STOP_LOSS_PCT*100:.1f}%")
        while True:
            try:
                bal = ex.fetch_balance()
                eur = bal['free'].get('EUR',0)
                asset = SYMBOL.split('/')[0]
                have = bal['free'].get(asset,0)
                ticker = ex.fetch_ticker(SYMBOL)
                price = ticker['last']
                
                df = self.indicators()
                last = df.iloc[-1]; prev = df.iloc[-2]
                rsi = last.get('rsi',50)
                
                sig_buy = rsi < RSI_OVERSOLD or (prev['ema9']<=prev['ema21'] and last['ema9']>last['ema21'])
                sig_sell = rsi > RSI_OVERBOUGHT or (prev['ema9']>=prev['ema21'] and last['ema9']<last['ema21'])
                
                logger.info(f"📊 {SYMBOL} @ {price:.2f}€ RSI={rsi:.1f} EUR={eur:.2f} {asset}={have:.4f} PnL={self.daily_pnl:.2f}")
                
                # Manage open positions
                for pos in self.positions[:]:
                    pnl = (price - pos['entry']) * pos['amount']
                    exit_signal = price <= pos['stop'] or price >= pos['target']
                    if pos['side'] == 'SELL':
                        pnl = (pos['entry'] - price) * pos['amount']
                    
                    if exit_signal:
                        try:
                            side_func = ex.create_market_sell_order if pos['side'] == 'BUY' else ex.create_market_buy_order
                            side_func(SYMBOL, pos['amount'])
                            self.daily_pnl += pnl
                            logger.info(f"💰 CLOSE {pos['side']} @ {price:.2f} | PnL: {pnl:.2f}€")
                            self.positions.remove(pos)
                        except Exception as e:
                            logger.error(f"Close err: {e}")
                
                # New positions
                if len(self.positions) < MAX_POSITIONS:
                    if sig_buy and eur > POSITION_SIZE:
                        amt = POSITION_SIZE / price
                        order = ex.create_market_buy_order(SYMBOL, round(amt,5))
                        self.positions.append({'side':'BUY','entry':price,'amount':round(amt,5),
                            'stop':price*(1-STOP_LOSS_PCT),'target':price*(1+TAKE_PROFIT_PCT)})
                        logger.info(f"🚀 BUY {amt:.4f} @ {price:.2f} SL={price*(1-STOP_LOSS_PCT):.2f} TP={price*(1+TAKE_PROFIT_PCT):.2f}")
                    
                    elif sig_sell and have > (POSITION_SIZE/price*0.3):
                        amt = min(have, POSITION_SIZE/price)
                        order = ex.create_market_sell_order(SYMBOL, round(amt,5))
                        self.positions.append({'side':'SELL','entry':price,'amount':round(amt,5),
                            'stop':price*(1+STOP_LOSS_PCT),'target':price*(1-TAKE_PROFIT_PCT)})
                        logger.info(f"🚀 SELL {amt:.4f} @ {price:.2f}")
                
                if self.daily_pnl <= -MAX_DAILY_LOSS:
                    logger.warning(f"🚫 Daily loss limit! STOP")
                    break
                    
            except Exception as e:
                logger.error(f"Error: {e}")
                time.sleep(30)
            
            time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    Scalper().run()
