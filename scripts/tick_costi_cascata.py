#!/usr/bin/env python3
"""Quanto costa DAVVERO comprare al mercato nei minuti DOPO una caduta violenta.

Misura su tick trade Bybit (public.bybit.com/trading, gratuiti) per DOGEUSDT e
SOLUSDT: quanto si paga (slippage/impatto) entrando al mercato subito dopo le ore
piu' violente, e se il costo assunto dal backtest cascate (0,26% round-trip =
0,18% giro misto OKX + 0,08% slippage) regge.

COSA SONO QUESTI DATI (limite dichiarato, non aggirabile)
---------------------------------------------------------
I tick Bybit sono *trade*: timestamp, lato AGGRESSORE (Buy = il compratore ha
attraversato lo spread), size, prezzo. NON esiste l'order book storico in questa
raccolta, quindi **lo spread best bid/ask vero non e' misurabile**. Qui si usano
solo PROXY onesti dai trade:
  * impatto = prezzo medio pagato (VWAP dei trade) su una finestra / primo prezzo
    disponibile dopo il segnale, in bps. E' cio' che si ottiene eseguendo "al
    mercato" spalmando l'ordine sul flusso effettivo.
  * spread efficace (round-trip) = per ogni bucket di 10s con ENTRAMBI i lati,
    (vwap_buy - vwap_sell) / mid. Media sui bucket: e' il pedaggio medio di chi
    attraversa in acquisto rispetto a chi attraversa in vendita nello stesso
    istante (immune alla deriva del prezzo, che invece sporca i confronti tra
    finestre diverse).
  * stimatore di Roll (1984) su prezzi di trade consecutivi:
    spread = 2*sqrt(-cov(dp_t, dp_t-1)); robusto ma assume deriva ~0 nella finestra.
Tutti e tre sono PROXY. Nessuno di essi e' uno spread quotato.

Sola lettura, nessun ordine, nessuna chiave. Riproducibile: passata A aggrega i
minuti (cache), passata B rilegge i tick solo delle finestre selezionate.

Uso:
  .venv/bin/python scripts/tick_costi_cascata.py                    # completo ~29 giorni
  .venv/bin/python scripts/tick_costi_cascata.py --giorni 3         # prova rapida
  .venv/bin/python scripts/tick_costi_cascata.py --out prove/tick_costi_2026-10-14.md
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import glob
import gzip
import json
import math
import os
import random
import statistics as st
import sys
import tempfile
import time
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
TICK_DIR = RADICE / "data" / "tick"

# --- costi assunti dal backtest cascate (scripts/sonda_cascate.py) -----------
FEE_RT_OKX_MISTO = 0.0018      # 0,18% round-trip giro misto OKX (0,08% maker + 0,10% taker)
SLIP_ASSUNTO_LATO = 0.0004     # 0,04% per lato
COSTO_RT_ASSUNTO = FEE_RT_OKX_MISTO + 2 * SLIP_ASSUNTO_LATO   # 0,26%
FEE_RT_BYBIT_PERP_TAKER = 0.0011   # variante: 0,055% x 2 su Bybit perp

ORIZZONTI_S = (5, 15, 30, 60, 120, 300, 600)
BUCKET_SPREAD_S = 10
FINESTRA_S = 600
BPS = 1e4


# --------------------------------------------------------------------------- #
# utilities
# --------------------------------------------------------------------------- #
def leggi_giorno(path: Path):
    """Generatore (ts, lato_aggressore, size, prezzo) da un file tick Bybit."""
    with gzip.open(path, "rt") as fh:
        r = csv.reader(fh)
        next(r)
        for row in r:
            yield float(row[0]), row[2], float(row[3]), float(row[4])


def quantile(xs, q):
    if not xs:
        return float("nan")
    s = sorted(xs)
    if len(s) == 1:
        return s[0]
    pos = q * (len(s) - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def med(xs):
    return st.median(xs) if xs else float("nan")


# --------------------------------------------------------------------------- #
# passata A: aggregazione per minuto (una sola lettura dei ~29 giorni)
# --------------------------------------------------------------------------- #
# campi di ogni minuto: [n, n_buy, n_sell, vol_buy, vol_sell, usd_buy, usd_sell, first, last, min, max]
def aggrega_minuti(sym: str, cache_dir: Path, usa_cache: bool, giorni: int | None):
    cache = cache_dir / f"minuti_{sym}.json"
    if usa_cache and cache.exists() and giorni is None:
        d = json.loads(cache.read_text())
        minuti = {int(k): v for k, v in d["minuti"].items()}
        return minuti, int(d["n_righe"]), int(d["n_file"]), d.get("tick_min")
    files = sorted(glob.glob(str(TICK_DIR / f"{sym}_*.csv.gz")))
    if giorni:
        files = files[-giorni:]
    minuti: dict[int, list] = {}
    n_righe = 0
    tick_min = None
    for f in files:
        prev = None
        for ts, side, size, px in leggi_giorno(Path(f)):
            n_righe += 1
            if prev is not None and px != prev:
                d_ = abs(px - prev)
                if tick_min is None or d_ < tick_min:
                    tick_min = d_
            prev = px
            m = int(ts // 60)
            a = minuti.get(m)
            if a is None:
                a = [0, 0, 0, 0.0, 0.0, 0.0, 0.0, px, px, px, px]
                minuti[m] = a
            a[0] += 1
            if side == "Buy":
                a[1] += 1
                a[3] += size
                a[5] += size * px
            else:
                a[2] += 1
                a[4] += size
                a[6] += size * px
            a[8] = px
            if px < a[9]:
                a[9] = px
            if px > a[10]:
                a[10] = px
    if giorni is None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"minuti": {str(k): v for k, v in minuti.items()},
                                     "n_righe": n_righe, "n_file": len(files),
                                     "tick_min": tick_min}))
    return minuti, n_righe, len(files), tick_min


def ore_da_minuti(minuti: dict[int, list]):
    """hour -> dict con close, usd, n, vol, buy/sell, piu' i minuti ordinati."""
    ore: dict[int, dict] = {}
    for m, a in minuti.items():
        h = m // 60
        o = ore.get(h)
        if o is None:
            o = {"last_min": -1, "close": None, "usd": 0.0, "n": 0, "vol": 0.0,
                 "nbuy": 0, "nsell": 0, "vbuy": 0.0, "vsell": 0.0, "usdbuy": 0.0, "usdsell": 0.0}
            ore[h] = o
        if m > o["last_min"]:
            o["last_min"] = m
            o["close"] = a[8]
        o["n"] += a[0]
        o["nbuy"] += a[1]
        o["nsell"] += a[2]
        o["vol"] += a[3] + a[4]
        o["vbuy"] += a[3]
        o["vsell"] += a[4]
        o["usd"] += a[5] + a[6]
        o["usdbuy"] += a[5]
        o["usdsell"] += a[6]
    return ore


