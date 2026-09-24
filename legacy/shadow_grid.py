#!/usr/bin/env python3
"""
DENARO SHADOW GRID — Crash Recovery Bot
Piazza ordini di acquisto a livelli estremi (-8%, -12%, -18%).
Si attiva solo durante crolli improvvisi del mercato.
Usa capitale "di riserva" dal DCA e dal buffer.
"""
import os, json, time, logging, hmac, hashlib, urllib.parse, requests
from datetime import datetime
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))
API_KEY = os.getenv('BINANCE_API_KEY')
API_SECRET = os.getenv('BINANCE_API_SECRET')
BINANCE = 'https://api.binance.com'
STATE_FILE = os.path.join(BASE_DIR, ".tmp/shadow_grid_state.json")
LOG_FILE = os.path.join(BASE_DIR, "shadow_grid.log")
os.makedirs(os.path.join(BASE_DIR, ".tmp"), exist_ok=True)

handler = logging.FileHandler(LOG_FILE)
handler.setFormatter(logging.Formatter('%(asctime)s - SHADOW - %(levelname)s - %(message)s'))
logger = logging.getLogger("ShadowGrid")
logger.setLevel(logging.INFO)
logger.addHandler(handler)
logger.propagate = False

SYMBOL = "SOLEUR"
SHADOW_LEVELS = [0.03, 0.08]       # Solo -3% e -8%
SHADOW_EUR = [15.0, 15.0]          # 30€ totali riserva (il resto lavora)
CHECK_INTERVAL = 60
RECOVER_TARGET = 0.04                 # Sell at +4% above buy price after recovery

def sign(params):
    params['timestamp'] = int(time.time() * 1000)
    sig = hmac.new(API_SECRET.encode(), urllib.parse.urlencode(sorted(params.items())).encode(), hashlib.sha256).hexdigest()
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

def get_price():
    d = api_get('/api/v3/ticker/price', {'symbol': SYMBOL}, signed=False)
    return float(d['price']) if d and 'price' in d else None

def get_eur_free():
    bal = api_get('/api/v3/account', {})
    if bal:
        for b in bal.get('balances', []):
            if b['asset'] == 'EUR': return float(b['free'])
    return 0

def load_state():
    try:
        with open(STATE_FILE) as f: return json.load(f)
    except: return {'active': False, 'levels': [], 'total_invested': 0, 'total_profit': 0}

def save_state(s):
    with open(STATE_FILE, 'w') as f: json.dump(s, f, indent=2)

