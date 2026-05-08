#!/usr/bin/env python3
import ccxt
import os
import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("BINANCE_API_KEY")
api_secret = os.getenv("BINANCE_API_SECRET")

if not api_key or not api_secret:
    print("ERRORE: API keys non trovate")
    exit(1)

exchange = ccxt.binance({
    "apiKey": api_key,
    "secret": api_secret,
    "enableRateLimit": True
})

# Soglie alert
THRESHOLDS = {
    'CRITICAL': 0.0005,
    'WARNING': 0.001,
    'INFO': 0.002
}

STATE_FILE = '/home/marco/denaro/bnb_state.json'

def load_state():
    try:
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    except:
        return {'alerts': {'CRITICAL': False, 'WARNING': False, 'INFO': False}}

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def main():
    print(f"=== BNB CHECK @ {datetime.now().strftime('%H:%M:%S')} ===")
    
    try:
        balance = exchange.fetch_balance()
        bnb_free = balance.get("BNB", {}).get("free", 0)
        
        ticker = exchange.fetch_ticker("BNB/EUR")
        bnb_price = ticker["last"] if ticker["last"] else 543.74
        
        eur_value = bnb_free * bnb_price
        print(f"BNB: {bnb_free:.6f} BNB ({eur_value:.2f}€)")
        print(f"Prezzo: {bnb_price:.2f}€")
        
        # Calcola trade rimanenti
        fee_per_trade_eur = 0.0375  # 0.075% di 50€
        fee_per_trade_bnb = fee_per_trade_eur / bnb_price
        trades_left = int(bnb_free / fee_per_trade_bnb) if fee_per_trade_bnb > 0 else 0
        print(f"Trade rimanenti: {trades_left}")
        
        # Controlla soglie
        state = load_state()
        alert_log = []
        
        for level, threshold in THRESHOLDS.items():
            if bnb_free < threshold and not state['alerts'].get(level, False):
                if level == 'CRITICAL':
                    msg = f"🚨 BNB CRITICO: {bnb_free:.6f} BNB ({eur_value:.2f}€) - Solo {trades_left} trade!"
                elif level == 'WARNING':
                    msg = f"⚠️  BNB BASSO: {bnb_free:.6f} BNB ({eur_value:.2f}€) - {trades_left} trade rimasti"
                else:
                    msg = f"ℹ️  BNB in esaurimento: {bnb_free:.6f} BNB ({eur_value:.2f}€)"
                
                print(f"\n{msg}")
                alert_log.append(msg)
                state['alerts'][level] = True
        
        # Resetta se ricaricato
        if bnb_free > 0.004:
            for level in state['alerts']:
                if state['alerts'][level]:
                    print(f"✅ Alert {level} resettato (BNB ricaricato)")
                    state['alerts'][level] = False
        
        save_state(state)
        
        # Log alert
        if alert_log:
            with open('/home/marco/denaro/bnb_alerts.log', 'a') as f:
                for msg in alert_log:
                    f.write(f"{datetime.now().isoformat()} - {msg}\n")
        
        if not alert_log:
            print("\n✅ BNB sufficiente")
            
    except Exception as e:
        print(f"ERRORE: {e}")

if __name__ == "__main__":
    main()
