#!/usr/bin/env python3
"""
FUNDING RATE ARBITRAGE - PAPER TRADING
Strategia Delta-Neutral:-long spot + short futures per catturare il funding rate.
Nessun rischio direzionale, solo raccolta del "pizzo" ogni 8 ore.
Simulazione: nessun ordine reale, solo calcoli matematici.
"""

import os
import sys
import time
import json
import logging
import random
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict
import argparse

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
        logging.FileHandler('/home/sergio/denaro/funding_paper.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('FundingPaperBot')

@dataclass
class FundingRateSnapshot:
    symbol: str
    funding_rate: float  # e.g., 0.0005 = 0.05% per 8h
    next_funding_time: datetime
    timestamp: datetime

@dataclass
class VirtualPosition:
    symbol: str
    spot_qty: float
    futures_qty: float
    entry_spot_price: float
    entry_futures_price: float
    entry_funding: float
    entry_time: datetime
    total_pnl: float = 0.0

class FundingArbitragePaperBot:
    def __init__(self, capital: float = 200.0, min_funding: float = 0.0001):
        """
        :param capital: capitale totale (suddiviso 50% spot / 50% futures)
        :param min_funding: funding rate minimo per aprire posizione (0.0003 = 0.03% per 8h)
        """
        self.initial_capital = capital
        self.capital = capital
        self.min_funding = min_funding
        self.positions: Dict[str, VirtualPosition] = {}
        self.trade_log: List[dict] = []
        self.running = False
        
        # Exchange pubblico (per dati)
        self.exchange = ccxt.binance({'enableRateLimit': True})
        
        # Watchlist: meme coin ad alto funding
        self.watchlist = ['SOL/USDT', 'DOGE/USDT', 'SHIB/USDT', 'PEPE/USDT', 'FLOKI/USDT', 'BONK/USDT', 'WIF/USDT']
        
        # Simulazione storage dati storici funding (per paper)
        self.funding_history: Dict[str, List[FundingRateSnapshot]] = {}
        
        logger.info(f"FUNDING ARBITRAGE BOT - Capitale: {self.capital} USDT")
        logger.info(f"Soglia funding minima: {self.min_funding*100:.3f}% per 8h")
    
    def fetch_funding_rate(self, symbol: str) -> Optional[float]:
        """Recupera funding rate attuale da Binance (API pubblica)"""
        try:
            # Per futures: binance ha endpoint specifico
            # In ccxt: fetch_funding_rate(symbol)
            fr = self.exchange.fetch_funding_rate(symbol)
            rate = float(fr['fundingRate'])  # es: 0.0005
            next_ts = fr['nextFundingTime']
            next_dt = datetime.fromtimestamp(next_ts/1000) if next_ts else None
            return rate, next_dt
        except Exception as e:
            logger.debug(f"Errore funding rate {symbol}: {e}")
            return None, None
    
    def fetch_spot_price(self, symbol: str) -> float:
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            return ticker['last']
        except:
            return 0.0
    
    def scan_opportunities(self) -> List[dict]:
        """Cerca coppie con funding rate positivo e sufficiente"""
        opportunities = []
        logger.info("SCANSIONE funding rate...")
        
        for symbol in self.watchlist:
            rate, next_dt = self.fetch_funding_rate(symbol)
            if rate is None:
                continue
            
            if rate >= self.min_funding:
                spot_price = self.fetch_spot_price(symbol)
                if spot_price > 0:
                    opportunities.append({
                        'symbol': symbol,
                        'funding_rate': rate,
                        'next_funding': next_dt,
                        'spot_price': spot_price,
                        'annual_yield': rate * 365 / 8  # approssimativo
                    })
                    logger.info(f"OPPORTUNITY: {symbol} | Funding: {rate*100:.3f}% | APY approx: {rate*365/8*100:.1f}%")
        
        # Ordina per funding rate decrescente
        opportunities.sort(key=lambda x: x['funding_rate'], reverse=True)
        return opportunities
    
    def open_position(self, opp: dict) -> bool:
        """Apri posizione bilanciata: long spot + short futures"""
        symbol = opp['symbol']
        if symbol in self.positions:
            logger.warning(f"{symbol}: posizione già aperta")
            return False
        
        price = opp['spot_price']
        
        # Alloca capitale: 50% spot, 50% futures
        allocation = self.capital * 0.5
        
        # Quantità spot (compra)
        spot_qty = round(allocation / price, 4)
        # Quantità futures (vendi short, stessa notional)
        futures_qty = spot_qty  # 1:1 hedge
        
        # Simula apertura
        self.capital -= allocation  # capital locked (in realtà non esce, ma per paper teniamo traccia)
        
        pos = VirtualPosition(
            symbol=symbol,
            spot_qty=spot_qty,
            futures_qty=futures_qty,
            entry_spot_price=price,
            entry_futures_price=price,  # assumiamo pari
            entry_funding=opp['funding_rate'],
            entry_time=datetime.now()
        )
        self.positions[symbol] = pos
        self.trade_log.append({
            'action': 'OPEN',
            'symbol': symbol,
            'time': datetime.now().isoformat(),
            'funding_rate': opp['funding_rate'],
            'spot_price': price,
            'capital_remaining': self.capital
        })
        logger.info(f"APERTA POSIZIONE: {symbol} | Spot: {spot_qty:.4f} @ {price:.4f} | Funding: {opp['funding_rate']*100:.3f}%")
        logger.info(f"Capitale residuo (liquid): {self.capital:.2f} USDT | Asset bloccati: {self.initial_capital - self.capital:.2f} USDT")
        return True
    
    def close_position(self, symbol: str, reason: str) -> dict:
        """Chiude entrambe le gambe della posizione e somma PnLFunding"""
        pos = self.positions.get(symbol)
        if not pos:
            return {}
        
        # Prezzi attuali (simulati - possono muoversi)
        current_spot = self.fetch_spot_price(symbol)
        current_futures = current_spot  # assumiamo convergenza
        
        # PnL spot (cambio prezzo)
        spot_pnl = (current_spot - pos.entry_spot_price) * pos.spot_qty
        
        # PnL futures (corto: guadagna se prezzo scende)
        futures_pnl = (pos.entry_futures_price - current_futures) * pos.futures_qty
        
        # Funding raccolto: semplice stima: funding rate × tempo × size
        # In realtà ogni 8h si riceve/paga. Simuliamo che sia tempo sufficiente per 1 funding period
        holding_hours = (datetime.now() - pos.entry_time).total_seconds() / 3600
        periods = holding_hours / 8.0
        funding_cash = pos.entry_funding * periods * (pos.spot_qty * pos.entry_spot_price)
        
        total_pnl = spot_pnl + futures_pnl + funding_cash
        
        self.capital += (pos.spot_qty * pos.entry_spot_price)  # ritorna il valore spot iniziale
        # Futures non blocca capitale in margin (leverage 1x non richiede margin extra in questa semplificazione)
        
        result = {
            'symbol': symbol,
            'spot_pnl': spot_pnl,
            'futures_pnl': futures_pnl,
            'funding_cash': funding_cash,
            'total_pnl': total_pnl,
            'holding_hours': holding_hours,
            'close_reason': reason
        }
        
        logger.info(f"CHIUSURA: {symbol} | Motivo: {reason}")
        logger.info(f"  Spot PnL: {spot_pnl:+.2f} | Futures PnL: {futures_pnl:+.2f} | Funding: {funding_cash:+.2f}")
        logger.info(f"  TOT: {total_pnl:+.2f} USDT")
        
        del self.positions[symbol]
        return result
    
    def check_position_health(self) -> List[str]:
        """Controlla se qualche posizione deve essere chiusa (funding negativo o spread amplio)"""
        to_close = []
        for symbol, pos in self.positions.items():
            rate, _ = self.fetch_funding_rate(symbol)
            if rate is None:
                continue
            
            # Se funding diventa negativo o sotto soglia, esci
            if rate < 0.0001:  # funding negativo o zero
                to_close.append(f"Funding rate negativo ({rate*100:.3f}%)")
                continue
            
            # Se spread spot-futures > 0.5% (rischio decoupling)
            spot = self.fetch_spot_price(symbol)
            futures = spot  # assumiamo
            spread = abs(futures - spot) / spot
            if spread > 0.005:
                to_close.append(f"Spread elevato ({spread*100:.2f}%)")
                continue
        
        return to_close
    
    def kill_switch(self) -> bool:
        drawdown = (self.initial_capital - self.capital) / self.initial_capital
        if drawdown >= 0.05:  # 5% drawdown
            logger.error(f"KILL SWITCH: drawdown {drawdown*100:.1f}% >= 5%")
            return True
        return False
    
    def run(self):
        self.running = True
        cycle = 0
        logger.info("=== FUNDING ARBITRAGE PAPER BOT AVVIATO ===")
        logger.info("Strategia: Delta Neutral (Long Spot + Short Futures)")
        logger.info("Raccolta funding rate ogni 8 ore simulati")
        
        last_funding_check = datetime.now()
        funding_interval = 8 * 3600  # 8 ore in secondi (per simulazione)
        
        while self.running:
            cycle += 1
            try:
                # 1. SCAN: cerca nuove opportunità ogni 30 min
                if cycle % 30 == 0:  # ogni 30 cicli (30min se sleep 60s)
                    opps = self.scan_opportunities()
                    # Apri la migliore opportunità se non posso avere più di 2 posizioni aperte
                    if opps and len(self.positions) < 2:
                        best = opps[0]
                        logger.info(f"Migliore funding: {best['symbol']} @ {best['funding_rate']*100:.3f}%")
                        if best['symbol'] not in self.positions:
                            self.open_position(best)
                
                # 2. CONTROLLO POSIZIONI APERTE ogni minuto
                if self.positions:
                    for symbol in list(self.positions.keys()):
                        reasons = self.check_position_health(symbol)
                        if reasons:
                            self.close_position(symbol, ', '.join(reasons))
                
                # 3. funding collection simulation (ogni 8h simulate = ogni 30 cicli = 30min)
                if (datetime.now() - last_funding_check).total_seconds() >= funding_interval:
                    logger.info("=== RISCOSSIONE FUNDING SIMULATA ===")
                    for symbol, pos in self.positions.items():
                        rate, _ = self.fetch_funding_rate(symbol)
                        if rate:
                            # Simula incasso funding per 8 ore
                            notional = pos.spot_qty * pos.entry_spot_price
                            cash = rate * notional
                            logger.info(f"Funding {symbol}: {rate*100:.3f}% → +{cash:.2f} USDT")
                            self.capital += cash
                    last_funding_check = datetime.now()
                
                # 4. Report
                if cycle % 10 == 0:
                    total_pnl = self.capital - self.initial_capital
                    open_pos = len(self.positions)
                    logger.info(f"Ciclo {cycle} | Capitale: {self.capital:.2f} USDT | PnL: {total_pnl:+.2f} | Posizioni: {open_pos}")
                
                if self.kill_switch():
                    break
                
                time.sleep(60)
            except Exception as e:
                logger.error(f"Errore ciclo: {e}")
                time.sleep(60)
        
        # Chiusura forzata posizioni rimaste
        for symbol in list(self.positions.keys()):
            self.close_position(symbol, "Kill switch")
        logger.info(f"Bot terminato. Capitale finale: {self.capital:.2f} USDT | PnL totale: {self.capital - self.initial_capital:+.2f}")

    def stop(self):
        self.running = False

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--capital', type=float, default=200.0)
    parser.add_argument('--min-funding', type=float, default=0.0003)
    args = parser.parse_args()
    
    bot = FundingArbitragePaperBot(capital=args.capital, min_funding=args.min_funding)
    try:
        bot.run()
    except KeyboardInterrupt:
        bot.stop()
