#!/usr/bin/env python3
"""setaccia_onchain.py — quali metriche on-chain/sentiment predicono il rendimento?

Metodo (anti-look-ahead):
- z-score MOBILE su 180 giorni calcolato con somme cumulate (O(n), non O(n*finestra))
- correlazione di Pearson tra il segnale al giorno t e il rendimento realizzato a H giorni
- t-stat della correlazione; n dichiarato. Soglia di studio: |t| > 2.5.

Le metriche "ratio"/livello (MVRV, supply su exchange, indirizzi attivi, hash rate)
sono economicamente interpretabili: oltre allo z-score testo anche il valore grezzo.

Vantaggio economico della pista: segnali a bassa frequenza (H=7/30 giorni) pagano il
pedaggio poche volte l'anno, invece di divorare ogni operazione come sull'intraday.

Sola analisi su dati pubblici. Nessun ordine.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EST = ROOT / "data" / "esterni"
ASSET = ("btc", "eth", "xrp", "ada", "doge", "ltc", "link", "dot", "bch", "xlm", "trx")
FINESTRA = 180
LIVELLI = {"CapMVRVCur", "SplyExUSD", "AdrActCnt", "HashRate"}


def carica(asset: str) -> dict:
    p = EST / f"onchain_{asset}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def zscore_mobile(vals: list[float], w: int = FINESTRA) -> list[float | None]:
    n = len(vals)
    ps = [0.0] * (n + 1)
    ps2 = [0.0] * (n + 1)
    for i, v in enumerate(vals):
        ps[i + 1] = ps[i] + v
        ps2[i + 1] = ps2[i] + v * v
    fuori: list[float | None] = [None] * n
    for i in range(w, n):
        a = i - w
        mu = (ps[i] - ps[a]) / w
        var = (ps2[i] - ps2[a]) / w - mu * mu
        sd = math.sqrt(var) if var > 1e-24 else 1e-12
        fuori[i] = (vals[i] - mu) / sd
    return fuori


def pearson(x: list[float], y: list[float]):
    n = len(x)
    if n < 30:
        return 0.0, 0.0, n
    mx = statistics.fmean(x)
    my = statistics.fmean(y)
    num = sum((a - mx) * (b - my) for a, b in zip(x, y))
    dx = math.sqrt(sum((a - mx) ** 2 for a in x)) or 1e-12
    dy = math.sqrt(sum((b - my) ** 2 for b in y)) or 1e-12
    r = max(min(num / (dx * dy), 0.999999), -0.999999)
    t = r * math.sqrt(max(n - 2, 1)) / math.sqrt(max(1 - r * r, 1e-12))
    return r, t, n


def test_asset(asset: str, H: int):
    d = carica(asset)
    pxs = d.get("PriceUSD")
    if not pxs:
        return []
    date = sorted(pxs)
    px = [float(pxs[t]) for t in date]
    n = len(px)
    rf: list[float | None] = [None] * n
    for i in range(n - H):
        if px[i] > 0:
            rf[i] = (px[i + H] - px[i]) / px[i]
    risultati = []
    for nome, serie in d.items():
        if nome == "PriceUSD":
            continue
        grezzo: list[float | None] = [float(serie[t]) if t in serie else None for t in date]
        z = zscore_mobile([v if v is not None else 0.0 for v in grezzo])
        for etichetta, vals in (("z", z), ("grezzo", grezzo)):
            if etichetta == "grezzo" and nome not in LIVELLI:
                continue
            x, y = [], []
            for i in range(n):
                if vals[i] is None or rf[i] is None:
                    continue
                x.append(float(vals[i]))
                y.append(rf[i])
            r, t, c = pearson(x, y)
            if c >= 300:
                risultati.append((abs(r), r, t, c, nome, etichetta))
    return risultati


def main() -> int:
    for H in (7, 30):
        print(f"\n=== ON-CHAIN -> rendimento a {H} giorni (top 20 per |corr|) ===", flush=True)
        print(f"{'asset':6s} {'metrica':16s} {'tipo':7s} {'corr':>8s} {'t':>7s} {'n':>6s}")
        tutti = []
        for a in ASSET:
            for r in test_asset(a, H):
                tutti.append((r[0], a, r))
        tutti.sort(reverse=True)
        for _, a, (_, r, t, n, nome, etichetta) in tutti[:20]:
            print(f"{a:6s} {nome[:16]:16s} {etichetta:7s} {r:+8.3f} {t:+7.2f} {n:6d}")
        forti = [x for x in tutti if abs(x[2][2]) > 2.5]
        print(f"  -> coppie con |t|>2.5: {len(forti)} su {len(tutti)}", flush=True)

    print("\n=== FEAR & GREED -> rendimento futuro ===")
    fng = json.loads((EST / "sentiment_fng.json").read_text(encoding="utf-8"))
    fmap = {dt.datetime.fromtimestamp(int(k), dt.timezone.utc).date().isoformat(): v["valore"]
            for k, v in fng.items()}
    for asset in ("btc", "eth", "doge", "xrp"):
        d = carica(asset)
        pxs = d.get("PriceUSD", {})
        date = sorted(t for t in pxs if t in fmap)
        if len(date) < 400:
            continue
        px = [float(pxs[t]) for t in date]
        f = [float(fmap[t]) for t in date]
        for H in (7, 30):
            x, y = [], []
            for i in range(len(px) - H):
                if px[i] > 0:
                    x.append(f[i])
                    y.append((px[i + H] - px[i]) / px[i])
            r, t, n = pearson(x, y)
            print(f"  {asset:5s} F&G H={H:2d}g corr={r:+.3f} t={t:+6.2f} n={n}")

    print("\n=== TVL DeFi -> rendimento futuro (ETH) ===")
    tp = EST / "defi_tvl.json"
    if tp.exists():
        tvl = json.loads(tp.read_text(encoding="utf-8"))
        tmap = {dt.datetime.fromtimestamp(float(k), dt.timezone.utc).date().isoformat(): float(v)
                for k, v in tvl.items()}
        d = carica("eth")
        pxs = d.get("PriceUSD", {})
        date = sorted(t for t in pxs if t in tmap)
        if len(date) > 400:
            px = [float(pxs[t]) for t in date]
            zt = zscore_mobile([tmap[t] for t in date])
            for H in (7, 30):
                x, y = [], []
                for i in range(len(px) - H):
                    if zt[i] is not None and px[i] > 0:
                        x.append(zt[i])
                        y.append((px[i + H] - px[i]) / px[i])
                r, t, n = pearson(x, y)
                print(f"  TVL z-score H={H:2d}g vs ETH corr={r:+.3f} t={t:+6.2f} n={n}")
    print("\nfatto", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
