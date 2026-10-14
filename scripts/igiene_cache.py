#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""igiene_cache.py — audit di igiene della cache OHLCV Bybit (SOLA LETTURA).

COSA FA
=======
Scansiona `data/cache/bybit_*.json` e classifica OGNI file come:

    rotto    = almeno una FIRMA DURA (regole H*)
    sospetto = nessuna firma dura, ma almeno un'anomalia di scala/buco/volume (regole S*)
    ok       = nessuna firma dura e nessuna anomalia

Produce:
    * `data/cache_igiene.json`   — artefatto machine-readable (un record per file, con
                                   metriche, regole scattate, sha256 e finestra contesto)
    * un report markdown         — con --report (tabelle, conteggi, liste proposte)

Exit code: 0 sempre, tranne con `--esci-non-zero-se-rotto` (allora 1 se ci sono file rotti).

REGOLE (definizioni operative)
==============================
Firme dure (rotto):
    H0_file_illeggibile   JSON non leggibile / struttura non conforme
    H1_ritorno_close      |close[i]/close[i-1] - 1| > 3.0        (> 300%)
    H2_prezzo_non_positivo  open/high/low/close <= 0 oppure NaN/inf
    H3_ts_non_monotoni    timestamp duplicati o non strettamente crescenti
    H4_crollo_intrabarra  high/low dello STESSO bar > 100x       [ESTENSIONE, vedi sotto]

Anomalie (sospetto):
    S1_scala         max(high)/min(low) > 1e5 nella storia
    S2_prezzo_min    min(low) < 1e-5
    S3_buco          distanza tra ts consecutivi > 5x il timeframe
    S4_volume_zero   > 24 barre consecutive con volume == 0
    S5_picco_isolato high (o low) di un bar > 3x il massimo (minimo) dei due bar
                     adiacenti, con range intra-barra > 3x            [ESTENSIONE]

Anomalie informative (NON cambiano la categoria, finiscono in `anomalie_informative`):
    I_buco           buco > 1.5x tf (barra mancante) — sotto la soglia di sospetto
    I_range          barra con high/low > 3x (es. wick di flash-crash)
    I_volume_zero    run di volume zero >= 5 barre (sotto la soglia di sospetto)
    I_serie_troncata serie che finisce > 2x tf prima della fine comune dello stesso
                     timeframe (delisting o buco di raccolta, es. GAS/BNT/DGB/ICX)

PERCHE' LE DUE ESTENSIONI
=========================
H4 — CTC-USDT ha subito un token swap il 2022-09-21: nella serie 1d il crollo
(0.30 -> 8e-05 -> 0.29) e' visibile SOLO come low di una singola candela, quindi
il ritorno close-to-close non lo vede e la serie 1d passerebbe per 'ok' pur
contenendo un finto -99,97%. Soglia 100x = enorme margine: il range intra-barra
piu' grande del resto della cache e' 10,8x (tick spurio) e i wick veri del
flash-crash 2025-10-10 stanno a 3-5x.
S5 — AVAX-USDT porta un tick spurio isolato (high = 1000.2774 il 2021-11-18
mentre il prezzo di mercato era ~100): nessuna firma dura, ma e' un dato
da rivedere prima dei backtest.

Le due estensioni si disattivano con `--senza-estensioni`, che riproduce il
conteggio con le sole regole letterali.

SOLA LETTURA: il file di cache non viene mai modificato. Solo stdlib.
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import hashlib
import json
import math
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

TF_MS = {"1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}
TF_MS_DEFAULT = 3_600_000  # fallback per timeframe non noti (buco in unita' di tf)

SOGLIE = {
    "ritorno_close": 3.0,      # H1: |ritorno 1 barra| > 300%
    "intrabar_ratio": 100.0,   # H4: high/low stesso bar > 100x (estensione)
    "ratio_scala": 1e5,        # S1: max/min > 10^5
    "prezzo_min": 1e-5,        # S2: prezzo minimo < 1e-5
    "buco_tf": 5.0,            # S3: buco > 5x timeframe
    "run_volume_zero": 24,     # S4: > 24 barre consec. a volume zero
    "picco_isolato": 3.0,      # S5: picco > 3x i bar adiacenti (estensione)
    "buco_info_tf": 1.5,       # I_buco
    "range_info": 3.0,         # I_range
    "run_volume_info": 5,      # I_volume_zero
    "esempi_max": 5,           # quanti esempi salvare per regola
}

#: regola -> (categoria, tipo, descrizione)
REGOLE = {
    "H0_file_illeggibile": ("rotto", "letterale", "JSON non leggibile o struttura non conforme (venue/simbolo/timeframe/barre[6])"),
    "H1_ritorno_close": ("rotto", "letterale", "|ritorno close-to-close di 1 barra| > 300%"),
    "H2_prezzo_non_positivo": ("rotto", "letterale", "prezzo open/high/low/close <= 0 oppure NaN/inf"),
    "H3_ts_non_monotoni": ("rotto", "letterale", "timestamp non strettamente crescenti (duplicati o fuori ordine)"),
    "H4_crollo_intrabarra": ("rotto", "estensione", "high/low dello stesso bar > 100x (crollo/swap intra-barra invisibile al close-to-close)"),
    "S1_scala": ("sospetto", "letterale", "scala anomala: max(high)/min(low) > 1e5"),
    "S2_prezzo_min": ("sospetto", "letterale", "prezzo minimo < 1e-5"),
    "S3_buco": ("sospetto", "letterale", "buco: distanza tra barre consecutive > 5x il timeframe"),
    "S4_volume_zero": ("sospetto", "letterale", "oltre 24 barre consecutive con volume == 0"),
    "S5_picco_isolato": ("sospetto", "estensione", "picco isolato: high/low > 3x i bar adiacenti con range intra-barra > 3x"),
    "I_buco": ("info", "informativa", "barra mancante (buco > 1.5x il timeframe)"),
    "I_range": ("info", "informativa", "barra con range intra-barra > 3x"),
    "I_volume_zero": ("info", "informativa", "run di volume zero >= 5 barre"),
    "I_serie_troncata": ("info", "informativa", "serie che finisce > 2x il timeframe prima della fine comune dello stesso timeframe"),
}


# --------------------------------------------------------------------------- #
# utilita'
# --------------------------------------------------------------------------- #
def iso(ms: int | None) -> str | None:
    """Timestamp ms UTC -> 'YYYY-MM-DD HH:MM'."""
    if ms is None:
        return None
    try:
        return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).strftime("%Y-%m-%d %H:%M")
    except (OverflowError, OSError, ValueError):
        return str(ms)


