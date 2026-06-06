import ccxt, sys, os
from dotenv import load_dotenv

# Load .env from denaro directory
script_dir = os.path.dirname(os.path.abspath(__file__))
denaro_dir = os.path.dirname(script_dir)
if denaro_dir.endswith('/tmp') or denaro_dir == '/tmp':
    # Fallback: look in home
    import subprocess
    user = 'marco' if 'marco' in __file__ else 'sergio'
    home = f'/home/{user}/denaro'
    env_path = os.path.join(home, '.env')
else:
    env_path = os.path.join(script_dir, '..', '.env')

load_dotenv(env_path)

api_key = os.getenv('BINANCE_API_KEY')
secret = os.getenv('BINANCE_API_SECRET')

if not api_key or not secret:
    print('ERROR: No API keys found in .env')
    sys.exit(1)

print(f'Using API key: {api_key[:8]}...{api_key[-4:]}')

ex = ccxt.binance({
    'apiKey': api_key,
    'secret': secret,
    'options': {'defaultType': 'spot'},
    'enableRateLimit': True,
})

bal = ex.fetch_balance()
doge = bal['free'].get('DOGE', 0)
usdc_before = bal['free'].get('USDC', 0)
print(f'DOGE={doge} USDC=${usdc_before:.2f}')

if doge < 1:
    print('No DOGE to sell')
    sys.exit(0)

ticker = ex.fetch_ticker('DOGE/USDC')
price = ticker['last']
value = round(doge * price, 2)
print(f'DOGE/USDC: ${price:.4f}, value: ${value}')

if value < 10:
    print(f'Under min $10 notional, skipping')
    sys.exit(0)

print(f'Market selling {doge} DOGE...')
order = ex.create_order('DOGE/USDC', 'market', 'sell', doge)
print(f'Sold! Filled: {order.get("filled", 0)}')

bal2 = ex.fetch_balance()
usdc = bal2['free'].get('USDC', 0)
print(f'USDC: ${usdc_before:.2f} -> ${usdc:.2f} (+${usdc-usdc_before:.2f})')
