#!/usr/bin/env python3
"""scarica_bitvavo_1h.py — scarica candele 1h Bitvavo (API pubblica v2) per il set E8.

Universo CONGELATO dalla spec E8 (28/10/2026): 7 coppie EUR con volumeQuote >= 5M EUR/24h.
Finestra: 2024-06-01 -> 2026-10-28 (inclusiva). Formato di uscita = convenzione cache:
    {venue, simbolo, timeframe, barre: [[ts_ms, o, h, l, c, v], ...]} con ts crescente.

Uso:  python scripts/scarica_bitvavo_1h.py [--out data/cache]
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.request
from pathlib import Path

BASE = "https://api.bitvavo.com/v2"
INTERVAL = "1h"
MS_H = 3_600_000

# Universo congelato E8 (spec, 28/10/2026):
SIMBOLI = ["BTC-EUR", "XRP-EUR", "ETH-EUR", "SOL-EUR", "HYPE-EUR", "ADA-EUR", "PEPE-EUR"]
INIZIO_MS = 1_717_200_000_000  # 2024-06-01T00:00:00Z
FINE_MS = 1_793_318_400_000    # 2026-10-29T00:00:00Z (copre tutto il 28/10)


def get_json(url: str, tentativi: int = 3):
    for i in range(tentativi):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode())
        except Exception:
            if i == tentativi - 1:
                raise
            time.sleep(1.5 * (i + 1))


def scarica(market: str) -> list[list]:
    """Candele ASCENDENTI, dedup per ts, finestra [INIZIO_MS, FINE_MS).

    Semantica Bitvavo verificata 29/10: il parametro `end` fa da ancora e la risposta e'
    l'ultimo blocco di `limit` candele che FINISCE li' (start non sposta la finestra) ->
    si pagina camminando all'indietro con end = min(ts) finche' non si copre INIZIO_MS.
    """
    per_ts: dict[int, list] = {}
    end = FINE_MS
    guard = 0
    while end > INIZIO_MS and guard < 200:
        guard += 1
        url = f"{BASE}/{market}/candles?interval={INTERVAL}&limit=1440&end={end}"
        rows = get_json(url)
        if not rows:
            break
        for r in rows:  # newest-first
            ts = int(r[0])
            if INIZIO_MS <= ts < FINE_MS:
                per_ts[ts] = [ts, float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])]
        end = min(int(r[0]) for r in rows)
        time.sleep(0.25)
    return [per_ts[k] for k in sorted(per_ts)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/cache")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for market in SIMBOLI:
        barre = scarica(market)
        p = out / f"bitvavo_{market}_1h.json"
        payload = {"venue": "bitvavo", "simbolo": market, "timeframe": "1h", "barre": barre}
        p.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        if barre:
            primo = time.strftime("%Y-%m-%d", time.gmtime(barre[0][0] / 1000))
            ultimo = time.strftime("%Y-%m-%d", time.gmtime(barre[-1][0] / 1000))
            print(f"{market}: {len(barre)} barre | {primo} -> {ultimo} | {p}")
        else:
            print(f"{market}: 0 barre (!!) | {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
