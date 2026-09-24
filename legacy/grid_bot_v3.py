#!/usr/bin/env python3
"""
DENARO GRID BOT v3 PRO - Core-Driven
WebSocket-driven grid trading using DenaroCore for stability and efficiency.
"""

import asyncio
import json
import logging
import websockets
import time
from denaro_core import DenaroCore
from denaro_strategies import TrendFilter, VolatilityGrid, MartingaleLite, Rebalancer, ProfitOptimizer
from vault_utils import atomic_write

logging.basicConfig(level=logging.INFO, format='%(asctime)s - GRID-PRO - %(levelname)s - %(message)s')
logger = logging.getLogger("GridBotPro")

class GridBot(DenaroCore):
    def __init__(self):
        super().__init__(bot_name="GridBotPro")
        self.state = {
            "filled_orders": [],
            "total_invested": 0.0,
            "total_profit": 0.0,
            "peak_value": 0.0,
            "grid_active": False,
            "current_price": 0.0,
            "placed_order_ids": [],
            "sync_done": False,
            "last_config_reload": 0,
            "paused": False,
            "pause_reason": ""
        }
        # Initialize v4 Strategies
        self.trend_filter = TrendFilter(self.config)
        self.vol_grid = VolatilityGrid(self.config)
        self.martingale = MartingaleLite(self.config)
        self.rebalancer = Rebalancer(self.config)
        self.optimizer = ProfitOptimizer(self.config)

    async def on_tick(self, price, client):
        self.state['current_price'] = price
        
        # 1. Dynamic Config Reload
        if time.time() - self.state['last_config_reload'] > self.config.get('config_reload_sec', 600):
            self.load_config()
            self.state['last_config_reload'] = time.time()

        # 2. Out-of-bounds check (Kill Switch)
        if not self.state['paused'] and 'grid_buy_levels' in self.state and self.state['grid_buy_levels']:
            lowest_buy = min(self.state['grid_buy_levels'])
            out_of_bounds_threshold = self.config.get('out_of_bounds_threshold', 0.02)  # 2%
            if price < lowest_buy * (1 - out_of_bounds_threshold):
                self.state['paused'] = True
                self.state['pause_reason'] = f"Price {price}€ dropped below lowest grid level {lowest_buy}€ by more than {out_of_bounds_threshold*100}%"
                logger.warning(f"🚨 KILL SWITCH ACTIVATED: {self.state['pause_reason']}")
                # Cancel all open orders
                for order_id in self.state['placed_order_ids'][:]:
                    try:
                        await asyncio.to_thread(client.cancel_order, order_id, self.config['symbol'])
                        logger.info(f"Cancelled order {order_id}")
                    except Exception as e:
                        logger.error(f"Failed to cancel order {order_id}: {e}")
                self.state['placed_order_ids'] = []
        
        # 3. Trend Filter (v4)
        trend = self.trend_filter.get_trend(client, self.config['symbol'], price)
        if trend in ("STRONG_DOWN",):
            if not self.state['paused']:
                self.state['paused'] = True
                self.state['pause_reason'] = f"Trend: {trend} - Grid paused"
                logger.warning(f"⚠️ TREND PAUSE: {trend} - Grid paused, protecting capital")
                for order_id in self.state['placed_order_ids'][:]:
                    try:
                        await asyncio.to_thread(client.cancel_order, order_id, self.config['symbol'])
                    except: pass
                self.state['placed_order_ids'] = []
        elif trend == "DOWN" and not self.state['paused']:
            logger.info(f"⚠️ Trend: {trend} - Operating cautiously")
        elif trend in ("UP", "STRONG_UP", "NEUTRAL") and self.state['paused'] and "Trend" in self.state.get('pause_reason', ''):
            self.state['paused'] = False
            self.state['pause_reason'] = ""
            self.state['grid_active'] = False
            logger.info(f"🟢 TREND RESUME: Trend is now {trend} - Grid resuming")
        
        # 4. Peak tracking for Trailing Stop
        if price > self.state['peak_value']:
            self.state['peak_value'] = price
        
        # 4. Resume if price returns within bounds
        if self.state['paused'] and 'grid_buy_levels' in self.state and self.state['grid_buy_levels']:
            lowest_buy = min(self.state['grid_buy_levels'])
            if price >= lowest_buy * (1 - self.config.get('out_of_bounds_threshold', 0.02) / 2):  # 1% below lowest
                self.state['paused'] = False
                self.state['pause_reason'] = ""
                logger.info("🟢 KILL SWITCH DEACTIVATED: Price returned within bounds, resuming grid.")
                # Re-initialize grid
                self.state['grid_active'] = False
        
        # 5. Initial Sync
        if not self.state['sync_done']:
            await self.sync_existing_orders(client, price)
            self.state['sync_done'] = True
        
        # 6. Rebalance check (v4)
        if not self.state['paused'] and self.state['grid_active'] and 'grid_buy_levels' in self.state:
            if self.rebalancer.needs_rebalance(price, self.state['grid_buy_levels'], self.config):
                logger.info("🔄 Rebalancing grid...")
                self.state['grid_active'] = False
                self.rebalancer.mark_rebalanced()
        
        # 7. Grid Initialization/Healing (skip if paused)
        if not self.state['paused'] and not self.state['grid_active']:
            await self.init_grid(client, price)
        
        # 5. Trailing Stop Check
        if self.trailing_stop_check(price) == "EXIT":
            logger.warning(f"🚨 TRAILING STOP EXIT @ {price}€")
            await self.close_all_positions(client, price)
            return
        
        # 6. Check Fills
        await self.check_fills(client)
        
        # 7. Profit Optimizer adjustment (v4)
        adj = self.optimizer.get_adjustment(self.config['base_order_eur'])
        if adj != 1.0:
            metrics = self.optimizer.get_metrics()
            if metrics:
                logger.info(f"📊 Performance: WR={metrics['win_rate']:.0f}% PF={metrics['profit_factor']:.2f} Trades={metrics['total_trades']} Adj={adj:.2f}x")
        
        # 8. Periodic status log
        if int(time.time()) % 60 < 5:
            logger.info(f"Price: {price}€ | Invested: {self.state['total_invested']:.2f}€ | Profit: {self.state['total_profit']:.2f}€")

    async def sync_existing_orders(self, client, current_price):
        logger.info("Syncing orders with exchange...")
        try:
            open_orders = await self.sync_orders(self.config['symbol'])
            # Only count BUY orders for grid-active (sell orders are from range/sell grid)
            buy_orders = sorted([o for o in open_orders if o['side'] == 'buy'], key=lambda x: abs(x['price'] - current_price))
            sell_orders_from_grid = [o for o in open_orders if o['side'] == 'sell' and o.get('clientOrderId', '').startswith('x-')]
            
            keep_buys = buy_orders[:self.config['grid_levels']]
            cancel_orders = buy_orders[self.config['grid_levels']:]
            
            for o in cancel_orders:
                try: await asyncio.to_thread(client.cancel_order, o['id'], self.config['symbol'])
                except: pass
            
            self.state['placed_order_ids'] = [o['id'] for o in keep_buys + keep_sells]
            self.state['grid_active'] = len(keep_buys) > 0
            self.state['total_invested'] = len(keep_buys) * self.config['base_order_eur']
            logger.info(f"Sync complete: {len(keep_buys)} buy / {len(keep_sells)} sell orders (grid_active={self.state['grid_active']})")
        except Exception as e:
            logger.error(f"Sync error: {e}")

    async def init_grid(self, client, current_price):
        eur_free = await self.get_balance('EUR')
        num_levels = self.config['grid_levels']
        base_size = self.config['base_order_eur']
        
        # Martingale: calculate total budget needed
        mart_total = self.martingale.get_total_for_levels(num_levels)
        budget_eur = max(base_size, min(mart_total, self.config['max_total_invested'] - self.state['total_invested']))
        
        if eur_free < (budget_eur * 0.9):
            # Scale down levels based on available EUR
            for n in range(num_levels, 0, -1):
                if self.martingale.get_total_for_levels(n) <= eur_free * 0.9:
                    num_levels = n
                    break
            else:
                num_levels = max(1, int(eur_free / (base_size * 1.1)))
            if num_levels == 0:
                logger.error("Insufficient EUR for grid")
                self.state['grid_active'] = True 
                return

        # Volatility-adaptive grid spacing (v4)
        atr = await self.get_atr(self.config['symbol'], timeframe='1h', lookback=14)
        grid_range_pct, profit_pct = self.vol_grid.get_spacing(atr, current_price)
        logger.info(f"🔄 Volatility Adaptive: ATR={atr:.4f} ({atr/current_price*100:.2f}%), grid_range={grid_range_pct:.2%}, profit={profit_pct:.2%}")
        
        step = grid_range_pct / num_levels
        buy_prices = [round(current_price * (1 - (i * step)), 2) for i in range(1, num_levels + 1)]
        sell_prices = [round(bp * (1 + profit_pct), 2) for bp in buy_prices]
        
        # Store absolute grid levels for re-centering
        self.state['grid_buy_levels'] = buy_prices
        self.state['grid_sell_levels'] = sell_prices
        
        placed = 0
        for i, bp in enumerate(reversed(buy_prices)):
            if self.state['total_invested'] >= self.config['max_total_invested']: break
            order_eur = self.martingale.get_size(i)  # Martingale sizing (v4)
            order_eur = min(order_eur, self.config['max_total_invested'] - self.state['total_invested'])
            amount = order_eur / bp
            try:
                order = await asyncio.to_thread(client.create_limit_buy_order, self.config['symbol'], round(amount, 5), bp)
                self.state['placed_order_ids'].append(order['id'])
                self.state['total_invested'] += order_eur
                placed += 1
                await asyncio.sleep(0.2)
            except Exception as e:
                logger.error(f"BUY fail @ {bp}€: {e}")
        
        self.state['grid_active'] = True
        logger.info(f"Grid initialized: {placed} buy orders")

        # ── Range Trading: also place SELL orders above market using free SOL ──
        try:
            balances = await asyncio.to_thread(client.fetch_balance)
            sol_free = balances['free'].get('SOL', 0)
            if sol_free > 0.01:
                sol_per_sell = 0.05  # Use 0.05 SOL per sell level
                sell_levels = 3
                max_sol_use = min(sol_free, sol_per_sell * sell_levels)
                num_sells = int(max_sol_use / sol_per_sell)
                for i in range(num_sells):
                    sell_pct = (i + 1) * 0.004  # 0.4%, 0.8%, 1.2% above market
                    sell_price = round(current_price * (1 + sell_pct), 2)
                    try:
                        order = await asyncio.to_thread(
                            client.create_limit_sell_order,
                            self.config['symbol'],
                            round(sol_per_sell, 5),
                            sell_price
                        )
                        self.state['placed_order_ids'].append(order['id'])
                        logger.info(f"📈 RANGE SELL @ {sell_price}€ (+{sell_pct*100:.1f}%) {sol_per_sell} SOL")
                    except Exception as e:
                        logger.error(f"RANGE SELL fail @ {sell_price}€: {e}")
                self.state['range_sell_qty'] = sol_per_sell
        except Exception as e:
            logger.warning(f"Range sell init failed: {e}")

    def trailing_stop_check(self, current_price):
        if current_price <= 0 or not self.state['filled_orders']: return "HOLD"
        # Auto-breakeven: if price rises above buy price + fees, move stop loss to buy price
        if 'last_buy_price' in self.state:
            buy_price = self.state['last_buy_price']
            fee_pct = 0.00075  # Maker fee with BNB discount
            breakeven_price = buy_price * (1 + fee_pct * 2)  # entry + exit fees
            if current_price > breakeven_price:
                # Move stop loss to breakeven
                stop = breakeven_price
                if current_price < stop:
                    return "EXIT"
                logger.debug(f"Auto-breakeven active: stop={stop:.2f}€")
        
        if self.state['peak_value'] > 0:
            profit_pct = (current_price - self.state['peak_value'] * 0.98) / (self.state['peak_value'] * 0.98) * 100
            if profit_pct >= self.config['trailing_activation_pct']:
                stop = self.state['peak_value'] * (1 - self.config['trailing_stop_pct'] / 100)
                if current_price < stop: return "EXIT"
        return "HOLD"

    async def check_fills(self, client):
        for order_id in self.state['placed_order_ids'][:]:
            try:
                status = await asyncio.to_thread(client.fetch_order, order_id, self.config['symbol'])
                if status['status'] == 'closed':
                    side = status['side']
                    price, amount = float(status['average']), float(status['amount'])
                    if order_id in [o['id'] for o in self.state['filled_orders']]: continue
                    self.state['filled_orders'].append({'id': order_id, 'side': side, 'price': price, 'amount': amount})
                    
                    if side == 'buy':
                        logger.info(f"✅ BUY filled @ {price}€")
                        # Store buy price for auto-breakeven
                        self.state['last_buy_price'] = price
                        # Place corresponding SELL order at absolute sell level
                        if 'grid_sell_levels' in self.state and self.state['grid_sell_levels']:
                            # Find the closest sell price (should be price * (1 + profit_per_grid))
                            target_sell_price = price * (1 + self.config['profit_per_grid'])
                            closest = min(self.state['grid_sell_levels'], key=lambda x: abs(x - target_sell_price))
                            try:
                                amount = self.config['base_order_eur'] / price  # amount bought
                                sell_order = await asyncio.to_thread(client.create_limit_sell_order, self.config['symbol'], round(amount, 5), closest)
                                self.state['placed_order_ids'].append(sell_order['id'])
                                logger.info(f"📈 SELL order placed @ {closest}€")
                            except Exception as e:
                                logger.error(f"Failed to place SELL order @ {closest}€: {e}")
                    else:
                        fee = price * (amount if 'amount' in dir() else self.config['base_order_eur']/price) * 0.00075
                        # Find original level index for martingale profit calculation
                        orig_eur = self.config['base_order_eur']
                        if 'orig_level_idx' in self.state and self.state['grid_buy_levels']:
                            target_price = price / (1 + profit_pct if 'profit_pct' in dir() else self.config['profit_per_grid'])
                            closest_bp = min(self.state['grid_buy_levels'], key=lambda x: abs(x - target_price))
                            try:
                                level_i = self.state['grid_buy_levels'].index(closest_bp)
                                orig_eur = self.martingale.get_size(level_i)
                            except: pass
                        profit = (self.config['profit_per_grid'] * orig_eur) - fee
                        self.state['total_profit'] += profit
                        self.log_trade(self.config['symbol'], 'SELL', price, orig_eur/price, orig_eur, fee, profit)
                        self.optimizer.add_trade(profit)  # Track for optimizer
                        logger.info(f"💰 SELL filled @ {price}€, Profit: {profit:.2f}€")
                        
                        # Grid re-centering: replace the sold level with a new BUY order at original price
                        if 'grid_buy_levels' in self.state and self.state['grid_buy_levels']:
                            # Find the closest original buy price (should be price / (1 + profit_per_grid))
                            target_buy_price = price / (1 + self.config['profit_per_grid'])
                            closest = min(self.state['grid_buy_levels'], key=lambda x: abs(x - target_buy_price))
                            # Place a new BUY order at the original level with Martingale sizing
                            try:
                                level_i_rebuy = self.state['grid_buy_levels'].index(closest)
                                rebuy_eur = self.martingale.get_size(level_i_rebuy)
                                rebuy_amount = rebuy_eur / closest
                                new_order = await asyncio.to_thread(client.create_limit_buy_order, self.config['symbol'], round(rebuy_amount, 5), closest)
                                self.state['placed_order_ids'].append(new_order['id'])
                                logger.info(f"🔄 Grid re-centered: new BUY order @ {closest}€ ({rebuy_eur:.2f}€ martingale)")
                            except Exception as e:
                                logger.error(f"Failed to place re-centered BUY order @ {closest}€: {e}")
                    self.state['placed_order_ids'].remove(order_id)
            except Exception: pass

    async def close_all_positions(self, client, price):
        try:
            balances = await asyncio.to_thread(client.fetch_balance)
            asset = self.config['symbol'].split('/')[0]
            amount = balances['free'].get(asset, 0)
            if amount > 0.0001:
                await asyncio.to_thread(client.create_market_sell_order, self.config['symbol'], amount)
                logger.info(f"Closed all {asset} positions")
        except Exception as e: logger.error(f"Close error: {e}")

    async def run(self):
        client = self.client
        try:
            ticker = await asyncio.to_thread(client.fetch_ticker, self.config['symbol'])
            self.state['peak_value'] = ticker['last']
            logger.info(f"Starting price: {self.state['peak_value']}€")
        except Exception as e:
            logger.error(f"Initial price error: {e}")
            return
        
        url = f"wss://stream.binance.com:9443/ws/{self.config['symbol_ws']}@ticker"
        async with websockets.connect(url, ping_interval=30) as ws:
            logger.info("WebSocket connected!")
            while True:
                msg = await ws.recv()
                data = json.loads(msg)
                if data.get('e') == '24hrTicker':
                    await self.on_tick(float(data['c']), client)

if __name__ == "__main__":
    bot = GridBot()
    asyncio.run(bot.run())
