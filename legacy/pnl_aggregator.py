#!/usr/bin/env python3
"""Update pnl_state.json from actual bot states. Runs every 15 min via cron."""
import os, json, time, requests

BASE = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE, "pnl_state.json")

def read_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return {}

def write_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)

def get_price(symbol):
    try:
        r = requests.get(f'https://api.binance.com/api/v3/ticker/price?symbol={symbol}', timeout=10)
        return float(r.json()['price']) if r.status_code == 200 else None
    except:
        return None

# Read individual bot profits
profit_sources = {}

# 1. Sell grid state
sg = read_json(os.path.join(BASE, 'sell_grid_state.json'))
profit_sources['sell_grid'] = sg.get('total_profit', 0)

# 2. Grid bot log (last profit line)
try:
    with open(os.path.join(BASE, 'grid_bot_v3.log')) as f:
        for line in f:
            if 'Profit:' in line and 'Invested:' in line:
                parts = line.split('Profit:')
                if len(parts) > 1:
                    try:
                        profit_sources['grid_bot'] = float(parts[1].split('€')[0].strip())
                    except:
                        pass
except:
    profit_sources['grid_bot'] = 0

# 3. DCA state
dca = read_json(os.path.join(BASE, 'dca_state.json'))
eth_price = get_price('ETHEUR')
if dca and eth_price:
    total_asset = dca.get('total_asset', 0)
    total_invested = dca.get('total_invested', 0)
    current_value = total_asset * eth_price
    profit_sources['dca'] = round(current_value - total_invested, 2)
else:
    profit_sources['dca'] = 0

# 4. Shadow grid state
shadow = read_json(os.path.join(BASE, '.tmp/shadow_grid_state.json'))
profit_sources['shadow'] = shadow.get('total_profit', 0)

# 5. Swing & scalper (check their state files)
swing = read_json(os.path.join(BASE, 'swing_state.json'))
profit_sources['swing'] = swing.get('total_pnl', 0)

scalper = read_json(os.path.join(BASE, 'scalper_state.json'))
profit_sources['scalper'] = scalper.get('total_pnl', 0) if scalper else 0

# Agent PnL - reserved for flash_rebalancer
profit_sources['rebalancer'] = 0

# Total
total_pnl = round(sum(profit_sources.values()), 2)

# Write combined state
state = {
    'current_pnl': total_pnl,
    'last_updated': time.strftime('%Y-%m-%dT%H:%M:%S'),
    'sources': profit_sources
}
write_json(STATE_FILE, state)
print(f"pnl_state.json updated: total_pnl={total_pnl}€ | sources: {profit_sources}")
