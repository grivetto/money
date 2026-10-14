#!/usr/bin/env python3
"""confronto_trend.py — l'on-chain aggiunge qualcosa al semplice trend-following?

IPOTESI DA FALSIFICARE
======================
Le strategie "long se MVRV > media 180g" e "long se F&G > 50" hanno battuto buy&hold
out-of-sample su BTC/ETH. Ma MVRV = MarketCap/RealizedCap, e RealizedCap si muove
lentamente: MVRV > media180 e' quasi "prezzo > media". Se il trend-following PURO sul
prezzo (SMA200) da' gli stessi risultati, l'on-chain non aggiunge informazione e la
pista si riduce a "comprare quando sale", che non e' un edge nuovo.

Test su 11 asset. Confronto: B&H vs SMA200 vs MVRV-mom vs F&G-mom.
Un segnale on-chain ha valore solo se batte SMA200 in modo CONSISTENTE su piu' asset,
non se vince su uno.

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
ASSET = ("btc", "eth", "xrp", "ada", "doge", "ltc", "link", "dot", "bch", "xlm", "trx")


def serie(asset: str, metrica: str) -> dict[str, float]:
    p = EST / f"onchain_{asset}.json"
    if not p.exists():
        return {}
    d = json.loads(p.read_text(encoding="utf-8"))
    return {t: float(v) for t, v in (d.get(metrica) or {}).items()}


def sma(s: dict[str, float], n: int) -> dict[str, float]:
    date = sorted(s)
    out = {}
    for i in range(n, len(date)):
        out[date[i]] = sum(s[t] for t in date[i - n:i]) / n
    return out


def stats(eq: list[float]):
    if len(eq) < 30:
        return 0.0, 0.0, 0.0
    rend = [eq[i] / eq[i - 1] - 1 for i in range(1, len(eq))]
    mu = sum(rend) / len(rend)
    sd = math.sqrt(sum((r - mu) ** 2 for r in rend) / len(rend)) or 1e-12
    picco, dd = eq[0], 0.0
    for v in eq:
        picco = max(picco, v)
        dd = min(dd, v / picco - 1)
    return eq[-1] / eq[0] - 1, mu / sd * math.sqrt(365), dd


def bt(px: dict[str, float], pos: dict[str, int]):
    date = sorted(px)
    eq = [1.0]
    n = 0
    prec = 0
    for i in range(len(date) - 1):
        t, tn = date[i], date[i + 1]
        p = pos.get(t, prec)
        if p != prec:
            eq[-1] *= (1 - FEE_RT)
            n += 1
        r = px[tn] / px[t] - 1 if px[t] > 0 else 0.0
        eq.append(eq[-1] * (1 + (r if p else REND_FLAT)))
        prec = p
    return eq, n


def bh(px):
    date = sorted(px)
    eq = [1.0]
    for i in range(len(date) - 1):
        r = px[date[i + 1]] / px[date[i]] - 1 if px[date[i]] > 0 else 0.0
        eq.append(eq[-1] * (1 + r))
    return eq


def riga(nome, px, pos, taglio=None):
    if taglio:
        px = {t: v for t, v in px.items() if t >= taglio}
        pos = {t: v for t, v in pos.items() if t in px}
    if len(px) < 200:
        return None
    eq, n = bt(px, pos)
    r, s, dd = stats(eq)
    return f"{nome:16s} ret={r:+9.1%} sh={s:+5.2f} DD={dd:+6.1%} n={n:3d}"


def main() -> int:
    fng_raw = json.loads((EST / "sentiment_fng.json").read_text(encoding="utf-8"))
    fmap = {dt.datetime.fromtimestamp(int(k), dt.timezone.utc).date().isoformat(): float(v["valore"])
            for k, v in fng_raw.items()}

    print("=== OUT-OF-SAMPLE (dal 2021-01-01): chi batte il trend PURI sul prezzo? ===")
    conteggio = {"sma200": 0, "mvrv": 0, "fng": 0, "tot": 0}
    for a in ASSET:
        px = serie(a, "PriceUSD")
        if len(px) < 400:
            continue
        mvrv = serie(a, "CapMVRVCur")
        med180 = sma(mvrv, 180)
        med200 = sma(px, 200)
        pos_sma = {t: (1 if t in med200 and px[t] > med200[t] else 0) for t in px}
        pos_mvrv = {t: (1 if t in med180 and mvrv.get(t, 0) > med180[t] else 0) for t in px}
        px_f = {t: px[t] for t in px if t in fmap}
        pos_fng = {t: (1 if fmap[t] > 50 else 0) for t in px_f}

        print(f"\n--- {a.upper()} ---")
        b = riga("B&H", px, {t: 1 for t in px}, "2021-01-01")
        s1 = riga("prezzo > SMA200", px, pos_sma, "2021-01-01")
        s2 = riga("MVRV > media180", px, pos_mvrv, "2021-01-01")
        for x in (b, s1, s2):
            if x:
                print("   " + x)
        if len(px_f) > 400:
            s3 = riga("F&G > 50", px_f, pos_fng, "2021-01-01")
            if s3:
                print("   " + s3)

        # conteggio "chi vince" (sharpe OOS)
        if s1 and s2:
            def sh(txt):
                return float(txt.split("sh=")[1].split()[0])
            conteggio["tot"] += 1
            if sh(s1) > sh(b):
                conteggio["sma200"] += 1
            if sh(s2) > sh(s1):
                conteggio["mvrv"] += 1

    print("\n=== SINTESI (sharpe OOS) ===")
    print(f"  asset testati: {conteggio['tot']}")
    print(f"  SMA200 batte B&H: {conteggio['sma200']}/{conteggio['tot']}")
    print(f"  MVRV-mom batte SMA200: {conteggio['mvrv']}/{conteggio['tot']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
