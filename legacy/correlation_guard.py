#!/usr/bin/env python3
"""
Correlation Guard - Monitors correlation between SOL, ETH, BTC.
If correlation exceeds 0.85, signals Risk Manager to reduce exposure.
Essential for small capital protection against systemic crashes.
"""
import os, time, json, ccxt, logging
from dotenv import load_dotenv
from pathlib import Path
import numpy as np

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - CORR - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(Path(__file__).parent / 'correlation.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('CorrelationGuard')

BASE_DIR = Path(__file__).parent
STATE_FILE = BASE_DIR / 'correlation_state.json'
CHECK_INTERVAL = 3600  # 1 hour

PAIRS = ['SOL/EUR', 'ETH/EUR', 'BTC/EUR']
THRESHOLD = 0.85

class CorrelationGuard:
    def __init__(self):
        self.client = ccxt.binance({
            'enableRateLimit': True,
        })
        self.state = {'correlation': 0, 'reduction': 1.0, 'timestamp': 0}
    
    def get_returns(self, symbol, limit=24):
        ohlcv = self.client.fetch_ohlcv(symbol, timeframe='1h', limit=limit+1)
        closes = [c[4] for c in ohlcv]
        returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes))]
        return returns
    
    def calculate(self):
        try:
            returns = {}
            for pair in PAIRS:
                returns[pair] = self.get_returns(pair, 24)
            
            if any(len(r) < 20 for r in returns.values()):
                logger.warning('Insufficient data for correlation')
                return 0, 1.0
            
            # Calculate correlation matrix
            r_sol = np.array(returns['SOL/EUR'])
            r_eth = np.array(returns['ETH/EUR'])
            r_btc = np.array(returns['BTC/EUR'])
            
            corr_sol_eth = np.corrcoef(r_sol, r_eth)[0, 1]
            corr_sol_btc = np.corrcoef(r_sol, r_btc)[0, 1]
            corr_eth_btc = np.corrcoef(r_eth, r_btc)[0, 1]
            
            max_corr = max(abs(corr_sol_eth), abs(corr_sol_btc), abs(corr_eth_btc))
            
            # Determine exposure reduction
            if max_corr > 0.95:
                reduction = 0.3
            elif max_corr > 0.90:
                reduction = 0.5
            elif max_corr > THRESHOLD:
                reduction = 0.7
            else:
                reduction = 1.0
            
            logger.info(f'Corr SOL-ETH: {corr_sol_eth:.3f} | SOL-BTC: {corr_sol_btc:.3f} | ETH-BTC: {corr_eth_btc:.3f}')
            logger.info(f'Max correlation: {max_corr:.3f} | Reduction: {reduction:.1f}x')
            
            return max_corr, reduction
            
        except Exception as e:
            logger.error(f'Correlation error: {e}')
            return 0, 1.0
    
    def save_state(self, corr, reduction):
        state = {
            'correlation': round(corr, 3),
            'reduction': reduction,
            'timestamp': time.time(),
            'updated': time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime()),
            'threshold': THRESHOLD,
            'active': bool(corr > THRESHOLD)
        }
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)
    
    def run(self):
        logger.info('Correlation Guard started')
        while True:
            try:
                corr, reduction = self.calculate()
                self.save_state(corr, reduction)
            except Exception as e:
                logger.error(f'Run error: {e}')
            time.sleep(CHECK_INTERVAL)

if __name__ == '__main__':
    CorrelationGuard().run()
