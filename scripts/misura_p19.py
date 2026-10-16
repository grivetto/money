#!/usr/bin/env python3
"""P19 — FUNDING MULTI-VENUE: lo stesso carry su 4 exchange.

L'IPOTESI (dichiarata prima dei numeri)
=======================================
Il carry funding su OKX EEA e' l'unico esperimento PASS del progetto (C1).
Ma il funding e' SPECIFICO DEL VENUE: lo stesso simbolo puo' avere funding
diverso su OKX, Bybit, Binance, Bitget. Se un venue paga di piu', lo stesso
carry rende di piu' — stessa meccanica, stesso rischio, piu' incasso.

Primo dato (2026-10-16): BTC funding 0,00468%/8h su OKX EEA vs 0,00628% su
Bybit = +34%. Da verificare sistematicamente, non su un simbolo.

COSA MISURO (per ogni venue x simbolo)
=======================================
  - funding rate corrente (e media degli ultimi periodi, se disponibile)
  - prezzo (per verificare che il mercato spot esista: senza spot NON e' carry)
  - esistenza del mercato SPOT corrispondente (condizione necessaria del carry)

CRITERIO DI LETTURA (NON promozione)
=====================================
Un venue e' "carryabile" su un simbolo se:
  - ha il perp con funding > 0
  - ha lo spot corrispondente (per coprirsi)
  - il funding netto annuo (dopo costi di ciclo) e' > 0

NON promuove nulla: identifica dove il carry rende di piu'. La spec di
promozione resta money.cancello.

Sola lettura. Nessun ordine, nessuna chiave.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

#: Simboli del progetto (major con storia).
SIMBOLI = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "DOGE/USDT:USDT",
           "XRP/USDT:USDT", "ADA/USDT:USDT", "DOT/USDT:USDT", "LINK/USDT:USDT",
           "AVAX/USDT:USDT", "LTC/USDT:USDT"]

#: Costo di ciclo assunti per venue (fee spot+perp andata e ritorno + spread).
#: Conservativi e DICHIARATI: il carry rende al netto di questi.
COSTO_CICLO = {
    "okx_eea": 0.0034,
    "okx": 0.0034,
    "bybit": 0.0030,
    "binance": 0.0028,
    "bitget": 0.0035,
}

#: Regolamenti di funding al giorno (8h -> 3).
PERIODI_GIORNO = 3
GIORNI_ANNO = 365


def venue():
    import ccxt
    return {
        "okx_eea": ccxt.okx({"hostname": "eea.okx.com", "enableRateLimit": True,
                             "options": {"defaultType": "swap"}}),
        "bybit": ccxt.bybit({"enableRateLimit": True,
                            "options": {"defaultType": "swap"}}),
        "binance": ccxt.binance({"enableRateLimit": True,
                                 "options": {"defaultType": "swap"}}),
        "bitget": ccxt.bitget({"enableRateLimit": True,
                               "options": {"defaultType": "swap"}}),
    }


def main() -> int:
    print("=== P19 — FUNDING MULTI-VENUE ===")
    print("stesso carry (spot long + perp short), 4 exchange: dove rende di piu'?")
    print()

    risultati: Dict[str, Dict[str, dict]] = {}
    for nome, ex in venue().items():
        print(f"--- {nome}")
        try:
            fr = ex.fetch_funding_rates(SIMBOLI)
        except Exception as e:  # noqa: BLE001
            print(f"    ERRORE fetch_funding_rates: {type(e).__name__}: {str(e)[:80]}")
            continue
        risultati[nome] = {}
        for sym_swap, d in fr.items():
            base = sym_swap.split("/")[0]
            spot_sym = f"{base}/USDT"
            rate = d.get("fundingRate")
            if rate is None:
                continue
            # esiste lo spot per coprirsi?
            try:
                ex.load_markets()
                ha_spot = spot_sym in ex.markets
            except Exception:  # noqa: BLE001
                ha_spot = None
            annuo_lordo = rate * PERIODI_GIORNO * GIORNI_ANNO
            costo = COSTO_CICLO.get(nome, 0.0034)
            # il costo si paga 1 volta; su 1 anno di tenuta pesa costo/1 anno
            annuo_netto = annuo_lordo - costo
            risultati[nome][base] = {
                "funding_8h": rate,
                "annuo_lordo": annuo_lordo,
                "annuo_netto": annuo_netto,
                "spot_disponibile": ha_spot,
                "carryabile": bool(rate > 0 and ha_spot and annuo_netto > 0),
            }
        # stampa compatta
        for base in sorted(risultati[nome]):
            v = risultati[nome][base]
            tag = "CARRY" if v["carryabile"] else "  --  "
            print(f"    {base:6s} {v['funding_8h']*100:+.5f}%/8h  "
                  f"lordo {v['annuo_lordo']*100:+6.2f}%  netto {v['annuo_netto']*100:+6.2f}%  "
                  f"spot={'si' if v['spot_disponibile'] else 'NO'}  [{tag}]")
        print()

    # ── confronto: quale venue paga di piu' per ogni simbolo ──
    print("=== CONFRONTO: il venue migliore per ogni simbolo (netto annuo) ===")
    print(f"{'simbolo':8s} " + " ".join(f"{n:>12s}" for n in risultati))
    print("-" * 64)
    migliori = {}
    for base in sorted({b for v in risultati.values() for b in v}):
        riga = {}
        for nome in risultati:
            v = risultati[nome].get(base)
            riga[nome] = v["annuo_netto"] if v else None
        valori = {k: x for k, x in riga.items() if x is not None}
        if valori:
            best = max(valori, key=valori.get)
            migliori[base] = (best, valori[best])
        print(f"{base:8s} " + " ".join(
            (f"{x*100:>11.2f}%" if x is not None else f"{'--':>12s}")
            for x in riga.values()))

    print()
    print("=== DOVE IL CARRY RENDE DI PIU' (top 8 per netto annuo) ===")
    classifica = []
    for base, v in risultati.items():
        pass
    for nome, per_base in risultati.items():
        for base, v in per_base.items():
            if v["carryabile"]:
                classifica.append((nome, base, v["annuo_netto"], v["funding_8h"]))
    classifica.sort(key=lambda x: -x[2])
    for nome, base, netto, f8 in classifica[:8]:
        print(f"  {base:6s} su {nome:9s} netto {netto*100:+6.2f}%/anno  ({f8*100:+.5f}%/8h)")

    print()
    print(f"totale combinazioni carryabili: {len(classifica)}")

    out = ROOT / "prove" / "P19_funding_multivenue.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "risultati": risultati,
        "migliori": {k: {"venue": v[0], "netto": v[1]} for k, v in migliori.items()},
        "classifica": [{"venue": n, "simbolo": b, "netto": x, "funding_8h": f}
                       for n, b, x, f in classifica],
        "costo_ciclo": COSTO_CICLO,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }, indent=2, default=str))
    print(f"artefatto: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
