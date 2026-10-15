#!/usr/bin/env python3
"""Chiusura E2 — «cascate di liquidazione»: i quattro test che mancavano per la promozione.

CRITERI DICHIARATI (2026-10-15, PRIMA di guardare i risultati dei test; congelati in questo file).
La promozione di E2 a capitale richiede 4/4 test superati — niente credito parziale.

Regola sotto test (identica a backtest_cascate.py): caduta 3h <= -8% e volume >= 3x media 72h,
cooldown 12h/simbolo, ingresso apertura i+1, stop 2,5xATR(14) intrabarra (dist <= 50%),
uscita H=12h; costi taker 0,28% RT. Config promossa = cap 5/giorno + filtro se adottato.

TEST 1 — FASCE DI PROFONDITÀ (dose-response)
  Casi H=12 tutti i segnali, fasce per caduta 3h: [-8,-10) [-10,-12) [-12,-15) [<=-15).
  PASS se: (a) ogni fascia con n >= 40 ha media netta > 0;
           (b) la fascia <= -15% ha t >= 2,5;
           (c) media(fascia più profonda) >= media(fascia più superficiale).

TEST 2 — REGIME (2022 negativo: filtro dichiarato, o niente promozione)
  Filtro (unico testato, conta +1 tentativo): entra solo se BTC (1d) close > SMA200 sulla
  ultima barra daily CHIUSA prima dell'ingresso; se SMA200 non disponibile, non blocca.
  PASS se sul set filtrato: (a) media 2022 >= -0,1%; (b) media totale >= +0,7%; (c) OOS > 0.

TEST 3 — SURVIVORSHIP (monete morte)
  Aggiungere LUNC, USTC, FTT, SRM (Bybit spot 1h) al paniere; stessi eventi/simulazione.
  Criterio primario: AGGREGATO NON filtrato e non cappato (superstiti + morte):
  (a) media >= +0,6%/trade; (b) t >= 4,0. Report per-simbolo e per-anno dei morti.

TEST 4 — DSR, CONVENZIONE CONGELATA
  N = 18 tentativi: 9 (griglia soglie -5/-6/-8 x H 4/12/24) + 3 (rilanci finali H 4/12/24)
  + 1 (short H=12) + 4 (cap 3/5/10/nessuno) + 1 (filtro BTC). Varianza sugli SR di
  addestramento dei look della famiglia LONG: 9 griglia + 3 cap + 1 filtro = 13 valori
  [lettura A]. Lettura B (piu' severa): 13 + SR della config promossa stessa = 14 valori.
  OPERATIVO = minimo DSR tra A e B. PASS se DSR(N=18) >= 0,95.

Uso:  .venv/bin/python -u scripts/chiusura_cascate.py
Output: prove/chiusura_cascate_2026-10-15.json + riepilogo a schermo.
"""
from __future__ import annotations

import json
import statistics as st
import sys
from bisect import bisect_right
from datetime import datetime, timezone
from itertools import product
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE / "scripts"))
sys.path.insert(0, str(RADICE / "src"))

import backtest_cascate as bc  # noqa: E402
from money.statistica import sharpe_deflazionato, varianza_da_tentativi  # noqa: E402

CACHE_MORTE = RADICE / "data" / "cache_morte"
OUT_JSON = RADICE / "prove" / "chiusura_cascate_2026-10-15.json"

# ---- soglie/criteri (dichiarati sopra) ----
PROF_N_MIN = 40
PROF_T_MIN = 2.5
FILTRO_2022_MIN = -0.001
FILTRO_TOT_MIN = 0.007
AGG_MEDIA_MIN = 0.006
AGG_T_MIN = 4.0
DSR_MIN = 0.95
N_TENTATIVI = 18

FASCE = ((-0.10, -0.08, "caduta in [-8,-10)%"), (-0.12, -0.10, "caduta in [-10,-12)%"),
         (-0.15, -0.12, "caduta in [-12,-15)%"), (float("-inf"), -0.15, "caduta <= -15%"))


def raccogli_esteso(dati, h, long=True, soglia=bc.SOGLIA_DROP):
    """Come bc.raccogli ma conserva drop3 (profondità della caduta)."""
    casi = []
    ev = bc.eventi_di(dati, soglia)
    for s, barre in dati.items():
        for i in ev[s]:
            if i + h >= len(barre):
                continue
            r = bc.simula(barre, i, h, long=long)
            if r is None:
                continue
            netto, stress, ore, motivo, i_in, dist = r
            drop3 = float(barre[i][4]) / float(barre[i - 3][4]) - 1.0
            casi.append({"sym": s, "ts": int(barre[i_in][0]), "netto": netto, "stress": stress,
                         "motivo": motivo, "dist": dist, "drop3": drop3})
    casi.sort(key=lambda c: c["ts"])
    return casi


