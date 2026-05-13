#!/usr/bin/env python3
"""
DENARO ADA GRID — Grid trading semplificato per ADA/EUR
Piazza ordini limite su griglia, cattura micro-profitti.
Capitale: 25€, 4 livelli, spread 2%.
"""
import os, sys, json, time, logging, hmac, hashlib, urllib.parse, requests
from datetime import datetime
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))
API_KEY = os.getenv('BINANCE_API_KEY')
API_SECRET = os.getenv('BINANCE_API_SECRET')
BINANCE = 'https://api.binance.com'
STATE_FILE = os.path.join(BASE_DIR, "ada_grid_state.json")
LOG_FILE = os.path.join(BASE_DIR, "ada_grid.log")

handler = logging.FileHandler(LOG_FILE)
handler.setFormatter(logging.Formatter('%(asctime)s - ADA-GRID - %(levelname)s - %(message)s'))
logger = logging.getLogger("AdaGrid")
logger.setLevel(logging.INFO)
logger.addHandler(handler)
logger.propagate = False

SYMBOL = "ADAEUR"
MAX_CAPITAL = 25.0
GRID_LEVELS = 4
GRID_SPACING = 0.018  # 1.8% tra un livello e l'altro
PROFIT_PER_GRID = 0.006  # 0.6% profitto per scambio
CHECK_INTERVAL = 30
MIN_ORDER_EUR = 5.0
MAX_ORDERS_PER_SIDE = 3

