#!/usr/bin/env python3
"""
DENARO PORTFOLIO REBALANCER v1
Mantiene allocazioni fisse tra gli asset.
Vende sovrappesato, compra sottopesato.
"""
import os, json, time, logging, ccxt
from dotenv import load_dotenv
from vault_utils import atomic_write, atomic_read

load_dotenv(os.path.join(os.path.dirname(__file__) or ".", ".env"))

# Target allocation: percentuali del portafoglio totale
TARGETS = {"EUR": 15, "SOL": 25, "ADA": 25, "ETH": 20, "BNB": 15}
REBALANCE_THRESHOLD = 5  # % di deviazione per attivare il rebalance
CHECK_INTERVAL = 3600    # Ogni ora
LOG_FILE = os.path.join(os.path.dirname(__file__) or ".", "rebalancer.log")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - REBAL - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler(LOG_FILE)])
logger = logging.getLogger("Rebalancer")

ex = ccxt.binance({
    'apiKey': os.getenv("BINANCE_API_KEY"),
    'secret': os.getenv("BINANCE_API_SECRET"),
    'enableRateLimit': True,
    'options': {'defaultType': 'spot', 'defaultFeeCurrency': 'BNB'},
})

# Price cache
prices = {}

def get_price(sym):
    if sym == "EUR": return 1.0
    try:
        pair = f"{sym}/EUR" if sym != "USDT" else "USDT/EUR"
        return ex.fetch_ticker(pair)['last']
    except:
        try:
            pair = f"{sym}/USDT"
            usdt = ex.fetch_ticker("USDT/EUR")['last']
            return ex.fetch_ticker(pair)['last'] * usdt
        except:
            return 0

def get_portfolio():
    bal = ex.fetch_balance()
    total = 0
    assets = {}
    for asset in list(TARGETS.keys()) + ["DOT", "AVAX", "LINK", "DOGE"]:
        amount = bal['total'].get(asset, 0)
        if amount > 0.0001:
            price = get_price(asset)
            value = amount * price
            total += value
            assets[asset] = {"amount": amount, "price": price, "value": value}
    
    return assets, total

def rebalance():
    assets, total = get_portfolio()
    
    if total < 10:
        logger.info(f"Portafoglio troppo piccolo: {total:.2f}€")
        return
    
    logger.info(f"📊 Portafoglio: {total:.2f}€")
    deviations = []
    
    for asset, target_pct in TARGETS.items():
        current = assets.get(asset, {"amount": 0, "value": 0})
        current_pct = (current['value'] / total * 100) if total > 0 else 0
        deviation = current_pct - target_pct
        
        status = "✅" if abs(deviation) < REBALANCE_THRESHOLD else "⚠️"
        logger.info(f"  {status} {asset:5s}: {current_pct:5.1f}% (target {target_pct}%) | dev={deviation:+.1f}% | val={current['value']:6.2f}€")
        
        if abs(deviation) >= REBALANCE_THRESHOLD and asset != "EUR":
            deviations.append((asset, deviation, target_pct, current))
    
    if not deviations:
        logger.info("✅ Portafoglio bilanciato. Nessuna azione necessaria.")
        return
    
    for asset, deviation, target_pct, current in deviations:
        trade_value = abs(current['value'] - (total * target_pct / 100))
        trade_value = min(trade_value, total * 0.1)  # Max 10% del totale per trade
        
        if trade_value < 5:
            logger.info(f"  Importo troppo piccolo per {asset}: {trade_value:.2f}€ (min 5€)")
            continue
        
        try:
            if deviation > 0:  # Sovrappesato → VENDI
                sell_amount = trade_value / current['price']
                logger.info(f"  📉 VENDI {asset}: {sell_amount:.4f} @ {current['price']:.2f}€ ({trade_value:.2f}€)")
                ex.create_market_sell_order(f"{asset}/EUR", round(sell_amount, 5))
            else:  # Sottopesato → COMPRA
                buy_amount = trade_value / current['price']
                logger.info(f"  📈 COMPRA {asset}: {buy_amount:.4f} @ {current['price']:.2f}€ ({trade_value:.2f}€)")
                ex.create_market_buy_order(f"{asset}/EUR", round(buy_amount, 5))
            
            time.sleep(2)  # Pausa tra ordini
            
        except Exception as e:
            logger.error(f"  ❌ Errore {asset}: {e}")

if __name__ == "__main__":
    logger.info(f"🟢 Portfolio Rebalancer avviato")
    logger.info(f"   Target: {TARGETS}")
    logger.info(f"   Soglia: {REBALANCE_THRESHOLD}%")
    while True:
        try:
            rebalance()
        except Exception as e:
            logger.error(f"Errore: {e}")
        time.sleep(CHECK_INTERVAL)
