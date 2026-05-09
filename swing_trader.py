#!/usr/bin/env python3
"""
DENARO SWING TRADER v1 — Swing Trading su Altcoin a Media Capitalizzazione
Cattura oscillazioni di medio termine (2-7 giorni) su asset volatili.
Segnali: RSI oversold/overbought + EMA trend filter.
Max 15€ per posizione, stop-loss 5%.
"""
import os, json, time, logging, hmac, hashlib, urllib.parse, requests
from datetime import datetime
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))
API_KEY = os.getenv('BINANCE_API_KEY')
API_SECRET = os.getenv('BINANCE_API_SECRET')
BINANCE = 'https://api.binance.com'
TMP_DIR = os.path.join(BASE_DIR, ".tmp")
STATE_FILE = os.path.join(BASE_DIR, "swing_state.json")
LOG_FILE = os.path.join(BASE_DIR, "swing_trader.log")
os.makedirs(TMP_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - SWING - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()])
logger = logging.getLogger("Swing")

# ── CONFIG ─────────────────────────────────────────
SYMBOLS = ['ADAEUR', 'AVAXEUR', 'DOTEUR']  # Altcoin target
MAX_POSITIONS = 2          # Max posizioni aperte contemporaneamente
MAX_PER_TRADE = 15.0       # EUR massimi per trade
STOP_LOSS_PCT = 5.0        # Stop loss percentuale
TAKE_PROFIT_PCT = 8.0      # Take profit percentuale
CHECK_INTERVAL = 300       # Ogni 5 minuti
RSI_OVERSOLD = 30          # Soglia oversold
RSI_OVERBOUGHT = 70        # Soglia overbought

def sign(params):
    ts = int(time.time() * 1000)
    params['timestamp'] = ts
    query = urllib.parse.urlencode(params)
    sig = hmac.new(API_SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()
    params['signature'] = sig
    return params

def binance_get(endpoint, params=None, signed=True):
    if params is None: params = {}
    p = sign(params) if signed else params
    r = requests.get(BINANCE + endpoint, params=p, headers={'X-MBX-APIKEY': API_KEY} if signed else {}, timeout=10)
    return r.json() if r.status_code == 200 else None

def binance_post(endpoint, params):
    p = sign(params)
    r = requests.post(BINANCE + endpoint, params=p, headers={'X-MBX-APIKEY': API_KEY}, timeout=10)
    return r.json() if r.status_code == 200 else None

# ── TECNICI ─────────────────────────────────────────
def fetch_klines(symbol, interval='4h', limit=30):
    r = requests.get(f'{BINANCE}/api/v3/klines', params={'symbol': symbol, 'interval': interval, 'limit': limit}, timeout=10)
    if r.status_code == 200:
        return [[float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])] for k in r.json()]
    return None

def ema(prices, period):
    if len(prices) < period: return None
    k = 2 / (period + 1)
    ema_vals = [sum(prices[:period]) / period]
    for p in prices[period:]:
        ema_vals.append((p - ema_vals[-1]) * k + ema_vals[-1])
    return ema_vals

def rsi(prices, period=14):
    if len(prices) < period + 1: return 50
    deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    gains = [max(d, 0) for d in deltas[-period:]]
    losses = [max(-d, 0) for d in deltas[-period:]]
    avg_g = sum(gains) / period
    avg_l = sum(losses) / period
    if avg_l == 0: return 100
    return 100 - (100 / (1 + avg_g / avg_l))

# ── STATO ───────────────────────────────────────────
def load_state():
    try:
        with open(STATE_FILE) as f: return json.load(f)
    except: return {'positions': [], 'total_pnl': 0.0, 'trades_closed': []}

def save_state(s):
    with open(STATE_FILE, 'w') as f: json.dump(s, f, indent=2)

# ── ANALISI ─────────────────────────────────────────
def analyze_symbol(symbol):
    """Return buy/sell/hold signal for a symbol"""
    klines = fetch_klines(symbol)
    if not klines or len(klines) < 20:
        return None
    
    closes = [k[3] for k in klines]
    current = closes[-1]
    
    rsi_val = rsi(closes)
    ema20 = ema(closes, 20)
    ema20_v = ema20[-1] if ema20 else current
    
    # Signal logic
    ema_dist = (current - ema20_v) / ema20_v * 100
    
    if rsi_val <= RSI_OVERSOLD and ema_dist < -2:
        signal = 'BUY'
    elif rsi_val >= RSI_OVERBOUGHT and ema_dist > 2:
        signal = 'SELL'
    else:
        signal = 'HOLD'
    
    return {
        'symbol': symbol,
        'price': current,
        'rsi': round(rsi_val, 1),
        'ema20': round(ema20_v, 2),
        'ema_dist_pct': round(ema_dist, 2),
        'signal': signal
    }

