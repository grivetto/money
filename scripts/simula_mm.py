#!/usr/bin/env python3
"""simula_mm.py — simulazione di market making su tick reali Bybit.

MODELLO (dichiarato, ottimistico di proposito)
==============================================
Un solo lato alla volta, quotazione passiva attorno all'ultimo prezzo:
- flat: piazzo un BID a `px*(1-delta)`, lo tengo fermo; se un trade aggressore
  Sell tocca il mio livello o scende sotto, sono RIEMPITO (maker). Riposiziono
  dopo `riquot` secondi se non riempito.
- in posizione: piazzo l'ASK di uscita a `entry*(1+target)`; se un trade Buy lo
  tocca, chiudo (maker). Se passa `timeout`, chiudo AL MERCATO (taker) = perdita
  da adverse selection, che e' il costo vero del MM.

Il fill "per attraversamento" assume che il mio ordine sia in cima al book a quel
livello: e' un UPPER BOUND del fill rate. Se anche l'upper bound e' negativo, il
market making e' morto senza appello. Fee maker/taker sono parametri espliciti.

Sola simulazione su dati pubblici. Nessun ordine reale.
"""
from __future__ import annotations

import csv
import glob
import gzip
import math
import statistics
import sys


def simula(files: list[str], delta_bps: float, target_bps: float, timeout_s: float,
           riquot_s: float = 60.0, fee_maker: float = 0.0002, fee_taker: float = 0.00055):
    delta = delta_bps / 10_000
    target = target_bps / 10_000
    inv = 0.0          # 1 = long, -1 = flat/short non usato qui
    entry = 0.0
    entry_t = 0.0
    bid = None
    bid_t = 0.0
    pnl: list[float] = []
    n_fill = 0
    n_timeout = 0
    attesa: list[float] = []

    for f in sorted(files):
        with gzip.open(f, "rt") as fh:
            r = csv.reader(fh)
            next(r)
            for row in r:
                ts = float(row[0]); side = row[2]; px = float(row[4])
                if inv == 0.0:
                    if bid is None or ts - bid_t > riquot_s:
                        bid = px * (1 - delta); bid_t = ts
                    if side == "Sell" and px <= bid:
                        inv = 1.0; entry = bid; entry_t = ts          # comprato maker
                        n_fill += 1
                        bid = None
                else:
                    uscita = entry * (1 + target)
                    if side == "Buy" and px >= uscita:
                        pnl.append((uscita - entry) / entry - 2 * fee_maker)
                        attesa.append(ts - entry_t)
                        inv = 0.0
                    elif ts - entry_t > timeout_s:
                        pnl.append((px - entry) / entry - fee_maker - fee_taker)
                        attesa.append(ts - entry_t)
                        n_timeout += 1
                        inv = 0.0
                        bid = None
    return pnl, n_fill, n_timeout, attesa, delta_bps, target_bps, timeout_s


def report(simbolo: str, cartella: str = "data/tick"):
    import os
    if simbolo != "TUTTI":
        files = sorted(glob.glob(f"{cartella}/{simbolo}_*.csv.gz"))
    else:
        files = sorted(glob.glob(f"{cartella}/*.csv.gz"))
    limite = int(os.environ.get("MM_GIORNI", "0"))
    if limite:
        files = files[-limite:]
    if not files:
        print(f"{simbolo}: nessun file")
        return
    print(f"=== {simbolo}: {len(files)} giorni, fee maker 2bps / taker 5.5bps (Bybit perp) ===")
    print(f"{'delta':>5s} {'target':>7s} {'timeout':>7s} {'fill':>6s} {'to':>5s} "
          f"{'exp.netta':>10s} {'hit%':>6s} {'t-stat':>7s} {'attesa':>8s}")
    for delta in (1, 2, 5, 10, 20):
        for timeout in (300, 900):
            pnl, nf, nt, att, d, tg, to = simula(files, delta, delta, timeout)
            if len(pnl) < 30:
                continue
            media = statistics.mean(pnl)
            sd = statistics.pstdev(pnl) or 1e-12
            t = media / (sd / math.sqrt(len(pnl)))
            hit = sum(1 for p in pnl if p > 0) / len(pnl)
            print(f"{d:5.1f} {tg:7.1f} {to:7.0f} {nf:6d} {nt:5d} "
                  f"{media:+10.5%} {hit:5.1%} {t:+7.2f} {statistics.median(att):7.0f}s")


if __name__ == "__main__":
    for s in (sys.argv[1:] or ["DOGEUSDT"]):
        report(s)
        print()
