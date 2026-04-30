#!/usr/bin/env python3
"""
GRID TRADING BOT - PAPER TRADING
Strategia range-bound: compra a ribasso, vende a rialzo in un range definito.
Ideale per mercati laterali (80% del tempo in crypto).
Nessun ordine reale inviato. Simulazione pura.
"""

import os
import sys
import time
import json
import logging
from datetime import datetime
from dataclasses import dataclass
from typing import List, Optional, Dict

try:
    import ccxt
except ImportError:
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "ccxt"])
    import ccxt

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/home/sergio/denaro/grid_paper.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('GridPaperBot')

@dataclass
class GridOrder:
    id: int
    price: float
    quantity: float
    side: str  # 'BUY' o 'SELL'
    filled: bool = False
    filled_price: Optional[float] = None
    filled_time: Optional[datetime] = None

@dataclass
class VirtualTrade:
    entry_price: float
    exit_price: float
    quantity: float
    pnl: float
    entry_time: datetime
    exit_time: datetime

class GridPaperBot:
    def __init__(self, symbol: str, capital: float = 100.0):
        """
        :param symbol: es. 'SOL/USDT' o 'BTC/USDT'
        :param capital: capitale virtuale per questo bot (es. 100€ per nodo)
        """
        self.symbol = symbol
        self.initial_capital = capital
        self.capital = capital
        self.balance_asset = 0.0  # quantità di asset posseduta (es. SOL)
        
        # Configurazione grid
        self.grid_levels = 24  # numero di ordini totali (compravendita)
        self.grid_spacing_pct = 0.002  # 0.8%
        self.take_profit_pct = 0.004  # 1.2% per ordine chiuso
        self.stop_loss_pct = 0.010
        self.dynamic_grid = True
        self.asymmetric = True
        self.recenter_enabled = True
        self.recenter_threshold = 0.10
        self.order_size_pct = 0.02
        self.grid_range_pct = 0.15    # 3% stop loss globale
        self.max_positions = 5       # max posizioni contemporanee
        
        # Calcolo del range attorno al prezzo corrente
        self.exchange = ccxt.binance({'enableRateLimit': True})
        self.current_price = self.fetch_price()
        
        # Range: -15% a +15% dal prezzo corrente (ampio per catturare volatility)
        range_pct = 0.15
        self.lower_bound = self.current_price * (1 - range_pct)
        self.upper_bound = self.current_price * (1 + range_pct)
        
        # Genera griglia di ordini
        self.grid_orders: List[GridOrder] = []
        self.generate_grid()
        
        # Storico trade
        self.trade_history: List[VirtualTrade] = []
        self.running = False
        
        logger.info(f"Grid Bot inizializzato - {symbol}")
        logger.info(f"Prezzo attuale: {self.current_price:.4f}")
        logger.info(f"Range: {self.lower_bound:.4f} - {self.upper_bound:.4f}")
        logger.info(f"Griglia: {self.grid_levels} livelli | Spacing: {self.grid_spacing_pct*100:.2f}%")
        logger.info(f"Capitale: {self.capital:.2f} USDT | Asset: {self.balance_asset:.4f}")
    
    def fetch_price(self) -> float:
        ticker = self.exchange.fetch_ticker(self.symbol)
        return ticker['last']
    
    def generate_grid(self):
        step = (self.upper_bound - self.lower_bound) / (self.grid_levels - 1)
        prices = [self.lower_bound + i * step for i in range(self.grid_levels)]
        # I primi N/2 sono BUY (più bassi), i secondi N/2 sono SELL (più alti)
        mid = self.grid_levels // 2
        buy_prices = prices[:mid]
        sell_prices = prices[mid:]
        
        order_id = 0
        for p in sorted(buy_prices, reverse=True):  # dal più alto dei buy al più basso
            quantity = self.calc_quantity(p, is_buy=True)
            if quantity > 0:
                self.grid_orders.append(GridOrder(id=order_id, price=p, quantity=quantity, side='BUY'))
                order_id += 1
        for p in sorted(sell_prices):  # dal più basso dei sell al più alto
            quantity = self.calc_quantity(p, is_buy=False)
            if quantity > 0:
                self.grid_orders.append(GridOrder(id=order_id, price=p, quantity=quantity, side='SELL'))
                order_id += 1
        
        logger.info(f"Grid generato: {len([o for o in self.grid_orders if o.side=='BUY'])} buy, {len([o for o in self.grid_orders if o.side=='SELL'])} sell")
    
    def calc_quantity(self, price: float, is_buy: bool) -> float:
        """Calcola la quantità da comprare/vendere per ogni ordine"""
        if is_buy:
            # Ogni ordine buy usa una frazione del capitale disponibile
            allocation = self.capital * 0.05  # 5% del capitale per ordine (20 ordini -> 100%)
            qty = allocation / price
            return round(qty, 4)
        else:
            # Vendiamo una frazione degli asset posseduti
            if self.balance_asset <= 0:
                return 0
            allocation = self.balance_asset * 0.05  # 5% del posseduto per ordine
            return round(allocation, 4)
    
    def check_grid(self, current_price: float):
        """Controlla se qualche ordine della griglia è triggerato dal prezzo"""
        for order in self.grid_orders:
            if order.filled:
                continue
            
            if order.side == 'BUY' and current_price <= order.price:
                # Simula esecuzione buy
                cost = order.price * order.quantity
                if self.capital >= cost:
                    self.capital -= cost
                    self.balance_asset += order.quantity
                    order.filled = True
                    order.filled_price = order.price
                    order.filled_time = datetime.now()
                    logger.info(f"BUY SIMULATO: {self.symbol} qty={order.quantity} @ {order.price:.4f} | Capitale: {self.capital:.2f} | Asset: {self.balance_asset:.4f}")
            
            elif order.side == 'SELL' and current_price >= order.price:
                if self.balance_asset >= order.quantity:
                    self.balance_asset -= order.quantity
                    proceeds = order.price * order.quantity
                    self.capital += proceeds
                    order.filled = True
                    order.filled_price = order.price
                    order.filled_time = datetime.now()
                    logger.info(f"SELL SIMULATO: {self.symbol} qty={order.quantity} @ {order.price:.4f} | Capitale: {self.capital:.2f} | Asset: {self.balance_asset:.4f}")
                    
                    # Registra trade completo (associa al buy corrispondente più recente non chiuso)
                    # Semplificato: registriamo ogni sell come chiusura di una posizione generica
                    # In un bot reale, abbinarem buy/sell per calcolare PnL preciso
                    self.trade_history.append(VirtualTrade(
                        entry_price=order.price * 0.99,  # stima
                        exit_price=order.price,
                        quantity=order.quantity,
                        pnl=(order.price * 0.01) * order.quantity,  # 1% profit approssimativo
                        entry_time=datetime.now(),
                        exit_time=datetime.now()
                    ))
    
    def kill_switch(self) -> bool:
        drawdown = (self.initial_capital - self.capital) / self.initial_capital
        if drawdown >= self.stop_loss_pct:
            logger.error(f"KILL SWITCH: drawdown {drawdown*100:.1f}% > {self.stop_loss_pct*100:.0f}%")
            return True
        return False
    
    def run(self):
        self.running = True
        cycle = 0
        logger.info("=== GRID PAPER BOT AVVIATO ===")
        logger.info(f"Range: {self.lower_bound:.4f} - {self.upper_bound:.4f}")
        logger.info("In attesa di prezzo per triggerare ordini...")
        
        while self.running:
            cycle += 1
            try:
                price = self.fetch_price()
                prev_capital = self.capital
                prev_asset = self.balance_asset
                
                self.check_grid(price)
                
                # Report ogni ciclo
                if cycle % 12 == 0:  # ogni ora
                    total_pnl = sum(t.pnl for t in self.trade_history)
                    logger.info(f"Ciclo {cycle}: Prezzo={price:.4f} | Capitale={self.capital:.2f} | Asset={self.balance_asset:.4f} | PnL totale={total_pnl:.2f}")
                
                if self.kill_switch():
                    break
                
                time.sleep(60)  # controllo ogni minuto
            except Exception as e:
                logger.error(f"Errore ciclo: {e}")
                time.sleep(60)
        
        total_pnl = sum(t.pnl for t in self.trade_history)
        logger.info(f"Bot terminato. Capitale finale: {self.capital:.2f} USDT | Asset: {self.balance_asset:.4f} | PnL: {total_pnl:+.2f} USDT")
    
    def stop(self):
        self.running = False

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--symbol', default='SOL/USDT', help='Simbolo trading')
    parser.add_argument('--capital', type=float, default=100.0, help='Capitale virtuale')
    args = parser.parse_args()
    
    bot = GridPaperBot(symbol=args.symbol, capital=args.capital)
    try:
        bot.run()
    except KeyboardInterrupt:
        bot.stop()
        logger.info("Interrotto")
