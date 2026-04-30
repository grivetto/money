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

    def save_trade(self, bot_name, symbol, side, entry_price, exit_price, quantity, entry_time, exit_time, gross_pnl, fees, net_pnl, reason):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT INTO trades (bot_name, symbol, side, entry_price, exit_price, quantity, entry_time, exit_time, gross_pnl, fees, net_pnl, exit_reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (bot_name, symbol, side, entry_price, exit_price, quantity, entry_time, exit_time, gross_pnl, fees, net_pnl, reason))
            conn.commit()

    
    def log_trade(self, symbol, side, entry_price, exit_price, quantity, pnl, timestamp, strategy="grid", stop_loss=None, take_profit=None, exit_reason=None, order_id=None, fees=0.0, leverage=1.0):
        """Wrapper per compatibilità con DenaroCore."""
        self.save_trade(symbol, side, entry_price, exit_price, quantity, pnl, timestamp, strategy, stop_loss, take_profit, exit_reason, order_id, fees, leverage)

def get_daily_pnl(self):
        today = datetime.now().strftime('%Y-%m-%d')
        with sqlite3.connect(self.db_path) as conn:
            res = conn.execute('SELECT SUM(net_pnl) FROM trades WHERE date(exit_time) = ?', (today,)).fetchone()
            return res[0] if res[0] else 0.0

    def get_metrics(self):
        with sqlite3.connect(self.db_path) as conn:
            trades = conn.execute('SELECT net_pnl FROM trades').fetchall()
            if not trades: return {'win_rate': 0, 'total_profit': 0}
            
            pnls = [t[0] for t in trades]
            win_rate = (len([p for p in pnls if p > 0]) / len(pnls)) * 100
            total_profit = sum(pnls)
            return {'win_rate': win_rate, 'total_profit': total_profit}

    def get_unrealized_pnl(self, strategy=None):
        """Somma PnL posizioni ancora aperte (exit_time IS NULL)."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            if strategy:
                cursor.execute("SELECT SUM(net_pnl) FROM trades WHERE exit_time IS NULL AND strategy = ?", (strategy,))
            else:
                cursor.execute("SELECT SUM(net_pnl) FROM trades WHERE exit_time IS NULL")
            res = cursor.fetchone()
            conn.close()
            return res[0] or 0.0
        except:
            return 0.0

    def get_open_positions_count(self, strategy=None):
        """Numero posizioni aperte."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            if strategy:
                cursor.execute("SELECT COUNT(*) FROM trades WHERE exit_time IS NULL AND strategy = ?", (strategy,))
            else:
                cursor.execute("SELECT COUNT(*) FROM trades WHERE exit_time IS NULL")
            res = cursor.fetchone()
            conn.close()
            return res[0] or 0
        except:
            return 0

    def get_strategy_roic(self, strategy, days=1):
        """ROIC: Return on Invested Capital per strategia."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            since = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
            cursor.execute("""
                SELECT SUM(entry_price * quantity), SUM(net_pnl)
                FROM trades
                WHERE DATE(exit_time) >= ? AND strategy = ?
            """, (since, strategy))
            capital_used, pnl = cursor.fetchone() or (0.0, 0.0)
            conn.close()
            roic = (pnl / capital_used * 100) if capital_used > 0 else 0.0
            return {"capital_used": capital_used, "pnl": pnl, "roic": roic}
        except:
            return {"capital_used": 0.0, "pnl": 0.0, "roic": 0.0}

    def get_filter_stats(self, strategy=None, days=1):
        """Statistiche filtri: conteggio per reason."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            since = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
            if strategy:
                cursor.execute("SELECT reason, COUNT(*) FROM filter_events WHERE DATE(timestamp) >= ? AND strategy = ? GROUP BY reason", (since, strategy))
            else:
                cursor.execute("SELECT reason, COUNT(*) FROM filter_events WHERE DATE(timestamp) >= ? GROUP BY reason", (since,))
            rows = cursor.fetchall()
            conn.close()
            return {reason: count for reason, count in rows}
        except:
            return {}
