#!/usr/bin/env python3
"""backtest_onchain.py — strategie da segnali on-chain/sentiment + confronto buy&hold.

DISCIPLINA
==========
Il setaccio dice dove guardare, non se c'e' edge. Qui si fanno i conti veri:
- regole DICHIARATE A PRIORI (soglie classiche MVRV/F&G), non ottimizzate sui dati;
- fee a ogni cambio di posizione (0.18% round-trip, taker EEA);
- confronto esplicito con BUY & HOLD: una strategia long/flat batte il mercato solo
  se la sua equity finale e il suo Sharpe out-of-sample sono migliori;
- lettura per REGIME (bull/bear), perche' su BTC 2011-2026 qualunque cosa crescente
  "funziona" in-sample: l'unico test che conta e' il bear market e l'out-of-sample.

Sola analisi su dati pubblici. Nessun ordine.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EST = ROOT / "data" / "esterni"
FEE_RT = 0.0018          # taker round-trip EEA (cambio di posizione)
REND_FLAT = 0.05 / 365   # il capitale flat rende in Earn (~5%/anno), non zero


def carica_serie(asset: str, metrica: str) -> dict[str, float]:
    p = EST / f"onchain_{asset}.json"
    if not p.exists():
        return {}
    d = json.loads(p.read_text(encoding="utf-8"))
    s = d.get(metrica) or {}
    return {t: float(v) for t, v in s.items()}


def media_mobile(serie: dict[str, float], finestra: int) -> dict[str, float]:
    date = sorted(serie)
    out = {}
    for i in range(finestra, len(date)):
        fin = [serie[t] for t in date[i - finestra:i]]
        out[date[i]] = sum(fin) / finestra
    return out


def stats(eq: list[float]) -> tuple[float, float, float]:
    """(rendimento totale, sharpe annualizzato, max drawdown)"""
    if len(eq) < 30:
        return 0.0, 0.0, 0.0
    rend = [eq[i] / eq[i - 1] - 1 for i in range(1, len(eq))]
    mu = sum(rend) / len(rend)
    sd = math.sqrt(sum((r - mu) ** 2 for r in rend) / len(rend)) or 1e-12
    sharpe = mu / sd * math.sqrt(365)
    picco = eq[0]
    dd = 0.0
    for v in eq:
        picco = max(picco, v)
        dd = min(dd, v / picco - 1)
    return eq[-1] / eq[0] - 1, sharpe, dd


def backtest(px: dict[str, float], pos: dict[str, int]) -> tuple[list[float], int]:
    date = sorted(px)
    eq = [1.0]
    n_trade = 0
    prec = 0
    for i in range(len(date) - 1):
        t, tn = date[i], date[i + 1]
        p = pos.get(t)
        if p is None:
            p = prec
        if p != prec:
            eq[-1] *= (1 - FEE_RT)
            n_trade += 1
        r = px[tn] / px[t] - 1 if px[t] > 0 else 0.0
        eq.append(eq[-1] * (1 + (r if p else REND_FLAT)))
        prec = p
    return eq, n_trade


def buy_hold(px: dict[str, float]) -> list[float]:
    date = sorted(px)
    eq = [1.0]
    for i in range(len(date) - 1):
        r = px[date[i + 1]] / px[date[i]] - 1 if px[date[i]] > 0 else 0.0
        eq.append(eq[-1] * (1 + r))
    return eq


def valuta(nome: str, px: dict[str, float], pos: dict[str, int], taglio: str | None = None):
    if taglio:
        px = {t: v for t, v in px.items() if t >= taglio}
        pos = {t: v for t, v in pos.items() if t in px}
    if len(px) < 200:
        return
    eq, n = backtest(px, pos)
    bh = buy_hold(px)
    r, s, dd = stats(eq)
    rb, sb, ddb = stats(bh)
    print(f"  {nome:34s} ret={r:+8.1%} sharpe={s:+5.2f} maxDD={dd:+6.1%} "
          f"| B&H ret={rb:+8.1%} sharpe={sb:+5.2f} maxDD={ddb:+6.1%} | trade={n}")


def main() -> int:
    for asset in ("btc", "eth"):
        px = carica_serie(asset, "PriceUSD")
        if not px:
            continue
        mvrv = carica_serie(asset, "CapMVRVCur")
        med = media_mobile(mvrv, 180)
        print(f"\n===== {asset.upper()} ({len(px)} giorni) =====")

        # A) MVRV value (classico): long quando sottovalutato, fuori quando euforico
        print(" [tutto il campione]")
        valuta("A. MVRV value (long <1.5, out >3.0)",
               px, {t: (1 if mvrv.get(t, 99) < 1.5 else (0 if mvrv.get(t, 99) > 3.0 else 1))
                    for t in px})
        # B) MVRV momentum: long se sopra media 180g
        valuta("B. MVRV momentum (> media 180g)",
               px, {t: (1 if t in med and mvrv.get(t, 0) > med[t] else 0) for t in px})
        # C) MVRV contrarian: long se sotto media 180g
        valuta("C. MVRV contrarian (< media 180g)",
               px, {t: (1 if t in med and mvrv.get(t, 0) < med[t] else 0) for t in px})

        print(" [out-of-sample: dal 2021-01-01]")
        valuta("A. MVRV value", px,
               {t: (1 if mvrv.get(t, 99) < 1.5 else (0 if mvrv.get(t, 99) > 3.0 else 1))
                for t in px}, taglio="2021-01-01")
        valuta("B. MVRV momentum", px,
               {t: (1 if t in med and mvrv.get(t, 0) > med[t] else 0) for t in px},
               taglio="2021-01-01")
        valuta("C. MVRV contrarian", px,
               {t: (1 if t in med and mvrv.get(t, 0) < med[t] else 0) for t in px},
               taglio="2021-01-01")

    # Fear & Greed
    fp = EST / "sentiment_fng.json"
    if fp.exists():
        import datetime as dt
        fng = json.loads(fp.read_text(encoding="utf-8"))
        fmap = {dt.datetime.fromtimestamp(int(k), dt.timezone.utc).date().isoformat(): float(v["valore"])
                for k, v in fng.items()}
        for asset in ("btc", "eth"):
            px_all = carica_serie(asset, "PriceUSD")
            px = {t: px_all[t] for t in px_all if t in fmap}
            if len(px) < 400:
                continue
            print(f"\n===== {asset.upper()} x FEAR&GREED ({len(px)} giorni, dal 2018) =====")
            print(" [tutto il campione]")
            valuta("D. F&G contrarian (long <25)",
                   px, {t: (1 if fmap[t] < 25 else 0) for t in px})
            valuta("E. F&G momentum (long >50)",
                   px, {t: (1 if fmap[t] > 50 else 0) for t in px})
            valuta("F. F&G estremi (<20 long, >80 flat)",
                   px, {t: (1 if fmap[t] < 20 else (0 if fmap[t] > 80 else 1)) for t in px})
            print(" [out-of-sample: dal 2021-01-01]")
            valuta("D. F&G contrarian", px, {t: (1 if fmap[t] < 25 else 0) for t in px},
                   taglio="2021-01-01")
            valuta("E. F&G momentum", px, {t: (1 if fmap[t] > 50 else 0) for t in px},
                   taglio="2021-01-01")
            valuta("F. F&G estremi", px,
                   {t: (1 if fmap[t] < 20 else (0 if fmap[t] > 80 else 1)) for t in px},
                   taglio="2021-01-01")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
