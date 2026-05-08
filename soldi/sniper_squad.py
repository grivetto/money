import gc
import os
import time
import math
import logging
import json
from collections import deque
from datetime import datetime
from dotenv import load_dotenv
from binance.client import Client
from binance import ThreadedWebsocketManager
from binance.enums import *
from pathlib import Path
from trade_db import TradeDB

# --- CONFIGURATION ---
CONFIG = {
    "SYMBOLS": ["BTCEUR", "ETHEUR", "SOLEUR"],
    "MAX_TRADE_EUR": 60.0,
    "MAX_CONCURRENT_TRADES": 1,
    "TARGET_PERCENT": 0.015,
    "TARGET_FIXED_EUR": 5.0,
    "RSI_BUY_MIN": 28,
    "RSI_BUY_MAX": 80,
    "RSI_OVERSOLD": 26,
    "ATR_TP_MULT": 3.0,
    "ATR_SL_MULT": 1.2,
    "TP_TRAILING_FACTOR": 0.998,
    "VAULT_PERCENT": 0.20,
    "MIN_TRADE_EUR": 25.0,
    "LIMIT_ORDER_TIMEOUT": 45,
    "LOG_FILE": str(Path.home() / "denaro" / "sniper_squad.log"),
    "VAULT_FILE": str(Path.home() / "denaro" / "vault.json"),
    "MISSION_FILE": str(Path.home() / "denaro" / "daily_mission.json"),
    "DB_FILE": str(Path.home() / "denaro" / "trades.db"),
}

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler(CONFIG["LOG_FILE"]), logging.StreamHandler()]
)
logger = logging.getLogger("Sniper")

env_path = Path.home() / "denaro" / ".env"
load_dotenv(env_path)
API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")

if not API_KEY or not API_SECRET:
    logger.critical("API Credentials missing in .env!")
    exit(1)

try:
    client = Client(API_KEY, API_SECRET)
except Exception as e:
    logger.critical(f"Failed to connect to Binance: {e}")
    exit(1)

db = TradeDB(CONFIG["DB_FILE"])

klines = {s: deque(maxlen=100) for s in CONFIG["SYMBOLS"]}
highs = {s: deque(maxlen=100) for s in CONFIG["SYMBOLS"]}
lows = {s: deque(maxlen=100) for s in CONFIG["SYMBOLS"]}
volumes = {s: deque(maxlen=100) for s in CONFIG["SYMBOLS"]}
positions = {}
consecutive_losses = 0
paused_until = 0

def get_vault_locked():
    try:
        if os.path.exists(CONFIG["VAULT_FILE"]):
            with open(CONFIG["VAULT_FILE"], "r") as f:
                return float(json.load(f).get("LOCKED_EUR", 0.0))
    except:
        pass
    return 0.0

def add_to_vault(amount):
    locked = get_vault_locked() + amount
    try:
        with open(CONFIG["VAULT_FILE"], "w") as f:
            json.dump({"LOCKED_EUR": locked}, f)
        logger.info(f"Vault: +{amount:.2f}EUR -> {locked:.2f}EUR")
    except Exception as e:
        logger.error(f"Vault write error: {e}")

def get_daily_mission():
    today_str = datetime.now().strftime("%Y-%m-%d")
    try:
        if os.path.exists(CONFIG["MISSION_FILE"]):
            with open(CONFIG["MISSION_FILE"], "r") as f:
                mission = json.load(f)
            if mission.get("date") == today_str:
                return mission
    except:
        pass
    try:
        available_eur = float(client.get_asset_balance(asset="EUR")["free"])
    except:
        available_eur = 0.0
    usable_eur = max(0, available_eur - get_vault_locked())
    target_eur = CONFIG["TARGET_FIXED_EUR"]
    new_mission = {"date": today_str, "start_capital": usable_eur, "target_eur": target_eur, "profit_today": 0.0, "achieved": False}
    try:
        with open(CONFIG["MISSION_FILE"], "w") as f:
            json.dump(new_mission, f)
        logger.info(f"New daily mission: {target_eur:.2f}EUR (cap: {usable_eur:.2f}EUR)")
    except:
        pass
    return new_mission

def update_daily_mission(pnl_amount):
    mission = get_daily_mission()
    mission["profit_today"] += pnl_amount
    if mission["profit_today"] >= mission["target_eur"] and not mission["achieved"]:
        mission["achieved"] = True
        logger.info(f"DAILY GOAL REACHED: {mission['profit_today']:.2f}EUR")
    try:
        with open(CONFIG["MISSION_FILE"], "w") as f:
            json.dump(mission, f)
    except:
        pass
    return mission

