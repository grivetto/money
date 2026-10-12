#!/usr/bin/env python3
"""setaccia_onchain.py — quali metriche on-chain/sentiment predicono il rendimento?

Metodo (anti-look-ahead):
- per ogni metrica M costruisco lo z-score MOBILE su 180 giorni:  z_t = (M_t - mu[t-180:t]) / sd[t-180:t]
  (per MVRV, che ha un livello economicamente significativo, testo anche il valore grezzo)
- correlazione di Pearson tra il segnale al giorno t e il rendimento realizzato a H giorni
- t-stat della correlazione; n dichiarato

Un segnale utile qui ha un vantaggio strutturale: agisce a bassa frequenza (H=7/30
giorni), quindi il pedaggio per trade pesa molto meno che su un segnale intraday.

Sola analisi su dati pubblici. Nessun ordine.
"""
from __future__ import annotations

import json
import math
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EST = ROOT / "data" / "esterni"


def carica(asset: str) -> dict:
    p = EST / f"onchain_{asset}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def pearson(x, y):
    n = len(x)
    if n < 30:
        return 0.0, 0.0, n
    mx, my = statistics.mean(x), statistics.mean(y)
    sx = statistics.pstdev(x) or 1e-12
    sy = statistics.pstdev(y) or 1e-12
    cov = sum((a - mx) * (b - my) for a, b in zip(x, y)) / n
    r = cov / (sx * sy)
    t = r * math.sqrt(max(n - 2, 1)) / math.sqrt(max(1 - r * r, 1e-12))
    return r, t, n


def zscore_mobile(vals, finestra=180):
    fuori = [None] * len(vals)
    for i in range(len(vals)):
        if i < finestra:
            continue
        fin = vals[i - finestra:i]
        mu = statistics.mean(fin)
        sd = statistics.pstdev(fin) or 1e-12
        fuori[i] = (vals[i] - mu) / sd
    return fuori


def test_asset(asset: str, orizzonte: int = 7):
    d = carica(asset)
    if not d or "PriceUSD" not in d:
        return []
    pxs = d["PriceUSD"]
    date = sorted(pxs)
    px = [float(pxs[t]) for t in date]
    idx = {t: i for i, t in enumerate(date)}
    H = orizzonte
    rend: list[float | None] = [None] * len(px)
    for i in range(len(px) - H):
        rend[i] = (px[i + H] - px[i]) / px[i]
    risultati = []
    for nome, serie in d.items():
        if nome == "PriceUSD":
            continue
        grezzo = [float(serie[t]) if t in serie else None for t in date]
        # z-score mobile + versione grezza (solo se la metrica e' un livello)
        z = zscore_mobile([v if v is not None else 0.0 for v in grezzo])
        for etichetta, vals in (("z", z), ("grezzo", grezzo)):
            x, y = [], []
            for i in range(len(date)):
                if vals[i] is None or rend[i] is None:
                    continue
                x.append(vals[i]); y.append(rend[i])
            r, t, n = pearson(x, y)
            if n >= 300:
                risultati.append((abs(r), r, t, n, nome, etichetta))
    return risultati


def main() -> int:
    print("=== ON-CHAIN -> rendimento futuro (top per |corr|; t>2.5 = segnale da studiare) ===")
    for orizzonte in (7, 30):
        print(f"\n--- orizzonte {orizzonte} giorni ---")
        print(f"{'asset':6s} {'metrica':18s} {'tipo':7s} {'corr':>8s} {'t':>7s} {'n':>6s}")
        tutti = []
        for asset in ("btc", "eth", "xrp", "ada", "doge", "ltc", "link", "dot", "bch", "xlm", "trx"):
            for r in test_asset(asset, orizzonte):
                tutti.append((r[0], asset, r))
        tutti.sort(reverse=True)
        for _, asset, (_, r, t, n, nome, etichetta) in tutti[:18]:
            print(f"{asset:6s} {nome[:18]:18s} {etichetta:7s} {r:+8.3f} {t:+7.2f} {n:6d}")

    # sentiment
    print("\n=== FEAR & GREED -> rendimento futuro ===")
    fng = json.loads((EST / "sentiment_fng.json").read_text())
    import datetime as dt
    fmap = {dt.datetime.fromtimestamp(int(k), dt.timezone.utc).date().isoformat(): v["valore"]
            for k, v in fng.items()}
    for asset in ("btc", "eth", "doge"):
        d = carica(asset)
        pxs = d.get("PriceUSD", {})
        date = sorted(t for t in pxs if t in fmap)
        if len(date) < 400:
            continue
        px = [float(pxs[t]) for t in date]
        f = [fmap[t] for t in date]
        for H in (7, 30):
            x, y = [], []
            for i in range(len(px) - H):
                x.append(f[i]); y.append((px[i + H] - px[i]) / px[i])
            r, t, n = pearson(x, y)
            print(f"  {asset}: F&G H={H:2d}g corr={r:+.3f} t={t:+.2f} n={n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