def raccogli_morta(barre, h, soglia=bc.SOGLIA_DROP):
    casi = []
    mv = bc.medie_volume(barre)
    for i in bc.eventi(barre, mv, soglia):
        if i + h >= len(barre):
            continue
        r = bc.simula(barre, i, h, long=True)
        if r is None:
            continue
        netto, stress, ore, motivo, i_in, dist = r
        drop3 = float(barre[i][4]) / float(barre[i - 3][4]) - 1.0
        casi.append({"ts": int(barre[i_in][0]), "netto": netto, "motivo": motivo,
                     "dist": dist, "drop3": drop3})
    return casi


def applica_cap(casi, cap, chiave="netto"):
    """Max `cap` ingressi per giorno UTC (giorno del ts d'ingresso), scelti per caduta maggiore."""
    per_giorno: dict[int, list] = {}
    for c in casi:
        per_giorno.setdefault(c["ts"] // 86400000, []).append(c)
    tenuti = []
    per_giorno_scelti = {}
    for g, lista in per_giorno.items():
        lista.sort(key=lambda c: (c["drop3"], c["ts"]))
        per_giorno_scelti[g] = lista[:cap]
        tenuti.extend(lista[:cap])
    tenuti.sort(key=lambda c: c["ts"])
    return tenuti


def sr_train(casi):
    tr = [c["netto"] for c in casi if c["ts"] < bc.CONFINE_TRAIN_MS]
    if len(tr) < 30:
        return None, tr
    m = sum(tr) / len(tr)
    sd = st.stdev(tr)
    return (m / sd if sd else None), tr


def per_anno(casi):
    agg: dict[int, list] = {}
    for c in casi:
        agg.setdefault(c["ts"] // 31536000000 + 1970, []).append(c["netto"])
    return {a: {"n": len(v), "media": sum(v) / len(v),
                "t": (sum(v) / len(v)) / (st.stdev(v) / len(v) ** 0.5) if len(v) > 1 and st.stdev(v) else None}
            for a, v in sorted(agg.items())}


def stat(casi):
    xs = [c["netto"] for c in casi]
    if len(xs) < 2:
        return {"n": len(xs)}
    m = sum(xs) / len(xs)
    sd = st.stdev(xs)
    return {"n": len(xs), "media": m, "t": m / (sd / len(xs) ** 0.5),
            "mediana": st.median(xs), "pos": sum(1 for x in xs if x > 0) / len(xs)}


def main() -> int:
    esito: dict = {"data": "2026-10-15", "test": {}}

    # ---------- dati ----------
    dati, esclusi = {}, []
    for p in sorted(bc.CACHE.glob("bybit_*_1h.json")):
        s = p.name[len("bybit_"):-len("_1h.json")]
        try:
            dati[s] = bc.carica(s)
        except Exception as exc:  # noqa: BLE001
            esclusi.append(f"{s}: {exc}")
    print(f"universo: {len(dati)} simboli | esclusi: {', '.join(esclusi) or 'nessuno'}", flush=True)

    casi12 = raccogli_esteso(dati, 12)
    s12 = stat(casi12)
    print(f"[sanity] H=12 tutti: n={s12['n']} media {s12['media']:+.3%} t {s12['t']:.2f}", flush=True)

    # ---------- TEST 1: fasce di profondità ----------
    print("\n=== TEST 1 — fasce di profondità ===", flush=True)
    t1 = {"fasce": [], "pass": True}
    for (lo, hi, nome) in FASCE:
        gruppo = [c for c in casi12 if lo <= c["drop3"] < hi]
        riga = {"fascia": nome, **stat(gruppo)}
        t1["fasce"].append(riga)
        print(f"  {nome:22s} n={riga['n']:5d} media {riga.get('media', 0):+.3%} "
              f"t {riga.get('t', 0):5.2f}", flush=True)
    fasce = t1["fasce"]
    if any(f["n"] >= PROF_N_MIN and f.get("media", 0) <= 0 for f in fasce):
        t1["pass"] = False
    if fasce[3].get("t", 0) < PROF_T_MIN:
        t1["pass"] = False
    if fasce[3].get("media", 0) < fasce[0].get("media", 0):
        t1["pass"] = False
    t1["criteri"] = f"ogni fascia n>={PROF_N_MIN} media>0; profonda t>={PROF_T_MIN}; profonda>=superficiale"
    t1["pass"] = bool(t1["pass"])
    print(f"  -> {'PASS' if t1['pass'] else 'FAIL'}")
    esito["test"]["1_fasce"] = t1

    # ---------- cap e filtro ----------
    cap5 = applica_cap(casi12, 5)
    print(f"[cap5] n={len(cap5)} media {stat(cap5)['media']:+.3%} t {stat(cap5)['t']:.2f}", flush=True)

    btc = json.loads((bc.CACHE / "bybit_BTC-USDT_1d.json").read_text())["barre"]
    btc_ts = [int(b[0]) for b in btc]
    btc_cl = [float(b[4]) for b in btc]

    def regime_ok(ts_ingresso: int):
        idx = bisect_right(btc_ts, ts_ingresso - 86400000) - 1
        if idx < 200:
            return True
        sma = sum(btc_cl[idx - 199:idx + 1]) / 200.0
        return btc_cl[idx] > sma

    filtrati = [c for c in casi12 if regime_ok(c["ts"])]
    cap5_f = applica_cap(filtrati, 5)
    sf = stat(filtrati)
    print(f"[filtro BTC>SMA200] n={sf['n']} media {sf['media']:+.3%} t {sf['t']:.2f}", flush=True)

    # ---------- TEST 2: regime ----------
    print("\n=== TEST 2 — regime (filtro BTC>SMA200) ===", flush=True)
    a_f = per_anno(filtrati)
    y22 = a_f.get(2022, {}).get("media", 0.0)
    oos_f = [c["netto"] for c in filtrati if c["ts"] >= bc.CONFINE_TRAIN_MS]
    oos_m = sum(oos_f) / len(oos_f) if oos_f else 0.0
    t2 = {"2022_filtrato": y22, "totale_filtrato": sf["media"], "oos_filtrato": oos_m,
          "criteri": f"(a) 2022 >= {FILTRO_2022_MIN:.1%}; (b) totale >= {FILTRO_TOT_MIN:.1%}; (c) OOS > 0"}
    t2["pass"] = (y22 >= FILTRO_2022_MIN) and (sf["media"] >= FILTRO_TOT_MIN) and (oos_m > 0)
    for a, r in a_f.items():
        print(f"  {a}: n={r['n']:4d} media {r['media']:+.3%}" + (f" t {r['t']:5.2f}" if r["t"] else ""))
    print(f"  OOS filtrato: {oos_m:+.3%} -> {'PASS' if t2['pass'] else 'FAIL'}")
    esito["test"]["2_regime"] = t2

    # ---------- TEST 3: survivorship ----------
    print("\n=== TEST 3 — survivorship (monete morte) ===", flush=True)
    morti_casi, morti_per_sym = [], {}
    for p in sorted(CACHE_MORTE.glob("*_1h.json")):
        sym = p.name[:-len("_1h.json")]
        try:
            barre = json.loads(p.read_text())["barre"]
            if len(barre) < 500:
                print(f"  {sym}: {len(barre)} barre — troppe poche, saltata")
                continue
            cc = raccogli_morta(barre, 12)
            for c in cc:
                c["sym"] = sym
            morti_casi.extend(cc)
            morti_per_sym[sym] = {**stat(cc), "per_anno": per_anno(cc)}
            r = morti_per_sym[sym]
            print(f"  {sym}: n={r.get('n', 0)} media {r.get('media', 0):+.3%} "
                  f"t {r.get('t', 0) if r.get('t') else 0:.2f}")
        except Exception as exc:  # noqa: BLE001
            print(f"  {sym}: ERRORE {exc}")
    morti_casi.sort(key=lambda c: c["ts"])
    aggregato = sorted(casi12 + morti_casi, key=lambda c: c["ts"])
    sa = stat(aggregato)
    t3 = {"morti_per_simbolo": morti_per_sym, "aggregato": sa,
          "criteri": f"(a) media aggregato >= {AGG_MEDIA_MIN:.1%}; (b) t >= {AGG_T_MIN}"}
    t3["pass"] = (sa.get("media", 0) >= AGG_MEDIA_MIN) and (sa.get("t", 0) >= AGG_T_MIN)
    print(f"  aggregato (superstiti+morte): n={sa['n']} media {sa['media']:+.3%} t {sa['t']:.2f}"
          f" -> {'PASS' if t3['pass'] else 'FAIL'}")
    esito["test"]["3_survivorship"] = t3

    # ---------- TEST 4: DSR, convenzione congelata ----------
    print("\n=== TEST 4 — DSR (N=18 congelato) ===", flush=True)
    sr_grid = []
    for soglia, h in product((-0.05, -0.06, -0.08), (4, 12, 24)):
        casi = bc.raccogli(dati, h, long=True, soglia=soglia)
        sr, tr = sr_train(casi)
        if sr is not None:
            sr_grid.append(sr)
    sr_caps = []
    for cap in (3, 5, 10):
        sr, _ = sr_train(applica_cap(casi12, cap))
        if sr is not None:
            sr_caps.append(sr)
    sr_filtro, _ = sr_train(filtrati)
    sr_long = sr_grid + sr_caps + ([sr_filtro] if sr_filtro is not None else [])
    var = varianza_da_tentativi(sr_long)
    print(f"  SR addestramento: griglia {len(sr_grid)} + cap {len(sr_caps)} + filtro "
          f"{1 if sr_filtro else 0} = {len(sr_long)} valori; var={var:.6f}")

    sr_promossa, tr_promossa = sr_train(cap5_f if t2["pass"] else cap5)
    if sr_promossa is None:
        t4 = {"criteri": f"DSR(N={N_TENTATIVI}) >= {DSR_MIN}", "pass": False,
              "nota": "SR train non calcolabile (n_train troppo piccolo)"}
        print("  -> FAIL (n_train < 30)")
    else:
        n_tr = len(tr_promossa)
        var_b = (varianza_da_tentativi(sr_long + [sr_promossa])  # lettura B (piu' severa)
                 if t2["pass"] else var)  # se promossa = cap5, e' gia' nei 13
        d18 = sharpe_deflazionato(sr_promossa, n_tr, N_TENTATIVI, var)
        d18b = sharpe_deflazionato(sr_promossa, n_tr, N_TENTATIVI, var_b)
        d13 = sharpe_deflazionato(sr_promossa, n_tr, 13, var)
        d9 = sharpe_deflazionato(sr_promossa, n_tr, 9, var)
        dsr_op = min(d18["dsr"], d18b["dsr"])
        print(f"  config promossa: SR train {sr_promossa:.3f} su n_train {n_tr}")
        print(f"  DSR: A N=18 {d18['dsr']:.4f} | B N=18 {d18b['dsr']:.4f} [operativo: {dsr_op:.4f}]"
              f" | sens. N=13 {d13['dsr']:.4f} | N=9 {d9['dsr']:.4f}")
        t4 = {"sr_promossa": sr_promossa, "n_train": n_tr, "var_a": var, "var_b": var_b,
              "dsr_n18_a": d18["dsr"], "dsr_n18_b": d18b["dsr"], "dsr_operativo": dsr_op,
              "dsr_n13": d13["dsr"], "dsr_n9": d9["dsr"],
              "criteri": f"min(DSR A,B; N={N_TENTATIVI}) >= {DSR_MIN}"}
        t4["pass"] = dsr_op >= DSR_MIN
        print(f"  -> {'PASS' if t4['pass'] else 'FAIL'}")
    esito["test"]["4_dsr"] = t4

    # ---------- verdetto ----------
    promuovibile = all(v.get("pass") for v in esito["test"].values())
    esito["promuovibile"] = promuovibile
    esito["config_promossa"] = "cascate long H=12, cap 5/giorno" + (" + filtro BTC>SMA200" if t2["pass"] else "")
    print(f"\n================ VERDETTO CHIUSURA E2: "
          f"{'PROMUOVIBILE ✔' if promuovibile else 'NON PROMUOVIBILE ✘'} ================")
    for i in sorted(esito["test"]):
        print(f"  {i}: {'PASS' if esito['test'][i].get('pass') else 'FAIL'}")

    # statistiche finali della config promossa
    prom = cap5_f if t2["pass"] else cap5
    esito["config_promossa_stats"] = {"totale": stat(prom), "per_anno": per_anno(prom)}
    OUT_JSON.write_text(json.dumps(esito, indent=1, default=str))
    print(f"\nraw json: {OUT_JSON.relative_to(RADICE)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
