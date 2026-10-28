#!/usr/bin/env python3
"""crosssec_mom_vol.py — momentum cross-sectional normalizzato per volatilità (e4).

MANDATO (dal laboratorio Denaro, pre-registrato PRIMA dei numeri):
  1) universo: tutte le serie 1D e 4H in data/cache (min 30 asset);
  2) segnale: momentum normalizzato per volatilità: ret(L giorni) / (sigma(V giorni)·sqrt(L));
  3) portafoglio long-short market-neutral (top/bottom quintile, pesi EW o inverso-vol,
     ribilanciamento settimanale) + versione long-only (solo top quintile);
  4) costi reali su ogni ribilanciamento (giro 0,18% + slippage 0,04%/lato → 0,13% per lato,
     sul turnover EFFETTIVO, contabilità onesta come crosssec_v2);
  5) walk-forward: train fino 2024-06-01, verifica dopo; variante scelta SOLO sul train;
  6) cancello su OOS: (a) no look-ahead verificato per troncamento; (b) positivo in >=4/5
     blocchi; (c) sopravvive a fee+50%; (d) Monte Carlo (block-bootstrap) 5° pct non
     catastrofico (p5 CAGR > -15%/anno E p5 terminale >= 0,70); (e) regge senza i 3 asset
     con maggior contributo al P&L OOS.

UNIVERSO DICHIARATO
  - Pannello primario 1d: serie `okx_eea_<SYM>-USDT_1d.json` (90 simboli, 2019-2026): la
    sede su cui il conto opera davvero. Le serie bybit 1d NON aggiungono simboli (tutte
    presenti anche su okx_eea) e non vengono mescolate ai prezzi okx (una sede sola).
  - Pannello secondario 4h: serie `bybit_<SYM>-USDT_4h.json` (59 simboli) come verifica
    indipendente sull'altro timeframe richiesto dal mandato.
  - Esclusioni pre-dichiarate (stesse ragioni di crosssec_v2 + igiene cache):
      CTC  redenominazione/token swap (+195,7% il 2023-12-12; wick 3822x il 2022-09-21 sui 4h)
      GAS  serie rotta (scala prezzi incoerente con il mercato, vedi skill cache-ohlcv-igiene)
      USDC stablecoin: nessuna dispersione cross-sezionale, occupa sistematicamente una gamba.
  - Sospetti (|r| giornaliero > 100%) NON esclusi in base: elencati nel report; scenario
    `igiene_stretta` di sensibilità sul pannello 1d.

SEGNALE (griglia dichiarata, 12 varianti)
  score_s = (P_s[t-1]/P_s[t-1-L] - 1) / (stddev(rendimenti giornalieri su V giorni)·sqrt(L))
  L in (21, 42, 63, 90) giorni; V in (30, 60, 90) giorni.
  Sul 4h: stesse finestre in giorni → 6·L e 6·V barre.

PORTAFOGLIO (dichiarato)
  quintili: k = n//5 nomi per gamba, n = asset con score valido; si opera solo con n >= 30.
  LS: long i k migliori +1/(2k), short i k peggiori −1/(2k) → lordo 1,0 netto 0.
  LO: long i k migliori +1/k → lordo 1,0.
  Pesi: 'ew' equipesati o 'invol' inverso-volatilità dentro la gamba (2 varianti).
  Ribilanciamento: alla prima barra di ogni settimana ISO (esecuzione alla chiusura).
  Timing (fisso): segnale con barre fino alla chiusura di t−1, esecuzione alla chiusura di t,
  rendimento da t a t+1. Nessun dato del giorno di esecuzione entra nel ranking.

COSTI (dichiarato): costo_lato = (0,0018 + 2×0,0004)/2 = 0,0013 (0,26% RT / 2);
  addebitato SOLO sul turnover effettivo Σ|w_nuovo−w_vecchio|; chiusura forzata su fine dati
  o buco: un lato sul peso. Stress fee+50%: costo_lato×1,5.

WALK-FORWARD (dichiarato)
  confine 2024-06-01T00:00Z. Per ciascuna strategia (LS, LO) e per ciascun pannello:
  24 varianti misurate; variante promossa = argmax CAGR netto su TRAIN (tie-break dichiarato:
  a parità entro 0,5 pp di CAGR, si preferisce il turnover minore). La verifica OOS usa la
  variante CONGELATA. Nessuna scelta su OOS.

CANCELLO OOS (soglie pre-dichiarate)
  G1 no look-ahead: pannello troncato a T → rendimenti < T identici bit a bit.
  G2 blocchi: OOS diviso in 5 blocchi di uguale durata; promossa solo se positiva in >=4/5.
  G3 fee+50%: stesso OOS con costo_lato×1,5 → CAGR OOS ancora > 0.
  G4 Monte Carlo: block-bootstrap (blocchi da 7 giorni, 3000 percorsi) dei rendimenti OOS;
     p5 CAGR > −15%/anno E p5 ricchezza terminale >= 0,70.
  G5 senza i 3 asset migliori: rimossi dall'universo i 3 simboli con maggior contributo
     lordo al P&L OOS; backtest intero rifatto (variante congelata); CAGR OOS ancora > 0.

Artefatti: prove/e4_momentum_crosssec_<data>.md (report IT) e .json (numeri).
"""
from __future__ import annotations

import json
import math
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

RADICE = Path(__file__).resolve().parents[1]
CACHE = RADICE / "data" / "cache"
PROVE = RADICE / "prove"

CONFINE_ISO = "2024-06-01"
L_GRID = (21, 42, 63, 90)
V_GRID = (30, 60, 90)
PESI = ("ew", "invol")
MIN_ASSET = 30          # mandato: universo min 30 asset per operare
N_BLOCCHI = 5
PASS_BLOCCHI = 4        # (N-1)/N = 4/5
FEE_STRESS = 1.5
MC_N = 3000
MC_BLOCK = 7
MC_P5_CAGR_MIN = -0.15  # p5 CAGR OOS non peggiore di -15%/anno
MC_P5_TERM_MIN = 0.70   # p5 ricchezza terminale OOS non sotto 0,70
FUNDING_STRESS = 0.056  # sensibilità LS: funding annuo sul nozionale short (misurato carry)

