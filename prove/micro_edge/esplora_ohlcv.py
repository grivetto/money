#!/usr/bin/env python3
"""Esplorazione preliminare: statistiche base 5-min BTC/ETH OKX."""
import sys, numpy as np
sys.path.insert(0, "/home/sergio/money/prove/micro_edge")
from loaders import load_ohlcv

for sym in ["BTC/USDT", "ETH/USDT"]:
    d = load_ohlcv(sym)
    c, h, l = d["close"], d["high"], d["low"]
    r = np.diff(np.log(c))
    print(f"== {sym} ==  bars={len(c)}  {c[0]:.0f} -> {c[-1]:.0f}")
    print(f"  ret 5m: mean={r.mean()*1e6:.2f} bps  std={r.std()*1e4:.2f} bps  median={np.median(r)*1e4:.3f} bps")
    for lag in (1, 2, 3, 6, 12, 36, 72):
        rr = np.corrcoef(r[lag:], r[:-lag])[0, 1]
        n = len(r) - lag
        print(f"  autocorr lag{lag}: {rr:+.4f}  (t-stat={rr*np.sqrt(n-2)/np.sqrt(1-rr*rr):+.1f})")
    # proxy spread (h-l)/mid — limite superiore dello spread 5m
    hl = (h - l) / c * 1e4
    print(f"  (h-l)/mid: mediana={np.median(hl):.2f} bps  p25={np.percentile(hl,25):.2f}  p75={np.percentile(hl,75):.2f}")
    # quanto deve muoversi per superare round-trip 28bps? quota bar |r|>14bps
    print(f"  quota bar |r|>14bps: {(np.abs(r)*1e4>14).mean()*100:.1f}%   |r|>28bps: {(np.abs(r)*1e4>28).mean()*100:.1f}%")
    # vol EWMA
    v = np.abs(r)
    ew = np.empty_like(v); ew[0] = v[:288].mean()
    for i in range(1, len(v)):
        ew[i] = 0.97 * ew[i-1] + 0.03 * v[i]
    print(f"  vol EWMA 0.03 mediana={np.median(ew)*1e4:.2f} bps  p90={np.percentile(ew,90)*1e4:.2f}")
