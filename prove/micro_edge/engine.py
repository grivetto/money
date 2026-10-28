#!/usr/bin/env python3
"""Motore backtest microstruttura 5-min (numpy).

Convenzioni (no lookahead):
- segnale calcolato con dati fino alla CHIUSURA della barra i
- entry: OPEN della barra i+1, market (taker) + slippage
- uscita: OPEN della barra i+1+H  (H barre di esposizione)
- costi: fee taker 0.10%/lato + slippage 0.04%/lato = 0.14%/lato (0.28% RT)
  variante maker: fee 0.08% + slip 0.04% = 0.12%/lato
- una posizione alla volta (niente overlap), dimensione 1x notional
"""
import numpy as np

FEE_TAKER = 0.0010   # OKX EEA spot taker 10bp
FEE_MAKER = 0.0008   # OKX EEA spot maker 8bp
SLIP = 0.0004        # slippage per lato (conservativo su barre 5m)

def ewma_vol(r, halflife=96):
    """EWMA del valore assoluto dei ritorni (halflife in barre, default 8h)."""
    alpha = 1 - np.exp(np.log(0.5) / halflife)
    out = np.empty_like(r)
    out[0] = np.abs(r[:288]).mean() if len(r) > 288 else np.abs(r).mean()
    for i in range(1, len(r)):
        out[i] = (1 - alpha) * out[i - 1] + alpha * np.abs(r[i])
    return out

def rolling_mean_std(x, w):
    """media e std mobili (finestra w) via cumsum."""
    cs = np.concatenate(([0.0], np.cumsum(x)))
    cs2 = np.concatenate(([0.0], np.cumsum(x * x)))
    m = (cs[w:] - cs[:-w]) / w
    var = (cs2[w:] - cs2[:-w]) / w - m * m
    var = np.clip(var, 1e-30, None)
    return m, np.sqrt(var)

def features(d):
    """Ritorna dict di feature causali per barra i (indice su close di i)."""
    c, h, l, v, o = d["close"], d["high"], d["low"], d["volume"], d["open"]
    n = len(c)
    r = np.zeros(n); r[1:] = np.diff(np.log(c))
    vol = ewma_vol(r)
    z = np.where(vol > 1e-9, r / vol, 0.0)
    # clv = posizione della chiusura nel range
    rng = (h - l)
    clv = np.where(rng > 0, 2.0 * (c - l) / rng - 1.0, 0.0)
    vm, vs = rolling_mean_std(v, 288)
    vpad = np.concatenate([np.full(n - len(vm), vm[0]), vm])
    vspad = np.concatenate([np.full(n - len(vs), vs[0]), vs])
    vz = np.where(vspad > 1e-9, (v - vpad) / vspad, 0.0)
    return {"r": r, "vol": vol, "z": z, "clv": clv, "vz": vz, "n": n}

def run_backtest(d, target, H, cost_side, i0=0, i1=None, max_gap_s=900):
    """target: array di posizione obiettivo (causale a chiusura barra).
    Ritorna trade log-return netti, dirs, indici entry/exit."""
    if i1 is None:
        i1 = d["n"] if "n" in d else len(d["open"])
    o, ts = d["open"], d["ts"]
    n = len(o)
    trades = []
    next_ok = i0  # prima barra in cui posso entrare
    i = i0
    while i < i1 - H - 1:
        tgt = target[i]
        if tgt != 0 and i >= next_ok:
            ie, ix = i + 1, i + 1 + H
            if ix >= n or ix >= i1 + H + 1:
                break
            # salta se c'e' un buco temporale tra close(i) e open(i+1) o dentro l'hold
            if ts[ie] - ts[i] > max_gap_s or ts[ix] - ts[ix - 1] > max_gap_s:
                next_ok = ie
                i += 1
                continue
            ret = tgt * (np.log(o[ix]) - np.log(o[ie])) - 2 * cost_side
            trades.append((ie, ix, tgt, ret))
            next_ok = ix
            i = ix
        else:
            i += 1
    if not trades:
        return np.array([]), np.array([]), np.array([]), np.array([])
    A = np.array(trades)
    return A[:, 0].astype(int), A[:, 1].astype(int), A[:, 2], A[:, 3]

def metrics(pnl, entries_ts=None):
    """Statistiche sui trade. Se entries_ts (ts epoch s per trade) fornito,
    Sharpe annualizzato dal PnL giornaliero."""
    out = dict(n=len(pnl))
    if len(pnl) == 0:
        return dict(n=0, total=0.0, sharpe=0.0, tstat=0.0, winrate=0.0,
                    mean=0.0, maxdd=0.0, profit_factor=0.0, daily_sharpe=0.0)
    m, s = pnl.mean(), pnl.std(ddof=1)
    tstat = m / s * np.sqrt(len(pnl)) if s > 0 else 0.0
    wins = pnl[pnl > 0]; losses = pnl[pnl < 0]
    pf = wins.sum() / abs(losses.sum()) if len(losses) and losses.sum() != 0 else float("inf")
    cum = np.cumsum(pnl)
    peak = np.maximum.accumulate(np.concatenate([[0.0], cum]))
    maxdd = (peak[1:] - cum).max()
    out.update(n=len(pnl), total=pnl.sum(), tstat=tstat,
               winrate=(pnl > 0).mean(), mean=m, maxdd=maxdd, profit_factor=pf)
    if entries_ts is not None:
        days = {}
        for e, p in zip(entries_ts, pnl):
            d = int(e // 86400)
            days[d] = days.get(d, 0.0) + p
        dv = np.array(list(days.values()))
        # riempie i giorni senza trade con 0
        all_days = np.arange(int(min(entries_ts) // 86400), int(max(entries_ts) // 86400) + 1)
        full = np.array([days.get(d, 0.0) for d in all_days])
        out["daily_sharpe"] = full.mean() / full.std(ddof=1) * np.sqrt(365) if full.std(ddof=1) > 0 else 0.0
        out["daily_pnl"] = {int(d): days.get(d, 0.0) for d in all_days}
        out["n_days"] = len(all_days)
    return out

def daily_pnl_from_trades(entries, pnl, ts, d0, d1):
    """Aggrega i PnL dei trade per giorno UTC (per MC bootstrap)."""
    days = {}
    for e, p in zip(entries, pnl):
        day = int(ts[e] // 86400)
        days[day] = days.get(day, 0.0) + p
    return days

def montecarlo(daily_pnl, n_sims=5000, block_days=10, seed=42):
    """Block bootstrap del PnL giornaliero; ritorna p5 del totale e p5 del maxDD."""
    days = sorted(daily_pnl)
    vals = np.array([daily_pnl[d] for d in days])
    rng = np.random.default_rng(seed)
    n = len(vals)
    nblocks = int(np.ceil(n / block_days))
    tots = np.empty(n_sims); mdd = np.empty(n_sims)
    for k in range(n_sims):
        starts = rng.integers(0, n, size=nblocks)
        path = []
        for st in starts:
            path.append(vals[st: min(st + block_days, n)])
        p = np.concatenate(path)[:n]
        cum = np.cumsum(p)
        tots[k] = p.sum()
        peak = np.maximum.accumulate(np.concatenate([[0.0], cum]))
        mdd[k] = (peak[1:] - cum).max()
    return np.percentile(tots, 5), np.percentile(mdd, 5), tots.mean(), mdd.mean()
