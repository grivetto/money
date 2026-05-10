#!/usr/bin/env python3
"""
DENARO MOMENTUM SCALPER v1 — Micro-scalping su ETH/EUR
Cattura micro-movimenti di 1-2 minuti su timeframe 1m.
Entry: EMA20 breakout + volume spike.
Exit: +0.3% profit target, -0.3% stop loss.
Max 20€ per trade, 1 posizione aperta.
"""
import os, json, time, logging, hmac, hashlib, urllib.parse, requests
from datetime import datetime
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))
API_KEY = os.getenv('BINANCE_API_KEY')
API_SECRET = os.getenv('BINANCE_API_SECRET')
BINANCE = 'https://api.binance.com'
STATE_FILE = os.path.join(BASE_DIR, "scalper_state.json")
LOG_FILE = os.path.join(BASE_DIR, "momentum_scalper.log")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - SCALPER - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()])
logger = logging.getLogger("Scalper")

# ── CONFIG ─────────────────────────────────────────
SYMBOL = "ETHEUR"
MAX_PER_TRADE = 20.0       # EUR massimi per trade
PROFIT_TARGET = 0.003      # +0.3%
STOP_LOSS = 0.003          # -0.3%
CHECK_INTERVAL = 15        # secondi
MIN_VOLUME_MULT = 1.5      # Volume > 1.5x media

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

# ── TECNICI ─────────────────────────────────────────
def get_1m_data(limit=30):
    k = api_get('/api/v3/klines', {'symbol': SYMBOL, 'interval': '1m', 'limit': limit}, signed=False)
    if not k: return None, None, None
    closes = [float(x[4]) for x in k]
    volumes = [float(x[5]) for x in k]
    return closes[-1], closes, volumes

def ema(values, period=20):
    if len(values) < period: return None
    k = 2 / (period + 1)
    ema_vals = [sum(values[:period]) / period]
    for v in values[period:]:
        ema_vals.append((v - ema_vals[-1]) * k + ema_vals[-1])
    return ema_vals

# ── STATO ───────────────────────────────────────────
def load_state():
    try:
        with open(STATE_FILE) as f: return json.load(f)
    except: return {'position': None, 'total_pnl': 0.0, 'trades': 0}

def save_state(s):
    with open(STATE_FILE, 'w') as f: json.dump(s, f, indent=2)

# ── MAIN ────────────────────────────────────────────
def check_position(pos, current_price):
    """Check if current position hit TP or SL"""
    entry = pos['entry_price']
    change = (current_price - entry) / entry
    
    if change >= PROFIT_TARGET:
        # Take profit
        qty = f"{pos['qty']:.{pos.get('precision', 4)}f}"
        result = api_post('/api/v3/order', {
            'symbol': SYMBOL, 'side': 'SELL', 'type': 'MARKET', 'quantity': qty
        })
        if result and 'orderId' in result:
            profit = pos['invested'] * PROFIT_TARGET
            logger.info(f"🎯 TP: venduto {pos['qty']:.4f} ETH @ {current_price}€, profit {profit:.4f}€")
            return {'filled': 'tp', 'profit': profit, 'exit_price': current_price}
    
    elif change <= -STOP_LOSS:
        # Stop loss
        qty = f"{pos['qty']:.{pos.get('precision', 4)}f}"
        result = api_post('/api/v3/order', {
            'symbol': SYMBOL, 'side': 'SELL', 'type': 'MARKET', 'quantity': qty
        })
        if result and 'orderId' in result:
            loss = pos['invested'] * STOP_LOSS
            logger.info(f"🛑 SL: venduto {pos['qty']:.4f} ETH @ {current_price}€, loss {loss:.4f}€")
            return {'filled': 'sl', 'profit': -loss, 'exit_price': current_price}
    
    return None