def sign(params):
    ts = int(time.time() * 1000)
    params['timestamp'] = ts
    query = urllib.parse.urlencode(params)
    sig = hmac.new(API_SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()
    params['signature'] = sig
    return params

def api_get(endpoint, params=None, signed=True):
    if params is None: params = {}
    p = sign(params) if signed else params
    r = requests.get(BINANCE + endpoint, params=p, headers={'X-MBX-APIKEY': API_KEY} if signed else {}, timeout=10)
    return r.json() if r.status_code == 200 else None

def api_post(endpoint, params):
    p = sign(params)
    r = requests.post(BINANCE + endpoint, params=p, headers={'X-MBX-APIKEY': API_KEY}, timeout=10)
    return r.json() if r.status_code == 200 else None

def api_delete(endpoint, params):
    p = sign(params)
    r = requests.delete(BINANCE + endpoint, params=p, headers={'X-MBX-APIKEY': API_KEY}, timeout=10)
    return r.json() if r.status_code == 200 else None

def get_price():
    r = api_get('/api/v3/ticker/price', {'symbol': SYMBOL}, signed=False)
    return float(r['price']) if r and 'price' in r else None

def get_step_size():
    info = api_get('/api/v3/exchangeInfo', {'symbol': SYMBOL}, signed=False)
    if not info or not info.get('symbols'): return 0.1, 0.01
    step = 0.1
    min_not = 5.0
    for f in info['symbols'][0]['filters']:
        if f['filterType'] == 'LOT_SIZE':
            step = float(f['stepSize'])
        if f['filterType'] == 'MIN_NOTIONAL':
            min_not = float(f['minNotional'])
    return step, min_not

def round_qty(qty, step):
    precision = max(0, len(str(step).split('.')[-1]) if '.' in str(step) else 0)
    return int(qty / step) * step

def get_open_orders():
    r = api_get('/api/v3/openOrders', {'symbol': SYMBOL})
    return r if isinstance(r, list) else []

def cancel_order(order_id):
    return api_delete('/api/v3/order', {'symbol': SYMBOL, 'orderId': order_id})

def place_limit_order(side, qty, price):
    return api_post('/api/v3/order', {
        'symbol': SYMBOL, 'side': side, 'type': 'LIMIT_MAKER',
        'quantity': qty, 'price': price
    })

def load_state():
    try:
        with open(STATE_FILE) as f: return json.load(f)
    except: return {'grid_price': None, 'active_sells': {}, 'active_buys': {}, 'total_profit': 0.0, 'trades': 0}

def save_state(s):
    with open(STATE_FILE, 'w') as f: json.dump(s, f, indent=2)

def main():
    state = load_state()
    price = get_price()
    if not price:
        logger.warning("Impossibile ottenere prezzo ADA")
        time.sleep(10)
        return
    
    step, min_not = get_step_size()
    
    # Get existing open orders
    open_orders = get_open_orders()
    if open_orders is None:
        logger.warning("Impossibile ottenere ordini aperti")
        time.sleep(10)
        return
    
    # Separate into buys and sells
    existing_buys = {str(o['orderId']): o for o in open_orders if o['side'] == 'BUY'}
    existing_sells = {str(o['orderId']): o for o in open_orders if o['side'] == 'SELL'}
    
    # Get balance
    bal = api_get('/api/v3/account')
    if not bal:
        time.sleep(10)
        return
    try:
        eur_free = float([b for b in bal['balances'] if b['asset'] == 'EUR'][0]['free'])
        ada_free = float([b for b in bal['balances'] if b['asset'] == 'ADA'][0]['free'])
    except:
        time.sleep(10)
        return
    
    # Calculate grid price — re-center if price moved more than 5% from last grid
    grid_price = state.get('grid_price')
    if not grid_price or abs(price - grid_price) / grid_price > 0.05:
        logger.info(f"Ricentro griglia: prezzo={price:.4f}€ grid_prec={grid_price}")
        # Cancel all existing orders
        for oid in list(existing_buys.keys()) + list(existing_sells.keys()):
            cancel_order(oid)
        existing_buys = {}
        existing_sells = {}
        grid_price = price
        state['grid_price'] = grid_price
        state['active_buys'] = {}
        state['active_sells'] = {}
    
    # Calculate grid levels
    investment_per_level = min(MAX_CAPITAL / GRID_LEVELS, eur_free / 2 if eur_free > 0 else MAX_CAPITAL / GRID_LEVELS)
    
    buy_levels = []
    for i in range(1, GRID_LEVELS + 1):
        buy_price = grid_price * (1 - i * GRID_SPACING)
        buy_levels.append(buy_price)
    
    sell_levels = []
    for i in range(1, GRID_LEVELS + 1):
        sell_price = grid_price * (1 + i * GRID_SPACING)
        sell_levels.append(sell_price)
    
    # Place buy orders (if not already placed)
    buys_placed = 0
    for buy_price in buy_levels:
        if buys_placed >= MAX_ORDERS_PER_SIDE:
            break
        if investment_per_level < MIN_ORDER_EUR:
            logger.info(f"Investimento per livello ({investment_per_level:.2f}€) sotto minimo, salto")
            break
        
        # Check if buy order already exists at this price level
        already_placed = False
        for oid, o in existing_buys.items():
            existing_price = float(o['price'])
            if abs(existing_price - buy_price) / buy_price < 0.01:  # Within 1%
                already_placed = True
                break
        
        if already_placed:
            continue
        
        # Round qty to LOT_SIZE
        qty_raw = investment_per_level / buy_price
        qty = round_qty(qty_raw, step)
        qty_str = f"{qty:.{len(str(step).split('.')[-1]) if '.' in str(step) else 1}f}"
        # Round price to tickSize (PRICE_FILTER)
        tick = 0.0001
        price_rounded = int(buy_price / tick) * tick
        price_str = f"{price_rounded:.{len(str(tick).split('.')[-1]) if '.' in str(tick) else 4}f}"
        
        result = place_limit_order('BUY', qty_str, price_str)
        if result and 'orderId' in result:
            logger.info(f"BUY LIMIT {qty:.4f} ADA @ {buy_price:.4f}€ ({qty*buy_price:.2f}€)")
            buys_placed += 1
        elif result:
            logger.warning(f"Buy fallito: {result.get('msg', '?')}")
        else:
            logger.warning(f"Buy ORDER FALLITO (API error) qty={qty_str} price={price_str}")
    
    # Place sell orders (if we have ADA to sell)
    sells_placed = 0
    if ada_free > 0:
        for sell_price in sell_levels:
            if sells_placed >= MAX_ORDERS_PER_SIDE:
                break
            
            already_placed = False
            for oid, o in existing_sells.items():
                existing_price = float(o['price'])
                if abs(existing_price - sell_price) / sell_price < 0.01:
                    already_placed = True
                    break
            
            if already_placed:
                continue
            
            # Calculate how much ADA to sell per level
            ada_per_level = ada_free / min(len(sell_levels), MAX_ORDERS_PER_SIDE)
            qty = round_qty(ada_per_level, step)
            if qty * sell_price < MIN_ORDER_EUR:
                continue
            
            qty_str = f"{qty:.{len(str(step).split('.')[-1]) if '.' in str(step) else 1}f}"
            tick = 0.0001
            price_rounded = int(sell_price / tick) * tick
            price_str = f"{price_rounded:.{len(str(tick).split('.')[-1]) if '.' in str(tick) else 4}f}"
            
            result = place_limit_order('SELL', qty_str, price_str)
            if result and 'orderId' in result:
                logger.info(f"SELL LIMIT {qty:.4f} ADA @ {sell_price:.4f}€ ({qty*sell_price:.2f}€)")
                sells_placed += 1
            elif result:
                logger.warning(f"Sell fallito: {result.get('msg', '?')}")
            else:
                logger.warning(f"Sell ORDER FALLITO (API error) qty={qty_str} price={price_str}")
    
    # Check for filled orders
    for oid, o in existing_buys.items():
        if o['status'] == 'FILLED':
            qty = float(o['executedQty'])
            cost = float(o['cummulativeQuoteQty'])
            logger.info(f"BUY FILLED: {qty:.4f} ADA @ {cost/qty:.4f}€ (costo {cost:.2f}€)")
    
    for oid, o in existing_sells.items():
        if o['status'] == 'FILLED':
            qty = float(o['executedQty'])
            revenue = float(o['cummulativeQuoteQty'])
            profit = revenue - (qty * grid_price * 0.98)  # Approx cost
            state['total_profit'] += profit
            state['trades'] += 1
            logger.info(f"SELL FILLED: {qty:.4f} ADA @ {revenue/qty:.4f}€, profit {profit:.2f}€ | Tot: {state['total_profit']:.2f}€")
    
    logger.info(f"ADA @ {price:.4f}€ | Buy: {buys_placed} new/{len(existing_buys)} active | Sell: {sells_placed} new/{len(existing_sells)} active | EUR={eur_free:.2f} ADA={ada_free:.4f} | Profit={state['total_profit']:.2f}€")
    save_state(state)

if __name__ == '__main__':
    logger.info("=" * 40)
    logger.info("ADA GRID AVVIATO — 25€ capitale")
    while True:
        try:
            main()
        except Exception as e:
            logger.error(f"Errore: {e}")
        time.sleep(CHECK_INTERVAL)
