"""
Flash Crash Hunter v1 — Denaro Squadra
Monitora i prezzi in tempo reale, quando rileva un crollo >3% in 5 minuti
compra al bottom e rivende sul rimbalzo.

Ispirato a Michael Ionta — price action + risk management
"""
import ccxt, asyncio, time, logging, json, os, sys
from pathlib import Path
from datetime import datetime, timezone

BASE_DIR = Path(__file__).parent.parent
LOG_FILE = BASE_DIR / "flash_crash.log"
STATE_FILE = BASE_DIR / ".flash_crash_state.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | FlashCrash | %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
)
log = logging.getLogger("FlashCrashHunter")


class FlashCrashHunter:
    def __init__(self, exchange):
        self.ex = exchange
        self.symbols = ["SOL/USDC", "ADA/USDC"]
        self.price_buffer = {s: [] for s in self.symbols}
        self.max_buffer = 20
        self.crash_threshold_pct = 1.0
        self.bounce_threshold_pct = 0.5
        self.capital_pct = 0.50
        self.trade_cooldown = 300
        self.last_trade_time = 0
        self.state = self._load_state()

    def _load_state(self):
        if STATE_FILE.exists():
            try:
                with open(STATE_FILE) as f:
                    return json.load(f)
            except: pass
        return {"in_position": False, "entry_price": 0, "symbol": "", "amount": 0}

    def _save_state(self):
        with open(STATE_FILE, "w") as f:
            json.dump(self.state, f)

    async def scan(self):
        for symbol in self.symbols:
            try:
                ticker = await self.ex.fetch_ticker(symbol)
                price = ticker["last"]
                self.price_buffer[symbol].append(price)
                if len(self.price_buffer[symbol]) > self.max_buffer:
                    self.price_buffer[symbol].pop(0)
                buf = self.price_buffer[symbol]
                if len(buf) < 5: continue
                recent_avg = sum(buf[-3:]) / 3
                old_avg = sum(buf[:3]) / 3
                change_pct = (recent_avg - old_avg) / old_avg * 100

                if self.state["in_position"] and self.state["symbol"] == symbol:
                    bounce_pct = (price - self.state["entry_price"]) / self.state["entry_price"] * 100
                    if bounce_pct >= self.bounce_threshold_pct:
                        log.info(f"🚀 RIMBALZO {symbol}: +{bounce_pct:.2f}% -> VENDI")
                        await self._sell(symbol)
                    continue

                if change_pct <= -self.crash_threshold_pct:
                    if time.time() - self.last_trade_time < self.trade_cooldown: continue
                    log.warning(f"🔥 CRASH {symbol}: {change_pct:.2f}% -> COMPRO")
                    await self._buy(symbol, price)

            except Exception as e:
                log.error(f"Errore {symbol}: {e}")
            await asyncio.sleep(1)

    async def _buy(self, symbol, price):
        try:
            bal = await self.ex.fetch_balance()
            usdc = bal["free"].get("USDC", 0) * self.capital_pct
            if usdc < 5: return
            amount = round(usdc / price * 0.98, 4)
            if amount <= 0: return
            order = await self.ex.create_order(symbol, "market", "buy", amount)
            filled_qty = float(order.get("filled", amount))
            avg_price = float(order.get("price", price))
            self.state = {"in_position": True, "entry_price": avg_price, "symbol": symbol, "amount": filled_qty, "entry_time": time.time()}
            self._save_state()
            self.last_trade_time = time.time()
            log.info(f"✅ COMPRATO {filled_qty} {symbol} @ ${avg_price:.4f}")
        except Exception as e:
            log.error(f"❌ Buy error: {e}")

    async def _sell(self, symbol):
        try:
            qty = self.state["amount"]
            if qty <= 0: return
            order = await self.ex.create_order(symbol, "market", "sell", qty)
            filled_qty = float(order.get("filled", qty))
            avg_price = float(order.get("price", 0))
            pnl = (avg_price - self.state["entry_price"]) * filled_qty
            log.info(f"✅ VENDUTO {filled_qty} {symbol} @ ${avg_price:.4f} | PnL: ${pnl:.2f}")
            self.state = {"in_position": False, "entry_price": 0, "symbol": "", "amount": 0}
            self._save_state()
        except Exception as e:
            log.error(f"❌ Sell error: {e}")

    async def run(self):
        log.info("🚀 Flash Crash Hunter avviato")
        while True:
            try:
                await self.scan()
            except Exception as e:
                log.error(f"Errore loop: {e}")
            await asyncio.sleep(5)


# === ENTRY POINT per systemd ===
async def main_async():
    import ccxt.async_support as ccxt
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / '.env')

    api_key = os.getenv("BINANCE_API_KEY")
    secret = os.getenv("BINANCE_API_SECRET")
    if not api_key or api_key.startswith("your_"):
        log.warning("API key placeholder - disabilitato")
        return

    ex = ccxt.binance({"apiKey": api_key, "secret": secret, "options": {"defaultType": "spot"}, "enableRateLimit": True})
    await ex.load_markets()
    bot = FlashCrashHunter(ex)
    await bot.run()

if __name__ == "__main__":
    asyncio.run(main_async())
