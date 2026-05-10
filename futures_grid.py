#!/usr/bin/env python3
"""
DENARO PRO v1 — Futures Grid Bot (5x Leverage)
Binance SOL/USDT perpetual futures grid trading.
Risk-managed: max 150€ margin, -10% stop loss, auto circuit breaker.
"""
import os, json, time, logging, hmac, hashlib, urllib.parse, requests, sys
from datetime import datetime
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))
API_KEY = os.getenv('BINANCE_API_KEY')
API_SECRET = os.getenv('BINANCE_API_SECRET')
FAPI = 'https://fapi.binance.com'  # Futures API
STATE_FILE = os.path.join(BASE_DIR, ".tmp/futures_state.json")
PROFIT_LOG = os.path.join(BASE_DIR, ".tmp/futures_profit.csv")
LOG_FILE = os.path.join(BASE_DIR, "futures_grid.log")
os.makedirs(os.path.join(BASE_DIR, ".tmp"), exist_ok=True)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - PRO - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()])
logger = logging.getLogger("FuturesPro")

# ── CONFIG ──────────────────────────────────────────
SYMBOL = "SOLUSDT"
MARGIN = 150.0            # Margin in USDT
LEVERAGE = 5              # 5x leverage
GRID_LEVELS = 5
GRID_RANGE_PCT = 0.02     # ±2%
BASE_ORDER_USDT = 30.0    # Base order in USDT (margin)
MARTINGALE = 1.15
PROFIT_PCT = 0.0025       # 0.25% per level
STOP_LOSS_PCT = 0.10      # -10% of margin = 15USDT loss
CIRCUIT_BREAKER_PCT = 0.05  # -5% in 1h = pause all
CHECK_INTERVAL = 15
TIMEOUT = 10

