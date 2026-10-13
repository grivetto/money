#!/usr/bin/env python3
"""funding_watch.py — SORVEGLIANZA DEL FUNDING sui X-Perp OKX EEA. Read-only, nessun ordine.

PERCHE'
=======
Il carry delta-neutral (spot long + perp short) rende solo quando il funding e' alto:
la misura P4 (08/10) ha congelato il verdetto "9/10 simboli sotto la soglia dell'8% netto".
Il funding e' REGIME-DIPENDENTE: in fasi normali vale ~0,01%/8h (~11%/anno lordo), nei
regimi caldi sale molto di piu'. Questo strumento non apre nulla: dice QUANDO il mercato
paga abbastanza da giustificare l'allocazione, e lo dice con i costi reali del conto.

NUMERI
======
  lordo_annuo%   = funding_rate * 3 * 365 * 100        (rate per 8h, 3 regolamenti/giorno)
  netto_annuo%   = lordo_annuo% - costo_roundtrip% * 365 / giorni_tenuta
  costo_roundtrip = 0,30%  (spot ask 0,10 + perp short 0,05 in ingresso + 0,10 + 0,05 in uscita)
  rendimento sul CAPITALE impiegato ~ netto_annuo% / 2 a leva 1x (spot + margine perp)

USO
===
  .venv/bin/python scripts/funding_watch.py                      # soglia 12%, tenuta 30g
  .venv/bin/python scripts/funding_watch.py --soglia 15 --giorni 90
  .venv/bin/python scripts/funding_watch.py --alert              # + Telegram se sopra soglia
  .venv/bin/python scripts/funding_watch.py --json

Il verdetto e' per strumento: SOPRA_SOGLIA / SOTTO_SOGLIA / ILLIQUIDO (spread o volume insufficienti).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0"}
BASE = "https://eea.okx.com"
#: costi REALI del conto (misurati 09/10/2026). Frazioni del notional, andata+ritorno.
COSTO_SPOT_TAKER = 0.0010
COSTO_PERP_TAKER = 0.0005
COSTO_ROUNDTRIP = 2 * COSTO_SPOT_TAKER + 2 * COSTO_PERP_TAKER  # 0,30%
#: spread oltre il quale il prezzo non e' considerato eseguibile
SPREAD_MAX = 0.005
#: volume minimo 24h (controvalore USD) per considerare lo strumento liquido
VOL_MIN = 100_000.0
OUTDIR = Path("prove/funding_watch")
STATO_ALERT = OUTDIR / "stato_alert.json"
COOLDOWN_ALERT_S = 6 * 3600


def get(path: str, params: dict | None = None) -> list:
    url = BASE + path
    if params:
        url += "?" + "&".join(f"{k}={v}" for k, v in params.items())
    req = urllib.request.Request(url, headers=UA)
    return json.loads(urllib.request.urlopen(req, timeout=20).read()).get("data", [])


def lordo_annuo_pct(rate: float) -> float:
    """Funding per 8h -> % annualizzata lorda (3 regolamenti/giorno)."""
    return rate * 3.0 * 365.0 * 100.0


def netto_annuo_pct(rate: float, giorni_tenuta: float,
                    costo_roundtrip: float = COSTO_ROUNDTRIP) -> float:
    """% annualizzata netta: lordo meno i costi round-trip spalmati sui giorni di tenuta."""
    if giorni_tenuta <= 0:
        raise ValueError("giorni_tenuta deve essere > 0")
    return lordo_annuo_pct(rate) - costo_roundtrip * 100.0 * (365.0 / giorni_tenuta)


def rendimento_su_capitale(netto_pct: float, leva: float = 1.0) -> float:
    """Con leva L il capitale impiegato e' notional*(1 + 1/L) -> rendimento sul capitale."""
    return netto_pct / (1.0 + 1.0 / leva)


