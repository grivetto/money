#!/usr/bin/env python3
"""Ipotesi orderflow su L2 OKX BTC-EUR (snapshot ~1-2s, 2 giorni):
sbilancio profondita' (5-50-100bp) e spread -> ritorno mid forward 5/15/30 min.
Mini walk-forward: giorno 1 train (10-23), giorno 2 verifica (10-24).
Costi taker 0.14%/lato e maker 0.12%/lato.
"""
import sys, json, time
import numpy as np
sys.path.insert(0, "/home/sergio/money/prove/micro_edge")
from loaders import load_l2, DATA
from engine import FEE_TAKER, FEE_MAKER, SLIP

T0 = time.time()

def snap_to_5m(rows):
    """Ultimo snapshot per slot 5-min; ritorna ts_slot, mid, features."""
    slots = {}
    for r in rows:
        slot = r["ts"] // 300000  # ms -> 5min
        slots[slot] = r
    ss = sorted(slots)
    mid = np.array([slots[s]["mid"] for s in ss])
    imb50 = np.array([slots[s]["imbalance_50bp"] for s in ss])
    imb100 = np.array([slots[s]["imbalance_100bp"] for s in ss])
    d5b = np.array([slots[s]["depth_bid_5bp"] for s in ss])
    d5a = np.array([slots[s]["depth_ask_5bp"] for s in ss])
    spr = np.array([slots[s]["spread_bps"] for s in ss])
    ts = np.array([s * 300 for s in ss], dtype=np.float64)
    return ts, mid, imb50, imb100, d5b, d5a, spr

def ic(x, y):
    if len(x) < 30:
        return None
    c = np.corrcoef(x, y)[0, 1]
    t = c * np.sqrt(len(x) - 2) / np.sqrt(1 - c * c)
    return float(c), float(t), len(x)

def strat(mid, sig_feat, th, h, cost):
    """segnale: sign(feat) se |feat|>th, hold h barre, entry=mid del bar successivo."""
    n = len(mid)
    pnl = []
    i = 0
    while i < n - h - 1:
        f = sig_feat[i]
        if abs(f) > th:
            entry = mid[i + 1]
            exit_ = mid[i + 1 + h]
            pnl.append(np.sign(f) * np.log(exit_ / entry) - 2 * cost)
            i += h + 1
        else:
            i += 1
    return np.array(pnl)

def main():
    files = [f"{DATA}/l2/BTC-EUR_2026-10-23.jsonl", f"{DATA}/l2/BTC-EUR_2026-10-24.jsonl"]
    rows1 = load_l2(files[:1]); rows2 = load_l2(files[1:])
    tr = snap_to_5m(rows1); ve = snap_to_5m(rows2)
    print(f"train slots={len(tr[1])} verify slots={len(ve[1])}", flush=True)
    r1 = np.log(tr[1][1:] / tr[1][:-1])
    r2 = np.log(ve[1][1:] / ve[1][:-1])
    print(f"5m mid std train={r1.std()*1e4:.2f}bps verify={r2.std()*1e4:.2f}bps", flush=True)
    print(f"spread_bps: train med={np.median(tr[6]):.2f} verify med={np.median(ve[6]):.2f}", flush=True)
    report = {"train_5m_std_bps": float(r1.std() * 1e4), "verify_5m_std_bps": float(r2.std() * 1e4),
              "train_spread_med_bps": float(np.median(tr[6])), "verify_spread_med_bps": float(np.median(ve[6])),
              "ic": {}, "strat": {}}
    feats = {"imb50": tr[2], "imb100": tr[3], "depth_ratio_5bp": (tr[4] - tr[5]) / (tr[4] + tr[5] + 1e-12),
             "spread": tr[6]}
    feats_v = {"imb50": ve[2], "imb100": ve[3], "depth_ratio_5bp": (ve[4] - ve[5]) / (ve[4] + ve[5] + 1e-12),
               "spread": ve[6]}
    for h, label in ((1, "5m"), (3, "15m"), (6, "30m")):
        yt = np.log(tr[1][h:] / tr[1][:-h]); yv = np.log(ve[1][h:] / ve[1][:-h])
        for fname, xt in feats.items():
            xv = feats_v[fname]
            report["ic"][f"{fname}_{label}"] = dict(
                train=ic(xt[:-h], yt), verify=ic(xv[:-h], yv))
    # strategia: scegli (feat, th) su train per t-stat, verifica su day2
    combos = []
    for fname, xt in feats.items():
        for h, label in ((1, "5m"), (3, "15m"), (6, "30m")):
            yt = np.log(tr[1][h:] / tr[1][:-h])
            for th in (0.1, 0.2, 0.3, 0.5, 0.7):
                p = strat(tr[1], xt, th, h, FEE_TAKER + SLIP)
                if len(p) < 5:
                    continue
                tst = p.mean() / (p.std(ddof=1) + 1e-12) * np.sqrt(len(p))
                combos.append((tst, fname, h, th, len(p), float(p.sum())))
    combos.sort(reverse=True)
    for tst, fname, h, th, ntr, tot_tr in combos[:3]:
        pv = strat(ve[1], feats_v[fname], th, h, FEE_TAKER + SLIP)
        pv_gross = strat(ve[1], feats_v[fname], th, h, 0.0)
        pv_maker = strat(ve[1], feats_v[fname], th, h, FEE_MAKER + SLIP)
        report["strat"][f"{fname}_h{h*5}m_th{th}"] = dict(
            train=dict(tstat=round(tst, 2), n=ntr, total=round(tot_tr, 5)),
            verify=dict(n=len(pv),
                        gross_mean_bps=round(float(pv_gross.mean() * 1e4), 3) if len(pv_gross) else None,
                        net_taker_mean_bps=round(float(pv.mean() * 1e4), 3) if len(pv) else None,
                        net_taker_total=round(float(pv.sum()), 5) if len(pv) else None,
                        net_maker_mean_bps=round(float(pv_maker.mean() * 1e4), 3) if len(pv_maker) else None,
                        tstat=round(float(pv.mean() / (pv.std(ddof=1) + 1e-12) * np.sqrt(len(pv))), 2) if len(pv) else None,
                        wr=round(float((pv > 0).mean()), 3) if len(pv) else None))
        print(f"{fname} h{h*5}m th{th}: train tstat={tst:.2f} n={ntr} -> verify n={len(pv)} "
              f"net_taker_mean={pv.mean()*1e4:.2f}bps tot={pv.sum()*100:.3f}%", flush=True)
    with open("/home/sergio/money/prove/micro_edge/risultati_l2.json", "w") as f:
        json.dump(report, f, indent=1, default=str)
    print(f"done {time.time()-T0:.0f}s")

if __name__ == "__main__":
    main()
