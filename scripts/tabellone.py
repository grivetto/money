#!/usr/bin/env python3
"""tabellone.py — il libro contabile onesto del progetto Denaro.

Risponde a UNA domanda, con numeri e non con sensazioni: **stiamo guadagnando?**

    versato  = depositi - prelievi (netto, in EUR)
    equity   = valore attuale dei conti (aggregator, equity_source=balances)
    netto    = equity - versato            <-- LA risposta
    fee      = commissioni cumulate pagate all'exchange (da OKX bills)
    reale    = PnL realizzato (trade chiusi), al netto delle fee

Fonti (tutte in SOLA LETTURA):
  - equity: aggregator  (default http://[::1]:8912/api/infra.json, campo total_equity)
  - bills / depositi / prelievi: OKX EEA main (chiave IP-bound -> gira su MARCODG1/nuvola)

Uso:
    tabellone.py [--env /home/marco/denaro/secrets/main_okx.env]
                 [--equity-url http://[::1]:8912/api/infra.json]
                 [--versato N]     # se noto, forza il versato e segnala lo scarto
                 [--json]

Nessun ordine, nessun movimento, nessun valore di chiave stampato.
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.request
from pathlib import Path

try:
    import ccxt
except ImportError:  # pragma: no cover
    raise SystemExit("serve ccxt nel venv (es. /home/marco/denaro/venv/bin/python)")

OKX_PUB = "https://eea.okx.com"
#: i bills con pnl != 0 sono trade; questi tipi hanno pnl valorizzato
TIPI_TRADE = {"3", "5"}
TIPI_FEE = {"3", "5", "8", "9", "13", "26"}


def leggi_env(path: str) -> dict:
    d = {}
    for ln in Path(path).read_text().splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#") or "=" not in ln:
            continue
        k, v = ln.split("=", 1)
        d[k.strip()] = v.strip().strip('"').strip("'")
    return d


def prezzo_eur(ccy: str) -> float:
    """Prezzo indicativo di 1 unita' di `ccy` in EUR (spot pubblico)."""
    if ccy in ("EUR", ""):
        return 1.0
    if ccy == "USDC":
        ccy = "USDT"  # USDC ~ USDT per il libro contabile
    for inst in (f"{ccy}-EUR", f"{ccy}-USDT"):
        try:
            r = json.loads(urllib.request.urlopen(
                f"{OKX_PUB}/api/v5/market/ticker?instId={inst}", timeout=10).read())
            px = float(r["data"][0]["last"])
            if inst.endswith("-USDT"):
                e = json.loads(urllib.request.urlopen(
                    f"{OKX_PUB}/api/v5/market/ticker?instId=USDT-EUR", timeout=10).read())
                px *= float(e["data"][0]["last"])
            return px
        except Exception:
            continue
    return 0.0


def equity_aggregator(url: str) -> dict:
    d = json.loads(urllib.request.urlopen(url, timeout=15).read())
    return {"equity": d.get("total_equity"), "source": d.get("equity_source"),
            "breakdown": d.get("equity_breakdown"), "ts": d.get("timestamp")}


def bills(ex, inst_type: str, tetto: int = 60) -> list[dict]:
    out, after = [], None
    for _ in range(tetto):
        p = {"instType": inst_type, "limit": 100}
        if after:
            p["after"] = after
        try:
            d = ex.privateGetAccountBillsArchive(p)["data"]
        except Exception:
            break
        if not d:
            break
        out += d
        after = d[-1]["billId"]
        if len(d) < 100:
            break
        time.sleep(0.25)
    return out