def calc_ema(prices, period=9):
    if len(prices) < period:
        return prices[-1] if prices else 0
    k = 2 / (period + 1)
    ema = prices[0]
    for p in list(prices)[1:]:
        ema = (p * k) + (ema * (1 - k))
    return ema

def calc_rsi(prices, period=14):
    prices = list(prices)
    if len(prices) <= period:
        return 50.0
    gains, losses = 0.0, 0.0
    for i in range(1, period + 1):
        change = prices[i] - prices[i - 1]
        if change > 0:
            gains += change
        else:
            losses -= change
    if losses == 0:
        return 100.0
    rs = (gains / period) / (losses / period)
    return 100.0 - (100.0 / (1.0 + rs))

def calc_atr(high_prices, low_prices, close_prices, period=14):
    if len(close_prices) < period + 1:
        return 0.0
    tr_sum = 0.0
    h, l, c = list(high_prices), list(low_prices), list(close_prices)
    for i in range(-period, 0):
        tr = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
        tr_sum += tr
    return tr_sum / period

def get_step_size(symbol):
    try:
        info = client.get_symbol_info(symbol)
        for f in info["filters"]:
            if f["filterType"] == "LOT_SIZE":
                return float(f["stepSize"])
    except:
        pass
    return 1.0

def round_step(quantity, step_size):
    if step_size == 0:
        return quantity
    precision = int(round(-math.log10(step_size), 0))
    return round(quantity - (quantity % step_size), precision)

def cancel_stale_orders(symbol):
    try:
        orders = client.get_open_orders(symbol=symbol)
        for o in orders:
            client.cancel_order(symbol=symbol, orderId=o["orderId"])
            logger.info(f"Cancelled stale order: {symbol} {o['side']} {o['origQty']} @ {o['price']}")
    except Exception as e:
        logger.error(f"Error cancelling orders for {symbol}: {e}")

def get_btc_trend():
    try:
        klines_data = client.get_klines(symbol="BTCEUR", interval="15m", limit=40)
        closes = [float(k[4]) for k in klines_data]
        ema9 = calc_ema(closes, 9)
        ema21 = calc_ema(closes, 21)
        if ema9 < ema21:
            return "BEARISH"
        return "BULLISH"
    except:
        return "UNKNOWN"

def init_historical_data():
    for sym in CONFIG["SYMBOLS"]:
        try:
            hist = client.get_klines(symbol=sym, interval="1m", limit=100)
            for k in hist:
                klines[sym].append(float(k[4]))
                highs[sym].append(float(k[2]))
                lows[sym].append(float(k[3]))
                volumes[sym].append(float(k[5]))
        except Exception as e:
            logger.error(f"Error loading history for {sym}: {e}")
    logger.info("Historical data loaded.")

def recover_positions():
    for sym in CONFIG["SYMBOLS"]:
        asset = sym.replace("EUR", "")
        try:
            bal = client.get_asset_balance(asset=asset)
            qty = float(bal["free"])
            ticker = client.get_symbol_ticker(symbol=sym)
            price = float(ticker["price"])
            if qty * price > 10.0:
                positions[sym] = {"entry": price, "qty": qty, "highest": price, "tp": price * 1.02, "sl": price * 0.95, "buy_time": datetime.now().isoformat()}
                logger.info(f"Recovered position: {sym} ({qty} @ {price}EUR = {qty*price:.2f}EUR)")
        except:
            pass

