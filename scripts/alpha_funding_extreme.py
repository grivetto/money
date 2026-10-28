#!/usr/bin/env python3
"""alpha_funding_extreme.py — Funding Extreme Contrarian (Crowding Unwind).

Ipotesi pre-registrata: docs/ipotesi/funding_extreme_contrarian.md
Dati reali: data/funding_bybit/*.json (58 simboli, 8h) + data/cache/bybit_*_1d.json
Regola: nessun numero inventato; il verdetto lo dà il cancello (src/money/cancello.py).

Uso:
  .venv/bin/python scripts/alpha_funding_extreme.py
"""
from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
FUNDING = ROOT / "data" / "funding_bybit"
CACHE = ROOT / "data" / "cache"
OUT = ROOT / "prove" / "alpha_funding_extreme"

DAY_MS = 86_400_000
FEE_RT = 0.0030          # round trip conservativo (spot taker 0.10% x2 + slippage 0.05% x2)
NOTIONAL = 50.0          # EUR per trade
FEE_EUR = FEE_RT * NOTIONAL


def load_funding(symbol: str) -> dict[int, float]:
    p = FUNDING / f"{symbol}.json"
    if not p.exists():
        return {}
    d = json.loads(p.read_text())
    per_day: dict[int, list[float]] = defaultdict(list)
    for ts, rate in d.get("osservazioni", []):
        per_day[int(ts) // DAY_MS].append(float(rate))
    return {day: sum(v) for day, v in per_day.items() if len(v) >= 2}


def load_closes(symbol: str) -> dict[int, float]:
    base = symbol[:-4] if symbol.endswith("USDT") else symbol
    p = CACHE / f"bybit_{base}-USDT_1d.json"
    if not p.exists():
        return {}
    d = json.loads(p.read_text())
    out = {}
    for bar in d.get("barre", []):
        ts, _o, _h, _l, c, _v = bar[:6]
        out[int(ts) // DAY_MS] = float(c)
    return out


def zscores(funding: dict[int, float], window: int = 30, min_valid: int = 25) -> dict[int, float]:
    days = sorted(funding)
    out = {}
    for i in range(window, len(days)):
        hist = [funding[d] for d in days[i - window:i]]
        if len(hist) < min_valid:
            continue
        mu = float(np.mean(hist))
        sd = float(np.std(hist, ddof=1))
        if sd <= 0:
            continue
        out[days[i]] = (funding[days[i]] - mu) / sd
    return out


def build_trades(symbol: str, z: dict[int, float], closes: dict[int, float],
                 z_thr: float, hold: int) -> list[dict]:
    trades = []
    busy_until = -1
    for day in sorted(z):
        if day <= busy_until:
            continue
        if abs(z[day]) <= z_thr:
            continue
        if day not in closes or (day + hold) not in closes:
            continue
        entry, exit_ = closes[day], closes[day + hold]
        if entry <= 0:
            continue
        direction = -1 if z[day] > 0 else 1
        gross = direction * (exit_ / entry - 1.0)
        net = gross - FEE_RT
        trades.append({
            "symbol": symbol, "day": day, "z": z[day], "dir": direction,
            "gross": gross, "net": net, "pnl_eur": net * NOTIONAL,
        })
        busy_until = day + hold - 1
    return trades


def metrics(trades: list[dict]) -> dict:
    if not trades:
        return {"n": 0}
    r = np.array([t["net"] for t in trades], dtype=float)
    pnl = np.array([t["pnl_eur"] for t in trades], dtype=float)
    n = len(r)
    mean = float(r.mean())
    sd = float(r.std(ddof=1)) if n > 1 else 0.0
    t_stat = mean / (sd / math.sqrt(n)) if sd > 0 else 0.0
    gains = float(r[r > 0].sum())
    losses = float(abs(r[r < 0].sum()))
    pf = gains / losses if losses > 0 else float("inf")
    cum = np.cumsum(pnl)
    peak = np.maximum.accumulate(cum)
    dd = (cum - peak) / (np.abs(peak) + 1e-9)
    max_dd = float(abs(dd.min())) if n else 0.0
    rng = np.random.default_rng(42)
    means = np.array([rng.choice(r, size=n, replace=True).mean() for _ in range(5000)])
    ci_lo, ci_hi = np.percentile(means, [5, 95])
    return {
        "n": n, "mean_net": mean, "mean_pnl_eur": float(pnl.mean()),
        "sd": sd, "t_stat": t_stat, "pf": pf, "max_dd": max_dd,
        "ci_lo": float(ci_lo), "ci_hi": float(ci_hi),
        "win_rate": float((r > 0).mean()),
        "expectancy_vs_fee": mean / FEE_RT,
    }


def gate(trades: list[dict]) -> dict:
    sys.path.insert(0, str(ROOT / "src"))
    from money.cancello import promossa
    ok, rep = promossa([t["pnl_eur"] for t in trades], fee_per_trade=FEE_EUR)
    return {"pass": ok, **rep}


def run(symbols, z_thr, hold):
    trades = []
    for sym in symbols:
        f = load_funding(sym)
        c = load_closes(sym)
        if not f or not c:
            continue
        trades.extend(build_trades(sym, zscores(f), c, z_thr, hold))
    return trades


def year_of(day: int) -> int:
    return datetime.fromtimestamp(day * 86400, tz=timezone.utc).year


def main():
    symbols = sorted(p.stem for p in FUNDING.glob("*.json"))
    print(f"Simboli funding: {len(symbols)}")
    trades = run(symbols, 2.0, 3)
    print(f"Trade (|z|>2, H=3): {len(trades)}")
    m = metrics(trades)
    print("=== METRICHE PRIMARIE ===")
    for k, v in m.items():
        print(f"  {k}: {v}")
    g = gate(trades)
    print("=== CANCELLO (fee 0.15€/trade) ===")
    for k, v in g.items():
        print(f"  {k}: {v}")

    for side, sel in (("funding>0 (short)", lambda t: t["z"] > 0),
                      ("funding<0 (long)", lambda t: t["z"] < 0)):
        sub = [t for t in trades if sel(t)]
        mm = metrics(sub)
        print(f"  lato {side}: n={mm.get('n')} mean={mm.get('mean_net', 0):.5f} "
              f"t={mm.get('t_stat', 0):.2f}")

    by_year = defaultdict(list)
    for t in trades:
        by_year[year_of(t["day"])].append(t)
    print("=== PER ANNO ===")
    for y in sorted(by_year):
        mm = metrics(by_year[y])
        print(f"  {y}: n={mm.get('n')} mean={mm.get('mean_net', 0):.5f} "
              f"t={mm.get('t_stat', 0):.2f}")

    print("=== SENSITIVITY (riportata, NON selezione) ===")
    for hold in (1, 3, 5, 7):
        for zt in (1.5, 2.0, 2.5, 3.0):
            tr = run(symbols, zt, hold)
            mm = metrics(tr)
            print(f"  H={hold} |z|>{zt}: n={mm.get('n')} mean={mm.get('mean_net', 0):.5f} "
                  f"t={mm.get('t_stat', 0):.2f} pf={mm.get('pf', 0):.2f} "
                  f"dd={mm.get('max_dd', 0):.3f}")

    ann_eur = m.get("mean_pnl_eur", 0.0) * (365 / 3)
    print(f"=== RENDITA ANNUALIZZATA CORRETTA (H=3): {ann_eur:.2f}€/anno "
          f"su {NOTIONAL}€/trade ===")

    OUT.mkdir(parents=True, exist_ok=True)
    payload = {
        "config": {"z_thr": 2.0, "hold": 3, "fee_rt": FEE_RT, "notional": NOTIONAL},
        "metrics": m, "gate": g, "n_trades": len(trades), "trades": trades,
    }
    (OUT / "result.json").write_text(json.dumps(payload, indent=2))
    print(f"Salvato: {OUT / 'result.json'}")


if __name__ == "__main__":
    main()