def flussi_eur(ex) -> dict:
    """Depositi e prelievi netti in EUR (best effort: la history puo' essere limitata).
    Il versato affidabile resta quello dichiarato dal proprietario (`--versato`)."""
    tot = 0.0
    dettaglio = []
    for fonte, fn, segno in (("deposito", "privateGetAssetDepositHistory", 1),
                             ("prelievo", "privateGetAssetWithdrawalHistory", -1)):
        try:
            righe = getattr(ex, fn)({"limit": 100})["data"]
        except Exception:
            righe = []
        for r in righe:
            ccy = r.get("ccy") or "EUR"
            try:
                amt = float(r.get("amt") or 0)
            except (TypeError, ValueError):
                continue
            eur = amt * prezzo_eur(ccy) * segno
            tot += eur
            dettaglio.append({"tipo": fonte, "ccy": ccy, "amt": amt,
                              "eur": round(eur, 2), "ts": r.get("ts")})
    return {"netto_eur": round(tot, 2), "n": len(dettaglio), "dettaglio": dettaglio}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default="/home/marco/denaro/secrets/main_okx.env")
    ap.add_argument("--equity-url", default="http://[::1]:8912/api/infra.json")
    ap.add_argument("--versato", type=float, default=None)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    esito: dict = {"data": time.strftime("%Y-%m-%d %H:%M"), "fonti": {}}

    # --- equity (aggregator) ---
    try:
        eq = equity_aggregator(a.equity_url)
        esito["equity_eur"] = eq["equity"]
        esito["fonti"]["equity"] = a.equity_url
    except Exception as e:
        eq = {"equity": None}
        esito["equity_eur"] = None
        esito["errore_equity"] = f"{type(e).__name__}: {e}"

    # --- OKX main: bills, flussi ---
    env = leggi_env(a.env)
    ex = ccxt.okx({"apiKey": env["OKX_API_KEY"], "secret": env["OKX_API_SECRET"],
                   "password": env["OKX_PASSPHRASE"], "hostname": "eea.okx.com",
                   "enableRateLimit": True, "options": {"defaultType": "spot"}})

    tutti = []
    for it in ("SPOT", "SWAP"):
        tutti += bills(ex, it)
    reale = fee = 0.0
    for r in tutti:
        try:
            reale += float(r.get("pnl") or 0)
        except (TypeError, ValueError):
            pass
        try:
            fee += float(r.get("fee") or 0)   # OKX: negativo = pagata
        except (TypeError, ValueError):
            pass
    esito["pnl_realizzato_eur"] = round(reale, 2)
    esito["fee_cumulate_eur"] = round(fee, 2)
    esito["n_bills"] = len(tutti)

    fl = flussi_eur(ex)
    esito["versato_api_eur"] = fl["netto_eur"]
    esito["n_flussi"] = fl["n"]

    versato = a.versato if a.versato is not None else fl["netto_eur"]
    esito["versato_eur"] = versato
    if a.versato is not None:
        esito["scarto_versato_eur"] = round(a.versato - fl["netto_eur"], 2)

    if eq["equity"] is not None:
        esito["netto_vs_versato_eur"] = round(eq["equity"] - versato, 2)

    if a.json:
        print(json.dumps(esito, ensure_ascii=False, indent=2))
        return 0

    print(f"TABELLONE DENARO — {esito['data']}")
    print(f"  versato (netto)      : {versato:>10,.2f} EUR")
    print(f"  equity (aggregator)  : {(eq['equity'] or 0):>10,.2f} EUR   [{eq.get('source')}]")
    print(f"  fee cumulate (OKX)   : {fee:>10,.2f} EUR   ({len(tutti)} movimenti)")
    print(f"  PnL realizzato       : {reale:>10,.2f} EUR")
    if "netto_vs_versato_eur" in esito:
        n = esito["netto_vs_versato_eur"]
        print("  ------------------------------------------------")
        print(f"  NETTO vs VERSATO     : {n:>10,.2f} EUR   {'<-- guadagno' if n > 0 else '<-- perdita'}")
    if "scarto_versato_eur" in esito:
        print(f"  (scarto versato dichiarato vs API: {esito['scarto_versato_eur']:+,.2f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
