#!/usr/bin/env python3
"""Denaro Sentiment Monitor - Fear & Greed Index + Market Sentiment"""
import json, time, logging, os
from urllib.request import Request, urlopen

BASE = "/home/sergio/denaro/dashboard/public"
os.makedirs(BASE, exist_ok=True)

def get_fng():
    """Get Fear & Greed Index from alternative.me API"""
    try:
        req = Request("https://api.alternative.me/fng/?limit=1", headers={'User-Agent': 'Mozilla/5.0'})
        data = json.loads(urlopen(req, timeout=10).read())
        if data.get('data'):
            entry = data['data'][0]
            return {
                'value': int(entry.get('value', 50)),
                'classification': entry.get('value_classification', 'Neutral'),
                'timestamp': entry.get('timestamp', int(time.time()))
            }
    except Exception as e:
        logging.warning(f"FNG error: {e}")
    return {'value': 50, 'classification': 'Neutral', 'timestamp': int(time.time())}

def get_btc_dominance():
    """Get BTC dominance from CoinGecko"""
    try:
        req = Request("https://api.coingecko.com/api/v3/global", headers={'User-Agent': 'Mozilla/5.0'})
        data = json.loads(urlopen(req, timeout=10).read())
        dom = data.get('data', {}).get('market_cap_percentage', {}).get('btc', 0)
        return round(dom, 1)
    except:
        return 0

try:
    fng = get_fng()
    btc_dom = get_btc_dominance()
    
    sentiment = {
        'ts': time.strftime("%H:%M"),
        'fng': fng['value'],
        'label': fng['classification'],
        'btc_dom': btc_dom,
        'updated': int(time.time())
    }
    
    json.dump(sentiment, open(f"{BASE}/sentiment.json", "w"))
    print(f"Sentiment: FNG={fng['value']} ({fng['classification']}) | BTCdom={btc_dom}%")
except Exception as e:
    print(f"Sentiment error: {e}")