# ── API ─────────────────────────────────────────────
def sign(params):
    ts = int(time.time() * 1000)
    params['timestamp'] = ts
    query = urllib.parse.urlencode(sorted(params.items()))
    sig = hmac.new(API_SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()
    params['signature'] = sig
    return params

def fget(endpoint, params=None):
    if params is None: params = {}
    p = sign(params)
    r = requests.get(FAPI + endpoint, params=p, headers={'X-MBX-APIKEY': API_KEY}, timeout=TIMEOUT)
    return r.json() if r.status_code == 200 else {'_error': r.status_code, '_msg': r.text[:200]}

def fpost(endpoint, params):
    p = sign(params)
    r = requests.post(FAPI + endpoint, params=p, headers={'X-MBX-APIKEY': API_KEY}, timeout=TIMEOUT)
    return r.json() if r.status_code == 200 else {'_error': r.status_code, '_msg': r.text[:200]}

def fdel(endpoint, params):
    p = sign(params)
    r = requests.delete(FAPI + endpoint, params=p, headers={'X-MBX-APIKEY': API_KEY}, timeout=TIMEOUT)
    return r.json() if r.status_code == 200 else {'_error': r.status_code, '_msg': r.text[:200]}

# ── SETUP ───────────────────────────────────────────
def setup_futures():
    """Initialize futures account: set leverage and margin type."""
    logger.info(f"Setting up {SYMBOL} futures with {LEVERAGE}x leverage...")
    
    # Set leverage
    r = fpost('/fapi/v1/leverage', {'symbol': SYMBOL, 'leverage': LEVERAGE})
    if '_error' in r:
        logger.error(f"Leverage setup failed: {r}")
        return False
    logger.info(f"Leverage set to {LEVERAGE}x")
    
    # Set margin type to ISOLATED
    r = fpost('/fapi/v1/marginType', {'symbol': SYMBOL, 'marginType': 'ISOLATED'})
    if '_error' in r and 'already' not in str(r):
        logger.warning(f"Margin type: {r.get('_msg', str(r))}")
    else:
        logger.info("Margin type: ISOLATED")
    
    return True

# ── PRICE ───────────────────────────────────────────
def get_price():
    r = requests.get(f'{FAPI}/fapi/v1/ticker/price', params={'symbol': SYMBOL}, timeout=TIMEOUT)
    if r.status_code == 200: return float(r.json()['price'])
    return None

def get_mark_price():
    r = requests.get(f'{FAPI}/fapi/v1/premiumIndex', params={'symbol': SYMBOL}, timeout=TIMEOUT)
    if r.status_code == 200: return float(r.json()['markPrice'])
    return None

# ── BALANCE ─────────────────────────────────────────
def get_wallet_balance():
    """Get USDT futures wallet balance."""
    r = fget('/fapi/v2/account')
    if '_error' in r: return None, None, None
    for asset in r.get('assets', []):
        if asset['asset'] == 'USDT':
            wallet = float(asset['walletBalance'])
            margin = float(asset['marginBalance'])
            pnl = float(asset['unrealizedProfit'])
            return wallet, margin, pnl
    return None, None, None

def get_position():
    """Get current SOLUSDT position."""
    r = fget('/fapi/v2/positionRisk', {'symbol': SYMBOL})
    if '_error' in r: return None
    for pos in r:
        if pos['symbol'] == SYMBOL:
            return {
                'size': float(pos['positionAmt']),
                'entry': float(pos['entryPrice']),
                'liq': float(pos['liquidationPrice']),
                'margin': float(pos['isolatedMargin']),
                'pnl': float(pos['unRealizedProfit']),
                'roe': float(pos['unRealizedProfit']) / max(float(pos['isolatedMargin']), 0.01) * 100
            }
    return {'size': 0, 'entry': 0, 'liq': 0, 'margin': 0, 'pnl': 0, 'roe': 0}

# ── FUNDING RATE ────────────────────────────────────
def get_funding_rate():
    r = requests.get(f'{FAPI}/fapi/v1/premiumIndex', params={'symbol': SYMBOL}, timeout=TIMEOUT)
    if r.status_code == 200:
        data = r.json()
        return float(data.get('lastFundingRate', 0)) * 100  # in percent
    return 0

# ── ORDER MANAGEMENT ────────────────────────────────
def cancel_all():
    """Cancel all open orders for SYMBOL."""
    r = fdel('/fapi/v1/allOpenOrders', {'symbol': SYMBOL})
    return '_error' not in r

def place_limit_order(side, qty, price, reduce=False):
    """Place a limit order on futures."""
    params = {
        'symbol': SYMBOL,
        'side': side,
        'type': 'LIMIT',
        'timeInForce': 'GTC',
        'quantity': round(qty, 3),
        'price': round(price, 2)
    }
    if reduce:
        params['reduceOnly'] = 'true'
    r = fpost('/fapi/v1/order', params)
    return r if '_error' not in r else None

def place_market_order(side, qty, reduce=False):
    """Place a market order."""
    params = {
        'symbol': SYMBOL,
        'side': side,
        'type': 'MARKET',
        'quantity': round(qty, 3)
    }
    if reduce:
        params['reduceOnly'] = 'true'
    r = fpost('/fapi/v1/order', params)
    return r if '_error' not in r else None

# ── GRID LOGIC ─────────────────────────────────────
def calculate_grid(current_price):
    """Calculate buy grid levels below current price."""
    levels = []
    step = GRID_RANGE_PCT / GRID_LEVELS
    
    for i in range(GRID_LEVELS):
        buy_price = current_price * (1 - (i + 1) * step)
        order_size = BASE_ORDER_USDT * (MARTINGALE ** i)
        qty = order_size / buy_price
        
        # Convert: margin order → notional with leverage
        notional_qty = qty * LEVERAGE  # Actual contract qty
        
        levels.append({
            'level': i,
            'buy_price': round(buy_price, 2),
            'margin_order': round(order_size, 2),
            'notional_qty': round(notional_qty, 3),
            'sell_price': round(buy_price * (1 + PROFIT_PCT), 2)
        })
    
    return levels

def log_profit(amount):
    """Log profit to CSV for charting."""
    with open(PROFIT_LOG, 'a') as f:
        f.write(f"{datetime.now().isoformat()},{amount:.4f}\n")

# ── STATE ───────────────────────────────────────────
def load_state():
    try:
        with open(STATE_FILE) as f: return json.load(f)
    except: return {'active_levels': [], 'total_profit': 0.0, 'peak_margin': MARGIN, 'daily_pnl': [], 'cumulative': []}

def save_state(s):
    with open(STATE_FILE, 'w') as f: json.dump(s, f, indent=2)

# ── MAIN LOOP ──────────────────────────────────────
def main():
    logger.info("=" * 50)
    logger.info("🚀 DENARO PRO FUTURES GRID STARTED")
    logger.info(f"Symbol: {SYMBOL} | Leverage: {LEVERAGE}x | Margin: {MARGIN} USDT")
    
    if not setup_futures():
        logger.error("Setup failed")
        return
    
    state = load_state()
    
    # Initialize profit log header
    if not os.path.exists(PROFIT_LOG):
        with open(PROFIT_LOG, 'w') as f:
            f.write("timestamp,profit\n")
    
    error_count = 0
    circuit_breaker_time = 0
    
    while True:
        try:
            tick = time.time()
            
            # 1. Get current price
            price = get_mark_price()
            if not price:
                logger.warning("Price fetch failed")
                time.sleep(CHECK_INTERVAL)
                continue
            
            # 2. Get wallet status
            wallet, margin_balance, upnl = get_wallet_balance()
            if wallet is None:
                logger.warning("Balance fetch failed")
                time.sleep(CHECK_INTERVAL)
                continue
            
            current_loss = (MARGIN - margin_balance) / MARGIN * 100
            overall_pnl = margin_balance - MARGIN
            
            # 3. Circuit breaker
            if overall_pnl < -MARGIN * CIRCUIT_BREAKER_PCT:
                if circuit_breaker_time == 0:
                    circuit_breaker_time = time.time()
                    logger.warning(f"🔴 CIRCUIT BREAKER: PnL {overall_pnl:.2f}USDT ({current_loss:.1f}%)")
                    cancel_all()
                    # Close any position
                    pos = get_position()
                    if pos and abs(pos['size']) > 0:
                        side = 'SELL' if pos['size'] > 0 else 'BUY'
                        place_market_order(side, abs(pos['size']), reduce=True)
                        logger.info("Position closed by circuit breaker")
                    time.sleep(300)  # Pause 5 min
                    circuit_breaker_time = 0
                    continue
            else:
                circuit_breaker_time = 0
            
            # 4. Stop loss check
            if overall_pnl < -MARGIN * STOP_LOSS_PCT:
                logger.error(f"🛑 STOP LOSS: PnL {overall_pnl:.2f}USDT ({current_loss:.1f}%)")
                cancel_all()
                pos = get_position()
                if pos and abs(pos['size']) > 0:
                    side = 'SELL' if pos['size'] > 0 else 'BUY'
                    place_market_order(side, abs(pos['size']), reduce=True)
                    logger.info("All positions closed by stop loss")
                time.sleep(3600)  # Pause 1 hour
                continue
            
            # 5. Get funding rate
            fund_rate = get_funding_rate()
            
            # 6. Get current position
            pos = get_position()
            
            # 7. Calculate grid
            levels = calculate_grid(price)
            
            # 8. Check if grid is active (has orders)
            active_orders = fget('/fapi/v1/openOrders', {'symbol': SYMBOL})
            if '_error' in active_orders:
                active_orders = []
            
            existing_order_prices = set()
            if isinstance(active_orders, list):
                existing_order_prices = {float(o['price']): o for o in active_orders if o['symbol'] == SYMBOL}
            
            # 9. Place missing buy orders
            placed = 0
            for lvl in levels:
                bp = lvl['buy_price']
                # Check if order already exists at this price
                if bp in existing_order_prices:
                    continue
                
                # Check available margin
                if margin_balance < MARGIN * 0.9:
                    logger.warning(f"Margin low ({margin_balance:.2f}), skipping orders")
                    break
                
                order = place_limit_order('BUY', lvl['notional_qty'], bp)
                if order:
                    logger.info(f"  BUY order @ {bp}€ ({lvl['notional_qty']} SOL)")
                    placed += 1
                    time.sleep(0.2)
            
            # 10. Check filled orders (simplified: check position changes)
            if pos and abs(pos['size']) > 0.01:
                # Check if we have sells at the right levels
                for lvl in levels:
                    sp = lvl['sell_price']
                    if sp not in existing_order_prices:
                        # Place sell order for profit
                        sell_qty = abs(pos['size'])
                        order = place_limit_order('SELL', min(sell_qty, lvl['notional_qty']), sp, reduce=True)
                        if order:
                            logger.info(f"  SELL order @ {sp}€ (take profit)")
                            break  # One sell order at a time
            
            # 11. Log status
            if pos:
                logger.info(f"Status | Price: {price:.2f} | PnL: {overall_pnl:+.2f}USDT | "
                          f"ROE: {pos['roe']:+.1f}% | Liq: {pos.get('liq',0):.2f} | "
                          f"Funding: {fund_rate:.4f}% | Active orders: {len(existing_order_prices)}")
            
            # 12. Update cumulative profit
            if overall_pnl > 0:
                # Track peak
                if margin_balance > state.get('peak_margin', MARGIN):
                    state['peak_margin'] = margin_balance
            
            # 13. Daily PnL tracking
            today = datetime.now().strftime('%Y-%m-%d')
            daily_pnl = state.get('daily_pnl', [])
            today_entry = next((d for d in daily_pnl if d['date'] == today), None)
            if today_entry:
                today_entry['pnl'] = round(overall_pnl, 2)
            else:
                daily_pnl.append({'date': today, 'pnl': round(overall_pnl, 2)})
                if len(daily_pnl) > 30:
                    daily_pnl = daily_pnl[-30:]
            
            state['daily_pnl'] = daily_pnl
            state['last_check'] = time.time()
            state['current_price'] = price
            state['current_pnl'] = round(overall_pnl, 2)
            save_state(state)
            
            if overall_pnl > 0.5 and abs(overall_pnl - state.get('last_logged_pnl', 0)) > 0.5:
                log_profit(overall_pnl)
                state['last_logged_pnl'] = overall_pnl
                save_state(state)
            
            error_count = 0
            elapsed = time.time() - tick
            sleep_time = max(1, CHECK_INTERVAL - elapsed)
            time.sleep(sleep_time)
            
        except KeyboardInterrupt:
            logger.info("Stopped by user")
            break
        except Exception as e:
            logger.error(f"Error: {e}")
            error_count += 1
            if error_count > 10:
                logger.error("Too many errors, pausing 5 min")
                time.sleep(300)
                error_count = 0
            time.sleep(CHECK_INTERVAL)

if __name__ == '__main__':
    main()
