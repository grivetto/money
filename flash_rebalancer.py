#!/usr/bin/env python3
"""
DENARO FLASH REBALANCER — Cross-Asset Arbitrage
Monitora SOL vs ETH. Se la divergenza > 4%, vende il meglio performante per comprare il peggiore.
Ribilanciamento automatico del portafoglio.
"""
import os, json, time, logging, hmac, hashlib, urllib.parse, requests
from datetime import datetime
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))
API_KEY = os.getenv('BINANCE_API_KEY')
API_SECRET = os.getenv('BINANCE_API_SECRET')
BINANCE = 'https://api.binance.com'
STATE_FILE = os.path.join(BASE_DIR, ".tmp/rebalancer_state.json")
LOG_FILE = os.path.join(BASE_DIR, "rebalancer.log")
os.makedirs(os.path.join(BASE_DIR, ".tmp"), exist_ok=True)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - REBAL - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()])
logger = logging.getLogger("Rebalancer")

# Config
PAIR_A = "SOLEUR"   # Asset principale
PAIR_B = "ETHEUR"   # Asset secondario
DIVERGENCE_THRESHOLD = 0.04   # 4% divergenza
MAX_PER_TRADE = 20.0          # EUR max per trade
CHECK_INTERVAL = 300          # ogni 5 minuti
PRICE_HISTORY_HOURS = 24      # guarda indietro 24h per calcolare performance

def sign(params):
    params['timestamp'] = int(time.time() * 1000)
    sig = hmac.new(API_SECRET.encode(), urllib.parse.urlencode(sorted(params.items())).encode(), hashlib.sha256).hexdigest()
    params['signature'] = sig
    return params

def fapi_get(endpoint, params=None):
    if params is None: params = {}
    # Futures API for funding rate (read-only)
    r = requests.get('https://fapi.binance.com' + endpoint, params=params, timeout=10)
    return r.json() if r.status_code == 200 else None

def api_get(endpoint, params=None, signed=True):
    if params is None: params = {}
    p = sign(params) if signed else params
    r = requests.get(BINANCE + endpoint, params=p, headers={'X-MBX-APIKEY': API_KEY} if signed else {}, timeout=10)
    return r.json() if r.status_code == 200 else None

def api_post(endpoint, params):
    p = sign(params)
    r = requests.post(BINANCE + endpoint, params=p, headers={'X-MBX-APIKEY': API_KEY}, timeout=10)
    return r.json() if r.status_code == 200 else None

def get_balance():
    ts = int(time.time() * 1000)
    bal = api_get('/api/v3/account', {'timestamp': ts, 'signature': sign({})['signature']})
    result = {}
    if bal:
        for b in bal.get('balances', []):
            free, locked = float(b['free']), float(b['locked'])
            if free + locked > 0: result[b['asset']] = {'free': free, 'locked': locked}
    return result

def get_prices():
    sol = api_get('/api/v3/ticker/price', {'symbol': 'SOLEUR'}, signed=False)
    eth = api_get('/api/v3/ticker/price', {'symbol': 'ETHEUR'}, signed=False)
    return float(sol['price']) if sol else None, float(eth['price']) if eth else None

def get_klines(symbol, hours=PRICE_HISTORY_HOURS):
    """Get closing prices for the last N hours."""
    k = api_get('/api/v3/klines', {'symbol': symbol, 'interval': '1h', 'limit': hours}, signed=False)
    return [float(x[4]) for x in k] if k else []

def load_state():
    try:
        with open(STATE_FILE) as f: return json.load(f)
    except: return {'last_rebalance': 0, 'total_rebalances': 0, 'total_profit': 0.0, 'log': []}

def save_state(s):
    with open(STATE_FILE, 'w') as f: json.dump(s, f, indent=2)

