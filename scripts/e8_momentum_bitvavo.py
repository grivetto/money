#!/usr/bin/env python3
"""E8 — «momentum estremo sui major liquidi — hold-out Bitvavo» (spec: coda_catena/E8_...).

Un solo set, mai toccato: Bitvavo 1h, 7 coppie EUR congelate al 28/10/2026, 2024-06-01 -> 2026-10-28.
Regola identica a E6 (zero gradi di liberta'): z=(close-SMA168)/stdev168; long z>=+3, short z<=-3;
cooldown 24h; ingresso open(i+1); uscita prima barra |z|<=0.5 o 72h; stop 3xATR14 (max 50%).

Motore: riuso di scripts/e5_meanrev_7g.py (zscores/eventi/simula, lato invertito come E6)
con i costi del tariffario PUBBLICO Bitvavo: taker 0,25%/lato -> RT 0,50%; stress x2 = 1,00%;
scenario maker 0,30% RT (solo descrittivo).

La varianza del DSR e' stimata sui look STORICI della famiglia (E5 x2 + E6 x2), ricalcolati
qui dai loro stessi motori/dataset (Bybit, training) come da spec; N = 5.

Uso:  cd ~/money && .venv/bin/python scripts/e8_momentum_bitvavo.py
Output: prove/e8_bitvavo.json + prove/e8_bitvavo.txt (e riepilogo a schermo).
"""
from __future__ import annotations

import json
import math
import random
import statistics as st
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE / "scripts"))
sys.path.insert(0, str(RADICE / "src"))

import backtest_cascate as bc  # noqa: E402
import e5_meanrev_7g as e5  # noqa: E402
from money.statistica import sharpe_deflazionato, varianza_da_tentativi  # noqa: E402

COSTO_RT = 0.0050          # Bitvavo taker 0,25%/lato -> RT 0,50%
COSTO_RT_STRESS = 0.0100   # stress x2
COSTO_RT_MAKER = 0.0030    # scenario descrittivo
N_LOOK = 5                 # famiglia: E5 x2, E6 x2, E8 x1
DSR_MIN = 0.95
CONFINE_TRAIN_MS = int(datetime(2024, 6, 1, tzinfo=timezone.utc).timestamp() * 1000)

COPPIE = ["BTC-EUR", "XRP-EUR", "ETH-EUR", "SOL-EUR", "HYPE-EUR", "ADA-EUR", "PEPE-EUR"]
OUT_JSON = RADICE / "prove" / "e8_bitvavo.json"
OUT_TXT = RADICE / "prove" / "e8_bitvavo.txt"


def carica_bitvavo() -> dict[str, list]:
    dati = {}
    for coppia in COPPIE:
        p = bc.CACHE / f"bitvavo_{coppia}_1h.json"
        if not p.exists():
            raise SystemExit(f"dato Bitvavo mancante: {p} (scarica con scripts/scarica_bitvavo_1h.py)")
        b = json.loads(p.read_text())["barre"]
        if len(b) < 3000:
            raise SystemExit(f"storia troppo corta per {coppia}: {len(b)} barre")
        dati[coppia] = b
    return dati


def carica_bybit() -> dict[str, list]:
    dati = {}
    for p in sorted(bc.CACHE.glob("bybit_*_1h.json")):
        s = p.name[len("bybit_"):-len("_1h.json")]
        try:
            dati[s] = bc.carica(s)
        except Exception:  # noqa: BLE001
            continue
    return dati


def raccogli(dati: dict[str, list]) -> list[dict]:
    """Evento E5/E6, lato INVERTITO (momentum), costi dal modulo e5 (patchati a monte)."""
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


def ci90_bootstrap(xs: list[float], n_boot: int = 10000, seed: int = 42) -> list[float] | None:
    n = len(xs)
    if n < 2:
        return None
    rnd = random.Random(seed)
    medie = []
    for _ in range(n_boot):
        s = 0.0
        for _ in range(n):
            s += xs[rnd.randrange(n)]
        medie.append(s / n)
    medie.sort()
    return [medie[int(0.05 * n_boot)], medie[int(0.95 * n_boot) - 1]]


def stat(casi: list[dict]) -> dict:
    xs = [c["netto"] for c in casi]
    n = len(xs)
    if n < 2:
        return {"n": n}
    m = sum(xs) / n
    sd = st.stdev(xs)
    t = m / (sd / math.sqrt(n)) if sd else 0.0
    return {"n": n, "media": m, "mediana": st.median(xs), "t": t,
            "pos": sum(1 for x in xs if x > 0) / n,
            "ci90_boot": ci90_bootstrap(xs),
            "stress_media": sum(c["stress"] for c in casi) / n,
            "maker_media": m + (COSTO_RT - COSTO_RT_MAKER)}


def sr(xs: list[float]) -> float | None:
    if len(xs) < 30 or st.stdev(xs) == 0:
        return None
    return (sum(xs) / len(xs)) / st.stdev(xs)


