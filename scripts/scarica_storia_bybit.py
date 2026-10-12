#!/usr/bin/env python3
"""scarica_storia_bybit.py — storia OHLCV lunga da Bybit v5, in cache locale.

PERCHE' ESISTE
==============
OKX EEA da ~1 anno su 1h. Gli edge su candele non si misurano su 40 trade di
out-of-sample: serve storia lunga (5+ anni) perche' il t-test abbia un minimo di
potere. Bybit spot ha 5+ anni e copre lo stesso paniere.

PERCHE' NON ESTENDE `money.dati`
================================
`money.dati.Scarica` e' specializzato OKX EEA (nome file, hostname, parsing):
piegarlo a due sedi lo renderebbe un modulo che fa due cose male. Questo script
scrive lo **stesso formato di cache** (`{"venue","hostname","simbolo","timeframe",
"barre":[[ts,o,h,l,c,v],...]}`), quindi i dati sono leggibili dal resto della
pipeline senza toccare il motore.

SOLA LETTURA: endpoint pubblici `/v5/market/kline`, nessuna chiave.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import time
from pathlib import Path
from urllib.request import Request, urlopen

BASE = "https://api.bybit.com"
CACHE = Path(__file__).resolve().parents[1] / "data" / "cache"

#: codici intervallo Bybit v5 -> timeframe interno
TF_BYBIT = {"1d": "D", "4h": "240", "1h": "60", "30m": "30", "15m": "15", "5m": "5"}
TF_MS = {"1d": 86_400_000, "4h": 14_400_000, "1h": 3_600_000, "30m": 1_800_000,
         "15m": 900_000, "5m": 300_000}


def _get(path: str, params: dict, tentativi: int = 4) -> dict:
    q = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{BASE}{path}?{q}"
    ultimo: Exception | None = None
    for t in range(tentativi):
        try:
            req = Request(url, headers={"User-Agent": "curl/8"})
            with urlopen(req, timeout=20) as r:
                d = json.loads(r.read())
            if d.get("retCode") == 0:
                return d["result"]
            raise RuntimeError(f"bybit retCode={d.get('retCode')} {d.get('retMsg')}")
        except Exception as exc:  # rete/parse/rate-limit: riprovo con backoff
            ultimo = exc
            if t == tentativi - 1:
                break
            time.sleep(1.5 * (t + 1))
    raise RuntimeError(f"richiesta fallita: {url} ({ultimo})")


def scarica(simbolo: str, tf: str, inizio_ms: int, fine_ms: int,
            categoria: str = "spot", limite: int = 1000) -> list[list[float]]:
    """Pagina all'indietro da `fine` a `inizio`. Bybit ritorna al piu' `limite`,
    ordinati dal piu' recente al piu' vecchio."""
    durata = TF_MS[tf]
    barre: dict[int, list[float]] = {}
    fine = fine_ms
    finestre_vuote = 0
    while fine > inizio_ms and finestre_vuote < 3:
        inizio_finestra = max(inizio_ms, fine - durata * limite)
        res = _get("/v5/market/kline", {
            "category": categoria, "symbol": simbolo, "interval": TF_BYBIT[tf],
            "start": inizio_finestra, "end": fine, "limit": limite,
        })
        righe = res.get("list") or []
        if not righe:
            finestre_vuote += 1
        for r in righe:
            ts = int(r[0])
            if inizio_ms <= ts <= fine_ms:
                barre[ts] = [ts, float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])]
        fine = inizio_finestra - 1
        time.sleep(0.12)  # rate limit gentile: Bybit non perdona le raffiche
    return [barre[k] for k in sorted(barre)]


def main() -> int:
    ap = argparse.ArgumentParser(description="Scarica storia OHLCV da Bybit in cache locale.")
    ap.add_argument("simboli", nargs="+", help="es. BTC/USDT ETH/USDT")
    ap.add_argument("--tf", default="1d", choices=sorted(TF_BYBIT))
    ap.add_argument("--inizio", default="2020-01-01")
    ap.add_argument("--fine", default=dt.date.today().isoformat())
    ap.add_argument("--categoria", default="spot", choices=["spot", "linear"])
    a = ap.parse_args()

    inizio_ms = int(dt.datetime.fromisoformat(a.inizio).replace(
        tzinfo=dt.timezone.utc).timestamp() * 1000)
    fine_ms = int(dt.datetime.fromisoformat(a.fine).replace(
        tzinfo=dt.timezone.utc).timestamp() * 1000)

    CACHE.mkdir(parents=True, exist_ok=True)
    ok = 0
    for s in a.simboli:
        bybit_sym = s.replace("/", "").replace("-", "").upper()
        try:
            barre = scarica(bybit_sym, a.tf, inizio_ms, fine_ms, a.categoria)
        except Exception as exc:
            print(f"  {s}: ERRORE {type(exc).__name__}: {exc}", flush=True)
            continue
        if not barre:
            print(f"  {s}: nessun dato", flush=True)
            continue
        pulito = "".join(c if c.isalnum() else "-" for c in s)
        out = CACHE / f"bybit_{pulito}_{a.tf}.json"
        contenuto = {"venue": "bybit", "hostname": "api.bybit.com", "simbolo": s,
                     "timeframe": a.tf, "categoria": a.categoria, "barre": barre}
        out.write_text(json.dumps(contenuto, separators=(",", ":")), encoding="utf-8")
        ok += 1
        d0 = dt.datetime.fromtimestamp(barre[0][0] / 1000, dt.timezone.utc).date()
        d1 = dt.datetime.fromtimestamp(barre[-1][0] / 1000, dt.timezone.utc).date()
        print(f"  {s} [{a.categoria}] {a.tf}: {len(barre)} barre {d0}->{d1} {out.name}", flush=True)
    print(f"fatto: {ok}/{len(a.simboli)} serie", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
