#!/usr/bin/env python3
"""Zabbix wildcard metric extractor — restituisce una singola metrica dal JSON di zabbix_squadra.py.\n
Usage: zabbix_bot_metric.py <bot_name> <metric_name>   # es. vulcan eur\n
       zabbix_bot_metric.py total_eur                    # metrica globale\n"""
import json, sys, os

script_dir = os.path.dirname(os.path.abspath(__file__))
squadra_script = os.path.join(script_dir, 'zabbix_squadra.py')

# Run the main collector
result = os.popen(f'{sys.executable} {squadra_script}').read()
try:
    data = json.loads(result)
except Exception:
    print('0')
    sys.exit(1)

args = sys.argv[1:]

if len(args) == 1:
    # Global metric: total_eur, peak_eur, drawdown_pct, exposure, killswitch, bots_alive, bots_total, errors
    key = args[0].replace('-', '_')
    mapping = {
        'total_eur': 'eur',
        'peak_eur': 'peak',
        'drawdown_pct': 'drawdown_pct',
        'exposure': 'exposure',
        'killswitch': 'killswitch_state',
        'bots_alive': 'bots_alive',
        'bots_total': 'bots_total',
        'errors': 'errors',
    }
    k = mapping.get(key, key)
    print(data.get(k, 0))
elif len(args) == 2:
    # Bot metric: <bot_name> <metric>
    bot = args[0].lower()
    metric = args[1].lower()
    bot_data = data.get('bots', {}).get(bot, {})
    if not bot_data:
        print('0')
        sys.exit(0)
    m_map = {
        'eur': 'eur',
        'price': 'price',
        'entry_price': 'entry_price',
        'in_position': 'in_position',
        'action': 'action',
        'alive': 'alive',
        'pnl_eur': 'pnl_daily_eur',
        'pnl_pct': 'pnl_daily_pct',
    }
    k = m_map.get(metric, metric)
    val = bot_data.get(k, 0)
    if isinstance(val, bool):
        print('1' if val else '0')
    else:
        print(val)
else:
    print('0')