def process_socket_msg(msg):
    global consecutive_losses, paused_until

    if "data" not in msg or "e" not in msg["data"]:
        return
    event = msg["data"]

    mission = get_daily_mission()

    if event["e"] == "kline":
        k = event["k"]
        symbol = event["s"]
        price = float(k["c"])
        high = float(k["h"])
        low = float(k["l"])
        is_closed = k["x"]
        vol = float(k["v"])

        if symbol not in CONFIG["SYMBOLS"]:
            return

        if symbol in positions:
            pos = positions[symbol]
            entry = pos["entry"]
            qty = pos["qty"]
            tp = pos.get("tp", entry * 1.02)
            sl = pos.get("sl", entry * 0.95)
            highest = max(pos.get("highest", entry), price)
            pos["highest"] = highest
            pnl = (price - entry) / entry

            take_profit = price >= tp or (pnl > 0.005 and price < highest * CONFIG["TP_TRAILING_FACTOR"])
            stop_loss = price <= sl

            if take_profit or stop_loss:
                reason = "PROFIT" if take_profit else "STOP"
                try:
                    asset = symbol.replace("EUR", "")
                    actual_bal = client.get_asset_balance(asset=asset)
                    actual_qty = float(actual_bal["free"])
                    step = get_step_size(symbol)
                    sell_qty = round_step(actual_qty, step)
                    if sell_qty > 0:
                        sell_price = round(price * 0.999, 2)
                        order = client.create_order(symbol=symbol, side="SELL", type="LIMIT", timeInForce="GTC", quantity=sell_qty, price=sell_price)
                        time.sleep(3)
                        order_status = client.get_order(symbol=symbol, orderId=order["orderId"])
                        if order_status["status"] != "FILLED":
                            client.cancel_order(symbol=symbol, orderId=order["orderId"])
                            order = client.create_order(symbol=symbol, side="SELL", type="MARKET", quantity=sell_qty)
                        fills = order.get("fills", [])
                        if fills:
                            sell_qty_fill = sum(float(f["qty"]) for f in fills)
                            sell_avg = sum(float(f["price"]) * float(f["qty"]) for f in fills) / sell_qty_fill
                        else:
                            sell_avg = price
                            sell_qty_fill = qty
                        gross_pnl = (sell_avg - entry) * sell_qty_fill
                        fees = (entry * qty + sell_avg * sell_qty_fill) * 0.00075
                        real_pnl = gross_pnl - fees
                        mission = update_daily_mission(real_pnl)
                        logger.info(f"{reason} {symbol} | PnL: {real_pnl:+.2f}EUR | Session: {mission['profit_today']:.2f}/{mission['target_eur']:.2f}EUR")
                        if real_pnl >= 0:
                            consecutive_losses = 0
                        else:
                            consecutive_losses += 1
                            if consecutive_losses >= 3:
                                paused_until = time.time() + 1800
                                logger.critical(f"CIRCUIT BREAKER: 3 consecutive losses. Paused 30 min.")
                                consecutive_losses = 0
                        if real_pnl > 0:
                            add_to_vault(real_pnl * CONFIG["VAULT_PERCENT"])
                        try:
                            db.save_trade(bot_name="SniperSquad", symbol=symbol, side="LONG", entry_price=entry, exit_price=sell_avg, quantity=sell_qty_fill, entry_time=pos["buy_time"], exit_time=datetime.now().isoformat(), gross_pnl=round(gross_pnl, 2), fees=round(fees, 2), net_pnl=round(real_pnl, 2), reason=reason)
                        except Exception as e:
                            logger.error(f"DB record error: {e}")
                    del positions[symbol]
                except Exception as e:
                    logger.error(f"Exit error {symbol}: {e}")

        if is_closed:
            klines[symbol].append(price)
            highs[symbol].append(high)
            lows[symbol].append(low)
            volumes[symbol].append(vol)

            if len(klines[symbol]) >= 20:
                rsi = calc_rsi(klines[symbol], 14)
                ema9 = calc_ema(klines[symbol], 9)
                atr = calc_atr(highs[symbol], lows[symbol], klines[symbol], 14)

                if mission["achieved"]:
                    return

                btc_trend = get_btc_trend()
                if btc_trend == "BEARISH":
                    return

                cond_rsi = CONFIG["RSI_BUY_MIN"] < rsi < CONFIG["RSI_BUY_MAX"]
                cond_oversold = rsi < CONFIG["RSI_OVERSOLD"]
                cond_ema = price > ema9 * 0.998
                avg_vol = sum(volumes[symbol]) / len(volumes[symbol]) if volumes[symbol] else 0
                cond_vol = vol > avg_vol * 1.1 if avg_vol > 0 else True
                score = sum([cond_rsi, cond_oversold, cond_ema, cond_vol])

                if score >= 2 and symbol not in positions and len(positions) < CONFIG["MAX_CONCURRENT_TRADES"]:
                    try:
                        available_eur = float(client.get_asset_balance(asset="EUR")["free"])
                        usable_eur = available_eur - get_vault_locked()
                        trade_amount = min(CONFIG["MAX_TRADE_EUR"], usable_eur)
                        if trade_amount < CONFIG["MIN_TRADE_EUR"]:
                            return

                        cancel_stale_orders(symbol)

                        step = get_step_size(symbol)
                        qty = round_step(trade_amount / price, step)
                        if qty <= 0:
                            return

                        tp_price = price + (atr * CONFIG["ATR_TP_MULT"])
                        sl_price = price - (atr * CONFIG["ATR_SL_MULT"])

                        limit_price = round(price * 0.999, 2)
                        logger.info(f"BUY {symbol} @ {price:.4f}EUR | RSI:{rsi:.1f} Score:{score}/4 | ATR:{atr:.4f} | TP:{tp_price:.4f} SL:{sl_price:.4f}")

                        order = client.create_order(symbol=symbol, side="BUY", type="LIMIT", timeInForce="GTC", quantity=qty, price=limit_price)
                        time.sleep(CONFIG["LIMIT_ORDER_TIMEOUT"])
                        order_status = client.get_order(symbol=symbol, orderId=order["orderId"])

                        if order_status["status"] != "FILLED":
                            client.cancel_order(symbol=symbol, orderId=order["orderId"])
                            logger.info(f"LIMIT order {symbol} not filled in {CONFIG['LIMIT_ORDER_TIMEOUT']}s. Adapting to market...")
                            latest_ticker = client.get_symbol_ticker(symbol=symbol)
                            latest_price = float(latest_ticker["price"])
                            new_limit = round(latest_price * 0.999, 2)
                            new_qty = round_step(trade_amount / latest_price, step)
                            if new_qty > 0:
                                order = client.create_order(symbol=symbol, side="BUY", type="LIMIT", timeInForce="GTC", quantity=new_qty, price=new_limit)
                                time.sleep(15)
                                order_status = client.get_order(symbol=symbol, orderId=order["orderId"])

                        if order_status["status"] == "FILLED":
                            fills = order.get("fills", [])
                            if fills:
                                exec_qty = sum(float(f["qty"]) for f in fills)
                                avg_price = sum(float(f["price"]) * float(f["qty"]) for f in fills) / exec_qty
                            else:
                                avg_price = price
                                exec_qty = qty
                            final_tp = avg_price + (atr * CONFIG["ATR_TP_MULT"])
                            final_sl = avg_price - (atr * CONFIG["ATR_SL_MULT"])
                            positions[symbol] = {"entry": avg_price, "qty": exec_qty, "highest": avg_price, "tp": final_tp, "sl": final_sl, "buy_time": datetime.now().isoformat()}
                            logger.info(f"POSITION OPEN {symbol} | Qty:{exec_qty:.6f} @ {avg_price:.4f}EUR | TP:{final_tp:.4f} SL:{final_sl:.4f}")
                        else:
                            client.cancel_order(symbol=symbol, orderId=order["orderId"])
                            logger.info(f"SKIP {symbol}: LIMIT order not filled after 2nd attempt")
                    except Exception as e:
                        logger.error(f"Entry error {symbol}: {e}")

