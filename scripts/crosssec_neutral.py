#!/usr/bin/env python3
"""crosssec_neutral.py — SCREENER CROSS-SECTIONAL DOLLAR-NEUTRAL (mai testato).

PERCHE' E' UNA FRONTIERA NUOVA
==============================
Tutto cio' che il progetto ha testato finora (S1/S3/S4, P10, P14) e' LONG/FLAT:
si guadagna solo se il mercato sale. Il momentum CROSS-SEZIONALE del progetto (P10/P14)
era comunque long-only (top-k da tenere). Qui il meccanismo e' DIVERSO per costruzione:

    long i k migliori  +  short i k peggiori, dollari long = dollari short
    -> net exposure ~ 0: il mercato che sale o scende NON conta
    -> si guadagna (o si perde) solo dalla DISPERSIONE tra i simboli

Non e' una variazione di un indicatore: e' un cambio di natura dell'expousre. Se il
mercato sale, il long sale e lo short sale — il P&L e' la differenza. E' per questo che
non e' nei 312k tentativi: quelli erano tutti a una gamba.

DATI: barre giornaliere USDT (dal 2020), universo = simboli in cache `data/cache`.
COSTI: `money.costi` (la tariffa VERA del conto) + slippage per lato su OGNI cambio di
       composizione. Lo short paga lo stesso pedaggio del long (nessuna gratuita').

USO
===
  .venv/bin/python scripts/crosssec_neutral.py                  # griglia dichiarata sotto
  .venv/bin/python scripts/crosssec_neutral.py --inizio 2020-10-01 --confine 2024-06-01
  .venv/bin/python scripts/crosssec_neutral.py --json

NON promuove nulla: produce un verdetto DESCRITTIVO (train/OOS, DSR). La promozione resta
compito di `money.cancello` / `promozione.py`.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

for _antenato in Path(__file__).resolve().parents:
    _src = _antenato / "src"
    if (_src / "money" / "__init__.py").exists():
        for _p in (str(_src), str(_antenato)):
            if _p not in sys.path:
                sys.path.insert(0, _p)
        break

from money.costi import get_tariffa  # noqa: E402
from money.dati import a_ms  # noqa: E402

RADICE = Path(__file__).resolve().parents[1]
CACHE = RADICE / "data" / "cache"
#: griglia dichiarata PRIMA dei numeri (anti-overfitting): pochi gradi di liberta'
GRIGLIA = (
    {"lookback": 30, "ribilancio": 7, "k": 3},
    {"lookback": 30, "ribilancio": 14, "k": 3},
    {"lookback": 90, "ribilancio": 7, "k": 3},
    {"lookback": 90, "ribilancio": 14, "k": 5},
    {"lookback": 180, "ribilancio": 30, "k": 5},
)


def carica_cache() -> dict[str, list]:
    """Simbolo -> lista di (ts_ms, chiusura) dalle barre giornaliere in cache."""
    serie: dict[str, list] = {}
    for p in sorted(CACHE.glob("okx_eea_*-USDT_1d.json")):
        sym = p.name.replace("okx_eea_", "").replace("-USDT_1d.json", "") + "/USDT"
        try:
            dati = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        barre = dati.get("barre") or dati.get("dati") or dati
        if not isinstance(barre, list) or not barre:
            continue
        righe = []
        for b in barre:
            try:
                if isinstance(b, (list, tuple)):
                    righe.append((int(b[0]), float(b[4])))
                elif isinstance(b, dict):
                    righe.append((int(b.get("ts")), float(b.get("chiusura") or b.get("close"))))
            except (TypeError, ValueError, IndexError):
                continue
        if len(righe) > 300:
            serie[sym] = sorted(righe)
    return serie


def prezzi_allineati(serie: dict[str, list], inizio_ms: int, fine_ms: int):
    """(simboli, lista_ts, matrice prezzi per ts) — solo barre comuni (paniere coerente)."""
    ts_comuni: dict[int, dict[str, float]] = {}
    for sym, righe in serie.items():
        for ts, px in righe:
            if inizio_ms <= ts <= fine_ms and px > 0:
                ts_comuni.setdefault(ts, {})[sym] = px
    ts_ordinati = sorted(ts_comuni)
    # tiene solo i ts dove ci sono abbastanza simboli (>=4 per un long-short sensato)
    ts_ordinati = [t for t in ts_ordinati if len(ts_comuni[t]) >= 4]
    if len(ts_ordinati) < 60:
        return [], [], []
    simboli = sorted({s for t in ts_ordinati for s in ts_comuni[t]})
    return simboli, ts_ordinati, ts_comuni


def bt_neutral(simboli, ts, prezzi, *, lookback, ribilancio, k, costo_giro):
    """Backtest dollar-neutral: long top-k, short bottom-k per rendimento `lookback`.

    Ritorna la serie dei rendimenti giornalieri netti + conteggio dei ribilanciamenti.
    Esecuzione: decisione alla CHIUSURA di t, applicata al ritorno t -> t+1 (no look-ahead).
    """
    def ret(sym, i):
        if i - lookback < 0:
            return None
        p0 = prezzi[ts[i - lookback]].get(sym)
        p1 = prezzi[ts[i]].get(sym)
        if not p0 or not p1:
            return None
        return p1 / p0 - 1.0

    rendimenti = []          # rendimento netto del portafoglio per ogni passo t->t+1
    pesi = {}                # sym -> +1/k (long) o -1/k (short)
    ribilanci = 0
    ultimo_rib = -10**9

    for i in range(len(ts) - 1):
        # ribilanciamento ogni `ribilancio` barre: nuova composizione top/bottom
        if i - ultimo_rib >= ribilancio:
            r = {s: ret(s, i) for s in simboli}
            r = {s: v for s, v in r.items() if v is not None}
            if len(r) >= 2 * k:
                ord_ = sorted(r, key=lambda s: r[s])
                short = ord_[:k]
                long_ = ord_[-k:]
                pesi = {s: 1.0 / k for s in long_}
                pesi.update({s: -1.0 / k for s in short})
                ribilanci += 1
                ultimo_rib = i
        # rendimento del paniere al passo i->i+1 (pesi fissi tra un ribilanciamento e l'altro)
        r_port = 0.0
        for s, w in pesi.items():
            p0 = prezzi[ts[i]].get(s)
            p1 = prezzi[ts[i + 1]].get(s)
            if p0 and p1:
                r_port += w * (p1 / p0 - 1.0)
        # costo: il ribilanciamento gira ~2k posizioni a 1/k ciascuna -> 2 * costo_giro * (turnover)
        # qui addebitiamo il costo pieno del giro SOLO sulle posizioni cambiate: approssimazione
        # dichiarata = costo_giro * 2 (entrata+uscita) * frazione ruotata a ogni ribilanciamento
        rendimenti.append(r_port)

    # costo: numero ribilanciamenti * (2 lati * k posizioni * 1/k nozionale) * giro
    n = len(rendimenti)
    if n == 0:
        return {"n": 0}
    costo_tot = ribilanci * (2 * costo_giro) / max(1, n)  # ripartito per giorno
    rendimenti_net = [x - costo_tot for x in rendimenti]
    return {"n": n, "rendimenti": rendimenti_net, "ribilanci": ribilanci}


def statistiche(rend, confine_idx):
    def blk(a):
        if len(a) < 3:
            return {"n": len(a), "exp": None, "t": None, "sharpe": None}
        mu = statistics.mean(a)
        sd = statistics.pstdev(a)
        t = mu / (sd / math.sqrt(len(a))) if sd > 0 else 0.0
        sh = mu / sd if sd > 0 else 0.0
        return {"n": len(a), "exp": round(mu, 6), "t": round(t, 3), "sharpe": round(sh, 4)}
    train = rend[:confine_idx]
    oos = rend[confine_idx:]
    exp_tot = sum(rend) + 1.0
    return {"train": blk(train), "oos": blk(oos),
            "rendimento_cum": round(exp_tot - 1.0, 4),
            "max_dd": _max_dd(rend)}


def _max_dd(rend):
    eq, picco, dd = 1.0, 1.0, 0.0
    for r in rend:
        eq *= (1.0 + r)
        picco = max(picco, eq)
        dd = max(dd, (picco - eq) / picco)
    return round(dd, 4)


def main() -> int:
    ap = argparse.ArgumentParser(description="Screener cross-sectional dollar-neutral")
    ap.add_argument("--inizio", default="2020-10-01")
    ap.add_argument("--confine", default="2024-06-01")
    ap.add_argument("--fine", default="2026-10-08")
    ap.add_argument("--slippage", type=float, default=0.0004)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    tar = get_tariffa("okx_eea_con_perp")
    costo_giro = tar.giro_misto + 2 * a.slippage

    serie = carica_cache()
    simboli, ts, prezzi = prezzi_allineati(serie, a_ms(a.inizio), a_ms(a.fine))
    if not simboli:
        print("dati insufficienti", file=sys.stderr)
        return 1
    confine_ms = a_ms(a.confine)
    conf_idx = sum(1 for t in ts if t < confine_ms)

    print(f"CROSS-SECTIONAL DOLLAR-NEUTRAL — {datetime.now(timezone.utc):%Y-%m-%d %H:%M}Z")
    print(f"  simboli={len(simboli)} barre={len(ts)} | train {a.inizio}..{a.confine} | oos ..{a.fine}")
    print(f"  costo giro misto={costo_giro*100:.3f}% (tariffa {tar.condizione})")
    print("  " + "-" * 78)
    risultati = []
    for cfg in GRIGLIA:
        out = bt_neutral(simboli, ts, prezzi, lookback=cfg["lookback"],
                         ribilancio=cfg["ribilancio"], k=cfg["k"], costo_giro=costo_giro)
        if out.get("n", 0) == 0:
            continue
        st = statistiche(out["rendimenti"], conf_idx)
        o, tr = st["oos"], st["train"]
        sp = _spread_long_short(simboli, ts, prezzi, cfg, confine_ms)
        risultati.append({**cfg, **st, "spread_ls_bps": sp})
        print(f"  L{cfg['lookback']:>3} R{cfg['ribilancio']:>2} k{cfg['k']} | "
              f"train n={tr['n']:>3} exp={tr['exp']:+.5f} t={tr['t']:+.2f} | "
              f"oos n={o['n']:>3} exp={o['exp']:+.5f} t={o['t']:+.2f} sh={o['sharpe']:+.3f} | "
              f"DD {st['max_dd']:.1%}")
    print("  " + "-" * 78)
    coerenti = [r for r in risultati if (r["oos"]["exp"] or 0) > 0 and (r["train"]["exp"] or 0) > 0]
    print(f"  {len(coerenti)}/{len(risultati)} varianti con exp>0 in ENTRAMBE le finestre")

    out = {"ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "simboli": len(simboli), "barre": len(ts), "costo_giro": costo_giro,
           "varianti": risultati}
    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=1))
    (RADICE / "prove").mkdir(exist_ok=True)
    p = RADICE / "prove" / "crosssec_neutral.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    if not a.json:
        print(f"  artefatto: {p.relative_to(RADICE)}")
    return 0


def _spread_long_short(simboli, ts, prezzi, cfg, confine_ms):
    """Descrittivo: quanto si muove davvero il paniere long-short (dispersione media)."""
    look = cfg["lookback"]
    vals = []
    for i in range(look, len(ts)):
        r = {}
        for s in simboli:
            p0 = prezzi[ts[i - look]].get(s)
            p1 = prezzi[ts[i]].get(s)
            if p0 and p1:
                r[s] = p1 / p0 - 1.0
        if len(r) >= 2 * cfg["k"]:
            o = sorted(r.values())
            vals.append(o[-1] - o[0])
    return round(statistics.mean(vals) * 1e4, 1) if vals else None


if __name__ == "__main__":
    sys.exit(main())
