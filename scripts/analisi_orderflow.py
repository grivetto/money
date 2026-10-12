#!/usr/bin/env python3
"""Order-flow imbalance su molti giorni di tick Bybit: statistica seria.

Per ogni giorno: aggrega i tick per minuto (volume aggressore Buy/Sell, chiusura),
poi forma la coppia (imbalance del minuto m, rendimento realizzato nel minuto m+1).
I minuti vuoti rompono la catena (non si inventa un rendimento).

Sola analisi su dati pubblici. Nessun ordine.
"""
import csv
import glob
import gzip
import math
import statistics
import sys
from collections import defaultdict


def analizza(simbolo: str, cartella: str = "data/tick"):
    coppie: list[tuple[float, float]] = []
    tot_trade = 0
    file_fatti = 0
    for f in sorted(glob.glob(f"{cartella}/{simbolo}_*.csv.gz")):
        buy: dict[int, float] = defaultdict(float)
        sell: dict[int, float] = defaultdict(float)
        close: dict[int, float] = {}
        with gzip.open(f, "rt") as fh:
            r = csv.reader(fh)
            next(r)
            for row in r:
                ts = float(row[0])
                side = row[2]
                size = float(row[3])
                px = float(row[4])
                m = int(ts // 60)
                if side == "Buy":
                    buy[m] += size
                else:
                    sell[m] += size
                close[m] = px
                tot_trade += 1
        file_fatti += 1
        mins = sorted(close)
        for a, b in zip(mins, mins[1:]):
            if b - a != 1:
                continue
            v = buy[a] + sell[a]
            if v <= 0:
                continue
            coppie.append(((buy[a] - sell[a]) / v, (close[b] - close[a]) / close[a]))
    return coppie, tot_trade, file_fatti


def stat(coppie):
    n = len(coppie)
    x = [a for a, _ in coppie]
    y = [b for _, b in coppie]
    mx, my = statistics.mean(x), statistics.mean(y)
    sx = statistics.pstdev(x) or 1e-12
    sy = statistics.pstdev(y) or 1e-12
    cov = sum((a - mx) * (b - my) for a, b in zip(x, y)) / n
    corr = cov / (sx * sy)
    t = corr * math.sqrt(max(n - 2, 1)) / math.sqrt(max(1 - corr * corr, 1e-12))
    return corr, t, n, sx, sy


def main():
    simbolo = sys.argv[1] if len(sys.argv) > 1 else "DOGEUSDT"
    fee_rt = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0011  # taker RT perp 0.11%
    coppie, n_trade, n_file = analizza(simbolo)
    print(f"=== {simbolo}: {n_file} giorni, {n_trade:,} trade, {len(coppie):,} minuti ===")
    if not coppie:
        print("nessuna coppia")
        return
    corr, t, n, sx, sy = stat(coppie)
    print(f"corr(imb[m], rend[m+1]) = {corr:+.4f}  (t={t:+.2f}, n={n:,}, "
          f"sd_imb={sx:.3f} sd_rend={sy:.5%})")
    print()
    print(f"{'soglia':>7s} {'n':>7s} {'exp.lorda':>12s} {'exp.netta':>12s} {'t-stat':>8s} {'hit%':>6s}")
    for soglia in (0.05, 0.10, 0.20, 0.30, 0.40, 0.50):
        pnl = [r if i > soglia else (-r if i < -soglia else 0.0) for i, r in coppie]
        op = [p for p in pnl if p != 0.0]
        if len(op) < 20:
            continue
        exp = statistics.mean(op)
        sd = statistics.pstdev(op) or 1e-12
        tt = exp / (sd / math.sqrt(len(op)))
        hit = sum(1 for p in op if p > 0) / len(op)
        print(f"{soglia:7.2f} {len(op):7d} {exp:+11.5%} {exp - fee_rt:+11.5%} "
              f"{tt:+8.2f} {hit:5.1%}")
    print()
    print("invertito (contrarian): se il flusso predice, invertire deve perdere")
    for soglia in (0.20, 0.40):
        pnl = [-r if i > soglia else (r if i < -soglia else 0.0) for i, r in coppie]
        op = [p for p in pnl if p != 0.0]
        if len(op) >= 20:
            exp = statistics.mean(op)
            print(f"  soglia {soglia:.2f}: n={len(op):6d} exp.lorda={exp:+.5%}")


if __name__ == "__main__":
    main()
