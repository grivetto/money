#!/usr/bin/env python3
"""campiona_spread.py — misura lo spread denaro-lettera reale su Bybit e Bitvavo.

PERCHE' ESISTE
==============
Il market making non predice: incassa lo spread e paga/incassa fee maker. La
domanda economica e' una sola: **spread medio vs fee maker**. Se spread > 2x fee
maker, esiste margine lordo; poi l'adverse selection lo erode, e quello si misura
solo col tempo. Questo script raccoglie il dato di base (best bid/ask) ogni
esecuzione, appendendo una riga per simbolo in un CSV. Con qualche giorno di
campioni si stima lo spread mediano per simbolo e per fascia oraria.

SOLA LETTURA: endpoint pubblici ticker. Nessuna chiave, nessun ordine.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import sys
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "spread" / "spread.csv"

#: simbolo -> (categoria Bybit, mercato Bitvavo)
COPPIE = {
    "BTC": ("BTCUSDT", "BTC-USDC"),
    "ETH": ("ETHUSDT", "ETH-USDC"),
    "SOL": ("SOLUSDT", "SOL-USDC"),
    "DOGE": ("DOGEUSDT", "DOGE-USDC"),
    "XRP": ("XRPUSDT", "XRP-USDC"),
    "ADA": ("ADAUSDT", "ADA-USDC"),
    "AVAX": ("AVAXUSDT", "AVAX-USDC"),
    "LINK": ("LINKUSDT", "LINK-USDC"),
}

UA = {"User-Agent": "curl/8"}


def _json(url: str):
    req = Request(url, headers=UA)
    with urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def bybit_top(sym: str, categoria: str = "spot"):
    d = _json(f"https://api.bybit.com/v5/market/tickers?category={categoria}&symbol={sym}")
    t = (d.get("result") or {}).get("list") or []
    if not t:
        return None
    b, a = float(t[0]["bid1Price"]), float(t[0]["ask1Price"])
    return (b, a) if b > 0 and a > 0 else None


def bitvavo_top(market: str):
    d = _json(f"https://api.bitvavo.com/v2/{market}/book")
    b = a = None
    for lato in d.get("bids") or []:
        b = float(lato[0]); break
    for lato in d.get("asks") or []:
        a = float(lato[0]); break
    return (b, a) if b and a and b > 0 and a > 0 else None


def main() -> int:
    fuori = ROOT / "data" / "spread" / "spread.csv" if len(sys.argv) < 2 else Path(sys.argv[1])
    fuori.parent.mkdir(parents=True, exist_ok=True)
    nuovo = not fuori.exists()
    istante = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    righe = []
    for base, (bybit_sym, bv_market) in COPPIE.items():
        for venue, getter, arg in (("bybit", bybit_top, bybit_sym),
                                   ("bitvavo", bitvavo_top, bv_market)):
            try:
                top = getter(arg)
            except Exception as exc:
                righe.append([istante, venue, base, "", "", "", f"ERR {type(exc).__name__}"])
                continue
            if not top:
                righe.append([istante, venue, base, "", "", "", "vuoto"])
                continue
            b, a = top
            spread_bps = (a - b) / ((a + b) / 2) * 10_000
            righe.append([istante, venue, base, f"{b:.8g}", f"{a:.8g}",
                          f"{spread_bps:.3f}", "ok"])

    with fuori.open("a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if nuovo:
            w.writerow(["istante", "venue", "base", "bid", "ask", "spread_bps", "esito"])
        w.writerows(righe)

    ok = [r for r in righe if r[6] == "ok"]
    peggiore = ""
    if ok:
        m = {}
        for r in ok:
            m.setdefault(r[2], {})[r[1]] = float(r[5])
        peggiore = " | ".join(
            f"{k}: bybit {v.get('bybit', float('nan')):.1f} / bv {v.get('bitvavo', float('nan')):.1f} bps"
            for k, v in sorted(m.items())[:4])
    print(f"{istante}  {len(ok)}/{len(righe)} ok  {peggiore}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
