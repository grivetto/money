#!/usr/bin/env python3
"""carry_veloce.py — SCREENER CARRY/BASIS (market-neutral). Read-only, nessun ordine.

PERCHE' NON RIUSA ipotesi_veloce.py
===================================
Lo screener indicatori simula UNA gamba (long/flat su barre). Un carry e' DUE gambe
(spot long + future/perp short, net-delta ~0): quel motore non lo rappresenta e forzarlo
darebbe numeri falsi. Questo e' un motore dedicato che riusa i pezzi GIUSTI:
  - `money.costi`     -> fee reali del conto (spot 0.10% taker, fut/perp 0.05% taker);
  - OKX EEA pubblico -> spot (bid/ask) + futures/perp (bid/ask) + scadenze.

DUE FILONI
==========
  H2  cash-and-carry su FUTURE DATED: compro spot all'ask, vendo il future al bid, tengo
      a scadenza. Il basis e' DETERMINISTICO alla scadenza -> non serve storico funding.
  (H1 funding dinamico e' rinviato: lo storico raccolto e' ~3,5 mesi, insufficiente.)

USO
===
  .venv/bin/python scripts/carry_veloce.py                       # soglia 1%, capitale 1000
  .venv/bin/python scripts/carry_veloce.py --capitale 500 --soglia 2.0
  .venv/bin/python scripts/carry_veloce.py --json

Il verdetto e' per strumento: NETTO annualizzato = (vendita_future_al_bid / acquisto_spot_all_ask
- 1) * 365/gg  - costi_roundtrip. Se netto <= soglia -> RESPINTO.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone

UA = {"User-Agent": "Mozilla/5.0"}
BASE = "https://eea.okx.com"
#: costi REALI del conto (misurati 09/10/2026). Frazioni, per lato.
COSTO_SPOT_TAKER = 0.0010
COSTO_FUT_TAKER = 0.0005
#: Spread massimo accettabile per considerare un prezzo ESEGUIBILE (0,3%).
#: Oltre, il "basis" misurato e' un artefatto di un book largo, non un prezzo reale.
SPREAD_MAX = 0.003


def get(path: str, params: dict | None = None) -> list:
    url = BASE + path
    if params:
        url += "?" + "&".join(f"{k}={v}" for k, v in params.items())
    req = urllib.request.Request(url, headers=UA)
    return json.loads(urllib.request.urlopen(req, timeout=20).read()).get("data", [])


def scansione(capitale: float, soglia_pct: float) -> dict:
    now = time.time() * 1000
    spot = {}
    for r in get("/api/v5/market/tickers", {"instType": "SPOT"}):
        i = r.get("instId", "")
        if i.endswith("-USDT"):
            spot[i[:-5]] = r
    info = {x["instId"]: x for x in get("/api/v5/public/instruments", {"instType": "FUTURES"})}
    ticks = get("/api/v5/market/tickers", {"instType": "FUTURES"})

    righe = []
    for r in ticks:
        i = r.get("instId", "")
        if "_UM" not in i or i.count("-") != 2:
            continue
        base = i.split("-")[0]
        s = spot.get(base)
        if not s:
            continue
        m = info.get(i, {})
        try:
            exp = int(m.get("expTime") or 0)
        except (TypeError, ValueError):
            exp = 0
        if exp <= now:
            continue
        try:
            fut_bid = float(r.get("bidPx") or 0)
            fut_ask = float(r.get("askPx") or 0)
            spot_ask = float(s.get("askPx") or 0)
            spot_bid = float(s.get("bidPx") or 0)
        except (TypeError, ValueError):
            continue
        if fut_bid <= 0 or spot_ask <= 0 or fut_ask <= 0 or spot_bid <= 0:
            continue
        gg = (exp - now) / 86_400_000
        if gg <= 1:
            continue
        # spread relativo: se il book e' largo, il "basis" e' un artefatto, non un prezzo
        spread_fut = (fut_ask - fut_bid) / fut_bid
        spread_spot = (spot_ask - spot_bid) / spot_bid
        # cash-and-carry: entro comprando spot all'ask, vendo il future al bid
        lordo = fut_bid / spot_ask - 1.0
        costo_roundtrip = COSTO_SPOT_TAKER + COSTO_FUT_TAKER + COSTO_SPOT_TAKER
        netto_ass = lordo - costo_roundtrip
        netto_ann = netto_ass * 365.0 / gg * 100.0
        profitto_eur = capitale * netto_ass                     # sul capitale impegnato
        # eseguibile solo se il book e' stretto: uno spread largo rende il prezzo fittizio
        eseguibile = spread_fut <= SPREAD_MAX and spread_spot <= SPREAD_MAX
        if not eseguibile:
            verdetto = "ILLIQUIDO"
        elif netto_ann > soglia_pct:
            verdetto = "PROFITTEVOLE"
        else:
            verdetto = "RESPINTO"
        righe.append({
            "instId": i, "base": base, "gg": round(gg),
            "fut_bid": round(fut_bid, 6), "spot_ask": round(spot_ask, 6),
            "spread_fut_pct": round(spread_fut * 100, 4),
            "basis_pct": round(lordo * 100, 4),
            "netto_ann_pct": round(netto_ann, 3),
            "profitto_eur": round(profitto_eur, 2),
            "verdetto": verdetto,
        })
    righe.sort(key=lambda x: -x["netto_ann_pct"])
    return {"ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "capitale": capitale, "soglia_pct": soglia_pct,
            "costi": {"spot_taker": COSTO_SPOT_TAKER, "fut_taker": COSTO_FUT_TAKER,
                      "roundtrip": COSTO_SPOT_TAKER + COSTO_FUT_TAKER + COSTO_SPOT_TAKER},
            "strumenti": righe}


def main() -> int:
    ap = argparse.ArgumentParser(description="Screener carry/basis market-neutral (read-only)")
    ap.add_argument("--capitale", type=float, default=1000.0)
    ap.add_argument("--soglia", type=float, default=1.0, help="soglia netto annualizzato %%")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    out = scansione(a.capitale, a.soglia)
    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return 0

    print(f"CARRY SCREENER — {out['ts']} | capitale {a.capitale:.0f}€ | soglia {a.soglia:.1f}%/anno")
    print(f"  costi round-trip (spot ask + fut bid + uscita spot): "
          f"{out['costi']['roundtrip']*100:.2f}%  (spot {COSTO_SPOT_TAKER*100:.2f}% + fut {COSTO_FUT_TAKER*100:.2f}%)")
    print(f"  {'instId':24s} {'gg':>4s} {'spr%':>6s} {'basis%':>8s} {'netto_ann%':>10s} {'€/anno':>9s}  verdetto")
    print("  " + "-" * 80)
    for r in out["strumenti"][:12]:
        print(f"  {r['instId']:24s} {r['gg']:>4} {r['spread_fut_pct']:>6.3f} {r['basis_pct']:>8.3f} "
              f"{r['netto_ann_pct']:>10.3f} {r['profitto_eur']:>9.2f}  {r['verdetto']}")
    n_prof = sum(1 for r in out["strumenti"] if r["verdetto"] == "PROFITTEVOLE")
    n_ill = sum(1 for r in out["strumenti"] if r["verdetto"] == "ILLIQUIDO")
    print("  " + "-" * 80)
    print(f"  {n_prof} PROFITTEVOLI · {n_ill} ILLIQUIDI (spread>{SPREAD_MAX*100:.1f}%) · "
          f"{len(out['strumenti'])} totali")
    return 0


if __name__ == "__main__":
    sys.exit(main())