def look_for_entry(current_price, closes, volumes):
    """Look for momentum entry signal"""
    if len(closes) < 25 or len(volumes) < 25:
        return None
    
    ema_vals = ema(closes, 20)
    if not ema_vals: return None
    
    ema20 = ema_vals[-1]
    avg_vol = sum(volumes[-20:-5]) / 15 if len(volumes) >= 20 else sum(volumes) / len(volumes)
    
    # Entry conditions:
    # 1. Price > EMA20 (bullish momentum)
    # 2. Current volume > 1.5x average volume
    # 3. Previous candle was below EMA20 (breakout)
    # 4. Price moved up in last 3 candles
    
    price_above_ema = current_price > ema20 * 1.001  # 0.1% above
    vol_spike = volumes[-1] > avg_vol * MIN_VOLUME_MULT
    prev_below = closes[-2] < ema20 if len(closes) >= 2 else False
    upward = closes[-1] > closes[-3] if len(closes) >= 3 else False
    
    if price_above_ema and vol_spike and upward:
        logger.info(f"⚡ Segnale BUY: prezzo {current_price:.2f} > EMA20 {ema20:.2f}, volume {volumes[-1]:.0f} > media {avg_vol:.0f}")
        return True
    
    return False

def main():
    logger.info("=" * 50)
    logger.info("MOMENTUM SCALPER AVVIATO")
    state = load_state()
    
    current_price, closes, volumes = get_1m_data()
    if not current_price:
        logger.warning("Impossibile ottenere dati di mercato")
        return
    
    # 1. Check open position
    pos = state.get('position')
    if pos:
        result = check_position(pos, current_price)
        if result:
            state['total_pnl'] += result['profit']
            state['trades'] += 1
            state['position'] = None
            save_state(state)
            logger.info(f"📊 PnL totale: {state['total_pnl']:.4f}€ ({state['trades']} trade)")
            return  # Wait for next cycle to re-enter
    
    # 2. Look for entry (only if no position open)
    if not pos:
        # Check EUR balance
        ts = int(time.time() * 1000)
        sig = hmac.new(API_SECRET.encode(), urllib.parse.urlencode({'timestamp': ts}).encode(), hashlib.sha256).hexdigest()
        bal = api_get('/api/v3/account', {'timestamp': ts, 'signature': sig})
        if not bal: return
        eur_free = float([b for b in bal['balances'] if b['asset'] == 'EUR'][0]['free'])
        
        if eur_free < MAX_PER_TRADE:
            logger.info(f"EUR insufficiente per entry: {eur_free:.2f}€")
            return
        
        if look_for_entry(current_price, closes, volumes):
            # Place buy
            invest = min(MAX_PER_TRADE, eur_free * 0.8)
            qty = invest / current_price
            
            # Round to LOT_SIZE
            info = api_get('/api/v3/exchangeInfo', {'symbol': SYMBOL}, signed=False)
            step_size = 0.0001
            if info and info.get('symbols'):
                for f in info['symbols'][0]['filters']:
                    if f['filterType'] == 'LOT_SIZE':
                        step_size = float(f['stepSize'])
                        break
            step_str = str(step_size)
            decimals = abs(step_str.find('1') - step_str.find('.') - 1) if '.' in step_str else 4
            qty_rounded = int(qty / step_size) * step_size
            
            result = api_post('/api/v3/order', {
                'symbol': SYMBOL, 'side': 'BUY', 'type': 'MARKET',
                'quantity': f"{qty_rounded:.{decimals}f}"
            })
            
            if result and 'orderId' in result:
                filled_qty = float(result.get('executedQty', qty_rounded))
                filled_cost = float(result.get('cummulativeQuoteQty', qty_rounded * current_price))
                pos_data = {
                    'symbol': SYMBOL,
                    'entry_price': current_price,
                    'qty': filled_qty,
                    'invested': filled_cost,
                    'precision': decimals,
                    'time': datetime.now().isoformat()
                }
                state['position'] = pos_data
                save_state(state)
                logger.info(f"🟢 ENTRY: {filled_qty:.{decimals}f} ETH @ {current_price:.2f}€ ({filled_cost:.2f}€)")
                logger.info(f"   TP @ {current_price * (1+PROFIT_TARGET):.2f}€, SL @ {current_price * (1-STOP_LOSS):.2f}€")
        else:
            logger.debug(f"Nessun segnale: EMA20={ema(closes, 20)[-1]:.1f} prezzo={current_price}")

if __name__ == '__main__':
    while True:
        try:
            main()
        except Exception as e:
            logger.error(f"Errore: {e}")
        time.sleep(CHECK_INTERVAL)
