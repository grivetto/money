#!/usr/bin/env python3
"""
DENARO PORTFOLIO MONITOR
Tracks total portfolio value, P&L, and all bot statuses across the Denaro infrastructure.
Inspired by TradingAgents Portfolio Manager.
Runs every 30 min via systemd timer.
"""
import os, sys, json, time, logging, hmac, hashlib, urllib.parse, requests, subprocess
from datetime import datetime
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))
API_KEY = os.getenv('BINANCE_API_KEY')
API_SECRET = os.getenv('BINANCE_API_SECRET')
TMP_DIR = os.path.join(BASE_DIR, ".tmp")
STATE_FILE = os.path.join(TMP_DIR, "portfolio_state.json")
HISTORY_FILE = os.path.join(TMP_DIR, "portfolio_history.json")
os.makedirs(TMP_DIR, exist_ok=True)

LOG_FILE = os.path.join(BASE_DIR, "portfolio_monitor.log")
logging.basicConfig(level=logging.INFO, format='%(asctime)s - PORTFOLIO - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()])
logger = logging.getLogger("Portfolio")

# Bot services to monitor
BOT_SERVICES = [
    'grid_bot_v3', 'sell_grid_bot', 'risk_manager',
    'trend_following_bot', 'hedge_bot', 'market_technician', 'config_supervisor'
]

BINANCE = 'https://api.binance.com'

def read_json(path):
    try:
        with open(path) as f: return json.load(f)
    except: return None

def write_json(path, data):
    with open(path, 'w') as f: json.dump(data, f, indent=2)

def get_service_status():
    """Check systemd user service status for all bots"""
    statuses = {}
    for name in BOT_SERVICES:
        try:
            r = subprocess.run(['systemctl', '--user', 'is-active', f'{name}.service'],
                             capture_output=True, text=True, timeout=5)
            active = r.stdout.strip() == 'active'
            # Also check if process is running as fallback
            if not active:
                r2 = subprocess.run(['pgrep', '-f', f'{name}.py'], capture_output=True, timeout=5)
                active = r2.returncode == 0
            statuses[name] = 'active' if active else 'inactive'
        except:
            statuses[name] = 'unknown'
    return statuses

def get_portfolio():
    """Fetch full portfolio from Binance"""
    ts = int(time.time() * 1000)
    sig = hmac.new(API_SECRET.encode(), urllib.parse.urlencode({'timestamp': ts}).encode(), hashlib.sha256).hexdigest()
    bal = requests.get(f'{BINANCE}/api/v3/account', params={'timestamp': ts, 'signature': sig},
                       headers={'X-MBX-APIKEY': API_KEY}, timeout=10)
    if bal.status_code != 200: return None, None
    
    data = bal.json()
    pr = requests.get(f'{BINANCE}/api/v3/ticker/price', timeout=10)
    prices = {p['symbol']: float(p['price']) for p in pr.json()} if pr.status_code == 200 else {}
    
    total = 0.0
    details = {}
    for b in data['balances']:
        free = float(b['free'])
        locked = float(b['locked'])
        qty = free + locked
        if qty <= 0.001: continue
        if b['asset'] == 'EUR':
            val = qty
            total += val
            details['EUR'] = round(val, 2)
        elif b['asset'] + 'EUR' in prices:
            val = qty * prices[b['asset'] + 'EUR']
            total += val
            details[b['asset']] = round(val, 2)
    
    return round(total, 2), details

def main():
    logger.info("=" * 50)
    logger.info("PORTFOLIO MONITOR STARTED")
    
    # Check service statuses
    services = get_service_status()
    logger.info(f"Services: {json.dumps(services)}")
    
    # Get portfolio value
    total, details = get_portfolio()
    if total is None:
        logger.error("Failed to fetch portfolio")
        return
    
    logger.info(f"Portfolio: {total}€")
    for asset, val in sorted(details.items(), key=lambda x: -x[1]):
        logger.info(f"  {asset}: {val:.2f}€")
    
    # Load history
    history = read_json(HISTORY_FILE) or {'snapshots': []}
    now = time.time()
    
    # Calculate daily change
    today_start = now - (now % 86400)
    yesterday_snapshots = [s for s in history['snapshots'] if s['timestamp'] >= today_start - 86400 and s['timestamp'] < today_start]
    yesterday_close = yesterday_snapshots[-1]['total'] if yesterday_snapshots else total
    daily_change = total - yesterday_close
    daily_change_pct = (daily_change / yesterday_close * 100) if yesterday_close > 0 else 0
    
    # Build portfolio state
    state = {
        'timestamp': now,
        'datetime': datetime.now().isoformat(),
        'total_eur': total,
        'daily_change': round(daily_change, 2),
        'daily_change_pct': round(daily_change_pct, 2),
        'details': {k: v for k, v in sorted(details.items(), key=lambda x: -x[1])},
        'service_status': services,
        'alerts': []
    }
    
    # Generate alerts
    inactive = [s for s, st in services.items() if st != 'active']
    if inactive:
        state['alerts'].append(f"⚠️ Bots INACTIVE: {', '.join(inactive)}")
        logger.warning(f"Inactive bots: {inactive}")
    
    if daily_change < -10:
        state['alerts'].append(f"🔴 Daily loss > 10€: {daily_change:.2f}€")
        logger.warning(f"Large daily loss: {daily_change:.2f}€")
    
    # Save snapshot to history
    history['snapshots'].append({
        'timestamp': now,
        'total': total,
        'daily_change': round(daily_change, 2)
    })
    # Keep last 7 days of hourly data
    cutoff = now - 7 * 86400
    history['snapshots'] = [s for s in history['snapshots'] if s['timestamp'] > cutoff]
    # Keep max 500 snapshots
    if len(history['snapshots']) > 500:
        history['snapshots'] = history['snapshots'][-500:]
    
    write_json(STATE_FILE, state)
    write_json(HISTORY_FILE, history)
    
    logger.info(f"Daily change: {daily_change:+.2f}€ ({daily_change_pct:+.2f}%)")
    logger.info(f"Active bots: {sum(1 for s in services.values() if s == 'active')}/{len(services)}")
    logger.info("Portfolio monitor cycle complete")

if __name__ == '__main__':
    main()
