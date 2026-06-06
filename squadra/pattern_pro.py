"""
Pattern Pro v2 — Predittore multi-timeframe con divergenza RSI/MACD
Ispirato a Michael Ionta — pattern recognition + volume confirmation
"""
import ccxt, asyncio, numpy as np, logging, json, os, time
from pathlib import Path
from collections import deque

BASE_DIR = Path(__file__).parent.parent
LOG_FILE = BASE_DIR / "pattern_pro.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | PatternPro | %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
)
log = logging.getLogger("PatternPro")


def rsi(prices, period=14):
    """Calcola RSI"""
    if len(prices) < period + 1:
        return 50
    deltas = np.diff(np.array(prices[-period - 1:]))
    seed = deltas[:period]
    up = seed[seed >= 0].sum() / period
    down = -seed[seed < 0].sum() / period
    if down == 0:
        return 100
    rs = up / down
    return 100 - 100 / (1 + rs)


def macd(prices, fast=12, slow=26, signal=9):
    """Calcola MACD base"""
    if len(prices) < slow + signal:
        return 0, 0
    ema_fast = np.mean(prices[-fast:])
    ema_slow = np.mean(prices[-slow:])
    macd_line = ema_fast - ema_slow
    return macd_line, 0  # simplified


def detect_hammer(candle):
    o, h, l, c = candle[1], candle[2], candle[3], candle[4]
    body = abs(c - o)
    lower_shadow = min(c, o) - l
    upper_shadow = h - max(c, o)
    return lower_shadow > 2 * body and upper_shadow < body * 0.5


def detect_shooting_star(candle):
    o, h, l, c = candle[1], candle[2], candle[3], candle[4]
    body = abs(c - o)
    upper_shadow = h - max(c, o)
    lower_shadow = min(c, o) - l
    return upper_shadow > 2 * body and lower_shadow < body * 0.5


def detect_engulfing(candles):
    """Bullish or bearish engulfing"""
    if len(candles) < 2:
        return None
    c1, c2 = candles[-2], candles[-1]
    o1, c1_ = c1[1], c1[4]
    o2, c2_ = c2[1], c2[4]
    b1, b2 = abs(c1_ - o1), abs(c2_ - o2)
    if b2 > b1 and o2 < c1_ and c2_ > o1 and c2_ > c1_:
        return "bullish_engulfing"
    if b2 > b1 and o2 > c1_ and c2_ < o1 and c2_ < c1_:
        return "bearish_engulfing"
    return None


def detect_morning_star(candles):
    if len(candles) < 3:
        return False
    c1, c2, c3 = candles[-3], candles[-2], candles[-1]
    b1 = abs(c1[4] - c1[1])  # long bearish
    b2 = abs(c2[4] - c2[1])  # small body
    b3 = abs(c3[4] - c3[1])  # long bullish
    return (c1[4] < c1[1] and b2 < b1 * 0.3 and c3[4] > c3[1] and
            c3[4] > (c1[1] + c1[4]) / 2)


