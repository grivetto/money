#!/usr/bin/env python3
"""Caricatore dati microstruttura per micro_edge (numpy, no pandas).

Carica:
- ohlcv_xperp.jsonl (BTC/USDT, ETH/USDT, 5m, OKX)
- tick Bybit DOGE/SOL (per-day gzip csv)
- l2 OKX BTC-EUR snapshots jsonl
"""
import csv, gzip, glob, json, numpy as np

DATA = "/home/sergio/money/data"

def load_ohlcv(symbol="BTC/USDT"):
    ts, o, h, l, c, v = [], [], [], [], [], []
    with open(f"{DATA}/ohlcv_xperp.jsonl") as f:
        for line in f:
            r = json.loads(line)
            if r["simbolo"] != symbol:
                continue
            ts.append(r["ts"] / 1000.0)
            o.append(r["open"]); h.append(r["high"]); l.append(r["low"]); c.append(r["close"]); v.append(r["volume"])
    ts = np.array(ts); o = np.array(o); h = np.array(h); l = np.array(l); c = np.array(c); v = np.array(v)
    # dedupe: alcuni slot 5m hanno piu' record (25%); tiene l'ultimo per slot
    uniq, idx = np.unique(ts, return_index=True)
    keep = np.full(len(ts), False)
    # l'ultima occorrenza di ogni ts
    last = {}
    for i, t in enumerate(ts):
        last[t] = i
    keep[list(last.values())] = True
    return {k: x[keep] for k, x in zip(
        ["ts", "open", "high", "low", "close", "volume"], [ts, o, h, l, c, v])}

def load_tick_day(fn):
    """Ritorna (ts, side_buy_bool, size, px) per un file giornaliero."""
    ts, buy, sz, px = [], [], [], []
    with gzip.open(fn, "rt") as fh:
        r = csv.reader(fh); next(r)
        for row in r:
            if len(row) < 5 or row[0] == "":
                continue
            ts.append(float(row[0])); buy.append(1.0 if row[2] == "Buy" else -1.0)
            sz.append(float(row[3])); px.append(float(row[4]))
    return (np.array(ts), np.array(buy), np.array(sz), np.array(px))

def load_l2(files):
    rows = []
    for fn in files:
        with open(fn) as f:
            for line in f:
                if not line.strip():
                    continue
                r = json.loads(line)
                if r.get("mid", 0) <= 0:
                    continue
                rows.append(r)
    return rows
