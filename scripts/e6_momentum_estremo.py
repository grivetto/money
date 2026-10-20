#!/usr/bin/env python3
"""E6 — «momentum su estremi di 7 giorni»: specchio di E5, giudicato su OOS-3 (Binance).

Regola congelata in coda_catena/E6_momentum_estremo.md. Riusa il motore di E5
(z-score, uscita, stop, costi) invertendo solo il lato del segnale.

Uso:  PYTHONPATH=src .venv/bin/python -u scripts/e6_momentum_estremo.py
"""
from __future__ import annotations

import json
import math
import statistics as st
import sys
from datetime import datetime, timezone
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE / "scripts"))
sys.path.insert(0, str(RADICE / "src"))

import backtest_cascate as bc  # noqa: E402
import e5_meanrev_7g as e5  # noqa: E402
from money.statistica import sharpe_deflazionato, varianza_da_tentativi  # noqa: E402

OUT = RADICE / "prove" / "e6_momentum_estremo_2026-10-21.json"
CONFINE_TRAIN_MS = int(datetime(2024, 6, 1, tzinfo=timezone.utc).timestamp() * 1000)
N_TENTATIVI = 4
DSR_MIN = 0.95


def carica(venue: str) -> dict:
    dati = {}
    for p in sorted(bc.CACHE.glob(f"{venue}_*_1h.json")):
        s = p.name[len(venue) + 1:-len("_1h.json")]
        try:
            if venue == "bybit":
                dati[s] = bc.carica(s)
            else:
                b = json.loads(p.read_text())["barre"]
                if len(b) >= 3000:
                    dati[s] = b
        except Exception:  # noqa: BLE001
            continue
    return dati


def raccogli(dati: dict) -> list:
    """Stesso evento di E5, lato INVERTITO (momentum invece di reversion)."""
    casi = []
    for s, barre in dati.items():
        z = e5.zscores(barre)
        for i, lato in e5.eventi(barre, z):
            lato_inv = -lato
            r = e5.simula(barre, i, z, lato_inv)
            if r is None:
                continue
            netto, stress, motivo, dist = r
            casi.append({"sym": s, "ts": int(barre[i + 1][0]), "netto": netto,
                         "stress": stress, "motivo": motivo, "dist": dist, "lato": lato_inv})
    casi.sort(key=lambda c: c["ts"])
    return casi


def stat(casi):
    xs = [c["netto"] for c in casi]
    n = len(xs)
    if n < 2:
        return {"n": n}
    m = sum(xs) / n
    sd = st.stdev(xs)
    t = m / (sd / math.sqrt(n)) if sd else 0.0
    return {"n": n, "media": m, "mediana": st.median(xs), "t": t,
            "pos": sum(1 for x in xs if x > 0) / n,
            "ci90": [m - 1.645 * sd / math.sqrt(n), m + 1.645 * sd / math.sqrt(n)],
            "stress_media": sum(c["stress"] for c in casi) / n}