def scansione(soglia_pct: float, giorni_tenuta: float, max_strumenti: int) -> dict:
    istru = get("/api/v5/public/instruments", {"instType": "FUTURES"})
    xperp = [x for x in istru if "_XPERP" in x.get("instId", "") and x.get("state") == "live"]
    tick = {t["instId"]: t for t in get("/api/v5/market/tickers", {"instType": "FUTURES"})}
    # ordino per liquidita' reale e limito le chiamate di funding
    def vol(inst: str) -> float:
        try:
            return float(tick.get(inst, {}).get("volCcy24h") or 0.0)
        except (TypeError, ValueError):
            return 0.0
    xperp.sort(key=lambda x: vol(x["instId"]), reverse=True)
    righe = []
    for x in xperp[:max_strumenti]:
        inst = x["instId"]
        t = tick.get(inst, {})
        v = vol(inst)
        try:
            r = get("/api/v5/public/funding-rate", {"instId": inst})
        except Exception:
            continue
        if not r or r[0].get("fundingRate") is None:
            continue
        rate = float(r[0]["fundingRate"])
        try:
            bid = float(t.get("bidPx") or 0); ask = float(t.get("askPx") or 0)
        except (TypeError, ValueError):
            bid = ask = 0.0
        spread = (ask - bid) / bid if bid > 0 else 1.0
        netto = netto_annuo_pct(rate, giorni_tenuta)
        if v < VOL_MIN or spread > SPREAD_MAX:
            verdetto = "ILLIQUIDO"
        elif lordo_annuo_pct(rate) >= soglia_pct:
            verdetto = "SOPRA_SOGLIA"
        else:
            verdetto = "SOTTO_SOGLIA"
        righe.append({
            "instId": inst,
            "funding_rate": rate,
            "lordo_annuo_pct": round(lordo_annuo_pct(rate), 3),
            "netto_annuo_pct": round(netto, 3),
            "rend_capitale_leva1_pct": round(rendimento_su_capitale(netto, 1.0), 3),
            "spread_pct": round(spread * 100, 4),
            "vol24h_usd": round(v, 1),
            "verdetto": verdetto,
        })
        time.sleep(0.05)
    righe.sort(key=lambda x: -x["lordo_annuo_pct"])
    sopra = [r for r in righe if r["verdetto"] == "SOPRA_SOGLIA"]
    return {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "soglia_pct": soglia_pct, "giorni_tenuta": giorni_tenuta,
        "costi": {"spot_taker": COSTO_SPOT_TAKER, "perp_taker": COSTO_PERP_TAKER,
                  "roundtrip": COSTO_ROUNDTRIP},
        "strumenti": righe, "sopra_soglia": sopra,
        "n_esaminati": len(righe), "n_illiquidi": sum(1 for r in righe if r["verdetto"] == "ILLIQUIDO"),
    }


def invia_alert(out: dict, cooldown_s: int = COOLDOWN_ALERT_S) -> bool:
    """Telegram se c'e' almeno uno strumento sopra soglia, con cooldown anti-spam."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat or not out["sopra_soglia"]:
        return False
    firma = ",".join(f"{r['instId']}:{round(r['lordo_annuo_pct'])}" for r in out["sopra_soglia"][:5])
    try:
        prec = json.loads(STATO_ALERT.read_text())
    except Exception:
        prec = {}
    ora = time.time()
    if prec.get("firma") == firma and ora - float(prec.get("ts", 0)) < cooldown_s:
        return False
    top = out["sopra_soglia"][:8]
    testo = (f"FUNDING SOPRA SOGLIA ({out['soglia_pct']:.0f}%/anno lordo) — {out['ts']}\n" +
             "\n".join(f"{r['instId']}: lordo {r['lordo_annuo_pct']:.1f}%/a, "
                       f"netto {r['netto_annuo_pct']:.1f}%/a ({out['giorni_tenuta']:.0f}g), "
                       f"cap.leva1 {r['rend_capitale_leva1_pct']:.1f}%" for r in top))
    dati = json.dumps({"chat_id": chat, "text": testo}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage", data=dati,
        headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=15).read()
    except Exception as e:
        print("alert fallito:", str(e)[:120], file=sys.stderr)
        return False
    OUTDIR.mkdir(parents=True, exist_ok=True)
    STATO_ALERT.write_text(json.dumps({"firma": firma, "ts": ora}))
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="Sorveglianza funding X-Perp OKX EEA (read-only)")
    ap.add_argument("--soglia", type=float, default=12.0, help="soglia lordo annualizzato %%")
    ap.add_argument("--giorni", type=float, default=30.0, help="giorni di tenuta per il calcolo netto")
    ap.add_argument("--max-strumenti", type=int, default=60, help="max X-Perp esaminati (per liquidita')")
    ap.add_argument("--alert", action="store_true", help="invia Telegram se sopra soglia")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    out = scansione(a.soglia, a.giorni, a.max_strumenti)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    path = OUTDIR / f"funding_watch_{out['ts'].replace(':', '').replace('-', '')}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1))

    if a.alert:
        invia_alert(out)

    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return 0

    print(f"FUNDING WATCH X-PERP — {out['ts']} | soglia {a.soglia:.1f}%/anno lordo | tenuta {a.giorni:.0f}g")
    print(f"  costi round-trip {COSTO_ROUNDTRIP*100:.2f}% (spot 0,10 + perp 0,05 x2) | "
          f"esaminati {out['n_esaminati']} (illiquidi {out['n_illiquidi']})")
    print(f"  {'instId':26s} {'fund%':>8s} {'lordo%/a':>9s} {'netto%/a':>9s} {'cap.lev1%':>9s} {'spr%':>7s}  verdetto")
    print("  " + "-" * 84)
    for r in out["strumenti"][:15]:
        print(f"  {r['instId']:26s} {r['funding_rate']*100:8.4f} {r['lordo_annuo_pct']:9.2f} "
              f"{r['netto_annuo_pct']:9.2f} {r['rend_capitale_leva1_pct']:9.2f} {r['spread_pct']:7.3f}  {r['verdetto']}")
    print("  " + "-" * 84)
    print(f"  SOPRA SOGLIA: {len(out['sopra_soglia'])} strumenti")
    print(f"  artefatto: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