def cleanup_all_orders():
    for sym in CONFIG["SYMBOLS"]:
        try:
            cancel_stale_orders(sym)
        except:
            pass

def main():
    global paused_until

    logger.info("SNIPER SQUAD v4 (Fixed) avviata")
    cleanup_all_orders()

    m = get_daily_mission()
    logger.info(f"Daily target: {m['target_eur']:.2f}EUR | Session PnL: {m['profit_today']:.2f}EUR")

    init_historical_data()
    recover_positions()

    twm = ThreadedWebsocketManager(api_key=API_KEY, api_secret=API_SECRET)
    twm.start()
    streams = [f"{s.lower()}@kline_1m" for s in CONFIG["SYMBOLS"]]
    twm.start_multiplex_socket(callback=process_socket_msg, streams=streams)

    try:
        while True:
            if time.time() < paused_until:
                logger.warning(f"Trading paused until {datetime.fromtimestamp(paused_until).strftime('%H:%M:%S')}")
                time.sleep(60)
                continue
            get_daily_mission()
            time.sleep(60)
            logger.info(f"Heartbeat | Positions: {len(positions)} | EUR free: {client.get_asset_balance(asset='EUR')['free']}")
            gc.collect()
    except KeyboardInterrupt:
        logger.info("Stopping Sniper Squad...")
        twm.stop()
    except Exception as e:
        logger.critical(f"Main loop crash: {e}")
        twm.stop()

if __name__ == "__main__":
    main()