def rendimenti_orari(ore: dict[int, dict], min_ora: int, max_ora: int, warmup_h: int):
    """ritorni close-to-close per ora contigua + volume relativo alle 72h precedenti."""
    fuori = []
    for h in range(min_ora, max_ora + 1):
        o, p = ore.get(h), ore.get(h - 1)
        if not o or not p or o["close"] is None or p["close"] is None:
            continue
        if h < min_ora + warmup_h:
            continue
        vol72 = [ore[h - k]["usd"] for k in range(1, 73) if (h - k) in ore]
        base = st.mean(vol72) if len(vol72) > 12 else float("nan")
        o3 = ore.get(h - 3)
        drop3 = (o["close"] / o3["close"] - 1.0) if (o3 and o3["close"]) else float("nan")
        fuori.append({
            "h": h,
            "t0": (h + 1) * 3600,           # primo secondo dopo la chiusura dell'ora
            "r": o["close"] / p["close"] - 1.0,
            "drop3": drop3,
            "usd_ora": o["usd"],
            "n_ora": o["n"],
            "imb_ora": (o["vbuy"] - o["vsell"]) / (o["vbuy"] + o["vsell"]) if (o["vbuy"] + o["vsell"]) > 0 else float("nan"),
            "vol_x72": (o["usd"] / base) if base and base > 0 else float("nan"),
        })
    return fuori


# --------------------------------------------------------------------------- #
# passata B: tick grezzi delle finestre selezionate
# --------------------------------------------------------------------------- #
def carica_finestre(sym: str, t0_list: list[int], finestra: int = FINESTRA_S):
    """t0 -> lista di (ts, side, size, px) entro [t0, t0+finestra]."""
    per_giorno: dict[str, list[int]] = {}
    for t0 in t0_list:
        for gg in {(dt.datetime.fromtimestamp(t0, dt.timezone.utc).strftime("%F")),
                   (dt.datetime.fromtimestamp(t0 + finestra, dt.timezone.utc).strftime("%F"))}:
            per_giorno.setdefault(gg, []).append(t0)
    out = {t0: [] for t0 in t0_list}
    for gg, t0s in per_giorno.items():
        path = TICK_DIR / f"{sym}_{gg}.csv.gz"
        if not path.exists():
            continue
        lo, hi = min(t0s), max(t0s) + finestra
        for ts, side, size, px in leggi_giorno(path):
            if ts < lo:
                continue
            if ts > hi:
                break
            for t0 in t0s:
                if t0 <= ts <= t0 + finestra:
                    out[t0].append((ts, side, size, px))
    for t0 in out:
        out[t0].sort(key=lambda x: x[0])
    return out


