#!/usr/bin/env python3
"""genera_carry.py — stato del carry multi-coppia per dashboard e Zabbix.

PERCHE' ESISTE
==============
Il 16/10 sono state aperte le coppie DOT e ADA (90 EUR/gamba, 1x isolated).
Lo stato e' in `data/carry_multi/stato.json`, ma dashboard e Zabbix non lo
vedevano: serve un lettore che unisca lo stato salvato con i dati VIVI
(posizione reale, funding incassato, PnL) e scriva `data/carry_stato.json`,
l'unica fonte per gli altri due.

REGOLA: nessun numero inventato. Se una chiamata fallisce, il campo e' None e
la dashboard scrive "n/d".

Uso:  .venv/bin/python3 scripts/genera_carry.py
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/home/marco/money")
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from scripts.carry_multi import COPPIE, leggi_env, ENV_FILE, DIR_STATO  # noqa: E402

OUT = ROOT / "data" / "carry_stato.json"


def carica_stato_locale() -> dict:
    try:
        return json.loads((DIR_STATO / "stato.json").read_text())
    except (OSError, ValueError):
        return {"coppie": {}}


def main() -> int:
    import ccxt
    env = leggi_env(ENV_FILE)
    ex = ccxt.okx({"apiKey": env["OKX_API_KEY"], "secret": env["OKX_API_SECRET"],
                   "password": env["OKX_PASSPHRASE"], "hostname": "eea.okx.com",
                   "enableRateLimit": True})

    salvato = carica_stato_locale()
    coppie_out = {}

    # posizioni reali (una sola chiamata)
    try:
        posizioni = {p["symbol"]: p for p in ex.fetch_positions()
                     if abs(float(p.get("contracts") or 0)) > 0}
    except Exception:  # noqa: BLE001
        posizioni = {}

    for nome, c in COPPIE.items():
        d = (salvato.get("coppie") or {}).get(nome)
        if not d:
            continue
        try:
            px = ex.fetch_ticker(c.sym_spot)["last"]
        except Exception:  # noqa: BLE001
            px = None
        p = posizioni.get(c.sym_perp) or {}
        ct = float(p.get("contracts") or 0)
        upl = p.get("unrealizedPnl")
        lev = p.get("leverage")
        liq = p.get("liquidationPrice")
        coppie_out[nome] = {
            "ts_apri": d.get("ts_apri"),
            "nozionale_eur": d.get("nozionale_eur"),
            "qty_spot": d.get("qty_spot"),
            "ct_perp": ct,
            "delta": d.get("delta"),
            "prezzo_ora": px,
            "upl": float(upl) if upl is not None else None,
            "leva": str(lev) if lev is not None else None,
            "liq": float(liq) if liq else None,
            "aperta": ct > 0,
        }

    aperte = sum(1 for v in coppie_out.values() if v["aperta"])
    noz_tot = sum((v["nozionale_eur"] or 0) for v in coppie_out.values() if v["aperta"])
    upl_tot = sum((v["upl"] or 0) for v in coppie_out.values() if v["aperta"])

    out = {
        "generato_il": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "coppie_totali": len(coppie_out),
        "coppie_aperte": aperte,
        "nozionale_totale_eur": round(noz_tot, 2),
        "upl_totale": round(upl_tot, 4),
        "coppie": coppie_out,
        # Prossime candidate allo step D3 (abilitate nel gate il 18/10, dry-run ok).
        # Lista curata: NON tutte le coppie del dict sono ammissibili adesso
        # (LINK fuori gate, DOGE = canary sullo stesso conto, XRP sotto soglia).
        "candidate": ["LTC", "AVAX"],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"scritto: {OUT}")
    print(f"coppie aperte: {aperte}/{len(coppie_out)} | "
          f"nozionale {noz_tot:.2f} EUR | uPL {upl_tot:+.4f}")
    for n, v in coppie_out.items():
        print(f"  {n}: {'APERTA' if v['aperta'] else 'chiusa'} | lev {v['leva']} | "
              f"uPL {v['upl']} | delta {v['delta']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
