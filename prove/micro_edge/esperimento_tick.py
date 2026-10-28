#!/usr/bin/env python3
"""Ipotesi orderflow su tick Bybit DOGE/SOL: sbilancio aggressivo 5-min
-> ritorno forward 5/15/30 min. Walk-forward: train 20 giorni (09-13..10-02),
verifica 9 giorni (10-03..10-11). Costi taker 0.14%/lato + stress 0.30%/lato.
"""
import sys, glob, json, time
import numpy as np
sys.path.insert(0, "/home/sergio/money/prove/micro_edge")
from loaders import load_tick_day, DATA
from engine import FEE_TAKER, SLIP

T0 = time.time()

def bucket_day(fn, step=300):
    """Aggrega i tick del giorno in bucket di `step` secondi.
    Ritorna: t_bucket, close(last), buy_vol, sell_vol, range (h-l)/last."""
    ts, buy, sz, px = load_tick_day(fn)
    if len(ts) == 0:
        return None
    b = (ts // step).astype(np.int64)
    tb = np.unique(b)
    n = len(tb)
    close = np.empty(n); bv = np.zeros(n); sv = np.zeros(n)
    hi = np.empty(n); lo = np.empty(n)
    # usa np.searchsorted per mappare i tick nei bucket
    idx = np.searchsorted(tb, b)
    np.maximum.at(hi, idx, px)
    np.minimum.at(lo, idx, px)
    # close = ultimo prezzo del bucket
    order = np.argsort(b, kind="stable")
    b_s = b[order]; px_s = px[order]
    # ultimo indice per bucket
    last_idx = np.r_[np.where(b_s[:-1] != b_s[1:])[0], len(b_s) - 1]
    close = px_s[last_idx]
    tb_sorted = tb
    # volumi: somme per bucket
    np.add.at(bv, idx, np.where(buy > 0, sz * px, 0.0))
    np.add.at(sv, idx, np.where(buy < 0, sz * px, 0.0))
    rng = (hi - lo) / close
    return tb_sorted * step, close, bv, sv, rng

def process_symbol(sym, files, train_files, verify_files):
    def load_days(fns):
        out = []
        for fn in fns:
            r = bucket_day(fn)
            if r is not None:
                out.append(r)
        return out
    tr = load_days(train_files)
    ve = load_days(verify_files)
    res = {"sym": sym, "n_days_train": len(tr), "n_days_verify": len(ve)}
    # statistiche di base
    vols = [np.median(c[4]) for c in tr]
    res["median_5m_range_train"] = float(np.median(vols))
    # coppie (imb, fwd ret) su train e verify
    def pairs(days, h):
        X, Y = [], []
        for (tb, close, bv, sv, rng) in days:
            imb = (bv - sv) / (bv + sv + 1e-12)
            fwd = np.log(close[h:]) - np.log(close[:-h])
            X.append(imb[:-h]); Y.append(fwd)
        return np.concatenate(X), np.concatenate(Y)
    res["ic"] = {}
    for h in (1, 3, 6):  # 5, 15, 30 min
        Xt, Yt = pairs(tr, h)
        Xv, Yv = pairs(ve, h)
        def ic(x, y):
            c = np.corrcoef(x, y)[0, 1]
            t = c * np.sqrt(len(x) - 2) / np.sqrt(1 - c * c)
            return float(c), float(t), len(x)
        res["ic"][f"h{h*5}min"] = dict(train=ic(Xt, Yt), verify=ic(Xv, Yv))
        # decili: ritorno medio per decile di imbalance (train e verify)
        q = np.quantile(Xt, np.linspace(0, 1, 11))
        d = np.digitize(Xt, q[1:-1])
        dec = [float(Yt[d == k].mean()) for k in range(10)]
        qv = np.quantile(Xv, np.linspace(0, 1, 11))
        dv = np.digitize(Xv, qv[1:-1])
        decv = [float(Yv[dv == k].mean()) for k in range(10)]
        res["ic"][f"h{h*5}min"]["deciles_train"] = dec
        res["ic"][f"h{h*5}min"]["deciles_verify"] = decv
    # strategia: |imb|>th -> segno(imb), hold h bar; th scelto su train
    for h in (1, 3, 6):
        for th in (0.1, 0.2, 0.3, 0.5):
            def strat(days):
                pnl = []
                for (tb, close, bv, sv, rng) in days:
                    imb = (bv - sv) / (bv + sv + 1e-12)
                    sig = np.where(np.abs(imb) > th, np.sign(imb), 0.0)
                    # entry al close del bucket successivo (proxy conservativo)
                    fwd = np.log(close[h:]) - np.log(close[:-h])
                    # segnali non sovrapposti: prendi sig[i], salta h barre
                    i = 0; n = len(sig) - h
                    while i < n:
                        if sig[i] != 0:
                            pnl.append(sig[i] * fwd[i])
                            i += h
                        else:
                            i += 1
                return np.array(pnl)
            ptr = strat(tr)
            if len(ptr) < 5:
                continue
            res.setdefault("strat", {})[f"h{h*5}m_th{th}"] = dict(
                train=dict(n=len(ptr), total=float(ptr.sum()), tstat=float(ptr.mean() / ptr.std(ddof=1) * np.sqrt(len(ptr))) if ptr.std(ddof=1) > 0 else 0.0,
                           wr=float((ptr > 0).mean())),
                verify=None)
    # applica su verify i top-3 (th,h) per t-stat train
    combos = []
    for h in (1, 3, 6):
        for th in (0.1, 0.2, 0.3, 0.5):
            k = f"h{h*5}m_th{th}"
            if k in res.get("strat", {}):
                combos.append((res["strat"][k]["train"]["tstat"], h, th))
    combos.sort(reverse=True)
    for tstat_tr, h, th in combos[:3]:
        def strat(days):
            pnl = []
            for (tb, close, bv, sv, rng) in days:
                imb = (bv - sv) / (bv + sv + 1e-12)
                sig = np.where(np.abs(imb) > th, np.sign(imb), 0.0)
                fwd = np.log(close[h:]) - np.log(close[:-h])
                i = 0; n = len(sig) - h
                while i < n:
                    if sig[i] != 0:
                        pnl.append(sig[i] * fwd[i]); i += h
                    else:
                        i += 1
            return np.array(pnl)
        pv = strat(ve)
        k = f"h{h*5}m_th{th}"
        if len(pv):
            pv_net = pv - 2 * (FEE_TAKER + SLIP)
            pv_net30 = pv - 2 * 0.0030
            res["strat"][k]["verify"] = dict(
                n=len(pv), gross_total=float(pv.sum()), gross_tstat=float(pv.mean() / pv.std(ddof=1) * np.sqrt(len(pv))) if pv.std(ddof=1) > 0 else 0.0,
                wr=float((pv > 0).mean()), gross_mean_bps=float(pv.mean() * 1e4),
                net_taker14_total=float(pv_net.sum()), net_taker14_mean_bps=float(pv_net.mean() * 1e4),
                net_stress30_total=float(pv_net30.sum()))
    return res

def main():
    allfiles = {}
    for sym in ("DOGEUSDT", "SOLUSDT"):
        allfiles[sym] = sorted(glob.glob(f"{DATA}/tick/{sym}_*.csv.gz"))
    report = {"costi": dict(rt_taker14=2 * (FEE_TAKER + SLIP), rt_stress30=0.006)}
    for sym, files in allfiles.items():
        train_files = files[:20]
        verify_files = files[20:]
        print(f"== {sym}: train {len(train_files)} gg ({train_files[0].split('/')[-1]}..{train_files[-1].split('/')[-1]}), "
              f"verify {len(verify_files)} gg", flush=True)
        r = process_symbol(sym, files, train_files, verify_files)
        report[sym] = r
        print(json.dumps(r["ic"], indent=1), flush=True)
        print(json.dumps({k: v for k, v in r.get("strat", {}).items()}, indent=1), flush=True)
    with open("/home/sergio/money/prove/micro_edge/risultati_tick.json", "w") as f:
        json.dump(report, f, indent=1, default=str)
    print(f"done {time.time()-T0:.0f}s")

if __name__ == "__main__":
    main()
