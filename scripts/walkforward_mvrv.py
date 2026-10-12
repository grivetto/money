#!/usr/bin/env python3
"""walkforward_mvrv.py — MVRV momentum sotto lo stesso stress di F&G.

Se per anno, con split genuini e con sensibilita' alla finestra, il segnale non regge,
allora la pista on-chain/sentiment e' chiusa come le altre e va detto senza addolcire.

Sola analisi su dati pubblici. Nessun ordine.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EST = ROOT / "data" / "esterni"
FEE_RT = 0.0018
REND_FLAT = 0.05 / 365
ASSET = ("btc", "eth", "xrp", "ada", "doge", "ltc", "link", "dot", "bch", "xlm")


def serie(asset: str, metrica: str) -> dict[str, float]:
    p = EST / f"onchain_{asset}.json"
    if not p.exists():
        return {}
    d = json.loads(p.read_text(encoding="utf-8"))
    return {t: float(v) for t, v in (d.get(metrica) or {}).items()}


def sma(s: dict[str, float], n: int) -> dict[str, float]:
    date = sorted(s)
    return {date[i]: sum(s[t] for t in date[i - n:i]) / n for i in range(n, len(date))}


def per_anno(px: dict[str, float], pos: dict[str, int]):
    date = sorted(px)
    eq = 1.0
    prec = 0
    n = 0
    pa: dict[str, float] = {}
    a_eq = 1.0
    a_cor = date[0][:4]
    for i in range(len(date) - 1):
        t, tn = date[i], date[i + 1]
        p = pos.get(t, prec)
        if p != prec:
            eq *= (1 - FEE_RT)
            n += 1
        r = px[tn] / px[t] - 1 if px[t] > 0 else 0.0
        eq *= (1 + (r if p else REND_FLAT))
        anno = tn[:4]
        if anno != a_cor:
            pa[a_cor] = a_eq
            a_eq = 1.0
            a_cor = anno
        a_eq *= (1 + (r if p else REND_FLAT))
    pa[a_cor] = a_eq
    return eq, n, pa


def bh(px: dict[str, float]):
    date = sorted(px)
    eq = 1.0
    for i in range(len(date) - 1):
        eq *= 1 + (px[date[i + 1]] / px[date[i]] - 1 if px[date[i]] > 0 else 0.0)
    return eq


def val(px, pos):
    eq, n, _ = per_anno(px, pos)
    return eq, n


def main() -> int:
    print("=== MVRV > media 180g (momentum) — PER ANNO, vs buy&hold ===")
    print(f"{'asset':6s} " + " ".join(f"{y:>7s}" for y in ("2018", "2020", "2021", "2022", "2023", "2024", "2025", "2026")) + "    TOT    vs B&H")
    for a in ASSET:
        px = serie(a, "PriceUSD")
        mvrv = serie(a, "CapMVRVCur")
        if len(px) < 500 or len(mvrv) < 500:
            continue
        med = sma(mvrv, 180)
        pos = {t: (1 if t in med and mvrv.get(t, 0) > med[t] else 0) for t in px}
        eq, n, pa = per_anno(px, pos)
        b = bh(px)
        riga = f"{a:6s} "
        for y in ("2018", "2020", "2021", "2022", "2023", "2024", "2025", "2026"):
            v = pa.get(y)
            riga += f"{v-1:+6.0%} " if v is not None else f"{'':>7s} "
        print(riga + f"{eq-1:+7.0%} {eq-1-(b-1):+8.0%}")

    print("\n=== SPLIT GENUINI (MVRV > media 180g) ===")
    for a in ("btc", "eth", "doge", "ada"):
        px = serie(a, "PriceUSD")
        mvrv = serie(a, "CapMVRVCur")
        if len(px) < 500 or len(mvrv) < 500:
            continue
        med = sma(mvrv, 180)
        pos = {t: (1 if t in med and mvrv.get(t, 0) > med[t] else 0) for t in px}
        print(f"\n--- {a.upper()} ---")
        for eti, d0, d1 in (("train 2018-2020", "2018-01-01", "2021-01-01"),
                            ("OOS-1 2021-2022", "2021-01-01", "2023-01-01"),
                            ("OOS-2 2023-2026", "2023-01-01", "2027-01-01"),
                            ("OOS 2021-2026", "2021-01-01", "2027-01-01")):
            pxf = {t: v for t, v in px.items() if d0 <= t < d1}
            if len(pxf) < 200:
                continue
            eq, n = val(pxf, {t: v for t, v in pos.items() if t in pxf})
            bhf = bh(pxf)
            print(f"   {eti:16s} segnale={eq-1:+9.1%} n={n:3d} | B&H={bhf-1:+9.1%}"
                  f" | {'VINCE' if eq > bhf else 'perde'}")

    print("\n=== SENSIBILITA' ALLA FINESTRA (OOS 2021-2026) ===")
    for a in ("btc", "eth", "doge"):
        px = serie(a, "PriceUSD")
        mvrv = serie(a, "CapMVRVCur")
        if len(px) < 500 or len(mvrv) < 500:
            continue
        pxo = {t: v for t, v in px.items() if t >= "2021-01-01"}
        riga = f"{a:5s} "
        for w in (60, 90, 120, 180, 250, 365):
            med = sma(mvrv, w)
            pos = {t: (1 if t in med and mvrv.get(t, 0) > med[t] else 0) for t in pxo}
            eq, n = val(pxo, pos)
            riga += f"|{w}:{eq-1:+8.0%} "
        print(riga)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
