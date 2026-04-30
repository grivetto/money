#!/usr/bin/env python3
"""
MOMENTUM BOT - PAPER TRADING
Simulazione di trading su Binance con strategia momentum su meme coins.
Nessun ordine reale viene inviato. Tutto è loggato.
"""

import os
import sys
import time
import json
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import List, Optional, Dict

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/home/sergio/denaro/momentum_paper.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('MomentumPaperBot')

@dataclass
class TradeSignal:
    symbol: str
    side: str
    entry_price: float
    stop_loss: float
    take_profit: float
    quantity: float
    reason: str
    confidence: float
    timestamp: datetime

@dataclass
class VirtualPosition:
    symbol: str
    side: str
    entry_price: float
    current_price: float
    quantity: float
    stop_loss: float
    take_profit: float
    trailing_stop: Optional[float]
    entry_time: datetime
    max_price: float

class MomentumPaperBot:
    def __init__(self, capital: float = 200.0):
        self.initial_capital = capital
        self.capital = capital
        self.risk_per_trade = 0.10
        self.max_positions = 3
        self.positions: Dict[str, VirtualPosition] = {}
        self.trade_history: List[TradeSignal] = []
        self.running = False

        # Public API Binance (nessuna chiave per dati pubblici)
        import ccxt
        self.exchange = ccxt.binance({
            'enableRateLimit': True,
            'options': {'defaultType': 'spot'}
        })

        # Watchlist meme coins volatili
        self.watchlist = ['DOGE/USDT', 'SHIB/USDT', 'PEPE/USDT', 'FLOKI/USDT', 'BONK/USDT', 'WIF/USDT']

        logger.info(f"BOT INIZIALIZZATO - Capitale virtuale: {self.capital:.2f} USDT")

    def fetch_ohlcv(self, symbol: str, timeframe: str = '3m', limit: int = 50):
        try:
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            candles = []
            for c in ohlcv:
                candles.append({
                    'timestamp': datetime.fromtimestamp(c[0]/1000),
                    'open': c[1], 'high': c[2], 'low': c[3], 'close': c[4], 'volume': c[5]
                })
            return candles
        except Exception as e:
            logger.error(f"Errore fetch {symbol}: {e}")
            return []

    def calculate_ma(self, closes: List[float], period: int) -> float:
        if len(closes) < period:
            return 0.0
        return sum(closes[-period:]) / period

    def calculate_avg_volume(self, volumes: List[float], period: int) -> float:
        if len(volumes) < period:
            return 0.0
        return sum(volumes[-period:]) / period

    def scan(self) -> List[TradeSignal]:
        signals = []
        logger.info("SCANNING mercato...")

        for symbol in self.watchlist:
            candles = self.fetch_ohlcv(symbol, '5m', 50)
            if len(candles) < 25:
                continue

            current = candles[-1]
            prev = candles[-2]
            closes = [c['close'] for c in candles]
            volumes = [c['volume'] for c in candles]

            ma20 = self.calculate_ma(closes, 10)
            prev_ma20 = self.calculate_ma(closes[:-1], 10)

            vol_avg = self.calculate_avg_volume(volumes, 12)
            volume_surge = current['volume'] > vol_avg * 5.0

            price_cross = (current['close'] > ma20) and (prev['close'] <= prev_ma20)

            if price_cross and volume_surge:
                entry = current['close']
                qty = self.position_size(entry)
                if qty <= 0:
                    continue

                signal = TradeSignal(
                    symbol=symbol,
                    side='BUY',
                    entry_price=entry,
                    stop_loss=entry * 0.975,
                    take_profit=entry * 1.012,
                    quantity=qty,
                    reason=f"MA20 cross + Vol x{current['volume']/vol_avg:.1f}",
                    confidence=0.8,
                    timestamp=datetime.now()
                )
                signals.append(signal)
                logger.info(f"SEGNALE: {symbol} BUY @ {entry:.6f} | qty={qty:.4f} | Vol x{current['volume']/vol_avg:.1f}")

        return signals

    def position_size(self, entry_price: float) -> float:
        risk_amount = self.capital * self.risk_per_trade
        stop_distance_pct = 0.025
        quantity = risk_amount / (entry_price * stop_distance_pct)
        return round(quantity, 4)

    def execute_buy(self, signal: TradeSignal) -> bool:
        if len(self.positions) >= self.max_positions:
            logger.warning("MAX POSIZIONI raggiunto")
            return False
        if self.capital < signal.quantity * signal.entry_price:
            logger.warning("Capitale insufficiente")
            return False

        costo = signal.quantity * signal.entry_price
        self.capital -= costo

        pos = VirtualPosition(
            symbol=signal.symbol,
            side='LONG',
            entry_price=signal.entry_price,
            current_price=signal.entry_price,
            quantity=signal.quantity,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            trailing_stop=None,
            entry_time=datetime.now(),
            max_price=signal.entry_price
        )
        self.positions[signal.symbol] = pos
        self.trade_history.append(signal)
        logger.info(f"EXEC: ACQUISTO {signal.symbol} qty={signal.quantity} @ {signal.entry_price:.6f} | Capitale residuo: {self.capital:.2f}")
        return True

    def update_positions(self):
        if not self.positions:
            return

        for symbol, pos in list(self.positions.items()):
            try:
                candles = self.fetch_ohlcv(symbol, '5m', 1)
                if not candles:
                    continue
                current_price = candles[-1]['close']
                pos.current_price = current_price

                if current_price > pos.max_price:
                    pos.max_price = current_price

                unrealized_pct = (current_price - pos.entry_price) / pos.entry_price

                if unrealized_pct >= 0.05:
                    new_trailing = pos.entry_price * 1.003
                    if pos.trailing_stop is None:
                        pos.trailing_stop = new_trailing
                        logger.info(f"TRAILING ATTIVATO: {symbol} SL={new_trailing:.6f}")
                    else:
                        trail_candidate = pos.max_price * 0.997
                        if trail_candidate > pos.trailing_stop:
                            pos.trailing_stop = trail_candidate

                exit_reason = None
                if pos.trailing_stop and current_price <= pos.trailing_stop:
                    exit_reason = f"Trailing stop {pos.trailing_stop:.6f}"
                elif current_price <= pos.stop_loss:
                    exit_reason = f"Stop loss {pos.stop_loss:.6f}"
                elif current_price >= pos.take_profit:
                    exit_reason = f"Take profit {pos.take_profit:.6f}"

                if exit_reason:
                    self.close_position(symbol, current_price, exit_reason)
            except Exception as e:
                logger.error(f"Errore update {symbol}: {e}")

    def close_position(self, symbol: str, exit_price: float, reason: str):
        pos = self.positions[symbol]
        pnl = (exit_price - pos.entry_price) * pos.quantity
        self.capital += pos.quantity * exit_price
        pnl_pct = ((exit_price - pos.entry_price) / pos.entry_price) * 100
        logger.info(f"CHIUSURA: {symbol} | PnL: {pnl:.2f} USDT ({pnl_pct:.2f}%) | Motivo: {reason}")
        del self.positions[symbol]

    def kill_switch(self):
        drawdown = (self.initial_capital - self.capital) / self.initial_capital
        if drawdown >= 0.04:
            logger.error(f"KILL SWITCH: Drawdown {drawdown*100:.1f}% > 4%")
            return True
        return False

    def run(self):
        self.running = True
        cycle = 0
        logger.info("=== MOMENTUM PAPER BOT AVVIATO (Simulazione) ===")
        logger.info(f"Watchlist: {self.watchlist}")
        logger.info(f"Risk per trade: {self.risk_per_trade*100}% | Kill switch: 4% drawdown")

        while self.running:
            cycle += 1
            logger.info(f"\n--- Ciclo {cycle} | Capitale: {self.capital:.2f} USDT | Posizioni: {len(self.positions)} ---")

            signals = self.scan()
            if signals:
                best = max(signals, key=lambda s: s.confidence)
                self.execute_buy(best)

            if self.positions:
                self.update_positions()

            if self.kill_switch():
                self.running = False
                break

            if self.positions:
                for sym, pos in self.positions.items():
                    unreal = (pos.current_price - pos.entry_price) * pos.quantity
                    logger.info(f"POS: {sym} | Unrealized: {unreal:+.2f} USDT")

            time.sleep(300)  # 5 min

        logger.info(f"Bot terminato. Capitale finale: {self.capital:.2f} USDT | PnL: {(self.capital-self.initial_capital):+.2f}")

    def stop(self):
        self.running = False

if __name__ == '__main__':
    try:
        bot = MomentumPaperBot(capital=200.0)
        bot.run()
    except KeyboardInterrupt:
        logger.info("Interrotto manualmente")
        bot.stop()
