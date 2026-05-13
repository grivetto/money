#!/home/sergio/denaro/venv/bin/python
import os, json, hmac, hashlib, urllib.parse, time, requests
from dotenv import load_dotenv

env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(env_path)
API_KEY = os.getenv('BINANCE_API_KEY')
API_SECRET = os.getenv('BINANCE_API_SECRET')
BASE = 'https://api.binance.com'

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
    headers = {'X-MBX-APIKEY': API_KEY} if signed else {}
    r = requests.get(BASE + endpoint, params=p, headers=headers, timeout=15)
    if r.status_code != 200:
        raise Exception(f"HTTP {r.status_code}: {r.text[:300]}")
    return r.json()

result = {}

# --- Prices (unsigned) ---
symbols = ["SOLEUR", "BTCEUR", "DOGEEUR", "ADAEUR", "ETHEUR"]
prices = {}
for sym in symbols:
    t = binance_get('/api/v3/ticker/price', {'symbol': sym}, signed=False)
    prices[sym] = t['price']
result['prices'] = prices

# --- Account Balances (signed) ---
account = binance_get('/api/v3/account')
balances_nonzero = []
for bal in account['balances']:
    free = float(bal['free'])
    locked = float(bal['locked'])
    if free > 0 or locked > 0:
        balances_nonzero.append({
            'asset': bal['asset'],
            'free': bal['free'],
            'locked': bal['locked']
        })
result['balances'] = balances_nonzero

# --- Open Orders on ALL pairs (signed) ---
open_orders = binance_get('/api/v3/openOrders')
result['open_orders'] = open_orders

# --- Recent Trades ---
trade_symbols = {"SOLEUR": 5, "DOGEEUR": 5, "ADAEUR": 5}
trades = {}
for sym, lim in trade_symbols.items():
    t = binance_get('/api/v3/myTrades', {'symbol': sym, 'limit': lim})
    trades[sym] = t
result['recent_trades'] = trades

print(json.dumps(result, indent=2, default=str))