def metriche_finestra(tk: list[tuple], t0: int, px_rif: float | None = None):
    """Metriche di esecuzione sui tick di una finestra di 600s.

    px_rif = prezzo di riferimento del backtest (chiusura dell'ora del segnale): serve a
    misurare lo slippage *rispetto a quel prezzo*, che e' la grandezza che il backtest
    assume pari a 4 bps per lato.
    """
    if not tk:
        return None
    px0, ts0 = tk[0][3], tk[0][0]
    ev: dict = {"n_tot": len(tk), "px0": px0, "ts0": ts0, "attesa_s": ts0 - t0}
    if px_rif:
        ev["vsrif_0"] = (px0 / px_rif - 1.0) * BPS
    for H in ORIZZONTI_S:
        sel = [x for x in tk if x[0] <= t0 + H]
        if not sel:
            continue
        nb = ns = 0
        vb = vs = 0.0
        ub = us_ = 0.0
        for ts, side, size, px in sel:
            if side == "Buy":
                nb += 1
                vb += size
                ub += size * px
            else:
                ns += 1
                vs += size
                us_ += size * px
        v_all = vb + vs
        ev[f"n_{H}"] = len(sel)
        ev[f"usd_{H}"] = ub + us_
        ev[f"vol_{H}"] = v_all
        ev[f"imb_{H}"] = (vb - vs) / v_all if v_all > 0 else float("nan")
        ev[f"imbn_{H}"] = (nb - ns) / (nb + ns) if (nb + ns) > 0 else float("nan")
        if v_all > 0:
            ev[f"vwap_{H}"] = (ub + us_) / v_all
            ev[f"imp_{H}"] = ((ub + us_) / v_all / px0 - 1.0) * BPS
            if px_rif:
                ev[f"vsrif_{H}"] = ((ub + us_) / v_all / px_rif - 1.0) * BPS
        if vb > 0:
            ev[f"vwapbuy_{H}"] = ub / vb
            ev[f"impbuy_{H}"] = (ub / vb / px0 - 1.0) * BPS      # solo aggressioni in acquisto
            if px_rif:
                ev[f"vsrifbuy_{H}"] = (ub / vb / px_rif - 1.0) * BPS
        if vs > 0:
            ev[f"vwapsell_{H}"] = us_ / vs
            ev[f"impsell_{H}"] = (1.0 - (us_ / vs) / px0) * BPS  # costo di chi vende al mercato
    # percorso: minuti 1..10
    path = []
    for k in range(1, 11):
        sel = [x for x in tk if t0 + (k - 1) * 60 <= x[0] < t0 + k * 60]
        if not sel:
            continue
        pxs = [x[3] for x in sel]
        usd = sum(x[2] * x[3] for x in sel)
        vb = sum(x[2] for x in sel if x[1] == "Buy")
        vs = sum(x[2] for x in sel if x[1] == "Sell")
        path.append({
            "k": k, "n": len(sel), "usd": usd,
            "min_bps": (min(pxs) / px0 - 1.0) * BPS,
            "max_bps": (max(pxs) / px0 - 1.0) * BPS,
            "close_bps": (pxs[-1] / px0 - 1.0) * BPS,
            "imb": (vb - vs) / (vb + vs) if (vb + vs) > 0 else float("nan"),
        })
    ev["path"] = path
    # escursione peggiore/migliore entro 600s e prezzo a +10'
    pxs = [x[3] for x in tk]
    ev["min600_bps"] = (min(pxs) / px0 - 1.0) * BPS
    ev["max600_bps"] = (max(pxs) / px0 - 1.0) * BPS
    ev["close600_bps"] = (pxs[-1] / px0 - 1.0) * BPS
    # spread efficace su bucket da 10s con entrambi i lati
    gap_bucket, roll_serie = [], []
    for k in range(FINESTRA_S // BUCKET_SPREAD_S):
        sel = [x for x in tk if t0 + k * BUCKET_SPREAD_S <= x[0] < t0 + (k + 1) * BUCKET_SPREAD_S]
        if not sel:
            continue
        roll_serie.append(sel[-1][3])
        b = [x for x in sel if x[1] == "Buy"]
        s = [x for x in sel if x[1] == "Sell"]
        if b and s:
            vb = sum(x[2] for x in b)
            vs = sum(x[2] for x in s)
            if vb > 0 and vs > 0:
                pb = sum(x[2] * x[3] for x in b) / vb
                ps = sum(x[2] * x[3] for x in s) / vs
                mid = (pb + ps) / 2.0
                if mid > 0:
                    gap_bucket.append((pb - ps) / mid * BPS)
    ev["n_bucket_2lati"] = len(gap_bucket)
    ev["spread_10s_med_bps"] = med(gap_bucket)
    ev["spread_10s_mean_bps"] = st.mean(gap_bucket) if gap_bucket else float("nan")
    ev["spread_10s_qrt75_bps"] = quantile(gap_bucket, 0.75)
    # Roll su prezzi di trade consecutivi (deriva assunta ~0 nella finestra)
    if len(tk) > 3:
        d = [tk[i][3] - tk[i - 1][3] for i in range(1, len(tk))]
        m1 = st.mean(d)
        m2 = st.mean([x * x for x in d])
        cov = sum((d[i] - m1) * (d[i - 1] - m1) for i in range(1, len(d))) / max(len(d) - 1, 1)
        ev["roll_bps"] = 2.0 * math.sqrt(-cov) / px0 * BPS if cov < 0 else 0.0
        ev["sd_dp_bps"] = math.sqrt(max(m2 - m1 * m1, 0.0)) / px0 * BPS
    return ev


# --------------------------------------------------------------------------- #
# report
# --------------------------------------------------------------------------- #
def tabella(top, titolo):
    L = [f"### {titolo}", "",
         "| # | giorno (UTC) | ora | r_ora | drop 3h | USD ora | n trade | imb.ora | vol x72h | E2 (drop3<=-5% & vol>=3x) |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for i, e in enumerate(top, 1):
        d3 = e.get("drop3", float("nan"))
        q = "si" if (d3 == d3 and d3 <= -0.05 and e["vol_x72"] >= 3.0) else "no"
        L.append(f"| {i} | {e['giorno']} | {e['ora_utc']} | {e['r']*100:+.2f}% | "
                 f"{d3*100:+.2f}% | {e['usd_ora']/1e6:.2f} M$ | {e['n_ora']:,} | "
                 f"{e['imb_ora']:+.3f} | {e['vol_x72']:.2f} | {q} |")
    L.append("")
    return L


def tabella_e2(top, titolo):
    """Tabella per gli eventi che soddisfano la definizione del backtest (drop 3h + volume)."""
    L = [f"### {titolo}", "",
         "| # | giorno (UTC) | ora | r_ora | drop 3h | USD ora | vol x72h | n trade |",
         "|---|---|---|---|---|---|---|---|"]
    for i, e in enumerate(top, 1):
        L.append(f"| {i} | {e['giorno']} | {e['ora_utc']} | {e['r']*100:+.2f}% | "
                 f"{e['drop3']*100:+.2f}% | {e['usd_ora']/1e6:.2f} M$ | {e['vol_x72']:.2f} | {e['n_ora']:,} |")
    L.append("")
    return L


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--simboli", default="DOGEUSDT,SOLUSDT")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--giorni", type=int, default=None, help="usa solo gli ultimi N giorni (prova)")
    ap.add_argument("--controlli", type=int, default=8, help="ore di controllo per simbolo (tick grezzi)")
    ap.add_argument("--out", default="prove/tick_costi_2026-10-14.md")
    ap.add_argument("--cache-dir", default=None)
    ap.add_argument("--no-cache", action="store_true")
    a = ap.parse_args()

    cache_dir = Path(a.cache_dir) if a.cache_dir else Path(tempfile.gettempdir()) / "tick_costi_cache"
    simboli = [s.strip() for s in a.simboli.split(",") if s.strip()]
    t_start = time.time()

    per_simbolo = {}
    for sym in simboli:
        print(f"[{time.time()-t_start:6.1f}s] passata A {sym} ...", file=sys.stderr, flush=True)
        minuti, n_righe, n_file, tick_min = aggrega_minuti(sym, cache_dir, not a.no_cache, a.giorni)
        print(f"[{time.time()-t_start:6.1f}s]   {n_righe:,} trade, {n_file} file, {len(minuti):,} minuti",
              file=sys.stderr, flush=True)
        ore = ore_da_minuti(minuti)
        hrs = sorted(ore)
        rend = rendimenti_orari(ore, hrs[0], hrs[-1], warmup_h=72)
        top = sorted(rend, key=lambda e: -abs(e["r"]))[:a.top]
        neg = sorted([e for e in rend if e["r"] < 0], key=lambda e: e["r"])[:a.top]
        for e in top + neg:
            e["giorno"] = dt.datetime.fromtimestamp(e["h"] * 3600, dt.timezone.utc).strftime("%F")
            e["ora_utc"] = dt.datetime.fromtimestamp(e["h"] * 3600, dt.timezone.utc).strftime("%H:%M")
        per_simbolo[sym] = {"minuti": minuti, "ore": ore, "rend": rend, "top": top, "neg": neg,
                            "n_righe": n_righe, "n_file": n_file, "tick_min": tick_min}
        # eventi E2 veri (definizione del backtest cascate): drop 3h <= -5% e volume >= 3x (72h)
        e2 = [e for e in rend
              if e["drop3"] == e["drop3"] and e["drop3"] <= -0.05
              and e["vol_x72"] == e["vol_x72"] and e["vol_x72"] >= 3.0]
        e2.sort(key=lambda x: x["drop3"])
        per_simbolo[sym]["e2"] = e2[:a.top]
        for e in per_simbolo[sym]["e2"]:
            e["giorno"] = dt.datetime.fromtimestamp(e["h"] * 3600, dt.timezone.utc).strftime("%F")
            e["ora_utc"] = dt.datetime.fromtimestamp(e["h"] * 3600, dt.timezone.utc).strftime("%H:%M")

    # controlli: ore casuali lontane dagli eventi
    for sym, d in per_simbolo.items():
        rnd = random.Random(20261014)
        esclusi = {e["h"] + k for e in d["top"] + d["neg"] + d["e2"] for k in range(-2, 3)}
        cand = [e for e in d["rend"] if e["h"] not in esclusi]
        d["controlli"] = rnd.sample(cand, min(a.controlli, len(cand)))

    # passata B
    for sym, d in per_simbolo.items():
        gruppi = [("top", d["top"]), ("neg", d["neg"]), ("e2", d["e2"]), ("ctrl", d["controlli"])]
        t0s = sorted({e["t0"] for _, g in gruppi for e in g})
        print(f"[{time.time()-t_start:6.1f}s] passata B {sym}: {len(t0s)} finestre ...",
              file=sys.stderr, flush=True)
        ticks = carica_finestre(sym, t0s)
        for _, g in gruppi:
            for e in g:
                o = d["ore"].get(e["h"])
                rif = o["close"] if o else None
                e["rif"] = rif
                e["mis"] = metriche_finestra(ticks[e["t0"]], e["t0"], rif)
        print(f"[{time.time()-t_start:6.1f}s]   fatto", file=sys.stderr, flush=True)

    scrivi_report(per_simbolo, a, t_start)
    return 0


def scrivi_report(per_simbolo, a, t_start):
    L = []
    L.append("# Costi reali di esecuzione nelle cascate — tick Bybit (DOGE, SOL)")
    L.append("")
    L.append(f"Generato da `scripts/tick_costi_cascata.py` il "
             f"{dt.datetime.now(dt.timezone.utc).strftime('%F %T')} UTC.")
    L.append("")
    L.append("## Perimetro e limiti (dichiarati)")
    L.append("")
    L.append("Dati: tick *trade* Bybit (`public.bybit.com/trading`, gratuiti), colonne timestamp /")
    L.append("lato AGGRESSORE / size / prezzo. **Non c'e' l'order book storico**: lo spread quotato")
    L.append("best bid/ask non e' misurabile da qui. Tutti i numeri sotto sono PROXY da trade,")
    L.append("dichiarati come tali: VWAP su finestre, spread efficace buy-vs-sell su bucket da 10s,")
    L.append("stimatore di Roll. Per il dettaglio metodologico vedi l'intestazione dello script.")
    L.append("")
    L.append("Costi assunti dal backtest cascate (`scripts/sonda_cascate.py`):")
    L.append(f"**{COSTO_RT_ASSUNTO:.2%} round-trip** = {FEE_RT_OKX_MISTO:.2%} giro misto OKX + "
             f"2x{SLIP_ASSUNTO_LATO:.2%} slippage. Variante Bybit perp taker: "
             f"{FEE_RT_BYBIT_PERP_TAKER:.2%} RT di sole fee.")
    L.append("")
    for sym, d in per_simbolo.items():
        gg = sorted({Path(f).name.split("_")[1][:10] for f in
                     glob.glob(str(TICK_DIR / f"{sym}_*.csv.gz"))})
        if a.giorni:
            gg = gg[-a.giorni:]
        chi = sorted(v[8] for v in d["minuti"].values())
        px_med = chi[len(chi) // 2] if chi else float("nan")
        tk = d.get("tick_min")
        floor = (tk / px_med * BPS) if tk and px_med == px_med else float("nan")
        d["px_med"] = px_med
        d["tick_bps"] = floor
        L.append(f"- **{sym}**: {len(gg)} giorni ({gg[0]} -> {gg[-1]}), {d['n_righe']:,} trade, "
                 f"{len(d['minuti']):,} minuti con attivita', {len(d['rend']):,} ore contigue. "
                 f"Prezzo mediano {px_med:g}; passo di prezzo minimo osservato {tk!r} = "
                 f"**{floor:.2f} bps** (un attraversamento round-trip non puo' costare meno di 1 passo).")
    L.append("")

    # ---- 1. eventi ----
    def gruppi_di(d):
        g = [("top-|r|", d["top"]), ("cadute", d["neg"])]
        if d["e2"]:
            g.append(("E2 (definizione backtest)", d["e2"]))
        g.append(("controllo (ore normali)", d["controlli"]))
        return g

    L.append("## 1. Le ore piu' violente e i 10 minuti successivi")
    L.append("")
    L.append("Segnale = chiusura dell'ora (t0). Tutte le misure partono dal **primo prezzo")
    L.append("disponibile dopo t0** (`px0`). Colonna `vol x72h` = volume dell'ora / media 72h")
    L.append("precedenti: `qualifica E2 = si` significa che l'ora soddisferebbe anche il filtro")
    L.append("del backtest cascate (drop <= -5% e volume >= 3x).")
    L.append("")
    for sym, d in per_simbolo.items():
        top = d["top"]
        L += tabella(top, f"Top {len(top)} ore per |ritorno| — {sym}")
        L += tabella(d["neg"], f"Top {len(d['neg'])} ore per CADUTA (ritorno piu' negativo) — {sym}")
        if d["e2"]:
            L += tabella_e2(d["e2"], f"Eventi della definizione del backtest cascate "
                                     f"(drop 3h <= -5% e volume >= 3x) — {sym}")
        else:
            L.append(f"### Eventi della definizione del backtest cascate — {sym}")
            L.append("")
            L.append("**Nessun evento** nel periodo coperto dai tick (drop 3h <= -5% con volume >= 3x).")
            L.append("")
    L.append("")

    # ---- 2. microstruttura dei 10 minuti ----
    L.append("## 2. Cosa succede nei 10 minuti dopo il segnale (misure sui tick)")
    L.append("")
    L.append("`imp_H` = (VWAP di tutti i trade entro H secondi)/px0 - 1, in bps: e' il prezzo medio")
    L.append("pagato da chi esegue al mercato spalmando l'ordine su quella finestra.")
    L.append("`impbuy_H` = lo stesso usando **solo i trade con aggressore Buy** (piu' severo:")
    L.append("e' il prezzo medio di chi compra davvero). `impsell_H` = costo simmetrico per chi vende.")
    L.append("`min600/max600` = escursione peggiore/migliore entro 10 minuti rispetto a px0.")
    L.append("`spread10s` = spread efficace mediano su bucket da 10s con entrambi i lati")
    L.append("(proxy del pedaggio round-trip di attraversamento, senza fee). ATTENZIONE: e' un")
    L.append("**limite inferiore**, non lo spread quotato — su un bucket affollato i due VWAP")
    L.append("convergono e il proxy tende a 0, mentre lo spread vero non puo' scendere sotto 1 passo")
    L.append("di prezzo (colonna 'passo' nella tabella dei simboli). Il 'Roll' e' un secondo")
    L.append("stimatore indipendente, anch'esso un limite inferiore in presenza di deriva.")
    L.append("")
    def tab_dettaglio(gruppo, etichetta):
        out = ["", f"#### {etichetta}", "",
               "`vsrif` = prezzo eseguito rispetto alla **chiusura dell'ora del segnale** (il prezzo che il",
               "backtest assume di pagare): negativo = si paga meno di quanto assume il backtest.",
               "",
               "| giorno | ora | r_ora | attesa s | n60 | n600 | M$ 60s | M$ 600s | imb 60s | imb 600s | "
               "imp 60s | impbuy 60s | imp 120s | impbuy 120s | impsell 120s | vsrif px0 | vsrif vwap60 | "
               "min600 | max600 | close600 | spread10s(med) | Roll |",
               "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for e in gruppo:
            m = e["mis"]
            if not m:
                continue
            g = lambda k, d_=None: m.get(k, d_) if d_ is not None else m.get(k, float("nan"))
            out.append(
                f"| {e['giorno']} | {e['ora_utc']} | {e['r']*100:+.2f}% | {m['attesa_s']:.1f} | "
                f"{m.get('n_60', 0):,} | {m.get('n_600', 0):,} | {m.get('usd_60', 0)/1e6:.3f} | "
                f"{m.get('usd_600', 0)/1e6:.2f} | {g('imb_60'):+.2f} | {g('imb_600'):+.2f} | "
                f"{g('imp_60'):+.1f} | {g('impbuy_60'):+.1f} | {g('imp_120'):+.1f} | {g('impbuy_120'):+.1f} | "
                f"{g('impsell_120'):+.1f} | {g('vsrif_0'):+.1f} | {g('vsrif_60'):+.1f} | "
                f"{m['min600_bps']:+.1f} | "
                f"{m['max600_bps']:+.1f} | {m['close600_bps']:+.1f} | "
                f"{m['spread_10s_med_bps']:.1f} | {g('roll_bps'):.1f} |")
        out.append("")
        out += ["| minuto | USD medi | n trade | min bps (med) | close bps (med) | imb (med) |",
                "|---|---|---|---|---|---|"]
        for k in range(1, 11):
            sel = [e["mis"]["path"][k - 1] for e in gruppo
                   if e["mis"] and len(e["mis"]["path"]) >= k]
            if not sel:
                continue
            out.append(f"| +{k}' | {med([x['usd'] for x in sel])/1e6:.3f} M$ | {med([x['n'] for x in sel]):,.0f} | "
                       f"{med([x['min_bps'] for x in sel]):+.1f} | {med([x['close_bps'] for x in sel]):+.1f} | "
                       f"{med([x['imb'] for x in sel]):+.2f} |")
        out.append("")
        return out

    for sym, d in per_simbolo.items():
        L.append(f"### {sym}")
        L += tab_dettaglio(d["top"], "eventi: top 10 per |ritorno| (i piu' violenti in assoluto)")
        L += tab_dettaglio(d["neg"], "eventi: top 10 per CADUTA (il caso del backtest cascate)")
        if d["e2"]:
            L += tab_dettaglio(d["e2"], "eventi E2: definizione esatta del backtest cascate")

    # ---- 3. slippage market buy/sell (2 minuti) + confronto con i controlli ----
    L.append("## 3. Stima (conservativa) dello slippage di un market buy/sell")
    L.append("")
    L.append("Proxy: differenza tra il **prezzo medio dei trade BUY nei primi 120s** e il primo")
    L.append("prezzo disponibile px0, in bps. E' conservativa in due sensi: (a) spalma l'ordine su")
    L.append("120 secondi, cosa che un'esecuzione reale non fa (ma il flusso viene tutto dal lato")
    L.append("che si muove contro di te), (b) ignora il consumo di liquidita' oltre il flusso")
    L.append("osservato. Per il sell e' speculare.")
    L.append("")
    L.append("| simbolo | campione | n | slippage buy 120s (med) | p75 | slippage sell 120s (med) | p75 | "
             "RT stimato (buy+sell) | spread10s (med) |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    riassunto = {}
    for sym, d in per_simbolo.items():
        for nome, grp in gruppi_di(d):
            sb = [e["mis"]["impbuy_120"] for e in grp if e["mis"] and "impbuy_120" in e["mis"]]
            ss = [e["mis"]["impsell_120"] for e in grp if e["mis"] and "impsell_120" in e["mis"]]
            sp = [e["mis"]["spread_10s_med_bps"] for e in grp if e["mis"] and
                  not math.isnan(e["mis"]["spread_10s_med_bps"])]
            if not sb or not ss:
                continue
            rt = med(sb) + med(ss)
            riassunto[(sym, nome)] = {"buy": med(sb), "sell": med(ss), "rt": rt,
                                      "buy_p75": quantile(sb, 0.75), "sell_p75": quantile(ss, 0.75),
                                      "spread": med(sp) if sp else float("nan"), "n": len(sb),
                                      "buy_mean": st.mean(sb), "sell_mean": st.mean(ss)}
            L.append(f"| {sym} | {nome} | {len(sb)} | {med(sb):+.1f} bps | {quantile(sb,0.75):+.1f} | "
                     f"{med(ss):+.1f} bps | {quantile(ss,0.75):+.1f} | **{rt:+.1f} bps** | "
                     f"{med(sp) if sp else float('nan'):.1f} bps |")
    L.append("")
    # confronto diretto col prezzo di riferimento del backtest (chiusura dell'ora)
    L.append("### 3b. Prezzo eseguito vs prezzo di riferimento del backtest (chiusura dell'ora)")
    L.append("")
    L.append("Il backtest assume di comprare alla chiusura dell'ora con 4 bps di slippage per lato.")
    L.append("Qui si misura il prezzo *realmente disponibile* rispetto a quella chiusura, in bps.")
    L.append("Negativo = si paga MENO del prezzo assunto dal backtest, quindi lo slippage assunto non")
    L.append("serve (nella direzione sfavorevole); positivo = il mercato e' scappato.")
    L.append("")
    L.append("| simbolo | campione | n | px0 vs rif | vwap 5s vs rif | vwap 60s vs rif | vwap buy 60s vs rif | vwap buy 120s vs rif |")
    L.append("|---|---|---|---|---|---|---|---|")
    for sym, d in per_simbolo.items():
        for nome, grp in gruppi_di(d):
            v0 = [e["mis"]["vsrif_0"] for e in grp if e["mis"] and "vsrif_0" in e["mis"]]
            v5 = [e["mis"]["vsrif_5"] for e in grp if e["mis"] and "vsrif_5" in e["mis"]]
            v60 = [e["mis"]["vsrif_60"] for e in grp if e["mis"] and "vsrif_60" in e["mis"]]
            vb60 = [e["mis"]["vsrifbuy_60"] for e in grp if e["mis"] and "vsrifbuy_60" in e["mis"]]
            vb120 = [e["mis"]["vsrifbuy_120"] for e in grp if e["mis"] and "vsrifbuy_120" in e["mis"]]
            if not v0:
                continue
            L.append(f"| {sym} | {nome} | {len(v0)} | {med(v0):+.1f} | {med(v5):+.1f} | {med(v60):+.1f} | "
                     f"{med(vb60):+.1f} | {med(vb120):+.1f} |")
    L.append("")
    if riassunto:
        for fam in ("top-|r|", "cadute"):
            casc = [v["rt"] for (s, n), v in riassunto.items() if n == fam]
            ctrl = [v["rt"] for (s, n), v in riassunto.items() if n.startswith("controllo")]
            if not casc or not ctrl:
                continue
            a_, b_ = st.mean(casc), st.mean(ctrl)
            L.append(f"Slippage round-trip mediano — {fam}: **{a_:+.1f} bps** vs controllo "
                     f"{b_:+.1f} bps (rapporto {a_/b_:.1f}x)." if b_ else "")
        L.append("")

    # ---- 4. confronto con i 0,26% ----
    L.append("## 4. Confronto con il costo assunto (0,26% RT)")
    L.append("")
    L.append("All-in = fee round-trip + slippage RT proxy misurato (mediana buy + mediana sell).")
    L.append("")
    if riassunto:
        L.append("| simbolo | campione | fee RT | slippage RT proxy | costo all-in RT | vs assunto 0,26% |")
        L.append("|---|---|---|---|---|---|")
        for (sym, nome), v in sorted(riassunto.items()):
            for etichetta, fee in (("OKX misto 0,18%", FEE_RT_OKX_MISTO),
                                   ("Bybit taker 0,11%", FEE_RT_BYBIT_PERP_TAKER)):
                allin = fee + v["rt"] / BPS
                L.append(f"| {sym} | {nome} — {etichetta} | {fee:.2%} | {v['rt']:.1f} bps "
                         f"({v['rt']/BPS:.2%}) | **{allin:.3%}** | {(allin/COSTO_RT_ASSUNTO-1)*100:+.0f}% |")
        L.append("")
        L.append("Versione severa (p75 del buy + p75 del sell, non le mediane):")
        L.append("")
        L.append("| simbolo | campione | slippage RT p75 | all-in (fee OKX 0,18%) |")
        L.append("|---|---|---|---|")
        for (sym, nome), v in sorted(riassunto.items()):
            allin = FEE_RT_OKX_MISTO + (v["buy_p75"] + v["sell_p75"]) / BPS
            L.append(f"| {sym} | {nome} | {v['buy_p75']+v['sell_p75']:.1f} bps | **{allin:.3%}** |")
        L.append("")

    # ---- 5. impatto per dimensione ordine ----
    L.append("## 5. Impatto atteso per dimensione dell'ordine (proxy lineare, dichiarato)")
    L.append("")
    L.append("Il costo sopra e' quello del *flusso*, cioe' di un ordine grande quanto l'intero")
    L.append("volume scambiato nella finestra. Per un ordine piu' piccolo il costo e' assunto")
    L.append("proporzionale alla quota di flusso che occupa (legge lineare di Kyle: approssimazione")
    L.append("- l'impatto reale e' sub-lineare, quindi questa stima e' prudenziale per ordini piccoli")
    L.append("e ottimistica per ordini grandi). Per lato: (proprio USD / USD taker nei primi 120s) x")
    L.append("slippage_buy_120s misurato. Eventi di caduta (il caso del backtest).")
    L.append("")
    L.append("| simbolo | ordine | quota del flusso 120s (med) | slippage stimato per lato | all-in RT con fee 0,18% |")
    L.append("|---|---|---|---|---|")
    for sym, d in per_simbolo.items():
        grp = d["e2"] or d["neg"] or d["top"]
        usds = [e["mis"]["usd_120"] for e in grp if e["mis"] and "usd_120" in e["mis"]]
        sb = [e["mis"]["impbuy_120"] for e in grp if e["mis"] and "impbuy_120" in e["mis"]]
        ss = [e["mis"]["impsell_120"] for e in grp if e["mis"] and "impsell_120" in e["mis"]]
        if not usds or not sb or not ss:
            continue
        u, s, s2 = med(usds), med(sb), med(ss)
        for taglia in (10_000, 50_000, 100_000, 500_000, 1_000_000):
            quota = taglia / u
            lato = s * quota
            allin = FEE_RT_OKX_MISTO + (lato + s2 * quota) / BPS
            L.append(f"| {sym} | {taglia/1e3:.0f}k$ | {quota:.2%} | {lato:+.2f} bps | {allin:.3%} |")
    L.append("")

    # ---- verdetto ----
    L.append("## 6. Numeri chiave (generati) e verdetto")
    L.append("")
    if riassunto:
        righe = []
        for (sym, nome), v in sorted(riassunto.items()):
            if nome.startswith("controllo"):
                continue
            allin = FEE_RT_OKX_MISTO + v["rt"] / BPS
            righe.append((sym, nome, v, allin))
        L.append("| simbolo | campione | slippage buy (med) | slippage sell (med) | spread10s (med) | all-in RT |")
        L.append("|---|---|---|---|---|---|")
        for sym, nome, v, allin in righe:
            L.append(f"| {sym} | {nome} | {v['buy']:+.1f} bps | {v['sell']:+.1f} bps | "
                     f"{v['spread']:.1f} bps | {allin:.3%} |")
        L.append("")
        peggiori = [allin for _, _, _, allin in righe]
        cand = max(peggiori) if peggiori else float("nan")
        if cand > COSTO_RT_ASSUNTO:
            L.append(f"**Verdetto automatico**: il costo all-in piu' alto misurato e' {cand:.3%}, "
                     f"sopra l'assunto di {COSTO_RT_ASSUNTO:.2%} ("
                     f"{(cand/COSTO_RT_ASSUNTO-1)*100:+.0f}%). Il costo assunto NON regge: "
                     f"va alzato ad almeno ~{cand:.2%}.")
        else:
            L.append(f"**Verdetto automatico**: il costo all-in piu' alto misurato e' {cand:.3%}, "
                     f"sotto l'assunto di {COSTO_RT_ASSUNTO:.2%}. Il costo assunto regge.")
        L.append("")
    L.append("## 7. Lettura e verdetto")
    L.append("")
    L.append("_Sezione scritta a mano sul run completo del 2026-10-15 (29 giorni di tick); i numeri")
    L.append("citati sono quelli delle tabelle qui sopra, rigenerabili con lo script._")
    L.append("")
    L.append("### 7.1 Copertura: cosa manca (da dire per primo)")
    L.append("")
    L.append("Nella finestra tick (2026-09-13 -> 2026-10-11) **non esiste nessun evento della")
    L.append("definizione E2** (drop 3h <= -5% con volume >= 3x): in questi 29 giorni il mercato non")
    L.append("ha fatto cascate. L'evento piu' vicino e' **2026-10-08 15:00 UTC**: DOGE -5,14% in UNA")
    L.append("ora con volume 10x la media 72h (SOL -3,51% nella stessa ora, 7,3x). Le tabelle sopra")
    L.append("misurano quindi il massimo di violenza *disponibile*, non una cascata vera. Tutto")
    L.append("quanto segue vale per eventi di questa taglia; su una cascata da -15%/-20% in un'ora")
    L.append("non c'e' nessuna evidenza in questi dati.")
    L.append("")
    L.append("### 7.2 Cosa costa davvero comprare al mercato dopo la caduta")
    L.append("")
    L.append("1. **Esecuzione immediata** (primo print dopo la chiusura del segnale, ritardo ~0,1 s):")
    L.append("   prezzo = **+0,0 bps** rispetto alla chiusura d'ora usata dal backtest come")
    L.append("   riferimento, sia nelle ore violente sia nel controllo. Comprando subito si paga il")
    L.append("   prezzo che il backtest assume, senza maggiorazione misurabile.")
    L.append("2. **Esecuzione spalmata su 60-120 s**: +3,0 bps (DOGE) e +4,7 bps (SOL) mediani nelle")
    L.append("   10 ore di caduta, con punte di +15,6 bps (DOGE) e +9,8 bps (SOL) nell'ora peggiore.")
    L.append("   Aspettare costa: subito dopo un crollo il mercato rimbalza.")
    L.append("3. **Pedaggio di attraversamento** (spread efficace da trade): 0,4-0,6 bps mediani,")
    L.append("   contro un pavimento fisico di 1 passo di prezzo = 1,08 bps (DOGE) e 0,86 bps (SOL);")
    L.append("   lo stimatore di Roll da' lo stesso ordine di grandezza. Sono **limiti inferiori**:")
    L.append("   con i soli trade non si puo' misurare lo spread quotato.")
    L.append("4. **La coda e' il vero problema**: p75 dello slippage round-trip = 28,4 bps (DOGE) e")
    L.append("   9,2 bps (SOL) nelle ore di caduta, 36,0 bps (DOGE) sulle ore piu' violenti. In un")
    L.append("   quarto degli eventi si paga 3-7 volte la mediana.")
    L.append("5. **Dimensione dell'ordine**: fino a 100k$ l'impatto addizionale e' <= 0,2 bps per lato;")
    L.append("   a 1 M$ ~2 bps per lato. Per il size presumibile del backtest e' irrilevante.")
    L.append("")
    L.append("### 7.3 Verdetto sul 0,26% round-trip")
    L.append("")
    L.append("- **Caso mediano: REGGE.** 0,18% (fee OKX) + 5,2 bps (DOGE) = **0,232%**; + 3,2 bps")
    L.append("  (SOL) = **0,212%**. Cioe' 11-19% sotto il costo assunto. Con le sole fee Bybit taker")
    L.append("  (0,11%) si scende a 0,14-0,16%: il costo assunto e' quasi il doppio del necessario.")
    L.append("- **Caso coda: NON REGGE.** 0,18% + 28,4 bps = **0,464%** (DOGE cadute); 0,18% + 36,0 bps")
    L.append("  = **0,540%** (DOGE ore piu' violenti); SOL 0,272%.")
    L.append("- Il run a 0,26% e' quindi accettabile come caso base per DOGE/SOL, ma **non e' un")
    L.append("  numero prudente**: va affiancato da uno stress a ~0,50% RT. Se l'edge delle cascate")
    L.append("  vive solo tra 0,26% e 0,50% RT, e' fragile. In assenza di una cascata vera in finestra")
    L.append("  tick, e' la coda misurata sulle ore piu' violenti disponibili la migliore stima del")
    L.append("  costo atteso in condizioni di stress.")
    L.append("- **Regola operativa che esce dalle misure**: eseguire al primo print, non spalmare.")
    L.append("  Aspettare 60-120 s costa 3-6 bps mediani e fino a 16 bps nell'ora peggiore.")
    L.append("")
    L.append("_Limite residuo da tenere presente: senza order book storico non si puo' escludere che in")
    L.append("una cascata vera lo spread si allarghi oltre quanto misurato qui; i numeri di questa")
    L.append("pagina sono un limite inferiore del costo reale in condizioni di stress._")
    L.append("")
    testo_out = Path(RADICE / a.out)
    testo_out.parent.mkdir(parents=True, exist_ok=True)
    testo_out.write_text("\n".join(L) + "\n")
    if riassunto:
        num = {f"{sym}|{nome}": {"slippage_buy_bps": v["buy"], "slippage_sell_bps": v["sell"],
                                 "rt_bps": v["rt"], "buy_p75_bps": v["buy_p75"],
                                 "sell_p75_bps": v["sell_p75"], "spread10s_med_bps": v["spread"],
                                 "allin_rt_okx": FEE_RT_OKX_MISTO + v["rt"] / BPS, "n": v["n"]}
               for (sym, nome), v in riassunto.items()}
        sidecar = testo_out.with_suffix(".json")
        sidecar.write_text(json.dumps(num, indent=1))
        print(f"[numeri: {sidecar}]", file=sys.stderr)
    print("\n".join(L))
    print(f"\n[report scritto: {testo_out}]  ({time.time()-t_start:.0f}s)", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
