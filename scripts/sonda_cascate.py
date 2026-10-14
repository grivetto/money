#!/usr/bin/env python3
"""Sonda E2 — cascate di liquidazione: «caduta violenta + volume anomalo → rimbalzo?».

E' una SONDA, non un verdetto: nessun cancello, nessun DSR. Serve a decidere SE la
pista E2 merita il backtest completo (stop ATR, intra-barra, 59 simboli, giudice).

Definizione dell'evento (a priori, dichiarata QUI prima di guardare i numeri):
  evento in i  <=>  c[i]/c[i-3] - 1 <= soglia_drop   (caduta in 3 ore)
                e  v[i] / media(v[i-72:i]) >= 3.0   (volume anomalo)
                e  cooldown di 12 barre dall'ultimo evento contato.

Misura: acquisto alla CHIUSURA di i (proxy esecuzione market), uscita alla chiusura
di i+H. Costi reali: 0,26% round-trip (0,18% giro misto OKX + 0,08% slippage), piu'
la versione LORDA per capire da dove viene cosa.

Uso:  .venv/bin/python scripts/sonda_cascate.py [--simboli DOGE-USDT,SOL-USDT,...]
"""
from __future__ import annotations

import argparse
import json
import math
import statistics as st
import sys
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
CACHE = RADICE / "data" / "cache"

COSTO_RT = 0.0018 + 2 * 0.0004   # giro misto OKX + slippage per lato (come in scansione)
SOGLIE_DROP = (-0.05, -0.06, -0.08)
SOGLIA_VOL = 3.0
COOLDOWN = 12
ORIZZONTI = (4, 12, 24)
SIMBOLI_DEFAULT = "DOGE-USDT,SOL-USDT,XRP-USDT,AVAX-USDT,LINK-USDT,BTC-USDT,ETH-USDT"


def carica(simbolo: str) -> tuple:
    p = CACHE / f"bybit_{simbolo}_1h.json"
    d = json.loads(p.read_text())
    barre = d["barre"]
    ts = [b[0] for b in barre]
    ch = [float(b[4]) for b in barre]
    vo = [float(b[5]) for b in barre]
    return ts, ch, vo


def eventi(ch: list, vo: list, soglia_drop: float) -> list:
    """Indici degli eventi con cooldown. Volume: confronto con la media delle 72 barre PRIMA."""
    fuori = []
    ultimo = -10**9
    for i in range(72, len(ch) - max(ORIZZONTI)):
        if i - ultimo <= COOLDOWN:
            continue
        base_vol = sum(vo[i - 72:i]) / 72.0
        if base_vol <= 0 or vo[i] <= 0:
            continue
        drop3 = ch[i] / ch[i - 3] - 1.0
        if drop3 <= soglia_drop and vo[i] / base_vol >= SOGLIA_VOL:
            fuori.append(i)
            ultimo = i
    return fuori


def statistiche(xs: list) -> tuple:
    n = len(xs)
    if n < 2:
        return n, float("nan"), float("nan")
    m = sum(xs) / n
    sd = st.stdev(xs)
    t = m / (sd / math.sqrt(n)) if sd > 0 else float("nan")
    return n, m, t


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--simboli", default=SIMBOLI_DEFAULT)
    a = ap.parse_args()
    simboli = [s.strip() for s in a.simboli.split(",") if s.strip()]

    dati = {}
    for s in simboli:
        try:
            dati[s] = carica(s)
        except FileNotFoundError:
            print(f"  (salto {s}: cache assente)")

    print(f"SONDA E2 — cascate 1h | costi netti {COSTO_RT:.2%} RT | cooldown {COOLDOWN}h")
    print(f"finestra: {min(d[0][0] for d in dati.values())} -> {max(d[0][-1] for d in dati.values())}"
          f" | simboli: {len(dati)}")
    print()
    tot_barre = sum(len(d[1]) for d in dati.values())
    for soglia in SOGLIE_DROP:
        per_simbolo = {}
        for s, (ts, ch, vo) in dati.items():
            per_simbolo[s] = eventi(ch, vo, soglia)
        n_tot = sum(len(v) for v in per_simbolo.values())
        print(f"--- drop <= {soglia:.0%} & volume >= {SOGLIA_VOL:.1f}x (72h) --- "
              f"eventi: {n_tot} su {tot_barre} barre ({n_tot / tot_barre:.2%})")
        for h in ORIZZONTI:
            lordi, netti = [], []
            for s, (ts, ch, vo) in dati.items():
                for i in per_simbolo[s]:
                    if i + h < len(ch):
                        r = ch[i + h] / ch[i] - 1.0
                        lordi.append(r)
                        netti.append(r - COSTO_RT)
            n, ml, _ = statistiche(lordi)
            _, mn, tn = statistiche(netti)
            quota = sum(1 for x in netti if x > 0) / n if n else float("nan")
            print(f"  H={h:2d}h  n={n:4d}  lordo {ml:+.3%}  netto {mn:+.3%} (t {tn:5.2f}, "
                  f"pos {quota:.0%})")
        print()

    # vista per anno sul solo H=12 (stabilita' del segno)
    print("--- per anno, drop <= -6%, H=12h (netto) ---")
    lordi = []
    righe = {}
    for s, (ts, ch, vo) in dati.items():
        for i in eventi(ch, vo, -0.06):
            if i + 12 < len(ch):
                anno = ts[i] // 31536000000 + 1970
                r = ch[i + 12] / ch[i] - 1.0 - COSTO_RT
                righe.setdefault(anno, []).append(r)
    for anno in sorted(righe):
        n, m, t = statistiche(righe[anno])
        print(f"  {anno}: n={n:4d}  netto {m:+.3%} (t {t:5.2f})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