def main() -> int:
    t0 = time.time()

    # 1) look storici della famiglia (E5 x2, E6 x2) per la varianza del DSR — costi ORIGINALI e5
    bybit = carica_bybit()
    # E5 (reversion): lato NON invertito, ricostruito dai suoi stessi eventi e dal suo simula.
    casi_e5 = []
    for s, barre in bybit.items():
        z = e5.zscores(barre)
        for i, lato in e5.eventi(barre, z):          # lato: 1 su z<=-3, -1 su z>=+3 (mean-reversion)
            r = e5.simula(barre, i, z, lato)
            if r is None:
                continue
            netto, stress, motivo, dist = r
            casi_e5.append({"sym": s, "ts": int(barre[i + 1][0]), "netto": netto,
                            "lato": lato})
    casi_e6 = raccogli(bybit)                        # lato invertito (momentum)
    train5 = [c for c in casi_e5 if c["ts"] < CONFINE_TRAIN_MS]
    train6 = [c for c in casi_e6 if c["ts"] < CONFINE_TRAIN_MS]
    sr_visti = []
    for lato in (1, -1):
        v = sr([c["netto"] for c in train5 if c["lato"] == lato])
        if v is not None:
            sr_visti.append(v)
        v = sr([c["netto"] for c in train6 if c["lato"] == lato])
        if v is not None:
            sr_visti.append(v)
    var = varianza_da_tentativi(sr_visti) if len(sr_visti) > 1 else 0.0

    # 2) misure E8 col tariffario Bitvavo
    e5.COSTO_RT = COSTO_RT
    e5.COSTO_RT_STRESS = COSTO_RT_STRESS
    bitvavo = carica_bitvavo()
    casi = raccogli(bitvavo)

    agg = stat(casi)
    long_s = stat([c for c in casi if c["lato"] == 1])
    short_s = stat([c for c in casi if c["lato"] == -1])
    per_coppia = {s: stat([c for c in casi if c["sym"] == s]) for s in bitvavo}

    sr_e8 = sr([c["netto"] for c in casi])
    dsr = None
    if sr_e8 is not None:
        dsr = float(sharpe_deflazionato(sr_e8, agg["n"], N_LOOK, var)["dsr"])

    esiti = {
        "T1_bitvavo": bool(agg["n"] >= 30 and agg["media"] > 0 and agg["t"] >= 2.0),
        "T2_costi_x2": bool(agg["n"] >= 30 and agg["stress_media"] > 0),
        "T3_long": bool(long_s.get("n", 0) >= 2 and long_s["media"] > 0 and long_s["t"] >= 2.0),
        "DSR": bool(dsr is not None and dsr >= DSR_MIN),
    }
    promosso = all(esiti.values())

    righe = []
    righe.append("=== E8 momentum estremo | hold-out Bitvavo 1h | z>=+3 long, z<=-3 short ===")
    righe.append(f"finestra: 2024-06-01 -> 2026-10-28 | coppie: {', '.join(COPPIE)}")
    righe.append(f"costi: RT {COSTO_RT:.2%} (taker 0,25%/lato) | stress {COSTO_RT_STRESS:.2%} | maker (descrittivo) {COSTO_RT_MAKER:.2%}")
    righe.append("")
    for nome, s in (("AGGREGATO", agg), ("LONG", long_s), ("SHORT", short_s)):
        if s.get("n", 0) < 2:
            righe.append(f"{nome:10s} n={s.get('n', 0)} — troppo poco")
            continue
        cb = s["ci90_boot"]
        righe.append(f"{nome:10s} n={s['n']:4d}  media {s['media']:+.3%}  t {s['t']:5.2f}  pos {s['pos']:.0%}  "
                     f"CI90boot [{cb[0]:+.3%}, {cb[1]:+.3%}]  stress {s['stress_media']:+.3%}  maker {s['maker_media']:+.3%}")
    righe.append("")
    righe.append("per coppia (costi base):")
    for s, stt in per_coppia.items():
        if stt.get("n", 0) < 2:
            righe.append(f"  {s:9s} n={stt.get('n', 0)}")
            continue
        righe.append(f"  {s:9s} n={stt['n']:3d}  media {stt['media']:+.3%}  t {stt['t']:5.2f}  stress {stt['stress_media']:+.3%}")
    righe.append("")
    righe.append("--- verdetto (spec E8) ---")
    for k, v in esiti.items():
        righe.append(f"  {k}: {'PASS' if v else 'FAIL'}")
    righe.append(f"  DSR={None if dsr is None else round(dsr, 4)} (N={N_LOOK}, var={var:.6f}, sr_visti={[round(x, 4) for x in sr_visti]})")
    righe.append(f"\n=== ESITO: {'PROMOSSO -> canary (solo con go owner)' if promosso else 'NON PROMOSSO — vedi spec: se fallisce, famiglia chiusa'} ===")
    righe.append(f"(runtime {time.time() - t0:.1f}s)")

    testo = "\n".join(righe)
    print(testo)
    OUT_TXT.write_text(testo + "\n", encoding="utf-8")
    OUT_JSON.write_text(json.dumps({
        "data": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "spec": "coda_catena/E8_momentum_estremo_holdout_bitvavo.md",
        "finestra": ["2024-06-01", "2026-10-28"],
        "coppie": COPPIE,
        "costi": {"rt_base": COSTO_RT, "rt_stress": COSTO_RT_STRESS, "rt_maker": COSTO_RT_MAKER},
        "aggregato": agg, "long": long_s, "short": short_s, "per_coppia": per_coppia,
        "esiti": esiti, "promosso": promosso, "dsr": dsr,
        "dsr_var": var, "dsr_sr_visti": sr_visti, "dsr_n_look": N_LOOK,
        "limiti": ["gaps>1h nelle serie (18 per coppia, 46 HYPE) trattati come barre contigue",
                   "HYPE-EUR parte dal listing (2024-12-18)",
                   "tariffario Bitvavo pubblico (tier base), fee reali sul conto non misurate",
                   "costi pagati interamente per trade (nessun netting/ribilanciamento)"],
    }, indent=1, default=str), encoding="utf-8")
    print(f"\nartefatti: {OUT_JSON.name}, {OUT_TXT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
