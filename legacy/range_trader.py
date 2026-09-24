#!/usr/bin/env python3
"""
Range Trader Bot - Simple range trading automation for low capital.
Maintains a SELL above and a BUY below current price.
When an order fills, places the opposite order to capture profit.
Works with SOL/EUR on Binance spot.
"""
import os, time, hmac, hashlib, requests, json, sys
from dotenv import load_dotenv
load_dotenv()

API_KEY = os.getenv('BINANCE_API_KEY')
API_SECRET = os.getenv('BINANCE_API_SECRET')
SYMBOL = 'SOLEUR'
SPREAD_PCT = 0.006  # 0.6% spread
ORDER_SIZE_SOL = 0.3  # ~23 EUR per side
CHECK_INTERVAL = 60  # seconds

def sign(params):
    return hmac.new(API_SECRET.encode(), params.encode(), hashlib.sha256).hexdigest()

def headers():
    return {'X-MBX-APIKEY': API_KEY}

def api_call(method, endpoint, params=''):
    ts = int(time.time() * 1000)
    full_params = f'{params}&timestamp={ts}&recvWindow=5000' if params else f'timestamp={ts}&recvWindow=5000'
    sig = sign(full_params)
    url = f'https://api.binance.com/api/v3/{endpoint}?{full_params}&signature={sig}'
    r = requests.request(method, url, headers=headers(), timeout=10)
    return r

def get_price():
    r = requests.get(f'https://api.binance.com/api/v3/ticker/price?symbol={SYMBOL}', timeout=5)
    return float(r.json()['price'])

def get_open_orders():
    r = api_call('GET', 'openOrders')
    if r.status_code == 200:
        return r.json()
    return []

def cancel_all():
    orders = get_open_orders()
    for o in orders:
        api_call('DELETE', 'order', f'symbol={o["symbol"]}&orderId={o["orderId"]}')
        print(f'Cancelled {o["symbol"]} {o["side"]} order {o["orderId"]}')
    return len(orders)

def place_order(side, qty, price):
    params = f'symbol={SYMBOL}&side={side}&type=LIMIT&timeInForce=GTC&quantity={qty:.4f}&price={price:.2f}'
    r = api_call('POST', 'order', params)
    if r.status_code == 200:
        print(f'Placed {side} {qty:.4f} SOL @ {price:.2f} = {qty*price:.2f} EUR')
        return r.json()
    else:
        print(f'Failed {side}: {r.status_code} {r.text}')
        return None

def main():
    print(f'Range Trader started - {SYMBOL}')
    print(f'Spread: {SPREAD_PCT*100:.1f}%, Order size: {ORDER_SIZE_SOL} SOL')
    
    while True:
        try:
            price = get_price()
            orders = get_open_orders()
            
            # Count current orders by side
            sells = [o for o in orders if o['symbol'] == SYMBOL and o['side'] == 'SELL']
            buys = [o for o in orders if o['symbol'] == SYMBOL and o['side'] == 'BUY']
            
            # Check if any orders were filled since last check
            if len(sells) + len(buys) < 2:
                print(f'Order filled! Rebalancing...')
                cancel_all()
                price = get_price()  # fresh price
            
            # Ensure we have one SELL above and one BUY below current price
            if not sells:
                sell_price = round(price * (1 + SPREAD_PCT), 2)
                place_order('SELL', ORDER_SIZE_SOL, sell_price)
            else:
                # Check if existing sell price is too far from current
                existing_sell = float(sells[0]['price'])
                if existing_sell < price * (1 + SPREAD_PCT * 0.5):
                    print(f'Recenter sell: {existing_sell} -> {round(price * (1 + SPREAD_PCT), 2)}')
                    cancel_all()
                    continue
            
            if not buys:
                buy_price = round(price * (1 - SPREAD_PCT), 2)
                place_order('BUY', ORDER_SIZE_SOL, buy_price)
            else:
                existing_buy = float(buys[0]['price'])
                if existing_buy > price * (1 - SPREAD_PCT * 0.5):
                    print(f'Recenter buy: {existing_buy} -> {round(price * (1 - SPREAD_PCT), 2)}')
                    cancel_all()
                    continue
            
            print(f'[{time.strftime("%H:%M:%S")}] Price: {price:.2f} | Sell: {sells[0]["price"] if sells else "N/A"} | Buy: {buys[0]["price"] if buys else "N/A"}')
            
        except Exception as e:
            print(f'Error: {e}')
        
        time.sleep(CHECK_INTERVAL)

if __name__ == '__main__':
    main()
