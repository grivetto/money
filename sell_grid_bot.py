#!/usr/bin/env python3
"""
DENARO SELL GRID BOT v1 - SOL Utilization Layer
Sells existing SOL at predefined profit levels above market.
Auto-replenishes when the main grid bot buys more SOL.
"""
import os, json, time, logging, hmac, hashlib, urllib.parse, requests, sys
from datetime import datetime
from dotenv import load_dotenv

# ── CONFIG ──────────────────────────────────────────
SELL_LEVELS_PCT = [0.006, 0.013, 0.021, 0.030]  # % above price
SELL_QTY = 0.159          # SOL per order
CHECK_INTERVAL = 30       # seconds between checks
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sell_grid.log")
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sell_grid_state.json")
TIMEOUT = 10              # HTTP request timeout

# ── SETUP ────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - SELL-GRID - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("SellGrid")

# ── BINANCE CLIENT ────────────────────────────────────
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(env_path)
API_KEY = os.getenv('BINANCE_API_KEY')
API_SECRET = os.getenv('BINANCE_API_SECRET')
BASE = 'https://api.binance.com'

logger.info(f"Loading .env from {env_path}")
logger.info(f"API_KEY loaded: {bool(API_KEY)}, API_SECRET loaded: {bool(API_SECRET)}")

def sign(params):
    ts = int(time.time() * 1000)
    params['timestamp'] = ts
    query = urllib.parse.urlencode(params)
    sig = hmac.new(API_SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()
    params['signature'] = sig
    return params

def binance_get(endpoint, params=None, signed=True):
    if params is None: params = {}
    p = sign(params) if signed else params.copy()
    try:
        r = requests.get(BASE + endpoint, params=p, headers={'X-MBX-APIKEY': API_KEY} if signed else {}, timeout=TIMEOUT)
        return r.json() if r.status_code == 200 else {'_error': r.status_code, '_msg': r.text[:200]}
    except Exception as e:
        return {'_error': 'exception', '_msg': str(e)}

def binance_post(endpoint, params):
    p = sign(params)
    try:
        r = requests.post(BASE + endpoint, params=p, headers={'X-MBX-APIKEY': API_KEY}, timeout=TIMEOUT)
        return r.json() if r.status_code == 200 else {'_error': r.status_code, '_msg': r.text[:200]}
    except Exception as e:
        return {'_error': 'exception', '_msg': str(e)}

# ── STATE MANAGEMENT ──────────────────────────────────
def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except:
            logger.warning("Could not load state file, creating new state")
            pass
    return {'levels': [], 'total_profit': 0.0}

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

# ── MAIN LOOP ─────────────────────────────────────────
def main():
    logger.info("=" * 50)
    logger.info("SELL GRID BOT STARTED")
    state = load_state()
    
    # Initialize levels if first run
    if not state['levels']:
        price = binance_get('/api/v3/ticker/price', {'symbol': 'SOLEUR'}, signed=False)
        if price and 'price' in price and '_error' not in price:
            cp = float(price['price'])
            for pct in SELL_LEVELS_PCT:
                level = {'pct': pct, 'price': round(cp * (1 + pct), 2), 'qty': SELL_QTY, 'order_id': None}
                state['levels'].append(level)
            logger.info(f"Initialized {len(state['levels'])} sell levels from price {cp}")
            save_state(state)
        else:
            logger.error(f"Failed to initialize: {price}")
    
    errors = 0
    while True:
        try:
            tick = time.time()
            logger.info("DEBUG: loop iteration start")
            sys.stdout.flush()
            sys.stderr.flush()
            
            # 1. Get current price
            price_data = binance_get('/api/v3/ticker/price', {'symbol': 'SOLEUR'}, signed=False)
            if not price_data or '_error' in price_data:
                logger.warning(f"Failed to fetch price: {price_data}")
                time.sleep(CHECK_INTERVAL)
                errors += 1
                if errors > 5:
                    logger.error("Too many errors, waiting 60s")
                    time.sleep(60)
                    errors = 0
                continue
            current_price = float(price_data['price'])
            
            # 2. Get open orders
            open_orders = binance_get('/api/v3/openOrders')
            if not open_orders or '_error' in open_orders:
                logger.warning(f"Failed to fetch open orders: {open_orders}")
                time.sleep(CHECK_INTERVAL)
                continue
            
            # Build set of active order IDs
            active_order_ids = set()
            active_sell_prices = {}
            for o in open_orders:
                if o.get('side') == 'SELL' and o.get('symbol') == 'SOLEUR':
                    active_order_ids.add(o['orderId'])
                    active_sell_prices[o['orderId']] = float(o.get('price', 0))
            
            # 3. Get SOL balance
            account = binance_get('/api/v3/account')
            sol_free = 0.0
            if account and '_error' not in account:
                for b in account['balances']:
                    if b['asset'] == 'SOL':
                        sol_free = float(b.get('free', 0))
                        break
            else:
                logger.warning(f"Failed to fetch account: {account}")
                time.sleep(CHECK_INTERVAL)
                continue
            
            # 4. Check each level
            for level in state['levels']:
                oid = level.get('order_id')
                if oid and oid not in active_order_ids:
                    # Order was filled or cancelled
                    price_filled = active_sell_prices.get(oid, level['price'])
                    profit_eur = level['qty'] * price_filled * (level['pct'])
                    state['total_profit'] += profit_eur
                    pct_str = f"{level['pct']*100:.1f}%"
                    logger.info(f"💰 SELL FILLED @ {price_filled}€ ({pct_str}) | Profit: {profit_eur:.2f}€ | Total: {state['total_profit']:.2f}€")
                    level['order_id'] = None
                    save_state(state)
                
                # Check if we can place/replace this level
                if level.get('order_id') is None and sol_free >= level['qty'] * 0.95:
                    sp = round(level['price'], 2)
                    qty_str = f"{level['qty']:.3f}"
                    result = binance_post('/api/v3/order', {
                        'symbol': 'SOLEUR',
                        'side': 'SELL',
                        'type': 'LIMIT',
                        'timeInForce': 'GTC',
                        'quantity': qty_str,
                        'price': str(sp)
                    })
                    if '_error' not in result:
                        level['order_id'] = result['orderId']
                        pct_str = f"{level['pct']*100:.1f}%"
                        logger.info(f"🟢 SELL PLACED: {level['qty']} SOL @ {sp}€ ({pct_str}) | ID: {result['orderId']}")
                        sol_free -= level['qty']
                    else:
                        logger.error(f"Failed to place sell @ {sp}: {result.get('_msg','')}")
                    save_state(state)
            
            # 5. Log status periodically
            active_count = sum(1 for l in state['levels'] if l.get('order_id') is not None)
            missing_count = sum(1 for l in state['levels'] if l.get('order_id') is None)
            if missing_count > 0:
                logger.info(f"Status: {active_count} active, {missing_count} waiting, SOL free={sol_free:.4f}, total_profit={state['total_profit']:.2f}€")
            
            errors = 0
            elapsed = time.time() - tick
            sleep_time = max(1, CHECK_INTERVAL - elapsed)
            time.sleep(sleep_time)
            
        except KeyboardInterrupt:
            logger.info("Sell grid bot stopped by user")
            break
        except Exception as e:
            logger.error(f"Unhandled error: {e}")
            time.sleep(CHECK_INTERVAL)

if __name__ == '__main__':
    main()