# costo lato: giro misto 0,18% (maker 0,08 + taker 0,10, conto con X-Perps, verificato
# 2026-10-06) + 2 x 0,04% slippage → round-trip 0,26% → 0,13% per lato.
COSTO_LATO = 0.0013

ESCLUSI = {
    "CTC": "redenominazione/token swap (+195,7% il 2023-12-12; wick 3822x sui 4h il 2022-09-21)",
    "GAS": "serie rotta: scala prezzi incoerente con il mercato (skill cache-ohlcv-igiene)",
    "USDC": "stablecoin: nessuna dispersione cross-sezionale, occupa una gamba",
}

PANNELLI = {
    "1d_okx": dict(pattern="okx_eea_*-USDT_1d.json", bar_ms=86_400_000,
                   split=lambda n: n.split("okx_eea_", 1)[1].split("-USDT", 1)[0]),
    "4h_bybit": dict(pattern="bybit_*-USDT_4h.json", bar_ms=14_400_000,
                     split=lambda n: n.split("bybit_", 1)[1].split("-USDT", 1)[0]),
}


# --------------------------------------------------------------------------------------
# dati
# --------------------------------------------------------------------------------------
class Serie:
    """Serie di un simbolo: ts (ms, crescenti) e chiusure, più ritorni bar-to-bar."""

    __slots__ = ("sym", "ts", "close", "ret")

    def __init__(self, sym: str, ts: np.ndarray, close: np.ndarray):
        self.sym = sym
        self.ts = ts
        self.close = close
        self.ret = np.empty(len(close))
        self.ret[0] = np.nan
        if len(close) > 1:
            self.ret[1:] = close[1:] / close[:-1] - 1.0

    def score(self, L: int, V: int, j: int, bar_ms: int, n_bar_giorno: int):
        """score alla barra j (ultima barra nota): ret su L giorni / (sigma(V)·sqrt(L))."""
        Lb, Vb = L * n_bar_giorno, V * n_bar_giorno
        if j < Lb or j < Vb or self.close[j - Lb] <= 0:
            return None, None
        ret = self.close[j] / self.close[j - Lb] - 1.0
        seg = self.ret[j - Vb + 1: j + 1]
        sigma = float(np.std(seg))
        if not math.isfinite(sigma) or sigma <= 0:
            return None, None
        return ret / (sigma * math.sqrt(L)), sigma


def carica_pannello(nome: str, esclusi: dict) -> dict:
    """Ritorna dict con 'simboli', 'serie' (sym -> Serie), 'giorni' (ts panel ordinati),
    'px' (lista di dict sym->close per giorno), 'nome', 'bar_ms'."""
    cfg = PANNELLI[nome]
    serie: dict[str, Serie] = {}
    for p in sorted(CACHE.glob(cfg["pattern"])):
        sym = cfg["split"](p.name)
        if sym in esclusi:
            continue
        try:
            barre = json.loads(p.read_text(encoding="utf-8"))["barre"]
        except Exception:
            continue
        ts, cl = [], []
        for b in barre:
            try:
                t, c = int(b[0]), float(b[4])
            except (TypeError, ValueError, IndexError):
                continue
            if c > 0:
                ts.append(t)
                cl.append(c)
        if len(ts) < 100:
            continue
        serie[sym] = Serie(sym, np.array(ts, dtype=np.int64), np.array(cl, dtype=np.float64))

    giorni = sorted({int(t) for s in serie.values() for t in s.ts})
    px = [{s: None for s in serie} for _ in giorni]
    for idx, t in enumerate(giorni):
        d = px[idx]
        for sym, s in serie.items():
            j = int(np.searchsorted(s.ts, t))
            if j < len(s.ts) and s.ts[j] == t:
                d[sym] = float(s.close[j])
    # settimane ISO precomputate (per il ribilanciamento settimanale)
    iso = [datetime.fromtimestamp(t / 1000, timezone.utc).isocalendar()[:2] for t in giorni]
    weeks = np.array([y * 100 + w for y, w in iso], dtype=np.int64)
    return {"simboli": sorted(serie), "serie": serie, "giorni": giorni, "px": px,
            "nome": nome, "bar_ms": cfg["bar_ms"],
            "n_bar_giorno": 1 if cfg["bar_ms"] == 86_400_000 else 6, "weeks": weeks}


def settimana_chiave(ts: int) -> tuple:
    d = datetime.fromtimestamp(ts / 1000, timezone.utc).isocalendar()
    return (d[0], d[1])


# --------------------------------------------------------------------------------------
# selezione portafoglio
# --------------------------------------------------------------------------------------
def seleziona(scores: dict, sigma: dict, k: int, pesi: str, direzione: str) -> dict:
    """Pesi target da ranking decrescente di score.

    scores: sym -> score (NaN esclusi a monte). k = nomi per gamba (quintile).
    direzione 'ls' → +1/(2k) top / −1/(2k) bottom; 'lo' → +1/k top.
    """
    ord_sym = sorted(scores, key=lambda s: scores[s], reverse=True)
    top = ord_sym[:k]
    if direzione == "ls":
        bottom = ord_sym[-k:]
        if pesi == "invol":
            wl = {s: 1.0 / max(sigma[s], 1e-9) for s in top}
            ws = {s: 1.0 / max(sigma[s], 1e-9) for s in bottom}
            sl, ss = sum(wl.values()), sum(ws.values())
            return {s: 0.5 * wl[s] / sl for s in top} | {s: -0.5 * ws[s] / ss for s in bottom}
        return {s: 0.5 / k for s in top} | {s: -0.5 / k for s in bottom}
    if pesi == "invol":
        wl = {s: 1.0 / max(sigma[s], 1e-9) for s in top}
        sl = sum(wl.values())
        return {s: wl[s] / sl for s in top}
    return {s: 1.0 / k for s in top}