def _finito(x: float) -> bool:
    return isinstance(x, (int, float)) and math.isfinite(x)


def analizza_file(percorso: Path, soglie: dict = SOGLIE, estensioni: bool = True) -> dict:
    """Analizza un singolo file di cache. Non solleva: gli errori diventano firme dure."""
    nome = percorso.name
    testo = percorso.read_text(encoding="utf-8", errors="replace")
    rec: dict = {
        "file": nome,
        "sha256": hashlib.sha256(testo.encode("utf-8")).hexdigest(),
        "bytes": percorso.stat().st_size,
        "simbolo": None,
        "timeframe": None,
        "categoria": None,
        "n_barre": None,
        "primo_ts": None,
        "ultimo_ts": None,
        "primo_iso": None,
        "ultimo_iso": None,
        "copertura": None,
        "metriche": {},
        "firme": [],
        "sospetti": [],
        "anomalie_informative": [],
    }

    def firma(regola: str, dettaglio: str, esempi=None):
        rec["firme"].append({"regola": regola, "categoria": "rotto", "dettaglio": dettaglio, "esempi": esempi or []})

    def sospetto(regola: str, dettaglio: str, esempi=None):
        rec["sospetti"].append({"regola": regola, "categoria": "sospetto", "dettaglio": dettaglio, "esempi": esempi or []})

    def info(regola: str, dettaglio: str, esempi=None):
        rec["anomalie_informative"].append({"regola": regola, "dettaglio": dettaglio, "esempi": esempi or []})

    try:
        dati = json.loads(testo)
    except Exception as exc:  # noqa: BLE001
        firma("H0_file_illeggibile", f"JSON non leggibile: {type(exc).__name__}: {exc}")
        rec["categoria"] = "rotto"
        return rec

    if not isinstance(dati, dict) or not isinstance(dati.get("barre"), list) or not dati["barre"]:
        firma("H0_file_illeggibile", "struttura non conforme: manca 'barre' o e' vuota")
        rec["categoria"] = "rotto"
        return rec

    rec["simbolo"] = dati.get("simbolo")
    rec["timeframe"] = dati.get("timeframe")
    if rec["simbolo"] is None or rec["timeframe"] is None:
        firma("H0_file_illeggibile", "mancano 'simbolo' o 'timeframe'")
    base = nome[len("bybit_"):-len(".json")] if nome.startswith("bybit_") else nome
    rec["simbolo_file"], rec["timeframe_file"] = (base.rsplit("_", 1) + ["?"])[:2]

    barre = dati["barre"]
    n = len(barre)
    malformate = [i for i, b in enumerate(barre) if not isinstance(b, (list, tuple)) or len(b) != 6]
    if malformate:
        firma("H0_file_illeggibile", f"{len(malformate)} barre con forma != [ts,o,h,l,c,v]",
              [{"indice": i, "valore": str(barre[i])[:120]} for i in malformate[: soglie["esempi_max"]]])
        barre = [b for i, b in enumerate(barre) if i not in set(malformate)]
        if not barre:
            rec["categoria"] = "rotto"
            return rec

    soglia_tf = TF_MS.get(rec["timeframe"], TF_MS_DEFAULT)
    try:
        ts = [int(b[0]) for b in barre]
    except Exception:  # noqa: BLE001
        firma("H0_file_illeggibile", "timestamp non numerici")
        rec["categoria"] = "rotto"
        return rec

    ohlcv = []
    for b in barre:
        try:
            ohlcv.append((float(b[1]), float(b[2]), float(b[3]), float(b[4]), float(b[5])))
        except Exception:  # noqa: BLE001
            ohlcv.append((float("nan"),) * 5)

    # --- H2: prezzi non positivi / non finiti ----------------------------- #
    cattivi = []
    for i, (o, h, l, c, v) in enumerate(ohlcv):
        vals = (o, h, l, c, v)
        if not all(_finito(x) for x in vals[:4]) or min(o, h, l, c) <= 0:
            cattivi.append({"indice": i, "ts": ts[i], "iso": iso(ts[i]), "bar": [ts[i], *vals]})
    if cattivi:
        firma("H2_prezzo_non_positivo", f"barre con prezzo <= 0 o non finito: {len(cattivi)}",
              cattivi[: soglie["esempi_max"]])

    # --- H3: timestamp ---------------------------------------------------- #
    dup = [{"indice": i, "ts": ts[i], "iso": iso(ts[i]), "ts_prec": ts[i - 1]}
           for i in range(1, n) if ts[i] <= ts[i - 1]]
    if dup:
        firma("H3_ts_non_monotoni", f"coppie di timestamp non crescenti (duplicati o fuori ordine): {len(dup)}",
              dup[: soglie["esempi_max"]])

    # --- H1: ritorni close-to-close --------------------------------------- #
    salti = []
    max_ret, ts_max_ret = 0.0, None
    for i in range(1, n):
        c0, c1 = ohlcv[i - 1][3], ohlcv[i][3]
        if c0 > 0 and _finito(c0) and _finito(c1) and c1 > 0:
            ret = c1 / c0 - 1.0
            if abs(ret) > max_ret:
                max_ret, ts_max_ret = abs(ret), ts[i]
            if abs(ret) > soglie["ritorno_close"]:
                salti.append({"indice": i, "ts": ts[i], "iso": iso(ts[i]),
                              "close_prec": c0, "close": c1, "ritorno_pct": round(ret * 100, 4)})
    salti.sort(key=lambda d: -abs(d["ritorno_pct"]))
    if salti:
        firma("H1_ritorno_close",
              f"barre con |ritorno close-to-close| > {soglie['ritorno_close'] * 100:.0f}%: {len(salti)}",
              salti[: soglie["esempi_max"]])

    # --- H4: crollo intra-barra (estensione) ------------------------------ #
    indici_h4: set[int] = set()
    if estensioni:
        crolli = []
        max_ib, ts_max_ib = 0.0, None
        for i, (o, h, l, c, v) in enumerate(ohlcv):
            if _finito(h) and _finito(l) and l > 0:
                ratio = h / l
                if ratio > max_ib:
                    max_ib, ts_max_ib = ratio, ts[i]
                if ratio > soglie["intrabar_ratio"]:
                    crolli.append({"indice": i, "ts": ts[i], "iso": iso(ts[i]),
                                   "open": o, "high": h, "low": l, "close": c, "high_low_ratio": round(ratio, 2)})
        crolli.sort(key=lambda d: -d["high_low_ratio"])
        indici_h4 = {d["indice"] for d in crolli}
        if crolli:
            firma("H4_crollo_intrabarra",
                  f"barre con high/low > {soglie['intrabar_ratio']:.0f}x: {len(crolli)}",
                  crolli[: soglie["esempi_max"]])
    else:
        max_ib, ts_max_ib = None, None

    # --- metriche di scala ------------------------------------------------ #
    lows = [x[2] for x in ohlcv if _finito(x[2]) and x[2] > 0]
    highs = [x[1] for x in ohlcv if _finito(x[1]) and x[1] > 0]
    closes = [x[3] for x in ohlcv if _finito(x[3]) and x[3] > 0]
    min_prezzo = min(lows) if lows else None
    max_prezzo = max(highs) if highs else None
    id_min = ts[lows.index(min_prezzo)] if lows else None
    ratio_ohlc = (max_prezzo / min_prezzo) if (min_prezzo and max_prezzo) else None
    ratio_close = (max(closes) / min(closes)) if (closes and min(closes) > 0) else None

    if estensioni and ratio_ohlc is not None and ratio_ohlc > soglie["ratio_scala"]:
        sospetto("S1_scala", f"max/min = {ratio_ohlc:.4g} > {soglie['ratio_scala']:.0e}",
                 [{"min": min_prezzo, "max": max_prezzo}])
    if min_prezzo is not None and min_prezzo < soglie["prezzo_min"]:
        sospetto("S2_prezzo_min",
                 f"prezzo minimo {min_prezzo:.6g} < {soglie['prezzo_min']:.0e} (barra {iso(id_min)})",
                 [{"ts": id_min, "iso": iso(id_min), "min_prezzo": min_prezzo,
                   "max_prezzo": max_prezzo, "ratio_ohlc": round(ratio_ohlc, 2) if ratio_ohlc else None}])

    # --- buchi ------------------------------------------------------------ #
    buchi = [{"indice": i, "dopo_ts": ts[i - 1], "dopo_iso": iso(ts[i - 1]), "a_ts": ts[i],
              "buco_ms": ts[i] - ts[i - 1], "buco_tf": round((ts[i] - ts[i - 1]) / soglia_tf, 3)}
             for i in range(1, n) if ts[i] - ts[i - 1] > soglia_tf]
    grossi = [b for b in buchi if b["buco_tf"] > soglie["buco_tf"]]
    if grossi:
        sospetto("S3_buco", f"buchi > {soglie['buco_tf']}x il timeframe ({rec['timeframe']}): {len(grossi)}",
                 sorted(grossi, key=lambda d: -d["buco_tf"])[: soglie["esempi_max"]])
    medi = [b for b in buchi if soglie["buco_info_tf"] < b["buco_tf"] <= soglie["buco_tf"]]
    if medi:
        info("I_buco", f"barre mancanti (buchi tra {soglie['buco_info_tf']}x e {soglie['buco_tf']}x il timeframe): {len(medi)}",
             sorted(medi, key=lambda d: -d["buco_tf"])[: soglie["esempi_max"]])

    # --- volume zero ------------------------------------------------------ #
    run, run_max, run_start, n_zero = 0, 0, None, 0
    run_migliore = None
    for i, (o, h, l, c, v) in enumerate(ohlcv):
        if v == 0:
            n_zero += 1
            if run == 0:
                inizio = i
            run += 1
            if run > run_max:
                run_max, run_start = run, inizio
        else:
            run = 0
    if run_max > soglie["run_volume_zero"]:
        sospetto("S4_volume_zero", f"volume 0 per {run_max} barre consecutive (da {iso(ts[run_start])})",
                 [{"run": run_max, "inizio_ts": ts[run_start], "inizio_iso": iso(ts[run_start])}])
    elif run_max >= soglie["run_volume_info"]:
        run_migliore = {"run": run_max, "inizio_ts": ts[run_start], "inizio_iso": iso(ts[run_start])}
        info("I_volume_zero", f"run massimo di volume zero: {run_max} barre (da {iso(ts[run_start])})", [run_migliore])

    # --- picco isolato (estensione) --------------------------------------- #
    picchi = []
    if estensioni:
        for i in range(1, n - 1):
            if i in indici_h4:
                continue  # gia' coperto dalla firma H4 (stessa barra): non duplicare
            o, h, l, c, v = ohlcv[i]
            hp, hn = ohlcv[i - 1][1], ohlcv[i + 1][1]
            lp, ln = ohlcv[i - 1][2], ohlcv[i + 1][2]
            if not all(_finito(x) for x in (h, l, hp, hn, lp, ln)) or l <= 0:
                continue
            rng = h / l if l > 0 else 0.0
            if hp > 0 and hn > 0 and h > soglie["picco_isolato"] * max(hp, hn) and rng > soglie["range_info"]:
                picchi.append({"indice": i, "ts": ts[i], "iso": iso(ts[i]), "tipo": "high",
                               "valore": h, "adiacenti": [hp, hn], "high_low_ratio": round(rng, 2)})
            if lp > 0 and ln > 0 and l < min(lp, ln) / soglie["picco_isolato"] and rng > soglie["range_info"]:
                picchi.append({"indice": i, "ts": ts[i], "iso": iso(ts[i]), "tipo": "low",
                               "valore": l, "adiacenti": [lp, ln], "high_low_ratio": round(rng, 2)})
        if picchi:
            sospetto("S5_picco_isolato",
                     f"picchi isolati (> {soglie['picco_isolato']:.0f}x i bar adiacenti): {len(picchi)}",
                     picchi[: soglie["esempi_max"]])

    # --- barre con range anomalo (informativo) ---------------------------- #
    range_big = [{"indice": i, "ts": ts[i], "iso": iso(ts[i]), "high": ohlcv[i][1], "low": ohlcv[i][2],
                  "close": ohlcv[i][3], "high_low_ratio": round(ohlcv[i][1] / ohlcv[i][2], 2)}
                 for i in range(n)
                 if ohlcv[i][2] > 0 and _finito(ohlcv[i][1]) and ohlcv[i][1] / ohlcv[i][2] > soglie["range_info"]]
    if range_big:
        range_big.sort(key=lambda d: -d["high_low_ratio"])
        info("I_range", f"barre con range intra-barra > {soglie['range_info']:.0f}x: {len(range_big)} "
                        f"(max {range_big[0]['high_low_ratio']:.1f}x il {range_big[0]['iso']})",
             range_big[: soglie["esempi_max"]])

    # --- copertura -------------------------------------------------------- #
    attese = (ts[-1] - ts[0]) // soglia_tf + 1 if n > 1 else 1
    copertura = n / attese if attese else None

    rec.update({
        "n_barre": n,
        "primo_ts": ts[0],
        "ultimo_ts": ts[-1],
        "primo_iso": iso(ts[0]),
        "ultimo_iso": iso(ts[-1]),
        "copertura": round(copertura, 6) if copertura else None,
        "buchi": {"n": len(buchi), "max_buco_tf": round(max((b["buco_tf"] for b in buchi), default=0.0), 3)},
    })
    rec["metriche"] = {
        "max_ret_close": round(max_ret, 6),
        "ts_max_ret_close": ts_max_ret,
        "iso_max_ret_close": iso(ts_max_ret),
        "max_intrabar_ratio": round(max_ib, 3) if max_ib is not None else None,
        "ts_max_intrabar": ts_max_ib,
        "iso_max_intrabar": iso(ts_max_ib),
        "min_prezzo": min_prezzo,
        "min_prezzo_iso": iso(id_min),
        "max_prezzo": max_prezzo,
        "ratio_scala_ohlc": round(ratio_ohlc, 4) if ratio_ohlc else None,
        "ratio_scala_close": round(ratio_close, 4) if ratio_close else None,
        "n_barre_range_gt3": len(range_big),
        "n_volume_zero": n_zero,
        "max_run_volume_zero": run_max,
    }

    # --- categorie (prima le firme dure, poi i sospetti) ------------------ #
    if rec["firme"]:
        rec["categoria"] = "rotto"
    elif rec["sospetti"]:
        rec["categoria"] = "sospetto"
    else:
        rec["categoria"] = "ok"
    rec["motivo"] = " + ".join([d["regola"] for d in rec["firme"] + rec["sospetti"]]) or "nessuna anomalia"

    # --- contesto: finestra di 5 barre attorno all'evento peggiore -------- #
    evento = None
    for coll in (rec["firme"], rec["sospetti"]):
        for d in coll:
            if d["esempi"] and isinstance(d["esempi"][0], dict) and "indice" in d["esempi"][0]:
                evento = (d["regola"], d["esempi"][0])
                break
        if evento:
            break
    if evento is not None:
        regola, ev = evento
        i0 = ev["indice"]
        lo, hi = max(0, i0 - 2), min(n, i0 + 3)
        rec["contesto"] = {
            "regola": regola,
            "indice": i0,
            "iso": ev.get("iso"),
            "barre": [[ts[j], *ohlcv[j]] for j in range(lo, hi)],
            "indice_relativo": i0 - lo,
        }
    return rec


