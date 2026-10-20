#!/usr/bin/env python3
"""Scarica OHLCV 1h da OKX (spot USDT) per un paniere ampio — serve da OOS cross-exchange per E4.

Uso:  .venv/bin/python scripts/scarica_okx_1h.py [--n 30] [--dal 2024-06-01]
Output: data/cache/okx_<SYM>_1h.json  {"venue":"okx","simbolo":...,"timeframe":"1h","barre":[[ts,o,h,l,c,v],...]}
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import ccxt

RADICE = Path(__file__).resolve().parent.parent
CACHE = RADICE / "data" / "cache"


def scarica(ex, simbolo: str, dal_ms: int, fino_ms: int) -> list:
    barre: dict[int, list] = {}
    since = dal_ms
    while since < fino_ms:
        blocco: list = []
        for tentativo in range(4):
            try:
                blocco = ex.fetch_ohlcv(simbolo, "1h", since=since, limit=300)
                break
            except Exception as exc:  # noqa: BLE001
                if tentativo == 3:
                    raise
                print(f"    retry {simbolo} ({type(exc).__name__})", flush=True)
                time.sleep(1.5 * (tentativo + 1))
        if not blocco:
            break
        for b in blocco:
            barre[int(b[0])] = [int(b[0]), float(b[1]), float(b[2]), float(b[3]), float(b[4]), float(b[5])]
        nuovo = int(blocco[-1][0]) + 3600_000
        if nuovo <= since:
            break
        since = nuovo
        if len(barre) % 3000 < 300:
            print(f"    {simbolo}: {len(barre)} barre", flush=True)
    return [barre[k] for k in sorted(barre) if k < fino_ms]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--dal", default="2024-06-01")
    ap.add_argument("--simboli", default="")
    a = ap.parse_args()

    dal_ms = int(datetime.fromisoformat(a.dal).replace(tzinfo=timezone.utc).timestamp() * 1000)
    fino_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    ex = ccxt.okx({"enableRateLimit": True, "options": {"defaultType": "spot"}})
    ex.load_markets()

    if a.simboli:
        paniere = [s.strip() for s in a.simboli.split(",") if s.strip()]
    else:
        tk = ex.fetch_tickers()
        cand = [(s, float(v.get("quoteVolume") or 0)) for s, v in tk.items()
                if s.endswith("/USDT") and v.get("quoteVolume") and ex.markets.get(s, {}).get("spot")]
        cand.sort(key=lambda x: -x[1])
        paniere = [s for s, _ in cand[: a.n]]
    print(f"paniere: {len(paniere)} simboli | dal {a.dal}", flush=True)

    fatti = 0
    for s in paniere:
        try:
            barre = scarica(ex, s, dal_ms, fino_ms)
        except Exception as exc:  # noqa: BLE001
            print(f"  SALTO {s}: {type(exc).__name__} {str(exc)[:120]}", flush=True)
            continue
        if len(barre) < 3000:
            print(f"  SALTO {s}: storia corta ({len(barre)} barre)", flush=True)
            continue
        nome = s.replace("/", "-")
        (CACHE / f"okx_{nome}_1h.json").write_text(json.dumps(
            {"venue": "okx", "simbolo": s, "timeframe": "1h", "barre": barre}))
        primo = datetime.fromtimestamp(barre[0][0] / 1000, timezone.utc).strftime("%Y-%m-%d")
        ultimo = datetime.fromtimestamp(barre[-1][0] / 1000, timezone.utc).strftime("%Y-%m-%d")
        print(f"  OK {s}: {len(barre)} barre {primo} -> {ultimo}", flush=True)
        fatti += 1
    print(f"finito: {fatti} simboli salvati in {CACHE}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