class PatternPro:
    def __init__(self, exchange):
        self.ex = exchange
        self.symbols = ["SOL/USDC"]
        self.last_signals = {}


    async def _execute_signal(self, symbol, direction, price):
        if hasattr(self, "_last_trade_time") and time.time() - self._last_trade_time < 300:
            return
        try:
            base, quote = symbol.split("/")
            bal = await self.ex.fetch_balance()
            free_quote = bal["free"].get(quote, 0)
            free_base = bal["free"].get(base, 0)
            if direction == "BUY":
                amount_quote = min(free_quote * 0.25, 10)
                if amount_quote < 5.8:
                    return
                amount_base = amount_quote / price
                await self.ex.create_order(symbol, "market", "buy", amount_base)
                log.info(f"EXECUTED BUY {amount_base:.4f} {base} @ ~{price:.4f}")
            else:
                amount_base = min(free_base * 0.25, 10 / price)
                if amount_base * price < 5.8:
                    return
                await self.ex.create_order(symbol, "market", "sell", amount_base)
                log.info(f"EXECUTED SELL {amount_base:.4f} {base} @ ~{price:.4f}")
            self._last_trade_time = time.time()
        except Exception as e:
            log.error(f"Signal execution failed: {e}")

    async def scan(self):
        for symbol in self.symbols:
            try:
                # Prendi 3 timeframe
                ohlcv_5m = await self.ex.fetch_ohlcv(symbol, "5m", limit=30)
                ohlcv_15m = await self.ex.fetch_ohlcv(symbol, "15m", limit=30)
                ohlcv_1h = await self.ex.fetch_ohlcv(symbol, "1h", limit=30)

                prices_5m = [c[4] for c in ohlcv_5m]
                prices_15m = [c[4] for c in ohlcv_15m]
                prices_1h = [c[4] for c in ohlcv_1h]

                # RSI su 3 timeframe
                rsi_5m = rsi(prices_5m, 14)
                rsi_15m = rsi(prices_15m, 14)
                rsi_1h = rsi(prices_1h, 14)

                # MACD
                macd_5m, _ = macd(prices_5m)
                macd_15m, _ = macd(prices_15m)

                # Pattern detection (su 5m candles)
                pattern_5m = detect_engulfing(ohlcv_5m) or \
                    ("hammer" if detect_hammer(ohlcv_5m[-1]) else None) or \
                    ("shooting_star" if detect_shooting_star(ohlcv_5m[-1]) else None)
                morning = detect_morning_star(ohlcv_5m)

                # Divergenza: RSI 5m in calo ma prezzo in salita = divergence
                divergence = False
                if len(prices_15m) > 20 and len(prices_5m) > 20:
                    price_trend = prices_15m[-1] > prices_15m[-5] and prices_5m[-1] < prices_5m[-5]
                    rsi_trend = rsi_15m < rsi_5m - 5  # RSI 1h piu' basso di RSI 5m
                    divergence = price_trend and rsi_trend

                # Volume spike (ultimo volume > 2x media 20 periodi)
                volumes = [c[5] for c in ohlcv_5m]
                avg_vol = np.mean(volumes[-20:-1]) if len(volumes) > 20 else 0
                vol_spike = volumes[-1] > avg_vol * 2 if avg_vol > 0 else False

                # Confidence score
                confidence = 0
                direction = None

                if pattern_5m in ("hammer", "bullish_engulfing") or morning:
                    confidence += 0.3
                    direction = "BUY"
                if rsi_5m < 35 and rsi_15m < 40:  # ipervenduto su 2 timeframe
                    confidence += 0.25
                    direction = "BUY"
                if divergence and direction == "BUY":
                    confidence += 0.2
                if vol_spike and direction == "BUY":
                    confidence += 0.15

                if pattern_5m in ("shooting_star", "bearish_engulfing"):
                    confidence += 0.3
                    direction = "SELL"
                if rsi_5m > 65 and rsi_15m > 60:
                    confidence += 0.25
                    direction = "SELL"
                if vol_spike and direction == "SELL":
                    confidence += 0.15

                if confidence >= 0.55 and direction:
                    log.info(f"🔥 SEGNALE {direction} {symbol} (conf={confidence:.2f}) " +
                             f"RSI: 5m={rsi_5m:.0f} 15m={rsi_15m:.0f} 1h={rsi_1h:.0f} " +
                             f"Pattern: {pattern_5m or '—'} Spike: {vol_spike}")
                    self.last_signals[symbol] = {
                        "direction": direction,
                        "confidence": confidence,
                        "time": time.time(),
                        "price": ohlcv_5m[-1][4],
                    }
                    if confidence >= 0.85:
                        await self._execute_signal(symbol, direction, ohlcv_5m[-1][4])

            except Exception as e:
                log.error(f"Errore {symbol}: {e}")

        await asyncio.sleep(60)


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
    bot = PatternPro(ex)
    while True:
        await bot.scan()

if __name__ == "__main__":
    asyncio.run(main_async())  # check ogni minuto
