#!/usr/bin/env python3
"""
TEMPEST v1 — Momentum Hunter
Machine: MARCODG1 (87.106.222.123)
Strategy: RSI(7) + volume breakout scalping on SOL/EUR, ADA/EUR.
Quick entries, 0.6% TP, 0.3% SL, trailing stop. 30-60 trades/day.
"""
import asyncio, json, time, math
from pathlib import Path
from core import BotEngine

BASE = Path(__file__).parent
MIN_NOTIONAL = 5.0
FEE = 0.00075

PAIRS = {
    "SOL/EUR": {"asset": "SOL", "min_size": 0.1, "tp": 0.006, "sl": 0.003, "max_eur": 12, "decimals": 3},
    "ADA/EUR": {"asset": "ADA", "min_size": 5, "tp": 0.006, "sl": 0.003, "max_eur": 8, "decimals": 0},
}

class Tempest(BotEngine):
    def __init__(self):
        super().__init__("Tempest", "TEMPEST")
        self.setup_logging()
        self.positions = {}  # symbol -> {side, entry, tp, sl, oid, trail_peak, trail_active, state}
        self.total_profit = 0.0
        self.fills = 0
        for s in PAIRS:
            self.positions[s] = {"side": None, "entry": 0, "tp": 0, "sl": 0,
                                 "oid": None, "trail_peak": 0, "trail_active": False,
                                 "state": "idle"}
        self._load_state()

    def _load_state(self):
        s = self.db.get_state("tempest_state")
        if s:
            self.total_profit = s.get("profit", 0)
            self.fills = s.get("fills", 0)
            self.logger.info(f"State: PnL={self.total_profit:.4f} fills={self.fills}")

    def _save(self):
        self.db.set_state("tempest_state", {"profit": self.total_profit, "fills": self.fills})

    async def get_signal(self, symbol):
        ohlcv = await self.ohlcv(symbol, "1m", 30)
        if len(ohlcv) < 21: return None
        closes = [c[4] for c in ohlcv]
        vols = [c[5] for c in ohlcv]
        r7 = self.rsi(closes, 7)
        avg_vol = sum(vols) / len(vols)
        recent_vol = sum(vols[-3:]) / 3
        vol_ratio = recent_vol / max(avg_vol, 0.001)
        price = closes[-1]
        ema21 = self.ema(closes, 21)

        # Oversold bounce (BUY)
        if r7 < 30 and vol_ratio > 1.3 and price < ema21 * 1.02:
            return {"side": "buy", "confidence": min(1.0, (30 - r7) / 15 + (vol_ratio - 1) / 2),
                    "price": price, "rsi": r7, "vol": vol_ratio}

        # Overbought rejection (SELL)
        if r7 > 70 and vol_ratio > 1.3 and price > ema21 * 0.98:
            return {"side": "sell", "confidence": min(1.0, (r7 - 70) / 15 + (vol_ratio - 1) / 2),
                    "price": price, "rsi": r7, "vol": vol_ratio}

        # Momentum continuation (BUY) — RSI crossing up through 50 + volume
        if 48 <= r7 <= 55 and vol_ratio > 1.5 and price > ema21:
            return {"side": "buy", "confidence": 0.6, "price": price, "rsi": r7, "vol": vol_ratio}

        # Momentum continuation (SELL) — RSI crossing down through 50 + volume
        if 45 <= r7 <= 52 and vol_ratio > 1.5 and price < ema21:
            return {"side": "sell", "confidence": 0.6, "price": price, "rsi": r7, "vol": vol_ratio}

        return None

    async def manage_position(self, symbol, price):
        pos = self.positions[symbol]
        cfg = PAIRS[symbol]
        oid = pos["oid"]

        if oid is None:
            if pos["state"] == "entering":
                pos["state"] = "idle"
            return

        open_ids = await self.open_ids(symbol)
        filled = await self.filled_ids(symbol, 10)

        if oid not in open_ids:
            if oid in filled:
                self.fills += 1
                if pos["side"] == "buy":
                    tp = round(price * (1 + cfg["tp"]), cfg["decimals"])
                    sl = round(price * (1 - cfg["sl"]), cfg["decimals"])
                    # place take profit
                    bal = await self.bal(cfg["asset"])
                    amt = round(min(bal * 0.99, pos.get("amount", 0)), cfg["decimals"])
                    if amt * tp >= MIN_NOTIONAL:
                        toid = await self.place_sell(symbol, amt, tp)
                        self.logger.info(f"  TP SELL {amt} {cfg['asset']} @ {tp}")
                        pos["tp"] = tp
                        pos["oid"] = toid
                        pos["state"] = "tp_placed"
                        # also place SL
                        soid = await self.place_sell(symbol, amt, sl)
                        self.logger.info(f"  SL SELL {amt} {cfg['asset']} @ {sl}")
                elif pos["side"] == "sell":
                    tp = round(price * (1 - cfg["tp"]), cfg["decimals"])
                    sl = round(price * (1 + cfg["sl"]), cfg["decimals"])
                    bal = await self.bal("EUR")
                    size = min(cfg["max_eur"], bal * 0.8)
                    amt = round(size / tp, cfg["decimals"])
                    if amt * tp >= MIN_NOTIONAL:
                        toid = await self.place_buy(symbol, amt, tp)
                        self.logger.info(f"  TP BUY {amt} {cfg['asset']} @ {tp}")
                        pos["tp"] = tp
                        pos["oid"] = toid
                        pos["state"] = "tp_placed"
                pos["entry"] = price
                self._save()
            else:
                pos["oid"] = None
                pos["state"] = "idle"
                self.logger.info(f"  Order canceled/expired for {symbol}")

    async def check_tp_sl(self, symbol, price):
        pos = self.positions[symbol]
        cfg = PAIRS[symbol]
        if pos["state"] != "tp_placed": return

        open_ids = await self.open_ids(symbol)
        filled = await self.filled_ids(symbol, 10)

        if pos["oid"] and pos["oid"] not in open_ids:
            if pos["oid"] in filled:
                profit_pct = cfg["tp"] if pos["side"] == "buy" else cfg["tp"]
                profit_eur = profit_pct * cfg["max_eur"]
                fee_eur = cfg["max_eur"] * FEE * 2
                net = profit_eur - fee_eur
                self.total_profit += net
                self.fills += 1
                self.db.save_trade(symbol, pos["side"], pos["entry"], 0, cfg["max_eur"], fee_eur, net, "tempest")
                self.logger.info(f"  ✅ {symbol} {pos['side']} filled | net={net:.4f} | total={self.total_profit:.4f}")
                self._save()
                pos["state"] = "idle"
                pos["oid"] = None
                pos["side"] = None
            else:
                pos["oid"] = None
                pos["state"] = "idle"

    async def enter_position(self, symbol, signal):
        cfg = PAIRS[symbol]
        pos = self.positions[symbol]
        if pos["state"] != "idle": return

        if signal["side"] == "buy":
            bal = await self.bal("EUR")
            size = min(cfg["max_eur"], bal * 0.8)
            if size < MIN_NOTIONAL: return
            amt = round(size / signal["price"], cfg["decimals"])
            if amt * signal["price"] < MIN_NOTIONAL: return
            oid = await self.place_buy(symbol, amt, signal["price"])
            if oid:
                pos["side"] = "buy"
                pos["oid"] = oid
                pos["state"] = "entering"
                pos["amount"] = amt
                pos["entry"] = signal["price"]
                self.logger.info(f"  🟢 BUY {amt} {cfg['asset']} @ {signal['price']} (RSI={signal.get('rsi',0):.0f} vol={signal.get('vol',0):.1f}x)")

        elif signal["side"] == "sell":
            bal = await self.bal(cfg["asset"])
            amt = round(bal * 0.8, cfg["decimals"])
            if amt < cfg["min_size"]: return
            amt = round(min(amt, cfg["max_eur"] / signal["price"]), cfg["decimals"])
            if amt * signal["price"] < MIN_NOTIONAL: return
            oid = await self.place_sell(symbol, amt, signal["price"])
            if oid:
                pos["side"] = "sell"
                pos["oid"] = oid
                pos["state"] = "entering"
                pos["amount"] = amt
                pos["entry"] = signal["price"]
                self.logger.info(f"  🔴 SELL {amt} {cfg['asset']} @ {signal['price']} (RSI={signal.get('rsi',0):.0f} vol={signal.get('vol',0):.1f}x)")

    async def run(self):
        bal = await self.connect()
        self.logger.info(f"TEMPEST — Momentum hunter")
        self.logger.info(f"Start: PnL={self.total_profit:.4f} fills={self.fills}")

        pairs_list = list(PAIRS.keys())

        while self.running:
            try:
                signals = []
                for s in pairs_list:
                    sig = await self.get_signal(s)
                    if sig: signals.append((s, sig))

                for s in pairs_list:
                    p = await self.price(s)
                    if p <= 0: continue
                    await self.manage_position(s, p)
                    await self.check_tp_sl(s, p)
                    pos = self.positions[s]
                    if pos["state"] == "idle":
                        for sym, sig in signals:
                            if sym == s and sig["confidence"] >= 0.55:
                                await self.enter_position(s, sig)
                                break

                if int(time.time()) % 15 < 2:
                    parts = []
                    for sym in pairs_list:
                        pos = self.positions[sym]
                        st = pos["state"]
                        if st == "idle": st = "🟢"
                        elif st == "entering": st = "⏳"
                        elif st == "tp_placed": st = "🎯"
                        parts.append(f"{PAIRS[sym]['asset']}={st}")
                    self.logger.info(f"{' | '.join(parts)} | PnL={self.total_profit:.4f} fills={self.fills}")

                if int(time.time()) % 60 < 2:
                    self._save()

                await asyncio.sleep(3)
            except Exception as e:
                self.logger.error(f"Loop: {e}", exc_info=True)
                await asyncio.sleep(5)

if __name__ == "__main__":
    b = Tempest()
    try: asyncio.run(b.run())
    except KeyboardInterrupt:
        b.running = False
        asyncio.run(b.close())