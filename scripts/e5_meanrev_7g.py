#!/usr/bin/env python3
"""E5 — «ritorno alla media a 7 giorni»: misura e verdetto con la regola congelata in
coda_catena/E5_meanrev_7g.md.

Uso:  PYTHONPATH=src .venv/bin/python -u scripts/e5_meanrev_7g.py
Output: prove/e5_meanrev_7g_2026-10-21.json + riepilogo a schermo.
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
from money.statistica import sharpe_deflazionato, varianza_da_tentativi  # noqa: E402

OUT = RADICE / "prove" / "e5_meanrev_7g_2026-10-21.json"
CONFINE_TRAIN_MS = int(datetime(2024, 6, 1, tzinfo=timezone.utc).timestamp() * 1000)
LEN = 168          # 7 giorni di barre 1h
Z_IN = 3.0
Z_OUT = 0.5
MAX_ORE = 72
COOLDOWN = 24
STOP_MULT = 3.0
STOP_MAX = 0.50
COSTO_RT = 0.0020 + 2 * 0.0004
COSTO_RT_STRESS = 2 * COSTO_RT
N_TENTATIVI = 2
DSR_MIN = 0.95


def zscores(barre):
    """z(i) = (close - SMA168)/stdev168, con somme cumulative (O(n))."""
    n = len(barre)
    c = [float(b[4]) for b in barre]
    pc = [0.0] * (n + 1)
    pc2 = [0.0] * (n + 1)
    for k, v in enumerate(c):
        pc[k + 1] = pc[k] + v
        pc2[k + 1] = pc2[k] + v * v
    z = [None] * n
    for i in range(LEN - 1, n):
        s = pc[i + 1] - pc[i + 1 - LEN]
        s2 = pc2[i + 1] - pc2[i + 1 - LEN]
        m = s / LEN
        var = max(0.0, s2 / LEN - m * m)
        sd = math.sqrt(var)
        z[i] = (c[i] - m) / sd if sd > 1e-12 else None
    return z


def eventi(barre, z):
    fuori, ultimo = [], -10**9
    for i in range(LEN + 72, len(barre) - MAX_ORE - 2):
        if i - ultimo <= COOLDOWN:
            continue
        zi = z[i]
        if zi is None:
            continue
        if zi <= -Z_IN:
            fuori.append((i, 1))
            ultimo = i
        elif zi >= Z_IN:
            fuori.append((i, -1))
            ultimo = i
    return fuori


def simula(barre, i, z, lato):
    ingresso = float(barre[i + 1][1])
    if ingresso <= 0:
        return None
    dist = min(STOP_MULT * bc.atr14(barre, i) / ingresso, STOP_MAX)
    stop = ingresso * (1.0 - dist) if lato == 1 else ingresso * (1.0 + dist)
    uscita, motivo = None, "tempo"
    ultima = min(i + MAX_ORE, len(barre) - 1)
    for j in range(i + 1, ultima + 1):
        o, hi, lo = float(barre[j][1]), float(barre[j][2]), float(barre[j][3])
        if lato == 1:
            if o <= stop:
                uscita, motivo = o, "stop_gap"
                break
            if lo <= stop:
                uscita, motivo = stop, "stop"
                break
        else:
            if o >= stop:
                uscita, motivo = o, "stop_gap"
                break
            if hi >= stop:
                uscita, motivo = stop, "stop"
                break
        zj = z[j]
        # uscita = ritorno verso la media, SIMMETRICA nei due lati: |z| <= Z_OUT.
        # (La prima versione usava una disuguaglianza per lato: per il lato "momentum"
        #  era vera alla prima barra e il trade usciva subito — bug trovato il 21/10
        #  dal t anomala di E6, -7,93 su un'inversione che doveva essere speculare.)
        if zj is not None and abs(zj) <= Z_OUT:
            uscita, motivo = float(barre[j][4]), "rientro"
            break
    if uscita is None:
        uscita = float(barre[ultima][4])
    lordo = (uscita / ingresso - 1.0) * lato
    return lordo - COSTO_RT, lordo - COSTO_RT_STRESS, motivo, dist


def raccogli(dati, lato_filtro=None):
    casi = []
    for s, barre in dati.items():
        z = zscores(barre)
        for i, lato in eventi(barre, z):
            if lato_filtro and lato != lato_filtro:
                continue
            r = simula(barre, i, z, lato)
            if r is None:
                continue
            netto, stress, motivo, dist = r
            casi.append({"sym": s, "ts": int(barre[i + 1][0]), "netto": netto,
                         "stress": stress, "motivo": motivo, "dist": dist, "lato": lato})
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
    bybit, okx = {}, {}
    for p in sorted(bc.CACHE.glob("bybit_*_1h.json")):
        s = p.name[len("bybit_"):-len("_1h.json")]
        try:
            bybit[s] = bc.carica(s)
        except Exception:  # noqa: BLE001
            pass
    for p in sorted(bc.CACHE.glob("okx_*_1h.json")):
        try:
            d = json.loads(p.read_text())
        except Exception:  # noqa: BLE001
            continue
        s = d.get("simbolo") or p.name
        b = d["barre"]
        if len(b) >= 3000:
            okx[s] = b
    print(f"bybit {len(bybit)} simboli | okx {len(okx)} simboli", flush=True)

    casi_b = raccogli(bybit)
    casi_o = raccogli(okx)
    print(f"eventi: bybit {len(casi_b)} | okx {len(casi_o)}", flush=True)

    train = stat([c for c in casi_b if c["ts"] < CONFINE_TRAIN_MS])
    oos1 = stat([c for c in casi_b if c["ts"] >= CONFINE_TRAIN_MS])
    oos2 = stat(casi_o)

    print(f"\n=== E5 mean reversion 7g | z±{Z_IN:g} | uscita |z|<={Z_OUT:g} o {MAX_ORE}h ===")
    for nome, s in (("TRAIN bybit", train), ("OOS-1 bybit", oos1), ("OOS-2 okx", oos2)):
        if s.get("n", 0) < 2:
            print(f"  {nome:12s} n={s.get('n', 0)} — troppo poco")
            continue
        print(f"  {nome:12s} n={s['n']:4d}  media {s['media']:+.3%}  t {s['t']:5.2f}  "
              f"pos {s['pos']:.0%}  CI90 [{s['ci90'][0]:+.3%}, {s['ci90'][1]:+.3%}]  "
              f"stress {s['stress_media']:+.3%}")

    esiti = {
        "T1": bool(oos2.get("n", 0) >= 30 and oos2.get("media", -1) > 0 and oos2.get("t", 0) >= 2.0),
        "T2": bool(oos1.get("n", 0) >= 30 and oos1.get("media", -1) > 0 and oos1.get("t", 0) >= 2.0),
        "T3": bool(oos2.get("n", 0) >= 30 and oos2.get("stress_media", -1) > 0),
        "T4": bool(train.get("n", 0) >= 30 and train.get("media", -1) >= 0.005 and train.get("t", 0) >= 3.0),
    }
    sr_visti = []
    for lato in (1, -1):
        tr = [c["netto"] for c in casi_b if c["ts"] < CONFINE_TRAIN_MS and c["lato"] == lato]
        if len(tr) >= 30 and st.stdev(tr):
            sr_visti.append(sum(tr) / len(tr) / st.stdev(tr))
    var = varianza_da_tentativi(sr_visti) if len(sr_visti) > 1 else 0.0
    tr_all = [c["netto"] for c in casi_b if c["ts"] < CONFINE_TRAIN_MS]
    dsr = None
    if len(tr_all) >= 30 and st.stdev(tr_all):
        sr = sum(tr_all) / len(tr_all) / st.stdev(tr_all)
        dsr = float(sharpe_deflazionato(sr, len(tr_all), N_TENTATIVI, var)["dsr"])
    esiti["DSR"] = bool(dsr is not None and dsr >= DSR_MIN)

    print("\n--- verdetto ---")
    for k, v in esiti.items():
        print(f"  {k}: {'PASS' if v else 'FAIL'}")
    print(f"  DSR: {dsr if dsr is None else round(dsr, 3)} (N={N_TENTATIVI}, var {var:.6f})")
    promosso = all(esiti.values())
    print(f"\n=== ESITO: {'PROMOSSO -> canary' if promosso else 'NON PROMUOVIBILE'}")

    # per lato e per anno (descrittivo)
    for lato, nome in ((1, "long"), (-1, "short")):
        xs = [c["netto"] for c in casi_b if c["lato"] == lato]
        if len(xs) >= 2:
            m = sum(xs) / len(xs)
            print(f"  {nome}: n={len(xs)} media {m:+.3%}")
    per_anno = {}
    for c in casi_b:
        per_anno.setdefault(c["ts"] // 31536000000 + 1970, []).append(c["netto"])
    print("  per anno: " + "  ".join(f"{a}:{sum(v)/len(v):+.2%}({len(v)})"
                                     for a, v in sorted(per_anno.items())))

    OUT.write_text(json.dumps({"data": "2026-10-21", "regola": {"z_in": Z_IN, "z_out": Z_OUT,
                                                               "max_ore": MAX_ORE},
                               "train": train, "oos1": oos1, "oos2": oos2,
                               "esiti": esiti, "dsr": dsr, "promosso": promosso},
                              indent=1, default=str))
    print(f"\nraw json: {OUT.relative_to(RADICE)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
