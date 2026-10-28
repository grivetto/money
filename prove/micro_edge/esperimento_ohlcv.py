#!/usr/bin/env python3
"""Esperimento principale OHLCV 5-min OKX (BTC+ETH): 4 ipotesi microstruttura,
walk-forward con blocchi di verifica trimestrali, costi reali, sens. fee+50%, MC.

Ipotesi:
  H1 mean-reversion post-move estremo (z-score su EWMA vol)
  H2 autocorrelazione ritorni 1-5 min (contrarian / momentum su sign(r))
  H3 orderflow proxy OHLCV: CLV + volume z-score (continuazione)
  H4 stagionalita' oraria (drift per ora UTC, hold 5 min)
"""
import sys, json, time
import numpy as np
sys.path.insert(0, "/home/sergio/money/prove/micro_edge")
from loaders import load_ohlcv
from engine import features, run_backtest, metrics, montecarlo, FEE_TAKER, FEE_MAKER, SLIP

OUT = "/home/sergio/money/prove/micro_edge"
T0 = time.time()

def fold_bounds(ts, n_blocks=7):
    """Blocchi di verifica di ~3 mesi a partire da 2025-01-01."""
    t0 = 1735689600.0  # 2025-01-01
    t_end = ts.max()
    bounds = []
    for k in range(n_blocks):
        s = t0 + k * 90 * 86400.0
        e = min(s + 90 * 86400.0, t_end)
        if e <= s + 30 * 86400:
            continue
        bounds.append((s, e))
    return bounds

def h1_target(z, th):
    t = np.where(z > th, -1.0, 0.0)
    t = np.where(z < -th, 1.0, t)
    return t

def h2_target(r, vol, k, mode):
    # floor relativo alla vol EWMA
    t = np.zeros_like(r)
    if mode == "contrarian":
        m = (np.abs(r) > k * np.where(vol > 0, vol, 1e-9)) if k > 0 else np.ones_like(r, bool)
        t[m] = -np.sign(r[m])
    else:  # momentum
        m = (np.abs(r) > k * np.where(vol > 0, vol, 1e-9)) if k > 0 else np.ones_like(r, bool)
        t[m] = np.sign(r[m])
    return t

def h3_target(clv, vz, vzth):
    t = np.zeros_like(clv)
    m = vz > vzth
    t[m] = np.sign(clv[m])
    return t

