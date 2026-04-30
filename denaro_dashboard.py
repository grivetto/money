import sqlite3
import datetime
import os
import curses

def get_node_stats_extended(db_path, node_name=None):
    """Statistiche estese per nodo."""
    stats = {
        "profit": 0.0, "trades": 0,
        "unrealized_pnl": 0.0, "open_positions": 0,
        "roic": 0.0, "roic_capital": 0.0,
        "filter_stats": {}
    }
    if not os.path.exists(db_path):
        return stats
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        today = datetime.date.today().isoformat()
        
        cursor.execute("SELECT SUM(net_pnl), COUNT(*) FROM trades WHERE DATE(exit_time) = ?", (today,))
        row = cursor.fetchone()
        stats["profit"] = row[0] or 0.0
        stats["trades"] = row[1] or 0
        
        cursor.execute("SELECT SUM(net_pnl), COUNT(*) FROM trades WHERE exit_time IS NULL")
        row = cursor.fetchone()
        stats["unrealized_pnl"] = row[0] or 0.0
        stats["open_positions"] = row[1] or 0
        
        yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
        cursor.execute("""
            SELECT SUM(entry_price * quantity), SUM(net_pnl)
            FROM trades WHERE DATE(exit_time) = ? AND strategy IN ('grid', 'momentum', 'funding')
        """, (yesterday,))
        cap_used, pnl = cursor.fetchone() or (0.0, 0.0)
        stats["roic_capital"] = cap_used or 0.0
        stats["roic"] = (pnl / cap_used * 100) if cap_used and cap_used > 0 else 0.0
        
        try:
            cursor.execute("SELECT reason, COUNT(*) FROM filter_events WHERE DATE(timestamp) = ? GROUP BY reason", (today,))
            stats["filter_stats"] = {row[0]: row[1] for row in cursor.fetchall()}
        except:
            stats["filter_stats"] = {}
        
        conn.close()
    except:
        pass
    return stats

def get_funding_stats(db_path):
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        today = datetime.date.today().isoformat()
        cursor.execute("""
            SELECT SUM(net_pnl), COUNT(*), SUM(entry_price * quantity)
            FROM trades WHERE DATE(exit_time) = ? AND strategy = 'funding'
        """, (today,))
        row = cursor.fetchone()
        conn.close()
        return {"profit": row[0] or 0.0, "trades": row[1] or 0, "capital": row[2] or 0.0}
    except:
        return {"profit": 0.0, "trades": 0, "capital": 0.0}

def draw_dashboard(stdscr):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(2000)
    
    while True:
        stdscr.clear()
        
        marco_stats = get_node_stats_extended("/home/marco/denaro/trades.db", "MARCODG1")
        nuvola_stats = get_node_stats_extended("/home/sergio/denaro/trades.db", "nuvola")
        
        total_pnl = marco_stats['profit'] + nuvola_stats['profit']
        total_trades = marco_stats['trades'] + nuvola_stats['trades']
        
        stdscr.addstr(0, 0, "=== DENARO DASHBOARD — LIVE STATUS ===", curses.A_BOLD)
        stdscr.addstr(1, 0, "Ultimo aggiornamento: " + datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        stdscr.addstr(2, 0, "Profitto Totale Oggi: {:.4f} EUR".format(total_pnl))
        stdscr.addstr(3, 0, "Trade Totali Oggi: {}".format(total_trades))
        stdscr.addstr(4, 0, "-" * 60)
        
        stdscr.addstr(6, 0, "[MOMENTUM] MARCODG1", curses.A_BOLD)
        stdscr.addstr(7, 0, "  Posizioni aperte: {}".format(marco_stats.get('open_positions',0)))
        stdscr.addstr(7, 35, "PnL chiuso: {:.4f} EUR".format(marco_stats.get('profit',0)))
        stdscr.addstr(8, 0, "  PnL floating:    {:.4f} EUR".format(marco_stats.get('unrealized_pnl',0)))
        stdscr.addstr(8, 35, "ROIC ieri: {:.2f}%".format(marco_stats.get('roic',0)))
        if marco_stats.get('filter_stats'):
            items = ', '.join(["{}:{}".format(k,v) for k,v in marco_stats['filter_stats'].items()])
            stdscr.addstr(9, 0, "  Filtri applicati: " + items)
        else:
            stdscr.addstr(9, 0, "  Filtri applicati: (nessuno)")
        
        stdscr.addstr(11, 0, "[GRID] nuvola", curses.A_BOLD)
        stdscr.addstr(12, 0, "  Posizioni aperte: {}".format(nuvola_stats.get('open_positions',0)))
        stdscr.addstr(12, 35, "PnL chiuso: {:.4f} EUR".format(nuvola_stats.get('profit',0)))
        stdscr.addstr(13, 0, "  PnL floating:    {:.4f} EUR".format(nuvola_stats.get('unrealized_pnl',0)))
        stdscr.addstr(13, 35, "ROIC ieri: {:.2f}%".format(nuvola_stats.get('roic',0)))
        
        funding_stats_marco = get_funding_stats("/home/marco/denaro/trades.db")
        funding_stats_nuvola = get_funding_stats("/home/sergio/denaro/trades.db")
        fund_profit = funding_stats_marco["profit"] + funding_stats_nuvola["profit"]
        fund_trades = funding_stats_marco["trades"] + funding_stats_nuvola["trades"]
        
        stdscr.addstr(15, 0, "[FUNDING] Somma nodi", curses.A_BOLD)
        stdscr.addstr(16, 0, "  Trade chiusi oggi: {} | PnL: {:.4f} EUR".format(fund_trades, fund_profit))
        
        stdscr.addstr(18, 0, "-" * 60)
        stdscr.addstr(19, 0, "Comandi: q=esci | r=refresh subito | any=attendi")
        stdscr.addstr(20, 0, "Log: ~/denaro/*.log | DB: ~/denaro/trades.db")
        
        key = stdscr.getch()
        if key == ord('q'):
            break
        elif key == ord('r'):
            pass
        
        stdscr.refresh()

if __name__ == "__main__":
    curses.wrapper(draw_dashboard)
