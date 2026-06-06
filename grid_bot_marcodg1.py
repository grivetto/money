#!/usr/bin/env python3
"""
DENARO GRID BOT V2 - MARCODG1
ADAEUR spot grid bot - cancels and re-places orders each cycle (full refresh)
Simple, reliable, and self-correcting.
"""
import os, sys, time, json, hmac, hashlib, urllib.parse, logging, requests
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path("/home/marco/denaro")
load_dotenv(BASE_DIR / ".env")
BINANCE_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_SECRET = os.getenv("BINANCE_API_SECRET", "")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - GRID-MDG1 - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(BASE_DIR / "grid_marcodg1.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("GridBotMDG1")

def load_config():
    path = BASE_DIR / "grid_config.json"
    with open(path) as f:
        return json.load(f)

CONFIG = load_config()
SYMBOL = CONFIG["symbol"]  # ADAEUR
INTERVAL = CONFIG.get("rebalance_interval_sec", 180)

def api(method, path, params=None):
    """Signed request to Binance API"""
    if params is None: params = {}
    ts = int(time.time() * 1000)
    params["timestamp"] = ts
    params["recvWindow"] = 10000
    qs = urllib.parse.urlencode(sorted(params.items()))
    sig = hmac.new(BINANCE_SECRET.encode(), qs.encode(), hashlib.sha256).hexdigest()
    url = f"https://api1.binance.com{path}?{qs}&signature={sig}"
    headers = {"X-MBX-APIKEY": BINANCE_KEY}
    try:
        if method == "POST":
            r = requests.post(url, headers=headers, timeout=10)
        elif method == "DELETE":
            r = requests.delete(url, headers=headers, timeout=10)
        else:
            r = requests.get(url, headers=headers, timeout=10)
        return r.json()
    except Exception as e:
        log.error(f"API error ({path[:40]}): {e}")
        return None

def get_price():
    try:
        r = requests.get(f"https://api1.binance.com/api/v3/ticker/price?symbol={SYMBOL}", timeout=10)
        return float(r.json()["price"])
    except:
        return None

def round_qty(qty):
    """ADA step size = 0.1"""
    return max(0.1, round(qty * 10) / 10)

def round_price(p):
    """ADA price tick = 0.0001"""
    return round(p, 4)

def grid_tick():
    """One grid cycle: cancel all -> recalc -> place new orders"""
    price = get_price()
    if not price or price <= 0:
        log.error("Cannot get price, skipping cycle")
        return

    cfg = load_config()
    grid_levels = cfg["grid_levels"]
    range_pct = cfg["grid_range_pct"]
    base_eur = cfg["base_order_eur"]
    max_invested = cfg["max_total_invested"]
    martingale = cfg["martingale_factor"]
    min_order_eur = cfg.get("min_order_eur", 5.0)

    # 1. Cancel ALL existing ADAEUR orders
    orders = api("GET", "/api/v3/openOrders", {"symbol": SYMBOL})
    if orders is None:
        return
    if orders:
        for o in orders:
            api("DELETE", "/api/v3/order", {"symbol": SYMBOL, "orderId": o["orderId"]})
            time.sleep(0.1)
        log.info(f"Cancellati {len(orders)} ordini preesistenti")
        time.sleep(0.5)

    # Wait a moment for cancellations to clear
    time.sleep(0.5)

    # 2. Get current balances
    acct = api("GET", "/api/v3/account")
    if not acct:
        return
    bal = {}
    for b in acct.get("balances", []):
        bal[b["asset"]] = {"free": float(b["free"]), "locked": float(b["locked"])}

    eur_free = bal.get("EUR", {}).get("free", 0)
    ada_free = bal.get("ADA", {}).get("free", 0)

    log.info(f"ADAEUR @ {price}€ | EUR free: {eur_free:.2f}€ | ADA free: {ada_free:.4f}")

    # 3. Place BUY orders below price
    buy_put = 0
    total_buy_eur = 0
    for i in range(grid_levels):
        level_pct = ((i + 1) / grid_levels) * range_pct
        level_price = round_price(price * (1 - level_pct))
        if level_price >= price:
            continue
        # Martingale sizing
        order_eur = min(base_eur * (martingale ** i), max_invested - total_buy_eur)
        remaining = max_invested - total_buy_eur
        if remaining < min_order_eur:
            break
        order_eur = min(order_eur, remaining)
        if order_eur < min_order_eur:
            continue
        qty = round_qty(order_eur / level_price)
        if qty * level_price < min_order_eur:
            qty = round_qty(min_order_eur / level_price)
        if qty * level_price > eur_free:
            log.warning(f"Fondi insufficienti per BUY {qty} ADA @ {level_price}")
            continue
        if qty <= 0:
            continue
        r = api("POST", "/api/v3/order", {
            "symbol": SYMBOL, "side": "BUY", "type": "LIMIT",
            "timeInForce": "GTC", "quantity": str(qty), "price": str(level_price)
        })
        if r and "orderId" in r:
            dv = round(qty * level_price, 2)
            pct = round((level_price / price - 1) * 100, 2)
            log.info(f"✅ BUY {qty} ADA @ {level_price}€ = {dv}€ ({pct:+.2f}%)")
            buy_put += 1
            total_buy_eur += dv
            eur_free -= dv
            time.sleep(0.3)
        elif r:
            log.error(f"BUY failed: {r.get('msg', r)}")

    # 4. Place SELL orders above price (using ADA we hold)
    if ada_free >= 0.2:  # need at least 0.2 ADA to bother
        # Split ADA across grid levels
        ada_per_sell = round_qty(ada_free / grid_levels)
        if ada_per_sell >= 0.1:
            for i in range(grid_levels):
                level_pct = ((i + 1) / grid_levels) * range_pct
                level_price = round_price(price * (1 + level_pct))
                if level_price <= price:
                    continue
                qty = round_qty(ada_per_sell)
                if qty <= 0:
                    continue
                r = api("POST", "/api/v3/order", {
                    "symbol": SYMBOL, "side": "SELL", "type": "LIMIT",
                    "timeInForce": "GTC", "quantity": str(qty), "price": str(level_price)
                })
                if r and "orderId" in r:
                    dv = round(qty * level_price, 2)
                    pct = round((level_price / price - 1) * 100, 2)
                    log.info(f"✅ SELL {qty} ADA @ {level_price}€ = {dv}€ ({pct:+.2f}%)")
                    time.sleep(0.3)
                elif r:
                    log.error(f"SELL failed: {r.get('msg', r)}")

    # 5. Final check
    final_orders = api("GET", "/api/v3/openOrders", {"symbol": SYMBOL})
    n = len(final_orders) if final_orders else 0
    log.info(f"📊 Grid attiva: {n} ordini ADAEUR")

    # 6. Save state for collector
    state = {
        "timestamp": datetime.now().isoformat(),
        "price": price,
        "orders": n,
        "eur_free": round(bal.get("EUR", {}).get("free", 0), 2),
        "ada_free": round(ada_free, 4),
        "total_buy_eur": round(total_buy_eur, 2)
    }
    with open(BASE_DIR / "grid_state.json", "w") as f:
        json.dump(state, f)

if __name__ == "__main__":
    log.info("=" * 50)
    log.info(f"🟢 GRID BOT MARCODG1 V2 | {SYMBOL}")
    log.info(f"   Livelli: {CONFIG['grid_levels']} | Range: ±{CONFIG['grid_range_pct']*100}%")
    log.info(f"   Base: {CONFIG['base_order_eur']}€ | Max: {CONFIG['max_total_invested']}€")
    log.info(f"   Loop: ogni {INTERVAL}s")

    cycle = 0
    while True:
        try:
            cycle += 1
            grid_tick()
            log.info(f"⏳ Cycle #{cycle} done, next in {INTERVAL}s...")
            time.sleep(INTERVAL)
        except KeyboardInterrupt:
            log.info("⏹ Grid bot fermato")
            break
        except Exception as e:
            log.error(f"❌ Errore ciclo #{cycle}: {e}")
            import traceback
            traceback.print_exc()
            time.sleep(60)
