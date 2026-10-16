#!/usr/bin/env python3
"""P19b — FUNDING MULTI-VENUE: la MEDIA STORICA, non l'istantaneo.

PERCHE' ESISTE
==============
P19 ha misurato il funding ISTANTANEO: Bybit dava 0,00628%/8h su BTC (=+10,65%
annuo stimato). Ma la media su 200 periodi e' +4,71%: il valore istantaneo era
un picco. Misurare il funding istantaneo e' sbagliato per decidere un carry che
si tiene per settimane.

Qui si misura la MEDIA su finestre lunghe (storia disponibile per simbolo) e si
confronta OKX EEA vs Bybit sullo STESSO simbolo e lo STESSO periodo.

METRICA (dichiarata prima dei numeri)
======================================
  media_8h   = media aritmetica dei funding rate storici
  annuo      = media_8h * 3 * 365
  stabile    = frazione di periodi con funding > 0
  netto      = annuo - costo_ciclo_assunto
  affidabile = almeno 100 periodi di storia (sotto, la media e' rumorosa)

Sola lettura. Nessun ordine.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

SIMBOLI = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "DOGE/USDT:USDT",
           "XRP/USDT:USDT", "ADA/USDT:USDT", "DOT/USDT:USDT", "LINK/USDT:USDT",
           "AVAX/USDT:USDT", "LTC/USDT:USDT"]

COSTO_CICLO = {"okx_eea": 0.0034, "bybit": 0.0030}
MIN_PERIODI = 100


def media_funding(ex, sym: str, limit: int = 200) -> dict:
    try:
        h = ex.fetch_funding_rate_history(sym, limit=limit)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "errore": f"{type(e).__name__}: {str(e)[:70]}"}
    rates = [float(x["fundingRate"]) for x in h if x.get("fundingRate") is not None]
    if not rates:
        return {"ok": False, "errore": "nessun dato"}
    n = len(rates)
    media = sum(rates) / n
    return {
        "ok": True, "n": n, "media_8h": media,
        "annuo": media * 3 * 365,
        "stabile": sum(1 for r in rates if r > 0) / n,
        "min": min(rates), "max": max(rates),
        "affidabile": n >= MIN_PERIODI,
    }


def main() -> int:
    import ccxt
    venue = {
        "okx_eea": ccxt.okx({"hostname": "eea.okx.com", "enableRateLimit": True,
                             "options": {"defaultType": "swap"}}),
        "bybit": ccxt.bybit({"enableRateLimit": True,
                             "options": {"defaultType": "swap"}}),
    }

    print("=== P19b — FUNDING: media storica su 200 periodi (8h) ===")
    print("(l'istantaneo e' un picco: quello che conta e' la media)")
    print()

    ris = {}
    for nome, ex in venue.items():
        ris[nome] = {}
        print(f"--- {nome}")
        for sym in SIMBOLI:
            base = sym.split("/")[0]
            r = media_funding(ex, sym)
            ris[nome][base] = r
            if not r["ok"]:
                print(f"    {base:6s} ERR {r['errore']}")
                continue
            costo = COSTO_CICLO.get(nome, 0.0034)
            netto = r["annuo"] - costo
            tag = "CARRY" if netto > 0 and r["affidabile"] else "  --  "
            print(f"    {base:6s} n={r['n']:3d} media {r['media_8h']*100:+.5f}%/8h  "
                  f"annuo {r['annuo']*100:+6.2f}%  netto {netto*100:+6.2f}%  "
                  f"pos {r['stabile']*100:3.0f}%  [{tag}]")
        print()

    # ── chi paga di piu', sullo stesso simbolo, con dati affidabili ──
    print("=== CONFRONTO DIRETTO (solo media affidabili, n>=100) ===")
    print(f"{'simbolo':8s} {'OKX EEA':>12s} {'Bybit':>12s} {'delta':>10s} {'vince':>8s}")
    print("-" * 54)
    vignette = []
    for base in sorted({b for v in ris.values() for b in v}):
        o = ris["okx_eea"].get(base, {})
        b = ris["bybit"].get(base, {})
        if not (o.get("ok") and b.get("ok")):
            continue
        ao, ab = o["annuo"], b["annuo"]
        delta = ab - ao
        vincitore = "bybit" if delta > 0 else "okx_eea" if delta < 0 else "pari"
        vignette.append((base, ao, ab, delta, vincitore))
        print(f"{base:8s} {ao*100:>11.2f}% {ab*100:>11.2f}% {delta*100:>9.2f}% {vincitore:>8s}")

    print()
    conteggio = {}
    for *_, v in vignette:
        conteggio[v] = conteggio.get(v, 0) + 1
    print(f"chi paga di piu': {conteggio}")

    # ── dove il carry e' MIGLIORE (il numero che serve alla decisione) ──
    print()
    print("=== DOVE IL CARRY RENDE DI PIU' (media storica, netto annuo) ===")
    tutti = []
    for nome, per_base in ris.items():
        costo = COSTO_CICLO.get(nome, 0.0034)
        for base, r in per_base.items():
            if r.get("ok") and r.get("affidabile"):
                tutti.append((nome, base, r["annuo"] - costo, r["stabile"]))
    tutti.sort(key=lambda x: -x[2])
    for nome, base, netto, stab in tutti[:10]:
        print(f"  {base:6s} su {nome:9s} netto {netto*100:+6.2f}%/anno  (positivi {stab*100:.0f}%)")

    out = ROOT / "prove" / "P19b_funding_media.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "risultati": ris, "confronto": [
            {"simbolo": b, "okx_eea": o, "bybit": x, "delta": d, "vince": v}
            for b, o, x, d, v in vignette],
        "costo_ciclo": COSTO_CICLO,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }, indent=2, default=str))
    print(f"\nartefatto: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
