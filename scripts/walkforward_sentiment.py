#!/usr/bin/env python3
"""walkforward_sentiment.py — il segnale regge per REGIME e in out-of-sample vero?

DISCIPLINA (dove i segnali di sentiment/on-chain muoiono)
========================================================
1. lettura PER ANNO: un segnale che vive del bull 2021 e del bull 2023-26 ma non
   protegge nel bear 2022 non e' un edge, e' una scommessa sul regime.
2. SPLIT TEMPORALI genuini: addestro/sceglgo la regola su un periodo e la applico
   al successivo, senza riottimizzare.
3. FEE a ogni cambio: F&G>50 fa ~30 trade/anno -> 0.18% x 30 = 5.4%/anno di pedaggio.
   Il numero finale e' al netto.
4. CONFRONTO con B&H: long/flat deve battere il semplice "compra e tieni", altrimenti
   non aggiunge nulla.

Sola analisi su dati pubblici. Nessun ordine.
"""
from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EST = ROOT / "data" / "esterni"
FEE_RT = 0.0018
REND_FLAT = 0.05 / 365


def serie(asset: str, metrica: str) -> dict[str, float]:
    p = EST / f"onchain_{asset}.json"
    if not p.exists():
        return {}
    d = json.loads(p.read_text(encoding="utf-8"))
    return {t: float(v) for t, v in (d.get(metrica) or {}).items()}


def sma(s: dict[str, float], n: int) -> dict[str, float]:
    date = sorted(s)
    return {date[i]: sum(s[t] for t in date[i - n:i]) / n for i in range(n, len(date))}


def bt_anni(px: dict[str, float], pos: dict[str, int], per_anno: bool = False):
    date = sorted(px)
    eq = 1.0
    prec = 0
    n = 0
    per_anno_eq: dict[str, float] = {}
    anno_eq = 1.0
    anno_cor = date[0][:4]
    for i in range(len(date) - 1):
        t, tn = date[i], date[i + 1]
        p = pos.get(t, prec)
        if p != prec:
            eq *= (1 - FEE_RT)
            n += 1
        r = px[tn] / px[t] - 1 if px[t] > 0 else 0.0
        eq *= (1 + (r if p else REND_FLAT))
        if per_anno:
            anno = tn[:4]
            if anno != anno_cor:
                per_anno_eq[anno_cor] = anno_eq
                anno_eq = 1.0
                anno_cor = anno
            anno_eq *= (1 + (r if p else REND_FLAT))
    if per_anno:
        per_anno_eq[anno_cor] = anno_eq
        return eq, n, per_anno_eq
    return eq, n, {}


def bh_anni(px: dict[str, float]):
    date = sorted(px)
    per_anno = {}
    eq = 1.0
    anno_eq = 1.0
    anno_cor = date[0][:4]
    for i in range(len(date) - 1):
        r = px[date[i + 1]] / px[date[i]] - 1 if px[date[i]] > 0 else 0.0
        anno = date[i + 1][:4]
        if anno != anno_cor:
            per_anno[anno_cor] = anno_eq
            anno_eq = 1.0
            anno_cor = anno
        anno_eq *= (1 + r)
        eq *= (1 + r)
    per_anno[anno_cor] = anno_eq
    return eq, per_anno


def main() -> int:
    fng_raw = json.loads((EST / "sentiment_fng.json").read_text(encoding="utf-8"))
    fmap = {dt.datetime.fromtimestamp(int(k), dt.timezone.utc).date().isoformat(): float(v["valore"])
            for k, v in fng_raw.items()}

    print("=== F&G > 50 (long se greed) — rendimento PER ANNO ===")
    print(f"{'asset':6s} " + " ".join(f"{y:>8s}" for y in
          ("2018", "2019", "2020", "2021", "2022", "2023", "2024", "2025", "2026")))
    for a in ("btc", "eth", "xrp", "ada", "doge", "ltc", "link", "dot", "bch", "xlm"):
        px_all = serie(a, "PriceUSD")
        px = {t: px_all[t] for t in px_all if t in fmap}
        if len(px) < 500:
            continue
        pos = {t: (1 if fmap[t] > 50 else 0) for t in px}
        eq, n, pa = bt_anni(px, pos, per_anno=True)
        _, pa_bh = bh_anni(px)
        riga = f"{a:6s} "
        for y in ("2018", "2019", "2020", "2021", "2022", "2023", "2024", "2025", "2026"):
            v = pa.get(y)
            b = pa_bh.get(y, v)
            if v is None:
                riga += f"{'':>8s} "
            else:
                # mostro il segnale / B&H: il segnale deve proteggere nel bear
                diff = v - b
                riga += f"{v-1:+7.0%}{'*' if diff > 0 else ' '}"
        print(riga + f"  tot={eq-1:+.1%} n={n}")

    print("\n(* = segnale batte buy&hold in quell'anno)")
    print("\n=== SPLIT TEMPORALI GENUINI (regola fissa, nessuna riottimizzazione) ===")
    for a in ("btc", "eth", "doge"):
        px_all = serie(a, "PriceUSD")
        px = {t: px_all[t] for t in px_all if t in fmap}
        pos = {t: (1 if fmap[t] > 50 else 0) for t in px}
        print(f"\n--- {a.upper()} ---")
        for eti, d0, d1 in (("train 2018-2020", "2018-01-01", "2021-01-01"),
                            ("OOS-1 2021-2022", "2021-01-01", "2023-01-01"),
                            ("OOS-2 2023-2026", "2023-01-01", "2027-01-01"),
                            ("OOS 2021-2026", "2021-01-01", "2027-01-01")):
            pxf = {t: v for t, v in px.items() if d0 <= t < d1}
            if len(pxf) < 200:
                continue
            eq, n, _ = bt_anni(pxf, pos)
            bh, _ = bh_anni(pxf)
            print(f"   {eti:16s} segnale={eq-1:+9.1%} n={n:3d}  |  B&H={bh-1:+9.1%}"
                  f"  |  {'VINCE' if eq > bh else 'perde'}")

    print("\n=== SOGLIA: sensibilita' (mostra se e' robusto o curve-fit) ===")
    for a in ("btc", "eth", "doge"):
        px_all = serie(a, "PriceUSD")
        px = {t: px_all[t] for t in px_all if t in fmap}
        pxo = {t: v for t, v in px.items() if t >= "2021-01-01"}
        riga = f"{a:5s} "
        for soglia in (20, 30, 40, 50, 60, 70):
            pos = {t: (1 if fmap[t] > soglia else 0) for t in pxo}
            eq, n, _ = bt_anni(pxo, pos)
            riga += f"|{soglia}:{eq-1:+7.0%} "
        print(riga)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
