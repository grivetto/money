#!/usr/bin/env python3
"""E4 — «cascate profonde»: misura e verdetto con la regola congelata in
coda_catena/E4_cascate_profonde.md (soglia -10%, H=12, long, stop 2,5xATR).

Nessuna griglia: la soglia del verdetto e' -10%. -12 e -15 si misurano SOLO per
contare i look nella deflazione (N cumulativo = 21).

Uso:  PYTHONPATH=src .venv/bin/python -u scripts/e4_cascate_profonde.py
Output: prove/e4_cascate_profonde_2026-10-21.json + riepilogo a schermo.
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

OUT = RADICE / "prove" / "e4_cascate_profonde_2026-10-21.json"
CONFINE_TRAIN_MS = int(datetime(2024, 6, 1, tzinfo=timezone.utc).timestamp() * 1000)
SOGLIA_VERDETTO = -0.10
SOGLIE_LOOK = (-0.10, -0.12, -0.15)
H = 12
N_TENTATIVI = 21          # 18 di E2 + 3 soglie E4 (dichiarato prima)
DSR_MIN = 0.95
T1_N_MIN = 30
T1_T_MIN = 2.0
T2_T_MIN = 2.0
T4_MEDIA_MIN = 0.005
T4_T_MIN = 3.0


def carica_bybit() -> dict:
    dati, esclusi = {}, []
    for p in sorted(bc.CACHE.glob("bybit_*_1h.json")):
        s = p.name[len("bybit_"):-len("_1h.json")]
        try:
            dati[s] = bc.carica(s)
        except Exception as exc:  # noqa: BLE001
            esclusi.append(f"{s}: {exc}")
    print(f"bybit: {len(dati)} simboli | esclusi: {', '.join(esclusi) or 'nessuno'}", flush=True)
    return dati


def carica_okx() -> dict:
    dati = {}
    for p in sorted(bc.CACHE.glob("okx_*_1h.json")):
        try:
            d = json.loads(p.read_text())
        except Exception as exc:  # noqa: BLE001
            print(f"  salto {p.name}: {exc}", flush=True)
            continue
        s = d.get("simbolo") or p.name[len("okx_"):-len("_1h.json")]
        barre = d["barre"]
        if len(barre) < 3000:
            continue
        prev, rotto = None, False
        for b in barre:
            c = float(b[4])
            if c <= 0 or float(b[1]) <= 0:
                rotto = True
                break
            if prev is not None and not (1 / 3.0 < c / prev < 3.0):
                rotto = True
                break
            prev = c
        if rotto:
            print(f"  salto {s}: serie rotta", flush=True)
            continue
        dati[s] = barre
    print(f"okx: {len(dati)} simboli", flush=True)
    return dati


def stat(casi: list[dict]) -> dict:
    xs = [c["netto"] for c in casi]
    n = len(xs)
    if n < 2:
        return {"n": n}
    m = sum(xs) / n
    sd = st.stdev(xs)
    t = m / (sd / math.sqrt(n)) if sd else 0.0
    ci90 = (m - 1.645 * sd / math.sqrt(n), m + 1.645 * sd / math.sqrt(n))
    return {"n": n, "media": m, "mediana": st.median(xs), "sd": sd, "t": t,
            "pos": sum(1 for x in xs if x > 0) / n, "ci90": list(ci90),
            "stress_media": sum(c["stress"] for c in casi) / n}


def prendi(casi, *, train=None, dal=None, fino=None):
    out = casi
    if train is True:
        out = [c for c in out if c["ts"] < CONFINE_TRAIN_MS]
    elif train is False:
        out = [c for c in out if c["ts"] >= CONFINE_TRAIN_MS]
    if dal:
        out = [c for c in out if c["ts"] >= dal]
    if fino:
        out = [c for c in out if c["ts"] < fino]
    return out


def main() -> int:
    bybit, okx = carica_bybit(), carica_okx()

    casi_bybit = bc.raccogli(bybit, H, long=True, soglia=SOGLIA_VERDETTO)
    casi_okx = bc.raccogli(okx, H, long=True, soglia=SOGLIA_VERDETTO)

    train = stat(prendi(casi_bybit, train=True))
    oos1 = stat(prendi(casi_bybit, train=False))
    oos2 = stat(casi_okx)

    print(f"\n=== E4 cascate profonde | soglia {SOGLIA_VERDETTO:.0%} | H={H}h | long ===")
    for nome, s in (("TRAIN bybit", train), ("OOS-1 bybit", oos1), ("OOS-2 okx", oos2)):
        if s.get("n", 0) < 2:
            print(f"  {nome:14s} n={s.get('n', 0)} — troppo poco")
            continue
        print(f"  {nome:14s} n={s['n']:4d}  media {s['media']:+.3%}  t {s['t']:5.2f}  "
              f"pos {s['pos']:.0%}  CI90 [{s['ci90'][0]:+.3%}, {s['ci90'][1]:+.3%}]  "
              f"stress {s['stress_media']:+.3%}")

    # --- verdetto: 4 test, 4/4 ---
    esiti = {}
    esiti["T1"] = bool(oos2.get("n", 0) >= T1_N_MIN and oos2.get("media", -1) > 0
                       and oos2.get("t", 0) >= T1_T_MIN)
    esiti["T2"] = bool(oos1.get("n", 0) >= 30 and oos1.get("media", -1) > 0
                       and oos1.get("t", 0) >= T2_T_MIN)
    esiti["T3"] = bool(oos2.get("n", 0) >= T1_N_MIN and oos2.get("stress_media", -1) > 0)
    esiti["T4"] = bool(train.get("n", 0) >= 30 and train.get("media", -1) >= T4_MEDIA_MIN
                       and train.get("t", 0) >= T4_T_MIN)

    # --- DSR (deflazione sui 21 look) ---
    sr_visti = []
    for sg in SOGLIE_LOOK:
        for h in (4, 12, 24):
            c = bc.raccogli(bybit, h, long=True, soglia=sg)
            tr = [x["netto"] for x in c if x["ts"] < CONFINE_TRAIN_MS]
            if len(tr) >= 30 and st.stdev(tr):
                sr_visti.append(sum(tr) / len(tr) / st.stdev(tr))
    c_short = bc.raccogli(bybit, H, long=False, soglia=SOGLIA_VERDETTO)
    tr_short = [x["netto"] for x in c_short if x["ts"] < CONFINE_TRAIN_MS]
    if len(tr_short) >= 30 and st.stdev(tr_short):
        sr_visti.append(sum(tr_short) / len(tr_short) / st.stdev(tr_short))
    var = varianza_da_tentativi(sr_visti) if len(sr_visti) > 1 else 0.0
    tr_v = [x["netto"] for x in casi_bybit if x["ts"] < CONFINE_TRAIN_MS]
    dsr = None
    if len(tr_v) >= 30 and st.stdev(tr_v):
        sr_v = sum(tr_v) / len(tr_v) / st.stdev(tr_v)
        d = sharpe_deflazionato(sr_v, len(tr_v), N_TENTATIVI, var)
        dsr = float(d["dsr"])
    esiti["DSR"] = bool(dsr is not None and dsr >= DSR_MIN)

    print("\n--- verdetto (4/4 + DSR) ---")
    for k, v in esiti.items():
        print(f"  {k}: {'PASS' if v else 'FAIL'}")
    print(f"  DSR valore: {dsr:.3f} (N={N_TENTATIVI}, var SR {var:.6f}, look misurati {len(sr_visti)})")
    promosso = all(esiti.values())
    print(f"\n=== ESITO: {'PROMOSSO -> canary' if promosso else 'NON PROMUOVIBILE - famiglia chiusa'}")

    # profondita' (dose-response descrittiva, non entra nel verdetto)
    import chiusura_cascate as cc  # noqa: E402
    estesi = cc.raccogli_esteso(bybit, H, long=True, soglia=SOGLIA_VERDETTO)
    print("\n--- dose-response (descrittiva, fuori verdetto) ---")
    for nome, (lo, hi) in (("[-10,-12)", (-0.12, -0.10)), ("[-12,-15)", (-0.15, -0.12)),
                           ("<=-15%", (float("-inf"), -0.15))):
        xs = [c["netto"] for c in estesi if lo < c["drop3"] <= hi]
        if len(xs) >= 2:
            m = sum(xs) / len(xs)
            sd = st.stdev(xs)
            print(f"  {nome:10s} n={len(xs):3d}  media {m:+.3%}  t {m/(sd/math.sqrt(len(xs))):5.2f}")

    OUT.write_text(json.dumps({"data": "2026-10-21", "soglia": SOGLIA_VERDETTO, "h": H,
                               "train": train, "oos1": oos1, "oos2": oos2,
                               "esiti": esiti, "dsr": dsr, "promosso": promosso},
                              indent=1, default=str))
    print(f"\nraw json: {OUT.relative_to(RADICE)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
