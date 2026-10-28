#!/usr/bin/env python3
"""paper_track.py — PAPER del funding carry sistematico K<=5 su OKX EEA.

Sola lettura: nessun ordine. Portafoglio virtuale: long spot + short XPERP
sugli asset con funding annualizzato sopra soglia (media ultimi L giorni).
PnL virtuale = funding incassato - costi (0.34%/apertura+chiusura), nessun
drift prezzo (delta-neutral). Stato in prove/carry_paper_state.json,
serie in prove/carry_paper_series.jsonl.

Uso: python3 ops/carry_sistematico/paper_track.py
"""
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://eea.okx.com"
ASSETS = {
    "BTC": "BTC-USD_UM_XPERP-310404", "ETH": "ETH-USD_UM_XPERP-310404",
    "LINK": "LINK-USD_UM_XPERP-310523", "LTC": "LTC-USD_UM_XPERP-310404",
    "ADA": "ADA-USD_UM_XPERP-310404", "DOGE": "DOGE-USD_UM_XPERP-310404",
    "FIL": "FIL-USD_UM_XPERP-310718", "UNI": "UNI-USD_UM_XPERP-310718",
    "BCH": "BCH-USD_UM_XPERP-310530", "NEAR": "NEAR-USD_UM_XPERP-310613",
    "CRV": "CRV-USD_UM_XPERP-310815", "AAVE": "AAVE-USD_UM_XPERP-310704",
    "SUSHI": "SUSHI-USD_UM_XPERP-310912", "XRP": "XRP-USD_UM_XPERP-310404",
    "SOL": "SOL-USD_UM_XPERP-310404", "DOT": "DOT-USD_UM_XPERP-310808",
}
IN_PCT = 3.0      # soglia ingresso funding annualizzato %
OUT_PCT = 2.0     # soglia uscita %
K_MAX = 5         # max posizioni
SIZE_USD = 55.0   # nozionale virtuale per asset
COST = 0.0034     # apertura+chiusura (giro+slip, 4 lati)
PROVE = Path.home() / "money" / "prove"


def funding_ann(sym):
    url = f"{BASE}/api/v5/public/funding-rate?instId={ASSETS[sym]}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        d = json.loads(r.read().decode())
    row = (d.get("data") or [{}])[0]
    fr = float(row.get("fundingRate") or 0)
    return fr * 3 * 365 * 100


def main():
    now = datetime.now(timezone.utc)
    state_p = PROVE / "carry_paper_state.json"
    series_p = PROVE / "carry_paper_series.jsonl"
    state = json.loads(state_p.read_text()) if state_p.exists() else {
        "posizioni": {}, "pnl_usd": 0.0, "avviato": now.isoformat()}

    ann = {s: funding_ann(s) for s in ASSETS}
    pos = state["posizioni"]
    # uscite virtuali
    for sym in list(pos):
        if ann.get(sym, 0) < OUT_PCT:
            state["pnl_usd"] -= COST * SIZE_USD
            del pos[sym]
    # ingressi virtuali
    for sym, a in sorted(ann.items(), key=lambda kv: -kv[1]):
        if a >= IN_PCT and sym not in pos and len(pos) < K_MAX:
            pos[sym] = {"ingresso": now.isoformat(), "funding_pct": round(a, 2)}
            state["pnl_usd"] -= COST * SIZE_USD
    # funding incassato dal run precedente
    ore = 0.0
    for sym, p in pos.items():
        dt = datetime.fromisoformat(p["ingresso"])
        ore = max(ore, (now - dt).total_seconds() / 3600.0)
        p["funding_ora_pct"] = round(ann.get(sym, 0) / (3 * 365) / 100, 8)
    # stima funding accumulato dall'ultimo run (intervallo del cron)
    last = state.get("ultimo_run")
    if last:
        delta_h = (now - datetime.fromisoformat(last)).total_seconds() / 3600.0
        for sym, p in pos.items():
            rate = ann.get(sym, 0) / 100 / 365 / 24  # frazione/ora
            state["pnl_usd"] += rate * delta_h * SIZE_USD
    state["ultimo_run"] = now.isoformat()
    state["funding_ora"] = {s: round(a, 3) for s, a in ann.items()}

    state_p.write_text(json.dumps(state, indent=2))
    with series_p.open("a") as f:
        f.write(json.dumps({"ts": now.isoformat(), "n_pos": len(pos),
                            "posizioni": sorted(pos),
                            "pnl_usd": round(state["pnl_usd"], 4)}) + "\n")
    print(json.dumps({"n_pos": len(pos), "posizioni": sorted(pos),
                      "pnl_usd": round(state["pnl_usd"], 4),
                      "top_funding": dict(sorted(ann.items(),
                                                 key=lambda kv: -kv[1])[:6])}, indent=2))


if __name__ == "__main__":
    main()