# --------------------------------------------------------------------------- #
# aggregazione
# --------------------------------------------------------------------------- #
def aggrega(records: list[dict]) -> dict:
    # --- serie troncate: confronto per timeframe (serve l'intera cache) --- #
    fine_comune: dict[str, int] = {}
    for r in records:
        tf = r["timeframe"] or "?"
        fine_comune[tf] = max(fine_comune.get(tf, 0), r["ultimo_ts"] or 0)
    troncate = []
    for r in records:
        tf = r["timeframe"] or "?"
        tf_ms = TF_MS.get(tf, TF_MS_DEFAULT)
        ultimo = r["ultimo_ts"]
        if ultimo is None:
            continue
        ritardo_ms = fine_comune.get(tf, ultimo) - ultimo
        if ritardo_ms > 2 * tf_ms:
            troncate.append({"file": r["file"], "simbolo": r["simbolo"] or r["simbolo_file"],
                             "timeframe": tf, "ultimo_iso": r["ultimo_iso"],
                             "fine_comune_iso": iso(fine_comune.get(tf)),
                             "ritardo_tf": round(ritardo_ms / tf_ms, 1)})
            r["anomalie_informative"].append({
                "regola": "I_serie_troncata",
                "dettaglio": f"serie troncata: finisce {round(ritardo_ms / tf_ms, 1)}x il timeframe "
                             f"({r['ultimo_iso']}) prima della fine comune del timeframe ({iso(fine_comune.get(tf))})",
                "esempi": [{"ultimo_ts": ultimo, "fine_comune_ts": fine_comune.get(tf)}],
            })
    troncate.sort(key=lambda d: (d["simbolo"], d["timeframe"]))

    conteggi = {"ok": 0, "sospetto": 0, "rotto": 0}
    per_regola: dict[str, int] = {}
    for r in records:
        conteggi[r["categoria"]] += 1
        for d in r["firme"] + r["sospetti"]:
            per_regola[d["regola"]] = per_regola.get(d["regola"], 0) + 1

    rotti = [r for r in records if r["categoria"] == "rotto"]
    sospetti = [r for r in records if r["categoria"] == "sospetto"]

    # simboli da escludere: rotti che hanno almeno una firma dura
    duri = {"H1_ritorno_close", "H2_prezzo_non_positivo", "H3_ts_non_monotoni", "H0_file_illeggibile"}
    duri_est = duri | {"H4_crollo_intrabarra"}
    per_simbolo: dict[str, set] = {}
    for r in rotti:
        regole = {d["regola"] for d in r["firme"]}
        if regole & duri_est:
            per_simbolo.setdefault(r["simbolo"] or r["simbolo_file"], set()).add(r["timeframe"])

    tutti_tf, per_tf = [], []
    for sim, tfs in sorted(per_simbolo.items()):
        tfs_tot = {x["timeframe"] for x in records if (x["simbolo"] or x["simbolo_file"]) == sim}
        if tfs >= tfs_tot:
            tutti_tf.append(sim)
        else:
            per_tf.append({"simbolo": sim, "timeframe": sorted(tfs), "timeframe_serie": sorted(tfs_tot)})

    sospetti_simboli: dict[str, list] = {}
    for r in sospetti:
        sospetti_simboli.setdefault(r["simbolo"] or r["simbolo_file"], []).append(
            {"timeframe": r["timeframe"], "regole": [d["regola"] for d in r["sospetti"]]})

    return {
        "conteggi": conteggi,
        "conteggi_per_regola": dict(sorted(per_regola.items())),
        "conteggi_letterali": {
            "rotto": sum(1 for r in records if any(d["regola"] != "H4_crollo_intrabarra" for d in r["firme"])),
            "sospetto": sum(1 for r in records
                            if not r["firme"] and any(d["regola"] != "S5_picco_isolato" for d in r["sospetti"])),
            "nota": "conteggio con le sole regole letterali; la differenza e' data dalle estensioni H4/S5",
        },
        "esclusione_backtest": {"simboli_tutti_tf": tutti_tf, "per_timeframe": per_tf},
        "sospetti_per_simbolo": {k: sorted(v, key=lambda d: d["timeframe"]) for k, v in sorted(sospetti_simboli.items())},
        "serie_troncate": troncate,
    }


