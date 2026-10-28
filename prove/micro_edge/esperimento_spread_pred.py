#!/usr/bin/env python3
"""H5: predittivita' dello spread (campionato 5-min, Bybit+Bitvavo, 8 monete)
sul ritorno mid forward 5-30 min. Split temporale: sett.1 train, sett.2 verify.
Costi taker 0.14%/lato (realistici OKX EEA; spread misurato su Bybit come proxy).
"""
import sys, csv, json
import numpy as np
sys.path.insert(0, "/home/sergio/money/prove/micro_edge")
from engine import FEE_TAKER, SLIP

DATA = "/home/sergio/money/data/spread/spread.csv"

def load():
    rows = {}
    with open(DATA) as f:
        r = csv.DictReader(f)
        for row in r:
            if row["esito"] != "ok" or not row.get("bid") or not row.get("ask"):
                continue
            ts = row["istante"].replace("T", " ").replace("+00:00", "")
            t = int(np.datetime64(ts).astype("datetime64[s]").astype(int))
            key = (row["base"], row["venue"])
            rows.setdefault(key, []).append((t, float(row["bid"]), float(row["ask"])))
    out = {}
    for k, v in rows.items():
        v.sort()
        out[k] = (np.array([x[0] for x in v]), np.array([x[1] for x in v]), np.array([x[2] for x in v]))
    return out

def series(data):
    ts, b, a = data
    mid = (b + a) / 2
    spr = (a - b) / mid  # spread relativo
    r = np.zeros(len(mid)); r[1:] = np.diff(np.log(mid))
    # z-score spread vs media mobile 1 giorno (288 slot), causale
    w = 288
    cs = np.cumsum(spr); cs2 = np.cumsum(spr * spr)
    m = (cs[w:] - cs[:-w]) / w
    var = np.clip((cs2[w:] - cs2[:-w]) / w - m * m, 1e-30, None)
    zz = np.where(np.sqrt(var) > 0, (spr[w:] - m) / np.sqrt(var), 0.0)
    z = np.concatenate([np.zeros(w), zz])
    return ts, mid, spr, r, z

def main():
    data = load()
    report = {}
    for key in sorted(data):
        base, venue = key
        ts, mid, spr, r, z = series(data[key])
        n = len(ts)
        if n < 1000:
            continue
        # split: prima meta' train, seconda verifica
        half = n // 2
        out = {}
        for h, lab in ((1, "5m"), (3, "15m"), (6, "30m")):
            y = np.zeros(n); y[h:] = np.log(mid[h:] / mid[:-h])
            def ic(xa, ya):
                c = np.corrcoef(xa, ya)[0, 1]
                t = c * np.sqrt(len(xa) - 2) / np.sqrt(1 - c * c)
                return float(c), float(t), len(xa)
            out[f"ic_{lab}"] = dict(train=ic(z[:half], y[:half]), verify=ic(z[half:], y[half:]))
            # strategia: spread z>th -> short (ritorno atteso negativo? da testare entrambi i segni su train)
            def strat(i0, i1, sign_):
                pnl = []
                i = i0
                while i < i1 - h - 1:
                    if abs(z[i]) > 2.0:
                        pnl.append(sign_ * (np.log(mid[i + 1 + h]) - np.log(mid[i + 1])) - 2 * (FEE_TAKER + SLIP))
                        i += h + 1
                    else:
                        i += 1
                return np.array(pnl)
            for sgn, name in ((1, "long_on_wide"), (-1, "short_on_wide")):
                ptr = strat(0, half, sgn)
                if len(ptr) < 5:
                    continue
                pv = strat(half, n, sgn)
                out[f"strat_{name}_{lab}"] = dict(
                    train=dict(n=len(ptr), total=float(ptr.sum()), tstat=float(ptr.mean() / (ptr.std(ddof=1) + 1e-12) * np.sqrt(len(ptr)))),
                    verify=dict(n=len(pv), total=float(pv.sum()),
                                tstat=float(pv.mean() / (pv.std(ddof=1) + 1e-12) * np.sqrt(len(pv))) if len(pv) else None))
        report[f"{base}_{venue}"] = dict(n_slots=n, spread_med_bps=float(np.median(spr) * 1e4),
                                        start=ts[0], end=ts[-1], **out)
        print(f"{base}_{venue}: n={n} spread_med={np.median(spr)*1e4:.2f}bps", flush=True)
    with open("/home/sergio/money/prove/micro_edge/risultati_spread_pred.json", "w") as f:
        json.dump(report, f, indent=1, default=str)
    print("done")

if __name__ == "__main__":
    main()