def main() -> int:
    bybit, okx, bina = carica("bybit"), carica("okx"), carica("binance")
    print(f"bybit {len(bybit)} | okx {len(okx)} | binance {len(bina)}", flush=True)
    if not bina:
        print("OOS-3 (binance) assente: non si emette verdetto.", flush=True)
        return 2

    cb, co, c3 = raccogli(bybit), raccogli(okx), raccogli(bina)
    print(f"eventi: bybit {len(cb)} | okx {len(co)} | binance {len(c3)}", flush=True)

    train = stat([c for c in cb if c["ts"] < CONFINE_TRAIN_MS])
    oos1 = stat([c for c in cb if c["ts"] >= CONFINE_TRAIN_MS])
    oos2 = stat(co)
    oos3 = stat(c3)

    print(f"\n=== E6 momentum estremi 7g | long z>=+3, short z<=-3 ===")
    for nome, s in (("TRAIN bybit", train), ("OOS-1 bybit", oos1),
                    ("OOS-2 okx", oos2), ("OOS-3 BINANCE", oos3)):
        if s.get("n", 0) < 2:
            print(f"  {nome:14s} n={s.get('n', 0)} — troppo poco")
            continue
        print(f"  {nome:14s} n={s['n']:4d}  media {s['media']:+.3%}  t {s['t']:5.2f}  "
              f"pos {s['pos']:.0%}  CI90 [{s['ci90'][0]:+.3%}, {s['ci90'][1]:+.3%}]  "
              f"stress {s['stress_media']:+.3%}")

    esiti = {
        "T1_oos3": bool(oos3.get("n", 0) >= 30 and oos3.get("media", -1) > 0 and oos3.get("t", 0) >= 2.0),
        "T2_oos2": bool(oos2.get("n", 0) >= 30 and oos2.get("media", -1) > 0 and oos2.get("t", 0) >= 2.0),
        "T3_stress3": bool(oos3.get("n", 0) >= 30 and oos3.get("stress_media", -1) > 0),
        "T4_train": bool(train.get("n", 0) >= 30 and train.get("media", -1) >= 0.005 and train.get("t", 0) >= 3.0),
    }
    sr_visti = []
    for lato in (1, -1):
        tr = [c["netto"] for c in cb if c["ts"] < CONFINE_TRAIN_MS and c["lato"] == lato]
        if len(tr) >= 30 and st.stdev(tr):
            sr_visti.append(sum(tr) / len(tr) / st.stdev(tr))
    var = varianza_da_tentativi(sr_visti) if len(sr_visti) > 1 else 0.0
    tr_all = [c["netto"] for c in cb if c["ts"] < CONFINE_TRAIN_MS]
    dsr = None
    if len(tr_all) >= 30 and st.stdev(tr_all):
        sr = sum(tr_all) / len(tr_all) / st.stdev(tr_all)
        dsr = float(sharpe_deflazionato(sr, len(tr_all), N_TENTATIVI, var)["dsr"])
    esiti["DSR"] = bool(dsr is not None and dsr >= DSR_MIN)

    print("\n--- verdetto ---")
    for k, v in esiti.items():
        print(f"  {k}: {'PASS' if v else 'FAIL'}")
    print(f"  DSR: {None if dsr is None else round(dsr, 4)} (N={N_TENTATIVI}, var {var:.6f})")
    promosso = all(esiti.values())
    print(f"\n=== ESITO: {'PROMOSSO -> canary' if promosso else 'NON PROMUOVIBILE'}")

    per_anno = {}
    for c in cb:
        per_anno.setdefault(c["ts"] // 31536000000 + 1970, []).append(c["netto"])
    print("  bybit per anno: " + "  ".join(f"{a}:{sum(v)/len(v):+.2%}({len(v)})"
                                           for a, v in sorted(per_anno.items())))
    per_anno3 = {}
    for c in c3:
        per_anno3.setdefault(c["ts"] // 31536000000 + 1970, []).append(c["netto"])
    print("  binance per anno: " + "  ".join(f"{a}:{sum(v)/len(v):+.2%}({len(v)})"
                                             for a, v in sorted(per_anno3.items())))
    for lato, nome in ((1, "long"), (-1, "short")):
        xs = [c["netto"] for c in c3 if c["lato"] == lato]
        if len(xs) >= 2:
            m = sum(xs) / len(xs)
            sd = st.stdev(xs)
            print(f"  binance {nome}: n={len(xs)} media {m:+.3%} t {m/(sd/math.sqrt(len(xs))):.2f}")

    OUT.write_text(json.dumps({"data": "2026-10-21", "regola": {"long": "z>=+3", "short": "z<=-3"},
                               "train": train, "oos1": oos1, "oos2": oos2, "oos3": oos3,
                               "esiti": esiti, "dsr": dsr, "promosso": promosso},
                              indent=1, default=str))
    print(f"\nraw json: {OUT.relative_to(RADICE)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