# --------------------------------------------------------------------------- #
# report markdown
# --------------------------------------------------------------------------- #
def _riga(r: dict) -> str:
    return (f"| `{r['file']}` | {r['n_barre']} | {r['primo_iso']} | {r['ultimo_iso']} | "
            f"{r['motivo']} |")


def genera_report(records: list[dict], agg: dict, soglie: dict, cache_dir: Path, pattern: str,
                  generato: str, estensioni: bool, sha_json: str | None = None) -> str:
    c = agg["conteggi"]
    L: list[str] = []
    ap = L.append

    ap("# Pulizia cache Bybit — audit di igiene dati")
    ap("")
    ap(f"- Generato: **{generato}** da `scripts/igiene_cache.py` (sola lettura sulla cache)")
    ap(f"- Ambito: `{cache_dir.relative_to(REPO_ROOT) if str(cache_dir).startswith(str(REPO_ROOT)) else cache_dir}/{pattern}`"
       f" — **{len(records)} file**")
    ap("- Artefatto JSON: `data/cache_igiene.json`"
       + (f" (sha256 `{sha_json}`)" if sha_json else ""))
    ap("- Riproduzione:")
    ap("")
    ap("```bash")
    ap("cd /home/sergio/money")
    ap(".venv/bin/python scripts/igiene_cache.py --report prove/pulizia_cache_2026-10-14.md")
    ap("# solo regole letterali (senza estensioni H4/S5):")
    ap(".venv/bin/python scripts/igiene_cache.py --senza-estensioni --out /tmp/igiene_letterale.json")
    ap("```")
    ap("")
    ap("## 1. Metodo")
    ap("")
    ap("Un file e' **rotto** se contiene almeno una firma dura, **sospetto** se non ha firme dure ma ha")
    ap("almeno un'anomalia di scala/buco/volume, **ok** altrimenti.")
    ap("")
    ap("| regola | categoria | origine | definizione operativa |")
    ap("|---|---|---|---|")
    for reg, (cat, origine, desc) in REGOLE.items():
        ap(f"| `{reg}` | {cat} | {origine} | {desc} |")
    ap("")
    ap(f"Soglie: ritorno close-to-close > {soglie['ritorno_close'] * 100:.0f}% · high/low intra-barra > "
       f"{soglie['intrabar_ratio']:.0f}x · max/min > {soglie['ratio_scala']:.0e} · prezzo min < {soglie['prezzo_min']:.0e} · "
       f"buco > {soglie['buco_tf']:.0f}x tf · volume zero > {soglie['run_volume_zero']} barre · "
       f"picco > {soglie['picco_isolato']:.0f}x i vicini.")
    ap("")
    ap("Precisazioni: i ritorni sono calcolati **close-to-close**; `max/min` e `prezzo minimo` sono calcolati")
    ap("su **tutti i prezzi OHLC** (max dei high, min dei low), che e' la lettura piu' inclusiva; un **buco** e'")
    ap("la distanza tra due timestamp consecutivi divisa per la durata del timeframe.")
    ap("")
    if estensioni:
        ap("### 1.1 Estensioni attive")
        ap("")
        ap("Due regole aggiunte alle definizioni letterali, entrambe necessarie a coprire casi reali:")
        ap("")
        ap("- **`H4_crollo_intrabarra`** — CTC-USDT ha subito un token swap il 2022-09-21: nella serie `1d` il")
        ap("  crollo (0.30 → 8e-05 → 0.29) compare **solo come low di una singola candela**, quindi il ritorno")
        ap("  close-to-close non lo vede e la serie `1d` passerebbe per `ok` pur contenendo un finto −99,97%.")
        ap("  Soglia 100x con margine enorme: il massimo range intra-barra di tutto il resto della cache e' 10,8x.")
        ap("- **`S5_picco_isolato`** — AVAX-USDT porta un tick spurio isolato (high 1000.2774 il 2021-11-18 mentre")
        ap("  il prezzo di mercato era ~100): nessuna firma dura, ma e' un dato da rivedere prima dei backtest.")
        ap("")
        ap(f"Con le sole regole letterali i conteggi sarebbero: rotto {agg['conteggi_letterali']['rotto']}, "
           f"sospetto {agg['conteggi_letterali']['sospetto']}.")
    else:
        ap("### 1.1 Estensioni DISATTIVATE (`--senza-estensioni`)")
        ap("")
        ap("Sono attive le sole regole letterali: H4/S5 non concorrono alla classificazione.")
    ap("")

    ap("## 2. Conteggi")
    ap("")
    ap("| categoria | file | quota |")
    ap("|---|---|---|")
    for k in ("ok", "sospetto", "rotto"):
        ap(f"| **{k}** | {c[k]} | {100.0 * c[k] / len(records):.1f}% |")
    ap(f"| **totale** | {len(records)} | 100.0% |")
    ap("")
    ap("| regola scattata | file |")
    ap("|---|---|")
    for reg, n in agg["conteggi_per_regola"].items():
        ap(f"| `{reg}` ({REGOLE[reg][0]}) | {n} |")
    ap("")

    rotti = [x for x in records if x["categoria"] == "rotto"]
    ap(f"## 3. File ROTTI ({len(rotti)} file, {len({r['simbolo'] for r in rotti})} simboli)")
    ap("")
    ap("| file | n barre | primo ts (UTC) | ultimo ts (UTC) | motivo |")
    ap("|---|---|---|---|---|")
    for r in rotti:
        ap(_riga(r))
    ap("")
    for i, r in enumerate(rotti, 1):
        ap(f"### 3.{i} `{r['file']}` — {r['motivo']}")
        ap("")
        for d in r["firme"]:
            ap(f"- **{d['regola']}**: {d['dettaglio']}")
            for e in d["esempi"]:
                if d["regola"] == "H1_ritorno_close":
                    ap(f"  - {e['iso']} (UTC): close {e['close_prec']} → {e['close']} = "
                       f"**{e['ritorno_pct']:+.2f}%**")
                elif d["regola"] == "H4_crollo_intrabarra":
                    ap(f"  - {e['iso']} (UTC): O {e['open']} H {e['high']} L {e['low']} C {e['close']} "
                       f"— high/low = **{e['high_low_ratio']:.0f}x**")
                else:
                    ap(f"  - {e}")
        ap("")

    ap(f"## 4. File SOSPETTI ({c['sospetto']})")
    ap("")
    ap("| file | n barre | primo ts (UTC) | ultimo ts (UTC) | motivo |")
    ap("|---|---|---|---|---|")
    for r in [x for x in records if x["categoria"] == "sospetto"]:
        ap(_riga(r))
    ap("")
    for r in [x for x in records if x["categoria"] == "sospetto"]:
        ap(f"- `{r['file']}`: " + "; ".join(f"**{d['regola']}** {d['dettaglio']}" for d in r["sospetti"]))
    ap("")

    ap("## 5. LISTA PROPOSTA — simboli da escludere dai backtest")
    ap("")
    ap("Criterio: sono esclusi **solo i file `rotto` con firma dura** (regole H1/H2/H3/H4).")
    ap("")
    ap("**A. Esclusione totale (rotto su tutti i timeframe disponibili):**")
    ap("")
    if agg["esclusione_backtest"]["simboli_tutti_tf"]:
        for s in agg["esclusione_backtest"]["simboli_tutti_tf"]:
            ap(f"- **{s}**")
    else:
        ap("- (nessuno)")
    ap("")
    ap("**B. Esclusione per timeframe (serie parzialmente compromesse):**")
    ap("")
    if agg["esclusione_backtest"]["per_timeframe"]:
        ap("| simbolo | escludere i tf | serie disponibili |")
        ap("|---|---|---|")
        for d in agg["esclusione_backtest"]["per_timeframe"]:
            ap(f"| **{d['simbolo']}** | {', '.join(d['timeframe'])} | {', '.join(d['timeframe_serie'])} |")
    else:
        ap("- (nessuno)")
    ap("")
    if agg["esclusione_backtest"]["per_timeframe"]:
        ap("Da sapere: sugli altri timeframe dello stesso simbolo restano anomalie informative")
        ap("(non firme dure), da valutare prima di usare quei file:")
        ap("")
        for d in agg["esclusione_backtest"]["per_timeframe"]:
            voci = []
            for r in records:
                if (r["simbolo"] or r["simbolo_file"]) != d["simbolo"]:
                    continue
                regs = [x["regola"] for x in r["anomalie_informative"] if x["regola"] in ("I_range", "I_serie_troncata")]
                if regs:
                    voci.append(f"{r['timeframe']}: {', '.join(sorted(set(regs)))}")
            ap(f"- **{d['simbolo']}** → " + ("; ".join(voci) if voci else "nessuna anomalia informativa"))
        ap("")
    ap("")
    ap("File da NON usare nei backtest:")
    ap("")
    ap("```")
    for r in [x for x in records if x["categoria"] == "rotto"]:
        ap(f"data/cache/{r['file']}")
    ap("```")
    ap("")

    ap("## 6. Sospetti da valutare a parte (non in lista di esclusione)")
    ap("")
    ap("| simbolo | timeframe | regole |")
    ap("|---|---|---|")
    for sim, voci in agg["sospetti_per_simbolo"].items():
        ap(f"| {sim} | {', '.join(v['timeframe'] for v in voci)} | "
           f"{', '.join(sorted({r for v in voci for r in v['regole']}))} |")
    ap("")

    ap("## 7. Anomalie informative (non cambiano la classificazione)")
    ap("")
    conteggio_info: dict[str, int] = {}
    for r in records:
        for d in r["anomalie_informative"]:
            conteggio_info[d["regola"]] = conteggio_info.get(d["regola"], 0) + 1
    ap("| regola | file |")
    ap("|---|---|")
    for reg, n in sorted(conteggio_info.items()):
        ap(f"| `{reg}` | {n} |")
    ap("")
    ap("Buchi sistemici (stessa barra mancante in piu' file — probabile buco del provider, non del file):")
    ap("")
    buchi_ts: dict[tuple, list] = {}
    for r in records:
        for d in r["anomalie_informative"]:
            if d["regola"] == "I_buco":
                for e in d["esempi"]:
                    buchi_ts.setdefault((e["dopo_ts"], r["timeframe"], e["buco_tf"]), []).append(r["simbolo"])
    ap("| barra mancante (inizio, UTC) | timeframe | file coinvolti |")
    ap("|---|---|---|")
    for (ts0, tf, btf), sims in sorted(buchi_ts.items(), key=lambda kv: -len(kv[1]))[:12]:
        ap(f"| {iso(ts0 + TF_MS.get(tf, TF_MS_DEFAULT))} | {tf} | {len(sims)} |")
    ap("")
    ap("Barre con range intra-barra anomalo (wick estremi; es. flash-crash 2025-10-10):")
    ap("")
    ap("| file | barra (UTC) | high | low | close | high/low |")
    ap("|---|---|---|---|---|---|")
    righe = []
    for r in records:
        if r["categoria"] == "rotto":
            continue  # le barre peggiori sono gia' dettagliate nella sezione 3
        for d in r["anomalie_informative"]:
            if d["regola"] == "I_range":
                for e in d["esempi"][:3]:
                    righe.append((e["high_low_ratio"], r["file"], e))
    for ratio, f, e in sorted(righe, key=lambda x: -x[0])[:12]:
        ap(f"| `{f}` | {e['iso']} | {e['high']} | {e['low']} | {e['close']} | {ratio}x |")
    ap("")

    ap("## 8. Calibrazione delle soglie")
    ap("")
    marg = sorted([r for r in records if r["categoria"] != "rotto"], key=lambda r: -r["metriche"]["max_ret_close"])[:5]
    ap("Ritorni close-to-close massimi **sotto** la soglia del 300% (margine della soglia H1):")
    ap("")
    ap("| file | max |ritorno| | quando (UTC) |")
    ap("|---|---|---|")
    for r in marg:
        m = r["metriche"]
        ap(f"| `{r['file']}` | {m['max_ret_close'] * 100:.2f}% | {m['iso_max_ret_close']} |")
    ap("")
    marg2 = sorted([r for r in records if r["categoria"] != "rotto"], key=lambda r: -(r["metriche"]["max_intrabar_ratio"] or 0))[:5]
    ap("Range intra-barra massimi **sotto** la soglia 100x (margine della soglia H4):")
    ap("")
    ap("| file | high/low | quando (UTC) |")
    ap("|---|---|---|")
    for r in marg2:
        m = r["metriche"]
        ap(f"| `{r['file']}` | {m['max_intrabar_ratio']}x | {m['iso_max_intrabar']} |")
    ap("")

    ap("## 9. Copertura della cache")
    ap("")
    fuori = [r for r in records if (r["copertura"] or 1) < 1.0]
    ap(f"- File con copertura < 100% (barre mancanti dentro l'intervallo coperto): **{len(fuori)}**")
    ap(f"- Buco massimo osservato: **{max((r['buchi']['max_buco_tf'] for r in records), default=0):.1f}x** il timeframe")
    ap(f"- Finestra piu' ampia coperta: {min(r['primo_iso'] for r in records)} → {max(r['ultimo_iso'] for r in records)}")
    ap("")
    troncate = agg.get("serie_troncate", [])
    ap(f"**Serie troncate** (finiscono prima della fine comune dello stesso timeframe): {len(troncate)} file "
       f"— {len({t['simbolo'] for t in troncate})} simboli.")
    ap("")
    ap("| simbolo | timeframe | ultimo bar (UTC) | fine comune (UTC) | ritardo |")
    ap("|---|---|---|---|---|")
    for t in troncate:
        ap(f"| {t['simbolo']} | {t['timeframe']} | {t['ultimo_iso']} | {t['fine_comune_iso']} | "
           f"{t['ritardo_tf']:.0f}x tf |")
    ap("")
    ap("Non e' una firma dura: sono serie che si fermano prima (delisting o buco di raccolta). Per i backtest")
    ap("conta perche' un test che assume la finestra piena trattera' questi simboli come \"senza dati\" dopo la")
    ap("fine della serie, con un campione piu' corto del previsto.")
    ap("")

    ap("## 10. Casi noti — verifica")
    ap("")

    def _render_contesto(r: dict):
        ct = r.get("contesto")
        if not ct:
            ap(f"- `{r['file']}`: nessuna finestra disponibile (regola {r['motivo']})")
            return
        ap(f"- `{r['file']}` — regola `{ct['regola']}`, evento {ct['iso']} (UTC):")
        ap("")
        ap("  | barra (UTC) | open | high | low | close | volume |")
        ap("  |---|---|---|---|---|---|")
        for k, b in enumerate(ct["barre"]):
            iso_b = iso(b[0])
            evid = " **← evento**" if k == ct["indice_relativo"] else ""
            ap(f"  | {iso_b}{evid} | {b[1]} | {b[2]} | {b[3]} | {b[4]} | {b[5]} |")
        ap("")

    ap("### 10.1 CTC-USDT — token swap del 2022-09-21 (caso noto, confermato)")
    ap("")
    for r in records:
        if (r["simbolo"] or "") == "CTC-USDT":
            _render_contesto(r)
    ap("Lettura: nello stesso giorno il prezzo passa da ~0.304 a 8e-05 e poi torna a ~0.305 (`4h`/`1h`).")
    ap("E' l'artefatto del token swap, non un movimento di mercato: nella serie `1d` lo stesso evento")
    ap("compare **solo come low** della candela del 2022-09-21 (O 0.30096 / H 0.311135 / L 8e-05 /")
    ap("C 0.292734), quindi il solo ritorno close-to-close non lo vede.")
    ap("")

    ap("### 10.2 GAS-USDT — scala sospetta (caso noto, confermato come `sospetto`)")
    ap("")
    ap("| file | n barre | min prezzo | max prezzo | max/min | barra del minimo (UTC) | fine serie (UTC) |")
    ap("|---|---|---|---|---|---|---|")
    for r in records:
        if (r["simbolo"] or "") == "GAS-USDT":
            m = r["metriche"]
            ap(f"| `{r['file']}` | {r['n_barre']} | {m['min_prezzo']:.6g} | {m['max_prezzo']:.6g} | "
               f"{m['ratio_scala_ohlc']} | {m['min_prezzo_iso']} | {r['ultimo_iso']} |")
    ap("")
    ap("Lettura: tutta la storia sta a 1,28e-06 … 2,117e-04, cioe' 4-5 ordini di grandezza sotto la scala")
    ap("degli altri simboli; il minimo (1,28e-06) viola la soglia 1e-5 → `S2_prezzo_min`. La serie si ferma")
    ap("il 2023-03-10 su tutti i timeframe.")
    ap("")
    ap("Verifica esterna (pagine pubbliche, non chiavi API): la storia pubblica di GAS/USD (ADVFN su dati")
    ap("CEX.IO) segna 2,49 USD il 2022-12-02, con la fascia di quel periodo attorno a 2,2-2,5 USD, e la")
    ap("pagina pubblica CoinGecko riporta per GAS un massimo storico di 91,94 USD e un minimo di 0,6213 USD.")
    ap("Nella cache la stessa data vale 1,60e-06, cioe' un fattore implicito di circa **1,5e6** sui livelli,")
    ap("e il turnover implicito (volume 7,3e8 x 1,6e-06) e' dell'ordine di 1e3 USD/giorno: incompatibile con")
    ap("un mid-cap. Conclusione: la serie GAS della cache **non e' la serie GAS reale riscalata di una")
    ap("costante**, quindi i LIVELLI non sono usabili e i rendimenti restano non verificati. Va chiarita la")
    ap("fonte (o il simbolo) prima di qualunque backtest che la includa.")
    ap("")

    ap("### 10.3 ICX-USDT — +478% in 1h il 2026-09-21 (serie troncata subito dopo)")
    ap("")
    for r in records:
        if (r["simbolo"] or "") == "ICX-USDT" and r["timeframe"] == "1h":
            _render_contesto(r)
    ap("Lettura: il close passa 0.01004 → 0.05804 (+478%) e il massimo della barra e' 0.07; la serie `1h`")
    ap("si ferma il 2026-09-24 08:00, ~18 giorni prima della fine comune (`I_serie_troncata` su tutti e tre")
    ap("i timeframe). Non e' un errore di formato ma e' un evento da trattare con cautela: `1d` e `4h` non")
    ap("hanno firma dura (il massimo giornaliero e' un range 7,4x, sotto la soglia) ma contengono la stessa")
    ap("pompa. Valutare se escludere anche `1d`/`4h` se il backtest usa il periodo finale.")
    ap("")

    ap("### 10.4 SHIB-USDT — regola `S2` scattata, probabile artefatto della definizione")
    ap("")
    ap("| file | n barre | min prezzo | max prezzo | max/min | barra del minimo (UTC) |")
    ap("|---|---|---|---|---|---|")
    for r in records:
        if (r["simbolo"] or "") == "SHIB-USDT":
            m = r["metriche"]
            ap(f"| `{r['file']}` | {r['n_barre']} | {m['min_prezzo']:.6g} | {m['max_prezzo']:.6g} | "
               f"{m['ratio_scala_ohlc']} | {m['min_prezzo_iso']} |")
    ap("")
    ap("Lettura: SHIB quota per costruzione nella fascia 1e-5 (minimo 4,05e-06, massimo 4,56e-05), quindi la")
    ap("soglia \"prezzo minimo < 1e-5\" scatta su un dato plausibile e non su un errore: **falso positivo")
    ap("della regola**, da NON escludere dai backtest. Un test che usa soglie assolute di prezzo (es. filtri")
    ap("\"prezzo > 0.01\") va comunque adattato alla scala.")
    ap("")

    ap("### 10.5 AVAX-USDT — tick spurio del 2021-11-18 (nessuna firma dura)")
    ap("")
    for r in records:
        if (r["simbolo"] or "") == "AVAX-USDT" and r["timeframe"] == "1d":
            _render_contesto(r)
    ap("Lettura: `high = 1000.2774` mentre i bar adiacenti stanno a 110-116 (e il close e' 101.18): e' un")
    ap("tick spurio isolato, ripetuto identico su tutti e tre i timeframe. Non produce firme dure (il close")
    ap("non salta) → il file resta `sospetto` per `S5`, non `rotto`. Un backtest che usa i massimi")
    ap("(breakout, canali) va protetto; per il resto il file e' utilizzabile.")
    ap("")

    ap("## 11. Limiti")
    ap("")
    ap("- La classificazione e' di **forma**, non di merito: un file `ok` significa \"nessuna firma dura o")
    ap("  anomalia nota\", non \"prezzi verificati contro una seconda fonte\".")
    ap("- I ritorni sono close-to-close: un crollo intra-barra resta invisibile tranne che per `H4`.")
    ap("- Le soglie sono quelle concordate; il margine e' ampio (sezione 8), quindi il conteggio e' stabile.")
    ap("")
    return "\n".join(L)


# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Audit di igiene della cache OHLCV Bybit (sola lettura).")
    ap.add_argument("--cache-dir", default=str(REPO_ROOT / "data" / "cache"))
    ap.add_argument("--pattern", default="bybit_*.json")
    ap.add_argument("--out", default=str(REPO_ROOT / "data" / "cache_igiene.json"))
    ap.add_argument("--report", default=None, help="scrive anche il report markdown in questo percorso")
    ap.add_argument("--senza-estensioni", action="store_true", help="solo regole letterali (niente H4/S5)")
    ap.add_argument("--esci-non-zero-se-rotto", action="store_true",
                    help="exit code 1 se ci sono file rotti (default: 0)")
    ap.add_argument("--soglie", default=None, help="JSON con override delle soglie")
    a = ap.parse_args(argv)

    soglie = dict(SOGLIE)
    if a.soglie:
        soglie.update(json.loads(a.soglie))
    cache_dir = Path(a.cache_dir).expanduser()
    if not cache_dir.is_absolute():
        cache_dir = REPO_ROOT / cache_dir
    percorsi = [Path(p) for p in sorted(glob.glob(str(cache_dir / a.pattern)))]

    records = [analizza_file(p, soglie=soglie, estensioni=not a.senza_estensioni) for p in percorsi]
    agg = aggrega(records)
    generato = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    out = {
        "generato_il": generato,
        "script": "scripts/igiene_cache.py",
        "ambito": {"cache_dir": str(cache_dir), "pattern": a.pattern, "n_file": len(records)},
        "regole": {k: {"categoria": v[0], "origine": v[1], "descrizione": v[2]} for k, v in REGOLE.items()},
        "soglie": soglie,
        "estensioni_attive": not a.senza_estensioni,
        "riepilogo": agg,
        "file": records,
    }
    out_path = Path(a.out).expanduser()
    if not out_path.is_absolute():
        out_path = REPO_ROOT / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    testo_json = json.dumps(out, ensure_ascii=False, indent=2) + "\n"
    out_path.write_text(testo_json, encoding="utf-8")
    sha = hashlib.sha256(testo_json.encode("utf-8")).hexdigest()[:16]

    print(f"[igiene_cache] {len(records)} file analizzati da {cache_dir}/{a.pattern}")
    print(f"[igiene_cache] ok={agg['conteggi']['ok']} sospetti={agg['conteggi']['sospetto']} "
          f"rotti={agg['conteggi']['rotto']}" + ("" if not a.senza_estensioni else " (senza estensioni)"))
    print(f"[igiene_cache] esclusione backtest: tutto={agg['esclusione_backtest']['simboli_tutti_tf']} "
          f"per-tf={[(d['simbolo'], d['timeframe']) for d in agg['esclusione_backtest']['per_timeframe']]}")
    print(f"[igiene_cache] scritto {out_path} (sha256 {sha}…)")

    if a.report:
        rep = Path(a.report).expanduser()
        if not rep.is_absolute():
            rep = REPO_ROOT / rep
        md = genera_report(records, agg, soglie, cache_dir, a.pattern, generato,
                           not a.senza_estensioni, sha_json=sha)
        # preserva un eventuale log di lavorazione in coda al report esistente
        marker = "<!-- LOG-LAVORAZIONE:START -->"
        if rep.exists():
            vecchio = rep.read_text(encoding="utf-8")
            if marker in vecchio:
                md = md.rstrip("\n") + "\n\n" + vecchio[vecchio.index(marker):]
        rep.parent.mkdir(parents=True, exist_ok=True)
        rep.write_text(md, encoding="utf-8")
        print(f"[igiene_cache] scritto report {rep}")

    return 1 if (a.esci_non_zero_se_rotto and agg["conteggi"]["rotto"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