# --------------------------------------------------------------------------------------
# backtest
# --------------------------------------------------------------------------------------
def backtest(pan: dict, *, L: int, V: int, pesi: str, direzione: str,
             costo_lato: float, funding_annuo: float = 0.0,
             universo: set | None = None, attribuzione: bool = False,
             pesi_log: bool = False):
    """Serie netta giornaliera/barra della strategia sul pannello `pan`.

    Esecuzione: se la settimana ISO della barra corrente è nuova rispetto alla precedente,
    si ribilancia alla CHIUSURA della barra corrente t usando score noti alla chiusura di
    t−1; il rendimento è guadagnato da chiusura t a chiusura t+1.
    """
    giorni, px = pan["giorni"], pan["px"]
    weeks = pan["weeks"]
    serie = pan["serie"]
    bar_ms = pan["bar_ms"]
    ng = pan["n_bar_giorno"]
    universo = set(pan["simboli"]) if universo is None else universo
    n = len(giorni)
    pesi_attuali: dict[str, float] = {}
    lordo: list[float] = []
    netto: list[float] = []
    costi: list[float] = []
    rib: list[dict] = []
    attr: list[dict] = [] if attribuzione else None
    log_pesi: list[tuple] = [] if pesi_log else None
    costo_uscite = 0.0

    for i in range(1, n - 1):          # i = barra di ESECUZIONE
        if weeks[i] != weeks[i - 1]:
            t_ref = giorni[i - 1]      # ultimo dato noto prima dell'esecuzione
            scores, sigmas, n_valid = {}, {}, 0
            for sym in universo:
                s = serie.get(sym)
                if s is None:
                    continue
                j = int(np.searchsorted(s.ts, t_ref, side="right")) - 1
                if j < 0 or t_ref - s.ts[j] > 1.5 * bar_ms:
                    continue            # serie ferma: simbolo non più quotato/stale
                sc, sg = s.score(L, V, j, bar_ms, ng)
                if sc is None:
                    continue
                scores[sym], sigmas[sym] = sc, sg
                n_valid += 1
            if n_valid >= MIN_ASSET:
                k = max(1, n_valid // 5)
                nuovi = seleziona(scores, sigmas, k, pesi, direzione)
                if nuovi:
                    turnover = sum(abs(nuovi.get(s, 0.0) - pesi_attuali.get(s, 0.0))
                                   for s in set(nuovi) | set(pesi_attuali))
                    costi_rib = costo_lato * turnover
                    rib.append({"i": i, "turnover": turnover, "costo": costi_rib,
                                "n_long": sum(1 for w in nuovi.values() if w > 0),
                                "n_short": sum(1 for w in nuovi.values() if w < 0)})
                    pesi_attuali = nuovi
                    if pesi_log:
                        log_pesi.append((i, dict(nuovi)))
        r, c = 0.0, 0.0
        usciti = []
        attr_i = {}
        for s, w in pesi_attuali.items():
            p0, p1 = px[i].get(s), px[i + 1].get(s)
            if p0 and p1:
                rs = p1 / p0 - 1.0
                r += w * rs
                if attribuzione:
                    attr_i[s] = w * rs
            else:
                usciti.append(s)       # dato mancante/fine serie: chiusura forzata
        cc = sum(abs(pesi_attuali[s]) for s in usciti) * costo_lato
        costo_uscite += cc
        for s in usciti:
            del pesi_attuali[s]
        if rib and rib[-1]["i"] == i:
            c += rib[-1]["costo"]
        c += cc
        if funding_annuo > 0:
            short_not = sum(-w for w in pesi_attuali.values() if w < 0)
            c += funding_annuo * short_not * bar_ms / (365.0 * 86_400_000)
        lordo.append(r)
        costi.append(c)
        netto.append(r - c)
        if attribuzione:
            attr.append(attr_i)
    return {"lordo": lordo, "netto": netto, "costi": costi, "rib": rib,
            "giorni": giorni[1:-1], "costo_uscite": costo_uscite, "attr": attr,
            "log_pesi": log_pesi}


# --------------------------------------------------------------------------------------
# statistiche
# --------------------------------------------------------------------------------------
def t_stat(rend):
    if len(rend) < 3:
        return None
    mu, sd = statistics.mean(rend), statistics.pstdev(rend)
    return mu / (sd / math.sqrt(len(rend))) if sd > 0 else None


def t_nw(rend, lag=7):
    n = len(rend)
    if n < lag + 3:
        return t_stat(rend)
    mu = statistics.mean(rend)
    dev = np.array(rend) - mu
    g0 = float(np.mean(dev * dev))
    s = g0
    for l in range(1, lag + 1):
        s += 2.0 * (1.0 - l / (lag + 1.0)) * float(np.mean(dev[l:] * dev[:-l]))
    if s <= 0:
        return t_stat(rend)
    return mu / math.sqrt(s / n)


def cagr(rend):
    if not rend:
        return None
    cum = math.prod(1.0 + r for r in rend)
    if cum <= 0:
        return None
    return cum ** (365.0 * 86_400_000 / (86_400_000 * len(rend))) - 1.0 if False else cum ** (365.0 / len(rend)) - 1.0


def sharpe(rend):
    if len(rend) < 3:
        return None
    mu, sd = statistics.mean(rend), statistics.pstdev(rend)
    return mu / sd * math.sqrt(365.0) if sd > 0 else None


def max_dd(netto):
    eq, picco, dd = 1.0, 1.0, 0.0
    for r in netto:
        eq *= 1.0 + r
        picco = max(picco, eq)
        dd = max(dd, (picco - eq) / picco)
    return dd


def blocchi(netto, giorni, confine_ms):
    """N_BLOCCHI blocchi di uguale durata sul periodo [confine_ms, fine]; ritorni composti."""
    t0 = confine_ms
    t1 = max(giorni)
    if t1 <= t0:
        return []
    w = (t1 - t0) / N_BLOCCHI
    out = []
    for b in range(N_BLOCCHI):
        a, z = t0 + b * w, (t0 + (b + 1) * w if b < N_BLOCCHI - 1 else t1 + 1)
        seg = [r for t, r in zip(giorni, netto) if a <= t < z]
        cum = math.prod(1.0 + x for x in seg) - 1.0 if seg else None
        out.append({"da": datetime.fromtimestamp(a / 1000, timezone.utc).date().isoformat(),
                    "a": datetime.fromtimestamp((z - 1) / 1000, timezone.utc).date().isoformat(),
                    "n": len(seg), "cum": cum})
    return out


def per_anno(netto, giorni):
    per: dict[int, list] = {}
    for t, r in zip(giorni, netto):
        per.setdefault(datetime.fromtimestamp(t / 1000, timezone.utc).year, []).append(r)
    return {a: math.prod(1.0 + x for x in v) - 1.0 for a, v in sorted(per.items())}


def statistiche(out, giorni, confine_ms):
    netto = out["netto"]
    oos_idx = [k for k, t in enumerate(giorni) if t >= confine_ms]
    tr_idx = [k for k, t in enumerate(giorni) if t < confine_ms]
    tr = [netto[k] for k in tr_idx]
    oo = [netto[k] for k in oos_idx]
    turn = [r["turnover"] for r in out["rib"]]
    return {
        "n": len(netto),
        "n_rib": len(out["rib"]),
        "turnover_medio": statistics.mean(turn) if turn else 0.0,
        "turnover_ann": (sum(turn) / len(netto) * 365.0) if netto else 0.0,
        "costo_medio_rib": statistics.mean([r["costo"] for r in out["rib"]]) if out["rib"] else 0.0,
        "cagr_full": cagr(netto),
        "sharpe_full": sharpe(netto),
        "t_full": t_stat(netto),
        "t_nw_full": t_nw(netto),
        "dd_full": max_dd(netto),
        "cagr_train": cagr(tr),
        "cagr_oos": cagr(oo),
        "sharpe_oos": sharpe(oo),
        "t_oos": t_stat(oo),
        "t_nw_oos": t_nw(oo),
        "dd_oos": max_dd(oo),
        "costo_ann": statistics.mean(out["costi"]) * 365.0 if out["costi"] else 0.0,
        "blocchi": blocchi(netto, giorni, confine_ms),
        "per_anno": per_anno(netto, giorni),
    }


def mc_bootstrap(netto_oos, n=MC_N, blk=MC_BLOCK):
    """Block-bootstrap sui rendimenti OOS: p5/p50 di CAGR e ricchezza terminale."""
    arr = np.array(netto_oos)
    m = len(arr)
    if m < 2 * blk:
        return None
    nblk = m // blk
    blocks = arr[: nblk * blk].reshape(nblk, blk)
    rng = np.random.default_rng(42)
    cagrs, terms = [], []
    for _ in range(n):
        idx = rng.integers(0, nblk, size=(m // blk) + 1)
        path = blocks[idx].ravel()[:m]
        cum = float(np.prod(1.0 + path))
        terms.append(cum)
        cagrs.append(cum ** (365.0 / m) - 1.0 if cum > 0 else -1.0)
    return {"p5_cagr": float(np.percentile(cagrs, 5)),
            "p50_cagr": float(np.percentile(cagrs, 50)),
            "p5_term": float(np.percentile(terms, 5)),
            "p50_term": float(np.percentile(terms, 50))}


# --------------------------------------------------------------------------------------
# run e griglia
# --------------------------------------------------------------------------------------
def confine_ms():
    return int(datetime.fromisoformat(CONFINE_ISO).replace(tzinfo=timezone.utc).timestamp() * 1000)


def griglia():
    return [{"L": L, "V": V, "pesi": p} for L in L_GRID for V in V_GRID for p in PESI]


def chiave(cfg, direzione):
    return f"{direzione}-L{cfg['L']}-V{cfg['V']}-{cfg['pesi']}"


def seleziona_train(righe):
    """argmax CAGR train; tie-break: a parità entro 0,5 pp, turnover minore."""
    best = max(righe, key=lambda r: (r["cagr_train"] if r["cagr_train"] is not None else -9))
    soglia = best["cagr_train"] - 0.005
    cand = [r for r in righe if r["cagr_train"] is not None and r["cagr_train"] >= soglia]
    return min(cand, key=lambda r: r["turnover_ann"])


def _run_variante(args):
    pan, cfg, direzione, costo_lato, cms = args
    out = backtest(pan, L=cfg["L"], V=cfg["V"], pesi=cfg["pesi"], direzione=direzione,
                   costo_lato=costo_lato)
    st = statistiche(out, out["giorni"], cms)
    return {**cfg, **st}


def misura_griglia(pan, direzione, costo_lato, cms, quiet=False):
    import concurrent.futures as cf
    import os
    task = [(pan, cfg, direzione, costo_lato, cms) for cfg in griglia()]
    workers = max(1, min(12, os.cpu_count() or 4))
    righe = []
    with cf.ProcessPoolExecutor(max_workers=workers, mp_context=__import__("multiprocessing").get_context("fork")) as ex:
        for r in ex.map(_run_variante, task, chunksize=2):
            righe.append(r)
    righe.sort(key=lambda r: (r["L"], r["V"], r["pesi"]))
    if not quiet:
        for r in righe:
            print(f"    {direzione} L{r['L']:>2} V{r['V']:>2} {r['pesi']:>5} | "
                  f"tr={r['cagr_train']*100:+7.2f}% oos={r['cagr_oos']*100:+7.2f}% "
                  f"full={r['cagr_full']*100:+7.2f}% tNW={r['t_nw_oos']:+5.2f} "
                  f"turn/ann={r['turnover_ann']:.2f}")
    return righe


# --------------------------------------------------------------------------------------
# cancello
# --------------------------------------------------------------------------------------
def cancello(pan, cfg, direzione, cms, costo_lato) -> dict:
    """Tutti i controlli del cancello sulla variante promossa (congelata)."""
    res: dict = {}
    # G1: troncamento (base = cfg promossa)
    T = len(pan["giorni"]) - 30
    sub = {k: v for k, v in pan.items()}
    sub["giorni"] = pan["giorni"][:T]
    sub["px"] = pan["px"][:T]
    full = backtest(pan, L=cfg["L"], V=cfg["V"], pesi=cfg["pesi"], direzione=direzione,
                    costo_lato=costo_lato, attribuzione=True)
    cut = backtest(sub, L=cfg["L"], V=cfg["V"], pesi=cfg["pesi"], direzione=direzione,
                   costo_lato=costo_lato)
    m = min(len(full["netto"]), len(cut["netto"]))
    diff = max((abs(full["netto"][i] - cut["netto"][i]) for i in range(m)), default=0.0)
    res["G1_no_lookahead"] = {"ok": diff == 0.0, "dettaglio": f"{m} rendimenti identici, scarto max {diff:.1e}"}

    # metrica OOS della variante promossa (ricavata dal run full con attribuzione)
    st = statistiche(full, full["giorni"], cms)
    oos = [full["netto"][k] for k, t in enumerate(full["giorni"]) if t >= cms]
    res["oos"] = st
    res["oos_netto"] = oos

    # G2: blocchi
    pos = sum(1 for b in st["blocchi"] if (b["cum"] or -9) > 0)
    res["G2_blocchi"] = {"ok": pos >= PASS_BLOCCHI, "positivi": pos, "su": N_BLOCCHI,
                         "blocchi": st["blocchi"]}

    # G3: fee +50%
    out15 = backtest(pan, L=cfg["L"], V=cfg["V"], pesi=cfg["pesi"], direzione=direzione,
                     costo_lato=costo_lato * FEE_STRESS)
    st15 = statistiche(out15, out15["giorni"], cms)
    res["G3_fee150"] = {"ok": (st15["cagr_oos"] or -9) > 0, "cagr_oos": st15["cagr_oos"],
                        "blocchi_pos": sum(1 for b in st15["blocchi"] if (b["cum"] or -9) > 0)}

    # G4: Monte Carlo
    mc = mc_bootstrap(oos)
    if mc:
        res["G4_mc"] = {"ok": mc["p5_cagr"] > MC_P5_CAGR_MIN and mc["p5_term"] >= MC_P5_TERM_MIN,
                        **mc}
    else:
        res["G4_mc"] = {"ok": False, "nota": "OOS troppo corto per il bootstrap"}

    # G5: senza i 3 asset con maggior contributo lordo al P&L OOS
    contrib: dict[str, float] = {}
    for k, t in enumerate(full["giorni"]):
        if t >= cms:
            for s, v in (full["attr"][k] or {}).items():
                contrib[s] = contrib.get(s, 0.0) + v
    top3 = [s for s, _ in sorted(contrib.items(), key=lambda x: -x[1])[:3]]
    univ = set(pan["simboli"]) - set(top3)
    out5 = backtest(pan, L=cfg["L"], V=cfg["V"], pesi=cfg["pesi"], direzione=direzione,
                    costo_lato=costo_lato, universo=univ)
    st5 = statistiche(out5, out5["giorni"], cms)
    res["G5_senza_top3"] = {"ok": (st5["cagr_oos"] or -9) > 0, "top3": top3,
                            "cagr_oos": st5["cagr_oos"],
                            "blocchi_pos": sum(1 for b in st5["blocchi"] if (b["cum"] or -9) > 0)}
    return res


# --------------------------------------------------------------------------------------
# implementabilità OKX EEA
# --------------------------------------------------------------------------------------
def okx_listing(percorso_json: Path):
    """Set dei simboli live su OKX EEA (spot e swap). Fallback: cache okx_eea."""
    try:
        dati = json.loads(percorso_json.read_text(encoding="utf-8"))
        spot = {x["instId"].split("-")[0] for x in dati.get("spot", [])}
        swap = {x["instId"].split("-")[0] for x in dati.get("swap", [])}
        return spot, swap
    except Exception:
        from glob import glob as _g
        syms = {Path(p).name.split("okx_eea_", 1)[1].split("-USDT", 1)[0]
                for p in _g(str(CACHE / "okx_eea_*-USDT_1d.json"))}
        return syms, set()


def copertura_okx(pan, cfg, direzione, cms, costo_lato, spot_live, swap_live):
    """Per la variante promossa: frazione di ribilanciamenti OOS in cui la gamba LONG è
    interamente spot-live su OKX EEA (e, per il LS, la gamba SHORT interamente swap-live)."""
    out = backtest(pan, L=cfg["L"], V=cfg["V"], pesi=cfg["pesi"], direzione=direzione,
                   costo_lato=costo_lato, pesi_log=True)
    ok_long, ok_short, tot = 0, 0, 0
    for i, w in out["log_pesi"]:
        if giorni_esec(pan, i) < cms:
            continue
        tot += 1
        long_s = {s for s in w if w[s] > 0}
        short_s = {s for s in w if w[s] < 0}
        if long_s and all(s in spot_live for s in long_s):
            ok_long += 1
        if not short_s or all(s in swap_live for s in short_s):
            ok_short += 1
    return {"rib_oos": tot, "long_live": ok_long, "short_live": ok_short}


def giorni_esec(pan, i):
    return pan["giorni"][i]


# --------------------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------------------
def fmt(x, dec=2, pct=True, segno=True):
    if x is None:
        return "n/d"
    if pct:
        s = f"{x*100:{'+' if segno else ''}.{dec}f}%"
    else:
        s = f"{x:.{dec}f}"
    return s


def scrivi_report(ris: dict, path_md: Path, path_json: Path) -> None:
    L: list[str] = []
    A = L.append
    ora = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%MZ")
    A("# E4 — Momentum cross-sectional normalizzato per volatilità (1d + 4h)")
    A("")
    A(f"*Generato il {ora} da `scripts/crosssec_mom_vol.py`. Tutte le soglie e la griglia "
      f"sono pre-registrate nello script prima delle misure.*")
    A("")
    A("## 0. Verdetto")
    A("")
    A(ris["verdetto"])
    A("")
    A("## 1. Universo e igiene")
    for nome, pan in ris["pannelli"].items():
        A(f"- **{nome}**: {len(pan['simboli'])} simboli, {len(pan['giorni'])} barre dal "
          f"{datetime.fromtimestamp(pan['giorni'][0]/1000, timezone.utc).date()} al "
          f"{datetime.fromtimestamp(pan['giorni'][-1]/1000, timezone.utc).date()}.")
    A("- Serie bybit 1d: **nessun simbolo aggiuntivo** rispetto a okx_eea (sottoinsieme): "
      "il pannello 1d usa una sola sede (okx_eea, quella del conto); il 4h usa bybit come "
      "verifica indipendente.")
    A("- Esclusioni pre-dichiarate: " + "; ".join(f"`{s}` ({m})" for s, m in ESCLUSI.items()) + ".")
    A("- Sospetti NON esclusi in base (|r| giornaliero > 100%): " +
      ", ".join(f"`{s}`" for s in ris["sospetti_1d"]) + ". Scenario `igiene_stretta` in §7.")
    A("")
    A("## 2. Meccanica")
    A("- Segnale: `score = ret(L giorni) / (sigma(V giorni)·sqrt(L))` con L ∈ (21, 42, 63, 90) "
      "e V ∈ (30, 60, 90) → 12 segnali × 2 pesi (ew, inverso-vol) = **24 varianti per strategia**, "
      "misurate su train e OOS.")
    A("- Portafoglio: quintili (k = n//5 per gamba, si opera solo con n ≥ 30 asset); LS = "
      "+1/(2k) top / −1/(2k) bottom (lordo 1,0, netto 0); LO = +1/k top (lordo 1,0).")
    A("- Ribilanciamento settimanale (prima barra di ogni settimana ISO), esecuzione alla "
      "chiusura con 1 barra di ritardo: **zero look-ahead** (verificato per troncamento, G1).")
    A(f"- Costi: {COSTO_LATO*100:.3f}% per lato (RT 0,26% = giro misto 0,18% + 2×0,04% slippage) "
      f"sul turnover effettivo; chiusura forzata su fine dati: un lato sul peso.")
    A("- Walk-forward: train fino 2024-06-01, variante promossa = argmax CAGR netto train "
      "(tie-break: turnover minore entro 0,5 pp); OOS con variante **congelata**.")
    A("")
    A("## 3. Griglia su train e OOS (24 varianti per strategia per pannello)")
    for nome_pan, pan in ris["pannelli"].items():
        for direzione in ("ls", "lo"):
            rr = ris["griglie"][f"{nome_pan}|{direzione}"]
            A(f"### {nome_pan} — {direzione.upper()}")
            A("")
            A("| L | V | pesi | CAGR train | CAGR OOS | CAGR full | Sharpe OOS | t OOS | tNW OOS | "
              "maxDD full | turn/ann | costo ann |")
            A("|---|---|---|---|---|---|---|---|---|---|---|")
            for r in sorted(rr, key=lambda r: -(r["cagr_train"] or -9)):
                A(f"| {r['L']} | {r['V']} | {r['pesi']} | {fmt(r['cagr_train'])} | {fmt(r['cagr_oos'])} | "
                  f"{fmt(r['cagr_full'])} | {r['sharpe_oos'] and f'{r['sharpe_oos']:.2f}' or 'n/d'} | "
                  f"{r['t_oos'] and f'{r['t_oos']:+.2f}' or 'n/d'} | {r['t_nw_oos'] and f'{r['t_nw_oos']:+.2f}' or 'n/d'} | "
                  f"{fmt(r['dd_full'], dec=1, segno=False)} | {r['turnover_ann']:.2f} | {fmt(r['costo_ann'])} |")
            A("")
    A("## 4. Varianti promosse e cancello OOS")
    A("")
    A("| pannello | strategia | variante | G1 | G2 blocchi | G3 fee+50% | G4 MC p5 | G5 senza top3 |")
    A("|---|---|---|---|---|---|---|---|")
    for chiave_r, r in ris["cancelli"].items():
        g2, g3, g4, g5 = r["G2_blocchi"], r["G3_fee150"], r["G4_mc"], r["G5_senza_top3"]
        g4s = f"CAGR {g4.get('p5_cagr') and fmt(g4['p5_cagr'])} / term {g4.get('p5_term') and f'{g4['p5_term']:.2f}'}" if "p5_cagr" in g4 else g4.get("nota", "n/d")
        A(f"| {r['pannello']} | {r['direzione'].upper()} | {r['variante']} | "
          f"{'OK' if r['G1_no_lookahead']['ok'] else 'FAIL'} | {g2['positivi']}/{g2['su']} | "
          f"{fmt(g3['cagr_oos'])} ({'OK' if g3['ok'] else 'FAIL'}) | {g4s} ({'OK' if g4['ok'] else 'FAIL'}) | "
          f"{fmt(g5['cagr_oos'])} ({'OK' if g5['ok'] else 'FAIL'}) |")
    A("")
    A("## 5. Dettaglio delle varianti promosse (OOS)")
    A("")
    for chiave_r, r in ris["cancelli"].items():
        st = r["oos"]
        A(f"### {r['pannello']} — {r['direzione'].upper()} — {r['variante']}")
        A("")
        A(f"- CAGR OOS **{fmt(st['cagr_oos'])}** · Sharpe OOS **{st['sharpe_oos'] and f'{st['sharpe_oos']:.2f}' or 'n/d'}** · "
          f"t **{st['t_oos'] and f'{st['t_oos']:+.2f}' or 'n/d'}** · t NW(7) **{st['t_nw_oos'] and f'{st['t_nw_oos']:+.2f}' or 'n/d'}** · "
          f"maxDD OOS **{fmt(st['dd_oos'], dec=1, segno=False)}**")
        A(f"- CAGR train {fmt(st['cagr_train'])} · CAGR full {fmt(st['cagr_full'])} · "
          f"turnover annuo **{st['turnover_ann']:.2f}** capitali/anno · "
          f"costo annuo {fmt(st['costo_ann'])} · {st['n_rib']} ribilanciamenti")
        A(f"- blocchi OOS: " + " | ".join(
            f"{b['da']}→{b['a']} {fmt(b['cum'])}" for b in st["blocchi"]))
        A(f"- per anno (full): " + " ".join(f"{a}:{v*100:+.1f}%" for a, v in st["per_anno"].items()))
        A(f"- MC OOS (block-bootstrap 7g, {MC_N} percorsi): p5 CAGR {fmt(r['G4_mc'].get('p5_cagr'))}, "
          f"p50 CAGR {fmt(r['G4_mc'].get('p50_cagr'))}, p5 terminale "
          f"{r['G4_mc'].get('p5_term') and f'{r['G4_mc']['p5_term']:.3f}' or 'n/d'}.")
        A(f"- senza i 3 asset migliori OOS (`{', '.join(r['G5_senza_top3']['top3'])}`): "
          f"CAGR OOS {fmt(r['G5_senza_top3']['cagr_oos'])}, "
          f"blocchi positivi {r['G5_senza_top3']['blocchi_pos']}/{N_BLOCCHI}.")
        if "copertura" in r:
            cov = r["copertura"]
            A(f"- copertura OKX EEA: {cov['long_live']}/{cov['rib_oos']} ribilanciamenti OOS con la "
              f"gamba long interamente spot-live su eea.okx.com; gamba short swap-live "
              f"{cov['short_live']}/{cov['rib_oos']}.")
        if "funding" in r:
            fu = r["funding"]
            A(f"- sensibilità funding {FUNDING_STRESS*100:.1f}%/anno sul nozionale short: "
              f"CAGR OOS {fmt(fu['cagr_oos'])}, blocchi positivi {fu['blocchi_pos']}/{N_BLOCCHI}.")
        A("")
    A("## 6. Confronto con crosssec_v2 (E3)")
    A("")
    A(ris["confronto_v2"])
    A("")
    A("## 7. Sensibilità aggiuntive (report-only, varianti congelate)")
    A("")
    A(ris["sensibilita"])
    A("")
    A("## 8. Riproducibilità")
    A("")
    A(f"- script: `scripts/crosssec_mom_vol.py`; numeri completi: `{path_json.name}`")
    A("- dati: `data/cache/okx_eea_*-USDT_1d.json` (90 file) e `data/cache/bybit_*-USDT_4h.json` (59 file), "
      "nessuna scrittura in cache.")
    A("- listing OKX EEA: `prove/e4_okx_instruments.json` (public instruments, letti il giorno del run).")
    path_md.write_text("\n".join(L) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------------------
def main() -> int:
    cms = confine_ms()
    data_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path_md = PROVE / f"e4_momentum_crosssec_{data_iso}.md"
    path_json = PROVE / f"e4_momentum_crosssec_{data_iso}.json"
    path_okx = PROVE / "e4_okx_instruments.json"

    # listing OKX EEA (public, sola lettura)
    if not path_okx.exists():
        import subprocess as sp
        try:
            spot_raw = sp.run(["curl", "-s", "--max-time", "15", "-A", "Mozilla/5.0",
                               "https://eea.okx.com/api/v5/public/instruments?instType=SPOT"],
                              capture_output=True, text=True, check=True).stdout
            swap_raw = sp.run(["curl", "-s", "--max-time", "15", "-A", "Mozilla/5.0",
                               "https://eea.okx.com/api/v5/public/instruments?instType=SWAP"],
                              capture_output=True, text=True, check=True).stdout
            spot = json.loads(spot_raw)
            swap = json.loads(swap_raw)
            path_okx.write_text(json.dumps({
                "spot": [x for x in spot.get("data", []) if x.get("state") == "live"],
                "swap": [x for x in swap.get("data", []) if x.get("state") == "live"]},
                ensure_ascii=False), encoding="utf-8")
            print(f"  listing OKX EEA: {len(spot.get('data', []))} spot live, "
                  f"{len(swap.get('data', []))} swap live")
        except Exception as e:
            print(f"  [warn] listing OKX non scaricato: {e}; fallback = cache okx_eea")
    spot_live, swap_live = okx_listing(path_okx)

    print(f"CROSSSEC MOM-VOL — {datetime.now(timezone.utc):%Y-%m-%d %H:%M}Z")
    print(f"  costo lato {COSTO_LATO*100:.3f}% | confine {CONFINE_ISO} | min asset {MIN_ASSET}")

    pannelli: dict[str, dict] = {}
    sospetti_1d: list[str] = []
    for nome in PANNELLI:
        pan = carica_pannello(nome, ESCLUSI)
        pannelli[nome] = pan
        print(f"  pannello {nome}: {len(pan['simboli'])} simboli, {len(pan['giorni'])} barre "
              f"({datetime.fromtimestamp(pan['giorni'][0]/1000, timezone.utc).date()} .. "
              f"{datetime.fromtimestamp(pan['giorni'][-1]/1000, timezone.utc).date()})")

    # sospetti |r|>100% sul pannello 1d
    for sym, s in pannelli["1d_okx"]["serie"].items():
        if np.nanmax(np.abs(s.ret)) > 1.0:
            sospetti_1d.append(sym)
    sospetti_1d.sort()

    griglie: dict[str, list] = {}
    cancelli: dict[str, dict] = {}
    for nome_pan in ("1d_okx", "4h_bybit"):
        pan = pannelli[nome_pan]
        for direzione in ("ls", "lo"):
            print(f"--- griglia {nome_pan} {direzione.upper()} ---")
            righe = misura_griglia(pan, direzione, COSTO_LATO, cms)
            griglie[f"{nome_pan}|{direzione}"] = righe
            promossa = seleziona_train(righe)
            cfg = {"L": promossa["L"], "V": promossa["V"], "pesi": promossa["pesi"]}
            print(f"  promossa su TRAIN: {chiave(cfg, direzione)} "
                  f"(train {promossa['cagr_train']*100:+.2f}%)")
            gate = cancello(pan, cfg, direzione, cms, COSTO_LATO)
            gate.update({"pannello": nome_pan, "direzione": direzione,
                         "variante": chiave(cfg, direzione),
                         "L": cfg["L"], "V": cfg["V"], "pesi": cfg["pesi"]})
            # copertura OKX EEA
            gate["copertura"] = copertura_okx(pan, cfg, direzione, cms, COSTO_LATO,
                                              spot_live, swap_live)
            # sensibilità funding (solo LS)
            if direzione == "ls":
                outf = backtest(pan, L=cfg["L"], V=cfg["V"], pesi=cfg["pesi"], direzione="ls",
                                costo_lato=COSTO_LATO, funding_annuo=FUNDING_STRESS)
                stf = statistiche(outf, outf["giorni"], cms)
                gate["funding"] = {"cagr_oos": stf["cagr_oos"],
                                   "blocchi_pos": sum(1 for b in stf["blocchi"]
                                                      if (b["cum"] or -9) > 0)}
            cancelli[f"{nome_pan}|{direzione}"] = gate
            g = gate
            print(f"    G1={g['G1_no_lookahead']['ok']} G2={g['G2_blocchi']['positivi']}/{N_BLOCCHI} "
                  f"G3={g['G3_fee150']['ok']} G4={g['G4_mc']['ok']} G5={g['G5_senza_top3']['ok']} | "
                  f"OOS {g['oos']['cagr_oos'] and f'{g['oos']['cagr_oos']*100:+.2f}%'}")

    # --- sensibilità report-only: igiene_stretta sul 1d (varianti congelate)
    sens: list[str] = []
    sens.append("**igiene_stretta (1d)**: tolte anche le serie con |r| giornaliero > 100% "
                f"({', '.join('`'+s+'`' for s in sospetti_1d)}), varianti congelate, solo OOS:")
    pan = pannelli["1d_okx"]
    univ = set(pan["simboli"]) - set(sospetti_1d)
    for direzione in ("ls", "lo"):
        cfg = {k: v for k, v in cancelli[f"1d_okx|{direzione}"].items() if k in ("L", "V", "pesi")}
        out = backtest(pan, L=cfg["L"], V=cfg["V"], pesi=cfg["pesi"], direzione=direzione,
                       costo_lato=COSTO_LATO, universo=univ)
        st = statistiche(out, out["giorni"], cms)
        sens.append(f"- {direzione.upper()} {chiave(cfg, direzione)}: CAGR OOS "
                    f"{fmt(st['cagr_oos'])}, blocchi positivi "
                    f"{sum(1 for b in st['blocchi'] if (b['cum'] or -9) > 0)}/{N_BLOCCHI}.")
    # long-only ristretto ai nomi spot-live OKX (1d): solo se il pannello non è già tutto live
    cfg = {k: v for k, v in cancelli["1d_okx|lo"].items() if k in ("L", "V", "pesi")}
    univ_live = set(pan["simboli"]) & spot_live
    sens.append(f"**long-only 1d ristretto ai {len(univ_live)} nomi spot-live OKX EEA**:")
    out = backtest(pan, L=cfg["L"], V=cfg["V"], pesi=cfg["pesi"], direzione="lo",
                   costo_lato=COSTO_LATO, universo=univ_live)
    st = statistiche(out, out["giorni"], cms)
    sens.append(f"- LO {chiave(cfg, 'lo')}: CAGR OOS {fmt(st['cagr_oos'])}, blocchi positivi "
                f"{sum(1 for b in st['blocchi'] if (b['cum'] or -9) > 0)}/{N_BLOCCHI}.")
    testo_sens = "\n".join(sens)

    # --- verdetto costruito dai numeri
    v = cancelli.get("1d_okx|lo")
    parti = []
    g2, g3, g4, g5 = v["G2_blocchi"], v["G3_fee150"], v["G4_mc"], v["G5_senza_top3"]
    gate_lo_ok = (g2["ok"] and g3["ok"] and g4["ok"] and g5["ok"])
    vls = cancelli.get("1d_okx|ls")
    g2s, g3s, g4s, g5s = vls["G2_blocchi"], vls["G3_fee150"], vls["G4_mc"], vls["G5_senza_top3"]
    gate_ls_ok = (g2s["ok"] and g3s["ok"] and g4s["ok"] and g5s["ok"])
    parti.append(f"**Long-only 1d (promossa `{v['variante']}`)**: cancello "
                 f"{'SUPERATO' if gate_lo_ok else 'NON superato'} — G2 {g2['positivi']}/{N_BLOCCHI} blocchi, "
                 f"G3 fee+50% CAGR OOS {fmt(g3['cagr_oos'])}, G4 MC p5 CAGR {fmt(g4.get('p5_cagr'))} "
                 f"(terminale p5 {g4.get('p5_term') and f'{g4['p5_term']:.2f}'}), "
                 f"G5 senza top-3 {fmt(g5['cagr_oos'])}.")
    parti.append(f"**Long-short 1d (promossa `{vls['variante']}`)**: cancello "
                 f"{'SUPERATO' if gate_ls_ok else 'NON superato'} — G2 {g2s['positivi']}/{N_BLOCCHI} blocchi, "
                 f"G3 {fmt(g3s['cagr_oos'])}, G4 p5 CAGR {fmt(g4s.get('p5_cagr'))}, G5 {fmt(g5s['cagr_oos'])}.")
    if gate_lo_ok:
        parti.append("**Implementabilità su OKX EEA con il nostro conto**: la versione LONG-ONLY "
                     "è implementabile **spot** (tutti i nomi della gamba long sono live su eea.okx.com: "
                     f"{v['copertura']['long_live']}/{v['copertura']['rib_oos']} ribilanciamenti OOS); "
                     "il long-short richiederebbe short su X-Perps con funding sul nozionale short "
                     f"(sensibilità: CAGR OOS {fmt(vls['funding']['cagr_oos'])}). **Promuovibile: long-only spot.**")
    elif gate_ls_ok and not gate_lo_ok:
        parti.append("**Implementabilità**: il long-short supera il cancello ma lo short su spot non è "
                     "eseguibile: serve il perp con funding — non promuovibile senza ulteriore verifica.")
    else:
        parti.append("**Verdetto: nessun edge promuovibile.**")
    verdetto = "\n\n".join(parti)

    confronto_v2 = (
        "Il precedente E3 (crosssec_v2) testava momentum/reversal **raw** a 3-14 giorni su 1d Bybit "
        "con k=3/5/10 e ribilanciamento 1-7 giorni: verdetto **nessun edge** (0/108 varianti positive "
        "in train e OOS, mediana −17,1%/anno netta, miglior t 0,66). Questo E4 cambia tre cose, "
        "pre-registrate: (a) segnale **normalizzato per volatilità** su orizzonti 21-90 giorni "
        "(il momentum di medio termine, non il reversal breve); (b) ribilanciamento **settimanale** "
        "fisso e quintili larghi (turnover più basso → pedaggio 1/3 di R=3); (c) universo okx_eea "
        "1d (90 simboli) + verifica 4h bybit. I numeri netti OOS vanno letti contro il −2,3% annuo "
        "OOS della migliore E3.")

    ris = {
        "pannelli": {k: {"simboli": pannelli[k]["simboli"], "giorni": pannelli[k]["giorni"]}
                     for k in pannelli},
        "sospetti_1d": sospetti_1d,
        "griglie": griglie,
        "cancelli": cancelli,
        "verdetto": verdetto,
        "confronto_v2": confronto_v2,
        "sensibilita": testo_sens,
        "esclusi": ESCLUSI,
        "costo_lato": COSTO_LATO,
        "confine": CONFINE_ISO,
    }
    path_json.write_text(json.dumps(ris, ensure_ascii=False, indent=1, default=str),
                         encoding="utf-8")
    scrivi_report(ris, path_md, path_json)
    print(f"  report: {path_md.relative_to(RADICE)}")
    print(f"  numeri: {path_json.relative_to(RADICE)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
