import sqlite3
from datetime import datetime

class TradeDB:
    def __init__(self, db_path='trades.db'):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bot_name TEXT,
                    symbol TEXT,
                    side TEXT,
                    entry_price REAL,
                    exit_price REAL,
                    quantity REAL,
                    entry_time DATETIME,
                    exit_time DATETIME,
                    gross_pnl REAL,
                    fees REAL,
                    net_pnl REAL,
                    exit_reason TEXT
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS bot_state (
                    bot_name TEXT PRIMARY KEY,
                    is_in_position BOOLEAN,
                    entry_price REAL,
                    quantity REAL,
                    last_heartbeat DATETIME
                )
            ''')
            conn.commit()

    def log_trade(self, symbol, side, price, amount, cost, fee, profit, strategy="grid"):
        """Called by DenaroCore - logs a completed trade to DB"""
        now = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT INTO trades (bot_name, symbol, side, entry_price, exit_price, quantity, entry_time, exit_time, gross_pnl, fees, net_pnl, exit_reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (strategy, symbol, side, price, price, amount, now, now, profit + fee, fee, profit, 'TP_SL'))
            conn.commit()

    def save_trade(self, bot_name, symbol, side, entry_price, exit_price, quantity, entry_time, exit_time, gross_pnl, fees, net_pnl, reason):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT INTO trades (bot_name, symbol, side, entry_price, exit_price, quantity, entry_time, exit_time, gross_pnl, fees, net_pnl, exit_reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (bot_name, symbol, side, entry_price, exit_price, quantity, entry_time, exit_time, gross_pnl, fees, net_pnl, reason))
            conn.commit()

    def get_daily_pnl(self):
        today = datetime.now().strftime('%Y-%m-%d')
        with sqlite3.connect(self.db_path) as conn:
            res = conn.execute('SELECT COALESCE(SUM(net_pnl),0) FROM trades WHERE date(exit_time) = ?', (today,)).fetchone()
            return res[0] if res and res[0] else 0.0
    
    def get_total_pnl(self, bot_name=None):
        with sqlite3.connect(self.db_path) as conn:
            if bot_name:
                res = conn.execute('SELECT COALESCE(SUM(net_pnl),0) FROM trades WHERE bot_name = ?', (bot_name,)).fetchone()
            else:
                res = conn.execute('SELECT COALESCE(SUM(net_pnl),0) FROM trades').fetchone()
            return res[0] if res and res[0] else 0.0
    
    def get_recent_trades(self, limit=10):
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute('SELECT exit_time, symbol, side, net_pnl, fees FROM trades ORDER BY exit_time DESC LIMIT ?', (limit,)).fetchall()
            return [{'time':r[0],'symbol':r[1],'side':r[2],'pnl':r[3],'fee':r[4]} for r in rows]

    def get_metrics(self):
        with sqlite3.connect(self.db_path) as conn:
            trades = conn.execute('SELECT net_pnl FROM trades').fetchall()
            if not trades: return {'win_rate': 0, 'total_profit': 0}
            
            pnls = [t[0] for t in trades]
            win_rate = (len([p for p in pnls if p > 0]) / len(pnls)) * 100
            total_profit = sum(pnls)
            return {'win_rate': win_rate, 'total_profit': total_profit}
