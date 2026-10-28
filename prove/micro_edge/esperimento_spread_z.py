#!/usr/bin/env python3
"""Test mirato: spread z-score estremo -> ritorno forward 30-120 min.
Condizionamento per bin, strategia short-on-wide / long-on-narrow,
costi maker 0.12%/lato e taker 0.14%/lato. Train=sett.1, verify=sett.2.
Per-simbolo (bybit, proxy OKX) e pooled."""
import sys, csv, json
import numpy as np
sys.path.insert(0, "/home/sergio/money/prove/micro_edge")
from engine import FEE_TAKER, FEE_MAKER, SLIP

DATA = "/home/sergio/money/data/spread/spread.csv"

def load(venue="bybit"):
    rows = {}
    with open(DATA) as f:
        r = csv.DictReader(f)
        for row in r:
            if row["venue"] != venue or row["esito"] != "ok" or not row.get("bid") or not row.get("ask"):
                continue
            ts = row["istante"].replace("T", " ").replace("+00:00", "")
            t = int(np.datetime64(ts).astype("datetime64[s]").astype(int))
            rows.setdefault(row["base"], []).append((t, float(row["bid"]), float(row["ask"])))
    out = {}
    for k, v in rows.items():
        v.sort()
        out[k] = (np.array([x[0] for x in v]), np.array([x[1] for x in v]), np.array([x[2] for x in v]))
    return out

def zseries(data, w=288):
    ts, b, a = data
    mid = (b + a) / 2
    spr = (a - b) / mid
    cs = np.cumsum(spr); cs2 = np.cumsum(spr * spr)
    m = (cs[w:] - cs[:-w]) / w
    var = np.clip((cs2[w:] - cs2[:-w]) / w - m * m, 1e-30, None)
    z = np.concatenate([np.zeros(w), (spr[w:] - m) / np.sqrt(var)])
    return ts, mid, spr, z

def main():
    data = load("bybit")
    COST_M = FEE_MAKER + SLIP  # 0.0012
    COST_T = FEE_TAKER + SLIP  # 0.0014
    report = {"costi": dict(rt_maker=2 * COST_M, rt_taker=2 * COST_T)}
    pooled = {"train": {}, "verify": {}}
    for base in sorted(data):
        ts, mid, spr, z = zseries(data[base])
        n = len(ts); half = n // 2
        out = {}
        for h, lab in ((6, "30m"), (12, "60m"), (24, "120m")):
            y = np.zeros(n); y[h:] = np.log(mid[h:] / mid[:-h])
            # bin di z -> ritorno medio condizionato
            edges = [1, 2, 3, 4, 6]
            bins = {f"z>{e}": None for e in edges}
            for e in edges:
                mtr = z[:half] > e; mve = z[half:] > e
                if mtr.sum() > 5:
                    bins[f"z>{e}"] = dict(train=float(y[:half][mtr].mean() * 1e4), n_tr=int(mtr.sum()),
                                          verify=float(y[half:][mve].mean() * 1e4) if mve.sum() > 5 else None,
                                          n_ve=int(mve.sum()))
                mtr = z[:half] < -e; mve = z[half:] < -e
                if mtr.sum() > 5:
                    bins[f"z<-{e}"] = dict(train=float(y[:half][mtr].mean() * 1e4), n_tr=int(mtr.sum()),
                                           verify=float(y[half:][mve].mean() * 1e4) if mve.sum() > 5 else None,
                                           n_ve=int(mve.sum()))
            out[lab] = dict(bins=bins)
            for key, cond, sgn in (("short_z>th", lambda zz: zz > 3, -1), ("long_z<-th", lambda zz: zz < -3, 1)):
                for cost, cname in ((0.0, "gross"), (COST_M, "maker"), (COST_T, "taker")):
                    pnl = []
                    for seg, i0, i1 in (("train", 0, half), ("verify", half, n)):
                        i = i0
                        while i < i1 - h - 1:
                            if cond(z[i]):
                                pnl.append((sgn * (np.log(mid[i + 1 + h]) - np.log(mid[i + 1])) - 2 * cost, seg, i))
                                i += h + 1
                            else:
                                i += 1
                    tr = [p for p in pnl if p[1] == "train"]
                    ve = [p for p in pnl if p[1] == "verify"]
                    def agg(l):
                        if not l:
                            return None
                        x = np.array([q[0] for q in l])
                        return dict(n=len(x), mean_bps=float(x.mean() * 1e4), total=float(x.sum()),
                                    tstat=float(x.mean() / (x.std(ddof=1) + 1e-12) * np.sqrt(len(x))))
                    out[lab][f"{key}_{cname}"] = dict(train=agg(tr), verify=agg(ve))
                    for p in tr:
                        pooled["train"].setdefault((lab, key, cname), []).append(p[0])
                    for p in ve:
                        pooled["verify"].setdefault((lab, key, cname), []).append(p[0])
        report[base] = dict(n_slots=n, **out)
    for segname, seg in pooled.items():
        for k, v in seg.items():
            x = np.array(v)
            report.setdefault("POOLED", {})[segname + "_" + "_".join(map(str, k))] = dict(
                n=len(x), mean_bps=float(x.mean() * 1e4), total=float(x.sum()),
                tstat=float(x.mean() / (x.std(ddof=1) + 1e-12) * np.sqrt(len(x))))
    with open("/home/sergio/money/prove/micro_edge/risultati_spread_z.json", "w") as f:
        json.dump(report, f, indent=1, default=str)
    # riassunto a schermo
    for base in ("BTC", "SOL", "XRP", "DOGE", "ETH"):
        if base not in report:
            continue
        print(f"== {base}", flush=True)
        for lab in ("30m", "60m", "120m"):
            b = report[base][lab]["bins"]
            parts = []
            for k, v in b.items():
                if v:
                    ve = v.get("verify")
                    ve_s = f"{ve:+.2f}bp({v.get('n_ve')})" if isinstance(ve, (int, float)) else "-"
                    parts.append(f"{k}: tr{v['train']:+.2f}bp({v['n_tr']}) ve{ve_s}")
                else:
                    parts.append(f"{k}:-")
            print(f"  {lab}: " + "  ".join(parts), flush=True)
    print("== POOLED", flush=True)
    for k, v in report["POOLED"].items():
        print(f"  {k}: n={v['n']} mean={v['mean_bps']:+.2f}bps tot={v['total']*100:+.2f}% tstat={v['tstat']:+.1f}", flush=True)

if __name__ == "__main__":
    main()