# ── MAIN ────────────────────────────────────────────
def main():
    logger.info("=" * 50)
    logger.info("SWING TRADER AVVIATO")
    state = load_state()
    
    # 1. Analyze all symbols
    signals = []
    for sym in SYMBOLS:
        analysis = analyze_symbol(sym)
        if analysis:
            signals.append(analysis)
            logger.info(f"{sym}: RSI={analysis['rsi']}, EMA20={analysis['ema_dist_pct']:+.1f}% → {analysis['signal']}")
    
    # 2. Check open positions for stop-loss / take-profit
    for pos in state.get('positions', [])[:]:
        # Get current price
        pr = binance_get('/api/v3/ticker/price', {'symbol': pos['symbol']}, signed=False)
        if not pr: continue
        current_price = float(pr['price'])
        
        change = (current_price - pos['entry_price']) / pos['entry_price'] * 100
        
        if change <= -STOP_LOSS_PCT:
            # Stop loss hit
            logger.info(f"🛑 STOP LOSS {pos['symbol']}: entrato {pos['entry_price']:.2f}, ora {current_price:.2f} ({change:.1f}%)")
            sell_qty = f"{min(pos['qty'], 99999):.4f}"
            result = binance_post('/api/v3/order', {
                'symbol': pos['symbol'], 'side': 'SELL', 'type': 'MARKET', 'quantity': sell_qty
            })
            if result and 'orderId' in result:
                loss = pos['invested'] * (STOP_LOSS_PCT / 100)
                state['total_pnl'] -= abs(loss)
                state['trades_closed'].append({
                    'symbol': pos['symbol'], 'type': 'stop_loss',
                    'entry': pos['entry_price'], 'exit': current_price,
                    'pnl': -round(abs(loss), 2), 'time': datetime.now().isoformat()
                })
                state['positions'].remove(pos)
                logger.info(f"  Posizione chiusa, loss: {abs(loss):.2f}€")
                save_state(state)
        
        elif change >= TAKE_PROFIT_PCT:
            # Take profit
            logger.info(f"🎯 TAKE PROFIT {pos['symbol']}: entrato {pos['entry_price']:.2f}, ora {current_price:.2f} ({change:.1f}%)")
            sell_qty = f"{min(pos['qty'], 99999):.4f}"
            result = binance_post('/api/v3/order', {
                'symbol': pos['symbol'], 'side': 'SELL', 'type': 'MARKET', 'quantity': sell_qty
            })
            if result and 'orderId' in result:
                profit = pos['invested'] * (TAKE_PROFIT_PCT / 100)
                state['total_pnl'] += profit
                state['trades_closed'].append({
                    'symbol': pos['symbol'], 'type': 'take_profit',
                    'entry': pos['entry_price'], 'exit': current_price,
                    'pnl': round(profit, 2), 'time': datetime.now().isoformat()
                })
                state['positions'].remove(pos)
                logger.info(f"  Posizione chiusa, profit: {profit:.2f}€")
                save_state(state)
        else:
            logger.info(f"  Posizione {pos['symbol']}: {change:+.2f}% (stop @ {STOP_LOSS_PCT}%, target @ {TAKE_PROFIT_PCT}%)")
    
    # 3. Open new positions based on signals
    active_count = len(state.get('positions', []))
    if active_count < MAX_POSITIONS:
        for sig in signals:
            if sig['signal'] == 'BUY' and active_count < MAX_POSITIONS:
                # Check balance
                ts = int(time.time() * 1000)
                sig_req = hmac.new(API_SECRET.encode(), urllib.parse.urlencode({'timestamp': ts}).encode(), hashlib.sha256).hexdigest()
                bal = binance_get('/api/v3/account', {'timestamp': ts, 'signature': sig_req})
                if not bal: continue
                eur_free = float([b for b in bal['balances'] if b['asset'] == 'EUR'][0]['free'])
                
                if eur_free < MAX_PER_TRADE:
                    logger.warning(f"EUR insufficiente per {sig['symbol']}: {eur_free:.2f}€")
                    continue
                
                # Place buy
                invest = min(MAX_PER_TRADE, eur_free * 0.5)
                qty = invest / sig['price']
                
                # Round to LOT_SIZE
                info = requests.get(f'{BINANCE}/api/v3/exchangeInfo', params={'symbol': sig['symbol']}).json()
                step_size = 0.001
                for f in info['symbols'][0]['filters']:
                    if f['filterType'] == 'LOT_SIZE':
                        step_size = float(f['stepSize'])
                        break
                qty_rounded = int(qty / step_size) * step_size
                actual_invest = qty_rounded * sig['price']
                
                result = binance_post('/api/v3/order', {
                    'symbol': sig['symbol'], 'side': 'BUY', 'type': 'MARKET',
                    'quantity': f"{qty_rounded:.{max(0, -int(__import__('math').log10(step_size)))}f}" if step_size >= 0.001 else f"{qty_rounded:.4f}"
                })
                
                if result and 'orderId' in result:
                    filled_qty = float(result.get('executedQty', qty_rounded))
                    filled_cost = float(result.get('cummulativeQuoteQty', actual_invest))
                    pos = {
                        'symbol': sig['symbol'],
                        'entry_price': sig['price'],
                        'qty': filled_qty,
                        'invested': filled_cost,
                        'time': datetime.now().isoformat(),
                        'signal': {'rsi': sig['rsi'], 'ema_dist': sig['ema_dist_pct']}
                    }
                    state['positions'].append(pos)
                    active_count += 1
                    logger.info(f"🟢 APERTA {sig['symbol']}: {filled_qty:.4f} @ {sig['price']:.2f}€ ({filled_cost:.2f}€)")
                    save_state(state)
    
    # 4. Summary
    logger.info(f"Posizioni aperte: {active_count} | PnL totale: {state.get('total_pnl', 0):.2f}€")
    save_state(state)

if __name__ == '__main__':
    while True:
        try:
            main()
        except Exception as e:
            logger.error(f"Errore: {e}")
        time.sleep(CHECK_INTERVAL)