def main():
    logger.info("=" * 50)
    logger.info("🌑 SHADOW GRID STARTED")
    state = load_state()
    
    while True:
        try:
            price = get_price()
            if not price: time.sleep(CHECK_INTERVAL); continue
            
            eur_free = get_eur_free()
            
            # If shadow grid is active, check for sell signals
            if state.get('active'):
                updated = False
                for lvl in state['levels']:
                    if lvl.get('filled') and not lvl.get('sold'):
                        # Check if price recovered enough to sell with profit
                        buy_price = lvl['buy_price']
                        if price >= buy_price * (1 + RECOVER_TARGET):
                            qty = f"{lvl['qty']:.3f}"
                            order = api_post('/api/v3/order', {
                                'symbol': SYMBOL, 'side': 'SELL', 'type': 'LIMIT',
                                'timeInForce': 'GTC',
                                'quantity': qty,
                                'price': f"{buy_price * (1 + RECOVER_TARGET):.2f}"
                            })
                            if order and 'orderId' in order:
                                profit = lvl['invested'] * RECOVER_TARGET
                                lvl['sell_price'] = round(buy_price * (1 + RECOVER_TARGET), 2)
                                lvl['sell_id'] = order['orderId']
                                lvl['sold'] = True
                                state['total_profit'] += profit
                                logger.info(f"💰 RECOVERY SELL: {qty} SOL @ {buy_price*(1+RECOVER_TARGET):.2f}€ (+{RECOVER_TARGET*100}%) profit {profit:.2f}€")
                                updated = True
                
                # Check if all levels are sold → shadow grid done
                all_done = all(l.get('sold') or not l.get('filled') for l in state['levels'])
                if all_done and all(l.get('sold') for l in state['levels']):
                    state['active'] = False
                    logger.info(f"✅ SHADOW GRID COMPLETE — Profit: {state['total_profit']:.2f}€")
                    state['levels'] = []
                
                if updated:
                    save_state(state)
            
            # Check if shadow grid should activate: price drop > 7% in short time
            else:
                # Get price 1h ago from klines
                klines = api_get('/api/v3/klines', {'symbol': SYMBOL, 'interval': '1h', 'limit': 2}, signed=False)
                if klines and len(klines) >= 2:
                    prev_close = float(klines[-2][4])
                    drop_pct = (prev_close - price) / prev_close
                    
                    if drop_pct > 0.07:  # 7% drop in 1h = crash signal
                        logger.info(f"⚡ CRASH DETECTED! Drop: {drop_pct*100:.1f}% in 1h")
                        
                        # Reserve capital: use buffer + DCA funds
                        reserve = min(30.0, eur_free * 0.5)
                        if reserve < 5:
                            logger.info(f"Reserve insufficient ({reserve:.2f}€), skip")
                            time.sleep(CHECK_INTERVAL); continue
                        
                        # Place shadow buy orders
                        levels = []
                        total_invested = 0
                        for i, (pct, amount) in enumerate(zip(SHADOW_LEVELS, SHADOW_EUR)):
                            buy_price = round(price * (1 - pct), 2)
                            qty = amount / buy_price
                            qty_rounded = int(qty / 0.001) * 0.001
                            
                            if total_invested + amount > reserve:
                                break
                            
                            order = api_post('/api/v3/order', {
                                'symbol': SYMBOL, 'side': 'BUY', 'type': 'LIMIT',
                                'timeInForce': 'GTC',
                                'quantity': f"{qty_rounded:.3f}",
                                'price': f"{buy_price:.2f}"
                            })
                            if order and 'orderId' in order:
                                levels.append({
                                    'level': i, 'buy_price': buy_price, 'qty': qty_rounded,
                                    'invested': round(qty_rounded * buy_price, 2),
                                    'order_id': order['orderId'],
                                    'filled': False, 'sold': False,
                                    'sell_price': 0, 'sell_id': 0
                                })
                                total_invested += qty_rounded * buy_price
                                logger.info(f"  🛡️ SHADOW BUY @ {buy_price}€ ({qty_rounded} SOL, {amount}€)")
                        
                        if levels:
                            state['active'] = True
                            state['levels'] = levels
                            state['total_invested'] = round(total_invested, 2)
                            save_state(state)
                            logger.info(f"Shadow grid activated: {len(levels)} levels, {total_invested:.2f}€ deployed")
            
            # Monitor for filled shadow orders (check if they exist in open orders)
            if state.get('active'):
                open_orders = api_get('/api/v3/openOrders', {'symbol': SYMBOL})
                open_ids = {o['orderId'] for o in open_orders} if open_orders else set()
                
                for lvl in state['levels']:
                    if lvl.get('order_id') and not lvl.get('filled'):
                        if lvl['order_id'] not in open_ids:
                            lvl['filled'] = True
                            fill_price = lvl['buy_price']
                            logger.info(f"  ✅ SHADOW FILLED: {lvl['qty']} SOL @ {fill_price}€")
                            # Place recovery sell order
                            sell_qty = f"{lvl['qty']:.3f}"
                            sell_price = round(fill_price * (1 + RECOVER_TARGET), 2)
                            sell_order = api_post('/api/v3/order', {
                                'symbol': SYMBOL, 'side': 'SELL', 'type': 'LIMIT',
                                'timeInForce': 'GTC', 'quantity': sell_qty, 'price': f"{sell_price:.2f}"
                            })
                            if sell_order and 'orderId' in sell_order:
                                lvl['sell_price'] = sell_price
                                lvl['sell_id'] = sell_order['orderId']
                                lvl['sold'] = True
                                profit = lvl['invested'] * RECOVER_TARGET
                                state['total_profit'] += profit
                                logger.info(f"  🎯 RECOVERY SELL placed @ {sell_price}€ (+{RECOVER_TARGET*100}%)")
                
                save_state(state)
            
            # Log status
            status = "🌑 ACTIVE" if state.get('active') else "💤 STANDBY"
            logger.info(f"{status} | Price: {price:.2f}€ | EUR free: {eur_free:.2f}€ | Profit: {state.get('total_profit',0):.2f}€")
            
        except Exception as e:
            logger.error(f"Error: {e}")
        
        time.sleep(CHECK_INTERVAL)

if __name__ == '__main__':
    main()
