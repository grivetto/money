#!/usr/bin/env python3
"""sonda_swap_funding.py — cerca i funding piu' alti su OKX EEA e verifica se
sono CARRYABILI (esiste lo spot per coprirsi? c'e' liquidita?).

Perche': il carry classico su crypto major rende ~11%/anno, che su 300 EUR sono
~20 EUR/anno. Se esistono strumenti con funding molto piu' alto E copertura spot,
il carry rende di piu' a parita' di rischio strutturale (delta-neutral).

Sola lettura: nessun ordine.
"""
from __future__ import annotations

import concurrent.futures as cf
from pathlib import Path

import ccxt

ENV = Path("/home/marco/denaro/secrets/main_okx.env")


def client():
    e = {}
    for l in ENV.read_text().splitlines():
        if "=" in l and not l.startswith("#"):
            k, v = l.split("=", 1)
            e[k] = v.strip()
    return ccxt.okx({"apiKey": e["OKX_API_KEY"], "secret": e["OKX_API_SECRET"],
                     "password": e["OKX_PASSPHRASE"], "hostname": "eea.okx.com",
                     "enableRateLimit": True})


def main() -> int:
    ex = client()
    ex.load_markets()
    swap = [m for m in ex.markets.values() if m.get("swap") and m.get("linear")]
    print(f"swap lineari su OKX EEA: {len(swap)}")

    def fr(i):
        try:
            r = ex.publicGetPublicFundingRate({"instId": i})
            d = (r.get("data") or [{}])[0]
            return (i, float(d.get("fundingRate") or 0))
        except Exception:
            return (i, None)

    ids = [m["id"] for m in swap]
    res = []
    with cf.ThreadPoolExecutor(24) as tp:
        for i, f in tp.map(fr, ids):
            if f is not None and f > 0.00005:      # sopra ~3%/anno
                res.append((i, f))
    res.sort(key=lambda x: -x[1])
    print(f"swap con funding positivo >3%/anno: {len(res)}\n")

    print(f"{'strumento':34s} {'funding':>10s} {'annuo':>8s} {'vol24h USDT':>14s} "
          f"{'spot?':>6s} {'CARRYABILE':>10s}")
    carryabili = []
    for i, f in res[:25]:
        base = i.replace("-USDT-SWAP", "")
        try:
            t = ex.fetch_ticker(i)
            vol = t.get("quoteVolume") or 0
            spot_id = f"{base}-USDT"
            ha_spot = spot_id in ex.markets
            # carryabile se: ha spot, liquidita decente (>50k USDT/day)
            ok = ha_spot and vol > 50_000
            if ok:
                carryabili.append((base, f, vol))
            print(f"{i:34s} {f*100:>9.5f}% {f*3*365*100:>7.1f}% {vol:>14,.0f} "
                  f"{'SI' if ha_spot else 'NO':>6s} {'SI' if ok else 'no':>10s}")
        except Exception as e:  # noqa: BLE001
            print(f"{i:34s} {f*100:>9.5f}%  ERR {str(e)[:40]}")

    print(f"\n=== CARRYABILI (spot + liquidita) : {len(carryabili)} ===")
    for base, f, vol in carryabili[:15]:
        print(f"  {base:14s} funding={f*100:+.5f}%/8h  annuo={f*3*365*100:+.1f}%  vol={vol:,.0f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
