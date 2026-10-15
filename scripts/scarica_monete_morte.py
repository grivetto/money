#!/usr/bin/env python3
"""Scarica le «monete morte / fracassate» (Bybit spot, barre 1h) per il test survivorship di E2.

Perche': il paniere E2 contiene solo simboli ANCORA quotati — le cascate delle monete morte
(LUNA/USTC maggio 2022, FTT novembre 2022, ...) non sono state misurate. Qui si scarica la
loro storia per testare la regola E2 su eventi che la strategia, se fosse stata live, avrebbe
davvero incontrato.

Uso:  .venv/bin/python scripts/scarica_monete_morte.py
Output: data/cache_morte/<SYMBOL>_1h.json  {"symbol": ..., "barre": [[ts,o,h,l,c,v], ...]}
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
DEST = RADICE / "data" / "cache_morte"
BASE = "https://api.bybit.com/v5/market/kline"
ORA_MS = 3600 * 1000
LARGHEZZA_MS = 1000 * ORA_MS          # Bybit restituisce al massimo 1000 barre per chiamata
SIMBOLI = ("LUNC-USDT", "USTC-USDT", "FTT-USDT", "SRM-USDT")


def scarica(sym: str, da_ms: int, a_ms: int) -> list:
    barre: dict[int, list] = {}
    cur = da_ms
    vuote_dopo_dati = 0
    viste = 0
    api_sym = sym.replace("-", "")
    while cur < a_ms:
        fin = min(cur + LARGHEZZA_MS, a_ms) - 1
        url = (f"{BASE}?category=spot&symbol={api_sym}&interval=60"
               f"&start={cur}&end={fin}&limit=1000")
        for tent in range(3):
            try:
                with urllib.request.urlopen(url, timeout=30) as r:
                    d = json.loads(r.read().decode())
                break
            except Exception:  # noqa: BLE001
                if tent == 2:
                    raise
                time.sleep(1.0 + tent)
        if d.get("retCode") != 0:
            raise RuntimeError(f"{sym}: retCode {d.get('retCode')}: {d.get('retMsg')}")
        righe = d["result"]["list"]
        for r in righe:
            ts = int(r[0])
            barre[ts] = [ts, float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])]
        if righe:
            viste += 1
            vuote_dopo_dati = 0
        elif viste:
            vuote_dopo_dati += 1
            if vuote_dopo_dati > 2:   # ~2000 ore vuote dopo dati => simbolo delistato
                break
        cur = fin + 1
        time.sleep(0.12)
    return [barre[t] for t in sorted(barre)]


def main() -> int:
    DEST.mkdir(parents=True, exist_ok=True)
    da = int(datetime(2021, 7, 5, tzinfo=timezone.utc).timestamp() * 1000)  # inizio finestra E2
    a = int(time.time() * 1000)
    for sym in SIMBOLI:
        print(f"== {sym} ==", flush=True)
        try:
            barre = scarica(sym, da, a)
        except Exception as exc:  # noqa: BLE001
            print(f"  ERRORE: {exc}")
            continue
        out = DEST / f"{sym}_1h.json"
        out.write_text(json.dumps({"symbol": sym, "barre": barre}))
        if barre:
            primo = datetime.fromtimestamp(barre[0][0] / 1000, timezone.utc)
            ultimo = datetime.fromtimestamp(barre[-1][0] / 1000, timezone.utc)
            print(f"  {len(barre)} barre | {primo:%F %H:%M} -> {ultimo:%F %H:%M}")
        else:
            print("  nessun dato (simbolo mai quotato/API vuota)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
