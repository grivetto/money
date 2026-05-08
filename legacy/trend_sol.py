#!/usr/bin/env python3
"""
DENARO TREND BOT - SOL/EUR
Macchina: MARCODG1
Capitale: €100
Strategia: Trend Following con trailing stop aggressivo
"""

import os
import time
import logging
import ccxt
import talib
import numpy as np

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - SOL_TREND - %(levelname)s - %(message)s'
)
logger = logging.getLogger("SOLTrend")

CONFIG = {
    "symbol": "SOL/EUR",
    "capital": 100.0,
    "max_position_pct": 0.15,  # Max 15% in una posizione
    "trend_ema_fast": 9,
    "trend_ema_slow": 21,
    "rsi_period": 14,
    "atr_period": 14,
    "trailing_stop_pct": 2.0,
    "profit_target_pct": 5.0,
    "check_interval": 60,
    "vault_pct": 0.33,
}

state = {
    "position": None,
    "entry_price": 0.0,
    "peak_price": 0.0,
    "total_profit": 0.0,
}

def get_client():
    return ccxt.binance({
        'apiKey': os.getenv("BINANCE_API_KEY"),
        'secret': os.getenv("BINANCE_API_SECRET"),
        'enableRateLimit': True,
    })

def get_ohlcv(client, limit=100):
    ohlcv = client.fetch_ohlcv(CONFIG["symbol"], '1h', limit=limit)
    return {
        'close': np.array([x[4] for x in ohlcv]),
        'high': np.array([x[2] for x in ohlcv]),
        'low': np.array([x[3] for x in ohlcv]),
        'volume': np.array([x[5] for x in ohlcv]),
    }

def check_entry(data, current_price):
    """Verifica se entrare in posizione"""
    closes = data['close']
    
    ema_fast = talib.EMA(closes, CONFIG["trend_ema_fast"])[-1]
    ema_slow = talib.EMA(closes, CONFIG["trend_ema_slow"])[-1]
    rsi = talib.RSI(closes, CONFIG["rsi_period"])[-1]
    
    # Condizioni: trend su, RSI non ipercomprato, prezzo vicino EMA
    trend_ok = ema_fast > ema_slow
    rsi_ok = 40 < rsi < 70
    price_ok = current_price > ema_fast * 0.98
    
    if trend_ok and rsi_ok and price_ok and state["position"] is None:
        return True, {'ema_fast': ema_fast, 'ema_slow': ema_slow, 'rsi': rsi}
    return False, {'ema_fast': ema_fast, 'ema_slow': ema_slow, 'rsi': rsi}

def check_exit(current_price):
    """Verifica se uscire dalla posizione"""
    if state["position"] is None:
        return False, "NO_POSITION"
    
    profit_pct = (current_price - state["entry_price"]) / state["entry_price"] * 100
    
    # Aggiorna peak
    state["peak_price"] = max(state["peak_price"], current_price)
    
    # Stop loss mobile
    stop = state["peak_price"] * (1 - CONFIG["trailing_stop_pct"] / 100)
    
    # Target profit
    if profit_pct >= CONFIG["profit_target_pct"]:
        return True, f"TARGET ({profit_pct:.1f}%)"
    
    # Trailing stop
    if current_price < stop:
        return True, f"TRAILING ({profit_pct:.1f}%)"
    
    return False, f"HOLD ({profit_pct:.1f}%)"

def main():
    logger.info("🚀 SOL TREND BOT Starting (MARCODG1) - Capital: €100")
    
    client = get_client()
    if not client:
        logger.error("No API client")
        return
    
    try:
        ticker = client.fetch_ticker(CONFIG["symbol"])
        current_price = ticker['last']
        logger.info(f"SOL price: {current_price}€")
    except Exception as e:
        logger.error(f"Price fetch failed: {e}")
        return
    
    logger.info(f"Strategy: Trend Following, Target: {CONFIG['profit_target_pct']}%, Trailing: {CONFIG['trailing_stop_pct']}%")
    
    while True:
        try:
            ticker = client.fetch_ticker(CONFIG["symbol"])
            current_price = ticker['last']
            data = get_ohlcv(client)
            
            # Check exit
            should_exit, reason = check_exit(current_price)
            if should_exit and state["position"]:
                profit = (current_price - state["entry_price"]) / state["entry_price"] * state["position"]
                state["total_profit"] += profit
                logger.info(f"🚨 EXIT {reason} @ {current_price}€, Profit: {profit:.2f}€")
                state["position"] = None
                state["entry_price"] = 0.0
                state["peak_price"] = 0.0
            
            # Check entry
            should_enter, indicators = check_entry(data, current_price)
            if should_enter:
                position_size = (CONFIG["capital"] * CONFIG["max_position_pct"]) / current_price
                try:
                    order = client.create_market_buy_order(CONFIG["symbol"], round(position_size, 5))
                    state["position"] = position_size
                    state["entry_price"] = current_price
                    state["peak_price"] = current_price
                    logger.info(f"✅ ENTER @ {current_price}€, Size: {position_size:.5f} SOL")
                except Exception as e:
                    logger.error(f"Buy failed: {e}")
            
            # Log status
            if time.time() % 300 < CONFIG["check_interval"]:
                logger.info(f"Price: {current_price}€, RSI: {indicators['rsi']:.1f}, EMA9: {indicators['ema_fast']:.2f}, EMA21: {indicators['ema_slow']:.2f}, Total Profit: {state['total_profit']:.2f}€")
            
            time.sleep(CONFIG["check_interval"])
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            logger.error(f"Error: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()