def h4_target(ts, r, k, hour_stats):
    """hour_stats: dict hour -> (mean, tstat). Segnale solo nelle ore filtro."""
    t = np.zeros_like(r)
    hours = ((ts % 86400) // 3600).astype(int)
    for h, (mean, tst) in hour_stats.items():
        if abs(tst) > k and mean != 0:
            t[hours == h] = np.sign(mean)
    return t

def hour_stats_train(ts, r, i1):
    hours = ((ts[:i1] % 86400) // 3600).astype(int)
    out = {}
    for h in range(24):
        m = hours == h
        if m.sum() > 100:
            rr = r[:i1][m]
            mean = rr.mean(); tst = mean / (rr.std(ddof=1) + 1e-12) * np.sqrt(len(rr))
            out[h] = (float(mean), float(tst))
    return out

def backtest_fold(d, target, H, cost, i0, i1):
    en, ex, dirs, pnl = run_backtest(d, target, H, cost, i0=i0, i1=i1)
    if len(pnl) == 0:
        return None
    ts_arr = d["ts"][en]
    m = metrics(pnl, entries_ts=ts_arr)
    m["gross_total"] = float((pnl + 2 * cost).sum())
    m["entries"] = [int(x) for x in en]
    m["exits"] = [int(x) for x in ex]
    return m

def run_family(d, fam, params, Hs, blocks, cost_side, tag, mode="taker"):
    """Walk-forward su una famiglia. Ritorna report dettagliato."""
    n = d["n"]
    idx = np.searchsorted(d["ts"], [s for s, e in blocks] + [blocks[-1][1]])
    starts = idx[: len(blocks)]; ends = idx[1:]
    feats = features(d)
    res_folds = []
    chosen = []
    for b, (s0, e0) in enumerate(blocks):
        i0, i1 = starts[b], ends[b]
        best = None; best_m = None
        for p in params:
            for H in Hs:
                tgt = fam(feats, p, H, d) if tag == "h4" else fam(feats, p, d)
                if tgt is None:
                    continue
                # train: [0, i0)
                m_tr = backtest_fold(d, tgt, H, cost_side, 0, i0)
                if m_tr is None or m_tr["n"] < 10:
                    continue
                score = m_tr["tstat"] if m_tr["tstat"] > 0 else -9
                if best is None or score > best:
                    best = score
                    best_m = (p, H, m_tr)
        if best_m is None:
            res_folds.append(dict(block=b, params=None, verify=None))
            chosen.append(None)
            continue
        p_sel, H_sel, m_tr = best_m
        tgt = fam(feats, p_sel, d) if tag != "h4" else fam(feats, p_sel, H_sel, d)
        m_ve = backtest_fold(d, tgt, H_sel, cost_side, i0, i1)
        res_folds.append(dict(
            block=b, train_sel=dict(param=p_sel, H=H_sel,
                                    train_tstat=round(m_tr["tstat"], 2),
                                    train_total=round(m_tr["total"], 5)),
            verify=({k: (round(v, 6) if isinstance(v, float) else v) for k, v in m_ve.items()
                     if k not in ("entries", "exits", "daily_pnl")} if m_ve else None)))
        chosen.append((p_sel, H_sel))
    return res_folds, chosen

def mc_and_sens(d, target, H, cost_side, blocks, starts, ends, fam_tag=None):
    """Aggrega OOS: PnL per blocco + MC bootstrap + sens costo x1.5."""
    all_en = []; all_pnl = []
    for b in range(len(blocks)):
        t = target if fam_tag else target
        en, ex, dirs, pnl = run_backtest(d, t, H, cost_side, i0=starts[b], i1=ends[b])
        all_en.append(en); all_pnl.append(pnl)
    en = np.concatenate(all_en) if all_en else np.array([], int)
    pnl = np.concatenate(all_pnl) if all_pnl else np.array([])
    m = metrics(pnl, entries_ts=d["ts"][en] if len(en) else None)
    m["gross_total"] = float((pnl + 2 * cost_side).sum()) if len(pnl) else 0.0
    mc = montecarlo(m.get("daily_pnl", {})) if m.get("daily_pnl") else (0, 0, 0, 0)
    m15 = metrics(pnl - 2 * (cost_side * 0.5), entries_ts=d["ts"][en] if len(en) else None) if len(pnl) else None
    return m, mc, m15, en, pnl

def main():
    symbols = ["BTC/USDT", "ETH/USDT"]
    cost_taker = FEE_TAKER + SLIP   # 0.0014
    cost_maker = FEE_MAKER + SLIP   # 0.0012
    report = {"costi": dict(fee_taker=FEE_TAKER, fee_maker=FEE_MAKER, slippage=SLIP,
                            rt_taker=2 * cost_taker, rt_maker=2 * cost_maker),
              "ipotesi": {}}
    for sym in symbols:
        d = load_ohlcv(sym)
        d["n"] = len(d["open"])
        print(f"== {sym} bars={d['n']} {d['ts'][0]:.0f}..{d['ts'][-1]:.0f}", flush=True)
        feats = features(d)
        blocks = fold_bounds(d["ts"])
        idx = np.searchsorted(d["ts"], [s for s, e in blocks] + [blocks[-1][1]])
        starts = idx[: len(blocks)]; ends = idx[1:]
        print(f"   fold blocks: {[(int(s//86400), int(e//86400)) for s,e in blocks]}", flush=True)

        fams = [
            ("H1_reversal_z", lambda f, p, dd: h1_target(f["z"], p), [1.5, 2.0, 2.5, 3.0], [3, 6, 12], "h1"),
            ("H2_autocorr_contrarian", lambda f, p, dd: h2_target(f["r"], f["vol"], p, "contrarian"), [0.0, 0.5, 1.0, 1.5], [1, 2, 3, 6], "h2c"),
            ("H2b_autocorr_momentum", lambda f, p, dd: h2_target(f["r"], f["vol"], p, "momentum"), [0.0, 0.5, 1.0], [3, 6, 12], "h2m"),
            ("H3_clv_volume", lambda f, p, dd: h3_target(f["clv"], f["vz"], p), [0.5, 1.0, 1.5, 2.0], [3, 6, 12], "h3"),
        ]
        for name, fam, params, Hs, tag in fams:
            folds, chosen = run_family(d, fam, params, Hs, blocks, cost_taker, tag)
            # parametro "consenso": il piu' scelto nelle fold; aggrega OOS con quello
            from collections import Counter
            if all(c is None for c in chosen):
                print(f"   {name}: nessun trade", flush=True)
                report["ipotesi"][f"{sym}|{name}"] = dict(folds=folds, oos=None)
                continue
            cnt = Counter(c for c in chosen if c is not None)
            (p_sel, H_sel), _ = cnt.most_common(1)[0]
            tgt = fam(feats, p_sel, d)
            m_oos, mc, m15, en, pnl = mc_and_sens(d, tgt, H_sel, cost_taker, blocks, starts, ends)
            print(f"   {name}: sel={p_sel},{H_sel} n={m_oos['n']} tot={m_oos['total']*100:.2f}% "
                  f"tstat={m_oos['tstat']:.2f} wr={m_oos['winrate']*100:.1f}% "
                  f"mdd={m_oos['maxdd']*100:.2f}% dSharpe={m_oos.get('daily_sharpe',0):.2f} "
                  f"MCp5={mc[0]*100:.2f}% | x1.5fee tot={(m15['total'] if m15 else 0)*100:.2f}%", flush=True)
            report["ipotesi"][f"{sym}|{name}"] = dict(
                chosen_params=dict(param=p_sel, H=H_sel),
                folds=[{k: v for k, v in f.items() if k != "verify"} | {"verify": f["verify"]} for f in folds],
                oos=dict(n=m_oos["n"], total=round(float(m_oos["total"]), 6),
                         tstat=round(m_oos["tstat"], 3), winrate=round(m_oos["winrate"], 4),
                         maxdd=round(float(m_oos["maxdd"]), 6),
                         daily_sharpe=round(m_oos.get("daily_sharpe", 0.0), 3),
                         gross_total=round(float(m_oos["gross_total"]), 6),
                         mc_p5_total=round(float(mc[0]), 6), mc_p5_mdd=round(float(mc[1]), 6),
                         mc_mean_total=round(float(mc[2]), 6),
                         fee150_total=round(float(m15["total"]), 6) if m15 else None,
                         blocks_positive=sum(1 for f in folds if f["verify"] and f["verify"]["total"] > 0),
                         n_blocks=len(folds)))
            # salva trade OOS per ispezione
            np.save(f"{OUT}/trades_{sym.replace('/', '')}_{name}.npy",
                    np.vstack([d["ts"][en], pnl]).T)

        # H4 stagionalita' oraria (parametri: k filtro t-stat, H=1)
        for k in [0.0, 1.0, 2.0]:
            name = f"H4_hourly_k{k}"
            folds_all = []
            chosen_all = []
            for b, (s0, e0) in enumerate(blocks):
                i0, i1 = starts[b], ends[b]
                hs = hour_stats_train(d["ts"], feats["r"], i0)
                tgt = h4_target(d["ts"], feats["r"], k, hs)
                m_tr = backtest_fold(d, tgt, 1, cost_taker, 0, i0)
                m_ve = backtest_fold(d, tgt, 1, cost_taker, i0, i1)
                folds_all.append(dict(block=b, verify=({kk: (round(vv, 6) if isinstance(vv, float) else vv)
                                                         for kk, vv in m_ve.items()
                                                         if kk not in ("entries", "exits", "daily_pnl")} if m_ve else None)))
            hs = hour_stats_train(d["ts"], feats["r"], len(d["ts"]))
            tgt = h4_target(d["ts"], feats["r"], k, hs)
            m_oos, mc, m15, en, pnl = mc_and_sens(d, tgt, 1, cost_taker, blocks, starts, ends)
            print(f"   {name}: n={m_oos['n']} tot={m_oos['total']*100:.3f}% tstat={m_oos['tstat']:.2f} "
                  f"wr={m_oos['winrate']*100:.1f}% MCp5={mc[0]*100:.2f}% x1.5={m15['total']*100 if m15 else 0:.3f}%", flush=True)
            report["ipotesi"][f"{sym}|{name}"] = dict(
                folds=folds_all,
                oos=dict(n=m_oos["n"], total=round(float(m_oos["total"]), 6),
                         tstat=round(m_oos["tstat"], 3), winrate=round(m_oos["winrate"], 4),
                         maxdd=round(float(m_oos["maxdd"]), 6),
                         daily_sharpe=round(m_oos.get("daily_sharpe", 0.0), 3),
                         mc_p5_total=round(float(mc[0]), 6),
                         fee150_total=round(float(m15["total"]), 6) if m15 else None,
                         blocks_positive=sum(1 for f in folds_all if f["verify"] and f["verify"]["total"] > 0),
                         n_blocks=len(folds_all)))
    with open(f"{OUT}/risultati_ohlcv.json", "w") as f:
        json.dump(report, f, indent=1, default=str)
    print(f"done in {time.time()-T0:.0f}s", flush=True)

if __name__ == "__main__":
    main()
