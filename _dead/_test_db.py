"""Test rapido accesso DB."""
import sys
sys.path.insert(0, '/home/sergio/denaro')

from trade_db import TradeDB
import os

db_path = '/home/sergio/denaro/trades.db'
print(f"Tentativo apertura: {db_path}")
print(f"Esiste: {os.path.exists(db_path)}")
print(f"Dir esiste: {os.path.isdir('/home/sergio/denaro')}")

try:
    # Forza creazione con path assoluto
    db = TradeDB(db_path)
    print(f"DB aperto OK: {db.db_path}")

    # Test scrittura
    with __import__('sqlite3').connect(db_path) as conn:
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        print(f"Tabelle: {[t[0] for t in tables]}")
except Exception as e:
    print(f"ERRORE: {e}")
    import traceback
    traceback.print_exc()