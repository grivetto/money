import sqlite3
import datetime
import os
import curses

def get_node_stats(db_path):
    if not os.path.exists(db_path):
        return {"profit": 0.0, "trades": 0}
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        today = datetime.date.today().isoformat()
        cursor.execute("SELECT SUM(net_pnl), COUNT(*) FROM trades WHERE DATE(exit_time) = ?", (today,))
        res = cursor.fetchone()
        conn.close()
        return {"profit": res[0] or 0.0, "trades": res[1]}
    except:
        return {"profit": 0.0, "trades": 0}

def draw_dashboard(stdscr):
    curses.curs_set(0)
    stdscr.nodelay(True)
    
    while True:
        stdscr.clear()
        
        # Aggiorna dati
        marco_stats = get_node_stats("/home/marco/denaro/trades.db")
        nuvola_stats = get_node_stats("/home/sergio/denaro/trades.db")
        
        total_pnl = marco_stats['profit'] + nuvola_stats['profit']
        
        stdscr.addstr(0, 0, "=== DENARO DASHBOARD - LIVE STATUS ===", curses.A_BOLD)
        stdscr.addstr(2, 0, f"Profitto Totale Oggi: {total_pnl:.4f}€")
        stdscr.addstr(3, 0, f"Totale Trade Oggi: {marco_stats['trades'] + nuvola_stats['trades']}")
        
        stdscr.addstr(5, 0, "--- Nodo: MARCODG1 (SOL/EUR) ---")
        stdscr.addstr(6, 0, f"Profitto: {marco_stats['profit']:.4f}€")
        stdscr.addstr(7, 0, f"Trade: {marco_stats['trades']}")
        
        stdscr.addstr(9, 0, "--- Nodo: Nuvola (BTC/EUR) ---")
        stdscr.addstr(10, 0, f"Profitto: {nuvola_stats['profit']:.4f}€")
        stdscr.addstr(11, 0, f"Trade: {nuvola_stats['trades']}")
        
        stdscr.addstr(14, 0, "Premi 'q' per uscire")
        
        stdscr.refresh()
        
        try:
            if stdscr.getkey() == 'q':
                break
        except:
            pass
        
        curses.napms(2000) # Update ogni 2s

if __name__ == "__main__":
    curses.wrapper(draw_dashboard)