def main():
    logger.info("=" * 50)
    logger.info("🔄 FLASH REBALANCER STARTED")
    state = load_state()
    
    while True:
        try:
            now = time.time()
            sol_price, eth_price = get_prices()
            if not sol_price or not eth_price: time.sleep(30); continue
            
            # Get performance over last 24h
            sol_klines = get_klines('SOLEUR', PRICE_HISTORY_HOURS)
            eth_klines = get_klines('ETHEUR', PRICE_HISTORY_HOURS)
            
            if len(sol_klines) < 2 or len(eth_klines) < 2:
                time.sleep(30); continue
            
            sol_perf = (sol_price - sol_klines[0]) / sol_klines[0]
            eth_perf = (eth_price - eth_klines[0]) / eth_klines[0]
            divergence = abs(sol_perf - eth_perf)
            
            logger.info(f"SOL: {sol_perf:+.2f}% | ETH: {eth_perf:+.2f}% | Div: {divergence:.2f}%")
            
            # Check cooldown (max 1 rebalance every 4h)
            if now - state.get('last_rebalance', 0) < 14400:
                time.sleep(CHECK_INTERVAL); continue
            
            # Rebalance if divergence exceeds threshold
            if divergence > DIVERGENCE_THRESHOLD:
                bal = get_balance()
                eur_free = bal.get('EUR', {}).get('free', 0)
                sol_free = bal.get('SOL', {}).get('free', 0)
                sol_locked = bal.get('SOL', {}).get('locked', 0)
                eth_free = bal.get('ETH', {}).get('free', 0)
                
                amount = min(MAX_PER_TRADE, eur_free * 0.7)
                
                if sol_perf > eth_perf and amount >= 10:
                    # SOL outperformed → sell some SOL, buy ETH
                    sell_sol = amount / sol_price
                    sell_sol = int(sell_sol / 0.001) * 0.001
                    
                    if sell_sol > 0 and sol_free >= sell_sol:
                        sell = api_post('/api/v3/order', {
                            'symbol': 'SOLEUR', 'side': 'SELL', 'type': 'MARKET', 'quantity': f"{sell_sol:.3f}"
                        })
                        if sell and 'orderId' in sell:
                            time.sleep(1)
                            # Buy ETH with proceeds
                            buy_eth = amount * 0.95 / eth_price  # 5% reserve for fees
                            buy_eth = int(buy_eth / 0.00001) * 0.00001
                            buy = api_post('/api/v3/order', {
                                'symbol': 'ETHEUR', 'side': 'BUY', 'type': 'MARKET', 'quantity': f"{buy_eth:.5f}"
                            })
                            if buy and 'orderId' in buy:
                                state['last_rebalance'] = now
                                state['total_rebalances'] += 1
                                entry = f"Sold {sell_sol:.3f} SOL → Bought {buy_eth:.5f} ETH (div {divergence:.1f}%)"
                                state['log'].append({'time': datetime.now().isoformat(), 'action': entry})
                                logger.info(f"🔄 {entry}")
                                save_state(state)
                
                elif eth_perf > sol_perf and amount >= 10:
                    # ETH outperformed → but we have little ETH
                    if eth_free * eth_price > 10:
                        sell_eth = amount / eth_price
                        sell_eth = int(sell_eth / 0.00001) * 0.00001
                        sell = api_post('/api/v3/order', {
                            'symbol': 'ETHEUR', 'side': 'SELL', 'type': 'MARKET', 'quantity': f"{sell_eth:.5f}"
                        })
                        if sell and 'orderId' in sell:
                            time.sleep(1)
                            buy_sol = amount * 0.95 / sol_price
                            buy_sol = int(buy_sol / 0.001) * 0.001
                            buy = api_post('/api/v3/order', {
                                'symbol': 'SOLEUR', 'side': 'BUY', 'type': 'MARKET', 'quantity': f"{buy_sol:.3f}"
                            })
                            if buy and 'orderId' in buy:
                                state['last_rebalance'] = now
                                state['total_rebalances'] += 1
                                entry = f"Sold {sell_eth:.5f} ETH → Bought {buy_sol:.3f} SOL (div {divergence:.1f}%)"
                                state['log'].append({'time': datetime.now().isoformat(), 'action': entry})
                                logger.info(f"🔄 {entry}")
                                save_state(state)
                    else:
                        logger.info(f"ETH holding too small ({eth_free:.5f}) to rebalance, skip")
            
            time.sleep(CHECK_INTERVAL)
            
        except Exception as e:
            logger.error(f"Error: {e}")
            time.sleep(30)

if __name__ == '__main__':
    main()
