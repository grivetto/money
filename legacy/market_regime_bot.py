#!/usr/bin/env python3
"""
Market Regime Classifier - Classifies market into 4 regimes based on EMA-200 (trend) and ATR (volatility).
Communicates with Risk Manager to adjust exposure dynamically.
"""
import os, time, json, ccxt, logging
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - REGIME - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(Path(__file__).parent / 'regime.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('RegimeClassifier')

BASE_DIR = Path(__file__).parent
STATE_FILE = BASE_DIR / 'regime_state.json'
CHECK_INTERVAL = 900  # 15 minutes

SYMBOLS = ['SOL/EUR', 'ETH/EUR', 'BTC/EUR']

class RegimeClassifier:
    def __init__(self):
        self.client = ccxt.binance({
            'apiKey': os.getenv('BINANCE_API_KEY'),
            'secret': os.getenv('BINANCE_API_SECRET'),
            'enableRateLimit': True,
        })
        self.state = {'regime': 'UNKNOWN', 'multiplier': 1.0, 'timestamp': 0}
    
    def get_ema(self, symbol, period=200):
        ohlcv = self.client.fetch_ohlcv(symbol, timeframe='1h', limit=period+1)
        closes = [c[4] for c in ohlcv]
        multiplier = 2 / (period + 1)
        ema = closes[0]
        for price in closes[1:]:
            ema = (price - ema) * multiplier + ema
        return ema
    
    def get_atr(self, symbol, period=14):
        ohlcv = self.client.fetch_ohlcv(symbol, timeframe='1h', limit=period+1)
        trs = []
        for i in range(1, len(ohlcv)):
            high, low, prev_close = ohlcv[i][2], ohlcv[i][3], ohlcv[i-1][4]
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            trs.append(tr)
        return sum(trs) / len(trs) if trs else 0
    
    def classify(self, symbol='SOL/EUR'):
        try:
            ticker = self.client.fetch_ticker(symbol)
            current_price = ticker['last']
            ema200 = self.get_ema(symbol, 200)
            atr = self.get_atr(symbol, 14)
            
            # Determine trend direction
            trend_pct = (current_price / ema200 - 1) * 100 if ema200 else 0
            is_bull = trend_pct > 0
            
            # Determine volatility
            atr_pct = (atr / current_price) * 100 if current_price and atr else 0
            is_volatile = atr_pct > 1.5  # above 1.5% = volatile
            
            # Classify into 4 regimes
            if is_bull and not is_volatile:
                return 'BULL_QUIET', 1.5, trend_pct, atr_pct
            elif is_bull and is_volatile:
                return 'BULL_VOLATILE', 1.2, trend_pct, atr_pct
            elif not is_bull and not is_volatile:
                return 'BEAR_QUIET', 0.7, trend_pct, atr_pct
            else:
                return 'BEAR_VOLATILE', 0.4, trend_pct, atr_pct
        except Exception as e:
            logger.error(f'Classification error: {e}')
            return 'UNKNOWN', 1.0, 0, 0
    
    def save_state(self, regime, multiplier):
        state = {
            'regime': regime,
            'multiplier': multiplier,
            'timestamp': time.time(),
            'updated': time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())
        }
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)
        logger.info(f'Regime: {regime} | Multiplier: {multiplier}x')
    
    def run(self):
        logger.info('Market Regime Classifier started')
        while True:
            try:
                regime, multiplier, trend, atr = self.classify()
                self.save_state(regime, multiplier)
                logger.info(f'Trend: {trend:.2f}% | ATR: {atr:.2f}%')
            except Exception as e:
                logger.error(f'Run error: {e}')
            time.sleep(CHECK_INTERVAL)

if __name__ == '__main__':
    RegimeClassifier().run()
